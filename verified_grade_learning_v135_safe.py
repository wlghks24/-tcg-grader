#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Safety adapter for v135 verified grade learning.

This adapter guarantees that ``vision_calibration.json`` is rebuilt only from
rows that already passed the v135 official-registry gate. It also prevents the
base module's compatibility call from training the vision residual model on a
mixed legacy store.

v287 additionally makes every production grade-learning writer share one
cross-process transaction.  The tablet RAW-proxy watcher, local server and
manual import paths can therefore not overwrite each other's learning rows.
"""
from __future__ import annotations

from contextlib import contextmanager
import threading
from pathlib import Path
from typing import Any, Callable, Mapping

import verified_grade_learning_v135 as base
from safe_runtime import exclusive_file_lock

# Re-export stable helpers used by the v135 server wrapper.
ROOT = base.ROOT
LEARNING_STORE = base.LEARNING_STORE
VERIFIED_CERTS = base.VERIFIED_CERTS
VISION_CALIBRATION = base.VISION_CALIBRATION
registry_index = base.registry_index
eligible_training_rows = base.eligible_training_rows
_cert_key = base._cert_key
_finite = base._finite

_PROXY_SOURCE_PREFIX = "verified_slab_card_roi_v"
_TRANSACTION_LOCAL = threading.local()

# Keep the original unwrapped writers even if this adapter is reloaded.  This
# prevents wrapper-on-wrapper recursion in long-running tablet processes/tests.
_BASE_PERSIST_VERIFIED_CERT = getattr(
    base._persist_verified_cert,
    "_tcg_unlocked_persist_verified_cert",
    base._persist_verified_cert,
)
_BASE_APPEND_STORE_ROW = getattr(
    base._append_store_row,
    "_tcg_unlocked_append_store_row",
    base._append_store_row,
)


def _safe_version(value: Any, default: int, minimum: int) -> int:
    if isinstance(value, bool):
        return max(minimum, default)
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return max(minimum, default)
    return max(minimum, min(1_000_000, number))


def _normalize_persisted_version(path: Path, *, default: int, minimum: int) -> None:
    """Repair only malformed/bounded version metadata before a verified write.

    The data rows themselves are left untouched.  Missing files are created by
    the normal base writer, so a metadata repair cannot manufacture learning
    state on its own.
    """
    target = Path(path)
    try:
        if target.is_symlink() or not target.is_file():
            return
    except OSError:
        return
    payload = base._load(target, {})
    if not isinstance(payload, dict):
        return
    normalized = _safe_version(payload.get("version"), default, minimum)
    raw = payload.get("version")
    if type(raw) is int and raw == normalized:
        return
    payload["version"] = normalized
    base._atomic_json(target, payload)


@contextmanager
def _learning_transaction():
    """Re-entrant thread scope over one cross-process learning-store lock."""
    depth = int(getattr(_TRANSACTION_LOCAL, "depth", 0) or 0)
    if depth > 0:
        _TRANSACTION_LOCAL.depth = depth + 1
        try:
            yield
        finally:
            _TRANSACTION_LOCAL.depth = depth
        return

    with exclusive_file_lock(base.LEARNING_STORE, timeout_seconds=60.0, stale_seconds=600.0):
        _TRANSACTION_LOCAL.depth = 1
        try:
            yield
        finally:
            _TRANSACTION_LOCAL.depth = 0


def _same_cert(row: Mapping[str, Any], candidate: Mapping[str, Any]) -> bool:
    company = base._company(row.get("company") or row.get("grader"))
    cert = base._cert(row.get("certification_id") or row.get("cert_no"))
    incoming_company = base._company(candidate.get("company") or candidate.get("grader"))
    incoming_cert = base._cert(candidate.get("certification_id") or candidate.get("cert_no"))
    return bool(company and cert and incoming_company and incoming_cert and
                base._cert_key(company, cert) == base._cert_key(incoming_company, incoming_cert))


def _proxy_overwrites_genuine_raw(row: Mapping[str, Any]) -> bool:
    incoming_source = str(row.get("source") or "")
    if not incoming_source.startswith(_PROXY_SOURCE_PREFIX):
        return False
    payload = base._load(base.LEARNING_STORE, {})
    rows = payload.get("v99_validation", []) if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        return False
    for existing in rows:
        if not isinstance(existing, Mapping) or not _same_cert(existing, row):
            continue
        existing_source = str(existing.get("source") or "")
        # Genuine RAW submissions historically have no source tag at all.  Any
        # same-cert row that is not an explicit slab proxy therefore outranks a
        # proxy and must never be replaced by the watcher.
        if not existing_source.startswith(_PROXY_SOURCE_PREFIX):
            return True
    return False


def _persist_verified_cert(company: str, cert: str, grade: float, verify_result: Mapping[str, Any]) -> None:
    with _learning_transaction():
        _normalize_persisted_version(base.VERIFIED_CERTS, default=1, minimum=1)
        _BASE_PERSIST_VERIFIED_CERT(company, cert, grade, verify_result)


def _append_store_row(row: dict[str, Any]) -> None:
    with _learning_transaction():
        _normalize_persisted_version(base.LEARNING_STORE, default=3, minimum=3)
        if _proxy_overwrites_genuine_raw(row):
            raise ValueError("genuine raw sample has priority over slab proxy")
        _BASE_APPEND_STORE_ROW(row)


# Mark wrappers so a module reload can always recover the true base writer.
_persist_verified_cert._tcg_unlocked_persist_verified_cert = _BASE_PERSIST_VERIFIED_CERT  # type: ignore[attr-defined]
_append_store_row._tcg_unlocked_append_store_row = _BASE_APPEND_STORE_ROW  # type: ignore[attr-defined]

# Patch the base module centrally.  verified_slab_raw_learning_v155 imports the
# base module first and this adapter immediately afterwards, before any sync is
# executed, so its direct ``grade_learning._append_store_row`` call also passes
# through the same transaction and genuine-RAW priority gate.
base._persist_verified_cert = _persist_verified_cert
base._append_store_row = _append_store_row


def rebuild_safe_vision_calibration() -> dict[str, Any]:
    with _learning_transaction():
        rows, audit = base.eligible_training_rows()
        from grading_accuracy_v99 import train_company_calibration
        from vision_calibration import sanitize_rows, train_calibration

        # sanitize_rows performs its own official-result/cert checks; the payload it
        # receives here has already been narrowed further by the exact verified
        # registry match in v135.
        payload = {"v99_validation": rows, "v30_validation": [], "v11_validation": []}
        global_models = train_company_calibration(rows)
        vision_rows = sanitize_rows(payload)
        result = train_calibration(vision_rows, global_models)
        result["registry_gate_v135"] = True
        result["registry_verified_training_rows"] = len(rows)
        result["registry_gate_audit"] = audit
        base._atomic_json(base.VISION_CALIBRATION, result)
        return result


def model_status() -> dict[str, Any]:
    status = base.model_status()
    calibration = base._load(base.VISION_CALIBRATION, {})
    safe = isinstance(calibration, dict) and calibration.get("registry_gate_v135") is True
    profiles = calibration.get("profiles", {}) if safe else {}
    status["vision_profiles"] = profiles if isinstance(profiles, dict) else {}
    status["policy"] = {
        **status.get("policy", {}),
        "vision_residual_registry_gate_required": True,
        "mixed_legacy_vision_calibration_used": False,
        "cross_process_training_transaction_lock": True,
        "reentrant_learning_transaction_lock": True,
        "proxy_learning_genuine_raw_priority_atomic": True,
        "persisted_version_metadata_repaired": True,
    }
    return status


def submit_verified_sample(
    payload: Mapping[str, Any],
    *,
    verifier: Callable[[str, str, float], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    # Server requests are already protected by DATA_WRITE_LOCK, but this module
    # is also used by manual import/maintenance entrypoints and by the separate
    # slab RAW-proxy watcher. Serialize the complete load-modify-save +
    # calibration transaction across OS processes.
    with _learning_transaction():
        # The base function has a compatibility call to vision_calibration.train_file.
        # Temporarily replace that single call, then immediately rebuild from the
        # registry-gated dataset through rebuild_safe_vision_calibration(). The
        # transaction prevents another safe-adapter invocation from seeing this
        # temporary replacement concurrently.
        import vision_calibration
        original = vision_calibration.train_file
        vision_calibration.train_file = lambda *args, **kwargs: {"skipped": "v135-safe-adapter"}
        try:
            result = base.submit_verified_sample(payload, verifier=verifier)
        finally:
            vision_calibration.train_file = original
        if result.get("accepted"):
            rebuild_safe_vision_calibration()
            result["model"] = model_status()
        return result


def audit() -> dict[str, Any]:
    status = model_status()
    return {
        "ok": True,
        "version": 135,
        "verified_registry_entries": len(base.registry_index()),
        "verified_training_rows": status.get("verified_training_rows", 0),
        "audit": status.get("audit", {}),
        "companies": status.get("companies", {}),
        "vision_profiles": len(status.get("vision_profiles", {})),
        "policy": status.get("policy", {}),
    }
