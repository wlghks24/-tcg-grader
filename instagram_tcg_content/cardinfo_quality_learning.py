#!/usr/bin/env python3
"""Cumulative quality-learning loop for Instagram card-info artifacts.

This learner improves *presentation quality only*. It has no authority over
factual verification, collection-health, source selection, or production
authorization.

Early phase:
- accumulate real user_feedback / human_audit / external_outcome labels;
- derive bounded rule guidance only from repeated verified negative issue tags;
- do not train or claim a neural model.

Mature phase:
- >=1,000 real labels, >=3 owner groups, <=70% owner dominance, unique
  artifact/origin ids, timezone-aware labels, binary class coverage;
- compare logistic vs shallow MLP ensembles (hidden 4/8/12 x 3 fixed seeds);
- model remains advisory and can only rank layout/copy quality variants.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT = "instagram_card"
TASK_ID = "6a9b8a22e72c8191849c273e1240378e"
SCHEMA_VERSION = 1
MIN_REAL_LABELS = 1000
MIN_OWNER_GROUPS = 3
MAX_OWNER_DOMINANCE = 0.70
ALLOWED_HIDDEN_SIZES = (4, 8, 12)
ALLOWED_SEEDS = (20260909, 20260919, 20260929)
FEATURES = (
    "layout_balance",
    "whitespace_balance",
    "text_density_fit",
    "hierarchy_clarity",
    "alignment_consistency",
    "card_image_prominence",
    "copy_brevity",
    "numeric_readability",
    "visual_consistency",
    "information_focus",
)
ALLOWED_LABEL_SOURCES = {"user_feedback", "human_audit", "external_outcome"}
ISSUE_TAGS = {
    "crowded_text",
    "weak_hierarchy",
    "low_whitespace",
    "small_card_image",
    "too_many_callouts",
    "inconsistent_alignment",
    "dense_table",
    "repetitive_copy",
    "unnatural_copy",
    "color_noise",
    "poor_number_readability",
    "weak_focus",
}
DEFAULT_LABELS = Path("TCG_CROSSCHECK/IG_CARDINFO/quality_learning/quality_labels.json")
DEFAULT_MODEL = Path("TCG_CROSSCHECK/IG_CARDINFO/quality_learning/quality_model.json")
DEFAULT_PROFILE = Path("TCG_CROSSCHECK/IG_CARDINFO/quality_learning/render_quality_profile.json")

BASE_PROFILE = {
    "schema_version": 1,
    "mode": "RULES_ONLY_EARLY_PHASE",
    "locked_master_mutation_allowed": False,
    "max_text_density": 0.34,
    "min_whitespace_ratio": 0.20,
    "max_callouts": 4,
    "max_dense_table_rows": 8,
    "min_card_image_prominence": 0.46,
    "max_copy_lines_per_block": 4,
    "prefer_short_labels": True,
    "numeric_grouping_required": True,
    "single_primary_visual_focus": True,
    "alignment_grid_required": True,
    "max_simultaneous_emphasis_styles": 3,
    "guidance": [],
}


def _aware_timestamp(value: object) -> float:
    if not isinstance(value, str) or not value:
        raise ValueError("TIMESTAMP_REQUIRED")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("INVALID_TIMESTAMP") from exc
    if parsed.tzinfo is None:
        raise ValueError("TIMEZONE_REQUIRED")
    return parsed.timestamp()


def _feature_vector(features: object) -> list[float]:
    if not isinstance(features, dict) or set(features) != set(FEATURES):
        raise ValueError("QUALITY_FEATURE_SCHEMA_MISMATCH")
    values = [features[name] for name in FEATURES]
    if any(type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1 for value in values):
        raise ValueError("QUALITY_FEATURE_INVALID")
    return [float(value) for value in values]


def issue_tags_from_features(features: dict[str, float], *, threshold: float = 0.65) -> list[str]:
    values = dict(zip(FEATURES, _feature_vector(features)))
    tags = []
    if values["text_density_fit"] < threshold:
        tags.append("crowded_text")
    if values["whitespace_balance"] < threshold:
        tags.append("low_whitespace")
    if values["hierarchy_clarity"] < threshold:
        tags.append("weak_hierarchy")
    if values["card_image_prominence"] < threshold:
        tags.append("small_card_image")
    if values["alignment_consistency"] < threshold:
        tags.append("inconsistent_alignment")
    if values["copy_brevity"] < threshold:
        tags.append("repetitive_copy")
    if values["numeric_readability"] < threshold:
        tags.append("poor_number_readability")
    if values["visual_consistency"] < threshold:
        tags.append("color_noise")
    if values["information_focus"] < threshold:
        tags.append("weak_focus")
    return tags


def _normalize_row(row: object) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise ValueError("QUALITY_LABEL_ROW_REQUIRED")
    if row.get("project") != PROJECT or row.get("task_id") != TASK_ID:
        raise ValueError("QUALITY_LABEL_SCOPE_MISMATCH")
    if row.get("label_source") not in ALLOWED_LABEL_SOURCES:
        raise ValueError("QUALITY_INDEPENDENT_LABEL_REQUIRED")
    for key in ("artifact_id", "origin_group", "owner_group", "label_reference"):
        value = row.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"{key.upper()}_REQUIRED")
    if row.get("synthetic") is not False:
        raise ValueError("QUALITY_SYNTHETIC_LABEL_FORBIDDEN")
    label = row.get("natural_quality_label")
    if type(label) is not int or label not in (0, 1):
        raise ValueError("QUALITY_BINARY_LABEL_REQUIRED")
    observed = _aware_timestamp(row.get("observed_at"))
    labeled = _aware_timestamp(row.get("labeled_at"))
    if labeled < observed:
        raise ValueError("QUALITY_LABEL_PRECEDES_OBSERVATION")
    features = _feature_vector(row.get("features"))
    raw_tags = row.get("issue_tags")
    if raw_tags is None:
        raw_tags = issue_tags_from_features(row.get("features"))
    if not isinstance(raw_tags, list) or any(tag not in ISSUE_TAGS for tag in raw_tags):
        raise ValueError("QUALITY_ISSUE_TAG_INVALID")
    if label == 1 and raw_tags:
        raise ValueError("POSITIVE_QUALITY_LABEL_CANNOT_CARRY_ISSUES")
    return {
        **row,
        "observed_epoch": observed,
        "labeled_epoch": labeled,
        "feature_vector": features,
        "issue_tags": list(dict.fromkeys(raw_tags)),
    }


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            temp = Path(handle.name)
        temp.replace(path)
    finally:
        if temp is not None and temp.exists():
            temp.unlink(missing_ok=True)


def append_quality_label(row: dict[str, Any], path: Path = DEFAULT_LABELS) -> dict[str, Any]:
    clean = _normalize_row(row)
    existing: list[dict[str, Any]] = []
    if path.is_file():
        raw = json.loads(path.read_text(encoding="utf-8"))
        existing = raw.get("rows", raw) if isinstance(raw, dict) else raw
        if not isinstance(existing, list):
            raise ValueError("QUALITY_LABEL_FILE_SCHEMA_INVALID")
    artifact_ids = {
        value.get("artifact_id")
        for value in existing
        if isinstance(value, dict)
    }
    origins = {
        value.get("origin_group")
        for value in existing
        if isinstance(value, dict)
    }
    if clean["artifact_id"] in artifact_ids:
        raise ValueError("DUPLICATE_ARTIFACT_ID")
    if clean["origin_group"] in origins:
        raise ValueError("DUPLICATE_ORIGIN_GROUP")

    stored = {
        key: value
        for key, value in row.items()
        if key not in {"observed_epoch", "labeled_epoch", "feature_vector"}
    }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "project": PROJECT,
        "task_id": TASK_ID,
        "label_authority": sorted(ALLOWED_LABEL_SOURCES),
        "synthetic_labels_forbidden": True,
        "rows": existing + [stored],
    }
    _write_json_atomic(path, payload)
    reread = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(reread, dict) or len(reread.get("rows") or []) != len(existing) + 1:
        raise RuntimeError("QUALITY_LABEL_WRITE_READBACK_FAILED")
    return {
        "status": "QUALITY_REAL_LABEL_APPENDED",
        "label_count": len(reread["rows"]),
        "artifact_id": clean["artifact_id"],
        "neural_training_ready": audit_labels(reread["rows"])["ready_for_neural_training"],
    }


def audit_labels(rows: object) -> dict[str, Any]:
    if not isinstance(rows, list):
        raise ValueError("QUALITY_LABELS_LIST_REQUIRED")
    normalized = []
    invalid = []
    artifacts, origins = set(), set()
    owners = Counter()
    labels = Counter()
    for index, row in enumerate(rows):
        try:
            clean = _normalize_row(row)
            if clean["artifact_id"] in artifacts:
                raise ValueError("DUPLICATE_ARTIFACT_ID")
            if clean["origin_group"] in origins:
                raise ValueError("DUPLICATE_ORIGIN_GROUP")
            artifacts.add(clean["artifact_id"])
            origins.add(clean["origin_group"])
            owners[clean["owner_group"]] += 1
            labels[clean["natural_quality_label"]] += 1
            normalized.append(clean)
        except ValueError as exc:
            invalid.append(f"row[{index}]:{exc}")

    dominance = max(owners.values(), default=0) / max(1, len(normalized))
    ready = (
        len(normalized) >= MIN_REAL_LABELS
        and len(owners) >= MIN_OWNER_GROUPS
        and dominance <= MAX_OWNER_DOMINANCE
        and set(labels) == {0, 1}
        and not invalid
    )
    reasons = []
    if len(normalized) < MIN_REAL_LABELS:
        reasons.append("INSUFFICIENT_REAL_QUALITY_LABELS")
    if len(owners) < MIN_OWNER_GROUPS:
        reasons.append("INSUFFICIENT_QUALITY_OWNER_DIVERSITY")
    if dominance > MAX_OWNER_DOMINANCE:
        reasons.append("QUALITY_OWNER_CONCENTRATION_TOO_HIGH")
    if set(labels) != {0, 1}:
        reasons.append("QUALITY_BINARY_CLASS_COVERAGE_REQUIRED")
    if invalid:
        reasons.append("QUALITY_LABEL_SCHEMA_ERROR")
    return {
        "rows": len(rows),
        "valid_real_rows": len(normalized),
        "minimum_real_labels": MIN_REAL_LABELS,
        "owner_groups": len(owners),
        "owner_dominance": dominance,
        "labels": dict(labels),
        "invalid_count": len(invalid),
        "invalid_sample": invalid[:20],
        "ready_for_neural_training": ready,
        "readiness_reasons": reasons,
        "_normalized": normalized,
    }


def _apply_issue(profile: dict[str, Any], tag: str) -> None:
    guidance = profile["guidance"]
    if tag == "crowded_text":
        profile["max_text_density"] = max(0.22, profile["max_text_density"] - 0.03)
        profile["max_copy_lines_per_block"] = min(profile["max_copy_lines_per_block"], 3)
        guidance.append("텍스트를 줄이고 핵심 숫자/카드명/변화만 우선 배치")
    elif tag == "low_whitespace":
        profile["min_whitespace_ratio"] = min(0.30, profile["min_whitespace_ratio"] + 0.03)
        guidance.append("섹션 간 여백을 늘리고 요소 간 간격을 일정하게 유지")
    elif tag == "weak_hierarchy":
        guidance.append("제목→핵심 수치→근거→보조정보 순서로 시각 계층 강화")
    elif tag == "small_card_image":
        profile["min_card_image_prominence"] = min(0.62, profile["min_card_image_prominence"] + 0.04)
        guidance.append("카드/상품 이미지를 더 크게 두고 텍스트가 이미지를 압도하지 않게 조정")
    elif tag == "too_many_callouts":
        profile["max_callouts"] = max(2, profile["max_callouts"] - 1)
        guidance.append("강조 박스 수를 줄이고 핵심 강조만 유지")
    elif tag == "inconsistent_alignment":
        guidance.append("모든 카드/텍스트/수치의 좌우 정렬 기준선을 통일")
    elif tag == "dense_table":
        profile["max_dense_table_rows"] = max(5, profile["max_dense_table_rows"] - 1)
        guidance.append("표는 상위 핵심 항목만 보여주고 나머지는 요약")
    elif tag in {"repetitive_copy", "unnatural_copy"}:
        profile["prefer_short_labels"] = True
        guidance.append("문구 반복을 줄이고 짧고 자연스러운 한국어/영어 문장 사용")
    elif tag == "color_noise":
        profile["max_simultaneous_emphasis_styles"] = max(2, profile["max_simultaneous_emphasis_styles"] - 1)
        guidance.append("동시에 사용하는 강조 색/스타일 수를 줄여 시각적 소음 억제")
    elif tag == "poor_number_readability":
        guidance.append("가격·상승률·날짜는 단위/구분기호/자리수를 일관되게 표시")
    elif tag == "weak_focus":
        guidance.append("한 장마다 하나의 주 메시지를 정하고 보조정보는 그 아래로 제한")


def build_rule_profile(rows: object, *, min_recurrence: int = 3) -> dict[str, Any]:
    if type(min_recurrence) is not int or min_recurrence < 2:
        raise ValueError("QUALITY_MIN_RECURRENCE_INVALID")
    audit = audit_labels(rows)
    profile = dict(BASE_PROFILE)
    profile["guidance"] = []
    negatives = [
        row for row in audit["_normalized"]
        if row["natural_quality_label"] == 0
    ]
    tag_origins: dict[str, set[str]] = {tag: set() for tag in ISSUE_TAGS}
    for row in negatives:
        for tag in row["issue_tags"]:
            tag_origins[tag].add(row["origin_group"])
    recurring = {
        tag: len(origins)
        for tag, origins in tag_origins.items()
        if len(origins) >= min_recurrence
    }
    for tag, _count in sorted(recurring.items(), key=lambda item: (-item[1], item[0])):
        _apply_issue(profile, tag)
    profile["guidance"] = list(dict.fromkeys(profile["guidance"]))
    profile["recurring_issue_counts"] = recurring
    profile["verified_negative_artifacts"] = len(negatives)
    profile["quality_label_count"] = audit["valid_real_rows"]
    profile["neural_training_ready"] = audit["ready_for_neural_training"]
    profile["mode"] = (
        "NEURAL_ELIGIBLE_ADVISORY"
        if audit["ready_for_neural_training"]
        else "RULES_ONLY_EARLY_PHASE"
    )
    profile["locked_master_mutation_allowed"] = False
    return profile


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1 / (1 + math.exp(-min(value, 700)))
    exp = math.exp(max(value, -700))
    return exp / (1 + exp)


def _predict(model: dict[str, Any], x: list[float]) -> float:
    kind = model.get("kind")
    if kind == "logistic":
        weights = model["weights"]
        return _sigmoid(weights[0] + sum(w * v for w, v in zip(weights[1:], x)))
    if kind == "mlp":
        hidden = [
            math.tanh(b + sum(w * v for w, v in zip(ws, x)))
            for ws, b in zip(model["hidden_weights"], model["hidden_bias"])
        ]
        return _sigmoid(model["output_bias"] + sum(w * v for w, v in zip(model["output_weights"], hidden)))
    if kind == "ensemble":
        return sum(_predict(member, x) for member in model["members"]) / len(model["members"])
    raise ValueError("QUALITY_MODEL_INVALID")


def _brier(model: dict[str, Any], rows: list[tuple[list[float], int]]) -> float:
    return sum((_predict(model, x) - y) ** 2 for x, y in rows) / len(rows)


def _train_logistic(rows: list[tuple[list[float], int]]) -> dict[str, Any]:
    weights = [0.0] * (len(FEATURES) + 1)
    for _ in range(220):
        grad = [0.0] * len(weights)
        for x, y in rows:
            error = _predict({"kind": "logistic", "weights": weights}, x) - y
            grad[0] += error
            for index, value in enumerate(x, 1):
                grad[index] += error * value
        for index in range(len(weights)):
            weights[index] -= 0.28 * (grad[index] / len(rows) + (0.01 * weights[index] if index else 0))
    return {"kind": "logistic", "weights": weights}


def _train_mlp(rows: list[tuple[list[float], int]], hidden_size: int, seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    hw = [[rng.uniform(-0.16, 0.16) for _ in FEATURES] for _ in range(hidden_size)]
    hb = [0.0] * hidden_size
    ow = [rng.uniform(-0.16, 0.16) for _ in range(hidden_size)]
    ob = 0.0
    for _ in range(140):
        ghw = [[0.0] * len(FEATURES) for _ in range(hidden_size)]
        ghb = [0.0] * hidden_size
        gow = [0.0] * hidden_size
        gob = 0.0
        for x, y in rows:
            hidden = [math.tanh(hb[h] + sum(hw[h][j] * x[j] for j in range(len(x)))) for h in range(hidden_size)]
            p = _sigmoid(ob + sum(ow[h] * hidden[h] for h in range(hidden_size)))
            error = p - y
            gob += error
            for h in range(hidden_size):
                gow[h] += error * hidden[h]
                delta = error * ow[h] * (1 - hidden[h] ** 2)
                ghb[h] += delta
                for j, value in enumerate(x):
                    ghw[h][j] += delta * value
        inv = 1.0 / len(rows)
        rate = 0.16
        ob -= rate * gob * inv
        for h in range(hidden_size):
            ow[h] -= rate * (gow[h] * inv + 0.01 * ow[h])
            hb[h] -= rate * ghb[h] * inv
            for j in range(len(FEATURES)):
                hw[h][j] -= rate * (ghw[h][j] * inv + 0.01 * hw[h][j])
    return {
        "kind": "mlp",
        "hidden_size": hidden_size,
        "hidden_weights": hw,
        "hidden_bias": hb,
        "output_weights": ow,
        "output_bias": ob,
    }


def train_quality_model(rows: object) -> dict[str, Any]:
    audit = audit_labels(rows)
    if not audit["ready_for_neural_training"]:
        return {
            "status": "QUALITY_MODEL_UPDATE_SKIPPED_KEEP_RULES",
            "audit": {key: value for key, value in audit.items() if not key.startswith("_")},
            "model": None,
            "existing_model_preserved": True,
        }

    clean = sorted(audit["_normalized"], key=lambda row: row["observed_epoch"])
    n = len(clean)
    a, b, c = int(n * 0.50), int(n * 0.65), int(n * 0.80)
    parts = [clean[:a], clean[a:b], clean[b:c], clean[c:]]
    if any(not part for part in parts):
        return {"status": "QUALITY_TEMPORAL_SPLIT_FAILED", "model": None, "existing_model_preserved": True}
    if any(parts[i][-1]["observed_epoch"] >= parts[i + 1][0]["observed_epoch"] for i in range(3)):
        return {"status": "QUALITY_TEMPORAL_SPLIT_OVERLAP", "model": None, "existing_model_preserved": True}
    if any(max(row["labeled_epoch"] for row in parts[i]) >= parts[i + 1][0]["observed_epoch"] for i in range(3)):
        return {"status": "QUALITY_FUTURE_LABEL_LEAKAGE", "model": None, "existing_model_preserved": True}
    if any(set(row["natural_quality_label"] for row in part) != {0, 1} for part in parts):
        return {"status": "QUALITY_SPLIT_CLASS_COVERAGE_FAILED", "model": None, "existing_model_preserved": True}

    train = [(row["feature_vector"], row["natural_quality_label"]) for row in parts[0]]
    tune = [(row["feature_vector"], row["natural_quality_label"]) for row in parts[1]]
    test = [(row["feature_vector"], row["natural_quality_label"]) for row in parts[3]]

    logistic = _train_logistic(train)
    logistic_score = _brier(logistic, tune)
    families = []
    for hidden_size in ALLOWED_HIDDEN_SIZES:
        members = [_train_mlp(train, hidden_size, seed) for seed in ALLOWED_SEEDS]
        scores = [_brier(member, tune) for member in members]
        families.append({
            "hidden_size": hidden_size,
            "members": members,
            "mean": sum(scores) / len(scores),
            "range": max(scores) - min(scores),
        })
    best = min(families, key=lambda family: (family["mean"] + 0.0002 * family["hidden_size"], family["hidden_size"]))
    use_neural = best["range"] <= 0.04 and best["mean"] + 0.005 < logistic_score
    selected = (
        {"kind": "ensemble", "hidden_size": best["hidden_size"], "seeds": list(ALLOWED_SEEDS), "members": best["members"]}
        if use_neural else logistic
    )
    test_brier = _brier(selected, test)
    baseline = sum((0.5 - y) ** 2 for _x, y in test) / len(test)
    operational = test_brier + 0.002 < baseline
    model = {
        "schema_version": SCHEMA_VERSION,
        **selected,
        "project": PROJECT,
        "task_id": TASK_ID,
        "purpose": "cardinfo_natural_quality",
        "features": list(FEATURES),
        "training_label_count": n,
        "temporal_split_policy": "50_15_15_20",
        "operational": operational,
        "verification_authority": False,
        "production_authority": False,
        "test_brier": test_brier,
        "constant_baseline_brier": baseline,
        "training_fingerprint": hashlib.sha256(
            json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest(),
    }
    return {
        "status": "QUALITY_MODEL_READY_ADVISORY" if operational else "QUALITY_MODEL_REJECTED_KEEP_RULES",
        "model": model if operational else None,
        "existing_model_preserved": not operational,
        "selection": {
            "logistic_tune_brier": logistic_score,
            "best_mlp_hidden_size": best["hidden_size"],
            "best_mlp_tune_brier": best["mean"],
            "best_mlp_seed_range": best["range"],
            "selected": selected["kind"],
            "test_was_used_for_selection": False,
        },
        "metrics": {"test_brier": test_brier, "constant_baseline_brier": baseline},
    }


def save_model(report: dict[str, Any], path: Path = DEFAULT_MODEL) -> dict[str, Any]:
    model = report.get("model") if isinstance(report, dict) else None
    if report.get("status") != "QUALITY_MODEL_READY_ADVISORY" or not isinstance(model, dict) or model.get("operational") is not True:
        return {"status": "QUALITY_MODEL_NOT_PROMOTED", "existing_model_preserved": True}
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return {"status": "QUALITY_ADVISORY_MODEL_SAVED", "path": str(path), "can_verify": False, "can_authorize_production": False}


def load_model(path: Path = DEFAULT_MODEL) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("status") != "QUALITY_MODEL_READY_ADVISORY":
        return None
    model = value.get("model")
    if (
        not isinstance(model, dict)
        or model.get("project") != PROJECT
        or model.get("task_id") != TASK_ID
        or model.get("features") != list(FEATURES)
        or model.get("operational") is not True
        or model.get("verification_authority") is not False
        or model.get("production_authority") is not False
        or model.get("training_label_count", 0) < MIN_REAL_LABELS
    ):
        return None
    return model


def rank_variant(features: dict[str, float], model: dict[str, Any] | None) -> dict[str, Any]:
    x = _feature_vector(features)
    if model is None:
        score = sum(x) / len(x)
        return {
            "status": "QUALITY_RULES_ONLY",
            "estimated_natural_quality": score,
            "can_verify": False,
            "can_authorize_production": False,
        }
    score = _predict(model, x)
    return {
        "status": "QUALITY_NEURAL_ADVISORY",
        "estimated_natural_quality": score,
        "can_verify": False,
        "can_authorize_production": False,
    }


def self_test() -> None:
    rows = []
    for i in range(6):
        rows.append({
            "project": PROJECT,
            "task_id": TASK_ID,
            "artifact_id": f"artifact-{i}",
            "origin_group": f"origin-{i}",
            "owner_group": "owner-a",
            "label_source": "user_feedback",
            "label_reference": f"chat-{i}",
            "synthetic": False,
            "natural_quality_label": 0,
            "observed_at": f"2026-09-0{1+i}T10:00:00+09:00",
            "labeled_at": f"2026-09-0{1+i}T10:01:00+09:00",
            "issue_tags": ["crowded_text", "low_whitespace", "unnatural_copy"] if i < 4 else [],
            "features": {name: 0.4 for name in FEATURES},
        })
    profile = build_rule_profile(rows)
    assert profile["mode"] == "RULES_ONLY_EARLY_PHASE", profile
    assert profile["max_text_density"] < BASE_PROFILE["max_text_density"], profile
    assert profile["min_whitespace_ratio"] > BASE_PROFILE["min_whitespace_ratio"], profile
    report = train_quality_model(rows)
    assert report["status"] == "QUALITY_MODEL_UPDATE_SKIPPED_KEEP_RULES", report
    ranked = rank_variant({name: 0.8 for name in FEATURES}, None)
    assert ranked["status"] == "QUALITY_RULES_ONLY" and ranked["can_authorize_production"] is False
    print("Instagram card-info quality learning: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", default=str(DEFAULT_LABELS))
    parser.add_argument("--model", default=str(DEFAULT_MODEL))
    parser.add_argument("--profile", default=str(DEFAULT_PROFILE))
    parser.add_argument("--train-if-ready", action="store_true")
    parser.add_argument("--build-profile", action="store_true")
    parser.add_argument("--append-label")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    labels_path = Path(args.labels)
    if args.append_label:
        value = json.loads(Path(args.append_label).read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise SystemExit("append-label input must be one JSON object")
        print(json.dumps(append_quality_label(value, labels_path), ensure_ascii=False, indent=2))
        return 0
    rows = []
    if labels_path.is_file():
        raw = json.loads(labels_path.read_text(encoding="utf-8"))
        rows = raw.get("rows", raw) if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        raise SystemExit("quality labels must be a list or {rows:[...]}")
    output = {}
    if args.build_profile:
        profile = build_rule_profile(rows)
        profile_path = Path(args.profile)
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        output["profile"] = profile
    if args.train_if_ready:
        report = train_quality_model(rows)
        output["training"] = report
        output["save"] = save_model(report, Path(args.model))
    if not output:
        output["audit"] = {key: value for key, value in audit_labels(rows).items() if not key.startswith("_")}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
