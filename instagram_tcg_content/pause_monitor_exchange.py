#!/usr/bin/env python3
"""Producer↔pause-monitor exchange contract for Instagram card info.

This module creates evidence, not guesses. It is deliberately separate from
content generation and never mutates scheduler/control-plane state.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PROJECT = "instagram_card"
TASK_ID = "6a9b8a22e72c8191849c273e1240378e"
MONITOR_TASK_ID = "6aa02cd749c0819196a6b17db6378958"
SCHEMA_VERSION = "1.1-card-pause-exchange"
KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parents[1]
EXCHANGE_ROOT = ROOT / "TCG_CROSSCHECK" / "IG_CARDINFO" / "pause_monitor_exchange"
PRODUCER_STATUS_PATH = EXCHANGE_ROOT / "PRODUCER_STATUS.json"
PRODUCER_ACK_PATH = EXCHANGE_ROOT / "PRODUCER_ACK.json"
MONITOR_STATUS_PATH = EXCHANGE_ROOT / "MONITOR_STATUS.json"
INCIDENT_DIR = EXCHANGE_ROOT / "incidents"

PRODUCER_PHASES = (
    "STARTED",
    "PREFLIGHT",
    "COLLECT",
    "VERIFY",
    "COLLECTION_HEALTH",
    "AI_RELIABILITY",
    "QUALITY_PROFILE",
    "RENDER",
    "OUTPUT_VALIDATION",
    "QUALITY_REVIEW",
    "LEARN",
    "VERIFIED_DELIVERY",
    "VERIFIED_NO_OUTPUT",
    "FAILED",
    "BLOCKED",
    "DEGRADED",
)
TERMINAL_SUCCESS_PHASES = {"VERIFIED_DELIVERY", "VERIFIED_NO_OUTPUT"}
TERMINAL_PHASES = TERMINAL_SUCCESS_PHASES | {"FAILED", "BLOCKED", "DEGRADED"}
RUN_LEVEL_FAILURE_PHASES = {"FAILED", "BLOCKED", "DEGRADED"}
COMPLETION_CLAIMS = (
    " complete",
    "completed",
    "success",
    "succeeded",
    "done",
    "finished",
    "완료",
)


def _parse_aware(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else None


def _same_instant(left: object, right: object) -> bool:
    a = _parse_aware(left)
    b = _parse_aware(right)
    if a is None or b is None:
        return False
    return a.astimezone(timezone.utc) == b.astimezone(timezone.utc)


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            temp = Path(handle.name)
        temp.replace(path)
    finally:
        if temp is not None and temp.exists():
            temp.unlink(missing_ok=True)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"EXCHANGE_JSON_READ_FAILED:{path.name}:{type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"EXCHANGE_JSON_ROOT_NOT_OBJECT:{path.name}")
    return value


def _read_json_diagnostic(path: Path) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    info: dict[str, Any] = {
        "path": str(path),
        "exists": path.is_file(),
        "readable": False,
        "read_error": None,
        "sha256": None,
        "modified_at": None,
    }
    if not info["exists"]:
        return None, info
    try:
        raw = path.read_bytes()
        info["sha256"] = hashlib.sha256(raw).hexdigest()
        info["modified_at"] = datetime.fromtimestamp(
            path.stat().st_mtime, timezone.utc
        ).isoformat()
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("JSON_ROOT_NOT_OBJECT")
        info["readable"] = True
        return value, info
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        info["read_error"] = f"{type(exc).__name__}:{exc}"
        return None, info


def _completion_claimed(evidence: object) -> bool:
    if not isinstance(evidence, str) or not evidence.strip():
        return False
    text = f" {evidence.casefold()}"
    return any(token in text for token in COMPLETION_CLAIMS)


def build_producer_status(
    *,
    run_id: str,
    scheduled_slot_kst: str,
    phase: str,
    seq: int,
    observed_at: str,
    code_version: str,
    failed_stage: str | None = None,
    error_code: str | None = None,
    root_cause: str | None = None,
    evidence: str | None = None,
    delivery_reference: str | None = None,
    artifact_count: int = 0,
    monitor_seq_seen: int | None = None,
) -> dict[str, Any]:
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("RUN_ID_REQUIRED")
    if phase not in PRODUCER_PHASES:
        raise ValueError("PRODUCER_PHASE_INVALID")
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 1:
        raise ValueError("PRODUCER_SEQ_INVALID")
    if _parse_aware(scheduled_slot_kst) is None or _parse_aware(observed_at) is None:
        raise ValueError("TIMEZONE_AWARE_TIME_REQUIRED")
    if not isinstance(code_version, str) or not code_version:
        raise ValueError("CODE_VERSION_REQUIRED")
    if isinstance(artifact_count, bool) or not isinstance(artifact_count, int) or artifact_count < 0:
        raise ValueError("ARTIFACT_COUNT_INVALID")

    terminal = phase in TERMINAL_PHASES
    if phase in RUN_LEVEL_FAILURE_PHASES and not (failed_stage and error_code):
        raise ValueError("FAILED_PHASE_REQUIRES_STAGE_AND_ERROR")
    if phase == "VERIFIED_DELIVERY" and (artifact_count != 6 or not delivery_reference):
        raise ValueError("VERIFIED_DELIVERY_REQUIRES_6_ARTIFACTS_AND_REFERENCE")
    if phase == "VERIFIED_NO_OUTPUT":
        if artifact_count != 0:
            raise ValueError("VERIFIED_NO_OUTPUT_REQUIRES_ZERO_ARTIFACTS")
        if not isinstance(evidence, str) or not evidence.strip():
            raise ValueError("VERIFIED_NO_OUTPUT_REQUIRES_EVIDENCE")

    return {
        "schema_version": SCHEMA_VERSION,
        "project": PROJECT,
        "task_id": TASK_ID,
        "run_id": run_id,
        "scheduled_slot_kst": scheduled_slot_kst,
        "phase": phase,
        "terminal": terminal,
        "seq": seq,
        "observed_at": observed_at,
        "code_version": code_version,
        "failed_stage": failed_stage,
        "error_code": error_code,
        "root_cause": root_cause or (
            "ROOT_CAUSE_UNRESOLVED" if phase in RUN_LEVEL_FAILURE_PHASES else None
        ),
        "evidence": evidence,
        "delivery_reference": delivery_reference,
        "artifact_count": artifact_count,
        "monitor_seq_seen": monitor_seq_seen,
        "self_disable": False,
        "self_pause": False,
        "self_reschedule": False,
    }


def write_producer_status(
    status: dict[str, Any], path: Path = PRODUCER_STATUS_PATH
) -> dict[str, Any]:
    if status.get("project") != PROJECT or status.get("task_id") != TASK_ID:
        raise ValueError("PRODUCER_SCOPE_MISMATCH")
    phase = status.get("phase")
    if phase not in PRODUCER_PHASES:
        raise ValueError("PRODUCER_PHASE_INVALID")
    expected_terminal = phase in TERMINAL_PHASES
    if status.get("terminal") is not expected_terminal:
        raise ValueError("PRODUCER_TERMINAL_PHASE_MISMATCH")

    prior = _read_json(path)
    if prior is not None:
        same_run = prior.get("run_id") == status.get("run_id")
        if same_run and int(status.get("seq") or 0) <= int(prior.get("seq") or 0):
            raise ValueError("PRODUCER_SEQ_NOT_ADVANCING")
        if not same_run:
            previous_slot = _parse_aware(prior.get("scheduled_slot_kst"))
            current_slot = _parse_aware(status.get("scheduled_slot_kst"))
            if previous_slot and current_slot and current_slot < previous_slot:
                raise ValueError("PRODUCER_SLOT_TIME_REGRESSION")

    _atomic_write(path, status)
    reread = _read_json(path)
    if reread != status:
        raise RuntimeError("PRODUCER_STATUS_READBACK_MISMATCH")
    return reread


def build_producer_ack(
    *,
    run_id: str,
    monitor_status: dict[str, Any] | None,
    observed_at: str,
    action_taken: str,
) -> dict[str, Any]:
    if _parse_aware(observed_at) is None:
        raise ValueError("ACK_TIME_REQUIRED")
    monitor_seq = None
    classification = None
    if isinstance(monitor_status, dict):
        monitor_seq = monitor_status.get("seq")
        classification = monitor_status.get("classification")
    return {
        "schema_version": SCHEMA_VERSION,
        "project": PROJECT,
        "task_id": TASK_ID,
        "run_id": run_id,
        "observed_at": observed_at,
        "monitor_seq_seen": monitor_seq,
        "monitor_classification_seen": classification,
        "action_taken": action_taken,
    }


def write_producer_ack(
    ack: dict[str, Any], path: Path = PRODUCER_ACK_PATH
) -> dict[str, Any]:
    if ack.get("project") != PROJECT or ack.get("task_id") != TASK_ID:
        raise ValueError("ACK_SCOPE_MISMATCH")
    _atomic_write(path, ack)
    reread = _read_json(path)
    if reread != ack:
        raise RuntimeError("PRODUCER_ACK_READBACK_MISMATCH")
    return reread


def classify_monitor_observation(
    *,
    scheduled_slot_kst: str,
    observed_at: str,
    is_enabled: bool,
    last_run_time: str | None,
    producer_status: dict[str, Any] | None,
    updated_at: str | None = None,
    actor_available: bool = False,
    reason_available: bool = False,
    error_trace_available: bool = False,
    exchange_read_error: str | None = None,
) -> dict[str, Any]:
    slot = _parse_aware(scheduled_slot_kst)
    now = _parse_aware(observed_at)
    last_run = _parse_aware(last_run_time)
    if slot is None or now is None:
        raise ValueError("MONITOR_TIME_INVALID")

    slot_due = now >= slot
    last_run_for_slot = bool(last_run and last_run >= slot)
    early_jitter_seen = bool(last_run and slot - timedelta(minutes=5) <= last_run < slot)

    producer_present = (
        isinstance(producer_status, dict)
        and producer_status.get("project") == PROJECT
        and producer_status.get("task_id") == TASK_ID
        and _same_instant(producer_status.get("scheduled_slot_kst"), scheduled_slot_kst)
    )
    producer_phase = producer_status.get("phase") if producer_present else None
    producer_terminal = producer_status.get("terminal") if producer_present else None
    producer_observed = (
        _parse_aware(producer_status.get("observed_at")) if producer_present else None
    )
    producer_status_age_seconds = (
        max(0.0, (now - producer_observed).total_seconds())
        if producer_observed is not None
        else None
    )

    exchange_anomalies: list[str] = []
    if producer_present:
        expected_terminal = producer_phase in TERMINAL_PHASES
        if not isinstance(producer_terminal, bool) or producer_terminal != expected_terminal:
            exchange_anomalies.append("EXCHANGE_RECEIPT_TERMINAL_MISMATCH")
        elif not producer_terminal and _completion_claimed(producer_status.get("evidence")):
            exchange_anomalies.append("EXCHANGE_RECEIPT_TERMINAL_MISMATCH")

    classification = "HEALTHY"
    failed_stage = None
    root = None
    control_plane_event = False
    auto_run_level_repair_allowed = False

    if exchange_read_error:
        classification = "EXCHANGE_PERSISTENCE_UNAVAILABLE"
        failed_stage = "EXCHANGE_PERSISTENCE"
        root = "ROOT_CAUSE_UNRESOLVED"
    elif slot_due and not last_run_for_slot and not producer_present:
        classification = "SCHEDULE_GAP_NO_PRODUCER_START"
        failed_stage = "BEFORE_PRODUCER_START"
        root = "UNRESOLVED_CONTROL_PLANE"
        control_plane_event = True
    elif producer_present and producer_phase in RUN_LEVEL_FAILURE_PHASES:
        classification = "PRODUCER_REPORTED_FAILURE"
        failed_stage = producer_status.get("failed_stage")
        root = producer_status.get("root_cause") or "ROOT_CAUSE_UNRESOLVED"
        auto_run_level_repair_allowed = True
    elif producer_present and producer_phase in TERMINAL_SUCCESS_PHASES and not is_enabled:
        classification = "POST_RUN_DISABLE"
        failed_stage = "AFTER_VERIFIED_TERMINAL"
        root = "UNRESOLVED_CONTROL_PLANE"
        control_plane_event = True
    elif (
        producer_present
        and producer_phase not in TERMINAL_PHASES
        and producer_status_age_seconds is not None
        and producer_status_age_seconds >= 20 * 60
    ):
        classification = "RUN_STARTED_NO_TERMINAL_RECEIPT"
        failed_stage = str(producer_phase or "UNKNOWN")
        root = "ROOT_CAUSE_UNRESOLVED"
    elif producer_present and "EXCHANGE_RECEIPT_TERMINAL_MISMATCH" in exchange_anomalies:
        classification = "EXCHANGE_RECEIPT_TERMINAL_MISMATCH"
        failed_stage = str(producer_phase or "EXCHANGE_PERSISTENCE")
        root = "ROOT_CAUSE_UNRESOLVED"
    elif slot_due and last_run_for_slot and not producer_present:
        classification = "RUN_INVOKED_NO_PRODUCER_RECEIPT"
        failed_stage = "EXCHANGE_PERSISTENCE"
        root = "ROOT_CAUSE_UNRESOLVED"
    elif slot_due and not last_run_for_slot and is_enabled:
        classification = "SCHEDULE_GAP_ACTIVE"
        failed_stage = "SCHEDULER_INVOCATION"
        root = "UNRESOLVED_CONTROL_PLANE"
        control_plane_event = True
    elif not is_enabled:
        classification = "DISABLED_WITHOUT_PRODUCER_EVIDENCE"
        failed_stage = "CONTROL_PLANE"
        root = "UNRESOLVED_CONTROL_PLANE"
        control_plane_event = True

    attribution = (
        "AVAILABLE"
        if actor_available or reason_available or error_trace_available
        else "CONTROL_PLANE_ATTRIBUTION_UNAVAILABLE"
    )
    if root == "UNRESOLVED_CONTROL_PLANE" and attribution == "AVAILABLE":
        root = "CONTROL_PLANE_EVIDENCE_AVAILABLE_REVIEW_REQUIRED"

    return {
        "schema_version": SCHEMA_VERSION,
        "project": PROJECT,
        "task_id": TASK_ID,
        "monitor_task_id": MONITOR_TASK_ID,
        "scheduled_slot_kst": scheduled_slot_kst,
        "observed_at": observed_at,
        "slot_due": slot_due,
        "last_run_time": last_run_time,
        "last_run_advanced": last_run_for_slot,
        "last_run_for_slot": last_run_for_slot,
        "early_jitter_seen": early_jitter_seen,
        "updated_at": updated_at,
        "is_enabled": is_enabled,
        "producer_status_present": producer_present,
        "producer_phase": producer_phase,
        "producer_terminal": producer_terminal,
        "producer_status_age_seconds": producer_status_age_seconds,
        "exchange_anomalies": exchange_anomalies,
        "classification": classification,
        "failed_stage": failed_stage,
        "root_cause": root,
        "attribution": attribution,
        "mandatory_reporting_slot": (
            slot.astimezone(KST).hour in {9, 10, 21, 22}
            and slot.astimezone(KST).minute == 30
        ),
        "repair_handoff": {
            "event_class": classification,
            "failed_stage": failed_stage,
            "root_cause": root,
            "recommended_action": (
                "NEXT_PRODUCER_RUN_USE_BOUNDED_ALTERNATE_STRATEGY"
                if auto_run_level_repair_allowed
                else (
                    "VERIFY_EXCHANGE_PERSISTENCE_AND_FORCE_VISIBLE_STATUS_REPORT"
                    if classification in {
                        "RUN_INVOKED_NO_PRODUCER_RECEIPT",
                        "EXCHANGE_PERSISTENCE_UNAVAILABLE",
                        "EXCHANGE_RECEIPT_TERMINAL_MISMATCH",
                    }
                    else "PRESERVE_PRODUCER_CODE_AND_VERIFY_NEXT_SCHEDULED_INVOCATION"
                )
            ),
            "auto_run_level_repair_allowed": auto_run_level_repair_allowed,
            "source_code_auto_patch_allowed": False,
            "control_plane_event": control_plane_event,
            "do_not_guess_root_cause": True,
        },
    }


def assess_monitor_status_freshness(
    *,
    observed_at: str,
    monitor_last_run_time: str | None,
    monitor_status: dict[str, Any] | None,
    cadence_minutes: int = 60,
    stale_cycles: int = 2,
) -> dict[str, Any]:
    now = _parse_aware(observed_at)
    monitor_last_run = _parse_aware(monitor_last_run_time)
    status_observed = (
        _parse_aware(monitor_status.get("observed_at"))
        if isinstance(monitor_status, dict)
        else None
    )
    if now is None:
        raise ValueError("MONITOR_TIME_INVALID")
    if cadence_minutes <= 0 or stale_cycles <= 0:
        raise ValueError("MONITOR_FRESHNESS_WINDOW_INVALID")

    age_seconds = (
        max(0.0, (now - status_observed).total_seconds())
        if status_observed is not None
        else None
    )
    lag_from_monitor_run_seconds = (
        max(0.0, (monitor_last_run - status_observed).total_seconds())
        if monitor_last_run is not None and status_observed is not None
        else None
    )
    stale_threshold = cadence_minutes * 60 * stale_cycles
    stale = (
        monitor_last_run is not None
        and (
            status_observed is None
            or (
                lag_from_monitor_run_seconds is not None
                and lag_from_monitor_run_seconds >= stale_threshold
            )
        )
    )
    return {
        "classification": "MONITOR_STATUS_STALE" if stale else "MONITOR_STATUS_FRESH",
        "monitor_status_present": isinstance(monitor_status, dict),
        "monitor_status_observed_at": (
            monitor_status.get("observed_at") if isinstance(monitor_status, dict) else None
        ),
        "monitor_status_age_seconds": age_seconds,
        "lag_from_monitor_run_seconds": lag_from_monitor_run_seconds,
        "cadence_minutes": cadence_minutes,
        "stale_cycles": stale_cycles,
        "root_cause": "ROOT_CAUSE_UNRESOLVED" if stale else None,
    }


def write_monitor_status(
    status: dict[str, Any], *, seq: int, path: Path = MONITOR_STATUS_PATH
) -> dict[str, Any]:
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 1:
        raise ValueError("MONITOR_SEQ_INVALID")
    payload = {**status, "seq": seq}
    if payload.get("monitor_task_id") != MONITOR_TASK_ID:
        raise ValueError("MONITOR_SCOPE_MISMATCH")
    prior = _read_json(path)
    if prior is not None and int(prior.get("seq") or 0) >= seq:
        raise ValueError("MONITOR_SEQ_NOT_ADVANCING")
    _atomic_write(path, payload)
    reread = _read_json(path)
    if reread != payload:
        raise RuntimeError("MONITOR_STATUS_READBACK_MISMATCH")
    if payload.get("classification") not in {"HEALTHY", None}:
        stamp = str(payload.get("observed_at") or "").replace(":", "").replace("+", "_")
        incident = INCIDENT_DIR / f"{stamp}_{payload['classification']}.json"
        _atomic_write(incident, payload)
    return reread


def read_exchange() -> dict[str, Any]:
    producer_status, producer_status_diag = _read_json_diagnostic(PRODUCER_STATUS_PATH)
    producer_ack, producer_ack_diag = _read_json_diagnostic(PRODUCER_ACK_PATH)
    monitor_status, monitor_status_diag = _read_json_diagnostic(MONITOR_STATUS_PATH)
    return {
        "producer_status": producer_status,
        "producer_ack": producer_ack,
        "monitor_status": monitor_status,
        "diagnostics": {
            "producer_status": producer_status_diag,
            "producer_ack": producer_ack_diag,
            "monitor_status": monitor_status_diag,
        },
        "exchange_persistence_ok": all(
            item["readable"]
            for item in (
                producer_status_diag,
                producer_ack_diag,
                monitor_status_diag,
            )
        ),
    }


def self_test() -> None:
    slot = "2026-09-10T08:30:00+09:00"
    observed = "2026-09-10T08:58:00+09:00"

    gap = classify_monitor_observation(
        scheduled_slot_kst=slot,
        observed_at=observed,
        is_enabled=True,
        last_run_time="2026-09-10T05:28:00+09:00",
        producer_status=None,
        updated_at="2026-09-10T08:00:00+09:00",
    )
    assert gap["classification"] == "SCHEDULE_GAP_NO_PRODUCER_START", gap
    assert gap["repair_handoff"]["control_plane_event"] is True
    assert gap["repair_handoff"]["auto_run_level_repair_allowed"] is False

    failed = build_producer_status(
        run_id="r1",
        scheduled_slot_kst=slot,
        phase="FAILED",
        seq=2,
        observed_at="2026-09-10T08:34:00+09:00",
        code_version="v6.8",
        failed_stage="COLLECT",
        error_code="HTTP_429",
        evidence="Retry-After observed",
    )
    reported = classify_monitor_observation(
        scheduled_slot_kst=slot,
        observed_at=observed,
        is_enabled=True,
        last_run_time="2026-09-10T08:31:00+09:00",
        producer_status=failed,
    )
    assert reported["classification"] == "PRODUCER_REPORTED_FAILURE", reported
    assert reported["repair_handoff"]["auto_run_level_repair_allowed"] is True
    assert reported["root_cause"] == "ROOT_CAUSE_UNRESOLVED"

    invoked_without_receipt = classify_monitor_observation(
        scheduled_slot_kst="2026-09-10T10:30:00+09:00",
        observed_at="2026-09-10T10:35:00+09:00",
        is_enabled=True,
        last_run_time="2026-09-10T10:30:33+09:00",
        producer_status=None,
    )
    assert invoked_without_receipt["classification"] == "RUN_INVOKED_NO_PRODUCER_RECEIPT"
    assert invoked_without_receipt["failed_stage"] == "EXCHANGE_PERSISTENCE"
    assert invoked_without_receipt["mandatory_reporting_slot"] is True

    early_only = classify_monitor_observation(
        scheduled_slot_kst="2026-09-10T10:30:00+09:00",
        observed_at="2026-09-10T10:35:00+09:00",
        is_enabled=True,
        last_run_time="2026-09-10T10:28:00+09:00",
        producer_status=None,
    )
    assert early_only["classification"] == "SCHEDULE_GAP_NO_PRODUCER_START", early_only
    assert early_only["early_jitter_seen"] is True

    no_output = build_producer_status(
        run_id="r-no-output",
        scheduled_slot_kst="2026-09-10T16:30:00+09:00",
        phase="VERIFIED_NO_OUTPUT",
        seq=3,
        observed_at="2026-09-10T16:33:00+09:00",
        code_version="v6.8",
        evidence="LIGHT_DELTA_WATCH_ONLY completed; no meaningful delta; no output expected",
        artifact_count=0,
    )
    assert no_output["terminal"] is True

    stale_complete = build_producer_status(
        run_id="r-stale",
        scheduled_slot_kst="2026-09-10T16:30:00+09:00",
        phase="VERIFY",
        seq=2,
        observed_at="2026-09-10T16:33:00+09:00",
        code_version="v6.8",
        evidence="LIGHT_DELTA_WATCH_ONLY complete; no render expected",
    )
    stale = classify_monitor_observation(
        scheduled_slot_kst="2026-09-10T07:30:00Z",
        observed_at="2026-09-10T17:17:00+09:00",
        is_enabled=True,
        last_run_time="2026-09-10T16:34:24+09:00",
        producer_status=stale_complete,
    )
    assert stale["producer_status_present"] is True, stale
    assert stale["classification"] == "RUN_STARTED_NO_TERMINAL_RECEIPT", stale
    assert "EXCHANGE_RECEIPT_TERMINAL_MISMATCH" in stale["exchange_anomalies"], stale

    delivery = build_producer_status(
        run_id="r2",
        scheduled_slot_kst=slot,
        phase="VERIFIED_DELIVERY",
        seq=9,
        observed_at="2026-09-10T08:34:00+09:00",
        code_version="v6.8",
        delivery_reference="attachment://six",
        artifact_count=6,
    )
    disabled = classify_monitor_observation(
        scheduled_slot_kst=slot,
        observed_at=observed,
        is_enabled=False,
        last_run_time="2026-09-10T08:31:00+09:00",
        producer_status=delivery,
    )
    assert disabled["classification"] == "POST_RUN_DISABLE", disabled

    freshness = assess_monitor_status_freshness(
        observed_at="2026-09-10T17:17:00+09:00",
        monitor_last_run_time="2026-09-10T16:37:40+09:00",
        monitor_status={"observed_at": "2026-09-10T10:33:15+09:00"},
        cadence_minutes=60,
        stale_cycles=2,
    )
    assert freshness["classification"] == "MONITOR_STATUS_STALE", freshness

    print("Instagram card pause-monitor exchange v1.1: PASS")


if __name__ == "__main__":
    self_test()
