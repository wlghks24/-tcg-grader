#!/usr/bin/env python3
from __future__ import annotations
import json
from datetime import datetime,timedelta,timezone
from pathlib import Path
from typing import Any

VALID={"READY","QUOTA_WAIT","CPU_ONLY","HOLD"}

def utcnow()->datetime:return datetime.now(timezone.utc)
def parse_time(v:Any)->datetime|None:
    try:
        d=datetime.fromisoformat(str(v).replace("Z","+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:return None

def default_state()->dict[str,Any]:
    return {"schema_version":1,"version":"v443","status":"READY","failure_count":0,
            "next_check_at":None,"last_probe_at":None,"last_reason":None,
            "resume_checkpoint":None,"last_gpu_available":None}

def load_state(path:Path)->dict[str,Any]:
    if not path.is_file():return default_state()
    try:data=json.loads(path.read_text(encoding="utf-8"))
    except Exception:return default_state()
    if not isinstance(data,dict) or data.get("schema_version")!=1:return default_state()
    out=default_state();out.update({k:data.get(k) for k in out})
    if out["status"] not in VALID:return default_state()
    if type(out["failure_count"]) is not int or out["failure_count"]<0:return default_state()
    return out

def save_state(path:Path,state:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    tmp.replace(path)

def should_probe(state:dict[str,Any],now:datetime|None=None)->bool:
    now=now or utcnow()
    if state.get("status")!="QUOTA_WAIT":return True
    nxt=parse_time(state.get("next_check_at"))
    return nxt is None or now>=nxt

def transition_after_probe(state:dict[str,Any],*,gpu_available:bool,backoff_minutes:list[int],now:datetime|None=None,reason:str|None=None)->dict[str,Any]:
    now=now or utcnow(); out=dict(state); out["last_probe_at"]=now.isoformat(); out["last_gpu_available"]=bool(gpu_available)
    if gpu_available:
        out.update({"status":"READY","failure_count":0,"next_check_at":None,"last_reason":"GPU_AVAILABLE"})
        return out
    n=max(1,int(out.get("failure_count") or 0)+1);out["failure_count"]=n
    idx=min(n-1,len(backoff_minutes)-1);wait=int(backoff_minutes[idx])
    out.update({"status":"QUOTA_WAIT","next_check_at":(now+timedelta(minutes=wait)).isoformat(),
                "last_reason":reason or "GPU_UNAVAILABLE_OR_FREE_CAPACITY_LIMIT"})
    return out

def mark_cpu_only(state:dict[str,Any],reason:str="CPU_SAFE_JOB")->dict[str,Any]:
    out=dict(state);out["status"]="CPU_ONLY";out["last_reason"]=reason;return out

def set_checkpoint(state:dict[str,Any],checkpoint:str|None)->dict[str,Any]:
    out=dict(state);out["resume_checkpoint"]=checkpoint;return out
