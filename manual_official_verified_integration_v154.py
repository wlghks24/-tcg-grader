#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Promote strict user-browser official-page matches into official verification.

Automatic PSA/BGS/CGC/TAG/BRG HTTP lookup stays disabled. When the user opens an
official grader page and uploads a matching proof screenshot, the existing proof
matcher checks company + certificate and requires the grade either on the page
or from the exact OCR-confirmed slab identity. v154 promotes that strict match
into the integrated official slab-verification registry.

This changes slab identity trust only. It never makes slab photos eligible for
RAW card defect/grade calibration, and official rows are not counted as the old
"reference learning" bucket in the dashboard.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import manual_graded_photo_registration as manual_photo
import manual_official_proof as proof
from safe_runtime import atomic_write_json

PATCH_ID = 154
_APPLIED = False
_ORIGINAL_SUBMIT = None
_ORIGINAL_PROOF_PUBLIC = None
_ORIGINAL_PUBLIC_STATUS = None
_LAST_MIGRATION: dict[str, Any] = {}

_ALLOWED_MATCH_MODES = {
    "official_page_company_cert_grade_ocr",
    "official_page_company_cert_plus_exact_slab_ocr_grade",
}
_MANUAL_OFFICIAL_SOURCE = "user_browser_official_page"
_OFFICIAL_LEARNING_STATE = "official_verified_slab"


def _finite_grade(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and 1 <= number <= 10 else None


def _clean_cert(value: Any) -> str:
    return proof._clean_cert(value)


def _identity_gate(row: dict[str, Any]) -> tuple[bool, str]:
    company = str(row.get("company") or row.get("ocr_company") or "").upper()
    cert = _clean_cert(row.get("certification_id") or row.get("ocr_certification_id"))
    grade = _finite_grade(row.get("claimed_grade") if row.get("claimed_grade") is not None else row.get("ocr_grade"))
    if company not in manual_photo.COMPANIES:
        return False, "unsupported_company"
    if len(cert) < 6:
        return False, "missing_certification_id"
    if grade is None:
        return False, "missing_grade"
    if row.get("manual_official_proof_registered") is not True:
        return False, "manual_proof_not_registered"
    if str(row.get("manual_official_proof_state") or "") != "matched":
        return False, "manual_proof_not_matched"
    if str(row.get("manual_official_proof_match_mode") or "") not in _ALLOWED_MATCH_MODES:
        return False, "manual_proof_match_mode_not_strict"
    if row.get("front_back_pair_complete") is not True:
        return False, "front_back_pair_incomplete"
    front_sha = str(row.get("image_sha256") or "")
    back_sha = str(row.get("back_image_sha256") or "")
    proof_sha = str(row.get("manual_official_proof_sha256") or "")
    if len(front_sha) < 32 or len(back_sha) < 32 or len(proof_sha) < 32:
        return False, "evidence_hash_missing"
    if front_sha == back_sha:
        return False, "front_back_same_image"
    return True, "ready"


def _inside_root_file(relative_path: Any, allowed_root: Path) -> bool:
    text = str(relative_path or "").strip()
    if not text:
        return False
    try:
        root = allowed_root.resolve()
        candidate = (manual_photo.ROOT / text).resolve()
        return candidate != root and root in candidate.parents and candidate.is_file() and not candidate.is_symlink()
    except (OSError, ValueError, RuntimeError):
        return False


def _stored_evidence_present(row: dict[str, Any]) -> bool:
    return bool(
        _inside_root_file(row.get("image_path"), manual_photo.INBOX_ROOT)
        and _inside_root_file(row.get("back_image_path"), manual_photo.INBOX_ROOT)
        and _inside_root_file(row.get("manual_official_proof_path"), proof.PROOF_ROOT)
    )


def _clean_reasons(row: dict[str, Any]) -> list[str]:
    remove = {
        "manual_claim_unverified", "official_lookup_required", "official_lookup_not_confirmed",
        "manual_official_verification_required", "manual_official_page_proof_only",
        "live_official_lookup_pending", "ocr_identity_required",
    }
    return sorted(
        reason for reason in set(row.get("quarantine_reasons") or [])
        if reason not in remove and not str(reason).startswith("official_proof_")
    )


def _promote_reference_file(row: dict[str, Any]) -> None:
    try:
        payload = proof._load_json(proof.REFERENCE_PATH, {"schema_version": 4, "references": []})
        if not isinstance(payload, dict):
            return
        values = payload.get("references", [])
        if not isinstance(values, list):
            return
        registration_id = str(row.get("registration_id") or "")
        changed = False
        for item in values:
            if not isinstance(item, dict) or str(item.get("registration_id") or "") != registration_id:
                continue
            item.update({
                "official_result": True,
                "official_verification_source": _MANUAL_OFFICIAL_SOURCE,
                "verification_method": row.get("official_verification_method"),
                "learning_eligibility": _OFFICIAL_LEARNING_STATE,
                "raw_grade_calibration_eligible": False,
            })
            changed = True
        if not changed:
            return
        payload.update({
            "schema_version": 4,
            "updated_at": manual_photo._now(),
            "references": values[-proof.MAX_REFERENCES:],
            "policy": {
                "matched_user_browser_official_page_is_official_verification": True,
                "raw_calibration_allowed": False,
                "automatic_official_lookup_required": False,
            },
        })
        atomic_write_json(proof.REFERENCE_PATH, payload, suffix=".manual-official-promote.tmp")
    except (OSError, ValueError, TypeError, RuntimeError):
        return


def promote_registration(registration_id: str) -> dict[str, Any]:
    registration_id = str(registration_id or "").strip()[:80]
    with manual_photo.LOCK:
        registry = manual_photo._registry()
        try:
            index, source = manual_photo._find_row(registry, registration_id)
        except ValueError:
            return {"ok": False, "promoted": False, "reason": "registration_not_found"}
        row = dict(source)
        if row.get("official_result") is True:
            return {"ok": True, "promoted": False, "already_official": True, "registration": manual_photo._public_row(row)}
        ready, reason = _identity_gate(row)
        if not ready:
            return {"ok": True, "promoted": False, "reason": reason, "registration": manual_photo._public_row(row)}
        if not _stored_evidence_present(row):
            return {"ok": True, "promoted": False, "reason": "stored_evidence_missing", "registration": manual_photo._public_row(row)}

        grade = _finite_grade(row.get("claimed_grade") if row.get("claimed_grade") is not None else row.get("ocr_grade"))
        row.update({
            "updated_at": manual_photo._now(),
            "official_result": True,
            "official_grade": grade,
            "status": "verified_reference",
            "verification_state": "verified_manual_official_page",
            "verification_method": "manual_user_browser_official_page_exact_match",
            "official_verification_method": "manual_user_browser_official_page_exact_match",
            "official_verification_source": _MANUAL_OFFICIAL_SOURCE,
            "official_verified_at": row.get("manual_official_proof_at") or manual_photo._now(),
            "learning_eligibility": _OFFICIAL_LEARNING_STATE,
            "training_eligible": False,
            "raw_grade_calibration_eligible": False,
            "retry_after_seconds": None,
            "quarantine_reasons": _clean_reasons(row),
        })
        published, error = manual_photo._publish_verified(row)
        if not published:
            source = dict(source)
            reasons = sorted(set((source.get("quarantine_reasons") or []) + [str(error or "verified_registry_publish_failed")]))
            source.update({
                "status": "quarantine",
                "verification_state": "manual_official_verified_registry_conflict",
                "official_result": False,
                "learning_eligibility": "quarantine_registry_conflict",
                "quarantine_reasons": reasons,
            })
            registry["registrations"][index] = source
            manual_photo._save_registry(registry)
            return {"ok": False, "promoted": False, "reason": str(error or "publish_failed"), "registration": manual_photo._public_row(source)}

        registry["registrations"][index] = row
        manual_photo._save_registry(registry)

    _promote_reference_file(row)
    manual_photo._record_collection_gap(row, verified=True)
    return {"ok": True, "promoted": True, "registration": manual_photo._public_row(row)}


def migrate_existing() -> dict[str, Any]:
    with manual_photo.LOCK:
        registry = manual_photo._registry()
        ids = [
            str(row.get("registration_id") or "")
            for row in registry.get("registrations", [])
            if isinstance(row, dict)
            and row.get("official_result") is not True
            and row.get("manual_official_proof_registered") is True
            and str(row.get("manual_official_proof_state") or "") == "matched"
        ]
    promoted = 0
    skipped = 0
    failures: list[str] = []
    for registration_id in ids:
        result = promote_registration(registration_id)
        if result.get("promoted") is True:
            promoted += 1
        elif result.get("ok") is False:
            failures.append(str(result.get("reason") or "unknown"))
        else:
            skipped += 1
    return {"candidates": len(ids), "promoted": promoted, "skipped": skipped, "failures": failures[:20]}


def _decorated_public(row: dict[str, Any]) -> dict[str, Any]:
    base = _ORIGINAL_PROOF_PUBLIC(row) if callable(_ORIGINAL_PROOF_PUBLIC) else dict(row)
    manual_official = bool(
        row.get("official_result") is True
        and str(row.get("official_verification_source") or "") == _MANUAL_OFFICIAL_SOURCE
    )
    base.update({
        "official_verification_source": row.get("official_verification_source"),
        "official_verification_method": row.get("official_verification_method"),
        "official_verified_at": row.get("official_verified_at"),
        "manual_official_verified": manual_official,
        "manual_reference_only": False if manual_official else base.get("manual_reference_only", False),
        "user_cancel_allowed": row.get("official_result") is not True,
    })
    return base


def _integrated_public_status() -> dict[str, Any]:
    payload = dict(_ORIGINAL_PUBLIC_STATUS()) if callable(_ORIGINAL_PUBLIC_STATUS) else {"ok": False}
    rows = payload.get("registrations", []) if isinstance(payload.get("registrations"), list) else []
    manual_verified = sum(bool(row.get("manual_official_verified")) for row in rows if isinstance(row, dict))
    official_total = sum(row.get("official_result") is True for row in rows if isinstance(row, dict))
    summary = dict(payload.get("summary") or {})
    summary.update({
        "official_verified_total": official_total,
        "manual_official_verified": manual_verified,
        "pending_manual_proof": sum(
            isinstance(row, dict) and row.get("official_result") is not True and row.get("manual_official_proof_registered") is not True
            for row in rows
        ),
    })
    policy = dict(payload.get("policy") or {})
    policy.update({
        "manual_screenshot_sets_official_result": True,
        "manual_screenshot_alone_sets_official_result": False,
        "matched_user_browser_official_page_is_official_verification": True,
        "strict_identity_front_back_and_stored_proof_required": True,
        "registry_conflict_blocks_promotion": True,
        "automatic_official_lookup_required_for_manual_match": False,
        "manual_screenshot_trains_raw_grade_calibration": False,
        "later_live_official_lookup_can_promote": False,
    })
    payload.update({"version": 5, "summary": summary, "policy": policy})
    return payload


def _submit_integrated(payload: dict[str, Any]) -> dict[str, Any]:
    result = _ORIGINAL_SUBMIT(payload)
    if str(payload.get("action") or "").strip().lower() == "delete_registration":
        return result
    registration = result.get("registration") if isinstance(result, dict) else None
    registration_id = str((registration or {}).get("registration_id") or "")
    if not registration_id or result.get("accepted") is not True:
        return result
    promotion = promote_registration(registration_id)
    output = dict(result)
    output["official_promotion"] = promotion
    if promotion.get("registration"):
        with manual_photo.LOCK:
            registry = manual_photo._registry()
            try:
                _, latest = manual_photo._find_row(registry, registration_id)
                output["registration"] = proof._proof_public(latest)
            except ValueError:
                pass
    if promotion.get("promoted") is True or promotion.get("already_official") is True:
        output["accepted"] = True
        output["official_result"] = True
        output["integrated_official_verified"] = True
        output["policy"] = {
            "official_result": True,
            "official_verification_source": _MANUAL_OFFICIAL_SOURCE,
            "raw_grade_calibration": False,
            "integrated_verified_registry": True,
        }
    return output


_submit_integrated._manual_official_verified_integration_v154 = True


def apply() -> dict[str, Any]:
    global _APPLIED, _ORIGINAL_SUBMIT, _ORIGINAL_PROOF_PUBLIC, _ORIGINAL_PUBLIC_STATUS, _LAST_MIGRATION
    if getattr(proof.submit, "_manual_official_verified_integration_v154", False):
        _APPLIED = True
        _LAST_MIGRATION = migrate_existing()
        return status()
    if _ORIGINAL_SUBMIT is None:
        _ORIGINAL_SUBMIT = proof.submit
    if _ORIGINAL_PROOF_PUBLIC is None:
        _ORIGINAL_PROOF_PUBLIC = proof._proof_public
    if _ORIGINAL_PUBLIC_STATUS is None:
        _ORIGINAL_PUBLIC_STATUS = proof.public_status
    proof._proof_public = _decorated_public
    proof.public_status = _integrated_public_status
    proof.submit = _submit_integrated
    _APPLIED = True
    _LAST_MIGRATION = migrate_existing()
    return status()


def status() -> dict[str, Any]:
    return {
        "ok": bool(
            _APPLIED
            and getattr(proof.submit, "_manual_official_verified_integration_v154", False)
            and proof._proof_public is _decorated_public
            and proof.public_status is _integrated_public_status
        ),
        "patch": PATCH_ID,
        "applied": _APPLIED,
        "manual_official_page_promotes_to_official": True,
        "manual_screenshot_alone_sets_official_result": False,
        "strict_identity_front_back_and_stored_proof_required": True,
        "registry_conflict_blocks_promotion": True,
        "integrated_verified_registry": True,
        "counts_as_reference_learning": False,
        "raw_grade_calibration_eligible": False,
        "last_migration": dict(_LAST_MIGRATION),
    }


if __name__ == "__main__":
    print(json.dumps(apply(), ensure_ascii=False, indent=2))
