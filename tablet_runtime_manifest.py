#!/usr/bin/env python3
"""Single source of truth for the Android tablet runtime bundle."""
from __future__ import annotations
import argparse, ast, json, re
from pathlib import Path
ROOT=Path(__file__).resolve().parent
ACTIVE_RUNTIME_FILES=(
"index.html","safe_runtime.py","collection_runtime_health.py","tablet_runtime_manifest.py","TABLET_SCHEDULED_UPDATE.sh",
"quality_review_policy.py","quality_review_policy_v2.json",
"auto_repair_engine.py","auto_update_all.py","collection_job_contract.py","collector_self_healing.py","tcg_code_repair_learning.py",
"tcg_updater.py","tcg_updater_v135.py","grading_accuracy_v99.py","server_security_guard.py","runtime_bundle_guard_v143.py","update_releases.py",
"update_market_watch.py","update_market_prices.py","update_promo_events.py","update_purchase_sources.py",
"update_exchange_rates.py","grading_company_watch.py","graded_photo_multi_source.py","graded_photo_manual_pair_queue.py",
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
"grading_vision_engine.js","grading_accuracy_v99.js","card_identity_recognition.js",
"grade_market_flow.js","grade_market_flow.css","grading_costs_live.js","grading_costs_live.css",
"grading_proxy_costs.js","grading_proxy_costs.css","grading_total_cost.js","grading_total_cost.css",
"inventory_lookup.js","inventory_lookup.css","auto_market_center.js","auto_market_center.css",
"multi_market_prices.js","multi_market_prices.css","auto_validation_flow.js","auto_validation_flow.css",
"graded_photo_dashboard.js","graded_photo_dashboard.css","market_catalog_expander.js","image_quality_guard.js",
"box_knowledge_stats.js","box_knowledge_stats.css","feature_category_nav.js","feature_category_nav.css",
"purchase_ui_polish.css","ui_polish_v121.css","ui_tablet_refine_v122.css",
"manifest.webmanifest","icon.svg","vision_calibration.json","grading_company_updates.json","sw.js")

_INDEX_SCRIPT_RE=re.compile(r'<script\b[^>]*\bsrc=["\']([^"\']+)["\']',re.I)
_SW_CORE_RE=re.compile(r'const\s+CORE\s*=\s*\[(.*?)\]\s*;',re.S)
_QUOTED_RE=re.compile(r'["\']([^"\']+)["\']')
_CRITICAL_SW_SUFFIXES={".js",".css",".webmanifest",".svg"}
_CRITICAL_SW_DATA={"vision_calibration.json","grading_company_updates.json"}

def _normalize_local_asset(value:str)->str|None:
    text=str(value or "").strip()
    if not text or text.startswith(("http://","https://","//","data:","blob:","#")):
        return None
    text=text.split("?",1)[0].split("#",1)[0].strip()
    while text.startswith("./"):
        text=text[2:]
    text=text.lstrip("/")
    return text or None

def _index_script_assets(root:Path)->list[str]:
    source=(root/"index.html").read_text(encoding="utf-8",errors="strict")
    return sorted({asset for raw in _INDEX_SCRIPT_RE.findall(source) if (asset:=_normalize_local_asset(raw))})

def _service_worker_core_assets(root:Path)->list[str]:
    source=(root/"sw.js").read_text(encoding="utf-8",errors="strict")
    match=_SW_CORE_RE.search(source)
    if not match:
        raise ValueError("sw_core_unparseable")
    return sorted({asset for raw in _QUOTED_RE.findall(match.group(1)) if (asset:=_normalize_local_asset(raw))})

def _startup_local_python_imports(root:Path)->list[str]:
    source=(root/"tcg_updater.py").read_text(encoding="utf-8",errors="strict")
    tree=ast.parse(source,filename="tcg_updater.py")
    modules:set[str]=set()
    for node in tree.body:
        if isinstance(node,ast.Import):
            modules.update(alias.name.split(".",1)[0] for alias in node.names)
        elif isinstance(node,ast.ImportFrom) and node.module and node.level==0:
            modules.add(node.module.split(".",1)[0])
    files=[]
    for module in sorted(modules):
        name=f"{module}.py"
        if (root/name).is_file():
            files.append(name)
    return files

def _dependency_errors(root:Path)->list[str]:
    manifest=set(ACTIVE_RUNTIME_FILES)
    errors=[]
    try:
        for asset in _index_script_assets(root):
            if asset not in manifest:
                errors.append(f"index_script_not_manifest:{asset}")
    except (OSError,UnicodeError,ValueError) as exc:
        errors.append(f"index_dependency_scan:{type(exc).__name__}")
    try:
        for asset in _service_worker_core_assets(root):
            if Path(asset).suffix.lower() in _CRITICAL_SW_SUFFIXES or asset in _CRITICAL_SW_DATA:
                if asset not in manifest:
                    errors.append(f"sw_core_not_manifest:{asset}")
    except (OSError,UnicodeError,ValueError) as exc:
        errors.append(f"sw_dependency_scan:{type(exc).__name__}")
    try:
        for name in _startup_local_python_imports(root):
            if name not in manifest:
                errors.append(f"startup_import_not_manifest:{name}")
    except (OSError,UnicodeError,SyntaxError,ValueError) as exc:
        errors.append(f"startup_dependency_scan:{type(exc).__name__}")
    return sorted(set(errors))

def audit(root:Path=ROOT,*,compile_python:bool=False)->dict:
    missing=[]; symlinks=[]; compile_errors=[]; checked_python=0
    duplicates=sorted({name for name in ACTIVE_RUNTIME_FILES if ACTIVE_RUNTIME_FILES.count(name)>1})
    for name in ACTIVE_RUNTIME_FILES:
        path=root/name
        if not path.is_file(): missing.append(name); continue
        if path.is_symlink(): symlinks.append(name); continue
        if compile_python and path.suffix.lower()==".py":
            checked_python+=1
            try: compile(path.read_text(encoding="utf-8",errors="strict"),name,"exec",dont_inherit=True)
            except (OSError,UnicodeError,SyntaxError,ValueError,OverflowError) as exc:
                compile_errors.append({"file":name,"error":type(exc).__name__,"line":getattr(exc,"lineno",None)})
    dependency_errors=_dependency_errors(root) if not missing else []
    try:
        import quality_review_policy
        quality_policy=quality_review_policy.validate(root/"quality_review_policy_v2.json")
    except Exception as exc:
        quality_policy={"ok":False,"errors":[f"validator_error:{type(exc).__name__}"]}
    return {"ok":not missing and not symlinks and not compile_errors and not duplicates and not dependency_errors and bool(quality_policy.get("ok")),"schema_version":2,
            "active_file_count":len(ACTIVE_RUNTIME_FILES),"python_checked":checked_python,
            "missing":missing,"symlinks":symlinks,"compile_errors":compile_errors,"duplicates":duplicates,
            "dependency_errors":dependency_errors,"quality_policy":quality_policy}
def main()->int:
    p=argparse.ArgumentParser(); p.add_argument("--check",action="store_true"); p.add_argument("--compile",action="store_true")
    args=p.parse_args(); result=audit(compile_python=args.compile)
    print(json.dumps(result,ensure_ascii=False,separators=(",",":"))); return 0 if result["ok"] else 1
if __name__=="__main__": raise SystemExit(main())
