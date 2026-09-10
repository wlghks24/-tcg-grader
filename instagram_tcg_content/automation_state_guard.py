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

CANONICAL_ID = "6aa2af4de8c88191aad2a1da62439e10"
CANONICAL_TITLE = "인스타 카드정보"
AI_RELIABILITY_PROJECT = "instagram_card"
AI_RELIABILITY_TASK_ID = CANONICAL_ID
SCHEDULE_MODE = "hourly_on_the_hour_single_router"
WEEKLY_PRODUCTION_WEEKDAY = 0
WEEKLY_PRODUCTION_HOUR = 19

NON_FATAL_PRECHECK_CODES = {"BASELINE_MISSING", "REVISION_BASELINE_MISSING", "SNAPSHOT_BUILDING", "NO_VERIFIED_FACTS", "INSUFFICIENT_VERIFIED_FACTS", "INSUFFICIENT_COMPLETED_SALES", "NO_COMPARABLE_DATA", "PRECHECK_DATA_NOT_READY"}
PRECHECK_STAGES = {"preflight", "production_preflight", "revision_preflight"}
FINGERPRINT_FIELDS = ("title", "schedule", "timing_mode", "prompt")

class AutomationStateGuardError(ValueError):
    pass

def build_ai_reliability_bridge(state_root: str | Path):
    from ai_reliability_v8 import ReliabilityBridge
    return ReliabilityBridge(Path(state_root), project=AI_RELIABILITY_PROJECT, task_id=AI_RELIABILITY_TASK_ID)

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
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()

def router_branch_for_slot(value: str | dt.datetime) -> str:
    parsed = _aware(value, "scheduled_slot_kst") if isinstance(value, str) else value
    if parsed is None:
        raise AutomationStateGuardError("scheduled_slot_kst required")
    if parsed.tzinfo is None:
        raise AutomationStateGuardError("scheduled_slot_kst must be timezone-aware")
    kst = parsed.astimezone(KST)
    if kst.weekday() == WEEKLY_PRODUCTION_WEEKDAY and kst.hour == WEEKLY_PRODUCTION_HOUR and kst.minute == 0:
        return "WEEKLY_PRODUCTION"
    return "COLLECTION_VERIFY_REFINE_ONLY"

def snapshot_state(state: dict[str, Any], *, observed_at: str) -> dict[str, Any]:
    if state.get("id") != CANONICAL_ID:
        raise AutomationStateGuardError("unexpected automation id")
    title = state.get("title")
    if not isinstance(title, str) or not title.strip():
        raise AutomationStateGuardError("title must be a non-empty string")
    observed = _aware(observed_at, "observed_at")
    updated = _aware(state.get("updated_at"), "updated_at")
    last_run = _aware(state.get("last_run_time"), "last_run_time")
    enabled = state.get("is_enabled")
    if not isinstance(enabled, bool):
        raise AutomationStateGuardError("is_enabled must be boolean")
    return {"task_id": CANONICAL_ID, "title": title, "expected_title": CANONICAL_TITLE, "title_matches_canonical": title == CANONICAL_TITLE, "is_enabled": enabled, "schedule": state.get("schedule"), "timing_mode": state.get("timing_mode"), "prompt": state.get("prompt"), "updated_at": updated.isoformat() if updated else None, "last_run_time": last_run.isoformat() if last_run else None, "snapshot_observed_at": observed.isoformat(), "schedule_mode": SCHEDULE_MODE, "fingerprints": {f: _stable_fingerprint(state.get(f)) for f in FINGERPRINT_FIELDS}}

def compare_snapshots(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    if not previous:
        return {"changed_fields": [], "change_window_start": None, "change_window_end": current["snapshot_observed_at"], "baseline_match": None}
    tracked = ("is_enabled", "title", "schedule", "timing_mode", "prompt")
    changed = [f for f in tracked if previous.get(f) != current.get(f)]
    return {"changed_fields": changed, "change_window_start": previous.get("snapshot_observed_at"), "change_window_end": current.get("updated_at") or current.get("snapshot_observed_at"), "baseline_match": not bool(changed)}

def _missed_slot_gap_start(*, last_run: dt.datetime | None, updated: dt.datetime | None, observed: dt.datetime) -> tuple[dt.datetime, str]:
    if last_run is not None:
        return last_run + SCHEDULE_RUN_EARLY_GRACE, "last_run_plus_early_grace"
    if updated is not None:
        return updated, "state_updated_at"
    return observed, "observed_at"

def _hourly_on_the_hour_slots(start: dt.datetime, end: dt.datetime) -> list[str]:
    if end <= start:
        return []
    start_kst, end_kst = start.astimezone(KST), end.astimezone(KST)
    cursor = start_kst.replace(minute=0, second=0, microsecond=0)
    if cursor <= start_kst:
        cursor += dt.timedelta(hours=1)
    out: list[str] = []
    while cursor < end_kst:
        out.append(cursor.isoformat(timespec="minutes"))
        cursor += dt.timedelta(hours=1)
    return out

def _hourly_half_past_slots(start: dt.datetime, end: dt.datetime) -> list[str]:
    return _hourly_on_the_hour_slots(start, end)

def _schedule_start_disable_without_run(updated: dt.datetime | None, last_run: dt.datetime | None) -> tuple[bool, str | None]:
    if updated is None:
        return False, None
    updated_kst = updated.astimezone(KST)
    slot_kst = updated_kst.replace(minute=0, second=0, microsecond=0)
    delta = updated_kst - slot_kst
    if delta < dt.timedelta(0) or delta > POST_RUN_DISABLE_WINDOW:
        return False, None
    slot_utc = slot_kst.astimezone(dt.timezone.utc)
    if last_run is not None and last_run >= slot_utc:
        return False, None
    return True, slot_kst.isoformat(timespec="minutes")

def _disable_event_class(*, updated: dt.datetime | None, last_run: dt.datetime | None, recurrence_count: int) -> str:
    if recurrence_count >= 3:
        return "PAUSE_RECURRENCE_CRITICAL"
    if updated is not None and last_run is not None and dt.timedelta(0) <= updated - last_run <= POST_RUN_DISABLE_WINDOW:
        return "POST_RUN_DISABLE"
    return "DISABLE_BETWEEN_RUNS"

def runtime_failure_policy(*, stage: str, error_code: str, retryable: bool) -> dict[str, Any]:
    stage = str(stage or "UNKNOWN").strip() or "UNKNOWN"
    error_code = str(error_code or "UNKNOWN_ERROR").strip() or "UNKNOWN_ERROR"
    precheck = stage.lower() in PRECHECK_STAGES or error_code.upper() in NON_FATAL_PRECHECK_CODES
    return {"stage": stage, "error_code": error_code, "run_status": "PRECHECK_NOT_READY" if precheck else ("DEGRADED" if retryable else "BLOCKED"), "automation_state_mutation_allowed": False, "self_disable_allowed": False, "self_pause_allowed": False, "self_reschedule_allowed": False, "preserve_enabled_state": True, "preserve_title": True, "preserve_schedule": True, "scheduler_terminal": False, "automation_continues": True, "next_action": "COMPLETE_RUN_AND_KEEP_NEXT_SLOT" if precheck else ("BOUNDED_RETRY" if retryable else "RECORD_AND_CONTINUE_NEXT_SLOT")}

def classify_pause(state: dict[str, Any], *, observed_at: str, cause_evidence: dict[str, Any] | None = None, prior_pause_count: int = 0, previous_snapshot: dict[str, Any] | None = None, post_recovery_snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    if isinstance(prior_pause_count, bool) or not isinstance(prior_pause_count, int) or prior_pause_count < 0:
        raise AutomationStateGuardError("prior_pause_count must be a non-negative integer")
    snapshot = snapshot_state(state, observed_at=observed_at)
    observed = _aware(snapshot["snapshot_observed_at"], "snapshot_observed_at")
    updated = _aware(snapshot["updated_at"], "updated_at")
    last_run = _aware(snapshot["last_run_time"], "last_run_time")
    assert observed is not None
    enabled = bool(snapshot["is_enabled"])
    pause_incident = not enabled
    gap_start, gap_anchor = _missed_slot_gap_start(last_run=last_run, updated=updated, observed=observed)
    missed_slots = _hourly_on_the_hour_slots(gap_start, observed)
    schedule_gap = bool(missed_slots)
    schedule_gap_active = enabled and schedule_gap
    production_missed = any(router_branch_for_slot(slot) == "WEEKLY_PRODUCTION" for slot in missed_slots)
    recurrence_count = prior_pause_count + (1 if pause_incident else 0)
    boundary, boundary_slot = (False, None)
    if pause_incident:
        boundary, boundary_slot = _schedule_start_disable_without_run(updated, last_run)
    comparison = compare_snapshots(previous_snapshot, snapshot)
    drift = [f for f in comparison["changed_fields"] if f in {"title", "schedule", "timing_mode", "prompt"}]
    actor = str((cause_evidence or {}).get("actor") or "").strip()
    reason = str((cause_evidence or {}).get("reason") or "").strip()
    error_trace = str((cause_evidence or {}).get("error_trace") or "").strip()
    has_attr = bool(actor and reason)
    if pause_incident or schedule_gap or drift:
        cause_status = "evidence_backed" if has_attr else "unresolved"
        cause_class = str((cause_evidence or {}).get("cause_class") or "EXPLICIT_STATE_CHANGE") if has_attr else "CONTROL_PLANE_ATTRIBUTION_UNAVAILABLE"
    else:
        cause_status, cause_class = "not_applicable", "NONE"
    if pause_incident:
        event_class = _disable_event_class(updated=updated, last_run=last_run, recurrence_count=recurrence_count)
    elif schedule_gap_active:
        event_class = "SCHEDULE_GAP_ACTIVE"
    elif schedule_gap:
        event_class = "SCHEDULE_GAP"
    elif drift:
        event_class = "CONTROL_PLANE_DRIFT"
    else:
        event_class = "NONE"
    post_match = None
    if post_recovery_snapshot:
        post_match = compare_snapshots(post_recovery_snapshot, snapshot)["baseline_match"]
        if post_recovery_snapshot.get("is_enabled") is True and snapshot["is_enabled"] is False:
            event_class = "PAUSE_RECURRENCE_CRITICAL" if recurrence_count >= 3 else "RECOVERY_REGRESSION"
    severity = "PAUSE_RECURRENCE_CRITICAL" if pause_incident and recurrence_count >= 2 else ("INCIDENT" if event_class != "NONE" else "NONE")
    priority = "CRITICAL" if recurrence_count >= 3 else ("HIGH" if event_class != "NONE" else "NORMAL")
    required = "REACTIVATE_EXISTING_CANONICAL_AUTOMATION" if pause_incident else ("MONITOR_NEXT_SLOT_NO_DUPLICATE_CATCHUP" if schedule_gap_active else ("REVIEW_VERIFIED_CONTROL_PLANE_DRIFT" if drift else "NONE"))
    return {"schema_version": "1.3-single-router", "automation_id": CANONICAL_ID, "title": snapshot["title"], "expected_title": CANONICAL_TITLE, "title_matches_canonical": snapshot["title_matches_canonical"], "pause_detected": pause_incident, "schedule_gap_detected": schedule_gap, "schedule_gap_active": schedule_gap_active, "event_class": event_class, "enabled_observed": enabled, "desired_enabled_state": True, "observed_at": snapshot["snapshot_observed_at"], "state_updated_at": snapshot["updated_at"], "last_run_time": snapshot["last_run_time"], "snapshot": snapshot, "changed_fields": comparison["changed_fields"], "control_plane_drift_fields": drift, "change_window_start": comparison["change_window_start"], "change_window_end": comparison["change_window_end"], "baseline_match": comparison["baseline_match"], "post_recovery_match": post_match, "cause_status": cause_status, "cause_class": cause_class, "cause_actor": actor or None, "cause_reason": reason or None, "error_trace_present": bool(error_trace), "root_cause_fabricated": False, "final_root_cause_class": cause_class if cause_status == "evidence_backed" else ("UNRESOLVED_CONTROL_PLANE" if event_class != "NONE" else "NONE"), "recurrence_count": recurrence_count, "severity": severity, "priority": priority, "state_transition_fingerprint": "SCHEDULE_START_DISABLE_WITHOUT_RUN" if boundary else None, "schedule_start_disable_without_run": boundary, "schedule_start_slot_kst": boundary_slot, "state_transition_is_root_cause": False, "missed_slots_kst": missed_slots, "missed_slot_count": len(missed_slots), "missed_slot_anchor": gap_anchor, "missed_slot_anchor_utc": gap_start.isoformat(), "schedule_run_early_grace_minutes": int(SCHEDULE_RUN_EARLY_GRACE.total_seconds() // 60), "missed_weekly_production": production_missed, "missed_full_0630": False, "missed_slot_branches": {slot: router_branch_for_slot(slot) for slot in missed_slots}, "required_action": required, "new_automation_allowed": False, "duplicate_catchup_allowed": False, "automation_state_mutation_allowed_by_runtime_failure": False, "schedule_mutation_allowed_without_user_request": False, "runtime_failure_must_not_disable_automation": True, "catchup_policy": "USER_REQUESTED_RECOVERY_ONLY" if pause_incident and production_missed else "NONE"}

def self_test() -> None:
    base = {"id": CANONICAL_ID, "title": CANONICAL_TITLE, "is_enabled": True, "schedule": "RRULE:FREQ=HOURLY;BYMINUTE=0;BYSECOND=0", "timing_mode": "exact_schedule", "prompt": "stable", "updated_at": "2026-09-10T14:40:00Z", "last_run_time": "2026-09-10T14:00:10Z"}
    ok = classify_pause(base, observed_at="2026-09-10T14:05:00Z")
    assert not ok["pause_detected"] and not ok["schedule_gap_detected"], ok
    gap = classify_pause(dict(base, last_run_time="2026-09-10T12:00:10Z"), observed_at="2026-09-10T14:05:00Z")
    assert "2026-09-10T22:00+09:00" in gap["missed_slots_kst"], gap
    assert router_branch_for_slot("2026-09-14T19:00:00+09:00") == "WEEKLY_PRODUCTION"
    assert router_branch_for_slot("2026-09-14T18:00:00+09:00") == "COLLECTION_VERIFY_REFINE_ONLY"
    print("Instagram automation state guard single-router: PASS")

def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument("--state"); p.add_argument("--observed-at"); p.add_argument("--cause-evidence"); p.add_argument("--previous-snapshot"); p.add_argument("--post-recovery-snapshot"); p.add_argument("--prior-pause-count", type=int, default=0); p.add_argument("--output"); p.add_argument("--self-test", action="store_true")
    a = p.parse_args()
    if a.self_test:
        self_test(); return 0
    if not a.state or not a.observed_at:
        raise SystemExit("--state and --observed-at are required")
    state = json.loads(Path(a.state).read_text(encoding="utf-8"))
    load = lambda x: json.loads(Path(x).read_text(encoding="utf-8")) if x else None
    result = classify_pause(state, observed_at=a.observed_at, cause_evidence=load(a.cause_evidence), prior_pause_count=a.prior_pause_count, previous_snapshot=load(a.previous_snapshot), post_recovery_snapshot=load(a.post_recovery_snapshot))
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if a.output:
        Path(a.output).write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
