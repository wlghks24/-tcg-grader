#!/usr/bin/env python3
"""Weekly-slot guard around the existing collection recovery policy."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from instagram_tcg_content.production_recovery_policy import (
    BLOCKED_MODE,
    RecoveryDecision,
    decide_preproduction_recovery,
)
from instagram_tcg_content.single_task_router import is_weekly_production_slot


def decide_for_slot(
    collection_report: dict[str, Any],
    *,
    scheduled_slot_kst: str,
    recovery_collection_attempts: int,
) -> RecoveryDecision:
    try:
        slot = datetime.fromisoformat(scheduled_slot_kst.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError("scheduled_slot_kst must be timezone-aware ISO-8601") from exc
    if slot.tzinfo is None:
        raise ValueError("scheduled_slot_kst must be timezone-aware ISO-8601")
    production_slot = is_weekly_production_slot(slot)
    decision = decide_preproduction_recovery(
        collection_report,
        is_production_slot=production_slot,
        recovery_collection_attempts=recovery_collection_attempts,
    )
    if not production_slot and decision.render_allowed:
        return RecoveryDecision(
            action=BLOCKED_MODE,
            reason="FINAL_RENDER_OUTSIDE_MONDAY_19_KST",
            run_bounded_collection=False,
            render_allowed=False,
            market_sections_allowed=False,
            must_emit_visible_report=False,
            recovery_attempt_limit=1,
        )
    return decision
