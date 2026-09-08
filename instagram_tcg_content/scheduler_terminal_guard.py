#!/usr/bin/env python3
from __future__ import annotations

from typing import Any

CANONICAL_ID = "6a9b8a22e72c8191849c273e1240378e"
CANONICAL_TITLE = "인스타 카드정보"

RUN_LEVEL_STATUSES = {
    "PASS",
    "PRECHECK_NOT_READY",
    "DEGRADED",
    "BLOCKED",
    "FAILED",
    "SOURCE_DEFERRED",
    "RUN_BUDGET_EXHAUSTED",
    "MISSING_ARTIFACT",
}


def scheduler_safe_terminal_record(
    *,
    run_status: str,
    stage: str,
    error_code: str | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    """Normalize any content/runtime result into a non-terminal scheduler record.

    A scheduled content run may fail, block, or be not-ready. None of those
    states may be interpreted as an instruction to pause/disable/reschedule the
    canonical ChatGPT automation. This function deliberately contains no
    scheduler mutation capability.
    """
    status = str(run_status or "FAILED").strip().upper() or "FAILED"
    if status not in RUN_LEVEL_STATUSES:
        status = "FAILED"

    return {
        "automation_id": CANONICAL_ID,
        "automation_title": CANONICAL_TITLE,
        "run_status": status,
        "stage": str(stage or "UNKNOWN").strip() or "UNKNOWN",
        "error_code": str(error_code).strip() if error_code else None,
        "detail": str(detail).strip() if detail else None,
        "scope": "RUN_ONLY",
        "scheduler_terminal": False,
        "automation_continues": True,
        "preserve_enabled_state": True,
        "preserve_title": True,
        "preserve_schedule": True,
        "preserve_timing_mode": True,
        "automation_state_mutation_allowed": False,
        "self_disable": False,
        "self_pause": False,
        "self_reschedule": False,
        "self_rename": False,
        "self_delete": False,
        "create_recovery_automation": False,
        "next_action": "RETURN_NORMALLY_AND_KEEP_NEXT_SLOT",
    }


def assert_scheduler_safe(record: dict[str, Any]) -> None:
    if record.get("automation_id") != CANONICAL_ID:
        raise AssertionError("unexpected automation id")
    if record.get("scheduler_terminal") is not False:
        raise AssertionError("scheduler_terminal must be false")
    if record.get("automation_continues") is not True:
        raise AssertionError("automation must continue")
    if record.get("preserve_enabled_state") is not True:
        raise AssertionError("enabled state must be preserved")
    if record.get("automation_state_mutation_allowed") is not False:
        raise AssertionError("automation state mutation must be forbidden")
    for key in (
        "self_disable",
        "self_pause",
        "self_reschedule",
        "self_rename",
        "self_delete",
        "create_recovery_automation",
    ):
        if record.get(key) is not False:
            raise AssertionError(f"{key} must be false")


def self_test() -> None:
    for status in sorted(RUN_LEVEL_STATUSES):
        record = scheduler_safe_terminal_record(
            run_status=status,
            stage="self_test",
            error_code="TEST",
        )
        assert record["run_status"] == status, record
        assert_scheduler_safe(record)

    unknown = scheduler_safe_terminal_record(
        run_status="PAUSED",
        stage="self_test",
        error_code="UNKNOWN_TOP_LEVEL_STATUS",
    )
    assert unknown["run_status"] == "FAILED", unknown
    assert unknown["scope"] == "RUN_ONLY", unknown
    assert_scheduler_safe(unknown)
    print("Instagram scheduler terminal guard: PASS")


if __name__ == "__main__":
    self_test()
