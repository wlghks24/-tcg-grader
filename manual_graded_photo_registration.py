#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Quarantine-first manual graded-photo registration.

Manual labels are user claims, never grade truth. A photo becomes a reference
only after the official company page confirms company + cert + grade. It never
enters raw-card calibration because that would leak the slab label into grading.
"""
from __future__ import annotations

import base64
import binascii
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import secrets
import struct
import threading
from typing import Any

from grading_cert_verifier import lookup_url, verify_cert
from safe_runtime import atomic_write_bytes, atomic_write_json, safe_read_text
from server_security_guard import OFFICIAL_LOOKUP_GUARD


ROOT = Path(__file__).resolve().parent
REGISTRY_PATH = ROOT / "manual_graded_photo_registrations.json"
INBOX_ROOT = ROOT / "GRADE_TRAINING_INBOX" / "manual"
VERIFIED_CERTIFICATIONS = ROOT / "verified_certifications.json"
VERIFIED_SLAB_REFERENCES = ROOT / "library_verified_slab_references.json"
COMPANIES = {"PSA", "BGS", "CGC", "TAG", "BRG"}
GAMES = {"pokemon", "onepiece", "naruto"}
MAX_IMAGE_BYTES = 6_000_000
MAX_IMAGE_PIXELS = 36_000_000
MAX_REGISTRATIONS = 5000
LOCK = threading.RLock()
PROCESS_LOCK = threading.Lock()
PROCESSING_IDS: set[str] = set()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(safe_read_text(path, max_bytes=8_000_000))
    except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        return default


def _registry() -> dict[str, Any]:
    value = _load(REGISTRY_PATH, {})
    rows = value.get("registrations", []) if isinstance(value, dict) else []
    return {
        "schema_version": 1,
        "updated_at": value.get("updated_at") if isinstance(value, dict) else None,
        "registrations": [dict(row) for row in rows if isinstance(row, dict)][-MAX_REGISTRATIONS:],
    }


def _save_registry(payload: dict[str, Any]) -> None:
    payload["schema_version"] = 1
    payload["updated_at"] = _now()
    payload["registrations"] = payload.get("registrations", [])[-MAX_REGISTRATIONS:]
    atomic_write_json(REGISTRY_PATH, payload, suffix=".manual-photo-registry.tmp")


def _bounded_text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").replace("\x00", " ").split())[:limit]


def _normalized_cert(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()[:24]


def _grade(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("등급은 1~10 숫자여야 합니다.") from exc
    if not math.isfinite(number) or not 1 <= number <= 10 or abs(number * 2 - round(number * 2)) > 1e-9:
        raise ValueError("등급은 1~10 범위의 0.5 단위여야 합니다.")
    return number


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    if not data.startswith(b"\xff\xd8"):
        return None
    offset = 2
    while offset + 9 <= len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue
        marker = data[offset + 1]
        offset += 2
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if offset + 2 > len(data):
            break
        length = int.from_bytes(data[offset:offset + 2], "big")
        if length < 2 or offset + length > len(data):
            break
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            height = int.from_bytes(data[offset + 3:offset + 5], "big")
            width = int.from_bytes(data[offset + 5:offset + 7], "big")
            return width, height
        offset += length
    return None


def _decode_image(data_url: Any) -> tuple[bytes, str, int, int]:
    text = str(data_url or "")
    match = re.fullmatch(r"data:image/(jpeg|png);base64,([A-Za-z0-9+/=\r\n]+)", text, re.I)
    if not match:
        raise ValueError("JPG 또는 PNG 사진만 등록할 수 있습니다.")
    try:
        data = base64.b64decode(match.group(2), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("사진 데이터가 손상되었습니다.") from exc
    if len(data) < 1024 or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("사진 크기는 1KB~6MB여야 합니다.")
    kind = match.group(1).lower()
    if kind == "png":
        if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) < 24:
            raise ValueError("PNG 파일 형식이 올바르지 않습니다.")
        width, height = struct.unpack(">II", data[16:24])
        extension = ".png"
    else:
        dimensions = _jpeg_dimensions(data)
        if dimensions is None:
            raise ValueError("JPG 파일 형식이 올바르지 않습니다.")
        width, height = dimensions
        extension = ".jpg"
    if not 320 <= width <= 12000 or not 320 <= height <= 12000:
        raise ValueError("사진 해상도는 가로·세로 320~12000px 범위여야 합니다.")
    if width * height > MAX_IMAGE_PIXELS:
        raise ValueError("사진 전체 해상도는 3600만 픽셀 이하여야 합니다.")
    return data, extension, width, height


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "registration_id", "created_at", "updated_at", "company", "game", "claimed_grade",
        "certification_id", "card_name", "card_number", "image_sha256", "image_width",
        "image_height", "status", "verification_state", "official_result",
        "official_reference_url", "learning_eligibility", "training_eligible",
        "quarantine_reasons", "ocr_company", "ocr_grade", "ocr_certification_id",
        "ocr_error", "ocr_cache_hit", "retry_after_seconds", "duplicate_of",
    )
    return {key: row.get(key) for key in keys if key in row}


def public_registry() -> dict[str, Any]:
    with LOCK:
        payload = _registry()
    rows = [_public_row(row) for row in reversed(payload["registrations"])]
    return {
        "ok": True,
        "schema_version": 1,
        "updated_at": payload.get("updated_at"),
        "registrations": rows[:200],
        "summary": {
            "total": len(rows),
            "verified_reference": sum(row.get("official_result") is True for row in rows),
            "pending": sum(row.get("status") == "pending_official_verification" for row in rows),
            "quarantined": sum(row.get("status") == "quarantine" for row in rows),
            "raw_calibration_rows_written": 0,
        },
        "policy": {
            "manual_claim_is_truth": False,
            "official_company_cert_grade_match_required": True,
            "raw_and_slab_learning_isolated": True,
        },
    }


def registration_exists(registration_id: Any) -> bool:
    registration_id = _bounded_text(registration_id, 80)
    with LOCK:
        return any(row.get("registration_id") == registration_id for row in _registry()["registrations"])


def register(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("등록자료 형식 오류")
    company = _bounded_text(payload.get("company"), 8).upper()
    game = _bounded_text(payload.get("game"), 16).lower().replace("_", "").replace("-", "")
    cert = _normalized_cert(payload.get("certification_id"))
    grade = _grade(payload.get("grade"))
    if company not in COMPANIES:
        raise ValueError("지원 등급사는 PSA·BGS·CGC·TAG·BRG입니다.")
    if game not in GAMES:
        raise ValueError("게임은 포켓몬·원피스·나루토 중에서 선택하세요.")
    if len(cert) < 6:
        raise ValueError("인증번호를 6자 이상 입력하세요.")
    image, extension, width, height = _decode_image(payload.get("image_data_url"))
    digest = hashlib.sha256(image).hexdigest()
    now = _now()
    with LOCK:
        registry = _registry()
        for existing in registry["registrations"]:
            if existing.get("image_sha256") == digest:
                same_claim = (
                    existing.get("company") == company
                    and existing.get("game") == game
                    and _normalized_cert(existing.get("certification_id")) == cert
                    and abs(float(existing.get("claimed_grade")) - grade) < 1e-9
                )
                if not same_claim:
                    raise ValueError("같은 사진이 다른 업체·인증번호·등급으로 이미 등록되어 있습니다.")
                return {"ok": True, "duplicate": True, "registration": _public_row(existing)}
        registration_id = f"manual-{datetime.now(timezone.utc):%Y%m%d%H%M%S}-{secrets.token_hex(6)}"
        folder = INBOX_ROOT / datetime.now(timezone.utc).strftime("%Y%m")
        target = folder / f"{registration_id}{extension}"
        atomic_write_bytes(target, image, suffix=".manual-photo.tmp")
        row = {
            "registration_id": registration_id,
            "created_at": now,
            "updated_at": now,
            "company": company,
            "game": game,
            "claimed_grade": grade,
            "certification_id": cert,
            "card_name": _bounded_text(payload.get("card_name"), 180),
            "card_number": _bounded_text(payload.get("card_number"), 60),
            "note": _bounded_text(payload.get("note"), 300),
            "original_filename": _bounded_text(payload.get("filename"), 120),
            "image_path": target.relative_to(ROOT).as_posix(),
            "image_sha256": digest,
            "image_width": width,
            "image_height": height,
            "image_bytes": len(image),
            "status": "pending_official_verification",
            "verification_state": "queued",
            "official_result": False,
            "official_reference_url": lookup_url(company, cert),
            "learning_eligibility": "quarantine_only_until_official_match",
            "training_eligible": False,
            "raw_grade_calibration_eligible": False,
            "quarantine_reasons": ["manual_claim_unverified", "official_lookup_required"],
            "audit": {"manual_upload": True, "image_magic_checked": True, "path_generated_server_side": True},
        }
        registry["registrations"].append(row)
        _save_registry(registry)
    return {"ok": True, "duplicate": False, "registration": _public_row(row)}


def _find_row(registry: dict[str, Any], registration_id: str) -> tuple[int, dict[str, Any]]:
    for index, row in enumerate(registry.get("registrations", [])):
        if row.get("registration_id") == registration_id:
            return index, row
    raise ValueError("수동등록 번호를 찾을 수 없습니다.")


def _publish_verified(row: dict[str, Any]) -> tuple[bool, str | None]:
    company, cert, grade = row["company"], row["certification_id"], float(row["claimed_grade"])
    certifications = _load(VERIFIED_CERTIFICATIONS, {"version": 1, "certifications": []})
    values = certifications.get("certifications", []) if isinstance(certifications, dict) else []
    values = [dict(item) for item in values if isinstance(item, dict)]
    for item in values:
        if str(item.get("company") or "").upper() == company and _normalized_cert(item.get("certification_id")) == cert:
            try:
                if abs(float(item.get("grade")) - grade) > 1e-9:
                    return False, "persisted_official_grade_conflict"
            except (TypeError, ValueError, OverflowError):
                return False, "persisted_official_grade_invalid"
            break
    else:
        values.append({
            "company": company, "certification_id": cert, "grade": grade, "verified": True,
            "official_reference_url": row["official_reference_url"], "card_name": row.get("card_name"),
            "game": row.get("game"), "mode": "slab", "source": "manual-photo-official-cert-match",
        })
        certifications = {"version": 1, "certifications": values,
                          "instructions": "Manual labels require official company+cert+grade verification before reference learning."}
        atomic_write_json(VERIFIED_CERTIFICATIONS, certifications, suffix=".manual-cert.tmp")

    references = _load(VERIFIED_SLAB_REFERENCES, {"schema_version": 1, "certifications": []})
    ref_values = references.get("certifications", []) if isinstance(references, dict) else []
    ref_values = [dict(item) for item in ref_values if isinstance(item, dict)]
    key = (company, cert, row["image_sha256"])
    exists = any((str(item.get("company") or "").upper(), _normalized_cert(item.get("certification_id")),
                  str(item.get("source_sha256") or "")) == key for item in ref_values)
    if not exists:
        ref_values.append({
            "company": company, "certification_id": cert, "official_grade": grade,
            "card_name": row.get("card_name"), "game": row.get("game"), "mode": "slab",
            "official_result": True, "official_reference_url": row["official_reference_url"],
            "source_sha256": row["image_sha256"], "source_name": row["image_path"],
            "learning_eligibility": "reference_only_missing_raw_prediction",
        })
        references = {
            "schema_version": 1, "updated_at": _now(), "certifications": ref_values[-2000:],
            "training_rows_written": 0,
            "reason": "Verified slab photos are reference-only; raw calibration remains isolated.",
        }
        atomic_write_json(VERIFIED_SLAB_REFERENCES, references, suffix=".manual-slab-reference.tmp")
    return True, None


def _ocr_image(image_path: Path) -> tuple[str, str | None, dict[str, Any], dict[str, Any]]:
    """Keep Pillow/Tesseract optional so registration still queues safely."""
    try:
        from library_slab_corpus import ocr_label
        from graded_photo_evidence import extract_label_evidence
        text, error, diagnostics = ocr_label(image_path, profile="fast")
        return text, error, diagnostics, extract_label_evidence(text)
    except (ImportError, OSError, ValueError, TypeError):
        return "", "ocr_unavailable", {}, {}


def _ocr_for_row(row: dict[str, Any]) -> tuple[str, str | None, dict[str, Any], dict[str, Any], bool]:
    """Reuse a complete OCR identity on safe retries instead of decoding twice."""
    cached_identity = {
        "company": row.get("ocr_company"),
        "grade": row.get("ocr_grade"),
        "certification_id": row.get("ocr_certification_id"),
    }
    cache_valid = bool(
        row.get("ocr_cached_sha256") == row.get("image_sha256")
        and cached_identity["company"]
        and cached_identity["grade"] is not None
        and cached_identity["certification_id"]
    )
    if cache_valid:
        diagnostics = row.get("ocr_diagnostics")
        return (
            str(row.get("ocr_label_text") or ""),
            row.get("ocr_error"),
            dict(diagnostics) if isinstance(diagnostics, dict) else {},
            cached_identity,
            True,
        )
    text, error, diagnostics, evidence = _ocr_image(ROOT / str(row["image_path"]))
    return text, error, diagnostics, evidence, False


def _claim_processing(registration_id: str) -> bool:
    with PROCESS_LOCK:
        if registration_id in PROCESSING_IDS:
            return False
        PROCESSING_IDS.add(registration_id)
        return True


def _release_processing(registration_id: str) -> None:
    with PROCESS_LOCK:
        PROCESSING_IDS.discard(registration_id)


def _process_registration_once(registration_id: str) -> dict[str, Any]:
    with LOCK:
        registry = _registry()
        index, row = _find_row(registry, registration_id)
        row.update({"verification_state": "ocr_running", "updated_at": _now(), "retry_after_seconds": None})
        registry["registrations"][index] = row
        _save_registry(registry)

    text, ocr_error, diagnostics, evidence, ocr_cache_hit = _ocr_for_row(row)
    conflicts = []
    if evidence.get("company") and evidence.get("company") != row["company"]:
        conflicts.append("ocr_company_conflict")
    if evidence.get("certification_id") and _normalized_cert(evidence.get("certification_id")) != row["certification_id"]:
        conflicts.append("ocr_certification_conflict")
    if evidence.get("grade") is not None and abs(float(evidence["grade"]) - float(row["claimed_grade"])) > 1e-9:
        conflicts.append("ocr_grade_conflict")

    allowed, guard = OFFICIAL_LOOKUP_GUARD.claim(row["company"])
    if not allowed:
        with LOCK:
            registry = _registry(); index, current = _find_row(registry, registration_id)
            current.update({
                "updated_at": _now(), "verification_state": "deferred_by_cooldown",
                "retry_after_seconds": guard.get("retry_after_seconds"), "ocr_label_text": text[:1800],
                "ocr_error": ocr_error, "ocr_diagnostics": diagnostics,
                "ocr_cached_sha256": row.get("image_sha256"), "ocr_cache_hit": ocr_cache_hit,
                "ocr_company": evidence.get("company"), "ocr_grade": evidence.get("grade"),
                "ocr_certification_id": evidence.get("certification_id"),
            })
            registry["registrations"][index] = current; _save_registry(registry)
        return {"ok": True, "deferred": True, "registration": _public_row(current)}

    result = verify_cert(row["company"], row["certification_id"], expected_grade=row["claimed_grade"], timeout=10)
    guard_result = OFFICIAL_LOOKUP_GUARD.record_result(row["company"], result)
    provider_blocked = bool(guard_result.get("blocked") or result.get("blocked_or_challenged"))
    ocr_identity_complete = bool(
        evidence.get("company") == row["company"]
        and _normalized_cert(evidence.get("certification_id")) == row["certification_id"]
        and evidence.get("grade") is not None
        and abs(float(evidence["grade"]) - float(row["claimed_grade"])) < 1e-9
    )
    official_verified = result.get("verified") is True and ocr_identity_complete and not conflicts
    status = "verified_reference" if official_verified else "quarantine" if result.get("conflict") or conflicts else "pending_official_verification"
    reasons = []
    if conflicts:
        reasons.extend(conflicts)
    if not result.get("verified"):
        reasons.append("official_lookup_not_confirmed")
    if not ocr_identity_complete:
        reasons.append("ocr_identity_not_confirmed")
    if result.get("blocked_or_challenged"):
        reasons.append("official_provider_cooldown")

    with LOCK:
        registry = _registry(); index, current = _find_row(registry, registration_id)
        current.update({
            "updated_at": _now(), "status": status,
            "verification_state": "verified" if official_verified else "deferred_by_cooldown" if provider_blocked else "completed_unverified",
            "official_result": official_verified,
            "official_grade": result.get("grade"),
            "official_reference_url": result.get("official_url") or current.get("official_reference_url"),
            "learning_eligibility": "reference_learning_only" if official_verified else "quarantine_only_until_official_match",
            "training_eligible": False, "raw_grade_calibration_eligible": False,
            "quarantine_reasons": sorted(set(reasons)),
            "retry_after_seconds": (guard_result.get("cooldown_seconds") or result.get("recommended_cooldown_seconds")) if provider_blocked else None,
            "ocr_label_text": text[:1800], "ocr_error": ocr_error, "ocr_diagnostics": diagnostics,
            "ocr_cached_sha256": row.get("image_sha256"), "ocr_cache_hit": ocr_cache_hit,
            "ocr_company": evidence.get("company"), "ocr_grade": evidence.get("grade"),
            "ocr_certification_id": evidence.get("certification_id"),
            "official_lookup": {key: result.get(key) for key in (
                "http_status", "verified", "conflict", "lookup_error", "notice", "recommended_cooldown_seconds"
            )},
        })
        if official_verified:
            published, error = _publish_verified(current)
            if not published:
                current.update({"status": "quarantine", "official_result": False,
                                "learning_eligibility": "quarantine_registry_conflict",
                                "quarantine_reasons": sorted(set(current["quarantine_reasons"] + [str(error)]))})
        registry["registrations"][index] = current; _save_registry(registry)
    return {"ok": True, "deferred": provider_blocked, "registration": _public_row(current)}


def process_registration(registration_id: Any) -> dict[str, Any]:
    registration_id = _bounded_text(registration_id, 80)
    with LOCK:
        registry = _registry()
        _, current = _find_row(registry, registration_id)
        public = _public_row(current)
    if not _claim_processing(registration_id):
        return {"ok": True, "deferred": True, "already_processing": True, "registration": public}
    try:
        return _process_registration_once(registration_id)
    finally:
        _release_processing(registration_id)


def mark_processing_failed(registration_id: Any) -> None:
    """Recover a background job without exposing internal exception text."""
    registration_id = _bounded_text(registration_id, 80)
    with LOCK:
        registry = _registry()
        try:
            index, row = _find_row(registry, registration_id)
        except ValueError:
            return
        row.update({
            "updated_at": _now(), "verification_state": "processing_failed",
            "status": "pending_official_verification", "official_result": False,
            "learning_eligibility": "quarantine_only_until_official_match",
            "training_eligible": False,
            "quarantine_reasons": sorted(set((row.get("quarantine_reasons") or []) + ["manual_processing_failed"])),
        })
        registry["registrations"][index] = row
        _save_registry(registry)
