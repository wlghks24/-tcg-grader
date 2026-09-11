#!/usr/bin/env python3
"""Two-phase receipt lifecycle for the canonical Instagram card-info pause monitor.

This module is additive: producer exchange semantics stay in pause_monitor_exchange.py.
The monitor writes a non-incident START receipt before doing work, then a FINAL receipt
through the existing final writer. This distinguishes "scheduler never invoked" from
"monitor invoked but did not reach final persistence" without backfilling history.
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from instagram_tcg_content.pause_monitor_exchange import (
    MONITOR_STATUS_PATH,
    MONITOR_TASK_ID,
    PROJECT,
    SCHEMA_VERSION,
    TASK_ID,
    _atomic_write,
    _parse_aware,
    _read_json,
    write_monitor_status,
)

MONITOR_STARTED = "MONITOR_STARTED"
MONITOR_FINAL = "MONITOR_FINAL"
DEFAULT_STALE_AFTER = timedelta(minutes=20)


def new_monitor_run_id(*, scheduled_slot_kst: str) -> str:
    """Return a unique run id anchored to a timezone-aware scheduled slot."""
    slot = _parse_aware(scheduled_slot_kst)
    if slot is None:
        raise ValueError("MONITOR_SLOT_TIME_INVALID")
    return f"monitor:{slot.isoformat()}:{uuid4().hex}"


def build_monitor_started(
    *,
    monitor_run_id: str,
    scheduled_slot_kst: str,
    observed_at: str,
    seq: int,
) -> dict[str, Any]:
    """Build the non-terminal receipt that must be persisted before monitor work."""
    if not isinstance(monitor_run_id, str) or not monitor_run_id:
        raise ValueError("MONITOR_RUN_ID_REQUIRED")
    if _parse_aware(scheduled_slot_kst) is None or _parse_aware(observed_at) is None:
        raise ValueError("MONITOR_TIME_INVALID")
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 1:
        raise ValueError("MONITOR_SEQ_INVALID")
    return {
        "schema_version": SCHEMA_VERSION,
        "project": PROJECT,
        "task_id": TASK_ID,
        "monitor_task_id": MONITOR_TASK_ID,
        "monitor_run_id": monitor_run_id,
        "receipt_phase": MONITOR_STARTED,
        "scheduled_slot_kst": scheduled_slot_kst,
        "observed_at": observed_at,
        "seq": seq,
        "terminal": False,
        "classification": None,
        "failed_stage": None,
        "root_cause": None,
        "incident_created": False,
        "historical_backfill": False,
    }


def write_monitor_started(
    started: dict[str, Any],
    *,
    path: Path = MONITOR_STATUS_PATH,
) -> dict[str, Any]:
    """Persist START directly with atomic write/readback and never create an incident."""
    if started.get("project") != PROJECT or started.get("task_id") != TASK_ID:
        raise ValueError("MONITOR_SCOPE_MISMATCH")
    if started.get("monitor_task_id") != MONITOR_TASK_ID:
        raise ValueError("MONITOR_SCOPE_MISMATCH")
    if started.get("receipt_phase") != MONITOR_STARTED or started.get("terminal") is not False:
        raise ValueError("MONITOR_STARTED_RECEIPT_INVALID")
    if started.get("classification") is not None or started.get("incident_created") is not False:
        raise ValueError("MONITOR_STARTED_MUST_NOT_CLASSIFY_OR_INCIDENT")
    seq = started.get("seq")
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 1:
        raise ValueError("MONITOR_SEQ_INVALID")

    prior = _read_json(path)
    if prior is not None and int(prior.get("seq") or 0) >= seq:
        raise ValueError("MONITOR_SEQ_NOT_ADVANCING")

    _atomic_write(path, started)
    reread = _read_json(path)
    if reread != started:
        raise RuntimeError("MONITOR_STARTED_READBACK_MISMATCH")
    return reread


def write_monitor_final(
    status: dict[str, Any],
    *,
    monitor_run_id: str,
    seq: int,
    path: Path = MONITOR_STATUS_PATH,
) -> dict[str, Any]:
    """Persist FINAL using the existing writer, preserving the START run id."""
    if not isinstance(monitor_run_id, str) or not monitor_run_id:
        raise ValueError("MONITOR_RUN_ID_REQUIRED")
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 2:
        raise ValueError("MONITOR_FINAL_SEQ_INVALID")

    prior = _read_json(path)
    if prior is None:
        raise ValueError("MONITOR_FINAL_REQUIRES_STARTED_RECEIPT")
    if prior.get("receipt_phase") != MONITOR_STARTED:
        raise ValueError("MONITOR_FINAL_REQUIRES_STARTED_RECEIPT")
    if prior.get("monitor_run_id") != monitor_run_id:
        raise ValueError("MONITOR_RUN_ID_MISMATCH")
    if int(prior.get("seq") or 0) >= seq:
        raise ValueError("MONITOR_SEQ_NOT_ADVANCING")

    payload = {
        **status,
        "monitor_run_id": monitor_run_id,
        "receipt_phase": MONITOR_FINAL,
        "terminal": True,
        "historical_backfill": False,
        "incident_created": status.get("classification") not in {"HEALTHY", None},
    }
    return write_monitor_status(payload, seq=seq, path=path)


def assess_monitor_receipt_completion(
    *,
    observed_at: str,
    monitor_status: dict[str, Any] | None,
    stale_after: timedelta = DEFAULT_STALE_AFTER,
) -> dict[str, Any]:
    """Classify only direct receipt evidence; never infer or backfill a missing run."""
    now = _parse_aware(observed_at)
    if now is None or stale_after.total_seconds() <= 0:
        raise ValueError("MONITOR_RECEIPT_WINDOW_INVALID")

    if not isinstance(monitor_status, dict):
        return {
            "classification": "MONITOR_RECEIPT_ABSENT",
            "monitor_run_id": None,
            "receipt_phase": None,
            "age_seconds": None,
            "root_cause": None,
            "historical_backfill_allowed": False,
        }

    phase = monitor_status.get("receipt_phase")
    run_id = monitor_status.get("monitor_run_id")
    receipt_time = _parse_aware(monitor_status.get("observed_at"))
    age = max(0.0, (now - receipt_time).total_seconds()) if receipt_time else None

    if phase == MONITOR_FINAL:
        classification = "MONITOR_RUN_COMPLETE"
        root_cause = None
    elif phase == MONITOR_STARTED:
        if age is not None and age >= stale_after.total_seconds():
            classification = "MONITOR_RUN_INCOMPLETE"
            root_cause = "ROOT_CAUSE_UNRESOLVED"
        else:
            classification = "MONITOR_RUN_IN_PROGRESS"
            root_cause = None
    else:
        classification = "MONITOR_RECEIPT_LEGACY_OR_UNKNOWN"
        root_cause = None

    return {
        "classification": classification,
        "monitor_run_id": run_id,
        "receipt_phase": phase,
        "age_seconds": age,
        "root_cause": root_cause,
        "historical_backfill_allowed": False,
    }
