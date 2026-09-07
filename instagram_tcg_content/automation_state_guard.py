#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

KST = dt.timezone(dt.timedelta(hours=9))
CANONICAL_ID = "6a9b8a22e72c8191849c273e1240378e"
CANONICAL_TITLE = "인스타 카드정보"


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


def classify_pause(
    state: dict[str, Any],
    *,
    observed_at: str,
    cause_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
    return {
        "schema_version": "1.0",
        "automation_id": CANONICAL_ID,
        "title": CANONICAL_TITLE,
        "pause_detected": incident,
        "enabled_observed": enabled,
        "observed_at": observed.isoformat(),
        "state_updated_at": updated.isoformat() if updated else None,
        "last_run_time": last_run.isoformat() if last_run else None,
        "cause_status": cause_status,
        "cause_class": cause_class,
        "cause_actor": actor or None,
        "cause_reason": reason or None,
        "root_cause_fabricated": False,
        "missed_slots_kst": missed_slots,
        "missed_full_0630": missed_0630,
        "required_action": (
            "REACTIVATE_EXISTING_CANONICAL_AUTOMATION"
            if incident else "NONE"
        ),
        "new_automation_allowed": False,
        "schedule_mutation_allowed_without_user_request": False,
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
    result = classify_pause(state, observed_at=args.observed_at, cause_evidence=evidence)
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
