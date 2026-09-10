#!/usr/bin/env python3
"""Evidence-first root-cause diagnostics for the canonical Instagram card-info task."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Mapping, Sequence

from instagram_tcg_content.automation_state_guard import CANONICAL_ID
from instagram_tcg_content.pause_monitor_exchange import SCHEMA_VERSION as PRODUCER_SCHEMA

DIAGNOSTIC_VERSION = "1.4-single-router-tracechain"
PROJECT = "instagram_card"
TASK_ID = CANONICAL_ID
MONITOR_TASK_ID = "6aa02cd749c0819196a6b17db6378958"
SYSTEM = "인스타 카드정보"
STALE_AFTER_SECONDS = 20 * 60
CLOCK_SKEW_WARN_SECONDS = 120
MAX_HISTORY = 32

TERMINAL_SUCCESS_PHASES = frozenset({"VERIFIED_DELIVERY", "VERIFIED_NO_OUTPUT"})
TERMINAL_FAILURE_PHASES = frozenset({"FAILED", "BLOCKED", "DEGRADED"})
TERMINAL_PHASES = TERMINAL_SUCCESS_PHASES | TERMINAL_FAILURE_PHASES
NONTERMINAL_PHASES = frozenset({"STARTED", "PREFLIGHT", "COLLECT", "VERIFY", "COLLECTION_HEALTH", "AI_RELIABILITY", "QUALITY_PROFILE", "RENDER", "OUTPUT_VALIDATION", "QUALITY_REVIEW", "LEARN"})
KNOWN_PHASES = TERMINAL_PHASES | NONTERMINAL_PHASES
PHASE_ORDER = {name: i for i, name in enumerate(("STARTED", "PREFLIGHT", "COLLECT", "VERIFY", "COLLECTION_HEALTH", "AI_RELIABILITY", "QUALITY_PROFILE", "RENDER", "OUTPUT_VALIDATION", "QUALITY_REVIEW", "LEARN", "VERIFIED_DELIVERY", "VERIFIED_NO_OUTPUT"))}
_UNRESOLVED = {"UNRESOLVED_CONTROL_PLANE", "ROOT_CAUSE_UNRESOLVED", None, ""}


@lru_cache(maxsize=4096)
def _parse_iso_cached(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone-aware timestamp required")
    return parsed.astimezone(timezone.utc)


def _parse_iso(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return _parse_iso_cached(value)
    except (TypeError, ValueError):
        return None


def same_instant(left: object, right: object) -> bool:
    a, b = _parse_iso(left), _parse_iso(right)
    return a is not None and b is not None and a == b


def _present(value: object) -> bool:
    return value not in (None, "", [], {})


def _stable_fp(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _matching(row: object, slot: str) -> bool:
    return bool(isinstance(row, dict) and row.get("project") == PROJECT and row.get("task_id") == TASK_ID and same_instant(row.get("scheduled_slot_kst"), slot))


def inspect_trace_chain(history: Sequence[Mapping[str, Any]] | None, *, scheduled_slot_kst: str, observed_at: str) -> dict[str, Any]:
    now = _parse_iso(observed_at)
    if now is None or _parse_iso(scheduled_slot_kst) is None:
        raise ValueError("TRACE_TIME_INVALID")
    source = list(history or [])[:MAX_HISTORY]
    matched = [dict(row) for row in source if _matching(row, scheduled_slot_kst)]
    matched.sort(key=lambda row: (_parse_iso(row.get("observed_at")) or datetime.min.replace(tzinfo=timezone.utc), int(row.get("seq") or 0)))
    anomalies: list[str] = []
    previous_seq = 0
    previous_phase_index = -1
    run_id: str | None = None
    for row in matched:
        seq = row.get("seq")
        if isinstance(seq, bool) or not isinstance(seq, int) or seq < 1 or seq <= previous_seq:
            if "TRACE_SEQ_NOT_MONOTONIC" not in anomalies:
                anomalies.append("TRACE_SEQ_NOT_MONOTONIC")
        else:
            previous_seq = seq
        candidate_run = row.get("run_id")
        if run_id is None and isinstance(candidate_run, str):
            run_id = candidate_run
        elif candidate_run != run_id:
            if "TRACE_RUN_ID_CHANGED_WITHIN_SLOT" not in anomalies:
                anomalies.append("TRACE_RUN_ID_CHANGED_WITHIN_SLOT")
        phase = row.get("phase")
        if phase not in KNOWN_PHASES:
            if "TRACE_UNKNOWN_PHASE" not in anomalies:
                anomalies.append("TRACE_UNKNOWN_PHASE")
            continue
        phase_index = PHASE_ORDER.get(str(phase), previous_phase_index)
        if phase_index < previous_phase_index:
            if "TRACE_PHASE_REGRESSION" not in anomalies:
                anomalies.append("TRACE_PHASE_REGRESSION")
        previous_phase_index = max(previous_phase_index, phase_index)
    return {
        "status": "CONSISTENT" if not anomalies else "INTEGRITY_FAILURE",
        "matched": len(matched), "examined": len(source), "anomalies": anomalies,
        "latest": matched[-1] if matched else None,
        "fingerprint": _stable_fp({"slot": scheduled_slot_kst, "rows": matched}) if matched else None,
    }


def _direct_failure_root(status: Mapping[str, Any]) -> tuple[str, str, list[str]]:
    root = status.get("root_cause")
    direct = (
        status.get("phase") in TERMINAL_FAILURE_PHASES
        and _present(status.get("failed_stage"))
        and _present(status.get("error_code"))
        and root not in _UNRESOLVED
        and _present(status.get("evidence"))
    )
    if direct:
        return str(root), "DIRECT", []
    return "ROOT_CAUSE_UNRESOLVED", "INCOMPLETE", ["PRODUCER_FAILURE_EVIDENCE_INCOMPLETE"]


def diagnose(*, scheduled_slot_kst: str, observed_at: str, is_enabled: bool,
             last_run_time: str | None, producer_status: Mapping[str, Any] | None,
             producer_history: Sequence[Mapping[str, Any]] | None = None,
             event_id: str | None = None, actor: str | None = None,
             reason: str | None = None, error_trace: str | None = None,
             updated_at: str | None = None) -> dict[str, Any]:
    slot, now, last_run = _parse_iso(scheduled_slot_kst), _parse_iso(observed_at), _parse_iso(last_run_time)
    if slot is None or now is None:
        raise ValueError("DIAGNOSTIC_TIME_INVALID")
    trace = inspect_trace_chain(producer_history, scheduled_slot_kst=scheduled_slot_kst, observed_at=observed_at) if producer_history is not None else {"status": "NOT_PROVIDED", "matched": 0, "anomalies": []}
    matching = bool(_matching(producer_status, scheduled_slot_kst))
    phase = producer_status.get("phase") if matching else None
    terminal = producer_status.get("terminal") if matching else None
    aux: list[str] = []
    root = None
    evidence_tier = "NONE"
    event_class = "HEALTHY"

    attribution_available = any(_present(v) for v in (event_id, actor, reason, error_trace))
    attribution = {
        "status": "AVAILABLE" if attribution_available else "CONTROL_PLANE_ATTRIBUTION_UNAVAILABLE",
        "event_id": event_id, "actor": actor, "reason": reason,
        "error_trace_present": _present(error_trace),
    }

    if trace.get("status") == "INTEGRITY_FAILURE":
        event_class = "EXCHANGE_TRACE_INTEGRITY_FAILURE"
        root = "ROOT_CAUSE_UNRESOLVED"
    elif matching and producer_status.get("schema_version") != PRODUCER_SCHEMA:
        event_class = "EXCHANGE_CONTRACT_VERSION_MISMATCH"
        root = "ROOT_CAUSE_UNRESOLVED"
    elif matching and (phase not in KNOWN_PHASES or not isinstance(terminal, bool) or terminal != (phase in TERMINAL_PHASES)):
        event_class = "EXCHANGE_RECEIPT_TERMINAL_MISMATCH"
        root = "ROOT_CAUSE_UNRESOLVED"
    elif matching and phase in TERMINAL_FAILURE_PHASES:
        event_class = "PRODUCER_REPORTED_FAILURE"
        root, evidence_tier, extra = _direct_failure_root(producer_status)
        aux.extend(extra)
    elif matching and phase not in TERMINAL_PHASES:
        producer_time = _parse_iso(producer_status.get("observed_at"))
        age = (now - producer_time).total_seconds() if producer_time else None
        if age is None or age >= STALE_AFTER_SECONDS:
            event_class = "RUN_STARTED_NO_TERMINAL_RECEIPT"
            root = "ROOT_CAUSE_UNRESOLVED"
    elif not matching and last_run is not None and last_run >= slot:
        event_class = "RUN_INVOKED_NO_PRODUCER_RECEIPT"
        root = "ROOT_CAUSE_UNRESOLVED"
    elif not matching and now >= slot and (last_run is None or last_run < slot):
        event_class = "SCHEDULE_GAP_NO_PRODUCER_START"
        aux.append("SCHEDULE_GAP_ACTIVE" if is_enabled else "SCHEDULE_GAP_DISABLED")
        root = "CONTROL_PLANE_EVIDENCE_AVAILABLE_REVIEW_REQUIRED" if attribution_available else "UNRESOLVED_CONTROL_PLANE"
    elif not is_enabled:
        event_class = "DISABLED_WITHOUT_PRODUCER_EVIDENCE"
        root = "CONTROL_PLANE_EVIDENCE_AVAILABLE_REVIEW_REQUIRED" if attribution_available else "UNRESOLVED_CONTROL_PLANE"

    if event_class == "HEALTHY" and not is_enabled:
        event_class = "POST_RUN_DISABLE" if matching and phase in TERMINAL_SUCCESS_PHASES else "DISABLED_WITHOUT_PRODUCER_EVIDENCE"
        root = "CONTROL_PLANE_EVIDENCE_AVAILABLE_REVIEW_REQUIRED" if attribution_available else "UNRESOLVED_CONTROL_PLANE"

    return {
        "diagnostic_version": DIAGNOSTIC_VERSION,
        "project": PROJECT, "task_id": TASK_ID, "monitor_task_id": MONITOR_TASK_ID,
        "system": SYSTEM, "scheduled_slot_kst": scheduled_slot_kst, "observed_at": observed_at,
        "is_enabled": is_enabled, "last_run_time": last_run_time, "updated_at": updated_at,
        "producer_status_present": matching, "producer_phase": phase, "producer_terminal": terminal,
        "event_class": event_class, "auxiliary_events": aux,
        "root_cause": root, "evidence_tier": evidence_tier,
        "attribution": attribution,
        "trace_status": trace.get("status"), "trace_matched": trace.get("matched", 0),
        "trace_anomalies": trace.get("anomalies", []),
        "root_cause_fabricated": False,
    }


def self_test() -> None:
    slot = "2026-09-14T19:00:00+09:00"
    assert same_instant(slot, "2026-09-14T10:00:00Z")
    gap = diagnose(scheduled_slot_kst=slot, observed_at="2026-09-14T19:06:00+09:00",
                   is_enabled=True, last_run_time="2026-09-14T18:00:03+09:00", producer_status=None)
    assert gap["event_class"] == "SCHEDULE_GAP_NO_PRODUCER_START"
    print("Instagram card root-cause diagnostics single-router: PASS")


if __name__ == "__main__":
    self_test()
