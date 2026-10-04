#!/usr/bin/env python3
"""Single source of truth for the Android tablet runtime bundle.

The tablet must not treat only the backend as "the runtime".  The control plane
(update/recovery/boot/verification/Drive sync), PWA entry assets, autonomy
controller and card/market modules are one deployable unit.  A partial checkout
therefore fails closed before startup.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONTROL_PLANE_SCHEMA_VERSION = 2

TABLET_CONTROL_PLANE_FILES = (
    "main",
    "ANDROID_RECOVER_UPDATE.sh",
    "ANDROID_UPDATE_AND_START.sh",
    "TABLET_SCHEDULED_UPDATE.sh",
    "ANDROID_AUTO_START_INSTALL.sh",
    "START_TCG_UPDATER_ANDROID.sh",
    "VERIFY_TABLET_FINAL.sh",
    "VERIFY_TABLET_RUNTIME.sh",
    "tablet_runtime_probe.py",
    "tablet_runtime_qa.py",
    "TABLET_GDRIVE_SYNC.sh",
    "TABLET_GDRIVE_SYNC_INSTALL.sh",
    "TABLET_COLLECT_AND_SEND.sh",
    "tablet_runtime_manifest.py",
)

TABLET_PWA_ENTRY_FILES = (
    "index.html",
    "manifest.webmanifest",
    "icon.svg",
    "sw.js",
    "feature_category_nav.js",
    "feature_category_nav.css",
    "ui_app_shell_v272.js",
    "ui_app_shell_v272.css",
    "tablet_autonomy_dashboard_v400.js",
    "tablet_autonomy_dashboard_v400.css",
)

_ACTIVE_RUNTIME_BODY = (
    "safe_runtime.py","runtime_sre_metrics.py","collection_runtime_health.py","ai_runtime_model_guard.py",
    "tablet_autonomous_evolution_v371.py","tablet_autonomous_evolution_v372.py","tablet_autonomous_evolution_v373.py",
    "tablet_autonomous_evolution_v374.py","tablet_autonomous_evolution_v375.py","tablet_autonomous_evolution_v376.py",
    "tablet_autonomous_evolution_v377.py","tablet_autonomous_evolution_v378.py","tablet_autonomous_evolution_v379.py",
    "tablet_autonomous_evolution_v380.py","tablet_autonomous_evolution_v381.py","tablet_autonomous_evolution_v382.py",
    "tablet_autonomous_evolution_v385.py","tablet_autonomous_evolution_v386.py","tablet_autonomous_evolution_v387.py",
    "tablet_autonomous_evolution_v388.py","tablet_autonomous_evolution_v390.py","tablet_autonomous_evolution_v391.py",
    "tablet_autonomous_evolution_v397.py","tablet_autonomous_evolution_v398.py","tablet_autonomous_evolution_v399.py",
    "tablet_autonomous_evolution_v400.py","screen_policy_neural_v401.py","verified_neural_self_refine.py",
    "grading_accuracy_v99.py","card_grading_valuation.py","card_identity_recognition.py","server_security_guard.py",
    "multi_market_price_collector.py","quality_review_policy.py","quality_review_policy_v2.json",
    "auto_repair_engine.py","auto_update_all.py","collection_job_contract.py","collector_self_healing.py",
    "tcg_code_repair_learning.py","tcg_updater.py","tcg_updater_v135.py","runtime_bundle_guard_v143.py",
    "tcg_game_registry.py","tcg_game_registry.json","promoted_tcg_source_monitor_v413.py","update_releases.py","update_market_watch.py","update_market_prices.py","box_hit_market_discovery.py","update_market_prices_parallel_v260.py",
    "wyyyes_market_source.py","update_promo_events.py","update_purchase_sources.py","update_exchange_rates.py",
    "grading_company_watch.py","grading_company_watch_resilient.py","graded_photo_multi_source.py",
    "graded_photo_manual_pair_queue.py","collection_verification_gate.py","collection_verification_gate_contextual.py",
    "tablet_collection_publish.py","tablet_collection_publish_contextual.py","tablet_gdrive_sync.py",
    "tablet_gdrive_sync_hardening.py","tablet_gdrive_sync_hardening_contextual.py","tablet_gdrive_sync_perf_v262.py",
    "grading_cert_verifier.py","manual_collection_mode.py","manual_graded_photo_registration.py",
    "manual_dual_photo_registration.py","manual_dual_photo_bridge.js","manual_official_proof.py",
    "ocr_accuracy_boost_v147.py","public_ocr_accuracy_boost_v147.py","ocr_front_back_fallback_v148.py",
    "legacy_ocr_registry_cleanup_v149.py","release_tcg_port.py","multi_channel_agent.py","search_method_learning.py",
    "verified_grade_learning_v135.py","verified_grade_learning_v135_safe.py","event_collection_hardening_v139.py",
    "event_collection_hardening_v140.py","event_collection_hardening_v141.py","collection_learning_hardening_v142.py",
    "collection_learning_hardening_v144.py","event_source_overlay_v144.py","event_source_expansion_v145.py",
    "event_gap_learning.py","event_priority_watch.py","event_quick_watch.py","social_event_discovery.py",
    "multi_route_event_discovery.py","adaptive_collection_learner.py","verified_collection_neural.py",
    "verified_collection_job_neural.py","fan_social_learning.py",
    # Card-price/analysis cockpit: vision -> identity -> grading -> validation -> market.
    "grading_vision_engine.js","grading_accuracy_v99.js","card_metadata_classifier_v326.js","card_identity_recognition.js",
    "grade_market_flow.js","grade_market_flow.css","auto_market_center.js","auto_market_center.css",
    "multi_market_prices.js","multi_market_prices.css","auto_validation_flow.js","auto_validation_flow.css",
    "image_quality_guard.js","market_catalog_expander.js","grading_costs_live.js","grading_costs_live.css",
    "inventory_lookup.js","inventory_lookup.css","box_knowledge_stats.js","box_knowledge_stats.css",
    "graded_photo_dashboard.js","graded_photo_dashboard.css",
)

ACTIVE_RUNTIME_FILES = tuple(dict.fromkeys(
    TABLET_CONTROL_PLANE_FILES + TABLET_PWA_ENTRY_FILES + _ACTIVE_RUNTIME_BODY
))


def audit(root: Path = ROOT, *, compile_python: bool = False) -> dict:
    missing = []
    symlinks = []
    compile_errors = []
    checked_python = 0
    for name in ACTIVE_RUNTIME_FILES:
        path = root / name
        if not path.is_file():
            missing.append(name)
            continue
        if path.is_symlink():
            symlinks.append(name)
            continue
        if compile_python and path.suffix.lower() == ".py":
            checked_python += 1
            try:
                compile(path.read_text(encoding="utf-8", errors="strict"), name, "exec", dont_inherit=True)
            except (OSError, UnicodeError, SyntaxError, ValueError, OverflowError) as exc:
                compile_errors.append({
                    "file": name,
                    "error": type(exc).__name__,
                    "line": getattr(exc, "lineno", None),
                })
    try:
        import quality_review_policy
        quality_policy = quality_review_policy.validate(root / "quality_review_policy_v2.json")
    except Exception as exc:
        quality_policy = {"ok": False, "errors": [f"validator_error:{type(exc).__name__}"]}

    control_missing = [name for name in TABLET_CONTROL_PLANE_FILES if name in missing]
    pwa_missing = [name for name in TABLET_PWA_ENTRY_FILES if name in missing]
    return {
        "ok": not missing and not symlinks and not compile_errors and bool(quality_policy.get("ok")),
        "schema_version": 2,
        "control_plane_schema_version": CONTROL_PLANE_SCHEMA_VERSION,
        "active_file_count": len(ACTIVE_RUNTIME_FILES),
        "control_plane_file_count": len(TABLET_CONTROL_PLANE_FILES),
        "pwa_entry_file_count": len(TABLET_PWA_ENTRY_FILES),
        "python_checked": checked_python,
        "missing": missing,
        "control_plane_missing": control_missing,
        "pwa_entry_missing": pwa_missing,
        "symlinks": symlinks,
        "compile_errors": compile_errors,
        "quality_policy": quality_policy,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--compile", action="store_true")
    args = parser.parse_args()
    result = audit(compile_python=args.compile)
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
