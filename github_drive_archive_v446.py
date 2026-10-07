#!/usr/bin/env python3
"""V446 GitHub Actions artifact -> Google Drive archive safety model.

This module plans archival at >=50% artifact storage and validates public-safe
receipts. Actual cross-service transfer is performed by the connected archive
worker; GitHub deletion is allowed only after a verified Drive receipt exists.
"""
from __future__ import annotations
import argparse, json, math, re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parent
POLICY_PATH=ROOT/"GITHUB_DRIVE_ARCHIVE_POLICY_V446.json"
HEX64=re.compile(r"^[0-9a-f]{64}$")
SAFE_NAME=re.compile(r"[^A-Za-z0-9._-]+")

def load_policy(path:Path=POLICY_PATH)->dict[str,Any]:
    p=json.loads(path.read_text(encoding="utf-8"))
    if p.get("schema_version")!=1 or p.get("version")!="v446": raise ValueError("policy version")
    if p.get("repository")!="wlghks24/-tcg-grader": raise ValueError("repository")
    if p.get("trigger_bytes")!=int(p["github_plan_bytes"]*p["trigger_fraction"]): raise ValueError("trigger")
    if p.get("target_bytes")!=int(p["github_plan_bytes"]*p["target_fraction"]): raise ValueError("target")
    if not (0<p["target_fraction"]<p["trigger_fraction"]<1): raise ValueError("fractions")
    if p.get("artifact_delete_requires_verified_drive_receipt") is not True: raise ValueError("delete gate")
    if p.get("drive_file_id_must_not_be_published") is not True or p.get("drive_url_must_not_be_published") is not True:
        raise ValueError("privacy")
    return p

def _time(v:Any)->datetime:
    d=datetime.fromisoformat(str(v).replace("Z","+00:00"))
    if d.tzinfo is None:d=d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)

def safe_name(v:str)->str:
    s=SAFE_NAME.sub("_",str(v or "").strip()).strip("._-")
    return (s or "artifact")[:100]

def archive_filename(row:dict[str,Any],policy:dict[str,Any])->str:
    aid=int(row["id"]);return policy["archive_file_name_template"].format(artifact_id=aid,safe_name=safe_name(row.get("name","")))

def _valid_artifact(row:Any)->bool:
    if not isinstance(row,dict):return False
    try:
        return (type(row.get("id")) is int and row["id"]>0 and isinstance(row.get("name"),str) and bool(row["name"].strip())
                and type(row.get("size_in_bytes")) is int and row["size_in_bytes"]>=0 and isinstance(row.get("created_at"),str)
                and isinstance(row.get("expired"),bool))
    except Exception:return False

def plan_archive(artifacts:list[dict[str,Any]],total_bytes:int,policy:dict[str,Any],*,now:datetime|None=None)->dict[str,Any]:
    if type(total_bytes) is not int or total_bytes<0:raise ValueError("total_bytes")
    now=(now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    trigger=int(policy["trigger_bytes"]);target=int(policy["target_bytes"])
    if total_bytes<trigger:
        return {"status":"BELOW_TRIGGER","triggered":False,"total_bytes":total_bytes,"selected":[],"selected_bytes":0,
                "projected_bytes":total_bytes,"target_bytes":target}
    valid=[r for r in artifacts if _valid_artifact(r) and not r["expired"]]
    by_name=defaultdict(list)
    for r in valid:by_name[r["name"]].append(r)
    protected=set()
    keep=int(policy["keep_newest_per_name"])
    for rows in by_name.values():
        rows.sort(key=lambda x:(_time(x["created_at"]),x["id"]),reverse=True)
        protected.update(r["id"] for r in rows[:keep])
    eligible=[]
    min_age=float(policy["min_artifact_age_hours"])
    for r in valid:
        if r["id"] in protected:continue
        age=(now-_time(r["created_at"])).total_seconds()/3600
        if age<min_age:continue
        eligible.append(r)
    eligible.sort(key=lambda x:(_time(x["created_at"]),x["id"]))
    need=max(0,total_bytes-target);selected=[];selected_bytes=0
    for r in eligible:
        if len(selected)>=int(policy["max_batch_count"]):break
        if selected and selected_bytes+int(r["size_in_bytes"])>int(policy["max_batch_bytes"]):break
        selected.append({
            "artifact_id":r["id"],"name":r["name"],"size_in_bytes":r["size_in_bytes"],
            "created_at":r["created_at"],"expires_at":r.get("expires_at"),
            "archive_file_name":archive_filename(r,policy)
        })
        selected_bytes+=int(r["size_in_bytes"])
        if selected_bytes>=need:break
    status="ARCHIVE_REQUIRED" if selected else "HOLD_NO_ELIGIBLE_ARTIFACT"
    return {"status":status,"triggered":True,"total_bytes":total_bytes,"selected":selected,
            "selected_bytes":selected_bytes,"projected_bytes":max(0,total_bytes-selected_bytes),"target_bytes":target,
            "enough_to_target":selected_bytes>=need}

def build_public_receipt(*,artifact:dict[str,Any],archive_file_name:str,drive_readback_size:int,
                         sha256:str|None,uploaded_at:str,transfer_completed:bool=True,
                         drive_readback_verified:bool=True,cleanup_authorized:bool=True)->dict[str,Any]:
    out={"schema_version":1,"version":"v446","repository":"wlghks24/-tcg-grader",
         "artifact_id":int(artifact["id"]),"artifact_name":str(artifact["name"]),
         "artifact_size_in_bytes":int(artifact["size_in_bytes"]),"artifact_created_at":str(artifact["created_at"]),
         "archive_file_name":archive_file_name,"drive_readback_size":int(drive_readback_size),
         "uploaded_at":str(uploaded_at),"transfer_completed":bool(transfer_completed),
         "drive_readback_verified":bool(drive_readback_verified),"cleanup_authorized":bool(cleanup_authorized)}
    if sha256 is not None:out["sha256"]=sha256
    return out

def validate_receipt(r:dict[str,Any],policy:dict[str,Any])->dict[str,Any]:
    if not isinstance(r,dict) or r.get("schema_version")!=1 or r.get("version")!="v446":raise ValueError("receipt schema")
    if r.get("repository")!=policy["repository"]:raise ValueError("receipt repository")
    if any(k in r for k in ("drive_file_id","drive_url","file_id","url")):raise ValueError("private Drive locator leaked")
    if type(r.get("artifact_id")) is not int or r["artifact_id"]<=0:raise ValueError("artifact id")
    if not isinstance(r.get("artifact_name"),str) or not r["artifact_name"]:raise ValueError("artifact name")
    if type(r.get("artifact_size_in_bytes")) is not int or r["artifact_size_in_bytes"]<0:raise ValueError("artifact size")
    if type(r.get("drive_readback_size")) is not int or r["drive_readback_size"]<=0:raise ValueError("readback size")
    if not isinstance(r.get("archive_file_name"),str) or not r["archive_file_name"].endswith(".zip"):raise ValueError("archive name")
    _time(r.get("artifact_created_at"));_time(r.get("uploaded_at"))
    for k,v in policy["receipt_requires"].items():
        if r.get(k) is not v:raise ValueError("receipt gate:"+k)
    digest=r.get("sha256")
    if digest is not None and (not isinstance(digest,str) or not HEX64.fullmatch(digest)):raise ValueError("sha256")
    return r

def source_matches_receipt(meta:dict[str,Any],r:dict[str,Any])->bool:
    return (isinstance(meta,dict) and meta.get("id")==r.get("artifact_id") and meta.get("name")==r.get("artifact_name")
            and meta.get("size_in_bytes")==r.get("artifact_size_in_bytes") and meta.get("expired") is False)

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--verify-receipt");ap.add_argument("--self-test",action="store_true");a=ap.parse_args()
    try:
        p=load_policy()
        if a.verify_receipt:
            r=json.loads(Path(a.verify_receipt).read_text(encoding="utf-8"));validate_receipt(r,p);print(json.dumps({"ok":True,"artifact_id":r["artifact_id"]}))
        if a.self_test:
            now=datetime(2026,10,7,tzinfo=timezone.utc)
            rows=[{"id":1,"name":"x","size_in_bytes":100,"created_at":"2026-10-01T00:00:00Z","expired":False},
                  {"id":2,"name":"x","size_in_bytes":100,"created_at":"2026-10-06T23:00:00Z","expired":False}]
            q=dict(p);q.update({"trigger_bytes":150,"target_bytes":50,"max_batch_bytes":1000})
            plan=plan_archive(rows,200,q,now=now);assert [x["artifact_id"] for x in plan["selected"]]==[1]
        return 0
    except Exception as exc:
        print(json.dumps({"ok":False,"error":type(exc).__name__},separators=(",",":")));return 2
if __name__=="__main__":raise SystemExit(main())
