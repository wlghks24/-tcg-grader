#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

KST = dt.timezone(dt.timedelta(hours=9))
SCHEDULE_RUN_EARLY_GRACE = dt.timedelta(minutes=5)
POST_RUN_DISABLE_WINDOW = dt.timedelta(minutes=15)

CANONICAL_ID = "6a9b8a22e72c8191849c273e1240378e"
CANONICAL_TITLE = "인스타 카드정보"
AI_RELIABILITY_PROJECT = "instagram_card"
AI_RELIABILITY_TASK_ID = CANONICAL_ID

NON_FATAL_PRECHECK_CODES = {
    "BASELINE_MISSING",
    "REVISION_BASELINE_MISSING",
    "SNAPSHOT_BUILDING",
    "NO_VERIFIED_FACTS",
    "INSUFFICIENT_VERIFIED_FACTS",
    "INSUFFICIENT_COMPLETED_SALES",
    "NO_COMPARABLE_DATA",
    "PRECHECK_DATA_NOT_READY",
}
PRECHECK_STAGES = {"preflight", "production_preflight", "revision_preflight"}
FINGERPRINT_FIELDS = ("title", "schedule", "timing_mode", "prompt")


class AutomationStateGuardError(ValueError):
    pass


def build_ai_reliability_bridge(state_root: str | Path):
    """Build the additive v8 bridge for this canonical task only."""
    from ai_reliability_v8 import ReliabilityBridge

    return ReliabilityBridge(
        Path(state_root),
        project=AI_RELIABILITY_PROJECT,
        task_id=AI_RELIABILITY_TASK_ID,
    )


def _aware(value: str | None, field: str) -> dt.datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise AutomationStateGuardError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise AutomationStateGuardError(f"{field} must be timezone-aware")
    return parsed.astimezone(dt.timezone.utc)


def _stable_fingerprint(value: Any) -> str | None:
    if value is None:
        return None
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def snapshot_state(state: dict[str, Any], *, observed_at: str) -> dict[str, Any]:
    """Create an immutable diagnostic snapshot without mutating scheduler state."""
    if state.get("id") != CANONICAL_ID:
        raise AutomationStateGuardError("unexpected automation id")
    if state.get("title") != CANONICAL_TITLE:
        raise AutomationStateGuardError("unexpected automation title")
    observed = _aware(observed_at, "observed_at")
    updated = _aware(state.get("updated_at"), "updated_at")
    last_run = _aware(state.get("last_run_time"), "last_run_time")
    enabled = state.get("is_enabled")
    if not isinstance(enabled, bool):
        raise AutomationStateGuardError("is_enabled must be boolean")

    return {
        "task_id": CANONICAL_ID,
        "title": CANONICAL_TITLE,
        "is_enabled": enabled,
        "schedule": state.get("schedule"),
        "timing_mode": state.get("timing_mode"),
        "prompt": state.get("prompt"),
        "updated_at": updated.isoformat() if updated else None,
        "last_run_time": last_run.isoformat() if last_run else None,
        "snapshot_observed_at": observed.isoformat(),
        "fingerprints": {
            field: _stable_fingerprint(state.get(field))
            for field in FINGERPRINT_FIELDS
        },
    }


def compare_snapshots(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
) -> dict[str, Any]:
    """Return changed fields and a conservative observation change window."""
    if not previous:
        return {
            "changed_fields": [],
            "change_window_start": None,
            "change_window_end": current["snapshot_observed_at"],
            "baseline_match": None,
        }

    tracked = ("is_enabled", "title", "schedule", "timing_mode", "prompt")
    changed = [field for field in tracked if previous.get(field) != current.get(field)]
    return {
        "changed_fields": changed,
        "change_window_start": previous.get("snapshot_observed_at"),
        "change_window_end": current.get("updated_at") or current.get("snapshot_observed_at"),
        "baseline_match": not bool(changed),
    }


def _missed_slot_gap_start(
    *,
    last_run: dt.datetime | None,
    updated: dt.datetime | None,
    observed: dt.datetime,
) -> tuple[dt.datetime, str]:
    if last_run is not None:
        return last_run + SCHEDULE_RUN_EARLY_GRACE, "last_run_plus_early_grace"
    if updated is not None:
        return updated, "state_updated_at"
    return observed, "observed_at"


def _hourly_half_past_slots(start: dt.datetime, end: dt.datetime) -> list[str]:
    if end <= start:
        return []
    start_kst = start.astimezone(KST)
    end_kst = end.astimezone(KST)
    cursor = start_kst.replace(minute=30, second=0, microsecond=0)
    if cursor <= start_kst:
        cursor += dt.timedelta(hours=1)
    slots: list[str] = []
    while cursor < end_kst:
        slots.append(cursor.isoformat(timespec="minutes"))
        cursor += dt.timedelta(hours=1)
    return slots


def _schedule_start_disable_without_run(
    updated: dt.datetime | None,
    last_run: dt.datetime | None,
) -> tuple[bool, str | None]:
    if updated is None:
        return False, None
    updated_kst = updated.astimezone(KST)
    slot_kst = updated_kst.replace(minute=30, second=0, microsecond=0)
    if updated_kst.minute < 30:
        slot_kst -= dt.timedelta(hours=1)
    delta = updated_kst - slot_kst
    if delta < dt.timedelta(0) or delta > POST_RUN_DISABLE_WINDOW:
        return False, None
    slot_utc = slot_kst.astimezone(dt.timezone.utc)
    if last_run is not None and last_run >= slot_utc:
        return False, None
    return True, slot_kst.isoformat(timespec="minutes")


def _disable_event_class(
    *,
    updated: dt.datetime | None,
    last_run: dt.datetime | None,
    recurrence_count: int,
) -> str:
    if recurrence_count >= 3:
        return "PAUSE_RECURRENCE_CRITICAL"
    if updated is not None and last_run is not None:
        delta = updated - last_run
        if dt.timedelta(0) <= delta <= POST_RUN_DISABLE_WINDOW:
            return "POST_RUN_DISABLE"
    return "DISABLE_BETWEEN_RUNS"


def runtime_failure_policy(
    *,
    stage: str,
    error_code: str,
    retryable: bool,
) -> dict[str, Any]:
    """Keep run-level failures from mutating the scheduler control plane."""
    stage = str(stage or "UNKNOWN").strip() or "UNKNOWN"
    error_code = str(error_code or "UNKNOWN_ERROR").strip() or "UNKNOWN_ERROR"
    is_precheck_not_ready = (
        stage.lower() in PRECHECK_STAGES
        or error_code.upper() in NON_FATAL_PRECHECK_CODES
    )
    if is_precheck_not_ready:
        run_status = "PRECHECK_NOT_READY"
        next_action = "COMPLETE_RUN_AND_KEEP_NEXT_SLOT"
    else:
        run_status = "DEGRADED" if retryable else "BLOCKED"
        next_action = "BOUNDED_RETRY" if retryable else "RECORD_AND_CONTINUE_NEXT_SLOT"
    return {
        "stage": stage,
        "error_code": error_code,
        "run_status": run_status,
        "automation_state_mutation_allowed": False,
        "self_disable_allowed": False,
        "self_pause_allowed": False,
        "self_reschedule_allowed": False,
        "preserve_enabled_state": True,
        "preserve_title": True,
        "preserve_schedule": True,
        "scheduler_terminal": False,
        "automation_continues": True,
        "next_action": next_action,
    }


def classify_pause(
    state: dict[str, Any],
    *,
    observed_at: str,
    cause_evidence: dict[str, Any] | None = None,
    prior_pause_count: int = 0,
    previous_snapshot: dict[str, Any] | None = None,
    post_recovery_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify pause *and* active schedule-gap incidents from one snapshot."""
    if isinstance(prior_pause_count, bool) or not isinstance(prior_pause_count, int) or prior_pause_count < 0:
        raise AutomationStateGuardError("prior_pause_count must be a non-negative integer")

    snapshot = snapshot_state(state, observed_at=observed_at)
    observed = _aware(snapshot["snapshot_observed_at"], "snapshot_observed_at")
    updated = _aware(snapshot["updated_at"], "updated_at")
    last_run = _aware(snapshot["last_run_time"], "last_run_time")
    enabled = bool(snapshot["is_enabled"])
    pause_incident = not enabled

    gap_start, gap_anchor = _missed_slot_gap_start(
        last_run=last_run,
        updated=updated,
        observed=observed,
    )
    # Schedule integrity is independent of enabled state. An active task can
    # miss a slot, which must be reported without forcing a duplicate catch-up.
    missed_slots = _hourly_half_past_slots(gap_start, observed)
    schedule_gap = bool(missed_slots)
    schedule_gap_active = enabled and schedule_gap
    missed_0630 = any(slot[11:16] == "06:30" for slot in missed_slots)

    recurrence_count = prior_pause_count + (1 if pause_incident else 0)
    schedule_disable_without_run = False
    schedule_disable_slot_kst = None
    state_transition_fingerprint = None
    if pause_incident:
        schedule_disable_without_run, schedule_disable_slot_kst = _schedule_start_disable_without_run(
            updated, last_run
        )
        if schedule_disable_without_run:
            state_transition_fingerprint = "SCHEDULE_START_DISABLE_WITHOUT_RUN"

    actor = str((cause_evidence or {}).get("actor") or "").strip()
    reason = str((cause_evidence or {}).get("reason") or "").strip()
    error_trace = str((cause_evidence or {}).get("error_trace") or "").strip()
    has_attribution = bool(actor and reason)
    cause_status = "not_applicable"
    cause_class = "NONE"
    if pause_incident or schedule_gap:
        if has_attribution:
            cause_status = "evidence_backed"
            cause_class = str((cause_evidence or {}).get("cause_class") or "EXPLICIT_STATE_CHANGE")
        else:
            cause_status = "unresolved"
            cause_class = "CONTROL_PLANE_ATTRIBUTION_UNAVAILABLE"

    if pause_incident:
        event_class = _disable_event_class(
            updated=updated,
            last_run=last_run,
            recurrence_count=recurrence_count,
        )
    elif schedule_gap_active:
        event_class = "SCHEDULE_GAP_ACTIVE"
    elif schedule_gap:
        event_class = "SCHEDULE_GAP"
    else:
        event_class = "NONE"

    comparison = compare_snapshots(previous_snapshot, snapshot)
    post_recovery_match = None
    if post_recovery_snapshot:
        post_recovery_match = compare_snapshots(post_recovery_snapshot, snapshot)["baseline_match"]
        if (
            post_recovery_snapshot.get("is_enabled") is True
            and snapshot["is_enabled"] is False
        ):
            event_class = (
                "PAUSE_RECURRENCE_CRITICAL"
                if recurrence_count >= 3
                else "RECOVERY_REGRESSION"
            )

    severity = "NONE"
    if pause_incident and recurrence_count >= 2:
        # Backward-compatible recurrence severity; CRITICAL priority starts at 3.
        severity = "PAUSE_RECURRENCE_CRITICAL"
    elif event_class != "NONE":
        severity = "INCIDENT"
    priority = "CRITICAL" if recurrence_count >= 3 else ("HIGH" if event_class != "NONE" else "NORMAL")

    required_action = "NONE"
    if pause_incident:
        required_action = "REACTIVATE_EXISTING_CANONICAL_AUTOMATION"
    elif schedule_gap_active:
        required_action = "MONITOR_NEXT_SLOT_NO_DUPLICATE_CATCHUP"

    return {
        "schema_version": "1.2",
        "automation_id": CANONICAL_ID,
        "title": CANONICAL_TITLE,
        "pause_detected": pause_incident,
        "schedule_gap_detected": schedule_gap,
        "schedule_gap_active": schedule_gap_active,
        "event_class": event_class,
        "enabled_observed": enabled,
        "desired_enabled_state": True,
        "observed_at": snapshot["snapshot_observed_at"],
        "state_updated_at": snapshot["updated_at"],
        "last_run_time": snapshot["last_run_time"],
        "snapshot": snapshot,
        "changed_fields": comparison["changed_fields"],
        "change_window_start": comparison["change_window_start"],
        "change_window_end": comparison["change_window_end"],
        "baseline_match": comparison["baseline_match"],
        "post_recovery_match": post_recovery_match,
        "cause_status": cause_status,
        "cause_class": cause_class,
        "cause_actor": actor or None,
        "cause_reason": reason or None,
        "error_trace_present": bool(error_trace),
        "root_cause_fabricated": False,
        "final_root_cause_class": (
            cause_class if cause_status == "evidence_backed"
            else ("UNRESOLVED_CONTROL_PLANE" if event_class != "NONE" else "NONE")
        ),
        "recurrence_count": recurrence_count,
        "severity": severity,
        "priority": priority,
        "state_transition_fingerprint": state_transition_fingerprint,
        "schedule_start_disable_without_run": schedule_disable_without_run,
        "schedule_start_slot_kst": schedule_disable_slot_kst,
        "state_transition_is_root_cause": False,
        "missed_slots_kst": missed_slots,
        "missed_slot_count": len(missed_slots),
        "missed_slot_anchor": gap_anchor,
        "missed_slot_anchor_utc": gap_start.isoformat(),
        "schedule_run_early_grace_minutes": int(SCHEDULE_RUN_EARLY_GRACE.total_seconds() // 60),
        "missed_full_0630": missed_0630,
        "required_action": required_action,
        "new_automation_allowed": False,
        "duplicate_catchup_allowed": False,
        "automation_state_mutation_allowed_by_runtime_failure": False,
        "schedule_mutation_allowed_without_user_request": False,
        "runtime_failure_must_not_disable_automation": True,
        "catchup_policy": (
            "AT_MOST_ONCE_SAME_DAY_WITHOUT_BASELINE_CREATION"
            if pause_incident and missed_0630
            else "NONE"
        ),
    }


def self_test() -> None:
    disabled = {
        "id": CANONICAL_ID,
        "title": CANONICAL_TITLE,
        "is_enabled": False,
        "schedule": "RRULE:FREQ=HOURLY;BYMINUTE=30;BYSECOND=0",
        "timing_mode": "exact_schedule",
        "prompt": "stable",
        "updated_at": "2026-09-06T20:34:07.836996Z",
        "last_run_time": "2026-09-06T19:30:22.873339Z",
    }
    result = classify_pause(disabled, observed_at="2026-09-07T01:01:48.674172Z")
    assert result["pause_detected"] is True, result
    assert result["cause_class"] == "CONTROL_PLANE_ATTRIBUTION_UNAVAILABLE", result
    assert result["root_cause_fabricated"] is False, result
    assert result["required_action"] == "REACTIVATE_EXISTING_CANONICAL_AUTOMATION", result
    assert result["new_automation_allowed"] is False, result
    assert result["missed_full_0630"] is True, result

    repeated = classify_pause(
        disabled,
        observed_at="2026-09-07T01:01:48.674172Z",
        prior_pause_count=2,
    )
    assert repeated["recurrence_count"] == 3, repeated
    assert repeated["event_class"] == "PAUSE_RECURRENCE_CRITICAL", repeated
    assert repeated["severity"] == "PAUSE_RECURRENCE_CRITICAL", repeated
    assert repeated["priority"] == "CRITICAL", repeated

    boundary = classify_pause(
        dict(
            disabled,
            updated_at="2026-09-08T01:37:01.377102Z",
            last_run_time="2026-09-07T20:27:56.644698Z",
        ),
        observed_at="2026-09-08T05:44:00Z",
        prior_pause_count=2,
    )
    assert boundary["state_transition_fingerprint"] == "SCHEDULE_START_DISABLE_WITHOUT_RUN", boundary
    assert boundary["state_transition_is_root_cause"] is False, boundary
    assert boundary["cause_class"] == "CONTROL_PLANE_ATTRIBUTION_UNAVAILABLE", boundary
    assert "2026-09-08T10:30+09:00" in boundary["missed_slots_kst"], boundary

    # Regression: enabled tasks can still miss scheduled slots.
    enabled_gap = classify_pause(
        dict(
            disabled,
            is_enabled=True,
            updated_at="2026-09-09T01:41:51.738851Z",
            last_run_time="2026-09-08T23:31:43.768364Z",
        ),
        observed_at="2026-09-09T02:45:00Z",
    )
    assert enabled_gap["pause_detected"] is False, enabled_gap
    assert enabled_gap["schedule_gap_active"] is True, enabled_gap
    assert enabled_gap["event_class"] == "SCHEDULE_GAP_ACTIVE", enabled_gap
    assert enabled_gap["missed_slot_count"] >= 1, enabled_gap
    assert enabled_gap["required_action"] == "MONITOR_NEXT_SLOT_NO_DUPLICATE_CATCHUP", enabled_gap

    previous = snapshot_state(disabled, observed_at="2026-09-09T01:35:52.289137Z")
    enabled_state = dict(disabled, is_enabled=True, updated_at="2026-09-09T01:41:51.738851Z")
    changed = classify_pause(
        enabled_state,
        observed_at="2026-09-09T01:42:00Z",
        previous_snapshot=previous,
    )
    assert changed["changed_fields"] == ["is_enabled"], changed
    assert changed["baseline_match"] is False, changed

    policy = runtime_failure_policy(
        stage="revision_preflight",
        error_code="REVISION_BASELINE_MISSING",
        retryable=False,
    )
    assert policy["run_status"] == "PRECHECK_NOT_READY", policy
    assert policy["automation_state_mutation_allowed"] is False, policy
    assert policy["scheduler_terminal"] is False, policy

    bad = dict(disabled, updated_at="2026-09-06T20:34:07")
    try:
        classify_pause(bad, observed_at="2026-09-07T01:01:48.674172Z")
    except AutomationStateGuardError:
        pass
    else:
        raise AssertionError("naive timestamps must fail closed")

    print("Instagram automation state guard: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state")
    parser.add_argument("--observed-at")
    parser.add_argument("--cause-evidence")
    parser.add_argument("--previous-snapshot")
    parser.add_argument("--post-recovery-snapshot")
    parser.add_argument("--prior-pause-count", type=int, default=0)
    parser.add_argument("--output")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0
    if not args.state or not args.observed_at:
        raise SystemExit("--state and --observed-at are required")

    state = json.loads(Path(args.state).read_text(encoding="utf-8"))
    evidence = json.loads(Path(args.cause_evidence).read_text(encoding="utf-8")) if args.cause_evidence else None
    previous = json.loads(Path(args.previous_snapshot).read_text(encoding="utf-8")) if args.previous_snapshot else None
    post_recovery = (
        json.loads(Path(args.post_recovery_snapshot).read_text(encoding="utf-8"))
        if args.post_recovery_snapshot
        else None
    )
    result = classify_pause(
        state,
        observed_at=args.observed_at,
        cause_evidence=evidence,
        prior_pause_count=args.prior_pause_count,
        previous_snapshot=previous,
        post_recovery_snapshot=post_recovery,
    )
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
