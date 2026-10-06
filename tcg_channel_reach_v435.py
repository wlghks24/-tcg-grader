#!/usr/bin/env python3
"""V435 bounded channel reach/health router for TCG public-source collection."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

STATES=("HEALTHY","DEGRADED","BLOCKED","AUTH_REQUIRED","RATE_LIMITED","UNKNOWN")
CHANNELS=("official_web","rss","x","instagram","youtube","reddit","github","publisher","retailer")
@dataclass(frozen=True)
class Endpoint:
 channel:str; url:str; lineage_key:str; priority:int=100; auth_required:bool=False
 def valid(self)->bool:
  try:p=urlsplit(self.url);return self.channel in CHANNELS and p.scheme=="https" and bool(p.hostname) and bool(self.lineage_key)
  except ValueError:return False

def classify_probe(*,http_status:int|None,error_code:str|None=None,auth_required:bool=False)->str:
 if auth_required and http_status in {401,403}:return "AUTH_REQUIRED"
 if http_status==429:return "RATE_LIMITED"
 if http_status in {401,403,451}:return "BLOCKED"
 if isinstance(http_status,int) and 200<=http_status<400:return "HEALTHY"
 if isinstance(http_status,int) and 500<=http_status<600:return "DEGRADED"
 if error_code in {"TIMEOUT","DNS","CONNECTION"}:return "DEGRADED"
 return "UNKNOWN"

def route(endpoints:list[Endpoint],probes:dict[str,dict[str,Any]])->dict[str,Any]:
 valid=[e for e in endpoints if e.valid()]
 rows=[]
 for e in valid:
  p=probes.get(e.url,{})
  state=classify_probe(http_status=p.get("http_status"),error_code=p.get("error_code"),auth_required=e.auth_required)
  rows.append({"channel":e.channel,"url":e.url,"lineage_key":e.lineage_key,"priority":e.priority,"state":state})
 rows.sort(key=lambda r:(0 if r["state"]=="HEALTHY" else 1,r["priority"],r["channel"],r["url"]))
 selected=[];seen=set()
 for row in rows:
  if row["state"]!="HEALTHY" or row["lineage_key"] in seen:continue
  seen.add(row["lineage_key"]);selected.append(row)
 return {"status":"READY" if selected else "HOLD","selected":selected,"diagnostics":rows,
         "lineage_deduplicated":True,"fallback_requires_healthy_probe":True}

def source_evidence(rows:list[dict[str,Any]])->dict[str,Any]:
 """Count independent evidence by lineage, never by mirrors/fallbacks."""
 accepted={}; rejected=[]
 for row in rows:
  if not isinstance(row,dict):continue
  key=str(row.get("lineage_key") or "")
  if row.get("state")!="HEALTHY" or not key:rejected.append(row);continue
  score=float(row.get("confidence",0) or 0)
  if not 0<=score<=1:rejected.append(row);continue
  prev=accepted.get(key)
  if prev is None or score>float(prev.get("confidence",0)):accepted[key]=row
 vals=list(accepted.values())
 return {"independent_lineages":len(vals),"accepted":vals,"rejected":rejected,
         "crosscheck_ready":len(vals)>=2,"single_lineage_cannot_crosscheck":True}
