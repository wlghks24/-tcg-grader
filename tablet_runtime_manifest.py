#!/usr/bin/env python3
"""Single source of truth for the Android tablet runtime bundle."""
from __future__ import annotations
import argparse, json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
ACTIVE_RUNTIME_FILES=(
"index.html","safe_runtime.py","runtime_sre_metrics.py","collection_runtime_health.py","ai_runtime_model_guard.py","tablet_runtime_manifest.py","TABLET_SCHEDULED_UPDATE.sh",
"grading_accuracy_v99.py","card_grading_valuation.py","card_identity_recognition.py","server_security_guard.py",
"quality_review_policy.py","quality_review_policy_v2.json",
"auto_repair_engine.py","auto_update_all.py","collection_job_contract.py","collector_self_healing.py","tcg_code_repair_learning.py",
"tcg_updater.py","tcg_updater_v135.py","runtime_bundle_guard_v143.py","update_releases.py",
"update_market_watch.py","update_market_prices.py","update_market_prices_parallel_v260.py","wyyyes_market_source.py","update_promo_events.py","update_purchase_sources.py",
"update_exchange_rates.py","grading_company_watch.py","grading_company_watch_resilient.py","graded_photo_multi_source.py","graded_photo_manual_pair_queue.py",
"collection_verification_gate.py","collection_verification_gate_contextual.py","tablet_collection_publish.py","tablet_collection_publish_contextual.py",
"tablet_gdrive_sync.py","tablet_gdrive_sync_hardening.py","tablet_gdrive_sync_hardening_contextual.py","tablet_gdrive_sync_perf_v262.py","TABLET_GDRIVE_SYNC.sh",
"grading_cert_verifier.py","manual_collection_mode.py","manual_graded_photo_registration.py",
"manual_dual_photo_registration.py","manual_dual_photo_bridge.js","manual_official_proof.py",
"ocr_accuracy_boost_v147.py","public_ocr_accuracy_boost_v147.py","ocr_front_back_fallback_v148.py",
"legacy_ocr_registry_cleanup_v149.py","release_tcg_port.py","multi_channel_agent.py","search_method_learning.py",
"verified_grade_learning_v135.py","verified_grade_learning_v135_safe.py","event_collection_hardening_v139.py",
"event_collection_hardening_v140.py","event_collection_hardening_v141.py","collection_learning_hardening_v142.py",
"collection_learning_hardening_v144.py","event_source_overlay_v144.py","event_source_expansion_v145.py",
"event_gap_learning.py","event_priority_watch.py","event_quick_watch.py","social_event_discovery.py",
"multi_route_event_discovery.py","adaptive_collection_learner.py","verified_collection_neural.py","verified_collection_job_neural.py","fan_social_learning.py",
# Browser assets are executable/visible parts of the tablet runtime too. Keep
# them in the fail-closed manifest so a partial checkout cannot pass startup
# merely because the Python backend still compiles.
"grading_vision_engine.js","grading_accuracy_v99.js","grading_probability_v292.js","card_identity_recognition.js","grade_market_flow.js","grade_market_flow.css","grading_costs_live.js","grading_costs_live.css","inventory_lookup.js","inventory_lookup.css",
"box_knowledge_stats.js","feature_category_nav.js","feature_category_nav.css","ui_app_shell_v272.js","ui_app_shell_v272.css","sw.js")
def audit(root:Path=ROOT,*,compile_python:bool=False)->dict:
    missing=[]; symlinks=[]; compile_errors=[]; checked_python=0
    for name in ACTIVE_RUNTIME_FILES:
        path=root/name
        if not path.is_file(): missing.append(name); continue
        if path.is_symlink(): symlinks.append(name); continue
        if compile_python and path.suffix.lower()==".py":
            checked_python+=1
            try: compile(path.read_text(encoding="utf-8",errors="strict"),name,"exec",dont_inherit=True)
            except (OSError,UnicodeError,SyntaxError,ValueError,OverflowError) as exc:
                compile_errors.append({"file":name,"error":type(exc).__name__,"line":getattr(exc,"lineno",None)})
    try:
        import quality_review_policy
        quality_policy=quality_review_policy.validate(root/"quality_review_policy_v2.json")
    except Exception as exc:
        quality_policy={"ok":False,"errors":[f"validator_error:{type(exc).__name__}"]}
    return {"ok":not missing and not symlinks and not compile_errors and bool(quality_policy.get("ok")),"schema_version":1,
            "active_file_count":len(ACTIVE_RUNTIME_FILES),"python_checked":checked_python,
            "missing":missing,"symlinks":symlinks,"compile_errors":compile_errors,"quality_policy":quality_policy}
def main()->int:
    p=argparse.ArgumentParser(); p.add_argument("--check",action="store_true"); p.add_argument("--compile",action="store_true")
    args=p.parse_args(); result=audit(compile_python=args.compile)
    print(json.dumps(result,ensure_ascii=False,separators=(",",":"))); return 0 if result["ok"] else 1
if __name__=="__main__": raise SystemExit(main())
