#!/usr/bin/env python3
"""Evidence-only producer↔pause-monitor exchange for the canonical Instagram card-info task."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from instagram_tcg_content.automation_state_guard import CANONICAL_ID

PROJECT = "instagram_card"
TASK_ID = CANONICAL_ID
MONITOR_TASK_ID = "6aa02cd749c0819196a6b17db6378958"
SCHEMA_VERSION = "1.2-card-pause-exchange-single-router"
KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parents[1]
EXCHANGE_ROOT = ROOT / "TCG_CROSSCHECK" / "IG_CARDINFO" / "pause_monitor_exchange"
PRODUCER_STATUS_PATH = EXCHANGE_ROOT / "PRODUCER_STATUS.json"
PRODUCER_ACK_PATH = EXCHANGE_ROOT / "PRODUCER_ACK.json"
MONITOR_STATUS_PATH = EXCHANGE_ROOT / "MONITOR_STATUS.json"
INCIDENT_DIR = EXCHANGE_ROOT / "incidents"

PRODUCER_PHASES = (
    "STARTED", "PREFLIGHT", "COLLECT", "VERIFY", "COLLECTION_HEALTH",
    "AI_RELIABILITY", "QUALITY_PROFILE", "RENDER", "OUTPUT_VALIDATION",
    "QUALITY_REVIEW", "LEARN", "VERIFIED_DELIVERY", "VERIFIED_NO_OUTPUT",
    "FAILED", "BLOCKED", "DEGRADED",
)
TERMINAL_SUCCESS_PHASES = {"VERIFIED_DELIVERY", "VERIFIED_NO_OUTPUT"}
RUN_LEVEL_FAILURE_PHASES = {"FAILED", "BLOCKED", "DEGRADED"}
TERMINAL_PHASES = TERMINAL_SUCCESS_PHASES | RUN_LEVEL_FAILURE_PHASES
COMPLETION_CLAIMS = (" complete", "completed", "success", "succeeded", "done", "finished", "완료")
STALE_AFTER = timedelta(minutes=20)


def _parse_aware(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return result if result.tzinfo is not None else None


def _same_instant(left: object, right: object) -> bool:
    a, b = _parse_aware(left), _parse_aware(right)
    return bool(a and b and a.astimezone(timezone.utc) == b.astimezone(timezone.utc))


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            temp = Path(handle.name)
        os.replace(temp, path)
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
        if temp and temp.exists():
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
    info = {"path": str(path), "exists": path.is_file(), "readable": False,
            "read_error": None, "sha256": None, "modified_at": None}
    if not path.is_file():
        return None, info
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("JSON_ROOT_NOT_OBJECT")
        info.update(readable=True, sha256=hashlib.sha256(raw).hexdigest(),
                    modified_at=datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat())
        return value, info
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        info["read_error"] = f"{type(exc).__name__}:{exc}"
        return None, info


def _completion_claimed(evidence: object) -> bool:
    return isinstance(evidence, str) and bool(evidence.strip()) and any(
        token in f" {evidence.casefold()}" for token in COMPLETION_CLAIMS
    )


def build_producer_status(*, run_id: str, scheduled_slot_kst: str, phase: str, seq: int,
                          observed_at: str, code_version: str, failed_stage: str | None = None,
                          error_code: str | None = None, root_cause: str | None = None,
                          evidence: Any = None, delivery_reference: str | None = None,
                          artifact_count: int = 0, monitor_seq_seen: int | None = None) -> dict[str, Any]:
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
    if phase in RUN_LEVEL_FAILURE_PHASES and not (failed_stage and error_code):
        raise ValueError("FAILED_PHASE_REQUIRES_STAGE_AND_ERROR")
    if phase == "VERIFIED_DELIVERY" and (artifact_count != 6 or not delivery_reference):
        raise ValueError("VERIFIED_DELIVERY_REQUIRES_6_ARTIFACTS_AND_REFERENCE")
    if phase == "VERIFIED_NO_OUTPUT" and (artifact_count != 0 or evidence in (None, "", {}, [])):
        raise ValueError("VERIFIED_NO_OUTPUT_REQUIRES_ZERO_ARTIFACTS_AND_EVIDENCE")
    return {
        "schema_version": SCHEMA_VERSION, "project": PROJECT, "task_id": TASK_ID,
        "run_id": run_id, "scheduled_slot_kst": scheduled_slot_kst, "phase": phase,
        "terminal": phase in TERMINAL_PHASES, "seq": seq, "observed_at": observed_at,
        "code_version": code_version, "failed_stage": failed_stage, "error_code": error_code,
        "root_cause": root_cause or ("ROOT_CAUSE_UNRESOLVED" if phase in RUN_LEVEL_FAILURE_PHASES else None),
        "evidence": evidence, "delivery_reference": delivery_reference,
        "artifact_count": artifact_count, "monitor_seq_seen": monitor_seq_seen,
        "self_disable": False, "self_pause": False, "self_reschedule": False,
    }


def write_producer_status(status: dict[str, Any], path: Path = PRODUCER_STATUS_PATH) -> dict[str, Any]:
    if status.get("project") != PROJECT or status.get("task_id") != TASK_ID:
        raise ValueError("PRODUCER_SCOPE_MISMATCH")
    phase = status.get("phase")
    if phase not in PRODUCER_PHASES or status.get("terminal") is not (phase in TERMINAL_PHASES):
        raise ValueError("PRODUCER_TERMINAL_PHASE_MISMATCH")
    prior = _read_json(path)
    if prior:
        same_run = prior.get("run_id") == status.get("run_id")
        if same_run and int(status.get("seq") or 0) <= int(prior.get("seq") or 0):
            raise ValueError("PRODUCER_SEQ_NOT_ADVANCING")
        if not same_run:
            previous_slot, current_slot = _parse_aware(prior.get("scheduled_slot_kst")), _parse_aware(status.get("scheduled_slot_kst"))
            if previous_slot and current_slot and current_slot < previous_slot:
                raise ValueError("PRODUCER_SLOT_TIME_REGRESSION")
    _atomic_write(path, status)
    reread = _read_json(path)
    if reread != status:
        raise RuntimeError("PRODUCER_STATUS_READBACK_MISMATCH")
    return reread


def build_producer_ack(*, run_id: str, monitor_status: dict[str, Any] | None,
                       observed_at: str, action_taken: str) -> dict[str, Any]:
    if _parse_aware(observed_at) is None:
        raise ValueError("ACK_TIME_REQUIRED")
    return {
        "schema_version": SCHEMA_VERSION, "project": PROJECT, "task_id": TASK_ID,
        "run_id": run_id, "observed_at": observed_at,
        "monitor_seq_seen": monitor_status.get("seq") if isinstance(monitor_status, dict) else None,
        "monitor_classification_seen": monitor_status.get("classification") if isinstance(monitor_status, dict) else None,
        "action_taken": action_taken,
    }


def write_producer_ack(ack: dict[str, Any], path: Path = PRODUCER_ACK_PATH) -> dict[str, Any]:
    if ack.get("project") != PROJECT or ack.get("task_id") != TASK_ID:
        raise ValueError("ACK_SCOPE_MISMATCH")
    _atomic_write(path, ack)
    reread = _read_json(path)
    if reread != ack:
        raise RuntimeError("PRODUCER_ACK_READBACK_MISMATCH")
    return reread


def _weekly_production_slot(slot: datetime) -> bool:
    local = slot.astimezone(KST)
    return local.weekday() == 0 and local.hour == 19 and local.minute == 0


def classify_monitor_observation(*, scheduled_slot_kst: str, observed_at: str, is_enabled: bool,
                                 last_run_time: str | None, producer_status: dict[str, Any] | None,
                                 updated_at: str | None = None, actor_available: bool = False,
                                 reason_available: bool = False, error_trace_available: bool = False,
                                 exchange_read_error: str | None = None) -> dict[str, Any]:
    slot, now, last_run = _parse_aware(scheduled_slot_kst), _parse_aware(observed_at), _parse_aware(last_run_time)
    if slot is None or now is None:
        raise ValueError("MONITOR_TIME_INVALID")
    slot_due = now >= slot
    last_run_for_slot = bool(last_run and last_run >= slot)
    early_jitter_seen = bool(last_run and slot - timedelta(minutes=5) <= last_run < slot)
    producer_present = bool(isinstance(producer_status, dict) and producer_status.get("project") == PROJECT
                            and producer_status.get("task_id") == TASK_ID
                            and _same_instant(producer_status.get("scheduled_slot_kst"), scheduled_slot_kst))
    phase = producer_status.get("phase") if producer_present else None
    terminal = producer_status.get("terminal") if producer_present else None
    producer_time = _parse_aware(producer_status.get("observed_at")) if producer_present else None
    age = max(0.0, (now - producer_time).total_seconds()) if producer_time else None
    anomalies: list[str] = []
    if producer_present:
        if not isinstance(terminal, bool) or terminal != (phase in TERMINAL_PHASES):
            anomalies.append("EXCHANGE_RECEIPT_TERMINAL_MISMATCH")
        elif not terminal and _completion_claimed(producer_status.get("evidence")):
            anomalies.append("EXCHANGE_RECEIPT_TERMINAL_MISMATCH")

    classification, failed_stage, root = "HEALTHY", None, None
    control_plane_event = False
    auto_repair = False
    if exchange_read_error:
        classification, failed_stage, root = "EXCHANGE_PERSISTENCE_UNAVAILABLE", "EXCHANGE_PERSISTENCE", "ROOT_CAUSE_UNRESOLVED"
    elif producer_present and "EXCHANGE_RECEIPT_TERMINAL_MISMATCH" in anomalies:
        classification, failed_stage, root = "EXCHANGE_RECEIPT_TERMINAL_MISMATCH", str(phase or "EXCHANGE_PERSISTENCE"), "ROOT_CAUSE_UNRESOLVED"
    elif producer_present and phase in RUN_LEVEL_FAILURE_PHASES:
        classification, failed_stage = "PRODUCER_REPORTED_FAILURE", producer_status.get("failed_stage")
        root = producer_status.get("root_cause") or "ROOT_CAUSE_UNRESOLVED"
        auto_repair = True
    elif producer_present and phase in TERMINAL_SUCCESS_PHASES and not is_enabled:
        classification, failed_stage, root, control_plane_event = "POST_RUN_DISABLE", "AFTER_VERIFIED_TERMINAL", "UNRESOLVED_CONTROL_PLANE", True
    elif producer_present and phase not in TERMINAL_PHASES and age is not None and age >= STALE_AFTER.total_seconds():
        classification, failed_stage, root = "RUN_STARTED_NO_TERMINAL_RECEIPT", str(phase or "UNKNOWN"), "ROOT_CAUSE_UNRESOLVED"
    elif slot_due and last_run_for_slot and not producer_present:
        classification, failed_stage, root = "RUN_INVOKED_NO_PRODUCER_RECEIPT", "EXCHANGE_PERSISTENCE", "ROOT_CAUSE_UNRESOLVED"
    elif slot_due and not last_run_for_slot and not producer_present:
        classification, failed_stage, root, control_plane_event = "SCHEDULE_GAP_NO_PRODUCER_START", "BEFORE_PRODUCER_START", "UNRESOLVED_CONTROL_PLANE", True
    elif not is_enabled:
        classification, failed_stage, root, control_plane_event = "DISABLED_WITHOUT_PRODUCER_EVIDENCE", "CONTROL_PLANE", "UNRESOLVED_CONTROL_PLANE", True

    attribution = "AVAILABLE" if actor_available or reason_available or error_trace_available else "CONTROL_PLANE_ATTRIBUTION_UNAVAILABLE"
    if root == "UNRESOLVED_CONTROL_PLANE" and attribution == "AVAILABLE":
        root = "CONTROL_PLANE_EVIDENCE_AVAILABLE_REVIEW_REQUIRED"
    return {
        "schema_version": SCHEMA_VERSION, "project": PROJECT, "task_id": TASK_ID,
        "monitor_task_id": MONITOR_TASK_ID, "scheduled_slot_kst": scheduled_slot_kst,
        "observed_at": observed_at, "slot_due": slot_due, "last_run_time": last_run_time,
        "last_run_advanced": last_run_for_slot, "last_run_for_slot": last_run_for_slot,
        "early_jitter_seen": early_jitter_seen, "updated_at": updated_at, "is_enabled": is_enabled,
        "producer_status_present": producer_present, "producer_phase": phase,
        "producer_terminal": terminal, "producer_status_age_seconds": age,
        "exchange_anomalies": anomalies, "classification": classification,
        "failed_stage": failed_stage, "root_cause": root, "attribution": attribution,
        "mandatory_reporting_slot": _weekly_production_slot(slot),
        "repair_handoff": {
            "event_class": classification, "failed_stage": failed_stage, "root_cause": root,
            "recommended_action": (
                "NEXT_PRODUCER_RUN_USE_BOUNDED_ALTERNATE_STRATEGY" if auto_repair else
                "VERIFY_EXCHANGE_PERSISTENCE_AND_FORCE_VISIBLE_STATUS_REPORT" if classification in {
                    "RUN_INVOKED_NO_PRODUCER_RECEIPT", "EXCHANGE_PERSISTENCE_UNAVAILABLE", "EXCHANGE_RECEIPT_TERMINAL_MISMATCH"
                } else "PRESERVE_PRODUCER_CODE_AND_VERIFY_NEXT_SCHEDULED_INVOCATION"
            ),
            "auto_run_level_repair_allowed": auto_repair,
            "source_code_auto_patch_allowed": False,
            "control_plane_event": control_plane_event,
            "do_not_guess_root_cause": True,
        },
    }


def assess_monitor_status_freshness(*, observed_at: str, monitor_last_run_time: str | None,
                                    monitor_status: dict[str, Any] | None,
                                    cadence_minutes: int = 60, stale_cycles: int = 2) -> dict[str, Any]:
    now, monitor_last_run = _parse_aware(observed_at), _parse_aware(monitor_last_run_time)
    status_observed = _parse_aware(monitor_status.get("observed_at")) if isinstance(monitor_status, dict) else None
    if now is None or cadence_minutes <= 0 or stale_cycles <= 0:
        raise ValueError("MONITOR_FRESHNESS_WINDOW_INVALID")
    age = max(0.0, (now - status_observed).total_seconds()) if status_observed else None
    lag = max(0.0, (monitor_last_run - status_observed).total_seconds()) if monitor_last_run and status_observed else None
    threshold = cadence_minutes * 60 * stale_cycles
    stale = bool(monitor_last_run and (status_observed is None or (lag is not None and lag >= threshold)))
    return {"classification": "MONITOR_STATUS_STALE" if stale else "MONITOR_STATUS_FRESH",
            "monitor_status_present": isinstance(monitor_status, dict),
            "monitor_status_observed_at": monitor_status.get("observed_at") if isinstance(monitor_status, dict) else None,
            "monitor_status_age_seconds": age, "lag_from_monitor_run_seconds": lag,
            "cadence_minutes": cadence_minutes, "stale_cycles": stale_cycles,
            "root_cause": "ROOT_CAUSE_UNRESOLVED" if stale else None}


def write_monitor_status(status: dict[str, Any], *, seq: int, path: Path = MONITOR_STATUS_PATH) -> dict[str, Any]:
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 1:
        raise ValueError("MONITOR_SEQ_INVALID")
    payload = {**status, "seq": seq}
    if payload.get("monitor_task_id") != MONITOR_TASK_ID or payload.get("task_id") != TASK_ID:
        raise ValueError("MONITOR_SCOPE_MISMATCH")
    prior = _read_json(path)
    if prior is not None and int(prior.get("seq") or 0) >= seq:
        raise ValueError("MONITOR_SEQ_NOT_ADVANCING")
    _atomic_write(path, payload)
    reread = _read_json(path)
    if reread != payload:
        raise RuntimeError("MONITOR_STATUS_READBACK_MISMATCH")
    if payload.get("classification") not in {"HEALTHY", None}:
        incident_root = path.parent / "incidents"
        stamp = str(payload.get("observed_at") or "").replace(":", "").replace("+", "_")
        _atomic_write(incident_root / f"{stamp}_{payload['classification']}.json", payload)
    return reread


def read_exchange() -> dict[str, Any]:
    rows = [_read_json_diagnostic(p) for p in (PRODUCER_STATUS_PATH, PRODUCER_ACK_PATH, MONITOR_STATUS_PATH)]
    return {
        "producer_status": rows[0][0], "producer_ack": rows[1][0], "monitor_status": rows[2][0],
        "diagnostics": {"producer_status": rows[0][1], "producer_ack": rows[1][1], "monitor_status": rows[2][1]},
        "exchange_persistence_ok": all(info["readable"] for _, info in rows),
    }


def self_test() -> None:
    slot = "2026-09-14T19:00:00+09:00"
    gap = classify_monitor_observation(scheduled_slot_kst=slot, observed_at="2026-09-14T19:06:00+09:00",
                                       is_enabled=True, last_run_time="2026-09-14T18:00:05+09:00", producer_status=None)
    assert gap["classification"] == "SCHEDULE_GAP_NO_PRODUCER_START" and gap["mandatory_reporting_slot"]
    collect = classify_monitor_observation(scheduled_slot_kst="2026-09-14T18:00:00+09:00", observed_at="2026-09-14T18:06:00+09:00",
                                           is_enabled=True, last_run_time="2026-09-14T18:00:03+09:00", producer_status=None)
    assert collect["classification"] == "RUN_INVOKED_NO_PRODUCER_RECEIPT" and not collect["mandatory_reporting_slot"]
    print("Instagram card pause-monitor exchange single-router: PASS")


if __name__ == "__main__":
    self_test()
