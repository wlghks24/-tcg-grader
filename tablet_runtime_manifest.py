#!/usr/bin/env python3
"""Single source of truth for the Android tablet runtime bundle."""
from __future__ import annotations
import argparse, json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
ACTIVE_RUNTIME_FILES=(
"index.html","safe_runtime.py","collection_runtime_health.py","tablet_runtime_manifest.py",
"auto_repair_engine.py","auto_update_all.py","collector_self_healing.py","tcg_code_repair_learning.py",
"tcg_updater.py","tcg_updater_v135.py","runtime_bundle_guard_v143.py","update_releases.py",
"update_market_watch.py","update_market_prices.py","update_promo_events.py","update_purchase_sources.py",
"update_exchange_rates.py","graded_photo_multi_source.py","graded_photo_manual_pair_queue.py",
"grading_cert_verifier.py","manual_collection_mode.py","manual_graded_photo_registration.py",
"manual_dual_photo_registration.py","manual_dual_photo_bridge.js","manual_official_proof.py",
"ocr_accuracy_boost_v147.py","public_ocr_accuracy_boost_v147.py","ocr_front_back_fallback_v148.py",
"legacy_ocr_registry_cleanup_v149.py","release_tcg_port.py","multi_channel_agent.py","search_method_learning.py",
"verified_grade_learning_v135.py","verified_grade_learning_v135_safe.py","event_collection_hardening_v139.py",
"event_collection_hardening_v140.py","event_collection_hardening_v141.py","collection_learning_hardening_v142.py",
"collection_learning_hardening_v144.py","event_source_overlay_v144.py","event_source_expansion_v145.py",
"event_gap_learning.py","event_priority_watch.py","event_quick_watch.py","social_event_discovery.py",
"multi_route_event_discovery.py","adaptive_collection_learner.py","fan_social_learning.py")
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
    return {"ok":not missing and not symlinks and not compile_errors,"schema_version":1,
            "active_file_count":len(ACTIVE_RUNTIME_FILES),"python_checked":checked_python,
            "missing":missing,"symlinks":symlinks,"compile_errors":compile_errors}
def main()->int:
    p=argparse.ArgumentParser(); p.add_argument("--check",action="store_true"); p.add_argument("--compile",action="store_true")
    args=p.parse_args(); result=audit(compile_python=args.compile)
    print(json.dumps(result,ensure_ascii=False,separators=(",",":"))); return 0 if result["ok"] else 1
if __name__=="__main__": raise SystemExit(main())
