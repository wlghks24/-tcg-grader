#!/usr/bin/env python3
"""Validated information-exchange governance for Tablet GPT / TCG Grader autonomy.

V379 wraps V378 without weakening its 100+1000 quality gate, V377 single-run
serialization, V376 transactional evidence barrier, or verified-learning rules.

The new layer consumes only strict peer-learning summary envelopes. It may:
- classify corroborated, single-system, conflicting, missing, or invalid exchange;
- block mutation on malformed/conflicting exchange evidence;
- require local reproduction before peer-only evidence can influence behavior;
- expose corroborated exchange as a bounded advisory council signal; and
- choose management actions for observation/reproduction/hold.

It never copies a peer fix automatically, trains on peer facts directly, promotes
facts/trust/prices/grades, predicts market direction, writes Git/main, generates
source code, or bypasses protected PR/CI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import tablet_autonomous_evolution_v378 as v378
from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
CONTROLLER_VERSION = "v379"
CORE_CONTROLLER_VERSION = "v378"
REPORT_PATH = ROOT / "tablet_autonomy_v379_report.json"
MAX_EXCHANGE_BYTES = 2_000_000
MAX_EXCHANGE_LESSONS = 512

PEER_LEARNING_FIELDS = (
    "lesson_id", "subsystem", "issue_class", "trigger_condition",
    "symptom_summary", "root_cause_class", "fix_pattern", "prevention_rule_id",
    "verification_result", "regression_pass", "recurrence_count",
    "applicable_scope", "confidence_level",
)
PASS_RESULTS = {"pass", "passed", "verified", "success", "ok", "true"}

SAFETY = dict(v378.SAFETY)
SAFETY.update({
    "information_exchange_manager_enabled": True,
    "information_exchange_summary_only": True,
    "information_exchange_conflict_blocks_mutation": True,
    "information_exchange_invalid_blocks_mutation": True,
    "information_exchange_input_stability_required": True,
    "peer_fix_auto_apply": False,
    "peer_learning_requires_local_reproduction": True,
    "peer_exchange_never_promotes_facts_prices_grades": True,
    "peer_content_direct_model_training": False,
    "existing_verified_neural_models_reused": True,
    "exchange_neural_signal_advisory_only": True,
    "source_code_auto_generation": False,
    "source_code_auto_rewrite": False,
    "arbitrary_command_execution": False,
    "git_write": False,
    "direct_main_write": False,
    "verification_bypass": False,
    "trust_or_fact_auto_promotion": False,
    "price_or_grade_invention": False,
    "market_direction_inferred": False,
})

_HOLD_STATUSES = set(getattr(v378, "_HOLD_STATUSES", set())) | {
    "EXCHANGE_INTEGRITY_HOLD",
    "EXCHANGE_CONFLICT_HOLD",
    "EXCHANGE_CHANGED_DURING_DECISION_HOLD",
}


def _mutating_requested(*, execute: bool, apply_capabilities: bool, train_meta: bool, apply_skills: bool) -> bool:
    return bool(execute or apply_capabilities or train_meta or apply_skills)


def _clean_scalar(value: Any, *, limit: int = 500) -> str:
    if isinstance(value, (dict, list, tuple, set, frozenset, bytes, bytearray)):
        raise TypeError("exchange learning fields must be scalar")
    return " ".join(str(value or "").replace("\x00", " ").split())[:limit]


def _tokens(value: Any) -> set[str]:
    text = _clean_scalar(value, limit=160).lower()
    for char in ",;/|":
        text = text.replace(char, " ")
    return {token for token in text.replace("-", "_").split() if token}


def _applies(row: dict[str, Any], target: str) -> bool:
    tokens = _tokens(row.get("applicable_scope"))
    universal = {"both", "shared", "common", "all", "cross_domain"}
    if tokens & universal:
        if target == "main":
            subsystem = _tokens(row.get("subsystem"))
            if subsystem & {
                "renderer", "rendering", "upload", "delivery", "design",
                "image_template", "caption", "hashtag",
            }:
                return False
        return True
    if target == "main":
        return bool(tokens & {"main", "market", "market_analysis", "grading_summary"})
    return bool(tokens & {"instagram", "instagram_content", "ig_cardinfo"})


def _verified(row: dict[str, Any]) -> bool:
    return (
        row.get("regression_pass") is True
        and _clean_scalar(row.get("verification_result"), limit=40).lower() in PASS_RESULTS
    )


def _match_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return tuple(
        _clean_scalar(row.get(field), limit=400).lower()
        for field in ("subsystem", "issue_class", "trigger_condition", "root_cause_class")
    )


def _load_summary(path: Path, expected_domain: str) -> dict[str, Any]:
    if not path.exists():
        return {"status": "missing", "lessons": [], "sha256": None}
    try:
        if path.is_symlink() or not path.is_file():
            return {"status": "invalid", "lessons": [], "sha256": None, "error_code": "UNSAFE_EXCHANGE_PATH"}
        text = safe_read_text(path, max_bytes=MAX_EXCHANGE_BYTES)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        value = json.loads(text)
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return {"status": "invalid", "lessons": [], "sha256": None, "error_code": type(exc).__name__}
    if not isinstance(value, dict) or set(value) != {"domain", "kind", "lessons"}:
        return {"status": "invalid", "lessons": [], "sha256": digest, "error_code": "EXCHANGE_ENVELOPE_MISMATCH"}
    if value.get("domain") != expected_domain or value.get("kind") != "learning_summary":
        return {"status": "invalid", "lessons": [], "sha256": digest, "error_code": "EXCHANGE_DOMAIN_OR_KIND_MISMATCH"}
    lessons = value.get("lessons")
    if not isinstance(lessons, list) or len(lessons) > MAX_EXCHANGE_LESSONS:
        return {"status": "invalid", "lessons": [], "sha256": digest, "error_code": "EXCHANGE_LESSON_COUNT_INVALID"}

    expected = set(PEER_LEARNING_FIELDS)
    cleaned: list[dict[str, Any]] = []
    for raw in lessons:
        if not isinstance(raw, dict) or set(raw) != expected:
            return {"status": "invalid", "lessons": [], "sha256": digest, "error_code": "EXCHANGE_LESSON_FIELDS_MISMATCH"}
        if type(raw.get("regression_pass")) is not bool:
            return {"status": "invalid", "lessons": [], "sha256": digest, "error_code": "EXCHANGE_REGRESSION_FLAG_INVALID"}
        recurrence = raw.get("recurrence_count")
        if isinstance(recurrence, bool) or not isinstance(recurrence, int) or recurrence < 0:
            return {"status": "invalid", "lessons": [], "sha256": digest, "error_code": "EXCHANGE_RECURRENCE_INVALID"}
        try:
            clean = {
                field: (
                    raw[field]
                    if field in {"regression_pass", "recurrence_count"}
                    else _clean_scalar(raw[field])
                )
                for field in PEER_LEARNING_FIELDS
            }
        except TypeError:
            return {"status": "invalid", "lessons": [], "sha256": digest, "error_code": "EXCHANGE_NESTED_STATE_FORBIDDEN"}
        if not clean["lesson_id"] or not clean["issue_class"] or not clean["root_cause_class"]:
            return {"status": "invalid", "lessons": [], "sha256": digest, "error_code": "EXCHANGE_REQUIRED_FIELD_EMPTY"}
        cleaned.append(clean)
    return {"status": "loaded", "lessons": cleaned, "sha256": digest}


def _input_digest(main_store: dict[str, Any], peer_store: dict[str, Any]) -> str:
    payload = {
        "main_status": main_store.get("status"),
        "main_sha256": main_store.get("sha256"),
        "peer_status": peer_store.get("status"),
        "peer_sha256": peer_store.get("sha256"),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def information_exchange_manager(root: Path = ROOT) -> dict[str, Any]:
    exchange = root / "crosscheck_exchange"
    main_store = _load_summary(exchange / "runtime-main-learning.json", "main")
    peer_store = _load_summary(exchange / "runtime-instagram-learning.json", "instagram_content")
    stores = {"main": main_store["status"], "peer": peer_store["status"]}
    digest = _input_digest(main_store, peer_store)
    safety = {
        "summary_only": True,
        "peer_fix_auto_apply": False,
        "raw_state_shared": False,
        "fact_price_grade_auto_promoted": False,
        "peer_content_direct_model_training": False,
    }
    zero = {"corroborated": 0, "single-system-only": 0, "conflicting-fix": 0, "not-applicable": 0}

    if "invalid" in stores.values():
        return {
            "status": "EXCHANGE_INTEGRITY_HOLD",
            "mutation_allowed": False,
            "peer_influence_allowed": False,
            "selected_management_action": "HOLD_INVALID_EXCHANGE",
            "counts": zero,
            "store_status": stores,
            "error_codes": sorted({
                str(main_store.get("error_code") or ""),
                str(peer_store.get("error_code") or ""),
            } - {""}),
            "signal_score": 0.0,
            "input_digest": digest,
            "safety": {**safety, "independent_reproduction_required": True},
        }

    if main_store["status"] != "loaded" or peer_store["status"] != "loaded":
        status = "EXCHANGE_UNAVAILABLE" if stores["main"] == stores["peer"] == "missing" else "EXCHANGE_PARTIAL"
        return {
            "status": status,
            "mutation_allowed": True,
            "peer_influence_allowed": False,
            "selected_management_action": "LOCAL_VERIFIED_ONLY",
            "counts": zero,
            "store_status": stores,
            "error_codes": [],
            "signal_score": 0.35 if status == "EXCHANGE_PARTIAL" else 0.30,
            "input_digest": digest,
            "safety": {**safety, "independent_reproduction_required": False},
        }

    main_rows = list(main_store["lessons"])
    peer_rows = list(peer_store["lessons"])
    peer_by_key: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for row in peer_rows:
        peer_by_key.setdefault(_match_key(row), []).append(row)

    counts = dict(zero)
    matched_peer_ids: set[str] = set()
    for left in main_rows:
        matches = peer_by_key.get(_match_key(left), [])
        if not matches:
            counts["not-applicable" if not _applies(left, "instagram_content") else "single-system-only"] += 1
            continue
        for right in matches:
            matched_peer_ids.add(str(right["lesson_id"]))
            if not _applies(left, "instagram_content") or not _applies(right, "main"):
                counts["not-applicable"] += 1
            elif _clean_scalar(left["fix_pattern"]).lower() != _clean_scalar(right["fix_pattern"]).lower():
                counts["conflicting-fix"] += 1
            elif _verified(left) and _verified(right):
                counts["corroborated"] += 1
            else:
                counts["single-system-only"] += 1

    for right in peer_rows:
        if str(right["lesson_id"]) in matched_peer_ids:
            continue
        counts["not-applicable" if not _applies(right, "main") else "single-system-only"] += 1

    if counts["conflicting-fix"]:
        status, allowed, influence, action, score = (
            "EXCHANGE_CONFLICT_HOLD", False, False,
            "RESOLVE_CONFLICT_WITH_LOCAL_REPRODUCTION", 0.0,
        )
    elif counts["single-system-only"]:
        status, allowed, influence, action, score = (
            "EXCHANGE_REPRODUCTION_REQUIRED", True, False,
            "REPRODUCE_PEER_LESSONS_LOCALLY", 0.50,
        )
    elif counts["corroborated"]:
        status, allowed, influence, action, score = (
            "EXCHANGE_CORROBORATED", True, True,
            "OBSERVE_CORROBORATED_PATTERNS", 0.85,
        )
    else:
        status, allowed, influence, action, score = (
            "EXCHANGE_EMPTY_OR_NOT_APPLICABLE", True, False,
            "LOCAL_VERIFIED_ONLY", 0.40,
        )
    return {
        "status": status,
        "mutation_allowed": allowed,
        "peer_influence_allowed": influence,
        "selected_management_action": action,
        "counts": counts,
        "store_status": stores,
        "error_codes": [],
        "signal_score": score,
        "input_digest": digest,
        "safety": {
            **safety,
            "independent_reproduction_required": bool(
                counts["single-system-only"] or counts["conflicting-fix"]
            ),
        },
    }


def _bounded_score(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not (number == number and abs(number) != float("inf")):
        return None
    return max(0.0, min(1.0, number))


def exchange_neural_council(result: dict[str, Any], exchange: dict[str, Any]) -> dict[str, Any]:
    base = result.get("neural_council") if isinstance(result.get("neural_council"), dict) else {}
    members = [deepcopy(row) for row in base.get("members", []) if isinstance(row, dict)]
    exchange_score = _bounded_score(exchange.get("signal_score"))
    if exchange_score is not None:
        members.append({
            "id": "information_exchange_governance",
            "score": round(exchange_score, 6),
            "verified_runtime_signal": False,
            "validated_exchange_signal": True,
        })
    scores = [
        float(row["score"]) for row in members
        if _bounded_score(row.get("score")) is not None
    ]
    confidence = sum(scores) / len(scores) if scores else 0.0
    spread = max(scores) - min(scores) if len(scores) >= 2 else 0.0
    agreement = max(0.0, min(1.0, 1.0 - spread))
    if exchange.get("mutation_allowed") is not True:
        readiness = "HOLD"
    elif confidence >= 0.70 and agreement >= 0.45:
        readiness = "HIGH"
    elif confidence >= 0.40:
        readiness = "MEDIUM"
    else:
        readiness = "LOW"
    return {
        "advisory_only": True,
        "existing_verified_neural_models_reused": True,
        "peer_content_direct_model_training": False,
        "member_count": len(members),
        "members": members,
        "confidence": round(confidence, 6),
        "agreement": round(agreement, 6),
        "readiness": readiness,
        "selected_management_action": exchange.get("selected_management_action"),
        "verified_outcome_learning_only": True,
        "unverified_prediction_not_promoted": True,
    }


def _exchange_queue(exchange: dict[str, Any]) -> list[dict[str, Any]]:
    status = str(exchange.get("status") or "")
    counts = exchange.get("counts") if isinstance(exchange.get("counts"), dict) else {}
    if status in {"EXCHANGE_CONFLICT_HOLD", "EXCHANGE_INTEGRITY_HOLD", "EXCHANGE_CHANGED_DURING_DECISION_HOLD"}:
        return [{
            "id": "RESOLVE_INFORMATION_EXCHANGE_HOLD",
            "priority": 98,
            "kind": "information_exchange",
            "auto_apply": False,
            "pr_required": False,
            "required_sequence": [
                "independent_reproduction", "root_cause_reconfirmation",
                "minimal_scope_fix", "local_regression", "full_regression",
            ],
            "reason": status,
        }]
    if int(counts.get("single-system-only") or 0) > 0:
        return [{
            "id": "REPRODUCE_PEER_LESSONS_LOCALLY",
            "priority": 78,
            "kind": "information_exchange",
            "auto_apply": False,
            "pr_required": False,
            "reason": "peer-only evidence cannot alter local behavior before independent reproduction",
        }]
    if int(counts.get("corroborated") or 0) > 0:
        return [{
            "id": "OBSERVE_CORROBORATED_PREVENTION_PATTERNS",
            "priority": 50,
            "kind": "information_exchange",
            "auto_apply": False,
            "pr_required": False,
            "reason": "corroborated summaries may guide observation but never copy peer fixes",
        }]
    return []


def _decorate(result: dict[str, Any], exchange: dict[str, Any]) -> dict[str, Any]:
    row = dict(result)
    row["core_controller_version"] = str(row.get("controller_version") or CORE_CONTROLLER_VERSION)
    row["controller_version"] = CONTROLLER_VERSION
    row["v379_status"] = str(row.get("v378_status") or row.get("v377_status") or row.get("status") or "UNKNOWN")
    row["information_exchange_manager"] = exchange
    row["information_exchange_neural_council"] = exchange_neural_council(row, exchange)
    existing = [deepcopy(item) for item in row.get("improvement_queue", []) if isinstance(item, dict)]
    row["improvement_queue"] = sorted(
        _exchange_queue(exchange) + existing,
        key=lambda item: (-int(item.get("priority") or 0), str(item.get("id") or "")),
    )
    contract = dict(row.get("evolution_contract") or {})
    contract.update({
        "information_exchange_management": "strict_summary_conflict_gate_local_reproduction",
        "information_exchange_peer_fix_auto_apply": False,
        "information_exchange_direct_peer_model_training": False,
        "information_exchange_fact_price_grade_promotion": False,
        "information_exchange_management_action": exchange.get("selected_management_action"),
        "source_level_new_functions": "proposal_only_pr_ci_required",
        "market_direction_prediction": False,
    })
    row["evolution_contract"] = contract
    row["safety"] = SAFETY
    return row


def _exchange_hold(quality: dict[str, Any], exchange: dict[str, Any]) -> dict[str, Any]:
    status = str(exchange.get("status") or "EXCHANGE_INTEGRITY_HOLD")
    result = {
        "controller_version": CORE_CONTROLLER_VERSION,
        "v378_status": status,
        "execution": {
            "status": status,
            "executed": False,
            "git_write": False,
            "source_code_modified": False,
            "proposals_executed": False,
        },
        "quality_governance": quality,
        "neural_council": {
            "advisory_only": True,
            "member_count": 0,
            "members": [],
            "confidence": 0.0,
            "agreement": 0.0,
            "readiness": "HOLD",
        },
        "adaptive_mode": {
            "mode": "EXCHANGE_HOLD",
            "market_regime": "UNKNOWN",
            "market_direction_inferred": False,
            "operational_signal_only": True,
        },
        "improvement_queue": [],
        "evolution_contract": {
            "runtime_self_added_functions": "allowlisted_declarative_capabilities_only",
            "source_level_new_functions": "proposal_only_pr_ci_required",
            "existing_function_tuning": "verified_outcomes_only",
            "market_direction_prediction": False,
        },
        "safety": SAFETY,
    }
    return _decorate(result, exchange)


def _persist(result: dict[str, Any], *, root: Path) -> dict[str, Any]:
    try:
        atomic_write_json(root / REPORT_PATH.name, result, suffix=".v379-report.tmp")
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        return {"status": "WRITE_FAILED", "error_code": type(exc).__name__}
    return {"status": "SAVED"}


def run_cycle(
    *, execute: bool = False, apply_capabilities: bool = False, train_meta: bool = False,
    apply_skills: bool = False, root: Path = ROOT, now=None, proc_root: Path = Path("/proc"),
    state_path: Path | None = None, capability_path: Path | None = None,
    meta_model_path: Path | None = None, meta_outcomes_path: Path | None = None,
    skill_state_path: Path | None = None, skill_outcomes_path: Path | None = None,
    journal_path: Path | None = None, lock_path: Path | None = None,
    quality_policy_path: Path | None = None, persist_outputs: bool = True,
) -> dict[str, Any]:
    exchange = information_exchange_manager(root)
    mutating = _mutating_requested(
        execute=execute, apply_capabilities=apply_capabilities,
        train_meta=train_meta, apply_skills=apply_skills,
    )
    policy_path = quality_policy_path or (root / v378.QUALITY_POLICY_PATH.name)
    quality = v378.quality_governance(policy_path)

    kwargs = dict(
        execute=execute, apply_capabilities=apply_capabilities, train_meta=train_meta,
        apply_skills=apply_skills, root=root, now=now, proc_root=proc_root,
        state_path=state_path, capability_path=capability_path, meta_model_path=meta_model_path,
        meta_outcomes_path=meta_outcomes_path, skill_state_path=skill_state_path,
        skill_outcomes_path=skill_outcomes_path, journal_path=journal_path, lock_path=lock_path,
        quality_policy_path=quality_policy_path, persist_outputs=persist_outputs,
    )

    if mutating and quality.get("ok") is not True:
        result = _decorate(v378.run_cycle(**kwargs), exchange)
    elif mutating and exchange.get("mutation_allowed") is not True:
        result = _exchange_hold(quality, exchange)
    else:
        if mutating:
            confirmed = information_exchange_manager(root)
            if confirmed.get("input_digest") != exchange.get("input_digest"):
                confirmed = dict(confirmed)
                confirmed.update({
                    "status": "EXCHANGE_CHANGED_DURING_DECISION_HOLD",
                    "mutation_allowed": False,
                    "peer_influence_allowed": False,
                    "selected_management_action": "RETRY_AFTER_STABLE_EXCHANGE",
                    "signal_score": 0.0,
                })
                result = _exchange_hold(quality, confirmed)
            else:
                result = _decorate(v378.run_cycle(**kwargs), confirmed)
        else:
            result = _decorate(v378.run_cycle(**kwargs), exchange)

    if persist_outputs:
        result["v379_runtime_output"] = _persist(result, root=root)
    return result


def self_test() -> None:
    assert SAFETY["information_exchange_manager_enabled"] is True
    assert SAFETY["information_exchange_conflict_blocks_mutation"] is True
    assert SAFETY["information_exchange_invalid_blocks_mutation"] is True
    assert SAFETY["information_exchange_input_stability_required"] is True
    assert SAFETY["peer_fix_auto_apply"] is False
    assert SAFETY["peer_content_direct_model_training"] is False
    assert SAFETY["source_code_auto_generation"] is False
    assert SAFETY["git_write"] is False
    assert SAFETY["verification_bypass"] is False
    assert SAFETY["price_or_grade_invention"] is False
    assert SAFETY["market_direction_inferred"] is False
    print("Tablet information-exchange autonomous governance v379: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-safe-learning", action="store_true")
    parser.add_argument("--apply-capabilities", action="store_true")
    parser.add_argument("--train-meta", action="store_true")
    parser.add_argument("--apply-skills", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    result = run_cycle(
        execute=args.execute_safe_learning,
        apply_capabilities=args.apply_capabilities,
        train_meta=args.train_meta,
        apply_skills=args.apply_skills,
    )
    if not args.quiet:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 2 if result.get("v379_status") in _HOLD_STATUSES else 0


if __name__ == "__main__":
    raise SystemExit(main())
