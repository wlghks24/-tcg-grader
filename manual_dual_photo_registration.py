#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Front/back pair support for manual graded-slab registration.

The existing manual registration keeps the front slab image as the primary OCR
source. This patch accepts an additional back image, stores it beside the front
image, and records pair metadata. OCR accuracy v147 is applied to manual/public
label OCR, and v148 may use the back only when front identity OCR is incomplete.

Compatibility note:
``ocr_front_back_fallback_v148`` wraps the v147 row-level OCR function. The old
v147 ``status()`` used strict function identity, so the wrapper made a healthy
OCR stack report ``ok=False``. This module installs a narrow status adapter that
recognises the intentional v148 wrapper while keeping all real apply checks.

v155 learning integration:
Strict official verification remains required first. After that,
``verified_slab_raw_learning_v155`` crops away the grader label/outer holder and
uses only card-only ROI features as a conservative RAW defect/grade proxy. The
public registration row exposes that learning state to the tablet UI.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import manual_graded_photo_registration as manual_photo
import ocr_accuracy_boost_v147 as ocr_boost
import public_ocr_accuracy_boost_v147 as public_ocr_boost
import ocr_front_back_fallback_v148 as front_back_ocr
from safe_runtime import atomic_write_bytes

PATCH_ID = 155
_APPLIED = False
_ORIGINAL_REGISTER = None
_ORIGINAL_PUBLIC_ROW = None
_ORIGINAL_OCR_STATUS = None


def _public_row_with_pair(row: dict[str, Any]) -> dict[str, Any]:
    base = _ORIGINAL_PUBLIC_ROW(row) if _ORIGINAL_PUBLIC_ROW else dict(row)
    for key in (
        "back_image_sha256", "back_image_width", "back_image_height", "back_image_bytes",
        "front_back_pair_complete", "back_original_filename", "pair_upload_mode",
        "manual_official_proof_state", "manual_official_proof_registered",
        "manual_official_proof_at", "manual_official_proof_match_mode",
        "manual_official_proof_ocr_company", "manual_official_proof_ocr_grade",
        "manual_official_proof_ocr_certification_id",
        "official_verification_source", "official_verification_method", "official_verified_at",
        "training_eligible", "raw_grade_calibration_eligible", "raw_defect_learning_eligible",
        "raw_proxy_learning_state", "raw_proxy_learning_engine", "raw_proxy_raw_pred",
        "raw_proxy_min_company_rows",
    ):
        if key in row:
            base[key] = row.get(key)
    return base


def _attach_back_image(registration_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    back_data, back_ext, back_width, back_height = manual_photo._decode_image(payload.get("back_image_data_url"))
    back_digest = hashlib.sha256(back_data).hexdigest()
    with manual_photo.LOCK:
        registry = manual_photo._registry()
        index, row = manual_photo._find_row(registry, registration_id)
        row = dict(row)
        front_digest = str(row.get("image_sha256") or "")
        if front_digest and front_digest == back_digest:
            raise ValueError("앞면과 뒷면 사진이 동일합니다. 서로 다른 앞/뒤 사진을 선택하세요.")
        existing_back = str(row.get("back_image_sha256") or "")
        if existing_back and existing_back != back_digest:
            raise ValueError("이미 다른 뒷면 사진이 등록되어 있습니다. 기존 자료를 확인하세요.")
        image_path = Path(str(row.get("image_path") or ""))
        if not image_path.parts:
            raise ValueError("앞면 사진 저장경로를 확인하지 못했습니다.")
        target = manual_photo.ROOT / image_path.parent / f"{registration_id}_back{back_ext}"
        atomic_write_bytes(target, back_data, suffix=".manual-back.tmp")
        row.update({
            "updated_at": manual_photo._now(),
            "back_image_path": target.relative_to(manual_photo.ROOT).as_posix(),
            "back_image_sha256": back_digest,
            "back_image_width": back_width,
            "back_image_height": back_height,
            "back_image_bytes": len(back_data),
            "back_original_filename": manual_photo._bounded_text(payload.get("back_filename"), 120),
            "front_back_pair_complete": True,
            "pair_upload_mode": "manual_front_back",
        })
        audit = dict(row.get("audit") or {})
        audit.update({
            "manual_front_back_pair": True,
            "back_image_magic_checked": True,
            "back_path_generated_server_side": True,
            "front_back_distinct_sha256": True,
        })
        row["audit"] = audit
        registry["registrations"][index] = row
        manual_photo._save_registry(registry)
    return row


def _register_with_optional_back(payload: dict[str, Any]) -> dict[str, Any]:
    result = _ORIGINAL_REGISTER(payload)
    if not payload.get("back_image_data_url"):
        return result
    registration = result.get("registration") if isinstance(result, dict) else None
    registration_id = str((registration or {}).get("registration_id") or "")
    if not registration_id:
        raise ValueError("앞면 등록 후 등록번호를 확인하지 못했습니다.")
    row = _attach_back_image(registration_id, payload)
    output = dict(result)
    output["registration"] = manual_photo._public_row(row)
    output["front_back_pair_complete"] = True
    return output


_register_with_optional_back._dual_photo_policy = True


def _install_ocr_status_compat() -> None:
    """Make v147 status wrapper-aware without weakening its real apply gate."""
    global _ORIGINAL_OCR_STATUS
    current = ocr_boost.status
    if getattr(current, "_v148_wrapper_aware_status", False):
        return
    if _ORIGINAL_OCR_STATUS is None:
        _ORIGINAL_OCR_STATUS = current

    def compatible_status() -> dict[str, Any]:
        original = _ORIGINAL_OCR_STATUS
        result = dict(original()) if callable(original) else {
            "ok": False,
            "patch": getattr(ocr_boost, "PATCH_ID", 147),
            "engine": getattr(ocr_boost, "ENGINE", "slab-ocr-accuracy-v147"),
            "applied": bool(getattr(ocr_boost, "_APPLIED", False)),
        }
        wrapped = bool(getattr(manual_photo._ocr_for_row, "_front_back_ocr_fallback", False))
        v147_applied = bool(result.get("applied") or getattr(ocr_boost, "_APPLIED", False))
        v148_applied = front_back_ocr.status().get("ok") is True
        if wrapped and v147_applied and v148_applied:
            result["ok"] = True
            result["wrapped_by_v148"] = True
            result["row_ocr_entrypoint"] = "front_back_fallback_v148"
        return result

    compatible_status._v148_wrapper_aware_status = True
    ocr_boost.status = compatible_status


def apply() -> dict[str, Any]:
    global _APPLIED, _ORIGINAL_REGISTER, _ORIGINAL_PUBLIC_ROW
    ocr_status = ocr_boost.apply()
    public_status = public_ocr_boost.apply()
    front_back_status = front_back_ocr.apply()
    if (
        ocr_status.get("ok") is not True
        or public_status.get("ok") is not True
        or front_back_status.get("ok") is not True
    ):
        raise RuntimeError("OCR accuracy boost v148 failed to apply")
    _install_ocr_status_compat()
    if _ORIGINAL_REGISTER is None:
        _ORIGINAL_REGISTER = manual_photo.register
    if _ORIGINAL_PUBLIC_ROW is None:
        _ORIGINAL_PUBLIC_ROW = manual_photo._public_row
    manual_photo._public_row = _public_row_with_pair
    manual_photo.register = _register_with_optional_back

    import manual_official_verified_integration_v154 as official_integration
    integration_status = official_integration.apply()
    if integration_status.get("ok") is not True:
        raise RuntimeError("manual official verification integration v154 failed to apply")

    _APPLIED = True
    return {
        "ok": True,
        "patch": PATCH_ID,
        "manual_front_back_upload": True,
        "front_used_for_ocr": True,
        "back_stored_separately": True,
        "manual_proof_state_exposed": True,
        "manual_official_integrated_verification": True,
        "verified_slab_raw_proxy_learning": True,
        "raw_learning_requires_official_verification": True,
        "manual_official_migration": integration_status.get("last_migration"),
        "ocr_accuracy_boost": ocr_boost.status().get("ok") is True,
        "public_ocr_accuracy_boost": public_status.get("ok") is True,
        "back_ocr_fallback": front_back_status.get("ok") is True,
        "ocr_engine": ocr_status.get("engine"),
        "ocr_adaptive_multi_crop": ocr_status.get("adaptive_multi_crop") is True,
    }


def status() -> dict[str, Any]:
    ocr_status = ocr_boost.status()
    public_status = public_ocr_boost.status()
    front_back_status = front_back_ocr.status()
    try:
        import manual_official_verified_integration_v154 as official_integration
        integration_status = official_integration.status()
    except (ImportError, RuntimeError, ValueError, TypeError):
        integration_status = {"ok": False}
    return {
        "ok": bool(
            getattr(manual_photo.register, "_dual_photo_policy", False)
            and ocr_status.get("ok") is True
            and public_status.get("ok") is True
            and front_back_status.get("ok") is True
            and integration_status.get("ok") is True
        ),
        "patch": PATCH_ID,
        "applied": _APPLIED,
        "manual_front_back_upload": True,
        "front_used_for_ocr": True,
        "back_stored_separately": True,
        "manual_proof_state_exposed": True,
        "manual_official_integrated_verification": integration_status.get("ok") is True,
        "verified_slab_raw_proxy_learning": True,
        "raw_learning_requires_official_verification": True,
        "ocr_accuracy_boost": ocr_status.get("ok") is True,
        "public_ocr_accuracy_boost": public_status.get("ok") is True,
        "back_ocr_fallback": front_back_status.get("ok") is True,
        "ocr_engine": ocr_status.get("engine"),
    }
