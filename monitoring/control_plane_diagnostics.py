#!/usr/bin/env python3
"""Evidence-first diagnostics for the existing core schedule watchdog.

This module is NOT a scheduler and never mutates automations. It converts
scheduler/producer snapshots into conservative incident records and bounded
recovery instructions for the single existing watchdog.
"""
from __future__ import annotations

import hashlib
import json
from collections import deque
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Mapping, Sequence

KST = timezone(timedelta(hours=9))
POST_RUN_DISABLE_WINDOW = timedelta(minutes=15)
PRODUCER_STALE_AFTER = timedelta(minutes=20)

WATCHDOG_ID = "6aa02cd749c0819196a6b17db6378958"
WATCHDOG_TITLE = "핵심 예약 작업 중지 감시"

MONITORED_TARGETS: dict[str, str] = {
    "6a98ce3a84ec8191b114f98ae66ba184": "인스타 애니정보",
    "6a9b8a22e72c8191849c273e1240378e": "인스타 카드정보",
    "6a9d514e332c8191b6b094259139ce6c": "릴스 AI 통합관리",
}
EXCLUDED_TARGETS = {
    "6a9b878f35bc8191963b8685566709c4",  # 카드시세분석
    "6a9a7637d124819192348b450508215f",  # 주식 통합
    "6a9e0eb9141081918bfd86a4e45a6a98",  # old reels-only watchdog
}

TERMINAL_SUCCESS_PHASES = frozenset({"VERIFIED_DELIVERY", "VERIFIED_NO_OUTPUT"})
TERMINAL_FAILURE_PHASES = frozenset({"FAILED", "BLOCKED", "DEGRADED"})
NONTERMINAL_PHASES = frozenset({
    "STARTED", "PREFLIGHT", "COLLECT", "VERIFY", "COLLECTION_HEALTH",
    "AI_RELIABILITY", "QUALITY_PROFILE", "RENDER", "OUTPUT_VALIDATION",
    "QUALITY_REVIEW", "LEARN", "GENRE_SELECT", "VISUAL_BUILD",
    "AUDIO_BUILD", "RENDERING", "LEARNING_UPDATE", "QUALITY",
})
ALL_KNOWN_PHASES = TERMINAL_SUCCESS_PHASES | TERMINAL_FAILURE_PHASES | NONTERMINAL_PHASES


class DiagnosticError(ValueError):
    pass


@lru_cache(maxsize=512)
def _parse_iso_cached(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DiagnosticError("invalid ISO-8601") from exc
    if parsed.tzinfo is None:
        raise DiagnosticError("timezone-aware value required")
    return parsed.astimezone(timezone.utc)


def _aware(value: object, field: str) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return _parse_iso_cached(str(value))
    except DiagnosticError as exc:
        raise DiagnosticError(f"{field}: {exc}") from exc


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _fingerprint(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _same_instant(a: object, b: object) -> bool:
    left = _aware(a, "left_time")
    right = _aware(b, "right_time")
    return left is not None and right is not None and left == right


def _nonempty(value: object) -> bool:
    return value not in (None, "", [], {})


def snapshot_target(state: Mapping[str, Any], *, observed_at: str, allow_watchdog: bool = False) -> dict[str, Any]:
    """Capture immutable scheduler evidence before classification or recovery."""
    task_id = str(state.get("id") or state.get("task_id") or "")
    if task_id in EXCLUDED_TARGETS:
        raise DiagnosticError("target is explicitly excluded from this watchdog")

    expected_title = MONITORED_TARGETS.get(task_id)
    if task_id == WATCHDOG_ID and allow_watchdog:
        expected_title = WATCHDOG_TITLE
    if expected_title is None:
        raise DiagnosticError("target is outside the fixed watchdog scope")

    observed = _aware(observed_at, "observed_at")
    updated = _aware(state.get("updated_at"), "updated_at")
    last_run = _aware(state.get("last_run_time"), "last_run_time")
    enabled = state.get("is_enabled")
    if not isinstance(enabled, bool):
        raise DiagnosticError("is_enabled must be boolean")

    title = str(state.get("title") or "")
    schedule = state.get("schedule")
    timing_mode = state.get("timing_mode")
    prompt = state.get("prompt")
    return {
        "task_id": task_id,
        "title": title,
        "expected_title": expected_title,
        "title_matches_expected": title == expected_title,
        "is_enabled": enabled,
        "schedule": schedule,
        "timing_mode": timing_mode,
        "updated_at": _iso(updated),
        "last_run_time": _iso(last_run),
        "snapshot_observed_at": _iso(observed),
        "fingerprints": {
            "title": _fingerprint(title),
            "schedule": _fingerprint(schedule),
            "timing_mode": _fingerprint(timing_mode),
            "prompt": _fingerprint(prompt),
        },
    }


def compare_snapshots(previous: Mapping[str, Any] | None, current: Mapping[str, Any]) -> dict[str, Any]:
    fields = ("is_enabled", "title", "schedule", "timing_mode")
    if not previous:
        return {
            "changed_fields": [],
            "change_window_start": None,
            "change_window_end": current.get("updated_at") or current.get("snapshot_observed_at"),
            "metadata_drift": [],
        }
    changed = [name for name in fields if previous.get(name) != current.get(name)]
    prev_prompt = (previous.get("fingerprints") or {}).get("prompt")
    cur_prompt = (current.get("fingerprints") or {}).get("prompt")
    if prev_prompt != cur_prompt:
        changed.append("prompt")
    metadata_drift = [x for x in changed if x in {"title", "schedule", "timing_mode", "prompt"}]
    return {
        "changed_fields": changed,
        "change_window_start": previous.get("snapshot_observed_at"),
        "change_window_end": current.get("updated_at") or current.get("snapshot_observed_at"),
        "metadata_drift": metadata_drift,
    }


def _attribution(evidence: Mapping[str, Any] | None) -> dict[str, Any]:
    evidence = evidence or {}
    actor = evidence.get("actor")
    reason = evidence.get("reason")
    error_trace = evidence.get("error_trace")
    available = any(_nonempty(value) for value in (actor, reason, error_trace))
    return {
        "status": "AVAILABLE" if available else "CONTROL_PLANE_ATTRIBUTION_UNAVAILABLE",
        "actor_available": _nonempty(actor),
        "reason_available": _nonempty(reason),
        "error_trace_available": _nonempty(error_trace),
        "actor": actor if _nonempty(actor) else None,
        "reason": reason if _nonempty(reason) else None,
        "error_trace": error_trace if _nonempty(error_trace) else None,
    }


def _producer_evidence(status: Mapping[str, Any] | None, scheduled_slot: str | None, *, observed_at: str | None = None, explicit_age_seconds: float | None = None) -> dict[str, Any]:
    if not isinstance(status, Mapping):
        return {"present": False, "matching_slot": False, "phase": None, "terminal": None, "age_seconds": None, "integrity_events": []}
    try:
        matching = bool(scheduled_slot and _same_instant(status.get("scheduled_slot_kst"), scheduled_slot))
    except DiagnosticError:
        matching = False
    if not matching:
        return {"present": False, "matching_slot": False, "phase": None, "terminal": None, "age_seconds": None, "integrity_events": []}

    phase = status.get("phase")
    terminal = status.get("terminal")
    integrity_events: list[str] = []
    if phase not in ALL_KNOWN_PHASES:
        integrity_events.append("EXCHANGE_UNKNOWN_PHASE")
    if not isinstance(terminal, bool):
        integrity_events.append("EXCHANGE_TERMINAL_FLAG_INVALID")
    elif phase in TERMINAL_SUCCESS_PHASES | TERMINAL_FAILURE_PHASES:
        if terminal is False:
            integrity_events.append("EXCHANGE_RECEIPT_TERMINAL_MISMATCH")
    elif phase in NONTERMINAL_PHASES and terminal is True:
        integrity_events.append("EXCHANGE_RECEIPT_TERMINAL_MISMATCH")

    age_seconds = explicit_age_seconds
    if age_seconds is None and observed_at and status.get("observed_at"):
        now = _aware(observed_at, "observed_at")
        producer_observed = _aware(status.get("observed_at"), "producer.observed_at")
        if now is not None and producer_observed is not None:
            age_seconds = max(0.0, (now - producer_observed).total_seconds())

    return {
        "present": True,
        "matching_slot": True,
        "phase": phase,
        "terminal": terminal,
        "observed_at": status.get("observed_at"),
        "failed_stage": status.get("failed_stage"),
        "error_code": status.get("error_code"),
        "root_cause": status.get("root_cause"),
        "evidence": status.get("evidence"),
        "age_seconds": age_seconds,
        "integrity_events": integrity_events,
    }


def classify_observation(current: Mapping[str, Any], *, previous: Mapping[str, Any] | None = None, post_recovery: Mapping[str, Any] | None = None, scheduled_slot: str | None = None, slot_due: bool = False, last_run_advanced: bool = False, producer_status: Mapping[str, Any] | None = None, producer_status_age_seconds: float | None = None, attribution_evidence: Mapping[str, Any] | None = None, recurrence_count: int = 0, user_stop_recorded: bool = False, exchange_status: str = "UNKNOWN") -> dict[str, Any]:
    """Classify one observed target without inventing a root cause."""
    task_id = current.get("task_id")
    if task_id not in MONITORED_TARGETS and task_id != WATCHDOG_ID:
        raise DiagnosticError("snapshot target outside fixed scope")
    if isinstance(recurrence_count, bool) or recurrence_count < 0:
        raise DiagnosticError("recurrence_count must be a non-negative integer")

    comparison = compare_snapshots(previous, current)
    attr = _attribution(attribution_evidence)
    producer = _producer_evidence(producer_status, scheduled_slot, observed_at=current.get("snapshot_observed_at"), explicit_age_seconds=producer_status_age_seconds)

    enabled = bool(current.get("is_enabled"))
    updated = _aware(current.get("updated_at"), "updated_at")
    last_run = _aware(current.get("last_run_time"), "last_run_time")
    auxiliary: list[str] = list(producer.get("integrity_events") or [])
    event = "HEALTHY"
    failed_stage = None
    root_cause = None
    control_plane_event = False

    metadata = set(comparison["metadata_drift"])
    if {"schedule", "timing_mode"} & metadata:
        auxiliary.append("SCHEDULE_DRIFT")
    if {"title", "prompt"} & metadata:
        auxiliary.append("CONTENT_METADATA_DRIFT")

    if post_recovery and post_recovery.get("is_enabled") is True and not enabled:
        event = "PAUSE_RECURRENCE_CRITICAL" if recurrence_count >= 3 else "RECOVERY_REGRESSION"
        failed_stage = "CONTROL_PLANE"
        root_cause = "UNRESOLVED_CONTROL_PLANE"
        control_plane_event = True
    elif slot_due and not last_run_advanced and not producer["present"]:
        event = "SCHEDULE_GAP_NO_PRODUCER_START"
        failed_stage = "BEFORE_PRODUCER_START"
        root_cause = "UNRESOLVED_CONTROL_PLANE"
        control_plane_event = True
        if enabled:
            auxiliary.append("SCHEDULE_GAP_ACTIVE")
    elif slot_due and last_run_advanced and not producer["present"]:
        event = "RUN_INVOKED_NO_PRODUCER_RECEIPT"
        failed_stage = "EXCHANGE_PERSISTENCE"
        root_cause = "ROOT_CAUSE_UNRESOLVED"
    elif producer["present"] and "EXCHANGE_RECEIPT_TERMINAL_MISMATCH" in auxiliary:
        event = "EXCHANGE_RECEIPT_TERMINAL_MISMATCH"
        failed_stage = producer.get("failed_stage") or producer.get("phase") or "EXCHANGE_PERSISTENCE"
        root_cause = "ROOT_CAUSE_UNRESOLVED"
    elif producer["present"] and producer.get("phase") in TERMINAL_FAILURE_PHASES:
        event = "PRODUCER_REPORTED_FAILURE"
        failed_stage = producer.get("failed_stage") or producer.get("phase")
        if _nonempty(producer.get("evidence")) and _nonempty(producer.get("error_code")):
            root_cause = producer.get("root_cause") or "ROOT_CAUSE_UNRESOLVED"
        else:
            root_cause = "ROOT_CAUSE_UNRESOLVED"
            auxiliary.append("PRODUCER_FAILURE_EVIDENCE_INCOMPLETE")
    elif producer["present"] and producer.get("phase") in NONTERMINAL_PHASES and producer.get("age_seconds") is not None and producer["age_seconds"] >= PRODUCER_STALE_AFTER.total_seconds():
        event = "RUN_STARTED_NO_TERMINAL_RECEIPT"
        failed_stage = producer.get("phase")
        root_cause = "ROOT_CAUSE_UNRESOLVED"
    elif producer["present"] and producer.get("phase") in TERMINAL_SUCCESS_PHASES and not enabled:
        event = "POST_RUN_DISABLE"
        failed_stage = "AFTER_VERIFIED_TERMINAL"
        root_cause = "UNRESOLVED_CONTROL_PLANE"
        control_plane_event = True
    elif not enabled:
        event = "DISABLE_BETWEEN_RUNS"
        if updated is not None and last_run is not None and timedelta(0) <= updated - last_run <= POST_RUN_DISABLE_WINDOW:
            event = "POST_RUN_DISABLE"
        failed_stage = "CONTROL_PLANE"
        root_cause = "UNRESOLVED_CONTROL_PLANE"
        control_plane_event = True
    elif auxiliary:
        if "SCHEDULE_DRIFT" in auxiliary:
            event = "SCHEDULE_DRIFT"
            failed_stage = "CONTROL_PLANE_METADATA"
            root_cause = "UNRESOLVED_CONTROL_PLANE"
            control_plane_event = True
        elif "CONTENT_METADATA_DRIFT" in auxiliary:
            event = "CONTENT_METADATA_DRIFT"
            failed_stage = "CONTROL_PLANE_METADATA"
            root_cause = "UNRESOLVED_CONTROL_PLANE"
            control_plane_event = True
        else:
            event = auxiliary[0]
            failed_stage = producer.get("phase") or "EXCHANGE_PERSISTENCE"
            root_cause = "ROOT_CAUSE_UNRESOLVED"

    if control_plane_event and attr["status"] == "AVAILABLE":
        root_cause = "CONTROL_PLANE_EVIDENCE_AVAILABLE_REVIEW_REQUIRED"

    recovery_allowed = not enabled and not user_stop_recorded and task_id in MONITORED_TARGETS
    recovery_plan = {
        "allowed": recovery_allowed,
        "reason": "TARGET_DISABLED_WITHOUT_USER_STOP" if recovery_allowed else "NONE",
        "changes": {"is_enabled": True} if recovery_allowed else {},
        "preserve_title": True,
        "preserve_schedule": True,
        "preserve_timing_mode": True,
        "preserve_prompt": True,
        "source_code_auto_patch_allowed": False,
        "duplicate_catchup_allowed": False,
    }

    incident_fingerprint = _fingerprint({
        "task_id": task_id,
        "event": event,
        "last_run_time": current.get("last_run_time"),
        "updated_at_before": current.get("updated_at"),
    })
    pattern_fingerprint = _fingerprint({
        "task_id": task_id,
        "event": event,
        "enabled": enabled,
        "changed_fields": sorted(comparison["changed_fields"]),
        "attribution": attr["status"],
        "schedule_drift": "SCHEDULE_DRIFT" in auxiliary or event == "SCHEDULE_DRIFT",
        "metadata_drift": bool(metadata),
        "correlated_mutation": False,
    })

    return {
        "schema_version": "1.1-core-watchdog-diagnostics",
        "watchdog_id": WATCHDOG_ID,
        "task_id": task_id,
        "title": current.get("title"),
        "event_class": event,
        "auxiliary_events": sorted(set(auxiliary)),
        "scheduled_slot": scheduled_slot,
        "slot_due": bool(slot_due),
        "last_run_advanced": bool(last_run_advanced),
        "last_run_time": current.get("last_run_time"),
        "is_enabled_before": enabled,
        "updated_at_before": current.get("updated_at"),
        "snapshot_observed_at": current.get("snapshot_observed_at"),
        "changed_fields": comparison["changed_fields"],
        "change_window_start": comparison["change_window_start"],
        "change_window_end": comparison["change_window_end"],
        "producer_status_present": producer["present"],
        "producer_phase": producer.get("phase"),
        "producer_terminal": producer.get("terminal"),
        "producer_status_age_seconds": producer.get("age_seconds"),
        "exchange_status": exchange_status,
        "failed_stage": failed_stage,
        "root_cause": root_cause,
        "attribution": attr,
        "user_stop_recorded": bool(user_stop_recorded),
        "recurrence_count": recurrence_count,
        "incident_fingerprint": incident_fingerprint,
        "pattern_fingerprint": pattern_fingerprint,
        "recovery_plan": recovery_plan,
        "do_not_guess_root_cause": True,
    }


def correlate_control_plane_mutations(records: Sequence[Mapping[str, Any]], *, window_seconds: int = 180) -> dict[str, Any]:
    """Flag the strongest correlation candidate in O(n log n) sorting + O(n) scan."""
    if window_seconds <= 0:
        raise DiagnosticError("window_seconds must be positive")
    points: list[tuple[datetime, str]] = []
    for item in records:
        if item.get("task_id") not in MONITORED_TARGETS:
            continue
        when = _aware(item.get("updated_at_before"), "updated_at_before")
        if when is not None and item.get("event_class") not in {"HEALTHY", None}:
            points.append((when, str(item.get("task_id"))))
    points.sort()

    window: deque[tuple[datetime, str]] = deque()
    counts: dict[str, int] = {}
    best_ids: set[str] = set()
    for point in points:
        when, task_id = point
        window.append(point)
        counts[task_id] = counts.get(task_id, 0) + 1
        while window and (when - window[0][0]).total_seconds() > window_seconds:
            _, old_task = window.popleft()
            counts[old_task] -= 1
            if counts[old_task] <= 0:
                del counts[old_task]
        current_ids = set(counts)
        if len(current_ids) > len(best_ids):
            best_ids = current_ids

    ids = sorted(best_ids)
    candidate = len(ids) >= 2
    return {
        "candidate": candidate,
        "event_class": "CORRELATED_CONTROL_PLANE_MUTATION" if candidate else "NONE",
        "task_ids": ids,
        "window_seconds": window_seconds,
        "common_cause_asserted": False,
        "root_cause": "UNRESOLVED_CONTROL_PLANE" if candidate else None,
    }


def assess_recovery_verification(*, before: Mapping[str, Any], immediate: Mapping[str, Any] | None, same_execution: Mapping[str, Any] | None, next_slot: Mapping[str, Any] | None, next_slot_executed: bool, next_slot_exchange_verified: bool | None = None) -> dict[str, Any]:
    """Keep recovery-created updated_at separate from incident-pre evidence."""
    updated_before = before.get("updated_at")
    updated_after = immediate.get("updated_at") if immediate else None
    immediate_ok = bool(immediate and immediate.get("is_enabled") is True)
    same_execution_ok = bool(same_execution and same_execution.get("is_enabled") is True)
    next_enabled = bool(next_slot and next_slot.get("is_enabled") is True)
    exchange_ok = True if next_slot_exchange_verified is None else bool(next_slot_exchange_verified)
    verified = bool(immediate_ok and same_execution_ok and next_enabled and next_slot_executed and exchange_ok)
    return {
        "updated_at_before": updated_before,
        "updated_at_after_recovery": updated_after,
        "immediate_verified": immediate_ok,
        "same_execution_verified": same_execution_ok,
        "next_slot_enabled": next_enabled,
        "next_slot_executed": bool(next_slot_executed),
        "next_slot_exchange_verified": next_slot_exchange_verified,
        "recovery_verified": verified,
        "incident_pre_updated_at_preserved": updated_before != updated_after or updated_after is None,
    }
