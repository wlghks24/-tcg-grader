#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Use the uploaded slab back photo only when front-label OCR is incomplete.

The front remains the primary OCR source. The back is a bounded fallback for
company/certification identity (bar-code text or repeated slab label). A back-side
number never replaces a successfully read front grade, which reduces false grade
matches from card numbers and barcodes.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import manual_graded_photo_registration as manual_photo
import ocr_accuracy_boost_v147 as boost

PATCH_ID = 148
_APPLIED = False
_ORIGINAL_OCR_FOR_ROW = None


def _complete(evidence: dict[str, Any]) -> bool:
    return bool(
        evidence.get("company")
        and evidence.get("certification_id")
        and evidence.get("grade") is not None
    )


def _ocr_for_row_front_back(row: dict[str, Any]):
    result = _ORIGINAL_OCR_FOR_ROW(row)
    text, error, diagnostics, evidence, cache_hit = result
    evidence = dict(evidence or {})
    diagnostics = dict(diagnostics or {})
    if cache_hit or _complete(evidence):
        diagnostics.setdefault("back_ocr_used", False)
        return text, error, diagnostics, evidence, cache_hit

    back_rel = str(row.get("back_image_path") or "").strip()
    if not back_rel:
        diagnostics["back_ocr_used"] = False
        diagnostics["back_ocr_reason"] = "back_image_not_available"
        return text, error, diagnostics, evidence, cache_hit

    back_path = manual_photo.ROOT / Path(back_rel)
    fallback_company = str(row.get("company") or evidence.get("company") or "").upper()
    try:
        import library_slab_corpus as slab
        back_text, back_error, back_diag = boost.ocr_label(
            back_path,
            profile="accuracy",
            fallback_company=fallback_company,
            slab_module=slab,
        )
        back_company, back_cert, back_grade = boost.fields_from_text(
            back_text,
            fallback_company=fallback_company,
            slab_module=slab,
        )
    except (ImportError, OSError, ValueError, TypeError):
        diagnostics["back_ocr_used"] = True
        diagnostics["back_ocr_error"] = "back_ocr_unavailable"
        return text, error, diagnostics, evidence, cache_hit

    # Back-side OCR is strongest for repeated company/cert data. Keep the front
    # grade when available; only expose back grade as a diagnostic hint.
    if not evidence.get("company") and back_company:
        evidence["company"] = back_company
    if not evidence.get("certification_id") and back_cert:
        evidence["certification_id"] = back_cert
    diagnostics.update({
        "back_ocr_used": True,
        "back_ocr_engine": back_diag.get("engine"),
        "back_ocr_pass_count": back_diag.get("pass_count", 0),
        "back_company_resolved": bool(back_company),
        "back_cert_resolved": bool(back_cert),
        "back_grade_hint": back_grade,
        "back_ocr_error": back_error,
    })
    combined = " | ".join(part for part in (str(text or ""), f"BACK:{back_text}" if back_text else "") if part)[:5000]
    return combined, error if text else back_error, diagnostics, evidence, False


_ocr_for_row_front_back._front_back_ocr_fallback = True


def apply() -> dict[str, Any]:
    global _APPLIED, _ORIGINAL_OCR_FOR_ROW
    if _ORIGINAL_OCR_FOR_ROW is None:
        _ORIGINAL_OCR_FOR_ROW = manual_photo._ocr_for_row
    manual_photo._ocr_for_row = _ocr_for_row_front_back
    _APPLIED = True
    return {
        "ok": True,
        "patch": PATCH_ID,
        "front_primary": True,
        "back_fallback_only_when_front_incomplete": True,
        "back_can_recover_company": True,
        "back_can_recover_certification": True,
        "back_cannot_override_front_grade": True,
    }


def status() -> dict[str, Any]:
    return {
        "ok": bool(_APPLIED and getattr(manual_photo._ocr_for_row, "_front_back_ocr_fallback", False)),
        "patch": PATCH_ID,
        "applied": _APPLIED,
    }
