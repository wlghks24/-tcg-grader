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
    ],
    "five_company_grading": [
        "test_five_company_verification_policy.py",
        "verify_v109_final.py",
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
    "ai_auto_tracking": [
        "ai_auto_tracker.py",
        "test_ai_auto_tracker_v27.py",
        ".github/workflows/ai-auto-tracking.yml",
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
    "ai_auto_tracking": "python ai_auto_tracker.py --self-test",
}

DAILY_COMMANDS = {
    "domain_isolation": "python selfrefine_domain_boundary_guard.py",
    "peer_learning_gate": "python peer_learning_crosscheck_gate.py --self-test",
    "instagram_peer_export": "python -m instagram_tcg_content.peer_learning_export --self-test",
    "live_collection_refresh": "tcg_updater.update_cycle('scheduled-0600-audit')",
    "daily_audit": "python daily_collection_instagram_accuracy.py",
    "health_freshness": "MAX_HEALTH_AGE_SECONDS = 600",
    "critical_collector_diagnostics": "critical_collection_results",
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
