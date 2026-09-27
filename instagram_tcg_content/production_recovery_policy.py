#!/usr/bin/env python3
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from instagram_tcg_content.automation_state_guard import CANONICAL_ID

PROJECT = "instagram_card"
TASK_ID = CANONICAL_ID
KST = timezone(timedelta(hours=9))
# Only data-state failures that a fresh IG-local capture can actually repair are
# retryable. Route/configuration failures stay fail-closed so a collection retry
# cannot hide a broken source contract.
RECOVERABLE_COLLECTION_REASONS = {
    "COMPLETED_SALE_COVERAGE_INSUFFICIENT",
    "NO_VERIFIED_FACTS",
    "SNAPSHOT_NAMESPACE_INVALID",
    "SNAPSHOT_NOT_FINALIZED",
    "SNAPSHOT_WRITE_READBACK_UNVERIFIED",
    "SNAPSHOT_BUILT_AT_INVALID",
    "SNAPSHOT_FACTS_INVALID",
}
RECOVERABLE_COLLECTION_PREFIXES = (
    "SNAPSHOT_STALE:",
    "LATEST_COLLECTION_ATTEMPT_NOT_READY:",
    "MALFORMED_VERIFIED_FACTS:",
    "DUPLICATE_FACT_LINEAGE:",
    "OUTPUT_MATRIX_COVERAGE_MISSING:",
)
NONRECOVERABLE_ROUTE_PREFIXES = (
    "PROVIDER_GROUP_MISSING:",
    "OFFICIAL_ROUTE_SHORTAGE:",
    "COMPLETED_SALE_ROUTE_SHORTAGE:",
    "MARKET_ROUTE_SHORTAGE:",
)
RECOVERY_MODE = "PREPRODUCTION_RECOVERY_COLLECTION"
BLOCKED_MODE = "PRODUCTION_BLOCKED_COLLECTION_NOT_READY"
GENERAL_MODE = "PROCEED_GENERAL_CARDINFO_WITHOUT_UNVERIFIED_MARKET_SECTIONS"
COLLECTION_ONLY_MODE = "COLLECTION_VERIFY_REFINE_ONLY"


@dataclass(frozen=True)
class RecoveryDecision:
    action: str
    reason: str
    run_bounded_collection: bool
    render_allowed: bool
    market_sections_allowed: bool
    must_emit_visible_report: bool
    recovery_attempt_limit: int

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _parse(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("scheduled_slot_kst must be timezone-aware")
    return dt.astimezone(KST)


def is_weekly_production_slot(scheduled_slot_kst: str) -> bool:
    dt = _parse(scheduled_slot_kst)
    return dt.weekday() == 0 and dt.hour == 19 and dt.minute == 0 and dt.second == 0


def _is_recoverable_collection_reason(reason: str) -> bool:
    value = str(reason or "")
    if value in RECOVERABLE_COLLECTION_REASONS:
        return True
    return any(value.startswith(prefix) for prefix in RECOVERABLE_COLLECTION_PREFIXES)


def _has_nonrecoverable_route_problem(reasons: list[str]) -> bool:
    return any(
        any(str(reason).startswith(prefix) for prefix in NONRECOVERABLE_ROUTE_PREFIXES)
        for reason in reasons
    ) or "PROVIDER_GROUPS_MISSING" in reasons


def decide_preproduction_recovery(
    collection_report: dict[str, Any], *, is_production_slot: bool, recovery_collection_attempts: int
) -> RecoveryDecision:
    if isinstance(recovery_collection_attempts, bool) or not isinstance(recovery_collection_attempts, int) or recovery_collection_attempts < 0:
        raise ValueError("recovery_collection_attempts must be a non-negative integer")
    general_ready = collection_report.get("general_cardinfo_ready") is True
    market_ready = collection_report.get("market_price_ready") is True
    reasons = [str(x) for x in (collection_report.get("reasons") or [])]
    if not is_production_slot:
        return RecoveryDecision(COLLECTION_ONLY_MODE, "NON_PRODUCTION_SLOT", True, False, False, False, 1)
    if general_ready:
        if market_ready:
            return RecoveryDecision("PROCEED_TO_PRODUCTION_PREFLIGHT", "GENERAL_AND_MARKET_READY", False, True, True, True, 1)
        return RecoveryDecision(GENERAL_MODE, "GENERAL_READY_MARKET_NOT_READY", False, True, False, True, 1)

    recoverable = any(_is_recoverable_collection_reason(reason) for reason in reasons)
    route_problem = _has_nonrecoverable_route_problem(reasons)
    if recoverable and not route_problem and recovery_collection_attempts < 1:
        return RecoveryDecision(RECOVERY_MODE, "GENERAL_CARDINFO_NOT_READY_TRY_ONE_BOUNDED_REFRESH", True, False, False, True, 1)

    blocked_reason = (
        "SOURCE_ROUTE_CONFIGURATION_NOT_RECOVERABLE_BY_COLLECTION"
        if route_problem
        else "GENERAL_CARDINFO_NOT_READY_AFTER_RECOVERY_OR_NOT_RECOVERABLE"
    )
    return RecoveryDecision(BLOCKED_MODE, blocked_reason, False, False, False, True, 1)


def decide_for_slot(
    collection_report: dict[str, Any], *, scheduled_slot_kst: str, recovery_collection_attempts: int
) -> RecoveryDecision:
    return decide_preproduction_recovery(
        collection_report,
        is_production_slot=is_weekly_production_slot(scheduled_slot_kst),
        recovery_collection_attempts=recovery_collection_attempts,
    )


def _failure_root_cause(collection_report: dict[str, Any], direct_root_cause: str | None) -> str:
    """Return the most specific root cause supported by verified readiness fields.

    Do not label a known readiness failure as unresolved. A caller-supplied direct
    cause remains authoritative, but otherwise a false general-card-info readiness
    flag is already sufficient evidence that verified general requirements were not
    met. This keeps the visible report useful without inventing a lower-level
    network/source cause that the collection report did not prove.
    """
    if direct_root_cause is not None:
        direct = str(direct_root_cause).strip()
        if direct:
            return direct
    if collection_report.get("general_cardinfo_ready") is not True:
        return "VERIFIED_GENERAL_CARDINFO_REQUIREMENTS_NOT_MET"
    return "ROOT_CAUSE_UNRESOLVED"


def build_visible_failure_report(
    *, scheduled_slot_kst: str, collection_report: dict[str, Any], producer_phase: str | None,
    exchange_status: str, recovery_collection_attempted: bool, artifact_count: int,
    direct_root_cause: str | None = None,
) -> dict[str, Any]:
    if not is_weekly_production_slot(scheduled_slot_kst):
        raise ValueError("VISIBLE_PRODUCTION_FAILURE_REPORT_ONLY_ALLOWED_FOR_MONDAY_1900")
    reasons = [str(x) for x in (collection_report.get("reasons") or [])]
    root = _failure_root_cause(collection_report, direct_root_cause)
    return {
        "OUTPUT_STATUS": "MISSING",
        "SCHEDULED_SLOT_KST": scheduled_slot_kst,
        "FAILED_STAGE": "COLLECTION_HEALTH",
        "ERROR_CODE": "GENERAL_CARDINFO_NOT_READY",
        "ROOT_CAUSE": root,
        "READINESS_REASONS": reasons,
        "PRODUCER_PHASE": producer_phase or "UNKNOWN",
        "EXCHANGE_STATUS": exchange_status,
        "COLLECTION_HEALTH": collection_report.get("status", "NOT_READY"),
        "GENERAL_CARDINFO_READY": collection_report.get("general_cardinfo_ready") is True,
        "MARKET_PRICE_READY": collection_report.get("market_price_ready") is True,
        "VERIFIED_FACT_COUNT": int(collection_report.get("unique_fact_count") or 0),
        "OUTPUT_MATRIX_COVERAGE": collection_report.get("matrix_counts") or {},
        "COMPLETED_SALE_COVERAGE": collection_report.get("completed_sale_counts") or {},
        "RECOVERY_COLLECTION_ATTEMPTED": recovery_collection_attempted,
        "RENDER_ATTEMPTED": False,
        "ARTIFACT_COUNT": int(artifact_count),
        "NEXT_ACTION": collection_report.get("next_action") or "RUN_BOUNDED_FULL_COLLECTION_AND_PERSIST_VERIFIED_IG_FACTS",
        "automation_continues": True,
        "must_emit_visible_report": True,
    }


def self_test() -> None:
    stale = {"general_cardinfo_ready": False, "market_price_ready": False, "reasons": ["SNAPSHOT_STALE:90.0h>36h"]}
    assert decide_for_slot(stale, scheduled_slot_kst="2026-09-14T19:00:00+09:00", recovery_collection_attempts=0).action == RECOVERY_MODE
    matrix_gap = {"general_cardinfo_ready": False, "market_price_ready": False, "reasons": ["OUTPUT_MATRIX_COVERAGE_MISSING:pokemon:KR"]}
    assert decide_preproduction_recovery(matrix_gap, is_production_slot=True, recovery_collection_attempts=0).action == RECOVERY_MODE
    route_gap = {"general_cardinfo_ready": False, "market_price_ready": False, "reasons": ["OFFICIAL_ROUTE_SHORTAGE:pokemon:0/1"]}
    route_decision = decide_preproduction_recovery(route_gap, is_production_slot=True, recovery_collection_attempts=0)
    assert route_decision.action == BLOCKED_MODE and not route_decision.run_bounded_collection
    assert route_decision.reason == "SOURCE_ROUTE_CONFIGURATION_NOT_RECOVERABLE_BY_COLLECTION"
    c = decide_for_slot(stale, scheduled_slot_kst="2026-09-14T18:00:00+09:00", recovery_collection_attempts=0)
    assert c.action == COLLECTION_ONLY_MODE and not c.render_allowed and not c.must_emit_visible_report
    report = build_visible_failure_report(
        scheduled_slot_kst="2026-09-14T19:00:00+09:00",
        collection_report=stale,
        producer_phase="COLLECTION_HEALTH",
        exchange_status="HEALTHY",
        recovery_collection_attempted=True,
        artifact_count=0,
    )
    assert report["ROOT_CAUSE"] == "VERIFIED_GENERAL_CARDINFO_REQUIREMENTS_NOT_MET"
    assert report["READINESS_REASONS"] == stale["reasons"]
    print("Instagram card production recovery single-router: PASS")


if __name__ == "__main__":
    self_test()
