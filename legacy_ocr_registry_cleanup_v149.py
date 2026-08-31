#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Clean legacy OCR certification IDs without trusting them as grade truth.

Older tablet builds could store OCR fragments such as ``IFICATE`` as a
certification ID.  Current OCR v147/v148 uses grader-specific numeric lengths,
but stale registry rows remain visible until they are repaired.

This cleanup is intentionally conservative:
- never touches live-officially verified rows;
- never touches rows with an accepted manual official-page proof;
- only normalizes a certification when the current v147 parser can derive a
  company-valid numeric ID;
- otherwise clears the invalid certification and sends the row back to manual
  identity input/quarantine;
- never enables training or RAW grade calibration.
"""
from __future__ import annotations

import argparse
import json
from typing import Any

import manual_graded_photo_registration as manual_photo
import ocr_accuracy_boost_v147 as ocr_boost

PATCH_ID = 149


def _company(row: dict[str, Any]) -> str:
    value = str(row.get("company") or row.get("ocr_company") or "").upper().strip()
    return value if value in ocr_boost.COMPANIES else ""


def _cert(row: dict[str, Any]) -> str:
    return manual_photo._normalized_cert(row.get("certification_id") or row.get("ocr_certification_id"))


def _missing_fields(row: dict[str, Any]) -> list[str]:
    values = (
        ("company", str(row.get("company") or "").upper().strip()),
        ("grade", row.get("claimed_grade")),
        ("certification_id", manual_photo._normalized_cert(row.get("certification_id"))),
    )
    return [name for name, value in values if value in (None, "")]


def _safe_to_repair(row: dict[str, Any]) -> bool:
    return not (
        row.get("official_result") is True
        or row.get("manual_official_proof_registered") is True
        or row.get("verification_state") == "manual_official_proof_matched"
    )


def clean_registry() -> dict[str, Any]:
    stats = {
        "ok": True,
        "patch": PATCH_ID,
        "rows_seen": 0,
        "rows_changed": 0,
        "certifications_normalized": 0,
        "invalid_certifications_cleared": 0,
        "trusted_rows_skipped": 0,
    }
    with manual_photo.LOCK:
        registry = manual_photo._registry()
        rows = registry.get("registrations", [])
        for index, raw in enumerate(rows):
            if not isinstance(raw, dict):
                continue
            stats["rows_seen"] += 1
            row = dict(raw)
            company = _company(row)
            cert = _cert(row)
            if not company or not cert:
                continue
            if not _safe_to_repair(row):
                stats["trusted_rows_skipped"] += 1
                continue

            normalized = ocr_boost.normalize_cert(company, cert)
            changed = False
            if normalized:
                if normalized != cert or row.get("certification_id") != normalized:
                    old_cert = cert
                    row["certification_id"] = normalized
                    if manual_photo._normalized_cert(row.get("ocr_certification_id")) == old_cert:
                        row["ocr_certification_id"] = normalized
                    row["updated_at"] = manual_photo._now()
                    reasons = set(row.get("quarantine_reasons") or [])
                    reasons.discard("legacy_invalid_ocr_cert_removed")
                    reasons.add("legacy_ocr_cert_normalized_v149")
                    row["quarantine_reasons"] = sorted(reasons)
                    row["official_reference_url"] = None
                    row["manual_identity_complete"] = bool(
                        row.get("company") and row.get("claimed_grade") is not None and normalized
                    )
                    row["missing_identity_fields"] = _missing_fields(row)
                    changed = True
                    stats["certifications_normalized"] += 1
            else:
                # A supported grader plus a certification that the current
                # grader-specific parser rejects is not allowed to remain an
                # identity-complete, learnable-looking row.
                row["certification_id"] = ""
                if manual_photo._normalized_cert(row.get("ocr_certification_id")) == cert:
                    row["ocr_certification_id"] = None
                row.update({
                    "updated_at": manual_photo._now(),
                    "official_result": False,
                    "official_reference_url": None,
                    "training_eligible": False,
                    "raw_grade_calibration_eligible": False,
                    "manual_identity_complete": False,
                    "status": "pending_manual_official_verification",
                    "verification_state": "manual_input_required",
                    "learning_eligibility": "quarantine_only_until_manual_identity_confirmed",
                })
                reasons = set(row.get("quarantine_reasons") or [])
                reasons.update({"legacy_invalid_ocr_cert_removed", "manual_identity_required"})
                row["quarantine_reasons"] = sorted(reasons)
                row["missing_identity_fields"] = _missing_fields(row)
                changed = True
                stats["invalid_certifications_cleared"] += 1

            if changed:
                rows[index] = row
                stats["rows_changed"] += 1

        if stats["rows_changed"]:
            registry["registrations"] = rows
            manual_photo._save_registry(registry)
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="레거시 OCR 인증번호 안전 정리")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    result = clean_registry()
    if not args.quiet:
        print(json.dumps(result, ensure_ascii=False))
        if result["rows_changed"]:
            print(
                f"[OK] 레거시 OCR 인증번호 정리: 보정 {result['certifications_normalized']}건 · "
                f"무효값 제거 {result['invalid_certifications_cleared']}건"
            )
        else:
            print("[OK] 레거시 OCR 인증번호 정리: 변경 없음")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
