#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Manual-only official verification policy for graded-photo workflows.

This patch is applied by runtime_bundle_guard_v143 during server startup.
It deliberately removes automatic PSA/BGS/CGC/TAG/BRG HTTP verification from:
- public graded-photo collection
- manual graded-photo registration background processing

The collector may still use already-persisted officially verified registry rows.
New/unverified rows are sent to the user-browser manual verification workflow.
After each in-process graded-photo collection, only certification-bearing front
+ back pairs are copied to the game-only manual-review folders. The grader stays
in metadata, but no PSA/BGS/CGC/TAG/BRG subfolder is created below each game.
"""
from __future__ import annotations

import os
from typing import Any

from graded_photo_evidence import normalize_cert
from grading_cert_verifier import lookup_url

PATCH_ID = 145
_APPLIED = False
_ORIGINAL_COLLECT = None


def _finite_grade(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if 1 <= number <= 10 else None


def _registry_only_official_verify_rows(rows: list[dict], registry: dict, max_live: int = 10):
    """Never make an official-site request; use only the persisted trusted registry."""
    import graded_photo_multi_source as collector

    stats = {
        "registry_matches": 0,
        "live_attempts": 0,
        "live_verified": 0,
        "conflicts": 0,
        "unavailable": 0,
        "deferred_by_cooldown": 0,
        "company_deferred": {company: 0 for company in collector.COMPANIES},
        "next_retry_seconds": None,
        "company_live_attempts": {company: 0 for company in collector.COMPANIES},
        "game_live_attempts": {game: 0 for game in collector.GAMES},
        "manual_verification_required": 0,
        "automatic_official_lookup_disabled": True,
    }
    output: list[dict] = []
    for raw in rows:
        item = dict(raw)
        company = str(item.get("company") or "").upper()
        cert = normalize_cert(item.get("certification_id"))
        grade = _finite_grade(item.get("grade"))
        if company not in collector.COMPANIES or not cert or grade is None:
            output.append(item)
            continue
        item["certification_id"] = cert
        registered = registry.get((company, cert))
        if registered is not None:
            registered_grade = _finite_grade(registered)
            if registered_grade is not None and abs(registered_grade - grade) < 1e-9:
                item.update({
                    "official_result": True,
                    "official_reference_url": lookup_url(company, cert),
                    "verification_method": "persisted_official_registry",
                    "official_grade": registered_grade,
                    "manual_official_verification_required": False,
                })
                stats["registry_matches"] += 1
            else:
                item["evidence_conflicts"] = sorted(set(
                    (item.get("evidence_conflicts") or []) + ["official_grade_conflict"]
                ))
                item["official_grade"] = registered_grade
                stats["conflicts"] += 1
            output.append(item)
            continue

        item.update({
            "official_result": False,
            "official_reference_url": lookup_url(company, cert),
            "verification_method": "manual_user_browser_required",
            "official_lookup_status": "automatic_official_lookup_disabled",
            "manual_official_verification_required": True,
        })
        stats["manual_verification_required"] += 1
        output.append(item)
    return output, stats


_registry_only_official_verify_rows._manual_only_policy = True


def _manual_only_process_registration_once(registration_id: str):
    """OCR the uploaded slab, then stop before any official-site network call."""
    import manual_graded_photo_registration as manual_photo

    now = manual_photo._now()
    with manual_photo.LOCK:
        registry = manual_photo._registry()
        index, row = manual_photo._find_row(registry, registration_id)
        row = dict(row)
        row.update({
            "verification_state": "ocr_running",
            "updated_at": now,
            "retry_after_seconds": None,
        })
        registry["registrations"][index] = row
        manual_photo._save_registry(registry)

    text, ocr_error, diagnostics, evidence, ocr_cache_hit = manual_photo._ocr_for_row(row)
    manual_company = str(row.get("company") or "").upper()
    manual_cert = manual_photo._normalized_cert(row.get("certification_id"))
    manual_grade = _finite_grade(row.get("claimed_grade"))
    ocr_company = str(evidence.get("company") or "").upper()
    if ocr_company not in manual_photo.COMPANIES:
        ocr_company = ""
    ocr_cert = manual_photo._normalized_cert(evidence.get("certification_id"))
    if len(ocr_cert) < 6:
        ocr_cert = ""
    ocr_grade = _finite_grade(evidence.get("grade"))

    conflicts: list[str] = []
    if manual_company and ocr_company and manual_company != ocr_company:
        conflicts.append("ocr_company_conflict")
    if manual_cert and ocr_cert and manual_cert != ocr_cert:
        conflicts.append("ocr_certification_conflict")
    if manual_grade is not None and ocr_grade is not None and abs(manual_grade - ocr_grade) > 1e-9:
        conflicts.append("ocr_grade_conflict")

    company = manual_company or ocr_company
    cert = manual_cert or ocr_cert
    grade = manual_grade if manual_grade is not None else ocr_grade
    missing = [
        name for name, value in (
            ("company", company),
            ("grade", grade),
            ("certification_id", cert),
        )
        if value in (None, "")
    ]
    now = manual_photo._now()

    with manual_photo.LOCK:
        registry = manual_photo._registry()
        index, current = manual_photo._find_row(registry, registration_id)
        current.update({
            "updated_at": now,
            "official_result": False,
            "training_eligible": False,
            "raw_grade_calibration_eligible": False,
            "retry_after_seconds": None,
            "ocr_label_text": str(text or "")[:1800],
            "ocr_error": ocr_error,
            "ocr_diagnostics": diagnostics,
            "ocr_cached_sha256": row.get("image_sha256"),
            "ocr_cache_hit": ocr_cache_hit,
            "ocr_company": ocr_company or None,
            "ocr_grade": ocr_grade,
            "ocr_certification_id": ocr_cert or None,
            "automatic_official_lookup_disabled": True,
        })

        if missing:
            current.update({
                "status": "pending_manual_official_verification",
                "verification_state": "manual_input_required",
                "missing_identity_fields": missing,
                "learning_eligibility": "quarantine_only_until_manual_official_match",
                "quarantine_reasons": sorted(set(
                    conflicts + ["ocr_identity_not_confirmed", "manual_identity_required"]
                )),
            })
        elif conflicts:
            current.update({
                "status": "quarantine",
                "verification_state": "manual_identity_conflict",
                "company": company,
                "claimed_grade": grade,
                "certification_id": cert,
                "missing_identity_fields": [],
                "official_reference_url": lookup_url(company, cert),
                "learning_eligibility": "quarantine_manual_identity_conflict",
                "quarantine_reasons": sorted(set(conflicts + ["manual_official_verification_required"])),
            })
        else:
            current.update({
                "status": "pending_manual_official_verification",
                "verification_state": "manual_official_verification_required",
                "company": company,
                "claimed_grade": grade,
                "certification_id": cert,
                "missing_identity_fields": [],
                "official_reference_url": lookup_url(company, cert),
                "learning_eligibility": "reference_only_pending_manual_official_verification",
                "quarantine_reasons": ["manual_official_verification_required"],
            })

        registry["registrations"][index] = current
        manual_photo._save_registry(registry)

    manual_photo._record_collection_gap(current, verified=False)
    return {
        "ok": True,
        "deferred": True,
        "manual_official_verification_required": True,
        "automatic_official_lookup_disabled": True,
        "registration": manual_photo._public_row(current),
    }


_manual_only_process_registration_once._manual_only_policy = True


def _collect_and_sync_manual_pairs():
    """Run the normal public collector, then export only cert+front/back pairs."""
    import graded_photo_multi_source as collector
    import graded_photo_manual_pair_queue as pair_queue

    original = _ORIGINAL_COLLECT or collector.collect
    payload = original()
    try:
        pair_status = pair_queue.sync_once()
        if isinstance(payload, dict):
            payload = dict(payload)
            summary = dict(payload.get("summary") or {})
            pair_summary = pair_status.get("summary") if isinstance(pair_status, dict) else {}
            summary["manual_certified_front_back_pairs"] = int((pair_summary or {}).get("total_manual_pairs", 0) or 0)
            summary["manual_pairs_newly_saved"] = int((pair_summary or {}).get("newly_saved_pairs", 0) or 0)
            summary["automatic_official_lookup_attempts"] = 0
            payload["summary"] = summary
            payload["manual_pair_queue"] = pair_status
    except (ImportError, OSError, ValueError, TypeError, TimeoutError):
        pass
    return payload


_collect_and_sync_manual_pairs._manual_only_policy = True


def apply() -> dict[str, Any]:
    global _APPLIED, _ORIGINAL_COLLECT
    import graded_photo_multi_source as collector
    import manual_graded_photo_registration as manual_photo

    os.environ["TCG_DISABLE_AUTO_GRADER_LOOKUP"] = "1"

    collector._official_verify_rows = _registry_only_official_verify_rows
    manual_photo._process_registration_once = _manual_only_process_registration_once
    if _ORIGINAL_COLLECT is None:
        _ORIGINAL_COLLECT = collector.collect
    collector.collect = _collect_and_sync_manual_pairs
    _APPLIED = True
    return {
        "ok": True,
        "patch": PATCH_ID,
        "automatic_official_lookup": False,
        "collector_uses_persisted_registry_only": True,
        "manual_registration_auto_official_lookup": False,
        "manual_user_browser_verification_required": True,
        "certification_front_back_pair_required": True,
        "grouped_by_game_only": True,
        "grader_subfolders_created": False,
        "front_back_pair_queue_module": "graded_photo_manual_pair_queue.py",
    }


def status() -> dict[str, Any]:
    import graded_photo_multi_source as collector
    import manual_graded_photo_registration as manual_photo
    return {
        "ok": bool(
            getattr(collector._official_verify_rows, "_manual_only_policy", False)
            and getattr(manual_photo._process_registration_once, "_manual_only_policy", False)
            and getattr(collector.collect, "_manual_only_policy", False)
        ),
        "patch": PATCH_ID,
        "applied": _APPLIED,
        "automatic_official_lookup": False,
        "environment_no_network_gate": os.environ.get("TCG_DISABLE_AUTO_GRADER_LOOKUP") == "1",
        "collector_manual_only": bool(getattr(collector._official_verify_rows, "_manual_only_policy", False)),
        "manual_registration_manual_only": bool(getattr(manual_photo._process_registration_once, "_manual_only_policy", False)),
        "collector_syncs_manual_pairs": bool(getattr(collector.collect, "_manual_only_policy", False)),
        "grouped_by_game_only": True,
        "grader_subfolders_created": False,
    }
