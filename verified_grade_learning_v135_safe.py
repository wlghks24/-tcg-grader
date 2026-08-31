#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Safety adapter for v135 verified grade learning.

This adapter guarantees that ``vision_calibration.json`` is rebuilt only from
rows that already passed the v135 official-registry gate. It also prevents the
base module's compatibility call from training the vision residual model on a
mixed legacy store.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping

import verified_grade_learning_v135 as base

# Re-export stable helpers used by the v135 server wrapper.
ROOT = base.ROOT
LEARNING_STORE = base.LEARNING_STORE
VERIFIED_CERTS = base.VERIFIED_CERTS
VISION_CALIBRATION = base.VISION_CALIBRATION
registry_index = base.registry_index
eligible_training_rows = base.eligible_training_rows
_cert_key = base._cert_key
_finite = base._finite
_persist_verified_cert = base._persist_verified_cert
_append_store_row = base._append_store_row


def rebuild_safe_vision_calibration() -> dict[str, Any]:
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
    }
    return status


def submit_verified_sample(
    payload: Mapping[str, Any],
    *,
    verifier: Callable[[str, str, float], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    # The base function has a compatibility call to vision_calibration.train_file.
    # Temporarily replace that single call, then immediately rebuild from the
    # registry-gated dataset through rebuild_safe_vision_calibration().
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
