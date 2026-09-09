#!/usr/bin/env python3
"""Runtime adapter connecting Instagram collection health to AI Reliability v8.

The AI path is strictly advisory.  It can rank review urgency and train a
candidate only after the existing v8 real-label gates pass.  It can never mark
facts verified, override collection health, or authorize production.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from ai_reliability_v8.adaptive_learning import AdaptiveEvidenceLearner
from ai_reliability_v8.diverse_collection import SourceCoveragePlanner
from ai_reliability_v8.evidence_learning import FEATURES, MIN_REAL_LABELS
from instagram_tcg_content.automation_state_guard import (
    AI_RELIABILITY_PROJECT,
    AI_RELIABILITY_TASK_ID,
    CANONICAL_ID,
    build_ai_reliability_bridge,
)

ROOT = Path(__file__).resolve().parents[1]
BINDING_PATH = ROOT / "ai_reliability_v8" / "binding.json"
DEFAULT_MODEL = ROOT / "TCG_CROSSCHECK" / "IG_CARDINFO" / "ai_reliability" / "model.json"
DEFAULT_LABELS = ROOT / "TCG_CROSSCHECK" / "IG_CARDINFO" / "ai_reliability" / "independent_labels.json"
DEFAULT_STATE_ROOT = ROOT / "TCG_CROSSCHECK" / "IG_CARDINFO" / "ai_reliability" / "runtime"
PURPOSE = "verification_review"
REVISION = "v8-integration"
EXPECTED_OUTPUT_KEYS = (
    "pokemon:KR",
    "pokemon:EN",
    "one_piece:KR",
    "one_piece:EN",
    "naruto:KR",
    "naruto:EN",
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_binding_integrity(binding_path: Path = BINDING_PATH) -> dict[str, Any]:
    binding = _read_json(binding_path)
    errors: list[str] = []
    if binding.get("project") != AI_RELIABILITY_PROJECT or AI_RELIABILITY_PROJECT != "instagram_card":
        errors.append("PROJECT_BINDING_MISMATCH")
    if binding.get("task_id") != AI_RELIABILITY_TASK_ID or AI_RELIABILITY_TASK_ID != CANONICAL_ID:
        errors.append("TASK_BINDING_MISMATCH")
    if binding.get("schema_version") != 8:
        errors.append("BINDING_SCHEMA_MISMATCH")

    policy = binding.get("integration_policy")
    if not isinstance(policy, dict):
        errors.append("INTEGRATION_POLICY_MISSING")
        policy = {}
    if policy.get("model_update_min_real_labels") != MIN_REAL_LABELS:
        errors.append("REAL_LABEL_GATE_MISMATCH")
    if policy.get("synthetic_or_ai_self_labels_forbidden") is not True:
        errors.append("SYNTHETIC_LABEL_POLICY_MISMATCH")
    if policy.get("neural_hidden_sizes") != [4, 8, 12]:
        errors.append("HIDDEN_SIZE_POLICY_MISMATCH")
    if policy.get("temporal_split") != "50_15_15_20":
        errors.append("TEMPORAL_SPLIT_POLICY_MISMATCH")

    files = binding.get("files")
    if not isinstance(files, dict) or not files:
        errors.append("BINDING_FILES_MISSING")
        files = {}
    root = binding_path.parent
    checked = 0
    for name, expected in files.items():
        path = root / str(name)
        if not path.is_file():
            errors.append(f"BINDING_FILE_MISSING:{name}")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            errors.append(f"BINDING_HASH_MISMATCH:{name}")
        checked += 1

    return {
        "status": "PASS" if not errors else "FAIL",
        "project": binding.get("project"),
        "task_id": binding.get("task_id"),
        "schema_version": binding.get("schema_version"),
        "checked_file_count": checked,
        "minimum_real_labels": policy.get("model_update_min_real_labels"),
        "errors": errors,
    }


def _bounded_ratio(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def collection_features(report: dict[str, Any]) -> dict[str, float]:
    if not isinstance(report, dict):
        raise ValueError("COLLECTION_REPORT_REQUIRED")

    matrix = report.get("matrix_counts")
    completed = report.get("completed_sale_counts")
    reasons = report.get("reasons")
    route_problems = report.get("route_problems")
    if not isinstance(matrix, dict) or not isinstance(completed, dict):
        raise ValueError("COLLECTION_COVERAGE_REQUIRED")
    if not isinstance(reasons, list) or not isinstance(route_problems, list):
        raise ValueError("COLLECTION_HEALTH_FIELDS_REQUIRED")

    populated = sum(1 for key in EXPECTED_OUTPUT_KEYS if int(matrix.get(key) or 0) > 0)
    field_completeness = populated / len(EXPECTED_OUTPUT_KEYS)

    completed_support = sum(
        min(1.0, max(0.0, float(completed.get(key) or 0) / 10.0))
        for key in EXPECTED_OUTPUT_KEYS
    ) / len(EXPECTED_OUTPUT_KEYS)

    age = report.get("snapshot_age_hours")
    if type(age) not in (int, float):
        freshness = 0.0
    else:
        freshness = _bounded_ratio(1.0 - max(0.0, float(age)) / 36.0)

    source_match = _bounded_ratio(1.0 - len(route_problems) / 9.0)
    conflict = 1.0 if any(
        token in str(reason)
        for reason in reasons
        for token in ("CONFLICT", "DUPLICATE")
    ) else 0.0
    parser_health = 0.0 if any(
        token in str(reason)
        for reason in reasons
        for token in ("MALFORMED", "LATEST_COLLECTION_ATTEMPT_NOT_READY")
    ) else 1.0

    features = {
        "source_match": source_match,
        "freshness": freshness,
        "independent_support": completed_support,
        "field_completeness": field_completeness,
        "conflict": conflict,
        "parser_health": parser_health,
    }
    if set(features) != set(FEATURES):
        raise ValueError("AI_FEATURE_SCHEMA_MISMATCH")
    return {key: _bounded_ratio(value) for key, value in features.items()}


def load_optional_model(path: Path = DEFAULT_MODEL) -> tuple[dict[str, Any] | None, str]:
    if not path.is_file():
        return None, "MODEL_FILE_ABSENT"
    value = _read_json(path)
    if not isinstance(value, dict):
        return None, "MODEL_FILE_INVALID"
    return value, "MODEL_FILE_PRESENT"


def load_optional_labels(path: Path = DEFAULT_LABELS) -> tuple[list[dict[str, Any]], str]:
    if not path.is_file():
        return [], "LABEL_FILE_ABSENT"
    value = _read_json(path)
    rows = value.get("rows") if isinstance(value, dict) else value
    if not isinstance(rows, list):
        raise ValueError("LABEL_FILE_SCHEMA_INVALID")
    return rows, "LABEL_FILE_PRESENT"


def evaluate_ai_runtime(
    collection_report: dict[str, Any],
    *,
    state_root: Path = DEFAULT_STATE_ROOT,
    model_path: Path = DEFAULT_MODEL,
    labels_path: Path = DEFAULT_LABELS,
) -> dict[str, Any]:
    binding = verify_binding_integrity()
    if binding["status"] != "PASS":
        return {
            "connection_status": "BINDING_FAILED_RULES_ONLY",
            "binding": binding,
            "neural_active": False,
            "training_status": "KEEP_EXISTING_MODEL_NO_TRAINING",
            "can_verify": False,
            "can_override_collection_health": False,
            "can_authorize_production": False,
        }

    bridge = build_ai_reliability_bridge(state_root)
    learner = bridge.evidence_learner(purpose=PURPOSE, revision=REVISION)
    if not isinstance(learner, AdaptiveEvidenceLearner):
        raise RuntimeError("ADAPTIVE_LEARNER_NOT_CONNECTED")

    features = collection_features(collection_report)
    labels, labels_status = load_optional_labels(labels_path)
    label_audit = bridge.source_coverage_planner().audit_labels(labels)
    training_status = (
        "TRAINING_ELIGIBLE_REAL_LABEL_GATE_PASSED"
        if label_audit.get("ready_for_training") is True
        else "KEEP_EXISTING_MODEL_NO_TRAINING"
    )

    model, model_status = load_optional_model(model_path)
    if model is None:
        ranking = learner.rank(features, None)
        model_status = "RULES_ONLY_NO_OPERATIONAL_MODEL"
    else:
        try:
            ranking = learner.rank(features, model)
        except ValueError as exc:
            ranking = learner.rank(features, None)
            model_status = f"MODEL_REJECTED_RULES_ONLY:{type(exc).__name__}:{exc}"

    if ranking.get("can_verify") is not False:
        raise RuntimeError("AI_VERIFICATION_AUTHORITY_BREACH")

    return {
        "connection_status": "CONNECTED_ADVISORY_ONLY",
        "binding": binding,
        "features": features,
        "model_status": model_status,
        "labels_status": labels_status,
        "label_audit": label_audit,
        "training_status": training_status,
        "neural_active": ranking.get("status") == "ADVISORY_ONLY",
        "ranking": ranking,
        "collection_health_status": collection_report.get("status"),
        "collection_health_unchanged": True,
        "can_verify": False,
        "can_override_collection_health": False,
        "can_authorize_production": False,
        "next_action": (
            "COLLECT_INDEPENDENT_HUMAN_OR_EXTERNAL_OUTCOME_LABELS"
            if training_status == "KEEP_EXISTING_MODEL_NO_TRAINING"
            else "TRAIN_CANDIDATE_THROUGH_V8_GATES"
        ),
    }


def train_candidate_if_ready(
    *,
    labels_path: Path = DEFAULT_LABELS,
    model_path: Path = DEFAULT_MODEL,
    state_root: Path = DEFAULT_STATE_ROOT,
) -> dict[str, Any]:
    binding = verify_binding_integrity()
    if binding["status"] != "PASS":
        return {"status": "BINDING_FAILED_KEEP_EXISTING_MODEL", "binding": binding}

    rows, labels_status = load_optional_labels(labels_path)
    bridge = build_ai_reliability_bridge(state_root)
    audit = bridge.source_coverage_planner().audit_labels(rows)
    if audit.get("ready_for_training") is not True:
        return {
            "status": "KEEP_EXISTING_MODEL_NO_TRAINING",
            "labels_status": labels_status,
            "label_audit": audit,
            "existing_model_preserved": True,
        }

    learner = bridge.evidence_learner(purpose=PURPOSE, revision=REVISION)
    report = learner.fit(rows)
    save = learner.save_model(report, model_path)
    return {
        "status": report.get("status"),
        "labels_status": labels_status,
        "label_audit": audit,
        "save": save,
        "can_verify": False,
        "can_authorize_production": False,
    }


def self_test() -> None:
    healthy = {
        "status": "READY",
        "snapshot_age_hours": 3.0,
        "matrix_counts": {key: 12 for key in EXPECTED_OUTPUT_KEYS},
        "completed_sale_counts": {key: 10 for key in EXPECTED_OUTPUT_KEYS},
        "route_problems": [],
        "reasons": [],
    }
    features = collection_features(healthy)
    assert set(features) == set(FEATURES), features
    assert features["field_completeness"] == 1.0, features
    assert features["independent_support"] == 1.0, features

    thin = {
        "status": "NOT_READY",
        "snapshot_age_hours": 72.0,
        "matrix_counts": {key: 0 for key in EXPECTED_OUTPUT_KEYS},
        "completed_sale_counts": {key: 0 for key in EXPECTED_OUTPUT_KEYS},
        "route_problems": ["route"],
        "reasons": ["OUTPUT_MATRIX_COVERAGE_MISSING", "LATEST_COLLECTION_ATTEMPT_NOT_READY:NO_VERIFIED_FACTS"],
    }
    low = collection_features(thin)
    assert low["freshness"] == 0.0 and low["field_completeness"] == 0.0, low

    binding = verify_binding_integrity()
    assert binding["status"] == "PASS", binding
    print("Instagram AI reliability runtime link: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--collection-report")
    parser.add_argument("--model", default=str(DEFAULT_MODEL))
    parser.add_argument("--labels", default=str(DEFAULT_LABELS))
    parser.add_argument("--state-root", default=str(DEFAULT_STATE_ROOT))
    parser.add_argument("--train-if-ready", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0
    if args.train_if_ready:
        result = train_candidate_if_ready(
            labels_path=Path(args.labels),
            model_path=Path(args.model),
            state_root=Path(args.state_root),
        )
    else:
        if not args.collection_report:
            raise SystemExit("--collection-report is required unless --self-test or --train-if-ready is used")
        result = evaluate_ai_runtime(
            _read_json(Path(args.collection_report)),
            state_root=Path(args.state_root),
            model_path=Path(args.model),
            labels_path=Path(args.labels),
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
