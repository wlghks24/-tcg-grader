#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Manual official verification for saved graded-photo candidates.

Only candidates with resolved company/certificate/grade are exposed. The user
opens the official grader page in their own browser and uploads a screenshot.
The screenshot must OCR-match company + certificate + grade before the candidate
is promoted to an official reference-learning row.

A separate negative-proof path is provided when the official grader page says
that no record exists.  Negative proof can only remove an *unverified* candidate,
requires an exact certification-number confirmation, archives the screenshot and
never creates grading truth or RAW calibration data.

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
import shutil
import subprocess
import tempfile
from typing import Any

import graded_photo_multi_source as gp
import graded_photo_existing_revalidation_v159 as existing
import manual_graded_photo_registration as manual_photo
import manual_official_proof as manual_proof
from grading_cert_verifier import lookup_url
from safe_runtime import atomic_write_bytes

ENGINE = "v171-pending-official-candidate-korean-negative-proof-ocr"
ROOT = Path(__file__).resolve().parent
PROOF_ROOT = ROOT / "GRADE_TRAINING_INBOX" / "pending_official_candidate_proof"
NEGATIVE_PROOF_ROOT = ROOT / "GRADE_TRAINING_INBOX" / "pending_official_candidate_negative_proof"
REJECTION_LOG = ROOT / "pending_official_candidate_rejections.json"
MAX_PROOF_BYTES = 8_000_000
_DATA_URL_RE = re.compile(r"^data:(image/(?:jpeg|png));base64,([A-Za-z0-9+/=\r\n]+)$", re.I)
_NEGATIVE_PATTERNS = (
    re.compile(r"검색\s*(?:된)?\s*(?:기록|결과)\s*(?:이|가)?\s*없(?:습니다|음)", re.I),
    re.compile(r"조회\s*(?:된)?\s*(?:기록|결과)\s*(?:이|가)?\s*없(?:습니다|음)", re.I),
    re.compile(r"(?:일치하는|해당)\s*(?:기록|결과|인증번호)\s*(?:이|가)?\s*없(?:습니다|음)", re.I),
    re.compile(r"no\s+records?\s+(?:were\s+)?found", re.I),
    re.compile(r"no\s+results?\s+(?:were\s+)?found", re.I),
    re.compile(r"(?:certificate|certification|cert(?:ificate)?\s*number)\s+(?:was\s+)?not\s+found", re.I),
    re.compile(r"(?:検索|照会).*?(?:結果|記録).*?(?:ありません|見つかりません)", re.I),
    re.compile(r"(?:查無|找不到|沒有).*?(?:紀錄|記錄|結果|認證|认证)", re.I),
)
_SITE_ERROR_PATTERNS = (
    re.compile(r"application\s+error", re.I),
    re.compile(r"server[-\s]*side\s+exception", re.I),
    re.compile(r"internal\s+server\s+error", re.I),
    re.compile(r"service\s+unavailable", re.I),
    re.compile(r"\bdigest\s*:\s*\d+", re.I),
    re.compile(r"서버\s*(?:오류|에러)", re.I),
)
_COMPANY_BRANDS = {
    "PSA": ("PSA",),
    "BGS": ("BGS", "BECKETT", "비그스"),
    "CGC": ("CGC",),
    "TAG": ("TAG",),
    "BRG": ("BRG",),
}


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
    rejected = _rejected_cert_keys()
    for row in rows:
        if not isinstance(row, dict) or row.get("official_result") is True:
            continue
        company = str(row.get("company") or "").upper().strip()
        cert = gp.normalize_cert(row.get("certification_id"))
        grade = _grade(row.get("grade"))
        if (company, cert) in rejected:
            continue
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


def _rejection_payload() -> dict[str, Any]:
    value = gp._load(REJECTION_LOG, {})
    rows = value.get("rejections", []) if isinstance(value, dict) else []
    return {
        "schema_version": 1,
        "updated_at": value.get("updated_at") if isinstance(value, dict) else None,
        "rejections": [dict(row) for row in rows if isinstance(row, dict)][-5000:],
    }


def _rejected_cert_keys() -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for row in _rejection_payload()["rejections"]:
        company = str(row.get("company") or "").upper().strip()
        cert = gp.normalize_cert(row.get("certification_id"))
        if company in gp.COMPANIES and cert and row.get("reason") == "official_record_not_found_user_confirmed":
            out.add((company, cert))
    return out


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
            "manual_no_record_can_remove_unverified_candidate": True,
            "negative_proof_exact_cert_confirmation_required": True,
            "negative_proof_is_archived": True,
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


def _find_unverified_target(rows: list[dict[str, Any]], candidate_id: str) -> dict[str, Any]:
    matches = [row for row in rows if row.get("official_result") is not True and _candidate_id(row) == candidate_id]
    if not matches:
        raise ValueError("공식검증 미완료 후보를 찾지 못했습니다. 화면을 새로고침하세요.")
    return matches[0]


def _negative_ocr(text: Any, evidence: Any, company: str) -> dict[str, Any]:
    raw = " ".join(str(text or "").replace("\x00", " ").split())
    negative = any(pattern.search(raw) for pattern in _NEGATIVE_PATTERNS)
    site_error = any(pattern.search(raw) for pattern in _SITE_ERROR_PATTERNS)
    upper = raw.upper()
    brands = _COMPANY_BRANDS.get(company, (company,))
    brand = any(str(token).upper() in upper for token in brands if token)
    evidence_company = str((evidence or {}).get("company") or "").upper() if isinstance(evidence, dict) else ""
    if evidence_company == company:
        brand = True
    return {
        "negative_text_detected": negative,
        "company_brand_detected": brand,
        "site_error_detected": site_error,
        "ocr_text": raw[:1800],
    }


def _tesseract_languages() -> set[str]:
    binary = shutil.which("tesseract")
    if not binary:
        return set()
    try:
        run = subprocess.run(
            [binary, "--list-langs"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=8, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    raw = "\n".join((run.stdout or "", run.stderr or ""))
    return {
        line.strip().lower() for line in raw.splitlines()
        if line.strip() and not line.lower().startswith("list of available languages")
    }


def _multilang_negative_ocr(image_path: Path) -> tuple[str, str | None]:
    """OCR browser proof with Korean support without weakening delete policy."""
    binary = shutil.which("tesseract")
    if not binary:
        return "", "tesseract_not_installed"
    languages = _tesseract_languages()
    if "kor" not in languages:
        return "", "korean_tessdata_missing"
    language = "kor+eng" if "eng" in languages else "kor"
    try:
        from PIL import Image, ImageOps
        with Image.open(image_path) as opened:
            source = ImageOps.exif_transpose(opened).convert("RGB")
        width, height = source.size
        regions = (
            ("full", source),
            ("upper72", source.crop((0, 0, width, max(1, int(height * 0.72))))),
            ("upper45", source.crop((0, 0, width, max(1, int(height * 0.45))))),
        )
        chunks: list[str] = []
        with tempfile.TemporaryDirectory(prefix="tcg-negative-proof-") as directory:
            for name, region in regions:
                gray = ImageOps.autocontrast(ImageOps.grayscale(region))
                target_w = max(1400, min(2400, gray.width * 2))
                if gray.width != target_w:
                    ratio = target_w / max(1, gray.width)
                    gray = gray.resize((target_w, max(300, int(gray.height * ratio))))
                file_path = Path(directory) / f"{name}.png"
                gray.save(file_path, format="PNG")
                for psm in (6, 11):
                    run = subprocess.run(
                        [binary, str(file_path), "stdout", "--psm", str(psm), "-l", language],
                        capture_output=True, text=True, encoding="utf-8", errors="replace",
                        timeout=18, check=False,
                    )
                    if run.returncode == 0 and run.stdout.strip():
                        chunks.append(run.stdout.strip())
        text = "\n".join(dict.fromkeys(chunks))
        return text[:8000], None if text else "ocr_empty"
    except ImportError:
        return "", "pillow_not_installed"
    except (OSError, ValueError, subprocess.SubprocessError):
        return "", "multilang_ocr_failed"


def _save_candidate_payload(payload: dict[str, Any], rows: list[dict[str, Any]], *, promoted_delta: int = 0,
                            rejected_delta: int = 0, timestamp_key: str | None = None) -> dict[str, Any]:
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
        "manual_official_candidate_promoted": int(summary.get("manual_official_candidate_promoted", 0) or 0) + promoted_delta,
        "manual_official_candidate_rejected_not_found": int(summary.get("manual_official_candidate_rejected_not_found", 0) or 0) + rejected_delta,
    })
    current = dict(payload) if isinstance(payload, dict) else {}
    current["records"] = rows
    current["summary"] = summary
    if timestamp_key:
        current[timestamp_key] = _now()
    gp.atomic_write_json(gp.OUT, current, suffix=".manual-official-candidate.tmp")
    return summary


def _submit_not_found(incoming: dict[str, Any]) -> dict[str, Any]:
    candidate_id = str(incoming.get("candidate_id") or "").strip()[:64]
    if not candidate_id:
        raise ValueError("후보 식별정보가 없습니다.")
    if incoming.get("confirm_no_record") is not True:
        raise ValueError("공식사이트에서 검색 기록이 없음을 확인해야 삭제할 수 있습니다.")
    image, extension = _decode_proof(incoming.get("proof_image"))

    payload = gp._load(gp.OUT, {})
    rows = [dict(row) for row in payload.get("records", []) if isinstance(row, dict)] if isinstance(payload, dict) else []
    target = _find_unverified_target(rows, candidate_id)
    company = str(target.get("company") or "").upper().strip()
    cert = gp.normalize_cert(target.get("certification_id"))
    grade = _grade(target.get("grade"))
    confirmation = gp.normalize_cert(incoming.get("certification_id_confirmation"))
    if company not in gp.COMPANIES or not cert or grade is None:
        raise ValueError("등급사·인증번호·등급이 모두 확인된 후보만 정리할 수 있습니다.")
    if confirmation != cert:
        raise ValueError(f"삭제 확인 인증번호가 일치하지 않습니다. {cert}를 정확히 입력하세요.")

    digest = hashlib.sha256(image).hexdigest()
    folder = NEGATIVE_PROOF_ROOT / company
    proof_path = folder / f"{cert}-{digest[:12]}{extension}"
    atomic_write_bytes(proof_path, image, suffix=".pending-official-negative.tmp")

    text = ""
    ocr_error = None
    evidence: dict[str, Any] = {}
    try:
        text, ocr_error, _diagnostics, raw_evidence = manual_photo._ocr_image(proof_path)
        evidence = raw_evidence if isinstance(raw_evidence, dict) else {}
    except Exception as exc:
        ocr_error = type(exc).__name__
    signal = _negative_ocr(text, evidence, company)
    multilang_error = None
    if (not signal.get("site_error_detected")
            and (not signal.get("negative_text_detected") or not signal.get("company_brand_detected"))):
        extra_text, multilang_error = _multilang_negative_ocr(proof_path)
        if extra_text:
            text = "\n".join(part for part in (text, extra_text) if part)
            signal = _negative_ocr(text, evidence, company)
    if signal.get("site_error_detected"):
        proof_path.unlink(missing_ok=True)
        raise ValueError("공식사이트 서버 오류 화면은 '조회결과 없음' 증거가 아닙니다. 후보는 유지됩니다. 잠시 후 공식사이트에서 다시 확인하세요.")
    if not signal.get("negative_text_detected"):
        proof_path.unlink(missing_ok=True)
        if multilang_error == "korean_tessdata_missing":
            raise ValueError("한글 공식조회 결과를 읽기 위한 OCR 언어자료가 없습니다. Termux에서 pkg install tesseract-data-kor -y 실행 후 다시 선택하세요.")
        raise ValueError("공식사이트에 '조회 결과 없음/인증번호 없음' 문구가 확인된 화면만 후보삭제에 사용할 수 있습니다.")
    if not signal.get("company_brand_detected"):
        proof_path.unlink(missing_ok=True)
        raise ValueError("공식 등급사 화면임을 확인할 수 없습니다. 등급사 로고/명칭과 조회결과 없음 문구가 함께 보이도록 캡처하세요.")

    rejected_at = _now()
    rejection = {
        "rejected_at": rejected_at,
        "candidate_id": candidate_id,
        "company": company,
        "game": str(target.get("game") or "unknown").lower(),
        "grade": grade,
        "certification_id": cert,
        "source": str(target.get("source") or target.get("source_name") or "공개후보")[:120],
        "title": str(target.get("title") or "")[:220],
        "reason": "official_record_not_found_user_confirmed",
        "verification_method": "user_browser_official_page_no_record_screenshot_exact_cert_confirmation",
        "official_reference_url": lookup_url(company, cert),
        "negative_proof_path": str(proof_path.relative_to(ROOT)),
        "negative_proof_sha256": digest,
        "manual_cert_confirmation_exact": True,
        "ocr_negative_text_detected": signal["negative_text_detected"],
        "ocr_company_brand_detected": signal["company_brand_detected"],
        "ocr_text": signal["ocr_text"],
        "ocr_error": str(ocr_error or "")[:180] or None,
        "raw_grade_calibration_eligible": False,
        "learning_eligible": False,
    }
    rejection_payload = _rejection_payload()
    rejection_payload["updated_at"] = rejected_at
    rejection_payload["rejections"].append(rejection)
    rejection_payload["rejections"] = rejection_payload["rejections"][-5000:]
    gp.atomic_write_json(REJECTION_LOG, rejection_payload, suffix=".official-negative-proof.tmp")

    removed = 0
    remaining: list[dict[str, Any]] = []
    for row in rows:
        if row.get("official_result") is True or _candidate_id(row) != candidate_id:
            remaining.append(row)
            continue
        removed += 1
    if removed < 1:
        raise ValueError("삭제할 미검증 후보가 없습니다.")
    summary = _save_candidate_payload(payload, remaining, rejected_delta=removed,
                                      timestamp_key="manual_official_candidate_last_rejected_at")
    try:
        gp.record_official_feedback(remaining)
    except Exception:
        pass
    return {
        "ok": True,
        "accepted": True,
        "deleted": True,
        "candidate_id": candidate_id,
        "company": company,
        "certification_id": cert,
        "grade": grade,
        "deleted_rows": removed,
        "reason": "official_record_not_found_user_confirmed",
        "negative_proof_archived": True,
        "ocr_negative_text_detected": signal["negative_text_detected"],
        "ocr_company_brand_detected": signal["company_brand_detected"],
        "remaining_candidates": int(summary.get("total_candidates", len(remaining)) or 0),
        "raw_grade_calibration_eligible": False,
    }


def submit(incoming: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(incoming, dict):
        raise ValueError("등록자료 형식 오류")
    if str(incoming.get("action") or "").strip().lower() == "official_not_found":
        return _submit_not_found(incoming)

    candidate_id = str(incoming.get("candidate_id") or "").strip()[:64]
    if not candidate_id:
        raise ValueError("후보 식별정보가 없습니다.")
    image, extension = _decode_proof(incoming.get("proof_image"))

    payload = gp._load(gp.OUT, {})
    rows = [dict(row) for row in payload.get("records", []) if isinstance(row, dict)] if isinstance(payload, dict) else []
    target = _find_unverified_target(rows, candidate_id)
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
        text, ocr_error, diagnostics, evidence = manual_proof._ocr_official_page(
            proof_path, expected_company=company, expected_cert=cert,
        )
        match = manual_proof._match_proof(
            row=target, text=text, evidence=evidence if isinstance(evidence, dict) else {},
            company=company, cert=cert, expected_grade=float(grade),
        )
        if not bool(match.get("matched")):
            proof_path.unlink(missing_ok=True)
            return {
                "ok": True,
                "accepted": False,
                "candidate_id": candidate_id,
                "error": "공식 조회 화면 일치검사 실패: " + ", ".join(match.get("missing") or match.get("explicit_conflicts") or ["OCR 판독 불충분"]),
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

    summary = _save_candidate_payload(payload, rows, promoted_delta=promoted,
                                      timestamp_key="manual_official_candidate_last_verified_at")
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
