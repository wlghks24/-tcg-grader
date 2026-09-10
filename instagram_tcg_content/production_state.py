#!/usr/bin/env python3
"""Deterministic production state + single-run lock for Instagram TCG content.

This module does not render or post content. It enforces the state contract that
must be satisfied before/after a production run so duplicate runs, false
baselines, and false finalized records fail closed.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from instagram_tcg_content.source_verification_engine import (
    VERIFICATION_MODE,
    validate_production_verification_receipt,
)

SCHEMA_VERSION = 1
SCHEDULED_BASELINE_RUN_KIND = "scheduled_10_30"
USER_REQUESTED_RECOVERY_RUN_KIND = "user_requested_recovery"
RECOVERABLE_BLOCK_REASONS = {
    "INSUFFICIENT_VERIFIED_FACTS",
    "INSUFFICIENT_VERIFIED_FACTS_OBSERVED_POST_SLOT",
    "ARTIFACT_GENERATION_FAILED",
    "ARTIFACT_VALIDATION_FAILED",
    "DELIVERY_REFERENCE_MISSING",
}


class StateIntegrityError(RuntimeError):
    """Raised when an existing production-state file cannot be trusted."""

EXPECTED_ARTIFACT_COUNT = 6
EXPECTED_DIMENSIONS = [1080, 1350]

REQUIRED_PRODUCTION_FIELDS = {
    "production_date_kst",
    "scheduled_slot_kst",
    "actual_started_at_kst",
    "router_branch",
    "run_kind",
    "snapshot_id",
    "snapshot_hash",
    "schema_version",
    "payload_hashes",
    "artifact_hashes",
    "dimensions",
    "caption_hash",
    "hashtag_hash",
    "x10_status",
    "verification_receipt",
    "delivery_reference_status",
    "finalized_at",
}


def empty_state() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "run_locks": {},
        "production_records": {},
        "blocked_attempts": {},
        "catchup_attempts": {},
    }


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_state()
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise StateIntegrityError("STATE_READ_FAILED") from exc
    try:
        value = json.loads(raw)
    except (ValueError, TypeError, UnicodeError) as exc:
        raise StateIntegrityError("STATE_CORRUPT_JSON") from exc
    if not isinstance(value, dict):
        raise StateIntegrityError("STATE_ROOT_NOT_OBJECT")
    if value.get("schema_version") != SCHEMA_VERSION:
        raise StateIntegrityError("STATE_SCHEMA_MISMATCH")
    for key in ("run_locks", "production_records", "blocked_attempts", "catchup_attempts"):
        if key not in value:
            value[key] = {}
        elif not isinstance(value[key], dict):
            raise StateIntegrityError(f"STATE_FIELD_INVALID:{key}")

    for lock_key, row in value["run_locks"].items():
        if (
            not isinstance(lock_key, str)
            or not isinstance(row, dict)
            or not isinstance(row.get("run_id"), str)
            or not row.get("run_id")
            or row.get("status") not in {"running", "completed", "failed"}
        ):
            raise StateIntegrityError("STATE_RUN_LOCK_INVALID")

    for production_date, row in value["production_records"].items():
        if (
            not isinstance(production_date, str)
            or not isinstance(row, dict)
            or row.get("finalized") is not True
        ):
            raise StateIntegrityError("STATE_PRODUCTION_RECORD_INVALID")
        record_errors = validate_production_record(row)
        if record_errors:
            raise StateIntegrityError(
                "STATE_PRODUCTION_RECORD_INVALID:" + "; ".join(record_errors)
            )
        if str(row.get("production_date_kst")) != production_date:
            raise StateIntegrityError("STATE_PRODUCTION_DATE_KEY_MISMATCH")

    for production_date, row in value["blocked_attempts"].items():
        if (
            not isinstance(production_date, str)
            or not isinstance(row, dict)
            or str(row.get("production_date_kst") or "") != production_date
            or str(row.get("reason_code") or "") not in RECOVERABLE_BLOCK_REASONS
            or _parse_aware_iso(row.get("scheduled_slot_kst")) is None
            or _parse_aware_iso(row.get("recorded_at_kst")) is None
            or isinstance(row.get("verified_fact_count"), bool)
            or not isinstance(row.get("verified_fact_count"), int)
            or row.get("verified_fact_count") < 0
        ):
            raise StateIntegrityError("STATE_BLOCKED_ATTEMPT_INVALID")

    for production_date, count in value["catchup_attempts"].items():
        if (
            not isinstance(production_date, str)
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
        ):
            raise StateIntegrityError("STATE_CATCHUP_BUDGET_INVALID")
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
            handle.flush()
            os.fsync(handle.fileno())
            tmp = Path(handle.name)
        tmp.replace(path)
        try:
            dir_fd = os.open(path.parent, os.O_RDONLY)
        except OSError:
            dir_fd = None
        if dir_fd is not None:
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
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
    if prior is not None:
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


def _parse_aware_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else None


def validate_production_record(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED_PRODUCTION_FIELDS - set(record))
    if missing:
        errors.append("missing production fields: " + ",".join(missing))
        return errors

    if record.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version mismatch")

    for field in ("scheduled_slot_kst", "actual_started_at_kst", "finalized_at"):
        if _parse_aware_iso(record.get(field)) is None:
            errors.append(f"{field} must be timezone-aware ISO-8601")

    run_kind = record.get("run_kind")
    baseline_id = record.get("baseline_id")
    if run_kind == SCHEDULED_BASELINE_RUN_KIND and not baseline_id:
        errors.append("10:30 scheduled run requires baseline_id")
    if run_kind != SCHEDULED_BASELINE_RUN_KIND and baseline_id:
        errors.append("non-10:30 run cannot create baseline_id")
    if run_kind == USER_REQUESTED_RECOVERY_RUN_KIND:
        if _parse_aware_iso(record.get("recovery_of_slot_kst")) is None:
            errors.append("user-requested recovery requires recovery_of_slot_kst")
        evidence = record.get("recovery_request_evidence")
        if not isinstance(evidence, str) or not evidence.strip():
            errors.append("user-requested recovery requires recovery_request_evidence")

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

    if record.get("x10_status") != "pass":
        errors.append("x10_status must be pass")

    snapshot_id = record.get("snapshot_id")
    snapshot_hash = record.get("snapshot_hash")
    if not isinstance(snapshot_id, str) or not snapshot_id.strip():
        errors.append("snapshot_id missing")
    if (
        not isinstance(snapshot_hash, str)
        or len(snapshot_hash) != 64
        or any(ch not in "0123456789abcdef" for ch in snapshot_hash)
    ):
        errors.append("snapshot_hash must be lowercase SHA-256")
    if isinstance(snapshot_id, str) and snapshot_id.strip() and isinstance(snapshot_hash, str):
        receipt_errors = validate_production_verification_receipt(
            record.get("verification_receipt"),
            expected_snapshot_id=snapshot_id,
            expected_snapshot_fingerprint=snapshot_hash,
        )
        errors.extend(receipt_errors)
        receipt = record.get("verification_receipt")
        if isinstance(receipt, dict) and receipt.get("verification_mode") != VERIFICATION_MODE:
            errors.append("verification receipt must use Instagram-local evidence mode")

    if record.get("delivery_reference_status") != "verified":
        errors.append("delivery_reference_status must be verified")
    if not isinstance(record.get("caption_hash"), str) or not record.get("caption_hash"):
        errors.append("caption_hash missing")
    if not isinstance(record.get("hashtag_hash"), str) or not record.get("hashtag_hash"):
        errors.append("hashtag_hash missing")
    return errors


def finalized_record_for_date(
    state: dict[str, Any],
    production_date_kst: str,
) -> dict[str, Any] | None:
    row = state.setdefault("production_records", {}).get(production_date_kst)
    if isinstance(row, dict) and row.get("finalized") is True:
        return row
    return None


def record_blocked_production_attempt(
    state: dict[str, Any],
    *,
    production_date_kst: str,
    scheduled_slot_kst: str,
    reason_code: str,
    verified_fact_count: int,
    recorded_at_kst: str,
    detail: str = "",
) -> dict[str, Any]:
    if reason_code not in RECOVERABLE_BLOCK_REASONS:
        raise ValueError("UNSUPPORTED_BLOCK_REASON")
    if _parse_aware_iso(scheduled_slot_kst) is None:
        raise ValueError("scheduled_slot_kst must be timezone-aware ISO-8601")
    if _parse_aware_iso(recorded_at_kst) is None:
        raise ValueError("recorded_at_kst must be timezone-aware ISO-8601")
    if isinstance(verified_fact_count, bool) or not isinstance(verified_fact_count, int) or verified_fact_count < 0:
        raise ValueError("verified_fact_count must be a non-negative integer")
    if finalized_record_for_date(state, production_date_kst):
        raise RuntimeError("FINALIZED_PRODUCTION_ALREADY_EXISTS")

    row = {
        "production_date_kst": production_date_kst,
        "scheduled_slot_kst": scheduled_slot_kst,
        "reason_code": reason_code,
        "verified_fact_count": verified_fact_count,
        "recorded_at_kst": recorded_at_kst,
        "detail": str(detail or ""),
    }
    state.setdefault("blocked_attempts", {})[production_date_kst] = row
    return row


def can_start_user_requested_recovery(
    state: dict[str, Any],
    production_date_kst: str,
    *,
    user_requested: bool,
    missed_scheduled_slot_evidence: bool = False,
) -> tuple[bool, str]:
    """Authorize one user-requested recovery without inventing a baseline receipt.

    Normal recovery still requires a producer-side blocked baseline. A silent
    scheduler/producer gap has no such receipt by definition, so an explicit,
    independently observed missed-slot signal may substitute for the missing
    blocked record. This does not create/backfill a blocked attempt and cannot
    bypass the finalized-record or once-per-day catch-up budget.
    """
    if finalized_record_for_date(state, production_date_kst):
        return False, "FINALIZED_PRODUCTION_ALREADY_EXISTS"

    blocked = state.setdefault("blocked_attempts", {}).get(production_date_kst)
    if not isinstance(blocked, dict):
        if missed_scheduled_slot_evidence is not True:
            return False, "NO_BLOCKED_BASELINE_EVIDENCE"
        if user_requested is not True:
            return False, "USER_REQUEST_REQUIRED"
        count = int(state.setdefault("catchup_attempts", {}).get(production_date_kst, 0) or 0)
        if count >= 1:
            return False, "CATCHUP_BUDGET_EXHAUSTED"
        return True, "USER_REQUESTED_RECOVERY_ALLOWED_WITH_MISSED_SLOT_EVIDENCE"

    if blocked.get("reason_code") not in RECOVERABLE_BLOCK_REASONS:
        return False, "BLOCK_REASON_NOT_RECOVERABLE"
    if user_requested is not True:
        return False, "USER_REQUEST_REQUIRED"
    count = int(state.setdefault("catchup_attempts", {}).get(production_date_kst, 0) or 0)
    if count >= 1:
        return False, "CATCHUP_BUDGET_EXHAUSTED"
    return True, "USER_REQUESTED_RECOVERY_ALLOWED"


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
    records = state.setdefault("production_records", {})
    prior = records.get(production_date)
    if isinstance(prior, dict) and prior.get("finalized") is True:
        raise RuntimeError("FINALIZED_PRODUCTION_ALREADY_EXISTS")
    records[production_date] = {
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
