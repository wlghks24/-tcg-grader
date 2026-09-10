#!/usr/bin/env python3
"""Fast, evidence-first root-cause diagnostics for 인스타 카드정보.

Diagnostic-only. Never mutates scheduler/control-plane, content, render, source,
audio, or AI state. It narrows an incident to the last evidenced boundary and
keeps unresolved causes unresolved when direct attribution is unavailable.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Mapping, Sequence

DIAGNOSTIC_VERSION = "1.3-tracechain-fastpath"
PROJECT = 'instagram_card'
TASK_ID = '6a9b8a22e72c8191849c273e1240378e'
MONITOR_TASK_ID = "6aa02cd749c0819196a6b17db6378958"
SYSTEM = '인스타 카드정보'
PRODUCER_SCHEMA = '1.1-card-pause-exchange'
STALE_AFTER_SECONDS = 20 * 60
CLOCK_SKEW_WARN_SECONDS = 120

TERMINAL_SUCCESS_PHASES = frozenset(['VERIFIED_DELIVERY', 'VERIFIED_NO_OUTPUT'])
TERMINAL_FAILURE_PHASES = frozenset(("FAILED", "BLOCKED", "DEGRADED"))
NONTERMINAL_PHASES = frozenset(['STARTED', 'PREFLIGHT', 'COLLECT', 'VERIFY', 'COLLECTION_HEALTH', 'AI_RELIABILITY', 'QUALITY_PROFILE', 'RENDER', 'OUTPUT_VALIDATION', 'QUALITY_REVIEW', 'LEARN'])
KNOWN_PHASES = TERMINAL_SUCCESS_PHASES | TERMINAL_FAILURE_PHASES | NONTERMINAL_PHASES
PHASE_ORDER = {name: idx for idx, name in enumerate(['STARTED', 'PREFLIGHT', 'COLLECT', 'VERIFY', 'COLLECTION_HEALTH', 'AI_RELIABILITY', 'QUALITY_PROFILE', 'RENDER', 'OUTPUT_VALIDATION', 'QUALITY_REVIEW', 'LEARN', 'VERIFIED_DELIVERY', 'VERIFIED_NO_OUTPUT'])}
_UNRESOLVED = {"UNRESOLVED_CONTROL_PLANE", "ROOT_CAUSE_UNRESOLVED", None, ""}

@lru_cache(maxsize=4096)
def _parse_iso_cached(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timezone-aware timestamp required")
    return dt.astimezone(timezone.utc)

def _parse_iso(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return _parse_iso_cached(value)
    except (TypeError, ValueError):
        return None

def same_instant(left: object, right: object) -> bool:
    a, b = _parse_iso(left), _parse_iso(right)
    return a is not None and b is not None and a == b

def _present(value: object) -> bool:
    return value not in (None, "", [], {})

def _stable_fp(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

@dataclass(frozen=True)
class ProducerEvidence:
    present: bool
    matching_slot: bool
    phase: str | None
    terminal: bool | None
    age_seconds: float | None
    clock_skew_seconds: float | None
    seq: int | None
    run_id: str | None
    anomalies: tuple[str, ...]
    failed_stage: str | None
    error_code: str | None
    root_cause: str | None
    evidence: Any
    direct_failure_evidence: bool

def inspect_producer(status: Mapping[str, Any] | None, *, scheduled_slot_kst: str, observed_at: str) -> ProducerEvidence:
    if not isinstance(status, Mapping):
        return ProducerEvidence(False, False, None, None, None, None, None, None, (), None, None, None, None, False)
    scope_ok = status.get("project") == PROJECT and status.get("task_id") == TASK_ID
    slot_ok = same_instant(status.get("scheduled_slot_kst"), scheduled_slot_kst)
    present = bool(scope_ok and slot_ok)
    if not present:
        return ProducerEvidence(False, slot_ok, None, None, None, None, None, None, (), None, None, None, None, False)
    phase = status.get("phase")
    terminal = status.get("terminal")
    anomalies: list[str] = []
    if status.get("schema_version") != PRODUCER_SCHEMA:
        anomalies.append("EXCHANGE_CONTRACT_VERSION_MISMATCH")
    if phase not in KNOWN_PHASES:
        anomalies.append("UNKNOWN_PRODUCER_PHASE")
    expected_terminal = phase in (TERMINAL_SUCCESS_PHASES | TERMINAL_FAILURE_PHASES)
    if not isinstance(terminal, bool) or terminal != expected_terminal:
        anomalies.append("EXCHANGE_RECEIPT_TERMINAL_MISMATCH")
    seq = status.get("seq")
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 0:
        anomalies.append("EXCHANGE_SEQ_INVALID")
        seq = None
    run_id = status.get("run_id") if isinstance(status.get("run_id"), str) and status.get("run_id") else None
    if not run_id:
        anomalies.append("EXCHANGE_RUN_ID_MISSING")
    now = _parse_iso(observed_at)
    producer_at = _parse_iso(status.get("observed_at"))
    slot_at = _parse_iso(scheduled_slot_kst)
    age = max(0.0, (now - producer_at).total_seconds()) if now and producer_at else None
    skew = (producer_at - now).total_seconds() if now and producer_at else None
    if skew is not None and skew > CLOCK_SKEW_WARN_SECONDS:
        anomalies.append("PRODUCER_CLOCK_AHEAD")
    if producer_at and slot_at and producer_at < slot_at:
        anomalies.append("PRODUCER_RECEIPT_BEFORE_SLOT")
    failed_stage = status.get("failed_stage")
    error_code = status.get("error_code")
    evidence = status.get("evidence")
    direct_failure_evidence = phase in TERMINAL_FAILURE_PHASES and _present(error_code) and (_present(failed_stage) or _present(evidence))
    return ProducerEvidence(True, True, phase, terminal, age, skew, seq, run_id, tuple(sorted(set(anomalies))), failed_stage, error_code, status.get("root_cause"), evidence, bool(direct_failure_evidence))

def inspect_trace_chain(history: Sequence[Mapping[str, Any]] | None, *, scheduled_slot_kst: str, observed_at: str) -> dict[str, Any]:
    """Validate only the bounded current-slot lifecycle; never scans global history."""
    if not history:
        return {"status": "UNAVAILABLE", "matched": 0, "anomalies": [], "last_phase": None, "last_seq": None, "trace_hash": None}
    rows = []
    for item in history[-32:]:
        if not isinstance(item, Mapping):
            continue
        if item.get("project") != PROJECT or item.get("task_id") != TASK_ID:
            continue
        if not same_instant(item.get("scheduled_slot_kst"), scheduled_slot_kst):
            continue
        rows.append(item)
    if not rows:
        return {"status": "NO_MATCHING_SLOT", "matched": 0, "anomalies": [], "last_phase": None, "last_seq": None, "trace_hash": None}
    anomalies: list[str] = []
    prior_seq = None; prior_order = None; prior_run = None
    compact = []
    for item in rows:
        phase = item.get("phase"); seq = item.get("seq"); run_id = item.get("run_id")
        if prior_run is None:
            prior_run = run_id
        elif run_id != prior_run:
            anomalies.append("TRACE_RUN_ID_CHANGED_WITHIN_SLOT")
        if isinstance(seq, bool) or not isinstance(seq, int):
            anomalies.append("TRACE_SEQ_INVALID")
        else:
            if prior_seq is not None and seq <= prior_seq:
                anomalies.append("TRACE_SEQ_NOT_MONOTONIC")
            prior_seq = seq
        order = PHASE_ORDER.get(phase)
        if order is not None:
            if prior_order is not None and order < prior_order and phase not in TERMINAL_FAILURE_PHASES:
                anomalies.append("TRACE_PHASE_REGRESSION")
            prior_order = order
        compact.append((run_id, seq, phase, bool(item.get("terminal")), item.get("observed_at")))
    return {
        "status": "ANOMALOUS" if anomalies else "CONSISTENT",
        "matched": len(rows),
        "anomalies": sorted(set(anomalies)),
        "last_phase": rows[-1].get("phase"),
        "last_seq": rows[-1].get("seq"),
        "trace_hash": _stable_fp({"rows": compact}),
    }

def _attribution(actor: object = None, reason: object = None, error_trace: object = None, event_id: object = None) -> dict[str, Any]:
    available = any(_present(x) for x in (actor, reason, error_trace, event_id))
    return {
        "status": "AVAILABLE" if available else "CONTROL_PLANE_ATTRIBUTION_UNAVAILABLE",
        "actor_available": _present(actor), "reason_available": _present(reason),
        "error_trace_available": _present(error_trace), "event_id_available": _present(event_id),
    }

def _probe_for(event: str, failed_stage: str | None) -> tuple[str, ...]:
    probes = {
        "SCHEDULE_GAP_NO_PRODUCER_START": ("scheduler actor/reason/error trace or event_id", "next-slot last_run_time", "matching producer START"),
        "RUN_INVOKED_NO_PRODUCER_RECEIPT": ("producer status write/readback", "exchange path/permission", "matching run_id + slot"),
        "RUN_STARTED_NO_TERMINAL_RECEIPT": (f"heartbeat after {failed_stage or 'last phase'}", "terminal receipt write/readback", "direct stage exception"),
        "EXCHANGE_RECEIPT_TERMINAL_MISMATCH": ("phase/terminal invariant", "terminal writer call", "post-write readback"),
        "EXCHANGE_TRACE_INTEGRITY_FAILURE": ("same-slot seq progression", "run_id continuity", "phase progression"),
        "PRODUCER_REPORTED_FAILURE": ("failed_stage/error_code/evidence", "bounded repair outcome", "next-run recurrence"),
        "POST_RUN_DISABLE": ("post-terminal scheduler mutation actor/event_id", "updated_at change window", "explicit user stop record"),
        "EXCHANGE_CONTRACT_VERSION_MISMATCH": ("code schema", "Library contract schema", "producer receipt schema"),
    }
    return probes.get(event, ())

def diagnose(*, scheduled_slot_kst: str, observed_at: str, is_enabled: bool, last_run_time: str | None,
             producer_status: Mapping[str, Any] | None, producer_history: Sequence[Mapping[str, Any]] | None = None,
             updated_at: str | None = None, actor: object = None, reason: object = None,
             error_trace: object = None, event_id: object = None, exchange_read_error: str | None = None,
             user_stop_recorded: bool = False) -> dict[str, Any]:
    slot = _parse_iso(scheduled_slot_kst); now = _parse_iso(observed_at)
    if slot is None or now is None:
        raise ValueError("scheduled_slot_kst and observed_at must be timezone-aware ISO-8601")
    last_run = _parse_iso(last_run_time)
    slot_due = now >= slot
    last_run_for_slot = bool(last_run and last_run >= slot)
    producer = inspect_producer(producer_status, scheduled_slot_kst=scheduled_slot_kst, observed_at=observed_at)
    trace = inspect_trace_chain(producer_history, scheduled_slot_kst=scheduled_slot_kst, observed_at=observed_at)
    attr = _attribution(actor, reason, error_trace, event_id)
    event = "HEALTHY"; auxiliary: list[str] = []; failed_stage = None; root = None; boundary = "NONE"; control_plane_event = False
    if exchange_read_error:
        event = "EXCHANGE_PERSISTENCE_UNAVAILABLE"; failed_stage = "EXCHANGE_PERSISTENCE"; root = "ROOT_CAUSE_UNRESOLVED"; boundary = "EXCHANGE_PERSISTENCE"
    elif "EXCHANGE_CONTRACT_VERSION_MISMATCH" in producer.anomalies:
        event = "EXCHANGE_CONTRACT_VERSION_MISMATCH"; failed_stage = "EXCHANGE_CONTRACT"; root = "ROOT_CAUSE_UNRESOLVED"; boundary = "EXCHANGE_PERSISTENCE"
    elif trace["status"] == "ANOMALOUS":
        event = "EXCHANGE_TRACE_INTEGRITY_FAILURE"; failed_stage = trace.get("last_phase") or "EXCHANGE_TRACE"; root = "ROOT_CAUSE_UNRESOLVED"; boundary = "EXCHANGE_PERSISTENCE"
    elif slot_due and not last_run_for_slot and not producer.present:
        event = "SCHEDULE_GAP_NO_PRODUCER_START"; auxiliary += ["SCHEDULE_GAP_ACTIVE"] if is_enabled else []; failed_stage = "BEFORE_PRODUCER_START"; root = "UNRESOLVED_CONTROL_PLANE"; boundary = "BEFORE_PRODUCER_START"; control_plane_event = True
    elif slot_due and last_run_for_slot and not producer.present:
        event = "RUN_INVOKED_NO_PRODUCER_RECEIPT"; failed_stage = "EXCHANGE_PERSISTENCE"; root = "ROOT_CAUSE_UNRESOLVED"; boundary = "EXCHANGE_PERSISTENCE"
    elif "EXCHANGE_RECEIPT_TERMINAL_MISMATCH" in producer.anomalies:
        event = "EXCHANGE_RECEIPT_TERMINAL_MISMATCH"; failed_stage = producer.phase or "EXCHANGE_PERSISTENCE"; root = "ROOT_CAUSE_UNRESOLVED"; boundary = "EXCHANGE_PERSISTENCE"
    elif producer.phase in TERMINAL_FAILURE_PHASES:
        event = "PRODUCER_REPORTED_FAILURE"; failed_stage = producer.failed_stage or producer.phase; boundary = "PRODUCER_RUNTIME"
        if producer.direct_failure_evidence:
            root = producer.root_cause or "ROOT_CAUSE_UNRESOLVED"
        else:
            root = "ROOT_CAUSE_UNRESOLVED"; auxiliary.append("PRODUCER_FAILURE_EVIDENCE_INCOMPLETE")
    elif producer.present and producer.phase in NONTERMINAL_PHASES and producer.age_seconds is not None and producer.age_seconds >= STALE_AFTER_SECONDS:
        event = "RUN_STARTED_NO_TERMINAL_RECEIPT"; failed_stage = producer.phase; root = "ROOT_CAUSE_UNRESOLVED"; boundary = "PRODUCER_RUNTIME"
    elif producer.phase in TERMINAL_SUCCESS_PHASES and not is_enabled:
        event = "POST_RUN_DISABLE"; failed_stage = "AFTER_VERIFIED_TERMINAL"; root = "UNRESOLVED_CONTROL_PLANE"; boundary = "AFTER_TERMINAL_CONTROL_PLANE"; control_plane_event = True
    elif not is_enabled:
        event = "DISABLE_BETWEEN_RUNS"; failed_stage = "CONTROL_PLANE"; root = "UNRESOLVED_CONTROL_PLANE"; boundary = "CONTROL_PLANE"; control_plane_event = True
    if control_plane_event and attr["status"] == "AVAILABLE":
        root = "CONTROL_PLANE_EVIDENCE_AVAILABLE_REVIEW_REQUIRED"
    root_resolved = root not in _UNRESOLVED and root != "CONTROL_PLANE_EVIDENCE_AVAILABLE_REVIEW_REQUIRED"
    evidence_tier = "DIRECT" if root_resolved or (event == "PRODUCER_REPORTED_FAILURE" and producer.direct_failure_evidence) else "STRUCTURAL" if event != "HEALTHY" else "NONE"
    pattern_fingerprint = _stable_fp({"project": PROJECT, "event": event, "enabled": bool(is_enabled), "boundary": boundary, "producer_phase": producer.phase, "producer_present": producer.present, "anomalies": producer.anomalies, "trace_anomalies": trace["anomalies"], "attribution": attr["status"]})
    recovery_allowed = event in {"DISABLE_BETWEEN_RUNS", "POST_RUN_DISABLE"} and not user_stop_recorded
    return {
        "diagnostic_version": DIAGNOSTIC_VERSION, "project": PROJECT, "system": SYSTEM,
        "task_id": TASK_ID, "monitor_task_id": MONITOR_TASK_ID,
        "scheduled_slot_kst": scheduled_slot_kst, "observed_at": observed_at, "updated_at": updated_at,
        "slot_due": slot_due, "last_run_time": last_run_time, "last_run_for_slot": last_run_for_slot,
        "is_enabled": bool(is_enabled), "event_class": event, "auxiliary_events": auxiliary,
        "cause_boundary": boundary, "failed_stage": failed_stage, "root_cause": root,
        "root_cause_resolved": root_resolved, "attribution": attr,
        "producer_status_present": producer.present, "producer_phase": producer.phase,
        "producer_terminal": producer.terminal, "producer_status_age_seconds": producer.age_seconds,
        "producer_clock_skew_seconds": producer.clock_skew_seconds, "producer_seq": producer.seq,
        "producer_run_id": producer.run_id, "producer_anomalies": list(producer.anomalies),
        "producer_direct_failure_evidence": producer.direct_failure_evidence,
        "trace_status": trace["status"], "trace_matched": trace["matched"],
        "trace_anomalies": trace["anomalies"], "trace_hash": trace["trace_hash"],
        "exchange_status": "UNAVAILABLE" if exchange_read_error else "OBSERVED",
        "exchange_read_error": exchange_read_error, "evidence_tier": evidence_tier,
        "recommended_probes": list(_probe_for(event, failed_stage)),
        "pattern_fingerprint": pattern_fingerprint,
        "recovery_allowed": recovery_allowed, "recovery_change": {"is_enabled": True} if recovery_allowed else {},
        "do_not_guess_root_cause": True, "scheduler_mutation_performed": False,
    }
