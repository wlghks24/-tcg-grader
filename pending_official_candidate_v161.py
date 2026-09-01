#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Manual official verification for saved graded-photo candidates.

Only candidates with resolved company/certificate/grade are exposed. The user
opens the official grader page in their own browser and uploads a screenshot.
The screenshot must OCR-match company + certificate + grade before the candidate
is promoted to an official reference-learning row.

This path is intentionally separate from live automated lookup/cooldown. It does
not bypass grader-site access controls and it never makes a candidate eligible
for RAW grade calibration by itself.
"""
from __future__ import annotations

from datetime import datetime, timezone
import base64
import hashlib
import math
from pathlib import Path
import re
from typing import Any

import graded_photo_multi_source as gp
import graded_photo_existing_revalidation_v159 as existing
import manual_graded_photo_registration as manual_photo
import manual_official_proof as manual_proof
from grading_cert_verifier import lookup_url
from safe_runtime import atomic_write_bytes

ENGINE = "v161-pending-official-candidate-manual-verification"
ROOT = Path(__file__).resolve().parent
PROOF_ROOT = ROOT / "GRADE_TRAINING_INBOX" / "pending_official_candidate_proof"
MAX_PROOF_BYTES = 8_000_000
_DATA_URL_RE = re.compile(r"^data:(image/(?:jpeg|png));base64,([A-Za-z0-9+/=\r\n]+)$", re.I)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _grade(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or not 1 <= number <= 10:
        return None
    return number


def _candidate_id(row: dict[str, Any]) -> str:
    company = str(row.get("company") or "").upper().strip()
    cert = gp.normalize_cert(row.get("certification_id"))
    grade = _grade(row.get("grade"))
    source = str(row.get("url") or row.get("image_url") or row.get("title") or "")
    raw = f"{company}|{cert}|{grade}|{source}".encode("utf-8", "ignore")
    return hashlib.sha256(raw).hexdigest()[:24]


def _pending_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("records", []) if isinstance(payload, dict) else []
    out: list[dict[str, Any]] = []
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict) or row.get("official_result") is True:
            continue
        company = str(row.get("company") or "").upper().strip()
        cert = gp.normalize_cert(row.get("certification_id"))
        grade = _grade(row.get("grade"))
        if company not in gp.COMPANIES or not cert or grade is None:
            continue
        reasons = {str(v) for v in (row.get("quarantine_reasons") or []) if v}
        status = str(row.get("status") or "")
        if "official_verification_missing" not in reasons and status != "quarantine_candidate":
            continue
        out.append(row)
    return out


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    company = str(row.get("company") or "").upper().strip()
    cert = gp.normalize_cert(row.get("certification_id"))
    grade = _grade(row.get("grade"))
    return {
        "candidate_id": _candidate_id(row),
        "company": company,
        "game": str(row.get("game") or "unknown").lower(),
        "grade": grade,
        "certification_id": cert,
        "source": str(row.get("source") or row.get("source_name") or "공개후보")[:80],
        "title": str(row.get("title") or "")[:180],
        "official_reference_url": lookup_url(company, cert),
        "status": "official_verification_pending",
    }


def public_status() -> dict[str, Any]:
    payload = gp._load(gp.OUT, {})
    rows = _pending_rows(payload)
    public = [_public_row(row) for row in rows[:30]]
    return {
        "ok": True,
        "engine": ENGINE,
        "pending_count": len(rows),
        "candidates": public,
        "policy": {
            "user_opens_official_site": True,
            "screenshot_required": True,
            "exact_company_certificate_grade_ocr_required": True,
            "manual_exact_match_can_promote_reference": True,
            "raw_grade_calibration_eligible": False,
            "access_control_bypass_used": False,
        },
    }


def _decode_proof(value: Any) -> tuple[bytes, str]:
    match = _DATA_URL_RE.match(str(value or "").strip())
    if not match:
        raise ValueError("공식 조회 결과 화면은 JPG 또는 PNG로 선택하세요.")
    try:
        data = base64.b64decode(match.group(2), validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("공식 조회 화면 데이터가 올바르지 않습니다.") from exc
    if not data or len(data) > MAX_PROOF_BYTES:
        raise ValueError("공식 조회 화면은 8MB 이하만 등록할 수 있습니다.")
    mime = match.group(1).lower()
    if mime == "image/jpeg" and not data.startswith(b"\xff\xd8\xff"):
        raise ValueError("JPG 파일 형식이 올바르지 않습니다.")
    if mime == "image/png" and not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("PNG 파일 형식이 올바르지 않습니다.")
    return data, ".jpg" if mime == "image/jpeg" else ".png"


def submit(incoming: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(incoming, dict):
        raise ValueError("등록자료 형식 오류")
    candidate_id = str(incoming.get("candidate_id") or "").strip()[:64]
    if not candidate_id:
        raise ValueError("후보 식별정보가 없습니다.")
    image, extension = _decode_proof(incoming.get("proof_image"))

    payload = gp._load(gp.OUT, {})
    rows = [dict(row) for row in payload.get("records", []) if isinstance(row, dict)] if isinstance(payload, dict) else []
    matches = [row for row in rows if row.get("official_result") is not True and _candidate_id(row) == candidate_id]
    if not matches:
        raise ValueError("공식검증 미완료 후보를 찾지 못했습니다. 화면을 새로고침하세요.")
    target = matches[0]
    company = str(target.get("company") or "").upper().strip()
    cert = gp.normalize_cert(target.get("certification_id"))
    grade = _grade(target.get("grade"))
    if company not in gp.COMPANIES or not cert or grade is None:
        raise ValueError("등급사·인증번호·등급이 모두 확인된 후보만 수동 공식검증할 수 있습니다.")

    digest = hashlib.sha256(image).hexdigest()
    folder = PROOF_ROOT / company
    proof_path = folder / f"{cert}-{digest[:12]}{extension}"
    atomic_write_bytes(proof_path, image, suffix=".pending-official.tmp")
    try:
        text, ocr_error, diagnostics, evidence = manual_photo._ocr_image(proof_path)
        match = manual_proof._match_proof(
            row={}, text=text, evidence=evidence if isinstance(evidence, dict) else {},
            company=company, cert=cert, expected_grade=float(grade),
        )
        if not bool(match.get("matched")):
            proof_path.unlink(missing_ok=True)
            return {
                "ok": True,
                "accepted": False,
                "candidate_id": candidate_id,
                "error": "공식 조회 화면에서 등급사·인증번호·등급의 정확한 일치를 확인하지 못했습니다.",
                "ocr_error": str(ocr_error or "")[:160] or None,
                "match": {
                    "company_match": bool(match.get("company_match")),
                    "cert_match": bool(match.get("cert_match")),
                    "grade_match": bool(match.get("grade_match")),
                    "conflicts": list(match.get("explicit_conflicts") or []),
                },
            }
    except Exception:
        proof_path.unlink(missing_ok=True)
        raise

    rel_path = str(proof_path.relative_to(ROOT))
    promoted = 0
    verified_at = _now()
    for row in rows:
        if row.get("official_result") is True or _candidate_id(row) != candidate_id:
            continue
        row.update({
            "official_result": True,
            "verification_state": "manual_official_verified",
            "official_verification_method": "user_browser_official_page_exact_screenshot",
            "official_verification_source": "manual_official_candidate_v161",
            "official_reference_url": lookup_url(company, cert),
            "official_verified_at": verified_at,
            "manual_official_candidate_proof_path": rel_path,
            "manual_official_candidate_proof_sha256": digest,
            "manual_official_candidate_proof_match_mode": match.get("match_mode"),
            "manual_official_candidate_proof_ocr_company": (evidence or {}).get("company") if isinstance(evidence, dict) else None,
            "manual_official_candidate_proof_ocr_certification_id": (evidence or {}).get("certification_id") if isinstance(evidence, dict) else None,
            "manual_official_candidate_proof_ocr_grade": (evidence or {}).get("grade") if isinstance(evidence, dict) else None,
            "manual_official_candidate_verified": True,
            "raw_grade_calibration_eligible": False,
        })
        promoted += 1

    existing._apply_current_disposition(rows)
    reference_learning = gp._save_reference_learning(rows)
    reference_summary = reference_learning.get("summary", {}) if isinstance(reference_learning, dict) else {}
    summary = dict(payload.get("summary") or {}) if isinstance(payload, dict) else {}
    verified_count = sum(row.get("official_result") is True and not row.get("evidence_conflicts") for row in rows)
    summary.update({
        "total_candidates": len(rows),
        "verified_references": verified_count,
        "reference_learning_count": int(reference_summary.get("reference_learning_count", 0) or 0),
        "quarantined": len(rows) - verified_count,
        "manual_official_candidate_promoted": int(summary.get("manual_official_candidate_promoted", 0) or 0) + promoted,
    })
    current = dict(payload) if isinstance(payload, dict) else {}
    current["records"] = rows
    current["summary"] = summary
    current["manual_official_candidate_last_verified_at"] = verified_at
    gp.atomic_write_json(gp.OUT, current, suffix=".manual-official-candidate.tmp")
    try:
        gp.record_official_feedback(rows)
    except Exception:
        pass
    return {
        "ok": True,
        "accepted": True,
        "candidate_id": candidate_id,
        "company": company,
        "certification_id": cert,
        "grade": grade,
        "promoted_rows": promoted,
        "reference_learning_count": summary["reference_learning_count"],
        "raw_grade_calibration_eligible": False,
        "verification_method": "user_browser_official_page_exact_screenshot",
    }


if __name__ == "__main__":
    import json
    print(json.dumps(public_status(), ensure_ascii=False, indent=2))
