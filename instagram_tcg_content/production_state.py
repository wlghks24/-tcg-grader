#!/usr/bin/env python3
"""Deterministic production state + single-run lock for Instagram TCG content.

This module does not render or post content. It enforces the state contract that
must be satisfied before/after a production run so duplicate runs, false
baselines, and false finalized records fail closed.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
SCHEDULED_BASELINE_RUN_KIND = "scheduled_10_30"
EXPECTED_ARTIFACT_COUNT = 6
EXPECTED_DIMENSIONS = [1080, 1350]

REQUIRED_PRODUCTION_FIELDS = {
    "production_date_kst",
    "scheduled_slot_kst",
    "actual_started_at_kst",
    "router_branch",
    "run_kind",
    "snapshot_id",
    "schema_version",
    "payload_hashes",
    "artifact_hashes",
    "dimensions",
    "caption_hash",
    "hashtag_hash",
    "x10_status",
    "delivery_reference_status",
    "finalized_at",
}


def empty_state() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "run_locks": {},
        "production_records": {},
        "catchup_attempts": {},
    }


def load_state(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, UnicodeError):
        return empty_state()
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        return empty_state()
    value.setdefault("run_locks", {})
    value.setdefault("production_records", {})
    value.setdefault("catchup_attempts", {})
    return value


def write_state_atomic(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            tmp = Path(handle.name)
        tmp.replace(path)
    finally:
        if tmp is not None and tmp.exists():
            tmp.unlink(missing_ok=True)


def make_lock_key(
    production_date_kst: str,
    scheduled_slot_kst: str,
    router_branch: str,
) -> str:
    return "|".join((production_date_kst, scheduled_slot_kst, router_branch))


def acquire_run_lock(
    state: dict[str, Any],
    *,
    production_date_kst: str,
    scheduled_slot_kst: str,
    router_branch: str,
    run_id: str,
) -> tuple[bool, str]:
    key = make_lock_key(production_date_kst, scheduled_slot_kst, router_branch)
    locks = state.setdefault("run_locks", {})
    prior = locks.get(key)
    if isinstance(prior, dict) and prior.get("status") == "running":
        return False, "DUPLICATE_RUN_SUPPRESSED"
    locks[key] = {"run_id": run_id, "status": "running"}
    return True, key


def release_run_lock(
    state: dict[str, Any],
    lock_key: str,
    *,
    status: str,
) -> None:
    if status not in {"completed", "failed"}:
        raise ValueError("lock release status must be completed or failed")
    row = state.setdefault("run_locks", {}).get(lock_key)
    if not isinstance(row, dict):
        raise KeyError(lock_key)
    row["status"] = status


def validate_production_record(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED_PRODUCTION_FIELDS - set(record))
    if missing:
        errors.append("missing production fields: " + ",".join(missing))
        return errors

    run_kind = record.get("run_kind")
    baseline_id = record.get("baseline_id")
    if run_kind == SCHEDULED_BASELINE_RUN_KIND and not baseline_id:
        errors.append("10:30 scheduled run requires baseline_id")
    if run_kind != SCHEDULED_BASELINE_RUN_KIND and baseline_id:
        errors.append("non-10:30 run cannot create baseline_id")

    payload_hashes = record.get("payload_hashes")
    artifact_hashes = record.get("artifact_hashes")
    dimensions = record.get("dimensions")

    if (
        not isinstance(payload_hashes, list)
        or len(payload_hashes) != EXPECTED_ARTIFACT_COUNT
        or not all(isinstance(item, str) and item for item in payload_hashes)
    ):
        errors.append("payload_hashes must contain exactly 6 non-empty string values")
    if (
        not isinstance(artifact_hashes, list)
        or len(artifact_hashes) != EXPECTED_ARTIFACT_COUNT
        or not all(isinstance(item, str) and item for item in artifact_hashes)
    ):
        errors.append("artifact_hashes must contain exactly 6 non-empty string values")
    elif len(set(artifact_hashes)) != EXPECTED_ARTIFACT_COUNT:
        errors.append("artifact_hashes must be unique")
    if not isinstance(dimensions, list) or len(dimensions) != EXPECTED_ARTIFACT_COUNT:
        errors.append("dimensions must contain exactly 6 values")
    elif any(
        not isinstance(item, (list, tuple)) or list(item) != EXPECTED_DIMENSIONS
        for item in dimensions
    ):
        errors.append("all artifacts must be 1080x1350")

    if not record.get("delivery_reference_status"):
        errors.append("delivery_reference_status missing")
    if not record.get("finalized_at"):
        errors.append("finalized_at missing")
    return errors


def finalized_record_for_date(
    state: dict[str, Any],
    production_date_kst: str,
) -> dict[str, Any] | None:
    row = state.setdefault("production_records", {}).get(production_date_kst)
    if isinstance(row, dict) and row.get("finalized") is True:
        return row
    return None


def can_start_catchup(
    state: dict[str, Any],
    production_date_kst: str,
) -> tuple[bool, str]:
    if finalized_record_for_date(state, production_date_kst):
        return False, "FINALIZED_PRODUCTION_ALREADY_EXISTS"
    count = int(state.setdefault("catchup_attempts", {}).get(production_date_kst, 0) or 0)
    if count >= 1:
        return False, "CATCHUP_BUDGET_EXHAUSTED"
    return True, "CATCHUP_ALLOWED"


def record_catchup_attempt(state: dict[str, Any], production_date_kst: str) -> int:
    attempts = state.setdefault("catchup_attempts", {})
    count = int(attempts.get(production_date_kst, 0) or 0) + 1
    attempts[production_date_kst] = count
    return count


def finalize_production(
    state: dict[str, Any],
    record: dict[str, Any],
) -> None:
    errors = validate_production_record(record)
    if errors:
        raise ValueError("; ".join(errors))
    production_date = str(record["production_date_kst"])
    state.setdefault("production_records", {})[production_date] = {
        "finalized": True,
        **record,
    }


def baseline_id_for_date(
    state: dict[str, Any],
    production_date_kst: str,
) -> str | None:
    row = finalized_record_for_date(state, production_date_kst)
    if not row or row.get("run_kind") != SCHEDULED_BASELINE_RUN_KIND:
        return None
    value = row.get("baseline_id")
    return str(value) if value else None
