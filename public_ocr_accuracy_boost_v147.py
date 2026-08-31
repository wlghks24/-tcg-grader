#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Use the v147 adaptive label OCR for collected/public graded-photo evidence."""
from __future__ import annotations

import tempfile
from typing import Any

import graded_photo_evidence as evidence
import ocr_accuracy_boost_v147 as boost

PATCH_ID = 147
_APPLIED = False
_ORIGINAL_OCR = None
_ORIGINAL_COMPANY = None
_ORIGINAL_GRADE = None
_ORIGINAL_EXTRACT = None


def _company(text: str, fallback: str = "") -> str:
    original = _ORIGINAL_COMPANY
    visual = None
    if callable(original):
        try:
            visual = original(text, "")
        except (TypeError, ValueError):
            visual = None
    visual = visual or boost.detect_company(text)
    if visual in evidence.COMPANIES:
        return visual
    fallback = str(fallback or "").upper()
    return fallback if fallback in evidence.COMPANIES else ""


def _extract(text: str, fallback_company: str = "") -> dict[str, Any]:
    clean = " ".join(str(text or "").split())[:5000]
    visual_company = _company(clean, "")
    parse_company = visual_company or _company("", fallback_company)
    grade = None
    if callable(_ORIGINAL_GRADE):
        try:
            grade = _ORIGINAL_GRADE(clean)
        except (TypeError, ValueError, OverflowError):
            grade = None
    if grade is None:
        grade = boost.normalize_grade(clean, parse_company)
    cert = boost.normalize_cert(parse_company or None, clean) or ""
    return {
        "company": visual_company or (parse_company if fallback_company else ""),
        "grade": grade,
        "certification_id": cert,
        "ocr_text": clean[:1200],
    }


def _ocr(image):
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg") as tmp:
            image.convert("RGB").save(tmp.name, format="JPEG", quality=94)
            text, error, _ = boost.ocr_label(
                tmp.name, profile="accuracy", fallback_company="", slab_module=None
            )
        return text[:5000], error
    except (OSError, ValueError, TypeError):
        if callable(_ORIGINAL_OCR):
            return _ORIGINAL_OCR(image)
        return "", "ocr_failed"


def apply() -> dict[str, Any]:
    global _APPLIED, _ORIGINAL_OCR, _ORIGINAL_COMPANY, _ORIGINAL_GRADE, _ORIGINAL_EXTRACT
    if _ORIGINAL_OCR is None:
        _ORIGINAL_OCR = evidence._ocr
    if _ORIGINAL_COMPANY is None:
        _ORIGINAL_COMPANY = evidence._company
    if _ORIGINAL_GRADE is None:
        _ORIGINAL_GRADE = evidence._grade
    if _ORIGINAL_EXTRACT is None:
        _ORIGINAL_EXTRACT = evidence.extract_label_evidence
    evidence._ocr = _ocr
    evidence._company = _company
    evidence.extract_label_evidence = _extract
    _APPLIED = True
    return {
        "ok": True,
        "patch": PATCH_ID,
        "public_photo_adaptive_ocr": True,
        "grader_specific_cert_lengths": True,
        "common_ocr_confusions_repaired": True,
    }


def status() -> dict[str, Any]:
    return {
        "ok": bool(_APPLIED and evidence._ocr is _ocr and evidence.extract_label_evidence is _extract),
        "patch": PATCH_ID,
        "applied": _APPLIED,
    }
