#!/usr/bin/env python3
"""Recovery policy for missing Instagram card-info production output.

The policy separates two problems:
1) collection readiness recovery before render;
2) visible status reporting when production cannot proceed.

It never fabricates facts, never weakens collection gates, and never authorizes
scheduler/control-plane mutations.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PROJECT = "instagram_card"
TASK_ID = "6a9b8a22e72c8191849c273e1240378e"

RECOVERABLE_COLLECTION_REASONS = {
    "COMPLETED_SALE_COVERAGE_INSUFFICIENT",
    "NO_VERIFIED_FACTS",
    "SNAPSHOT_NOT_FINALIZED",
    "SNAPSHOT_WRITE_READBACK_UNVERIFIED",
}
RECOVERY_MODE = "PREPRODUCTION_RECOVERY_COLLECTION"
BLOCKED_MODE = "PRODUCTION_BLOCKED_COLLECTION_NOT_READY"


@dataclass(frozen=True)
class RecoveryDecision:
    action: str
    reason: str
    run_bounded_collection: bool
    render_allowed: bool
    must_emit_visible_report: bool
    recovery_attempt_limit: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "run_bounded_collection": self.run_bounded_collection,
            "render_allowed": self.render_allowed,
            "must_emit_visible_report": self.must_emit_visible_report,
            "recovery_attempt_limit": self.recovery_attempt_limit,
        }


def _has_stale_reason(reasons: list[str]) -> bool:
    return any(str(reason).startswith("SNAPSHOT_STALE:") for reason in reasons)


def decide_preproduction_recovery(
    collection_report: dict[str, Any],
    *,
    is_production_slot: bool,
    recovery_collection_attempts: int,
) -> RecoveryDecision:
    """Decide whether to run one bounded recovery collection before production."""
    production_ready = collection_report.get("production_ready") is True
    reasons = [str(x) for x in (collection_report.get("reasons") or [])]

    if production_ready:
        return RecoveryDecision(
            action="PROCEED_TO_PRODUCTION_PREFLIGHT",
            reason="COLLECTION_HEALTH_READY",
            run_bounded_collection=False,
            render_allowed=True,
            must_emit_visible_report=True,
            recovery_attempt_limit=1,
        )

    recoverable = _has_stale_reason(reasons) or any(
        reason in RECOVERABLE_COLLECTION_REASONS for reason in reasons
    )
    if is_production_slot and recoverable and recovery_collection_attempts < 1:
        return RecoveryDecision(
            action=RECOVERY_MODE,
            reason="COLLECTION_NOT_READY_TRY_ONE_BOUNDED_REFRESH",
            run_bounded_collection=True,
            render_allowed=False,
            must_emit_visible_report=True,
            recovery_attempt_limit=1,
        )

    return RecoveryDecision(
        action=BLOCKED_MODE,
        reason="COLLECTION_NOT_READY_AFTER_RECOVERY_OR_NOT_RECOVERABLE",
        run_bounded_collection=False,
        render_allowed=False,
        must_emit_visible_report=True,
        recovery_attempt_limit=1,
    )


def build_visible_failure_report(
    *,
    scheduled_slot_kst: str,
    collection_report: dict[str, Any],
    producer_phase: str | None,
    exchange_status: str,
    recovery_collection_attempted: bool,
    artifact_count: int,
) -> dict[str, Any]:
    """Build the minimum report that must survive even when render cannot start."""
    return {
        "OUTPUT_STATUS": "MISSING",
        "SCHEDULED_SLOT_KST": scheduled_slot_kst,
        "FAILED_STAGE": "COLLECTION_HEALTH",
        "ERROR_CODE": "COLLECTION_HEALTH_NOT_READY",
        "ROOT_CAUSE": "VERIFIED_DATA_REQUIREMENTS_NOT_MET",
        "PRODUCER_PHASE": producer_phase or "UNKNOWN",
        "EXCHANGE_STATUS": exchange_status,
        "COLLECTION_HEALTH": collection_report.get("status", "NOT_READY"),
        "VERIFIED_FACT_COUNT": int(collection_report.get("unique_fact_count") or 0),
        "OUTPUT_MATRIX_COVERAGE": collection_report.get("matrix_counts") or {},
        "COMPLETED_SALE_COVERAGE": collection_report.get("completed_sale_counts") or {},
        "RECOVERY_COLLECTION_ATTEMPTED": recovery_collection_attempted,
        "RENDER_ATTEMPTED": False,
        "ARTIFACT_COUNT": int(artifact_count),
        "NEXT_ACTION": collection_report.get("next_action")
        or "RUN_BOUNDED_FULL_COLLECTION_AND_PERSIST_VERIFIED_IG_FACTS",
        "automation_continues": True,
        "must_emit_visible_report": True,
    }


def self_test() -> None:
    stale = {
        "production_ready": False,
        "status": "NOT_READY",
        "reasons": [
            "SNAPSHOT_STALE:90.0h>36h",
            "COMPLETED_SALE_COVERAGE_INSUFFICIENT",
        ],
    }
    first = decide_preproduction_recovery(
        stale,
        is_production_slot=True,
        recovery_collection_attempts=0,
    )
    assert first.action == RECOVERY_MODE, first
    assert first.run_bounded_collection is True
    assert first.must_emit_visible_report is True

    second = decide_preproduction_recovery(
        stale,
        is_production_slot=True,
        recovery_collection_attempts=1,
    )
    assert second.action == BLOCKED_MODE, second
    assert second.render_allowed is False
    assert second.must_emit_visible_report is True

    ready = decide_preproduction_recovery(
        {"production_ready": True, "reasons": []},
        is_production_slot=True,
        recovery_collection_attempts=0,
    )
    assert ready.render_allowed is True

    report = build_visible_failure_report(
        scheduled_slot_kst="2026-09-10T10:30:00+09:00",
        collection_report={
            "status": "NOT_READY",
            "unique_fact_count": 1,
            "matrix_counts": {},
            "completed_sale_counts": {},
            "next_action": "RUN_BOUNDED_FULL_COLLECTION_AND_PERSIST_VERIFIED_IG_FACTS",
        },
        producer_phase="COLLECTION_HEALTH",
        exchange_status="RUN_INVOKED_NO_PRODUCER_RECEIPT",
        recovery_collection_attempted=True,
        artifact_count=0,
    )
    assert report["OUTPUT_STATUS"] == "MISSING"
    assert report["ARTIFACT_COUNT"] == 0
    assert report["must_emit_visible_report"] is True
    print("Instagram card production recovery policy: PASS")


if __name__ == "__main__":
    self_test()
