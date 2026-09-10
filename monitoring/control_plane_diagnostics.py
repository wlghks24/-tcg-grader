#!/usr/bin/env python3
"""Evidence-first diagnostics for the existing core schedule watchdog.

This module is NOT a scheduler and never mutates automations. It only turns
observed scheduler/producer snapshots into conservative incident records and a
bounded recovery instruction for the existing watchdog.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
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

TERMINAL_SUCCESS_PHASES = {"VERIFIED_DELIVERY", "VERIFIED_NO_OUTPUT"}
TERMINAL_FAILURE_PHASES = {"FAILED", "BLOCKED", "DEGRADED"}
NONTERMINAL_PHASES = {
    "STARTED", "PREFLIGHT", "COLLECT", "VERIFY", "COLLECTION_HEALTH",
    "AI_RELIABILITY", "QUALITY_PROFILE", "RENDER", "OUTPUT_VALIDATION",
    "QUALITY_REVIEW", "LEARN", "GENRE_SELECT", "VISUAL_BUILD",
    "AUDIO_BUILD", "RENDERING", "LEARNING_UPDATE", "QUALITY",
}


class DiagnosticError(ValueError):
    pass


def _aware(value: object, field: str) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise DiagnosticError(f"{field}: invalid ISO-8601") from exc
    if parsed.tzinfo is None:
        raise DiagnosticError(f"{field}: timezone-aware value required")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _fingerprint(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _same_instant(a: object, b: object) -> bool:
    left = _aware(a, "left_time")
    right = _aware(b, "right_time")
    return left is not None and right is not None and left == right


def snapshot_target(state: Mapping[str, Any], *, observed_at: str, allow_watchdog: bool = False) -> dict[str, Any]:
    """Capture immutable scheduler evidence before classification or recovery."""
    task_id = str(state.get("id") or state.get("task_id") or "")
    allowed = dict(MONITORED_TARGETS)
    if allow_watchdog:
        allowed[WATCHDOG_ID] = WATCHDOG_TITLE
    if task_id in EXCLUDED_TARGETS:
        raise DiagnosticError("target is explicitly excluded from this watchdog")
    if task_id not in allowed:
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
    expected_title = allowed[task_id]
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
    available = any(value not in (None, "", [], {}) for value in (actor, reason, error_trace))
    return {
        "status": "AVAILABLE" if available else "CONTROL_PLANE_ATTRIBUTION_UNAVAILABLE",
        "actor_available": actor not in (None, "", [], {}),
        "reason_available": reason not in (None, "", [], {}),
        "error_trace_available": error_trace not in (None, "", [], {}),
        "actor": actor if actor not in (None, "") else None,
        "reason": reason if reason not in (None, "") else None,
        "error_trace": error_trace if error_trace not in (None, "") else None,
    }


def _producer_evidence(status: Mapping[str, Any] | None, scheduled_slot: str | None) -> dict[str, Any]:
    if not isinstance(status, Mapping):
        return {"present": False, "matching_slot": False, "phase": None, "terminal": None, "age_seconds": None}
    matching = bool(scheduled_slot and _same_instant(status.get("scheduled_slot_kst"), scheduled_slot))
    phase = status.get("phase") if matching else None
    terminal = status.get("terminal") if matching else None
    return {
        "present": bool(matching),
        "matching_slot": matching,
        "phase": phase,
        "terminal": terminal,
        "observed_at": status.get("observed_at") if matching else None,
        "failed_stage": status.get("failed_stage") if matching else None,
        "error_code": status.get("error_code") if matching else None,
        "root_cause": status.get("root_cause") if matching else None,
        "evidence": status.get("evidence") if matching else None,
    }


def classify_observation(
    current: Mapping[str, Any],
    *,
    previous: Mapping[str, Any] | None = None,
    post_recovery: Mapping[str, Any] | None = None,
    scheduled_slot: str | None = None,
    slot_due: bool = False,
    last_run_advanced: bool = False,
    producer_status: Mapping[str, Any] | None = None,
    producer_status_age_seconds: float | None = None,
    attribution_evidence: Mapping[str, Any] | None = None,
    recurrence_count: int = 0,
    user_stop_recorded: bool = False,
    exchange_status: str = "UNKNOWN",
) -> dict[str, Any]:
    """Classify one observed target without inventing a root cause."""
    if current.get("task_id") not in MONITORED_TARGETS and current.get("task_id") != WATCHDOG_ID:
        raise DiagnosticError("snapshot target outside fixed scope")
    if isinstance(recurrence_count, bool) or recurrence_count < 0:
        raise DiagnosticError("recurrence_count must be a non-negative integer")

    comparison = compare_snapshots(previous, current)
    attr = _attribution(attribution_evidence)
    producer = _producer_evidence(producer_status, scheduled_slot)
    producer["age_seconds"] = producer_status_age_seconds if producer["present"] else None

    enabled = bool(current.get("is_enabled"))
    updated = _aware(current.get("updated_at"), "updated_at")
    last_run = _aware(current.get("last_run_time"), "last_run_time")
    auxiliary: list[str] = []
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
    elif producer["present"] and producer.get("phase") in TERMINAL_FAILURE_PHASES:
        event = "PRODUCER_REPORTED_FAILURE"
        failed_stage = producer.get("failed_stage") or producer.get("phase")
        root_cause = producer.get("root_cause") or "ROOT_CAUSE_UNRESOLVED"
    elif (
        producer["present"]
        and producer.get("phase") in NONTERMINAL_PHASES
        and producer_status_age_seconds is not None
        and producer_status_age_seconds >= PRODUCER_STALE_AFTER.total_seconds()
    ):
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
        event = auxiliary[0]
        failed_stage = "CONTROL_PLANE_METADATA"
        root_cause = "UNRESOLVED_CONTROL_PLANE"
        control_plane_event = True

    if control_plane_event and attr["status"] == "AVAILABLE":
        root_cause = "CONTROL_PLANE_EVIDENCE_AVAILABLE_REVIEW_REQUIRED"

    recovery_allowed = not enabled and not user_stop_recorded and current.get("task_id") in MONITORED_TARGETS
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
        "task_id": current.get("task_id"),
        "event": event,
        "last_run_time": current.get("last_run_time"),
        "updated_at_before": current.get("updated_at"),
    })
    pattern_fingerprint = _fingerprint({
        "task_id": current.get("task_id"),
        "event": event,
        "enabled": enabled,
        "changed_fields": sorted(comparison["changed_fields"]),
        "attribution": attr["status"],
        "schedule_drift": "SCHEDULE_DRIFT" in auxiliary or event == "SCHEDULE_DRIFT",
        "metadata_drift": bool(metadata),
        "producer_present": producer["present"],
    })

    return {
        "schema_version": "1.0-core-watchdog-diagnostics",
        "watchdog_id": WATCHDOG_ID,
        "task_id": current.get("task_id"),
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
    """Flag a correlation candidate without claiming a common cause."""
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
    best: list[tuple[datetime, str]] = []
    for i, start in enumerate(points):
        group = [start]
        for candidate in points[i + 1:]:
            if (candidate[0] - start[0]).total_seconds() <= window_seconds:
                group.append(candidate)
            else:
                break
        if len({task_id for _, task_id in group}) > len({task_id for _, task_id in best}):
            best = group
    ids = sorted({task_id for _, task_id in best})
    return {
        "candidate": len(ids) >= 2,
        "event_class": "CORRELATED_CONTROL_PLANE_MUTATION" if len(ids) >= 2 else "NONE",
        "task_ids": ids,
        "window_seconds": window_seconds,
        "common_cause_asserted": False,
        "root_cause": "UNRESOLVED_CONTROL_PLANE" if len(ids) >= 2 else None,
    }


def assess_recovery_verification(
    *,
    before: Mapping[str, Any],
    immediate: Mapping[str, Any] | None,
    same_execution: Mapping[str, Any] | None,
    next_slot: Mapping[str, Any] | None,
    next_slot_executed: bool,
) -> dict[str, Any]:
    """Keep recovery-created updated_at separate from incident-pre evidence."""
    updated_before = before.get("updated_at")
    updated_after = immediate.get("updated_at") if immediate else None
    immediate_ok = bool(immediate and immediate.get("is_enabled") is True)
    same_execution_ok = bool(same_execution and same_execution.get("is_enabled") is True)
    next_enabled = bool(next_slot and next_slot.get("is_enabled") is True)
    verified = bool(immediate_ok and same_execution_ok and next_enabled and next_slot_executed)
    return {
        "updated_at_before": updated_before,
        "updated_at_after_recovery": updated_after,
        "immediate_verified": immediate_ok,
        "same_execution_verified": same_execution_ok,
        "next_slot_enabled": next_enabled,
        "next_slot_executed": bool(next_slot_executed),
        "recovery_verified": verified,
        "incident_pre_updated_at_preserved": updated_before != updated_after or updated_after is None,
    }
