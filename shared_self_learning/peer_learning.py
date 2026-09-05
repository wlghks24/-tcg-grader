from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable

from .contracts import ALLOWED_DOMAINS, assert_passive_exchange_payload

PEER_LEARNING_FIELDS = (
    "lesson_id",
    "subsystem",
    "issue_class",
    "trigger_condition",
    "symptom_summary",
    "root_cause_class",
    "fix_pattern",
    "prevention_rule_id",
    "verification_result",
    "regression_pass",
    "recurrence_count",
    "applicable_scope",
    "confidence_level",
)

PEER_LEARNING_STATUSES = (
    "corroborated",
    "single-system-only",
    "conflicting-fix",
    "not-applicable",
)

FORBIDDEN_PEER_INPUT_FIELDS = {
    "raw_log",
    "raw_logs",
    "logs",
    "parser_config",
    "parser_state",
    "retry_queue",
    "retry_history",
    "source_health",
    "provider_health",
    "baseline",
    "ranking_weights",
    "confidence_tuning",
    "raw_measurements",
    "grading_raw",
    "grading_calibration",
    "pixel_features",
    "image_features",
    "render_state",
    "rendering_state",
    "upload_state",
    "delivery_state",
    "error_ledger",
    "quarantine",
    "prevention_rule",
    "learning_state",
}

_PASS_RESULTS = {"pass", "passed", "verified", "success", "ok", "true"}
_CONTAINER_TYPES = (dict, list, tuple, set, frozenset, bytes, bytearray)
_MAIN_INAPPLICABLE_SUBSYSTEM_TOKENS = {
    "renderer", "rendering", "upload", "delivery", "design", "image_template",
    "caption", "hashtag", "instagram_renderer", "instagram_upload", "instagram_delivery",
}


def _clean(value: Any, limit: int = 400) -> str:
    return " ".join(str(value or "").replace("\x00", " ").split())[:limit]


def _clean_scalar(value: Any, field: str, limit: int = 400) -> str:
    if isinstance(value, _CONTAINER_TYPES):
        raise TypeError(f"{field} must be a scalar value")
    return _clean(value, limit)


def _normalize_confidence(value: Any) -> str:
    text = _clean_scalar(value, "confidence_level", 40).lower()
    if text in {"low", "medium", "high", "unknown"}:
        return text
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "unknown"
    if number >= 0.8:
        return "high"
    if number >= 0.5:
        return "medium"
    return "low"


def _normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _clean_scalar(value, "regression_pass", 20).lower() in {"1", "true", "yes", "pass", "passed", "ok", "success"}


def _normalize_recurrence(value: Any) -> int:
    if isinstance(value, _CONTAINER_TYPES):
        raise TypeError("recurrence_count must be a scalar value")
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        number = 0
    return max(0, min(1_000_000, number))


def _validate_peer_input(row: dict[str, Any]) -> None:
    assert_passive_exchange_payload(row)
    bad = sorted(set(row) & FORBIDDEN_PEER_INPUT_FIELDS)
    if bad:
        raise ValueError(f"peer learning input contains forbidden raw/internal fields: {bad}")


def normalize_peer_lesson(domain: str, row: dict[str, Any]) -> dict[str, Any]:
    if domain not in ALLOWED_DOMAINS:
        raise ValueError(f"unsupported learning domain: {domain}")
    if not isinstance(row, dict):
        raise TypeError("peer learning lesson must be an object")
    _validate_peer_input(row)

    normalized = {
        "lesson_id": _clean_scalar(row.get("lesson_id"), "lesson_id", 160),
        "subsystem": _clean_scalar(row.get("subsystem"), "subsystem", 120),
        "issue_class": _clean_scalar(row.get("issue_class"), "issue_class", 120),
        "trigger_condition": _clean_scalar(row.get("trigger_condition"), "trigger_condition", 300),
        "symptom_summary": _clean_scalar(row.get("symptom_summary"), "symptom_summary", 500),
        "root_cause_class": _clean_scalar(row.get("root_cause_class"), "root_cause_class", 160),
        "fix_pattern": _clean_scalar(row.get("fix_pattern"), "fix_pattern", 500),
        "prevention_rule_id": _clean_scalar(row.get("prevention_rule_id"), "prevention_rule_id", 160),
        "verification_result": _clean_scalar(row.get("verification_result"), "verification_result", 120),
        "regression_pass": _normalize_bool(row.get("regression_pass")),
        "recurrence_count": _normalize_recurrence(row.get("recurrence_count")),
        "applicable_scope": _clean_scalar(row.get("applicable_scope"), "applicable_scope", 200),
        "confidence_level": _normalize_confidence(row.get("confidence_level")),
    }
    required = ("lesson_id", "subsystem", "issue_class", "root_cause_class", "fix_pattern", "applicable_scope")
    missing = [name for name in required if not normalized[name]]
    if missing:
        raise ValueError(f"peer learning lesson missing required fields: {missing}")
    if tuple(normalized) != PEER_LEARNING_FIELDS:
        raise AssertionError("peer learning projection drifted from exact allowlist")
    return normalized


def validate_peer_snapshot_lesson(domain: str, row: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise TypeError("peer learning snapshot lesson must be an object")
    expected = set(PEER_LEARNING_FIELDS)
    actual = set(row)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise ValueError(f"peer learning snapshot fields mismatch: missing={missing} extra={extra}")
    return normalize_peer_lesson(domain, row)


def _token(value: Any) -> str:
    return re.sub(r"[^a-z0-9가-힣]+", " ", _clean(value, 500).lower()).strip()


def lesson_match_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        _token(row.get("subsystem")),
        _token(row.get("issue_class")),
        _token(row.get("trigger_condition")),
        _token(row.get("root_cause_class")),
    )


def _scope_tokens(value: Any) -> set[str]:
    return {part for part in re.split(r"[^a-z0-9_]+", _clean(value, 240).lower()) if part}


def scope_applies(value: Any, target_domain: str) -> bool:
    if target_domain not in ALLOWED_DOMAINS:
        raise ValueError(f"unsupported learning domain: {target_domain}")
    tokens = _scope_tokens(value)
    if not tokens:
        return False
    universal = {"both", "shared", "common", "all", "cross_domain"}
    if tokens & universal:
        return True
    if target_domain == "main":
        if tokens & {"main", "market", "market_analysis", "grading_summary"}:
            return True
        if tokens & {"instagram", "instagram_content", "ig_cardinfo", "render", "rendering", "upload", "delivery", "design"}:
            return False
    else:
        if tokens & {"instagram", "instagram_content", "ig_cardinfo"}:
            return True
        if tokens & {
            "main", "market_analysis", "grading_raw", "grading_calibration",
            "pixel_features", "raw_measurements",
        }:
            return False
    return False


def lesson_applies_to_domain(row: dict[str, Any], target_domain: str) -> bool:
    if target_domain == "main":
        subsystem_tokens = _scope_tokens(row.get("subsystem"))
        if subsystem_tokens & _MAIN_INAPPLICABLE_SUBSYSTEM_TOKENS:
            return False
    return scope_applies(row.get("applicable_scope"), target_domain)


def _verified_pass(row: dict[str, Any]) -> bool:
    return bool(row.get("regression_pass")) and _token(row.get("verification_result")) in _PASS_RESULTS


def classify_learning_pair(main_lesson: dict[str, Any], instagram_lesson: dict[str, Any]) -> dict[str, Any]:
    left = normalize_peer_lesson("main", main_lesson)
    right = normalize_peer_lesson("instagram_content", instagram_lesson)

    if lesson_match_key(left) != lesson_match_key(right):
        raise ValueError("peer lessons are not comparable")

    if not lesson_applies_to_domain(left, "instagram_content") or not lesson_applies_to_domain(right, "main"):
        status = "not-applicable"
    elif _token(left["fix_pattern"]) != _token(right["fix_pattern"]):
        status = "conflicting-fix"
    elif _verified_pass(left) and _verified_pass(right):
        status = "corroborated"
    else:
        status = "single-system-only"

    return {
        "status": status,
        "main": left,
        "instagram_content": right,
        "peer_fix_auto_apply": False,
        "prevention_rule_shared": False,
        "raw_state_shared": False,
        "requires_independent_reproduction": status in {"single-system-only", "conflicting-fix"},
        "requires_safer_local_selection": status == "conflicting-fix",
    }


def compare_learning_sets(
    main_lessons: Iterable[dict[str, Any]],
    instagram_lessons: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    main_rows = [normalize_peer_lesson("main", row) for row in main_lessons]
    insta_rows = [normalize_peer_lesson("instagram_content", row) for row in instagram_lessons]

    by_key: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for row in insta_rows:
        by_key.setdefault(lesson_match_key(row), []).append(row)

    comparisons: list[dict[str, Any]] = []
    matched_instagram_ids: set[str] = set()

    for left in main_rows:
        candidates = sorted(by_key.get(lesson_match_key(left), []), key=lambda row: row["lesson_id"])
        if candidates:
            for right in candidates:
                matched_instagram_ids.add(right["lesson_id"])
                comparisons.append(classify_learning_pair(left, right))
            continue
        status = (
            "not-applicable"
            if not lesson_applies_to_domain(left, "instagram_content")
            else "single-system-only"
        )
        comparisons.append({
            "status": status,
            "main": left,
            "instagram_content": None,
            "peer_fix_auto_apply": False,
            "prevention_rule_shared": False,
            "raw_state_shared": False,
            "requires_independent_reproduction": status == "single-system-only",
            "requires_safer_local_selection": False,
        })

    for right in insta_rows:
        if right["lesson_id"] in matched_instagram_ids:
            continue
        status = "not-applicable" if not lesson_applies_to_domain(right, "main") else "single-system-only"
        comparisons.append({
            "status": status,
            "main": None,
            "instagram_content": right,
            "peer_fix_auto_apply": False,
            "prevention_rule_shared": False,
            "raw_state_shared": False,
            "requires_independent_reproduction": status == "single-system-only",
            "requires_safer_local_selection": False,
        })

    counts = {name: sum(1 for row in comparisons if row["status"] == name) for name in PEER_LEARNING_STATUSES}
    return {
        "version": 1,
        "main_lessons": len(main_rows),
        "instagram_lessons": len(insta_rows),
        "comparisons": comparisons,
        "counts": counts,
        "peer_fix_auto_apply": False,
        "prevention_rule_shared": False,
        "raw_state_shared": False,
    }


def evaluate_main_peer_adoption(
    peer_lesson: dict[str, Any],
    *,
    reproduction_pass: bool,
    root_cause_reconfirmed: bool,
    minimal_scope_fix: bool,
    local_regression_pass: bool,
    full_regression_pass: bool,
    crosscheck_status: str = "single-system-only",
    safer_fix_selected: bool = False,
    selected_fix_pattern: str | None = None,
) -> dict[str, Any]:
    peer = normalize_peer_lesson("instagram_content", peer_lesson)
    if crosscheck_status not in PEER_LEARNING_STATUSES:
        raise ValueError("unsupported peer learning status")

    checks = {
        "reproduction_pass": bool(reproduction_pass),
        "root_cause_reconfirmed": bool(root_cause_reconfirmed),
        "minimal_scope_fix": bool(minimal_scope_fix),
        "local_regression_pass": bool(local_regression_pass),
        "full_regression_pass": bool(full_regression_pass),
    }
    applicable = lesson_applies_to_domain(peer, "main")
    status_eligible = crosscheck_status != "not-applicable"
    selected_fix = _clean_scalar(selected_fix_pattern, "selected_fix_pattern", 500) if selected_fix_pattern is not None else ""
    selected_fix_explicit = bool(selected_fix)
    conflict_safe = crosscheck_status != "conflicting-fix" or (bool(safer_fix_selected) and selected_fix_explicit)
    allowed = applicable and status_eligible and all(checks.values()) and conflict_safe

    chosen_fix = selected_fix if selected_fix_explicit else peer["fix_pattern"]
    digest = hashlib.sha256(
        f'{peer["lesson_id"]}|{peer["issue_class"]}|{peer["root_cause_class"]}|{chosen_fix}'.encode("utf-8", "replace")
    ).hexdigest()[:16]
    local_rule = None
    if allowed:
        local_rule = {
            "prevention_rule_id": f"MARKET-PEER-{digest}",
            "subsystem": peer["subsystem"],
            "issue_class": peer["issue_class"],
            "trigger_condition": peer["trigger_condition"],
            "root_cause_class": peer["root_cause_class"],
            "fix_pattern": chosen_fix,
            "verification_result": "adopted_after_reproduction_rootcause_local_and_full_regression",
            "regression_pass": True,
            "learned_from_peer": peer["lesson_id"],
        }

    return {
        "adoption_allowed": allowed,
        "applicable_to_main": applicable,
        "crosscheck_status": crosscheck_status,
        "status_eligible": status_eligible,
        "safer_fix_selected": bool(safer_fix_selected),
        "selected_fix_explicit": selected_fix_explicit,
        "required_sequence": [
            "reproduction_test",
            "root_cause_reconfirmation",
            "minimal_scope_fix",
            "local_regression_test",
            "full_regression_test",
        ],
        "checks": checks,
        "peer_prevention_rule_copied": False,
        "learned_from_peer": peer["lesson_id"],
        "local_prevention_rule": local_rule,
    }
