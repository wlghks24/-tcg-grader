#!/usr/bin/env python3
"""Persistent collection-health state for tablet-only operation."""
from __future__ import annotations
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any
from safe_runtime import atomic_write_json, diagnostic_exception, safe_read_text

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "collection_runtime_health.json"
STALE_AFTER_SECONDS = 8 * 60 * 60
STARTUP_GRACE_SECONDS = 45 * 60

def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def _parse(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return stamp.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None

def _default() -> dict[str, Any]:
    return {"schema_version":1,"last_attempt_at":None,"last_success_at":None,"last_failure_at":None,
            "last_trigger":None,"last_error":None,"last_report_ok":None,"consecutive_failures":0,
            "next_due_at":None,"precollect":{"state":"not-run","updated_at":None,"error":None}}

def load(path: Path = STATE) -> dict[str, Any]:
    try:
        data = json.loads(safe_read_text(path, max_bytes=256_000))
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return _default()
    if not isinstance(data, dict):
        return _default()
    base = _default()
    base.update({k:v for k,v in data.items() if k in base})
    if not isinstance(base.get("precollect"), dict):
        base["precollect"] = _default()["precollect"]
    try:
        base["consecutive_failures"] = max(0,min(9999,int(base.get("consecutive_failures") or 0)))
    except (TypeError,ValueError,OverflowError):
        base["consecutive_failures"] = 0
    return base

def _safe_error(value: Any) -> str:
    text = diagnostic_exception(value, 600) if isinstance(value, BaseException) else str(value or "collection_failed")
    try:
        import auto_repair_engine
        return auto_repair_engine.redact_sensitive(text, 600) or "collection_failed"
    except (ImportError, AttributeError, TypeError, ValueError):
        text = re.sub(r"https?://[^\\s\\\"'<>]+", "<url>", text, flags=re.I)
        text = re.sub(r"(?i)\\b(?:token|api[_-]?key|authorization|password|secret)\\s*[=:]\\s*[^\\s,;]+", "<secret>", text)
        text = re.sub(r"[\\x00-\\x1f\\x7f]+", " ", text)
        text = re.sub(r"\\s+", " ", text).strip()
        return text[:600] or "collection_failed"
def mark_attempt(trigger: str, *, next_due_at: str | None=None, path: Path=STATE) -> dict[str,Any]:
    data=load(path); data["last_attempt_at"]=_now(); data["last_trigger"]=str(trigger or "unknown")[:120]
    if next_due_at: data["next_due_at"]=str(next_due_at)[:80]
    atomic_write_json(path,data,suffix=".collection-health.tmp"); return data

def mark_success(trigger: str, *, next_due_at: str | None=None, path: Path=STATE) -> dict[str,Any]:
    data=load(path); stamp=_now()
    data.update({"last_attempt_at":stamp,"last_success_at":stamp,"last_trigger":str(trigger or "unknown")[:120],
                 "last_error":None,"last_report_ok":True,"consecutive_failures":0})
    if next_due_at: data["next_due_at"]=str(next_due_at)[:80]
    atomic_write_json(path,data,suffix=".collection-health.tmp"); return data

def mark_failure(trigger: str, error: Any, *, next_due_at: str | None=None, path: Path=STATE) -> dict[str,Any]:
    data=load(path); stamp=_now()
    data.update({"last_attempt_at":stamp,"last_failure_at":stamp,"last_trigger":str(trigger or "unknown")[:120],
                 "last_error":_safe_error(error),"last_report_ok":False,
                 "consecutive_failures":min(9999,int(data.get("consecutive_failures") or 0)+1)})
    if next_due_at: data["next_due_at"]=str(next_due_at)[:80]
    atomic_write_json(path,data,suffix=".collection-health.tmp"); return data

def mark_precollect(status: dict[str,Any], *, path: Path=STATE) -> dict[str,Any]:
    data=load(path)
    state=str(status.get("state") or "unknown")[:40] if isinstance(status,dict) else "invalid"
    error=_safe_error(status.get("error")) if isinstance(status,dict) and status.get("error") else None
    data["precollect"]={"state":state,"updated_at":_now(),"error":error}
    atomic_write_json(path,data,suffix=".collection-health.tmp"); return data

def public_status(path: Path=STATE, *, now: datetime | None=None) -> dict[str,Any]:
    data=load(path); moment=(now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    success=_parse(data.get("last_success_at")); attempt=_parse(data.get("last_attempt_at"))
    success_age=None if success is None else max(0,int((moment-success).total_seconds()))
    attempt_age=None if attempt is None else max(0,int((moment-attempt).total_seconds()))
    failures=int(data.get("consecutive_failures") or 0)
    stale=success_age is not None and success_age>STALE_AFTER_SECONDS
    if success is None:
        failed_after_grace=failures>0 and attempt_age is not None and attempt_age>STARTUP_GRACE_SECONDS
        healthy=False if failed_after_grace else None; status="failed" if failed_after_grace else "starting"
    elif stale:
        healthy=False; status="stale"
    elif failures>=2:
        healthy=False; status="failed"
    elif failures==1:
        healthy=True; status="degraded"
    else:
        healthy=True; status="ok"
    return {**data,"healthy":healthy,"status":status,"stale":stale,"success_age_seconds":success_age,
            "attempt_age_seconds":attempt_age,"stale_after_seconds":STALE_AFTER_SECONDS,
            "requires_attention":healthy is False or failures>0,"process_restart_required":False}

def self_test() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/"health.json"
        assert public_status(path)["status"]=="starting"
        mark_failure("test",ValueError("https://example.com token=secret"),path=path)
        assert public_status(path)["consecutive_failures"]==1
        mark_success("test-recovery",path=path)
        ok=public_status(path); assert ok["healthy"] is True and ok["consecutive_failures"]==0
    print("collection runtime health: PASS")

if __name__=="__main__":
    self_test()
