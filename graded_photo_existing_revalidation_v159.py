#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Revalidate the already-saved graded-photo candidate corpus without new discovery.

This is the candidate-side companion to the manual front/back eight-zone recheck.
It re-probes the existing public image URLs, refreshes OCR/identity evidence,
re-runs bounded official verification, promotes only officially verified rows into
reference learning, and removes only repeat-confirmed unusable quarantine rows.

Temporary network/rate-limit/image-fetch failures are preserved for a later retry.
Verified references are never deleted here. Public candidate image bytes are not
persisted by this module.
"""
from __future__ import annotations

import json
from typing import Any

import graded_photo_multi_source as gp

ENGINE = "v159-existing-candidate-full-revalidation"


_TRANSIENT_IMAGE_ERRORS = (
    "httperror",
    "urlerror",
    "timeout",
    "timedout",
    "connection",
    "temporar",
    "rate",
    "429",
    "403",
    "404",
    "blocked",
    "challenge",
    "access",
)

_TRANSIENT_OCR_ERRORS = (
    "tesseract_not_installed",
    "tesseract_failed",
)


def _copy_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("records", []) if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, dict)]


def _row_key(row: dict[str, Any]) -> str:
    try:
        return gp._cleanup_candidate_key_v157(row)
    except Exception:
        return str(row.get("url") or row.get("image_url") or row.get("title") or "")[:500]


def _temporary_image_failure(row: dict[str, Any]) -> bool:
    error = str(row.get("image_probe_error") or "").strip().lower().replace(" ", "")
    if any(token.replace(" ", "") in error for token in _TRANSIENT_IMAGE_ERRORS):
        return True
    ocr_error = str(row.get("ocr_error") or "").strip().lower()
    return any(token in ocr_error for token in _TRANSIENT_OCR_ERRORS)


def _mark_retryable_image_failures(rows: list[dict[str, Any]]) -> int:
    kept = 0
    for row in rows:
        if str(row.get("image_probe_status") or "").lower() != "failed":
            continue
        if not _temporary_image_failure(row):
            continue
        # v157's hard-prune rule keys on exactly "failed". A network/tooling
        # failure is evidence that the row needs another attempt, not evidence
        # that the card/image is invalid.
        row["image_probe_status"] = "retryable_failed"
        row["image_revalidation_retryable"] = True
        kept += 1
    return kept


def _apply_current_disposition(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        conflicts = {str(value) for value in (row.get("evidence_conflicts") or []) if value}
        verified = bool(row.get("official_result") is True and not conflicts)
        reasons: list[str] = list(conflicts)
        cert = gp.normalize_cert(row.get("certification_id"))
        if not cert:
            reasons.append("certification_unresolved")
        if row.get("grade") is None:
            reasons.append("grade_unresolved")
        image_url = str(row.get("image_url") or "").strip()
        probe_status = str(row.get("image_probe_status") or "").lower()
        if not image_url:
            reasons.append("image_url_missing")
        elif probe_status == "failed":
            reasons.append("image_validation_failed")
        elif probe_status == "retryable_failed":
            reasons.append("image_validation_retryable")
        if not verified:
            reasons.append("official_verification_missing")
        row["quarantine_reasons"] = sorted(set(reasons))
        row["status"] = "verified_reference" if verified else "quarantine_candidate"
        row["learning_eligibility"] = "reference_learning_only" if verified else "not_eligible_unverified"


def _empty_result(payload: dict[str, Any]) -> dict[str, Any]:
    summary = dict(payload.get("summary") or {}) if isinstance(payload, dict) else {}
    summary.update(
        {
            "existing_candidate_revalidation": True,
            "existing_candidates_reviewed": 0,
            "existing_candidates_before": 0,
            "existing_candidates_after": 0,
            "verified_references": 0,
            "reference_learning_count": 0,
            "quarantined": 0,
            "quarantine_reviewed": 0,
            "quarantine_pruned": 0,
            "quarantine_retryable_kept": 0,
            "promoted_verified": 0,
            "promoted_learning": 0,
        }
    )
    return {"ok": True, "engine": ENGINE, "summary": summary, "cleanup_audit": []}


def revalidate_existing_candidates() -> dict[str, Any]:
    """Revalidate current ``graded_photo_candidates.json`` rows only.

    No marketplace/search discovery is started here. The existing rows are the
    complete review scope for this run, which lets the UI's "existing photos"
    button report exactly how many saved candidates were checked.
    """
    payload = gp._load(gp.OUT, {})
    previous_rows = _copy_rows(payload)
    if not previous_rows:
        result = _empty_result(payload)
        current = dict(payload) if isinstance(payload, dict) else {}
        current["engine"] = ENGINE
        current["created_at"] = gp._now()
        current["records"] = []
        current["summary"] = result["summary"]
        gp.atomic_write_json(gp.OUT, current, suffix=".existing-revalidation.tmp")
        return result

    rows = [dict(row) for row in previous_rows]
    before_total = len(rows)
    before_verified_keys = {
        _row_key(row)
        for row in previous_rows
        if row.get("official_result") is True and not row.get("evidence_conflicts")
    }
    old_summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    before_learning = int(old_summary.get("reference_learning_count", 0) or 0)

    # <=40 is the evidence module's explicit bounded ceiling. For the user's
    # current 21-row corpus this re-probes every primary image while still
    # allowing a few gallery alternates. Larger corpora remain bounded per run.
    probe_limit = min(40, max(before_total, 1))
    rows, image_stats = gp.enrich_rows(rows, limit=probe_limit, workers=2)
    transient_image_kept = _mark_retryable_image_failures(rows)

    registry = gp._registry()
    resolvable = sum(
        1
        for row in rows
        if str(row.get("company") or "").upper() in gp.COMPANIES
        and gp.normalize_cert(row.get("certification_id"))
        and row.get("grade") is not None
        and row.get("official_result") is not True
    )
    # Keep live official lookups bounded. 403/429/cooldown outcomes remain in
    # quarantine as retryable data; they are never proof for deletion.
    rows, official_stats = gp._official_verify_rows(rows, registry, max_live=min(12, max(5, resolvable)))
    rows = gp._resolve_cert_conflicts(rows)
    rows, image_conflict_stats = gp._resolve_image_conflicts(rows)
    official_stats.update(image_conflict_stats)
    rows = gp._apply_measurement_photo_quality(rows)
    _mark_retryable_image_failures(rows)
    _apply_current_disposition(rows)

    # Preserve v157's two-pass deletion gate. Since these rows already existed
    # before this explicit revalidation, their stored prior state is pass one;
    # this fresh probe/verification is pass two. Verified rows can never be
    # removed by the cleanup function.
    rows, cleanup_stats, cleanup_audit = gp._review_and_prune_quarantine_v157(rows, previous_rows)

    reference_learning = gp._save_reference_learning(rows)
    reference_summary = reference_learning.get("summary", {}) if isinstance(reference_learning, dict) else {}
    reference_count = int(reference_summary.get("reference_learning_count", 0) or 0)

    verified_count = sum(
        1 for row in rows if row.get("official_result") is True and not row.get("evidence_conflicts")
    )
    after_verified_keys = {
        _row_key(row)
        for row in rows
        if row.get("official_result") is True and not row.get("evidence_conflicts")
    }
    promoted_verified = len(after_verified_keys - before_verified_keys)
    promoted_learning = max(0, reference_count - before_learning)
    measurement_ready = sum(row.get("measurement_photo_ready") is True for row in rows)
    game_stats, company_stats = gp._aggregate_dimension_stats(rows)

    summary = dict(old_summary)
    summary.update(
        {
            "status": "ok",
            "existing_candidate_revalidation": True,
            "existing_candidates_reviewed": before_total,
            "existing_candidates_before": before_total,
            "existing_candidates_after": len(rows),
            "total_candidates": len(rows),
            "with_image_url": sum(bool(row.get("image_url")) for row in rows),
            "validated_images": sum(bool(row.get("image_validated")) for row in rows),
            "ocr_readable": sum(bool(row.get("ocr_label_text")) for row in rows),
            "certifications_resolved": sum(bool(gp.normalize_cert(row.get("certification_id"))) for row in rows),
            "verified_references": verified_count,
            "measurement_photo_ready": measurement_ready,
            "reference_learning_count": reference_count,
            "quarantined": len(rows) - verified_count,
            "quarantine_reviewed": int(cleanup_stats.get("reviewed", 0) or 0),
            "quarantine_pruned": int(cleanup_stats.get("pruned", 0) or 0),
            "quarantine_retryable_kept": int(cleanup_stats.get("retained_retryable", 0) or 0) + transient_image_kept,
            "quarantine_grace_kept": int(cleanup_stats.get("retained_grace", 0) or 0),
            "promoted_verified": promoted_verified,
            "promoted_learning": promoted_learning,
            "raw_grade_calibration_eligible": 0,
        }
    )

    current = dict(payload)
    current["schema_version"] = max(9, int(current.get("schema_version", 0) or 0))
    current["engine"] = ENGINE
    current["created_at"] = gp._now()
    current["records"] = rows
    current["summary"] = summary
    current["image_probe_stats"] = image_stats
    current["official_verification_stats"] = official_stats
    current["quarantine_cleanup_stats"] = cleanup_stats
    current["quarantine_cleanup_audit"] = cleanup_audit[:100]
    current["game_stats"] = game_stats
    current["company_stats"] = company_stats
    current["existing_candidate_revalidation"] = {
        "engine": ENGINE,
        "reviewed": before_total,
        "before": before_total,
        "after": len(rows),
        "verified": verified_count,
        "promoted_verified": promoted_verified,
        "reference_learning": reference_count,
        "promoted_learning": promoted_learning,
        "pruned": int(cleanup_stats.get("pruned", 0) or 0),
        "retryable_kept": summary["quarantine_retryable_kept"],
        "transient_image_failures_kept": transient_image_kept,
        "no_new_discovery": True,
    }
    policy = dict(current.get("policy") or {})
    policy.update(
        {
            "existing_revalidation_new_discovery": False,
            "verified_rows_never_pruned": True,
            "confirmed_unusable_two_pass_prune": True,
            "temporary_network_and_rate_limit_failures_preserved": True,
            "public_image_bytes_persisted": False,
        }
    )
    current["policy"] = policy
    gp.atomic_write_json(gp.OUT, current, suffix=".existing-revalidation.tmp")

    # Feed source/identifier learning only from the now-refreshed evidence. The
    # trust policy inside this function still permits verified feedback only.
    try:
        gp.record_official_feedback(rows)
    except Exception:
        pass

    return {
        "ok": True,
        "engine": ENGINE,
        "summary": summary,
        "cleanup_audit": cleanup_audit[:100],
        "image_probe_stats": image_stats,
        "official_verification_stats": official_stats,
    }


def main() -> int:
    result = revalidate_existing_candidates()
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
