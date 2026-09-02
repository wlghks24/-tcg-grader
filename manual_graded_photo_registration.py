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
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re
import secrets
import struct
import threading
from typing import Any

from grading_cert_verifier import lookup_url
from safe_runtime import atomic_write_bytes, atomic_write_json, safe_read_text


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


@lru_cache(maxsize=8)
def _cached_registry_payload(path_text: str, signature: tuple[int, int, int, int] | None) -> Any:
    """Cache a parsed registry until its inode, timestamp, or size changes."""
    return _load(Path(path_text), {})


def _registry() -> dict[str, Any]:
    try:
        metadata = REGISTRY_PATH.stat()
        signature = (metadata.st_dev, metadata.st_ino, metadata.st_mtime_ns, metadata.st_size)
    except OSError:
        signature = None
    value = _cached_registry_payload(str(REGISTRY_PATH.absolute()), signature)
    rows = value.get("registrations", []) if isinstance(value, dict) else []
    return {
        "schema_version": 2,
        "updated_at": value.get("updated_at") if isinstance(value, dict) else None,
        "registrations": [dict(row) for row in rows if isinstance(row, dict)][-MAX_REGISTRATIONS:],
    }


def _save_registry(payload: dict[str, Any]) -> None:
    payload["schema_version"] = 2
    payload["updated_at"] = _now()
    payload["registrations"] = payload.get("registrations", [])[-MAX_REGISTRATIONS:]
    atomic_write_json(REGISTRY_PATH, payload, suffix=".manual-photo-registry.tmp")
    _cached_registry_payload.cache_clear()


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


def _decode_optional_image(payload: dict[str, Any], key: str) -> tuple[bytes, str, int, int] | None:
    value = payload.get(key)
    if value in (None, ""):
        return None
    return _decode_image(value)


def _safe_client_quadrant_preview(value: Any) -> dict[str, Any] | None:
    """Keep bounded UI diagnostics for audit; never accept them as training truth."""
    if not isinstance(value, dict) or value.get("zone_count") != 8:
        return None
    sides: dict[str, Any] = {}
    for side in ("front", "back"):
        source = value.get(side)
        quadrants = source.get("quadrants") if isinstance(source, dict) else None
        if not isinstance(quadrants, dict) or set(quadrants) != {"tl", "tr", "bl", "br"}:
            return None
        rows: dict[str, Any] = {}
        for zone in ("tl", "tr", "bl", "br"):
            source_row = quadrants.get(zone)
            if not isinstance(source_row, dict):
                return None
            row: dict[str, Any] = {}
            for name in ("scratchRisk", "surfaceRisk", "edgeRisk", "cornerRisk", "whiteningRisk",
                         "combinedRisk", "confidence", "confirmedSegments"):
                try:
                    number = float(source_row.get(name, 0))
                except (TypeError, ValueError, OverflowError):
                    return None
                high = 100.0 if name != "confirmedSegments" else 500.0
                if not math.isfinite(number) or not 0 <= number <= high:
                    return None
                row[name] = round(number, 2)
            status = str(source_row.get("obliqueStatus") or "not_captured")
            row["obliqueStatus"] = status if status in {
                "not_captured", "confirmed", "clear_both_angles", "angle_mismatch"
            } else "invalid"
            rows[zone] = row
        sides[side] = {"quadrants": rows}
    return {
        "version": 1,
        "engine": _bounded_text(value.get("engine"), 96),
        "zone_count": 8,
        "oblique_crosscheck_complete": value.get("oblique_crosscheck_complete") is True,
        "authoritative_for_training": False,
        **sides,
    }


def _store_registration_image(folder: Path, stem: str, decoded: tuple[bytes, str, int, int]) -> dict[str, Any]:
    image, extension, width, height = decoded
    target = folder / f"{stem}{extension}"
    atomic_write_bytes(target, image, suffix=".manual-photo.tmp")
    return {
        "path": target.relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(image).hexdigest(),
        "width": width,
        "height": height,
        "bytes": len(image),
    }


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "registration_id", "created_at", "updated_at", "company", "game", "claimed_grade",
        "certification_id", "card_name", "card_number", "image_sha256", "image_width",
        "image_height", "status", "verification_state", "official_result",
        "official_reference_url", "learning_eligibility", "training_eligible",
        "quarantine_reasons", "ocr_company", "ocr_grade", "ocr_certification_id",
        "ocr_error", "ocr_cache_hit", "retry_after_seconds", "duplicate_of",
        "entry_mode", "manual_identity_complete", "missing_identity_fields",
        "back_image_sha256", "back_image_width", "back_image_height", "front_back_pair_complete",
        "front_oblique_image_sha256", "back_oblique_image_sha256", "oblique_crosscheck_complete",
        "quadrant_zone_count", "quadrant_inspection_state", "measurement_learning_eligible",
        "client_preview_training_eligible", "photo_revalidation", "manual_official_proof_required",
    )
    public = {key: row.get(key) for key in keys if key in row}
    # v190: Older tablet-local BRG registrations may still contain the retired
    # brgcard.com URL. Never expose that stale stored URL when the registration
    # already has a certificate identity; regenerate the current Break Korea
    # direct certification URL instead. This repairs existing rows at read time
    # without rewriting or deleting the user's local registration history.
    company = str(row.get("company") or row.get("ocr_company") or "").upper()
    cert = _normalized_cert(row.get("certification_id") or row.get("ocr_certification_id"))
    if company == "BRG" and cert:
        public["official_reference_url"] = lookup_url("BRG", cert)
    return public


def _record_collection_gap(row: dict[str, Any], *, verified: bool = False) -> None:
    """Teach coverage priority without allowing a manual claim to change trust."""
    try:
        from detailed_collection_intelligence import record_manual_recovery
        record_manual_recovery(
            str(row.get("registration_id") or ""), str(row.get("game") or ""),
            str(row.get("company") or row.get("ocr_company") or ""), verified=verified,
        )
    except (ImportError, OSError, ValueError, TypeError, TimeoutError):
        pass


def public_registry() -> dict[str, Any]:
    with LOCK:
        try:
            metadata = REGISTRY_PATH.stat()
            signature = (metadata.st_dev, metadata.st_ino, metadata.st_mtime_ns, metadata.st_size)
        except OSError:
            signature = None
        payload = _cached_registry_payload(str(REGISTRY_PATH.absolute()), signature)
        source_rows = payload.get("registrations", []) if isinstance(payload, dict) else []
        rows = [_public_row(row) for row in reversed(source_rows[-MAX_REGISTRATIONS:]) if isinstance(row, dict)]
    return {
        "ok": True,
        "schema_version": 2,
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
            "automatic_official_lookup_enabled": False,
            "manual_official_screenshot_required": True,
        },
    }


def registration_exists(registration_id: Any) -> bool:
    registration_id = _bounded_text(registration_id, 80)
    with LOCK:
        try:
            metadata = REGISTRY_PATH.stat()
            signature = (metadata.st_dev, metadata.st_ino, metadata.st_mtime_ns, metadata.st_size)
        except OSError:
            signature = None
        payload = _cached_registry_payload(str(REGISTRY_PATH.absolute()), signature)
        rows = payload.get("registrations", []) if isinstance(payload, dict) else []
        return any(isinstance(row, dict) and row.get("registration_id") == registration_id for row in rows[-MAX_REGISTRATIONS:])


def register(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("등록자료 형식 오류")
    company = _bounded_text(payload.get("company"), 8).upper()
    game = _bounded_text(payload.get("game"), 16).lower().replace("_", "").replace("-", "")
    cert = _normalized_cert(payload.get("certification_id"))
    grade_value = payload.get("grade")
    grade = None if grade_value in (None, "") else _grade(grade_value)
    if company and company not in COMPANIES:
        raise ValueError("지원 등급사는 PSA·BGS·CGC·TAG·BRG입니다.")
    if game not in GAMES:
        raise ValueError("게임은 포켓몬·원피스·나루토 중에서 선택하세요.")
    if cert and len(cert) < 6:
        raise ValueError("인증번호를 6자 이상 입력하세요.")
    manual_identity_complete = bool(company and cert and grade is not None)
    image, extension, width, height = _decode_image(payload.get("image_data_url"))
    back_decoded = _decode_optional_image(payload, "back_image_data_url")
    front_oblique_decoded = _decode_optional_image(payload, "front_oblique_image_data_url")
    back_oblique_decoded = _decode_optional_image(payload, "back_oblique_image_data_url")
    digest = hashlib.sha256(image).hexdigest()
    back_digest = hashlib.sha256(back_decoded[0]).hexdigest() if back_decoded else ""
    front_oblique_digest = hashlib.sha256(front_oblique_decoded[0]).hexdigest() if front_oblique_decoded else ""
    back_oblique_digest = hashlib.sha256(back_oblique_decoded[0]).hexdigest() if back_oblique_decoded else ""
    if back_digest and back_digest == digest:
        raise ValueError("앞면과 뒷면은 서로 다른 사진이어야 합니다.")
    if bool(front_oblique_decoded) != bool(back_oblique_decoded):
        raise ValueError("사선광 교차검증 사진은 앞면·뒷면을 함께 등록하세요.")
    if front_oblique_digest and front_oblique_digest == digest:
        raise ValueError("앞면 사선광 사진은 기본광 사진과 다른 각도로 촬영하세요.")
    if back_oblique_digest and back_oblique_digest == back_digest:
        raise ValueError("뒷면 사선광 사진은 기본광 사진과 다른 각도로 촬영하세요.")
    client_preview = _safe_client_quadrant_preview(payload.get("client_quadrant_preview"))
    now = _now()
    with LOCK:
        registry = _registry()
        for existing in registry["registrations"]:
            if existing.get("image_sha256") == digest:
                stored_back = str(existing.get("back_image_sha256") or "")
                if stored_back and back_digest and stored_back != back_digest:
                    raise ValueError("같은 앞면 사진이 다른 뒷면 사진과 이미 등록되어 있습니다.")
                existing_grade = existing.get("claimed_grade")
                same_claim = existing.get("game") == game
                for provided, stored in ((company, existing.get("company")), (cert, _normalized_cert(existing.get("certification_id")))):
                    if provided and stored and provided != stored:
                        same_claim = False
                if grade is not None and existing_grade is not None and abs(float(existing_grade) - grade) >= 1e-9:
                    same_claim = False
                if not same_claim:
                    raise ValueError("같은 사진이 다른 업체·인증번호·등급으로 이미 등록되어 있습니다.")
                if back_decoded and not stored_back:
                    folder = (ROOT / str(existing["image_path"])).parent
                    registration_id = str(existing["registration_id"])
                    back_info = _store_registration_image(folder, f"{registration_id}_back", back_decoded)
                    existing.update({
                        "back_image_path": back_info["path"], "back_image_sha256": back_info["sha256"],
                        "back_image_width": back_info["width"], "back_image_height": back_info["height"],
                        "back_image_bytes": back_info["bytes"], "back_original_filename": _bounded_text(payload.get("back_filename"), 120),
                        "front_back_pair_complete": True, "quadrant_zone_count": 8,
                    })
                    if front_oblique_decoded and back_oblique_decoded:
                        front_angle = _store_registration_image(folder, f"{registration_id}_front_oblique", front_oblique_decoded)
                        back_angle = _store_registration_image(folder, f"{registration_id}_back_oblique", back_oblique_decoded)
                        existing.update({
                            "front_oblique_image_path": front_angle["path"], "front_oblique_image_sha256": front_angle["sha256"],
                            "back_oblique_image_path": back_angle["path"], "back_oblique_image_sha256": back_angle["sha256"],
                            "oblique_crosscheck_complete": True,
                        })
                    existing.update({
                        "quadrant_inspection_state": "crosscheck_captured" if existing.get("oblique_crosscheck_complete") else "base_pair_captured",
                        "client_quadrant_preview": client_preview, "client_preview_training_eligible": False,
                        "updated_at": now, "verification_state": "queued", "status": "pending_official_verification",
                    })
                    _save_registry(registry)
                    return {"ok": True, "duplicate": False, "resumed": True, "registration": _public_row(existing)}
                supplied_identity = bool(company or cert or grade is not None)
                existing_incomplete = not bool(
                    existing.get("company") and _normalized_cert(existing.get("certification_id"))
                    and existing.get("claimed_grade") is not None
                )
                if supplied_identity and existing_incomplete:
                    existing["company"] = existing.get("company") or company
                    existing["certification_id"] = _normalized_cert(existing.get("certification_id")) or cert
                    existing["claimed_grade"] = existing.get("claimed_grade") if existing.get("claimed_grade") is not None else grade
                    existing["manual_identity_complete"] = bool(
                        existing["company"] and existing["certification_id"] and existing["claimed_grade"] is not None
                    )
                    existing["missing_identity_fields"] = [name for name, value in (
                        ("company", existing["company"]), ("grade", existing["claimed_grade"]),
                        ("certification_id", existing["certification_id"])
                    ) if value in (None, "")]
                    existing.update({"updated_at": now, "verification_state": "queued",
                                     "status": "pending_official_verification"})
                    if existing["company"] and existing["certification_id"]:
                        existing["official_reference_url"] = lookup_url(existing["company"], existing["certification_id"])
                    _save_registry(registry)
                    return {"ok": True, "duplicate": False, "resumed": True,
                            "registration": _public_row(existing)}
                return {"ok": True, "duplicate": True, "registration": _public_row(existing)}
        registration_id = f"manual-{datetime.now(timezone.utc):%Y%m%d%H%M%S}-{secrets.token_hex(6)}"
        folder = INBOX_ROOT / datetime.now(timezone.utc).strftime("%Y%m")
        target = folder / f"{registration_id}{extension}"
        atomic_write_bytes(target, image, suffix=".manual-photo.tmp")
        back_info = _store_registration_image(folder, f"{registration_id}_back", back_decoded) if back_decoded else None
        front_angle = _store_registration_image(folder, f"{registration_id}_front_oblique", front_oblique_decoded) if front_oblique_decoded else None
        back_angle = _store_registration_image(folder, f"{registration_id}_back_oblique", back_oblique_decoded) if back_oblique_decoded else None
        pair_complete = back_info is not None
        oblique_complete = front_angle is not None and back_angle is not None
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
            "back_original_filename": _bounded_text(payload.get("back_filename"), 120),
            "back_image_path": back_info["path"] if back_info else None,
            "back_image_sha256": back_info["sha256"] if back_info else None,
            "back_image_width": back_info["width"] if back_info else None,
            "back_image_height": back_info["height"] if back_info else None,
            "back_image_bytes": back_info["bytes"] if back_info else None,
            "front_oblique_original_filename": _bounded_text(payload.get("front_oblique_filename"), 120),
            "front_oblique_image_path": front_angle["path"] if front_angle else None,
            "front_oblique_image_sha256": front_angle["sha256"] if front_angle else None,
            "back_oblique_original_filename": _bounded_text(payload.get("back_oblique_filename"), 120),
            "back_oblique_image_path": back_angle["path"] if back_angle else None,
            "back_oblique_image_sha256": back_angle["sha256"] if back_angle else None,
            "front_back_pair_complete": pair_complete,
            "oblique_crosscheck_complete": oblique_complete,
            "quadrant_zone_count": 8 if pair_complete else 4,
            "quadrant_inspection_state": "crosscheck_captured" if oblique_complete else "base_pair_captured" if pair_complete else "front_only_legacy",
            "client_quadrant_preview": client_preview,
            "client_preview_training_eligible": False,
            "measurement_learning_eligible": False,
            "status": "pending_official_verification",
            "verification_state": "queued",
            "official_result": False,
            "official_reference_url": lookup_url(company, cert) if company and cert else None,
            "learning_eligibility": "quarantine_only_until_official_match",
            "training_eligible": False,
            "raw_grade_calibration_eligible": False,
            "quarantine_reasons": ["manual_claim_unverified", "official_lookup_required", "ocr_identity_required"]
                                  + ([] if pair_complete else ["front_back_pair_required_for_measurement_learning"]),
            "entry_mode": "manual_identity" if manual_identity_complete else "ocr_first",
            "manual_identity_complete": manual_identity_complete,
            "missing_identity_fields": [name for name, value in (
                ("company", company), ("grade", grade), ("certification_id", cert)
            ) if value in (None, "")],
            "audit": {"manual_upload": True, "image_magic_checked": True, "path_generated_server_side": True,
                      "manual_claim_is_truth": False, "ocr_autofill_requires_official_match": True,
                      "client_quadrant_preview_is_training_truth": False,
                      "server_remeasurement_required_before_learning": True},
        }
        registry["registrations"].append(row)
        _save_registry(registry)
    _record_collection_gap(row)
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
            "back_source_sha256": row.get("back_image_sha256"), "back_source_name": row.get("back_image_path"),
            "front_oblique_source_sha256": row.get("front_oblique_image_sha256"),
            "front_oblique_source_name": row.get("front_oblique_image_path"),
            "back_oblique_source_sha256": row.get("back_oblique_image_sha256"),
            "back_oblique_source_name": row.get("back_oblique_image_path"),
            "front_back_pair_complete": row.get("front_back_pair_complete") is True,
            "oblique_crosscheck_complete": row.get("oblique_crosscheck_complete") is True,
            "quadrant_zone_count": row.get("quadrant_zone_count"),
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
    manual_company = str(row.get("company") or "").upper()
    manual_cert = _normalized_cert(row.get("certification_id"))
    manual_grade = row.get("claimed_grade")
    ocr_company = str(evidence.get("company") or "").upper()
    if ocr_company not in COMPANIES:
        ocr_company = ""
    ocr_cert = _normalized_cert(evidence.get("certification_id"))
    if len(ocr_cert) < 6:
        ocr_cert = ""
    try:
        ocr_grade = _grade(evidence.get("grade")) if evidence.get("grade") is not None else None
    except ValueError:
        ocr_grade = None
    conflicts = []
    if manual_company and ocr_company and ocr_company != manual_company:
        conflicts.append("ocr_company_conflict")
    if manual_cert and ocr_cert and ocr_cert != manual_cert:
        conflicts.append("ocr_certification_conflict")
    if manual_grade is not None and ocr_grade is not None and abs(ocr_grade - float(manual_grade)) > 1e-9:
        conflicts.append("ocr_grade_conflict")

    resolved_company = manual_company or ocr_company
    resolved_cert = manual_cert or ocr_cert
    resolved_grade = float(manual_grade) if manual_grade is not None else ocr_grade
    missing = [name for name, value in (
        ("company", resolved_company), ("grade", resolved_grade), ("certification_id", resolved_cert)
    ) if value in (None, "")]
    if missing:
        with LOCK:
            registry = _registry(); index, current = _find_row(registry, registration_id)
            current.update({
                "updated_at": _now(), "status": "pending_official_verification",
                "verification_state": "manual_input_required", "missing_identity_fields": missing,
                "official_result": False,
                "quarantine_reasons": sorted(set(conflicts + ["ocr_identity_not_confirmed", "manual_identity_required"])),
                "ocr_label_text": text[:1800], "ocr_error": ocr_error, "ocr_diagnostics": diagnostics,
                "ocr_cached_sha256": row.get("image_sha256"), "ocr_cache_hit": ocr_cache_hit,
                "ocr_company": ocr_company or None, "ocr_grade": ocr_grade,
                "ocr_certification_id": ocr_cert or None,
            })
            registry["registrations"][index] = current; _save_registry(registry)
        return {"ok": True, "deferred": True, "manual_input_required": True,
                "registration": _public_row(current)}

    row.update({"company": resolved_company, "certification_id": resolved_cert,
                "claimed_grade": resolved_grade, "missing_identity_fields": [],
                "official_reference_url": lookup_url(resolved_company, resolved_cert)})

    # v192: company/certificate/grade identity is only a queue key.  Do not call
    # the grading-company website from the server.  The user must open the
    # official page in a browser, verify the cert, attach the result screenshot,
    # and explicitly complete verification through manual_official_proof.py.
    with LOCK:
        registry = _registry()
        index, current = _find_row(registry, registration_id)
        current.update({
            "updated_at": _now(),
            "status": "pending_official_verification",
            "verification_state": "manual_official_verification_required",
            "official_result": False,
            "official_grade": None,
            "official_reference_url": lookup_url(resolved_company, resolved_cert),
            "learning_eligibility": "manual_official_proof_required",
            "training_eligible": False,
            "raw_grade_calibration_eligible": False,
            "retry_after_seconds": None,
            "company": resolved_company,
            "claimed_grade": resolved_grade,
            "certification_id": resolved_cert,
            "missing_identity_fields": [],
            "ocr_label_text": text[:1800],
            "ocr_error": ocr_error,
            "ocr_diagnostics": diagnostics,
            "ocr_cached_sha256": row.get("image_sha256"),
            "ocr_cache_hit": ocr_cache_hit,
            "ocr_company": ocr_company or None,
            "ocr_grade": ocr_grade,
            "ocr_certification_id": ocr_cert or None,
            "manual_official_proof_required": True,
            "automatic_official_lookup_used": False,
        })
        reasons = set(current.get("quarantine_reasons") or [])
        reasons.discard("official_lookup_not_confirmed")
        reasons.discard("official_provider_blocked")
        reasons.add("manual_official_proof_required")
        current["quarantine_reasons"] = sorted(reasons)
        registry["registrations"][index] = current
        _save_registry(registry)
    _record_collection_gap(current)
    return {
        "ok": True, "deferred": True, "manual_official_proof_required": True,
        "automatic_official_lookup_used": False,
        "registration": _public_row(current),
    }


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
