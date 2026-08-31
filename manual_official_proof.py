#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Manual official-page proof fallback for graded-photo registration.

A user may open the official PSA/BGS/CGC/TAG/BRG lookup page and upload a
screenshot. The screenshot is reference-only evidence: it never sets
official_result=True and never enters RAW grade calibration.

v150 hardening:
- certificate number is the primary page-identity key;
- official-company text/domain evidence is required;
- grade may be recovered from the already OCR-confirmed slab when the official
  page screenshot does not expose the grade in the current viewport;
- OCR omissions do not quarantine the underlying card;
- explicit proof conflicts are recorded on the proof attempt but do not
  downgrade an otherwise valid pending registration.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import threading
import time
from typing import Any

import manual_graded_photo_registration as manual_photo
from grading_cert_verifier import lookup_url
from safe_runtime import atomic_write_bytes, atomic_write_json

ROOT = Path(__file__).resolve().parent
PROOF_ROOT = ROOT / "GRADE_TRAINING_INBOX" / "manual_official_proof"
REFERENCE_PATH = ROOT / "manual_official_proof_references.json"
MAX_REFERENCES = 2000
PROOF_RATE_WINDOW_SECONDS = 10 * 60.0
PROOF_RATE_MAX = 12
_REGISTRATION_RE = re.compile(r"^manual-[0-9]{14}-[0-9a-f]{12}$")
_PROOF_RATE_LOCK = threading.Lock()
_PROOF_ATTEMPTS: deque[float] = deque()

_COMPANY_HINTS = {
    "PSA": ("PSACARD", "PSA"),
    "BGS": ("BECKETT", "BGS"),
    "CGC": ("CGCCARDS", "CGC"),
    "TAG": ("TAGGRADING", "TAG"),
    "BRG": ("BRG",),
}
_DIGIT_CONFUSION = str.maketrans({"O": "0", "Q": "0", "I": "1", "L": "1", "S": "5", "B": "8", "G": "6", "Z": "2"})


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean_cert(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()[:24]


def _grade(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or not 1 <= number <= 10:
        return None
    return number


def _claim_proof_upload() -> None:
    now = time.monotonic()
    with _PROOF_RATE_LOCK:
        cutoff = now - PROOF_RATE_WINDOW_SECONDS
        while _PROOF_ATTEMPTS and _PROOF_ATTEMPTS[0] <= cutoff:
            _PROOF_ATTEMPTS.popleft()
        if len(_PROOF_ATTEMPTS) >= PROOF_RATE_MAX:
            retry = max(1, int(PROOF_RATE_WINDOW_SECONDS - (now - _PROOF_ATTEMPTS[0])))
            raise ValueError(f"수동 공식확인 등록 요청이 너무 빠릅니다. 약 {retry}초 후 다시 시도하세요.")
        _PROOF_ATTEMPTS.append(now)


def _load_json(path: Path, fallback: Any) -> Any:
    try:
        if path.is_symlink() or not path.is_file():
            return fallback
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return fallback


def _remove_proof_file(relative_path: Any) -> None:
    text = str(relative_path or "").strip()
    if not text:
        return
    try:
        root = PROOF_ROOT.resolve()
        candidate = (ROOT / text).resolve()
        if candidate == root or root not in candidate.parents:
            return
        if candidate.is_symlink() or not candidate.is_file():
            return
        candidate.unlink(missing_ok=True)
    except (OSError, ValueError, RuntimeError):
        return


def _proof_public(row: dict[str, Any]) -> dict[str, Any]:
    company = str(row.get("company") or row.get("ocr_company") or "").upper()
    cert = _clean_cert(row.get("certification_id") or row.get("ocr_certification_id"))
    grade = row.get("claimed_grade") if row.get("claimed_grade") is not None else row.get("ocr_grade")
    return {
        "registration_id": row.get("registration_id"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "game": row.get("game"),
        "company": company,
        "grade": grade,
        "certification_id": cert,
        "official_result": row.get("official_result") is True,
        "status": row.get("status"),
        "verification_state": row.get("verification_state"),
        "retry_after_seconds": row.get("retry_after_seconds"),
        "official_reference_url": row.get("official_reference_url") or (lookup_url(company, cert) if company and cert else None),
        "manual_official_proof_state": row.get("manual_official_proof_state"),
        "manual_official_proof_registered": row.get("manual_official_proof_registered") is True,
        "manual_official_proof_at": row.get("manual_official_proof_at"),
        "manual_official_proof_ocr_company": row.get("manual_official_proof_ocr_company"),
        "manual_official_proof_ocr_grade": row.get("manual_official_proof_ocr_grade"),
        "manual_official_proof_ocr_certification_id": row.get("manual_official_proof_ocr_certification_id"),
        "manual_official_proof_match_mode": row.get("manual_official_proof_match_mode"),
        "manual_reference_only": row.get("manual_official_proof_registered") is True and row.get("official_result") is not True,
        "identity_complete": bool(company and cert and grade is not None),
    }


def public_status() -> dict[str, Any]:
    with manual_photo.LOCK:
        registry = manual_photo._registry()
        rows = [dict(row) for row in registry.get("registrations", []) if isinstance(row, dict)]
    public = [_proof_public(row) for row in reversed(rows[-200:])]
    return {
        "ok": True,
        "version": 3,
        "registrations": public,
        "summary": {
            "total": len(public),
            "live_official_verified": sum(row["official_result"] for row in public),
            "manual_official_proof": sum(row["manual_official_proof_registered"] for row in public),
            "cooldown_or_pending": sum(
                row.get("official_result") is not True
                and row.get("verification_state") in {
                    "deferred_by_cooldown", "completed_unverified", "processing_failed",
                    "queued", "manual_official_proof_needs_review",
                    "manual_official_proof_conflict_needs_review",
                }
                for row in public
            ),
        },
        "policy": {
            "opens_official_site_in_user_browser": True,
            "manual_screenshot_requires_official_company_and_certificate": True,
            "manual_screenshot_grade_may_use_exact_slab_ocr_fallback": True,
            "manual_screenshot_missing_ocr_does_not_quarantine_card": True,
            "manual_screenshot_sets_official_result": False,
            "manual_screenshot_trains_raw_grade_calibration": False,
            "rejected_screenshot_bytes_retained": False,
            "valid_proof_cannot_be_downgraded_by_later_bad_upload": True,
            "proof_upload_rate_limited": True,
            "proof_upload_max_per_10_minutes": PROOF_RATE_MAX,
            "later_live_official_lookup_can_promote": True,
            "access_control_bypass_used": False,
        },
    }


def _append_reference(row: dict[str, Any]) -> None:
    payload = _load_json(REFERENCE_PATH, {"schema_version": 3, "references": []})
    if not isinstance(payload, dict):
        payload = {"schema_version": 3, "references": []}
    values = payload.get("references", [])
    if not isinstance(values, list):
        values = []
    key = (str(row.get("registration_id") or ""), str(row.get("manual_official_proof_sha256") or ""))
    kept = []
    for item in values:
        if not isinstance(item, dict):
            continue
        item_key = (str(item.get("registration_id") or ""), str(item.get("proof_sha256") or ""))
        if item_key != key:
            kept.append(item)
    kept.append({
        "registration_id": row.get("registration_id"),
        "company": row.get("company"),
        "certification_id": row.get("certification_id"),
        "grade": row.get("claimed_grade"),
        "game": row.get("game"),
        "official_reference_url": row.get("official_reference_url"),
        "proof_sha256": row.get("manual_official_proof_sha256"),
        "proof_path": row.get("manual_official_proof_path"),
        "verified_at": row.get("manual_official_proof_at"),
        "verification_method": row.get("manual_official_proof_match_mode") or "user_browser_official_page_reference",
        "official_result": False,
        "manual_official_proof_matched": True,
        "learning_eligibility": "reference_only_pending_live_official_verification",
        "raw_grade_calibration_eligible": False,
    })
    payload.update({
        "schema_version": 3,
        "updated_at": _now(),
        "references": kept[-MAX_REFERENCES:],
        "policy": {
            "manual_proof_is_live_official_truth": False,
            "raw_calibration_allowed": False,
            "later_live_lookup_required_for_official_result": True,
        },
    })
    atomic_write_json(REFERENCE_PATH, payload, suffix=".manual-official-proof.tmp")


def _text_upper(text: Any) -> str:
    return " ".join(str(text or "").upper().replace("\x00", " ").split())


def _cert_in_text(text: Any, cert: str) -> bool:
    cert = _clean_cert(cert)
    if not cert:
        return False
    compact = re.sub(r"[^A-Z0-9]", "", _text_upper(text))
    if cert in compact:
        return True
    if cert.isdigit() and cert in compact.translate(_DIGIT_CONFUSION):
        return True
    return False


def _company_in_text(text: Any, company: str) -> bool:
    upper = _text_upper(text)
    compact = re.sub(r"[^A-Z0-9.]", "", upper)
    return any(hint in upper or hint in compact for hint in _COMPANY_HINTS.get(company, (company,)))


def _explicit_grade_candidates(text: Any, company: str) -> set[float]:
    upper = _text_upper(text)
    found: set[float] = set()
    patterns = [
        r"\bGRADE\s*[:#-]?\s*(10|[1-9](?:\.5)?)\b",
        r"\b(?:GEM\s*MT|GEM\s*MINT|PRISTINE|MINT|NM[\s-]*MT|NEAR\s*MINT)\s*(10|[1-9](?:\.5)?)\b",
        r"\b(10|[1-9](?:\.5)?)\s*(?:GEM\s*MT|GEM\s*MINT|PRISTINE|MINT|NM[\s-]*MT|NEAR\s*MINT)\b",
    ]
    for pattern in patterns:
        for value in re.findall(pattern, upper):
            grade = _grade(value)
            if grade is not None:
                found.add(float(grade))
    if company == "PSA":
        psa_words = {
            10.0: (r"\bGEM\s*MT\s*10\b",),
            9.0: (r"\bMINT\s*9\b",),
            8.0: (r"\bNM[\s-]*MT\s*8\b",),
            7.0: (r"\bNM\s*7\b",),
            6.0: (r"\bEX[\s-]*MT\s*6\b",),
            5.0: (r"\bEX\s*5\b",),
        }
        for grade, pats in psa_words.items():
            if any(re.search(pat, upper) for pat in pats):
                found.add(grade)
    return found


def _slab_identity_exact(row: dict[str, Any], company: str, cert: str, expected_grade: float) -> bool:
    ocr_company = str(row.get("ocr_company") or "").upper()
    ocr_cert = _clean_cert(row.get("ocr_certification_id"))
    ocr_grade = _grade(row.get("ocr_grade"))
    if ocr_company == company and ocr_cert == cert and ocr_grade is not None and abs(ocr_grade - expected_grade) < 1e-9:
        return True
    image_path = str(row.get("image_path") or "").strip()
    if image_path:
        try:
            _, _, _, evidence = manual_photo._ocr_image(ROOT / image_path)
            retry_company = str(evidence.get("company") or "").upper()
            retry_cert = _clean_cert(evidence.get("certification_id"))
            retry_grade = _grade(evidence.get("grade"))
            return (
                retry_company == company
                and retry_cert == cert
                and retry_grade is not None
                and abs(retry_grade - expected_grade) < 1e-9
            )
        except (OSError, ValueError, TypeError):
            return False
    return False


def _match_proof(*, row: dict[str, Any], text: str, evidence: dict[str, Any], company: str, cert: str, expected_grade: float) -> dict[str, Any]:
    proof_company = str(evidence.get("company") or "").upper()
    if proof_company not in manual_photo.COMPANIES:
        proof_company = ""
    proof_cert = _clean_cert(evidence.get("certification_id"))
    proof_grade = _grade(evidence.get("grade"))

    company_text_match = _company_in_text(text, company)
    company_match = proof_company == company or company_text_match
    cert_text_match = _cert_in_text(text, cert)
    cert_match = proof_cert == cert or cert_text_match

    explicit_grades = _explicit_grade_candidates(text, company)
    grade_match = (
        proof_grade is not None and abs(proof_grade - expected_grade) < 1e-9
    ) or any(abs(value - expected_grade) < 1e-9 for value in explicit_grades)

    explicit_conflicts: list[str] = []
    if proof_company and proof_company != company and not company_text_match:
        explicit_conflicts.append("official_proof_company_mismatch")
    if proof_cert and proof_cert != cert and not cert_text_match:
        explicit_conflicts.append("official_proof_certification_mismatch")
    if explicit_grades and not any(abs(value - expected_grade) < 1e-9 for value in explicit_grades):
        explicit_conflicts.append("official_proof_grade_mismatch")

    slab_fallback = False
    match_mode = None
    if company_match and cert_match and grade_match and not explicit_conflicts:
        match_mode = "official_page_company_cert_grade_ocr"
    elif company_match and cert_match and not explicit_conflicts:
        slab_fallback = _slab_identity_exact(row, company, cert, expected_grade)
        if slab_fallback:
            match_mode = "official_page_company_cert_plus_exact_slab_ocr_grade"

    missing: list[str] = []
    if not company_match:
        missing.append("company")
    if not cert_match:
        missing.append("certification_id")
    if not grade_match and not slab_fallback:
        missing.append("grade")

    return {
        "matched": match_mode is not None,
        "match_mode": match_mode,
        "proof_company": proof_company,
        "proof_cert": proof_cert,
        "proof_grade": proof_grade,
        "company_match": company_match,
        "cert_match": cert_match,
        "grade_match": grade_match,
        "slab_grade_fallback": slab_fallback,
        "explicit_grade_candidates": sorted(explicit_grades),
        "conflicts": explicit_conflicts,
        "missing": missing,
    }


def _proof_reason_cleanup(reasons: set[str]) -> set[str]:
    return {
        reason for reason in reasons
        if not (
            reason.startswith("official_proof_")
            or reason in {"manual_official_proof_needs_review", "manual_official_proof_ocr_incomplete"}
        )
    }


def submit(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("수동 공식확인 자료 형식 오류")
    registration_id = str(payload.get("registration_id") or "").strip()[:80]
    if not _REGISTRATION_RE.fullmatch(registration_id):
        raise ValueError("수동등록 번호 형식 오류")
    _claim_proof_upload()

    with manual_photo.LOCK:
        registry = manual_photo._registry()
        _, row = manual_photo._find_row(registry, registration_id)
        row = dict(row)

    company = str(row.get("company") or row.get("ocr_company") or "").upper()
    cert = _clean_cert(row.get("certification_id") or row.get("ocr_certification_id"))
    expected_grade = _grade(row.get("claimed_grade") if row.get("claimed_grade") is not None else row.get("ocr_grade"))
    if company not in manual_photo.COMPANIES or len(cert) < 6 or expected_grade is None:
        raise ValueError("먼저 등급사·등급·인증번호를 확정한 뒤 공식확인 화면을 등록하세요.")
    if row.get("official_result") is True:
        return {"ok": True, "accepted": True, "already_live_verified": True, "registration": _proof_public(row)}

    image, extension, width, height = manual_photo._decode_image(payload.get("proof_image_data_url"))
    digest = hashlib.sha256(image).hexdigest()
    if row.get("manual_official_proof_registered") is True and row.get("manual_official_proof_sha256") == digest:
        return {
            "ok": True, "accepted": True, "duplicate": True,
            "registration": _proof_public(row),
            "policy": {"reference_only": True, "official_result": False, "raw_grade_calibration": False},
        }

    folder = PROOF_ROOT / datetime.now(timezone.utc).strftime("%Y%m")
    target = folder / f"{registration_id}-{digest[:12]}{extension}"
    atomic_write_bytes(target, image, suffix=".official-proof.tmp")

    text, ocr_error, diagnostics, evidence = manual_photo._ocr_image(target)
    match = _match_proof(
        row=row, text=text, evidence=evidence if isinstance(evidence, dict) else {},
        company=company, cert=cert, expected_grade=expected_grade,
    )
    matched = bool(match["matched"])
    now = _now()
    existing_matched = row.get("manual_official_proof_registered") is True

    proof_payload = {
        "company": match["proof_company"] or None,
        "grade": match["proof_grade"],
        "certification_id": match["proof_cert"] or None,
        "ocr_error": ocr_error,
        "conflicts": match["conflicts"],
        "missing": match["missing"],
        "match_mode": match["match_mode"],
        "company_match": match["company_match"],
        "certification_match": match["cert_match"],
        "grade_match": match["grade_match"],
        "slab_grade_fallback": match["slab_grade_fallback"],
    }

    if not matched and existing_matched:
        _remove_proof_file(target.relative_to(ROOT).as_posix())
        return {
            "ok": True, "accepted": False,
            "reason": "official_page_screenshot_needs_review_existing_valid_proof_preserved",
            "registration": _proof_public(row),
            "proof": proof_payload,
            "policy": {"reference_only": True, "official_result": False, "raw_grade_calibration": False},
        }

    old_path = ""
    with manual_photo.LOCK:
        registry = manual_photo._registry()
        index, current = manual_photo._find_row(registry, registration_id)
        old_path = str(current.get("manual_official_proof_path") or "")
        proof_state = "matched" if matched else (
            "conflict_needs_review" if match["conflicts"] else "ocr_incomplete_needs_review"
        )
        current.update({
            "updated_at": now,
            "manual_official_proof_state": proof_state,
            "manual_official_proof_registered": matched,
            "manual_official_proof_at": now,
            "manual_official_proof_path": target.relative_to(ROOT).as_posix() if matched else None,
            "manual_official_proof_sha256": digest,
            "manual_official_proof_width": width,
            "manual_official_proof_height": height,
            "manual_official_proof_ocr_text": str(text or "")[:1800],
            "manual_official_proof_ocr_error": ocr_error,
            "manual_official_proof_ocr_diagnostics": diagnostics if isinstance(diagnostics, dict) else {},
            "manual_official_proof_ocr_company": match["proof_company"] or None,
            "manual_official_proof_ocr_grade": match["proof_grade"],
            "manual_official_proof_ocr_certification_id": match["proof_cert"] or None,
            "manual_official_proof_match_mode": match["match_mode"],
            "manual_official_proof_missing_fields": match["missing"],
            "manual_official_proof_conflicts": match["conflicts"],
            "official_reference_url": current.get("official_reference_url") or lookup_url(company, cert),
            "official_result": False,
            "training_eligible": False,
            "raw_grade_calibration_eligible": False,
        })
        reasons = _proof_reason_cleanup(set(current.get("quarantine_reasons") or []))
        if matched:
            reasons.discard("official_lookup_not_confirmed")
            reasons.add("manual_official_page_proof_only")
            reasons.add("live_official_lookup_pending")
            current.update({
                "status": "manual_official_reference",
                "verification_state": "manual_official_proof_matched",
                "learning_eligibility": "reference_only_pending_live_official_verification",
            })
        else:
            reasons.add("official_lookup_not_confirmed")
            reasons.add("manual_official_proof_needs_review")
            underlying_conflict = any(
                reason in {
                    "ocr_company_conflict", "ocr_certification_conflict", "ocr_grade_conflict",
                    "persisted_official_grade_conflict", "persisted_official_grade_invalid",
                }
                for reason in reasons
            )
            current.update({
                "status": "quarantine" if underlying_conflict else "pending_official_verification",
                "verification_state": (
                    "manual_official_proof_conflict_needs_review"
                    if match["conflicts"] else "manual_official_proof_needs_review"
                ),
                "learning_eligibility": (
                    "quarantine_only_until_identity_resolved"
                    if underlying_conflict else "quarantine_only_until_official_match"
                ),
            })
        current["quarantine_reasons"] = sorted(reasons)
        registry["registrations"][index] = current
        manual_photo._save_registry(registry)

    new_path = target.relative_to(ROOT).as_posix()
    if matched:
        _append_reference(current)
        if old_path and old_path != new_path:
            _remove_proof_file(old_path)
    else:
        _remove_proof_file(new_path)

    reason = None if matched else (
        "official_page_screenshot_identity_conflict_needs_review"
        if match["conflicts"] else "official_page_screenshot_ocr_incomplete"
    )
    return {
        "ok": True,
        "accepted": matched,
        "reason": reason,
        "registration": _proof_public(current),
        "proof": proof_payload,
        "policy": {
            "reference_only": True,
            "official_result": False,
            "raw_grade_calibration": False,
            "rejected_screenshot_bytes_retained": False,
            "ocr_miss_does_not_quarantine_card": True,
            "later_live_lookup_required": True,
        },
    }
