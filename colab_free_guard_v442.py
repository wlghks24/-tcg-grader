#!/usr/bin/env python3
"""V442 guard for optional Google Colab Free acceleration.

Colab is never required for tablet operation and never auto-promotes outputs.
The guard cannot know Google's account-specific free quota; it enforces a local
budget and forbids paid/billing/keep-alive behavior.
"""
from __future__ import annotations
import argparse, hashlib, json, math, os, time
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parent
POLICY_PATH=ROOT/"COLAB_FREE_POLICY_V442.json"
NOTEBOOK_PATH=ROOT/"TCG_GRADER_COLAB_FREE_V442.ipynb"
NOTEBOOK_MANIFEST=ROOT/"COLAB_NOTEBOOK_MANIFEST_V442.json"

def _strict(path:Path)->Any:
    return json.loads(path.read_text(encoding="utf-8"),parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))

def load_policy(path:Path=POLICY_PATH)->dict[str,Any]:
    data=_strict(path)
    if not isinstance(data,dict): raise ValueError("policy must be object")
    validate_policy(data)
    return data

def validate_policy(p:dict[str,Any])->None:
    if p.get("schema_version")!=1 or p.get("version")!="v442": raise ValueError("policy version")
    if p.get("provider")!="Google Colab Free" or p.get("free_only") is not True: raise ValueError("free provider policy")
    forbidden_true=("paid_features_allowed","compute_units_purchase_allowed","gcp_billing_project_allowed",
                    "auto_reconnect_keepalive_allowed","background_server_allowed","github_write_allowed",
                    "tablet_auto_apply_allowed","drive_code_execution_allowed")
    if any(p.get(k) is not False for k in forbidden_true): raise ValueError("forbidden capability enabled")
    required_true=("manual_session_start_required","candidate_results_only")
    if any(p.get(k) is not True for k in required_true): raise ValueError("required guard disabled")
    lim=p.get("limits")
    if not isinstance(lim,dict): raise ValueError("limits")
    ints=("max_session_minutes","reserve_stop_minutes","max_single_job_minutes","max_input_bytes","max_output_bytes","max_candidate_files","checkpoint_interval_minutes")
    if any(type(lim.get(k)) is not int or lim[k]<=0 for k in ints): raise ValueError("invalid limits")
    if lim["max_session_minutes"]>120 or lim["max_single_job_minutes"]>45: raise ValueError("free budget too large")
    if lim["reserve_stop_minutes"]>=lim["max_session_minutes"]: raise ValueError("reserve")
    hw=p.get("hardware") or {}
    if hw.get("gpu_optional") is not True or hw.get("cpu_fallback_required") is not True or hw.get("require_paid_accelerator") is not False:
        raise ValueError("hardware policy")
    ratio=hw.get("stop_if_memory_pressure_ratio_gte")
    if not isinstance(ratio,(int,float)) or isinstance(ratio,bool) or not math.isfinite(float(ratio)) or not .5<=float(ratio)<1:
        raise ValueError("memory ratio")

def session_budget(start_monotonic:float, policy:dict[str,Any], now_monotonic:float|None=None)->dict[str,Any]:
    now=time.monotonic() if now_monotonic is None else float(now_monotonic)
    elapsed=max(0.0,(now-float(start_monotonic))/60.0)
    lim=policy["limits"]; stop_at=float(lim["max_session_minutes"]-lim["reserve_stop_minutes"])
    remaining=max(0.0,stop_at-elapsed)
    return {"elapsed_minutes":round(elapsed,3),"remaining_work_minutes":round(remaining,3),
            "must_stop":remaining<=0.0,"hard_session_minutes":lim["max_session_minutes"]}

def can_start_job(start_monotonic:float,estimated_minutes:float,input_bytes:int,policy:dict[str,Any],now_monotonic:float|None=None)->tuple[bool,str]:
    if not isinstance(input_bytes,int) or isinstance(input_bytes,bool) or input_bytes<0 or input_bytes>policy["limits"]["max_input_bytes"]:
        return False,"INPUT_BUDGET"
    try: est=float(estimated_minutes)
    except (TypeError,ValueError): return False,"ESTIMATE_INVALID"
    if not math.isfinite(est) or est<=0 or est>policy["limits"]["max_single_job_minutes"]: return False,"JOB_BUDGET"
    b=session_budget(start_monotonic,policy,now_monotonic)
    if b["must_stop"] or est>b["remaining_work_minutes"]: return False,"SESSION_BUDGET"
    return True,"OK"

def notebook_sha256(path:Path=NOTEBOOK_PATH)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def audit_notebook(path:Path=NOTEBOOK_PATH,manifest_path:Path=NOTEBOOK_MANIFEST)->dict[str,Any]:
    nb=_strict(path); mf=_strict(manifest_path)
    if nb.get("nbformat")!=4 or not isinstance(nb.get("cells"),list): raise ValueError("notebook schema")
    digest=notebook_sha256(path)
    if mf.get("sha256")!=digest or mf.get("file")!=path.name: raise ValueError("notebook digest")
    code="\n".join("".join(c.get("source",[])) for c in nb["cells"] if c.get("cell_type")=="code")
    forbidden=("git push","gh auth","compute units","colab pro","gcloud billing","while true","while True","keepalive","keep-alive")
    hits=[x for x in forbidden if x.casefold() in code.casefold()]
    if hits: raise ValueError("forbidden notebook behavior:"+",".join(hits))
    return {"ok":True,"sha256":digest,"cells":len(nb["cells"])}

def self_test()->None:
    p=load_policy()
    ok,why=can_start_job(0,10,1024,p,now_monotonic=60)
    assert ok and why=="OK"
    ok,why=can_start_job(0,40,1024,p,now_monotonic=60)
    assert not ok and why=="JOB_BUDGET"
    assert session_budget(0,p,now_monotonic=70*60)["must_stop"] is True

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--self-test",action="store_true");ap.add_argument("--audit-notebook",action="store_true");a=ap.parse_args()
    try:
        if a.self_test:self_test()
        if a.audit_notebook:print(json.dumps(audit_notebook(),separators=(",",":")))
        if not a.self_test and not a.audit_notebook:print(json.dumps(load_policy(),ensure_ascii=False,separators=(",",":")))
        return 0
    except Exception as exc:
        print(json.dumps({"ok":False,"error":type(exc).__name__},separators=(",",":")));return 2
if __name__=="__main__":raise SystemExit(main())
