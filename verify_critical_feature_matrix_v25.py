#!/usr/bin/env python3
"""Fail-closed contract that keeps critical TCG functionality wired into full CI.

This does not replace the feature tests. It verifies that the exhaustive and
06:00 workflows continue to invoke every critical validator so a future edit
cannot silently remove coverage while leaving the workflow green.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXHAUSTIVE = ROOT / ".github/workflows/exhaustive-selfrefine-guard.yml"
DAILY = ROOT / ".github/workflows/daily-0600-collection-instagram-accuracy.yml"

FEATURE_FILES = {
    "grading_vision_1_4_8": [
        "grading_vision_engine.js",
        "vision_calibration.py",
        "verify_vision_runtime.js",
        "verify_vision_calibration.py",
        "test_grading_hierarchy_v17.py",
    ],
    "ocr_card_identity": [
        "card_identity_recognition.py",
        "ocr_multistage_regions_v16.py",
        "verify_card_identity_recognition.py",
        "test_ocr_selfrefine_v15.py",
        "test_ocr_multistage_v16.py",
        "card_identity_recognition.js",
        "verify_pokemon_generation_runtime.js",
        "test_pokemon_generation_display_v207.py",
    ],
    "ocr_extended_verification": [
        "library_slab_corpus.py",
        "manual_graded_photo_registration.py",
        "graded_photo_evidence.py",
        "ocr_accuracy_boost_v147.py",
        "ocr_front_back_fallback_v148.py",
        "grading_cert_verifier.py",
        "test_ocr_accuracy_boost_v147.py",
        "test_ocr_front_back_fallback_v148.py",
        "test_bgs_cert_ocr_v169.py",
        "test_cgc_cert_ocr_v170.py",
        "test_negative_proof_korean_ocr_v171.py",
        "test_psa_official_proof_grade_v187.py",
        "test_grading_cert_verifier.py",
        "test_grader_cert_ocr_profiles_v193.py",
    ],
    "five_company_grading": [
        "test_five_company_verification_policy.py",
        "verify_v109_final.py",
    ],
    "manual_verified_learning_gate": [
        "manual_graded_photo_registration.py",
        "manual_official_proof.py",
        "manual_official_verified_integration_v154.py",
        "manual_official_verify_bridge.js",
        "pending_official_candidate_v161.py",
        "pending_official_candidate_bridge_v161.js",
        "verified_slab_training_archive_v152.py",
        "verified_slab_raw_learning_v155.py",
        "verified_grade_learning_v135.py",
        "test_manual_graded_photo_registration.py",
        "test_manual_official_proof.py",
        "test_manual_official_verified_integration_v154.py",
        "test_pending_official_candidate_v161.py",
        "test_manual_official_verify_ui_v194.py",
        "test_verified_slab_training_archive_v152.py",
        "test_verified_slab_raw_learning_v155.py",
        "test_verified_grade_learning_v135.py",
    ],
    "browser_camera_pwa": [
        "index.html",
        "sw.js",
        "feature_category_nav.css",
        "feature_category_nav.js",
        "verify_feature_category_navigation.js",
        "test_feature_category_navigation_v26.py",
        "verify_browser_runtime.js",
        "verify_camera_runtime.js",
        "verify_service_worker_runtime.js",
        "verify_v107_runtime_integration.py",
    ],
    "market_collection": [
        "tcg_updater.py",
        "auto_update_all.py",
        "update_market_prices.py",
        "daily_collection_instagram_accuracy.py",
    ],
    "release_event_promo_collection": [
        "update_releases.py",
        "release_history_backfill.py",
        "release_parser_learning.py",
        "update_promo_events.py",
        "multi_route_event_discovery.py",
        "event_quick_watch.py",
        "event_source_expansion_v145.py",
        "test_release_history_coverage_v4.py",
        "test_release_parser_learning.py",
        "test_update_releases_parser_recovery.py",
        "test_promo_event_keyword_coverage_v5.py",
        "test_multi_route_event_discovery.py",
        "test_event_quick_watch.py",
        "test_event_source_expansion_v145.py",
        "test_collection_verification_gate.py",
        "test_pokemon_run30_asia_recovery_v208.py",
        "manual_event_evidence.json",
        "promo_events.json",
    ],
    "runtime_delivery": [
        "test_runtime_delivery_guards.py",
        "verify_link_runtime.py",
    ],
    "tablet_termux": [
        "VERIFY_TABLET_FINAL.sh",
        "ANDROID_UPDATE_AND_START.sh",
        "ANDROID_AUTO_START_INSTALL.sh",
        "START_TCG_UPDATER_ANDROID.sh",
    ],
    "selfrefine_isolation": [
        "main_selfrefine_gate.py",
        "selfrefine_domain_boundary_guard.py",
        "selfrefine_crosscheck_gate.py",
        "peer_learning_crosscheck_gate.py",
    ],
    "security_integrity": [
        "repository_integrity_guard.py",
        "security_self_audit.py",
    ],
    "code_map_internal": [
        "verify_code_map_internal.py",
        "code_map_intelligence.py",
        "code_map_fast_route.py",
        "test_code_map_fast_route_v195.py",
        "test_code_map_entrypoint_route_v196.py",
        "GRAPHIFY_UPDATE.sh",
        "GRAPHIFY_SELF_HEAL.py",
        "GRAPHIFY_AUDIT.py",
        "SETUP_GRAPHIFY_TERMUX.sh",
        "test_ai_auto_tracker.py",
        "test_market_ai_auto_tracker.py",
        ".github/workflows/graphify-integration-guard.yml",
    ],
}

EXHAUSTIVE_COMMANDS = {
    "feature_matrix_guard": "python verify_critical_feature_matrix_v25.py",
    "root_test_sweep": "for file in test_*.py; do",
    "instagram_nested_tests": "python -m unittest discover -v -s instagram_tcg_content -p 'test_*.py'",
    "release_gate": "python verify_all.py",
    "local_server_pwa": "python verify_v107_runtime_integration.py",
    "browser_runtime": "node verify_browser_runtime.js",
    "feature_category_navigation": "node verify_feature_category_navigation.js",
    "camera_runtime": "node verify_camera_runtime.js",
    "service_worker": "node verify_service_worker_runtime.js",
    "vision_runtime": "node verify_vision_runtime.js",
    "link_runtime": "python verify_link_runtime.py",
    "card_identity": "python verify_card_identity_recognition.py",
    "tablet": "TCG_FINAL_SKIP_HEAD_MATCH=1 bash VERIFY_TABLET_FINAL.sh",
    "security": "python security_self_audit.py --fail-on medium",
    "main_selfrefine": "python main_selfrefine_gate.py",
    "code_map_internal": "python verify_code_map_internal.py",
}

DAILY_COMMANDS = {
    "domain_isolation": "python selfrefine_domain_boundary_guard.py",
    "peer_learning_gate": "python peer_learning_crosscheck_gate.py --self-test",
    "instagram_peer_export": "python -m instagram_tcg_content.peer_learning_export --self-test",
    "live_collection_refresh": "tcg_updater.update_cycle('scheduled-0600-audit')",
    "daily_audit": "python daily_collection_instagram_accuracy.py",
    "health_freshness": "current_run_age_seconds",
    "critical_collector_diagnostics": "critical_collection_results",
    "code_map_internal": "python verify_code_map_internal.py",
}

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")

def verify() -> dict:
    failures: list[str] = []
    checked_files = 0

    for feature, paths in FEATURE_FILES.items():
        for relative in paths:
            checked_files += 1
            path = ROOT / relative
            if not path.is_file() or path.stat().st_size <= 0:
                failures.append(f"{feature}: missing critical file {relative}")

    exhaustive = _read(EXHAUSTIVE)
    for feature, fragment in EXHAUSTIVE_COMMANDS.items():
        if fragment not in exhaustive:
            failures.append(f"exhaustive coverage missing: {feature}: {fragment}")

    daily = _read(DAILY)
    for feature, fragment in DAILY_COMMANDS.items():
        if fragment not in daily:
            failures.append(f"06:00 coverage missing: {feature}: {fragment}")

    if "branches: [main]" not in daily:
        failures.append("06:00 workflow no longer covers main pushes")
    if "cron: '0 21 * * *'" not in daily:
        failures.append("06:00 KST schedule contract missing")
    if "403_429_bypass_allowed" not in daily:
        failures.append("06:00 safety contract no longer checks 403/429 bypass prohibition")

    return {
        "ok": not failures,
        "critical_feature_groups": len(FEATURE_FILES),
        "critical_files_checked": checked_files,
        "exhaustive_commands_checked": len(EXHAUSTIVE_COMMANDS),
        "daily_commands_checked": len(DAILY_COMMANDS),
        "failures": failures,
    }

def main() -> int:
    result = verify()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
