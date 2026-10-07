#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,re,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
ROOT=Path(__file__).resolve().parent
POLICY_PATH=ROOT/"GITHUB_FREE_USAGE_POLICY_V444.json"
RUN_RE=re.compile(r"(?m)^\s*runs-on:\s*([^#\n]+)")
def load(path:Path=POLICY_PATH)->dict[str,Any]:
 d=json.loads(path.read_text(encoding="utf-8"))
 if d.get("version")!="v444" or d.get("schema_version")!=1:raise ValueError("policy")
 return d
def _runner_value(raw:str)->list[str]:
 s=raw.strip().strip("'\"")
 if s.startswith("[") and s.endswith("]"):
  return [x.strip().strip("'\"") for x in s[1:-1].split(",") if x.strip()]
 return [s]
def audit_workflows(root:Path,policy:dict[str,Any])->dict[str,Any]:
 allowed=set(policy["allowed_standard_runners"]);bad=[];seen=[]
 for p in sorted((root/".github/workflows").glob("*.y*ml")):
  txt=p.read_text(encoding="utf-8")
  for m in RUN_RE.finditer(txt):
   for label in _runner_value(m.group(1)):
    seen.append((p.name,label))
    if "${{" in label or label=="self-hosted" or label not in allowed:bad.append({"file":p.name,"runner":label})
 return {"ok":not bad,"runner_count":len(seen),"violations":bad}
def evaluate(*,visibility:str,artifact_bytes:int,cache_bytes:int,billing:dict[str,Any]|None,policy:dict[str,Any])->dict[str,Any]:
 st=policy["storage"];reasons=[]
 if artifact_bytes>=st["artifact_hard_bytes"] or cache_bytes>=st["cache_hard_bytes"]:return {"status":"QUOTA_WAIT","reasons":["STORAGE_HARD_LIMIT"],"run_nonessential":False}
 if artifact_bytes>=st["artifact_soft_bytes"]:reasons.append("ARTIFACT_SOFT_LIMIT")
 if cache_bytes>=st["cache_soft_bytes"]:reasons.append("CACHE_SOFT_LIMIT")
 if visibility=="public":
  return {"status":"DEGRADED_STORAGE" if reasons else "READY_PUBLIC_STANDARD","reasons":reasons,"run_nonessential":not reasons,"minutes_remaining":None}
 if visibility!="private":return {"status":"HOLD","reasons":["VISIBILITY_UNKNOWN"],"run_nonessential":False}
 if not isinstance(billing,dict):return {"status":"QUOTA_WAIT","reasons":["PRIVATE_BILLING_USAGE_UNKNOWN"],"run_nonessential":False}
 used=0.0
 for row in billing.get("usageItems",[]):
  if not isinstance(row,dict) or str(row.get("product","")).casefold()!="actions" or str(row.get("unitType","")).casefold()!="minutes":continue
  try:used+=float(row.get(policy["private_fallback"]["usage_metric"],0) or 0)
  except (TypeError,ValueError):pass
 inc=float(policy["private_fallback"]["conservative_included_minutes"]);reserve=float(policy["private_fallback"]["reserve_minutes"]);rem=max(0.0,inc-used)
 if rem<=reserve:return {"status":"QUOTA_WAIT","reasons":["PRIVATE_MINUTES_RESERVE"],"run_nonessential":False,"minutes_remaining":round(rem,2)}
 return {"status":"DEGRADED_STORAGE" if reasons else "READY_PRIVATE","reasons":reasons,"run_nonessential":not reasons,"minutes_remaining":round(rem,2)}
def _get(url:str,token:str|None)->dict[str,Any]:
 h={"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2026-03-10"}
 if token:h["Authorization"]="Bearer "+token
 with urllib.request.urlopen(urllib.request.Request(url,headers=h),timeout=20) as r:return json.load(r)
def _paged_sum(url:str,field:str,token:str)->int:
 total=0
 for page in range(1,51):
  sep="&" if "?" in url else "?"
  d=_get(f"{url}{sep}per_page=100&page={page}",token);rows=d.get(field,[])
  if not isinstance(rows,list):break
  total+=sum(int(x.get("size_in_bytes",0) or 0) for x in rows if isinstance(x,dict) and not x.get("expired",False))
  if len(rows)<100:break
 return total
def live(policy:dict[str,Any])->dict[str,Any]:
 repo=os.environ["GITHUB_REPOSITORY"];tok=os.environ.get("GITHUB_TOKEN","");owner=repo.split("/",1)[0]
 meta=_get("https://api.github.com/repos/"+repo,tok);vis=str(meta.get("visibility") or ("private" if meta.get("private") else "public"))
 artifacts=_paged_sum("https://api.github.com/repos/"+repo+"/actions/artifacts","artifacts",tok)
 caches=_paged_sum("https://api.github.com/repos/"+repo+"/actions/caches","actions_caches",tok)
 billing=None;bt=os.environ.get("GH_BILLING_READ_TOKEN","")
 if vis=="private" and bt:
  now=datetime.now(timezone.utc);billing=_get(f"https://api.github.com/users/{owner}/settings/billing/usage/summary?year={now.year}&month={now.month}&product=Actions",bt)
 out=evaluate(visibility=vis,artifact_bytes=artifacts,cache_bytes=caches,billing=billing,policy=policy)
 out.update({"visibility":vis,"artifact_bytes":artifacts,"cache_bytes":caches,"workflow_audit":audit_workflows(ROOT,policy)})
 if not out["workflow_audit"]["ok"]:out={"status":"HOLD","reasons":["NON_STANDARD_OR_UNKNOWN_RUNNER"],"run_nonessential":False,**{k:v for k,v in out.items() if k not in ("status","reasons","run_nonessential")}}
 return out
def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument("--audit-workflows",action="store_true");ap.add_argument("--live",action="store_true");a=ap.parse_args();p=load()
 out=live(p) if a.live else audit_workflows(ROOT,p)
 print(json.dumps(out,ensure_ascii=False,separators=(",",":")))
 if a.live and out.get("status") in {"QUOTA_WAIT","HOLD"}:return 3
 return 0 if out.get("ok",True) else 2
if __name__=="__main__":raise SystemExit(main())
