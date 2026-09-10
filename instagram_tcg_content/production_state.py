#!/usr/bin/env python3
"""Deterministic production state for the single canonical Instagram card-info router."""
from __future__ import annotations
import json, os, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from instagram_tcg_content.source_verification_engine import VERIFICATION_MODE, validate_production_verification_receipt

SCHEMA_VERSION=1
KST=timezone(timedelta(hours=9))
SCHEDULED_BASELINE_RUN_KIND="scheduled_weekly_monday_1900"
LEGACY_SCHEDULED_BASELINE_RUN_KIND="scheduled_10_30"
USER_REQUESTED_RECOVERY_RUN_KIND="user_requested_recovery"
COLLECTION_ONLY_RUN_KIND="collection_verify_refine_only"
RECOVERABLE_BLOCK_REASONS={"INSUFFICIENT_VERIFIED_FACTS","INSUFFICIENT_VERIFIED_FACTS_OBSERVED_POST_SLOT","ARTIFACT_GENERATION_FAILED","ARTIFACT_VALIDATION_FAILED","DELIVERY_REFERENCE_MISSING"}
EXPECTED_ARTIFACT_COUNT=6
EXPECTED_DIMENSIONS=[1080,1350]
REQUIRED_PRODUCTION_FIELDS={"production_date_kst","scheduled_slot_kst","actual_started_at_kst","router_branch","run_kind","snapshot_id","snapshot_hash","schema_version","payload_hashes","artifact_hashes","dimensions","caption_hash","hashtag_hash","x10_status","verification_receipt","delivery_reference_status","finalized_at"}

class StateIntegrityError(RuntimeError): pass

def empty_state()->dict[str,Any]: return {"schema_version":SCHEMA_VERSION,"run_locks":{},"production_records":{},"blocked_attempts":{},"catchup_attempts":{}}

def _parse_aware_iso(value:Any)->datetime|None:
    if not isinstance(value,str) or not value: return None
    try: dt=datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError: return None
    return dt if dt.tzinfo is not None else None

def is_weekly_production_slot(value:str)->bool:
    dt=_parse_aware_iso(value)
    if dt is None: return False
    local=dt.astimezone(KST)
    return local.weekday()==0 and local.hour==19 and local.minute==0 and local.second==0

def load_state(path:Path)->dict[str,Any]:
    if not path.exists(): return empty_state()
    try: raw=path.read_text(encoding="utf-8")
    except OSError as exc: raise StateIntegrityError("STATE_READ_FAILED") from exc
    try: value=json.loads(raw)
    except (ValueError,TypeError,UnicodeError) as exc: raise StateIntegrityError("STATE_CORRUPT_JSON") from exc
    if not isinstance(value,dict): raise StateIntegrityError("STATE_ROOT_NOT_OBJECT")
    if value.get("schema_version")!=SCHEMA_VERSION: raise StateIntegrityError("STATE_SCHEMA_MISMATCH")
    for key in ("run_locks","production_records","blocked_attempts","catchup_attempts"):
        if key not in value: value[key]={}
        elif not isinstance(value[key],dict): raise StateIntegrityError(f"STATE_FIELD_INVALID:{key}")
    for lock_key,row in value["run_locks"].items():
        if not isinstance(lock_key,str) or not isinstance(row,dict) or not isinstance(row.get("run_id"),str) or not row.get("run_id") or row.get("status") not in {"running","completed","failed"}: raise StateIntegrityError("STATE_RUN_LOCK_INVALID")
    for production_date,row in value["production_records"].items():
        if not isinstance(production_date,str) or not isinstance(row,dict) or row.get("finalized") is not True: raise StateIntegrityError("STATE_PRODUCTION_RECORD_INVALID")
        errors=validate_production_record(row, allow_legacy=True)
        if errors: raise StateIntegrityError("STATE_PRODUCTION_RECORD_INVALID:"+"; ".join(errors))
        if str(row.get("production_date_kst"))!=production_date: raise StateIntegrityError("STATE_PRODUCTION_DATE_KEY_MISMATCH")
    for production_date,row in value["blocked_attempts"].items():
        slot = _parse_aware_iso(row.get("scheduled_slot_kst")) if isinstance(row,dict) else None
        legacy_slot = bool(slot and slot.astimezone(KST).hour == 10 and slot.astimezone(KST).minute == 30)
        if not isinstance(production_date,str) or not isinstance(row,dict) or str(row.get("production_date_kst") or "")!=production_date or str(row.get("reason_code") or "") not in RECOVERABLE_BLOCK_REASONS or slot is None or (not is_weekly_production_slot(str(row.get("scheduled_slot_kst"))) and not legacy_slot) or _parse_aware_iso(row.get("recorded_at_kst")) is None or isinstance(row.get("verified_fact_count"),bool) or not isinstance(row.get("verified_fact_count"),int) or row.get("verified_fact_count")<0: raise StateIntegrityError("STATE_BLOCKED_ATTEMPT_INVALID")
    for production_date,count in value["catchup_attempts"].items():
        if not isinstance(production_date,str) or isinstance(count,bool) or not isinstance(count,int) or count<0: raise StateIntegrityError("STATE_CATCHUP_BUDGET_INVALID")
    return value

def write_state_atomic(path:Path,state:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True); tmp=None
    try:
        with tempfile.NamedTemporaryFile(mode="w",encoding="utf-8",dir=path.parent,prefix=f".{path.name}.",suffix=".tmp",delete=False) as h:
            json.dump(state,h,ensure_ascii=False,indent=2,sort_keys=True); h.write("\n"); h.flush(); os.fsync(h.fileno()); tmp=Path(h.name)
        tmp.replace(path)
    finally:
        if tmp is not None and tmp.exists(): tmp.unlink(missing_ok=True)

def make_lock_key(production_date_kst:str,scheduled_slot_kst:str,router_branch:str)->str: return "|".join((production_date_kst,scheduled_slot_kst,router_branch))
def acquire_run_lock(state:dict[str,Any],*,production_date_kst:str,scheduled_slot_kst:str,router_branch:str,run_id:str)->tuple[bool,str]:
    key=make_lock_key(production_date_kst,scheduled_slot_kst,router_branch); locks=state.setdefault("run_locks",{})
    if key in locks: return False,"DUPLICATE_RUN_SUPPRESSED"
    locks[key]={"run_id":run_id,"status":"running"}; return True,key
def release_run_lock(state:dict[str,Any],lock_key:str,*,status:str)->None:
    if status not in {"completed","failed"}: raise ValueError("lock release status must be completed or failed")
    row=state.setdefault("run_locks",{}).get(lock_key)
    if not isinstance(row,dict): raise KeyError(lock_key)
    row["status"]=status

def validate_production_record(record:dict[str,Any], *, allow_legacy: bool = False)->list[str]:
    errors=[]; missing=sorted(REQUIRED_PRODUCTION_FIELDS-set(record))
    if missing: return ["missing production fields: "+",".join(missing)]
    if record.get("schema_version")!=SCHEMA_VERSION: errors.append("schema_version mismatch")
    for field in ("scheduled_slot_kst","actual_started_at_kst","finalized_at"):
        if _parse_aware_iso(record.get(field)) is None: errors.append(f"{field} must be timezone-aware ISO-8601")
    run_kind=record.get("run_kind"); baseline_id=record.get("baseline_id")
    if run_kind==COLLECTION_ONLY_RUN_KIND: errors.append("collection-only run cannot be finalized as production")
    if run_kind==SCHEDULED_BASELINE_RUN_KIND:
        if not baseline_id: errors.append("weekly Monday 19:00 scheduled run requires baseline_id")
        if not is_weekly_production_slot(str(record.get("scheduled_slot_kst") or "")): errors.append("scheduled production baseline must be Monday 19:00 KST")
        if record.get("router_branch")!="WEEKLY_PRODUCTION": errors.append("scheduled production baseline requires WEEKLY_PRODUCTION router_branch")
    elif run_kind==LEGACY_SCHEDULED_BASELINE_RUN_KIND:
        if not allow_legacy: errors.append("legacy 10:30 scheduled run is read-only and cannot finalize")
        if not baseline_id: errors.append("legacy 10:30 scheduled run requires baseline_id")
    elif baseline_id: errors.append("non-weekly production run cannot create baseline_id")
    if run_kind==USER_REQUESTED_RECOVERY_RUN_KIND:
        if _parse_aware_iso(record.get("recovery_of_slot_kst")) is None: errors.append("user-requested recovery requires recovery_of_slot_kst")
        ev=record.get("recovery_request_evidence")
        if not isinstance(ev,str) or not ev.strip(): errors.append("user-requested recovery requires recovery_request_evidence")
    payload=record.get("payload_hashes"); artifacts=record.get("artifact_hashes"); dims=record.get("dimensions")
    if not isinstance(payload,list) or len(payload)!=6 or not all(isinstance(x,str) and x for x in payload): errors.append("payload_hashes must contain exactly 6 non-empty string values")
    if not isinstance(artifacts,list) or len(artifacts)!=6 or not all(isinstance(x,str) and x for x in artifacts): errors.append("artifact_hashes must contain exactly 6 non-empty string values")
    elif len(set(artifacts))!=6: errors.append("artifact_hashes must be unique")
    if not isinstance(dims,list) or len(dims)!=6: errors.append("dimensions must contain exactly 6 values")
    elif any(not isinstance(x,(list,tuple)) or list(x)!=EXPECTED_DIMENSIONS for x in dims): errors.append("all artifacts must be 1080x1350")
    if record.get("x10_status")!="pass": errors.append("x10_status must be pass")
    sid=record.get("snapshot_id"); sh=record.get("snapshot_hash")
    if not isinstance(sid,str) or not sid.strip(): errors.append("snapshot_id missing")
    if not isinstance(sh,str) or len(sh)!=64 or any(ch not in "0123456789abcdef" for ch in sh): errors.append("snapshot_hash must be lowercase SHA-256")
    if isinstance(sid,str) and sid.strip() and isinstance(sh,str):
        errors.extend(validate_production_verification_receipt(record.get("verification_receipt"),expected_snapshot_id=sid,expected_snapshot_fingerprint=sh))
        receipt=record.get("verification_receipt")
        if isinstance(receipt,dict) and receipt.get("verification_mode")!=VERIFICATION_MODE: errors.append("verification receipt must use Instagram-local evidence mode")
    if record.get("delivery_reference_status")!="verified": errors.append("delivery_reference_status must be verified")
    if not isinstance(record.get("caption_hash"),str) or not record.get("caption_hash"): errors.append("caption_hash missing")
    if not isinstance(record.get("hashtag_hash"),str) or not record.get("hashtag_hash"): errors.append("hashtag_hash missing")
    return errors

def finalized_record_for_date(state:dict[str,Any],production_date_kst:str)->dict[str,Any]|None:
    row=state.setdefault("production_records",{}).get(production_date_kst); return row if isinstance(row,dict) and row.get("finalized") is True else None
def record_blocked_production_attempt(state:dict[str,Any],*,production_date_kst:str,scheduled_slot_kst:str,reason_code:str,verified_fact_count:int,recorded_at_kst:str,detail:str="")->dict[str,Any]:
    if reason_code not in RECOVERABLE_BLOCK_REASONS: raise ValueError("UNSUPPORTED_BLOCK_REASON")
    if not is_weekly_production_slot(scheduled_slot_kst): raise ValueError("blocked production attempt must target Monday 19:00 KST")
    if _parse_aware_iso(recorded_at_kst) is None: raise ValueError("recorded_at_kst must be timezone-aware ISO-8601")
    if isinstance(verified_fact_count,bool) or not isinstance(verified_fact_count,int) or verified_fact_count<0: raise ValueError("verified_fact_count must be a non-negative integer")
    if finalized_record_for_date(state,production_date_kst): raise RuntimeError("FINALIZED_PRODUCTION_ALREADY_EXISTS")
    row={"production_date_kst":production_date_kst,"scheduled_slot_kst":scheduled_slot_kst,"reason_code":reason_code,"verified_fact_count":verified_fact_count,"recorded_at_kst":recorded_at_kst,"detail":str(detail or "")}; state.setdefault("blocked_attempts",{})[production_date_kst]=row; return row
def can_start_user_requested_recovery(state:dict[str,Any],production_date_kst:str,*,user_requested:bool)->tuple[bool,str]:
    if finalized_record_for_date(state,production_date_kst): return False,"FINALIZED_PRODUCTION_ALREADY_EXISTS"
    blocked=state.setdefault("blocked_attempts",{}).get(production_date_kst)
    if not isinstance(blocked,dict): return False,"NO_BLOCKED_BASELINE_EVIDENCE"
    if blocked.get("reason_code") not in RECOVERABLE_BLOCK_REASONS: return False,"BLOCK_REASON_NOT_RECOVERABLE"
    if user_requested is not True: return False,"USER_REQUEST_REQUIRED"
    if int(state.setdefault("catchup_attempts",{}).get(production_date_kst,0) or 0)>=1: return False,"CATCHUP_BUDGET_EXHAUSTED"
    return True,"USER_REQUESTED_RECOVERY_ALLOWED"
def can_start_catchup(state:dict[str,Any],production_date_kst:str)->tuple[bool,str]:
    if finalized_record_for_date(state,production_date_kst): return False,"FINALIZED_PRODUCTION_ALREADY_EXISTS"
    if int(state.setdefault("catchup_attempts",{}).get(production_date_kst,0) or 0)>=1: return False,"CATCHUP_BUDGET_EXHAUSTED"
    return True,"CATCHUP_ALLOWED"
def record_catchup_attempt(state:dict[str,Any],production_date_kst:str)->int:
    attempts=state.setdefault("catchup_attempts",{}); count=int(attempts.get(production_date_kst,0) or 0)+1; attempts[production_date_kst]=count; return count
def finalize_production(state:dict[str,Any],record:dict[str,Any])->None:
    errors=validate_production_record(record)
    if errors: raise ValueError("; ".join(errors))
    d=str(record["production_date_kst"]); records=state.setdefault("production_records",{})
    if isinstance(records.get(d),dict) and records[d].get("finalized") is True: raise RuntimeError("FINALIZED_PRODUCTION_ALREADY_EXISTS")
    records[d]={"finalized":True,**record}
def baseline_id_for_date(state:dict[str,Any],production_date_kst:str)->str|None:
    row=finalized_record_for_date(state,production_date_kst)
    if not row or row.get("run_kind") not in {SCHEDULED_BASELINE_RUN_KIND, LEGACY_SCHEDULED_BASELINE_RUN_KIND}: return None
    return str(row.get("baseline_id")) if row.get("baseline_id") else None

def self_test()->None:
    assert is_weekly_production_slot("2026-09-14T19:00:00+09:00")
    assert not is_weekly_production_slot("2026-09-14T18:00:00+09:00")
    s=empty_state(); ok,key=acquire_run_lock(s,production_date_kst="2026-09-14",scheduled_slot_kst="2026-09-14T19:00:00+09:00",router_branch="WEEKLY_PRODUCTION",run_id="r1"); assert ok; release_run_lock(s,key,status="completed")
    assert validate_production_record({"schema_version":1}, allow_legacy=True)[0].startswith("missing production fields")
    print("Instagram production state single-router: PASS")
if __name__=="__main__": self_test()
