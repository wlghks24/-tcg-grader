#!/usr/bin/env python3
"""Domain-local SELFREFINE error-code isolation and verified-resolution learning.

This module persists only bounded diagnostic state. It never executes learned text,
never creates source patches, never writes git, and never imports Instagram runtime.
Automatic repair eligibility is derived only from code-defined verified repair rules.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import verified_code_repair_rules as verified_repairs
from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "MAIN_SELFREFINE_ERROR_QUARANTINE_STATE.json"
SCHEMA = 1
MAX_ENTRIES = 500
MAX_HISTORY = 200
MAX_TEXT = 240

FAMILY_STAGES = {
    "syntax": {"PYTHON_SYNTAX", "JS_SYNTAX", "SHELL_SYNTAX"},
    "data_contract": {"STRICT_JSON", "FEATURE_CONTRACT_VISION_STALE", "OCR_FEATURE_COUNT_STALE"},
    "ci_runtime": {"CI_ACTION_RUNTIME_DEPRECATED"},
    "resource": {"RESOURCE_HANDLE_LEAK_RISK"},
    "security": {"SECURITY_HIGH"},
    "domain_boundary": {"DOMAIN_BOUNDARY", "STATE_LEAK"},
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean(value: Any, limit: int = MAX_TEXT) -> str:
    return " ".join(str(value or "").replace("\x00", " ").split())[:limit]


def error_family(stage: Any) -> str:
    token = _clean(stage, 80).upper() or "UNKNOWN"
    for family, stages in FAMILY_STAGES.items():
        if token in stages:
            return family
    if token.startswith("HTTP_") or "NETWORK" in token or "TIMEOUT" in token:
        return "transient_network"
    if "DEPENDENCY" in token or "IMPORT" in token:
        return "dependency"
    return "runtime_or_unknown"


def error_code(stage: Any) -> str:
    token = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in _clean(stage, 80).upper())
    token = "_".join(part for part in token.split("_") if part) or "UNKNOWN"
    return f"SELFREFINE.{error_family(token).upper()}.{token}"


def _signature(row: dict[str, Any]) -> str:
    existing = _clean(row.get("error_signature"), 80)
    if existing:
        return existing
    raw = "|".join((
        _clean(row.get("stage"), 80),
        _clean(row.get("path"), 240).replace("\\", "/").lower(),
        _clean(row.get("evidence"), 800).lower(),
    ))
    return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:20]


def _default() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "updated_at": None,
        "entries": {},
        "history": [],
        "safety": {
            "domain": "main",
            "learned_text_executable": False,
            "learned_patch_text_used": False,
            "source_patch_generated_from_state": False,
            "git_write": False,
            "code_defined_repair_rules_only": True,
            "cross_domain_state_merge": False,
            "unknown_error_auto_repair": False,
            "verification_failure_quarantine_threshold": 2,
        },
    }


def _safe_int(value: Any, maximum: int = 1_000_000) -> int:
    try:
        return max(0, min(maximum, int(value or 0)))
    except (TypeError, ValueError, OverflowError):
        return 0


def _load(path: Path = STATE) -> dict[str, Any]:
    try:
        raw = json.loads(safe_read_text(path, max_bytes=2_000_000))
    except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        return _default()
    if not isinstance(raw, dict):
        return _default()
    state = _default()
    rows = raw.get("entries") if isinstance(raw.get("entries"), dict) else {}
    for signature, item in list(rows.items())[-MAX_ENTRIES:]:
        if not isinstance(signature, str) or not signature or not isinstance(item, dict):
            continue
        rule = item.get("last_verified_rule")
        if rule not in verified_repairs.ALL_RULE_IDS:
            rule = None
        state["entries"][signature[:80]] = {
            "error_code": _clean(item.get("error_code"), 160),
            "family": _clean(item.get("family"), 80),
            "stage": _clean(item.get("stage"), 80),
            "path": _clean(item.get("path"), 240).replace("\\", "/"),
            "occurrences": _safe_int(item.get("occurrences")),
            "resolved_count": _safe_int(item.get("resolved_count"), 10000),
            "recurrence_after_verified_resolution": _safe_int(item.get("recurrence_after_verified_resolution"), 10000),
            "verified_successes": _safe_int(item.get("verified_successes"), 10000),
            "verified_failures": _safe_int(item.get("verified_failures"), 10000),
            "consecutive_verification_failures": _safe_int(item.get("consecutive_verification_failures"), 100),
            "last_verified_rule": rule,
            "last_seen": _clean(item.get("last_seen"), 80),
            "last_resolved": _clean(item.get("last_resolved"), 80),
            "status": item.get("status") if item.get("status") in {"isolated", "resolved", "quarantined"} else "isolated",
            "quarantined": item.get("quarantined") is True,
        }
    state["history"] = [x for x in (raw.get("history") or [])[-MAX_HISTORY:] if isinstance(x, dict)]
    return state


def _save(state: dict[str, Any], path: Path = STATE) -> None:
    state["updated_at"] = _now()
    state["history"] = state.get("history", [])[-MAX_HISTORY:]
    if len(state.get("entries", {})) > MAX_ENTRIES:
        ranked = sorted(
            state["entries"].items(),
            key=lambda kv: (str(kv[1].get("last_seen") or ""), kv[0]),
        )[-MAX_ENTRIES:]
        state["entries"] = dict(ranked)
    atomic_write_json(path, state, suffix=".error-quarantine.tmp")


def _confidence(entry: dict[str, Any]) -> float:
    successes = _safe_int(entry.get("verified_successes"), 10000)
    failures = _safe_int(entry.get("verified_failures"), 10000)
    return round((successes + 1.0) / (successes + failures + 2.0), 4)


def observe_open_errors(
    errors: list[dict[str, Any]],
    *,
    state_path: Path = STATE,
) -> dict[str, Any]:
    state = _load(state_path)
    annotated: list[dict[str, Any]] = []
    seen: set[str] = set()
    new_codes = recurring = learned_reuse = quarantined = 0
    now = _now()

    for raw in errors:
        if not isinstance(raw, dict) or raw.get("state") not in {None, "open"}:
            continue
        row = dict(raw)
        signature = _signature(row)
        if signature in seen:
            continue
        seen.add(signature)
        stage = _clean(row.get("stage"), 80) or "UNKNOWN"
        path = _clean(row.get("path"), 240).replace("\\", "/")
        code = error_code(stage)
        family = error_family(stage)
        entries = state.setdefault("entries", {})
        existed = signature in entries
        entry = entries.setdefault(signature, {
            "error_code": code,
            "family": family,
            "stage": stage,
            "path": path,
            "occurrences": 0,
            "resolved_count": 0,
            "recurrence_after_verified_resolution": 0,
            "verified_successes": 0,
            "verified_failures": 0,
            "consecutive_verification_failures": 0,
            "last_verified_rule": None,
            "last_seen": None,
            "last_resolved": None,
            "status": "isolated",
            "quarantined": False,
        })
        if entry.get("status") == "resolved":
            entry["recurrence_after_verified_resolution"] = min(
                10000, _safe_int(entry.get("recurrence_after_verified_resolution"), 10000) + 1
            )
        entry["error_code"] = code
        entry["family"] = family
        entry["stage"] = stage
        entry["path"] = path
        entry["occurrences"] = min(1_000_000, _safe_int(entry.get("occurrences")) + 1)
        entry["last_seen"] = now
        if entry.get("quarantined") is not True:
            entry["status"] = "isolated"

        rule_id = verified_repairs.rule_for_issue(row)
        known_rule = rule_id in verified_repairs.ALL_RULE_IDS
        confidence = _confidence(entry)
        learned = bool(
            known_rule
            and entry.get("last_verified_rule") == rule_id
            and _safe_int(entry.get("verified_successes"), 10000) > 0
            and entry.get("quarantined") is not True
        )
        auto_allowed = bool(known_rule and entry.get("quarantined") is not True)

        row.update({
            "error_signature": signature,
            "error_code": code,
            "error_family": family,
            "isolation_state": "quarantined" if entry.get("quarantined") else "isolated",
            "auto_repair_rule": rule_id,
            "auto_repair_allowed": auto_allowed,
            "learned_solution_reuse": learned,
            "learned_solution_confidence": confidence,
            "verified_solution_successes": _safe_int(entry.get("verified_successes"), 10000),
            "verified_solution_failures": _safe_int(entry.get("verified_failures"), 10000),
        })
        annotated.append(row)
        if not existed:
            new_codes += 1
        else:
            recurring += 1
        learned_reuse += int(learned)
        quarantined += int(entry.get("quarantined") is True)
        state.setdefault("history", []).append({
            "at": now,
            "signature": signature,
            "error_code": code,
            "stage": stage,
            "path": path,
            "event": "recurred_after_verified_resolution" if learned else "isolated",
            "rule_id": rule_id,
        })

    _save(state, state_path)
    return {
        "errors": annotated,
        "summary": {
            "isolated_count": len(annotated),
            "new_error_codes": new_codes,
            "recurring_error_codes": recurring,
            "learned_solution_reuse": learned_reuse,
            "quarantined_count": quarantined,
            "state_path": state_path.name,
        },
        "safety": state["safety"],
    }


def record_repair_outcomes(
    applied: list[dict[str, Any]],
    remaining_errors: list[dict[str, Any]],
    *,
    state_path: Path = STATE,
) -> dict[str, Any]:
    state = _load(state_path)
    open_signatures = {
        _signature(row)
        for row in remaining_errors
        if isinstance(row, dict) and row.get("state") == "open"
    }
    passed = failed = newly_quarantined = 0
    now = _now()

    for item in applied:
        if not isinstance(item, dict):
            continue
        signature = _clean(item.get("error_signature"), 80)
        rule_id = item.get("rule_id")
        if not signature or rule_id not in verified_repairs.ALL_RULE_IDS:
            continue
        entry = state.setdefault("entries", {}).get(signature)
        if not isinstance(entry, dict):
            continue

        resolved = signature not in open_signatures
        if resolved:
            entry["verified_successes"] = min(
                10000, _safe_int(entry.get("verified_successes"), 10000) + 1
            )
            entry["resolved_count"] = min(10000, _safe_int(entry.get("resolved_count"), 10000) + 1)
            entry["consecutive_verification_failures"] = 0
            entry["last_verified_rule"] = rule_id
            entry["last_resolved"] = now
            entry["status"] = "resolved"
            entry["quarantined"] = False
            passed += 1
            event = "verified_resolution_learned"
        else:
            entry["verified_failures"] = min(
                10000, _safe_int(entry.get("verified_failures"), 10000) + 1
            )
            entry["consecutive_verification_failures"] = min(
                100, _safe_int(entry.get("consecutive_verification_failures"), 100) + 1
            )
            became_quarantined = entry["consecutive_verification_failures"] >= 2
            if became_quarantined and entry.get("quarantined") is not True:
                newly_quarantined += 1
            entry["quarantined"] = became_quarantined
            entry["status"] = "quarantined" if became_quarantined else "isolated"
            failed += 1
            event = "repair_rule_quarantined" if became_quarantined else "verification_failed"

        state.setdefault("history", []).append({
            "at": now,
            "signature": signature,
            "error_code": entry.get("error_code"),
            "stage": entry.get("stage"),
            "path": entry.get("path"),
            "event": event,
            "rule_id": rule_id,
            "solution_confidence": _confidence(entry),
        })

    _save(state, state_path)
    return {
        "verified_resolution_learned": passed,
        "verification_failed": failed,
        "newly_quarantined": newly_quarantined,
        "state_path": state_path.name,
        "learned_text_executable": False,
        "source_patch_generated_from_state": False,
    }


def public_status(*, state_path: Path = STATE) -> dict[str, Any]:
    state = _load(state_path)
    entries = list(state.get("entries", {}).values())
    return {
        "ok": True,
        "isolated": sum(x.get("status") == "isolated" for x in entries),
        "resolved": sum(x.get("status") == "resolved" for x in entries),
        "quarantined": sum(x.get("status") == "quarantined" for x in entries),
        "verified_solution_codes": sum(_safe_int(x.get("verified_successes"), 10000) > 0 for x in entries),
        "safety": state["safety"],
    }
