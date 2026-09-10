#!/usr/bin/env python3
"""Weekly-production compatibility layer over the legacy production-state store."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from instagram_tcg_content import production_state as legacy
from instagram_tcg_content.single_task_router import (
    KST,
    WEEKLY_PRODUCTION,
    is_weekly_production_slot,
)

SCHEDULED_WEEKLY_RUN_KIND = "scheduled_monday_19"
USER_REQUESTED_RECOVERY_RUN_KIND = legacy.USER_REQUESTED_RECOVERY_RUN_KIND


def validate_weekly_production_record(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    try:
        slot = datetime.fromisoformat(str(record.get("scheduled_slot_kst") or "").replace("Z", "+00:00"))
    except ValueError:
        slot = None
    if slot is None or slot.tzinfo is None:
        errors.append("scheduled_slot_kst must be timezone-aware ISO-8601")
    elif not is_weekly_production_slot(slot.astimezone(KST)):
        errors.append("scheduled production must be Monday 19:00 KST")

    run_kind = record.get("run_kind")
    if run_kind == SCHEDULED_WEEKLY_RUN_KIND:
        if record.get("router_branch") != WEEKLY_PRODUCTION:
            errors.append("scheduled weekly run requires WEEKLY_PRODUCTION router branch")
        if record.get("baseline_id"):
            errors.append("legacy baseline_id is forbidden for weekly production")
    elif run_kind != USER_REQUESTED_RECOVERY_RUN_KIND:
        errors.append("unsupported production run_kind")

    shadow = dict(record)
    if run_kind == SCHEDULED_WEEKLY_RUN_KIND:
        shadow.pop("baseline_id", None)
    errors.extend(legacy.validate_production_record(shadow))
    return list(dict.fromkeys(errors))


def finalize_weekly_production(state: dict[str, Any], record: dict[str, Any]) -> None:
    errors = validate_weekly_production_record(record)
    if errors:
        raise ValueError("; ".join(errors))
    production_date = str(record["production_date_kst"])
    records = state.setdefault("production_records", {})
    prior = records.get(production_date)
    if isinstance(prior, dict) and prior.get("finalized") is True:
        raise RuntimeError("FINALIZED_PRODUCTION_ALREADY_EXISTS")
    records[production_date] = {"finalized": True, **record}
