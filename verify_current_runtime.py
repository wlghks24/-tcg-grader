#!/usr/bin/env python3
"""Current-main verification entrypoint; historical v109 reports are audit-only."""
from __future__ import annotations
import argparse, json, os, shutil, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
from safe_runtime import atomic_write_json, diagnostic_exception
ROOT=Path(__file__).resolve().parent
REPORT=ROOT/"CURRENT_RUNTIME_VERIFICATION_REPORT.json"
def _now(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
def _run(name,command,timeout=900,optional=False):
    started=time.monotonic()
    try:
        p=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=timeout,check=False)
        ok=p.returncode==0; detail=(p.stdout if ok else (p.stderr or p.stdout))[-5000:].strip()
        return {"name":name,"ok":ok,"optional":optional,"seconds":round(time.monotonic()-started,3),"detail":detail}
    except (OSError,subprocess.SubprocessError) as exc:
        return {"name":name,"ok":bool(optional),"optional":optional,"seconds":round(time.monotonic()-started,3),"detail":diagnostic_exception(exc,600)}
def _commands():
    py=sys.executable
    rows=[
      ("repository_integrity",[py,"repository_integrity_guard.py"],240,False),
      ("active_tablet_runtime",[py,"tablet_runtime_manifest.py","--check","--compile"],120,False),
      ("collection_health_selftest",[py,"collection_runtime_health.py"],60,False),
      ("ai_model_guard_selftest",[py,"ai_runtime_model_guard.py"],60,False),
      ("ai_model_guard_regression",[py,"-m","unittest","-v","test_ai_runtime_model_guard_v269.py"],120,False),
      ("security_audit",[py,"security_self_audit.py","--no-memory","--fail-on","high"],240,False),
      ("security_hardening",[py,"security_hardening_apply.py","--check"],120,False),
      ("runtime_delivery",[py,"test_runtime_delivery_guards.py"],120,False),
      ("tablet_qa_integration",[py,"test_tablet_runtime_qa_integration.py"],120,False),
      ("standalone_v209",[py,"-m","unittest","-v","test_tablet_standalone_hardening_v209.py"],180,False),
      ("verified_neural_selfrefine",[py,"-m","unittest","-v","test_verified_neural_self_refine_v210.py"],180,False),
      ("verified_collection_neural",[py,"-m","unittest","-v","test_verified_collection_neural_v211.py"],180,False),
      ("verified_collection_job_neural",[py,"-m","unittest","-v","test_verified_collection_job_neural_v212.py"],180,False),
      ("ai_score_freshness_v270",[py,"-m","unittest","-v","test_ai_score_freshness_v270.py"],180,False),
      ("repair_ai_score_freshness_v271",[py,"-m","unittest","-v","test_repair_ai_score_freshness_v271.py"],180,False),
      ("ui_app_shell_v272",[py,"-m","unittest","-v","test_ui_app_shell_v272.py"],180,False),
      ("card_core_static_regressions",[py,"-m","unittest","-v",
       "test_card_core_provenance_v296.py","test_card_market_edition_v297.py",
       "test_card_probability_ui_v298.py","test_card_regression_gate_v299.py",
       "test_card_tablet_runtime_v300.py","test_card_edition_precision_v302.py","test_card_region_generation_precision_v306.py",
       "test_card_identity_market_precision_v309.py","test_card_region_conflict_failclosed_v318.py",
       "test_card_identity_ambiguity_v320.py","test_card_precision_v321.py","test_multi_market_price_collector.py","test_tablet_runtime_manifest_ui_assets_v254.py"],360,False),
      # v182 is an executable assert-based self-test, not a unittest.TestCase module.
      # Running it through `python -m unittest` yields 0 tests / rc=5 and makes
      # the aggregate verifier fail even when the runtime is healthy.
      ("runtime_resilience_v182",[py,"test_runtime_resilience_v182.py"],180,False),
      ("current_runtime_regressions",[py,"-m","unittest","-v","test_grading_hierarchy_v17.py",
       "test_ocr_multistage_v16.py","test_verified_grade_learning_v135_safe.py","test_collection_verification_gate.py",
       "test_multi_route_event_discovery.py","test_pokemon_run30_asia_recovery_v208.py",
       "test_information_lifecycle_archive_v209.py"],600,False)]
    if shutil.which("node"):
        rows += [("card_core_node_regressions",[py,"-m","unittest","-v",
                  "test_card_core_crosscheck_v291.py","test_card_core_crosscheck_v292.py","test_card_core_crosscheck_v295.py",
                  "test_pokemon_generation_display_v207.py","test_card_edition_precision_v302.py","test_card_region_generation_precision_v306.py",
                  "test_card_identity_market_precision_v309.py","test_card_region_conflict_failclosed_v318.py",
                  "test_card_identity_ambiguity_v320.py"],360,False),
                 ("browser_runtime",["node","verify_browser_runtime.js"],180,False),
                 ("camera_runtime",["node","verify_camera_runtime.js"],180,False),
                 ("service_worker_runtime",["node","verify_service_worker_runtime.js"],180,False)]
    elif os.environ.get("TCG_REQUIRE_NODE")=="1": rows.append(("node_required",["node","--version"],30,False))
    else: rows.append(("node_optional",[py,"-c","print('Node.js optional: skipped')"],30,True))
    return rows
def run(passes:int):
    passes=max(1,min(5,int(passes))); payload={"schema_version":1,"engine":"current-main-v321-edition-consensus-valuation-provenance","started_at":_now(),"passes":[],"ok":False}
    for number in range(1,passes+1):
        checks=[]
        for name,cmd,timeout,optional in _commands():
            row=_run(name,cmd,timeout,optional); checks.append(row)
            print(f"[{'PASS' if row['ok'] else 'FAIL'}] {number}/{passes} {name}",flush=True)
            if not row["ok"] and not row["optional"]: break
        pass_ok=all(r["ok"] or r["optional"] for r in checks)
        payload["passes"].append({"pass":number,"ok":pass_ok,"checks":checks})
        atomic_write_json(REPORT,{**payload,"updated_at":_now()},suffix=".current-verify.tmp")
        if not pass_ok: break
    payload["finished_at"]=_now(); payload["ok"]=len(payload["passes"])==passes and all(r["ok"] for r in payload["passes"])
    payload["successful_passes"]=sum(r["ok"] for r in payload["passes"]); payload["failed_passes"]=sum(not r["ok"] for r in payload["passes"])
    atomic_write_json(REPORT,payload,suffix=".current-verify.tmp"); return payload
def main():
    p=argparse.ArgumentParser(); p.add_argument("--passes",type=int,default=1); a=p.parse_args(); r=run(a.passes)
    print(json.dumps({k:r[k] for k in ("engine","ok","successful_passes","failed_passes")},ensure_ascii=False)); return 0 if r["ok"] else 1
if __name__=="__main__": raise SystemExit(main())
