#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

KST = dt.timezone(dt.timedelta(hours=9))
CANONICAL_ID = "6a9b8a22e72c8191849c273e1240378e"
CANONICAL_TITLE = "인스타 카드정보"
AI_RELIABILITY_PROJECT = "instagram_card"
AI_RELIABILITY_TASK_ID = CANONICAL_ID


def build_ai_reliability_bridge(state_root: str | Path):
    """Build the additive v8 bridge for this canonical task only.

    Import is deliberately deferred so existing pause classification remains
    import-safe and the reliability package performs no scheduler mutation.
    """
    from ai_reliability_v8 import ReliabilityBridge

    return ReliabilityBridge(
        Path(state_root),
        project=AI_RELIABILITY_PROJECT,
        task_id=AI_RELIABILITY_TASK_ID,
    )


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

PRECHECK_STAGES = {
    "preflight",
    "production_preflight",
    "revision_preflight",
}


class AutomationStateGuardError(ValueError):
    pass


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


def _schedule_start_disable_without_run(
    updated: dt.datetime | None,
    last_run: dt.datetime | None,
) -> tuple[bool, str | None]:
    """Detect an observable disable transition near a :30 slot without a run.

    This is a state-transition fingerprint, not a root-cause attribution.
    """
    if updated is None:
        return False, None
    updated_kst = updated.astimezone(KST)
    slot_kst = updated_kst.replace(minute=30, second=0, microsecond=0)
    if updated_kst.minute < 30:
        slot_kst -= dt.timedelta(hours=1)
    delta = updated_kst - slot_kst
    if delta < dt.timedelta(0) or delta > dt.timedelta(minutes=15):
        return False, None
    slot_utc = slot_kst.astimezone(dt.timezone.utc)
    if last_run is not None and last_run >= slot_utc:
        return False, None
    return True, slot_kst.isoformat(timespec="minutes")


def _hourly_half_past_slots(start: dt.datetime, end: dt.datetime) -> list[str]:
    if end <= start:
        return []
    cursor = start.astimezone(KST).replace(second=0, microsecond=0)
    cursor = cursor.replace(minute=30)
    if cursor <= start.astimezone(KST):
        cursor += dt.timedelta(hours=1)
    out: list[str] = []
    while cursor < end.astimezone(KST):
        out.append(cursor.isoformat(timespec="minutes"))
        cursor += dt.timedelta(hours=1)
    return out


def runtime_failure_policy(
    *,
    stage: str,
    error_code: str,
    retryable: bool,
) -> dict[str, Any]:
    """Return the scheduler-safe policy for a failed content run.

    Runtime/content/source/render/delivery failures are run-level failures only.
    They must never be translated into automation disable/pause/reschedule writes.
    """
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
) -> dict[str, Any]:
    if state.get("id") != CANONICAL_ID:
        raise AutomationStateGuardError("unexpected automation id")
    if state.get("title") != CANONICAL_TITLE:
        raise AutomationStateGuardError("unexpected automation title")
    if isinstance(prior_pause_count, bool) or not isinstance(prior_pause_count, int) or prior_pause_count < 0:
        raise AutomationStateGuardError("prior_pause_count must be a non-negative integer")

    observed = _aware(observed_at, "observed_at")
    updated = _aware(state.get("updated_at"), "updated_at")
    last_run = _aware(state.get("last_run_time"), "last_run_time")

    enabled = state.get("is_enabled")
    if not isinstance(enabled, bool):
        raise AutomationStateGuardError("is_enabled must be boolean")

    incident = not enabled
    actor = ""
    reason = ""
    cause_status = "not_applicable"
    cause_class = "NONE"
    if incident:
        actor = str((cause_evidence or {}).get("actor") or "").strip()
        reason = str((cause_evidence or {}).get("reason") or "").strip()
        if actor and reason:
            cause_status = "evidence_backed"
            cause_class = str((cause_evidence or {}).get("cause_class") or "EXPLICIT_STATE_CHANGE")
        else:
            cause_status = "unresolved"
            cause_class = "CONTROL_PLANE_ATTRIBUTION_UNAVAILABLE"

    gap_start = updated or last_run or observed
    missed_slots = _hourly_half_past_slots(gap_start, observed) if incident else []
    missed_0630 = any(x[11:16] == "06:30" for x in missed_slots)
    recurrence_count = prior_pause_count + (1 if incident else 0)

    schedule_disable_without_run = False
    schedule_disable_slot_kst = None
    state_transition_fingerprint = None
    if incident:
        schedule_disable_without_run, schedule_disable_slot_kst = _schedule_start_disable_without_run(
            updated,
            last_run,
        )
        if schedule_disable_without_run:
            state_transition_fingerprint = "SCHEDULE_START_DISABLE_WITHOUT_RUN"

    severity = "NONE"
    if incident:
        severity = "PAUSE_RECURRENCE_CRITICAL" if recurrence_count >= 2 else "PAUSE_INCIDENT"

    return {
        "schema_version": "1.1",
        "automation_id": CANONICAL_ID,
        "title": CANONICAL_TITLE,
        "pause_detected": incident,
        "enabled_observed": enabled,
        "desired_enabled_state": True,
        "observed_at": observed.isoformat(),
        "state_updated_at": updated.isoformat() if updated else None,
        "last_run_time": last_run.isoformat() if last_run else None,
        "cause_status": cause_status,
        "cause_class": cause_class,
        "cause_actor": actor or None,
        "cause_reason": reason or None,
        "root_cause_fabricated": False,
        "recurrence_count": recurrence_count,
        "severity": severity,
        "state_transition_fingerprint": state_transition_fingerprint,
        "schedule_start_disable_without_run": schedule_disable_without_run,
        "schedule_start_slot_kst": schedule_disable_slot_kst,
        "state_transition_is_root_cause": False,
        "missed_slots_kst": missed_slots,
        "missed_full_0630": missed_0630,
        "required_action": (
            "REACTIVATE_EXISTING_CANONICAL_AUTOMATION"
            if incident else "NONE"
        ),
        "new_automation_allowed": False,
        "automation_state_mutation_allowed_by_runtime_failure": False,
        "schedule_mutation_allowed_without_user_request": False,
        "runtime_failure_must_not_disable_automation": True,
        "catchup_policy": (
            "AT_MOST_ONCE_SAME_DAY_WITHOUT_BASELINE_CREATION"
            if incident and missed_0630 else "NONE"
        ),
    }


def self_test() -> None:
    disabled = {
        "id": CANONICAL_ID,
        "title": CANONICAL_TITLE,
        "is_enabled": False,
        "updated_at": "2026-09-06T20:34:07.836996Z",
        "last_run_time": "2026-09-06T19:30:22.873339Z",
    }
    result = classify_pause(disabled, observed_at="2026-09-07T01:01:48.674172Z")
    assert result["pause_detected"] is True, result
    assert result["cause_status"] == "unresolved", result
    assert result["cause_class"] == "CONTROL_PLANE_ATTRIBUTION_UNAVAILABLE", result
    assert result["root_cause_fabricated"] is False, result
    assert result["required_action"] == "REACTIVATE_EXISTING_CANONICAL_AUTOMATION", result
    assert result["new_automation_allowed"] is False, result
    assert result["missed_full_0630"] is True, result
    assert result["runtime_failure_must_not_disable_automation"] is True, result

    repeated = classify_pause(
        disabled,
        observed_at="2026-09-07T01:01:48.674172Z",
        prior_pause_count=1,
    )
    assert repeated["recurrence_count"] == 2, repeated
    assert repeated["severity"] == "PAUSE_RECURRENCE_CRITICAL", repeated

    boundary_disabled = dict(
        disabled,
        updated_at="2026-09-08T01:37:01.377102Z",
        last_run_time="2026-09-07T20:27:56.644698Z",
    )
    boundary = classify_pause(
        boundary_disabled,
        observed_at="2026-09-08T05:44:00Z",
        prior_pause_count=2,
    )
    assert boundary["state_transition_fingerprint"] == "SCHEDULE_START_DISABLE_WITHOUT_RUN", boundary
    assert boundary["schedule_start_slot_kst"] == "2026-09-08T10:30+09:00", boundary
    assert boundary["state_transition_is_root_cause"] is False, boundary
    assert boundary["cause_class"] == "CONTROL_PLANE_ATTRIBUTION_UNAVAILABLE", boundary
    assert boundary["recurrence_count"] == 3, boundary

    backed = classify_pause(
        disabled,
        observed_at="2026-09-07T01:01:48.674172Z",
        cause_evidence={
            "actor": "user",
            "reason": "manual pause",
            "cause_class": "EXPLICIT_USER_PAUSE",
        },
    )
    assert backed["cause_status"] == "evidence_backed", backed
    assert backed["cause_class"] == "EXPLICIT_USER_PAUSE", backed

    enabled = dict(disabled, is_enabled=True)
    normal = classify_pause(enabled, observed_at="2026-09-07T01:01:48.674172Z")
    assert normal["pause_detected"] is False, normal
    assert normal["required_action"] == "NONE", normal

    policy = runtime_failure_policy(
        stage="render",
        error_code="ARTIFACT_GENERATION_FAILED",
        retryable=False,
    )
    assert policy["run_status"] == "BLOCKED", policy
    assert policy["self_disable_allowed"] is False, policy
    assert policy["preserve_enabled_state"] is True, policy
    assert policy["automation_continues"] is True, policy

    precheck = runtime_failure_policy(
        stage="revision_preflight",
        error_code="REVISION_BASELINE_MISSING",
        retryable=False,
    )
    assert precheck["run_status"] == "PRECHECK_NOT_READY", precheck
    assert precheck["next_action"] == "COMPLETE_RUN_AND_KEEP_NEXT_SLOT", precheck
    assert precheck["automation_state_mutation_allowed"] is False, precheck
    assert precheck["scheduler_terminal"] is False, precheck
    assert precheck["automation_continues"] is True, precheck

    bad = dict(disabled, updated_at="2026-09-06T20:34:07")
    try:
        classify_pause(bad, observed_at="2026-09-07T01:01:48.674172Z")
    except AutomationStateGuardError:
        pass
    else:
        raise AssertionError("naive timestamps must fail closed")

    print("Instagram automation pause guard: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state")
    parser.add_argument("--observed-at")
    parser.add_argument("--cause-evidence")
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
    evidence = (
        json.loads(Path(args.cause_evidence).read_text(encoding="utf-8"))
        if args.cause_evidence else None
    )
    result = classify_pause(
        state,
        observed_at=args.observed_at,
        cause_evidence=evidence,
        prior_pause_count=args.prior_pause_count,
    )
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
