#!/usr/bin/env python3
"""V437 bounded discovery inbox for newly observed TCGs.

Discovery can nominate candidates; only registry review can promote them.
No arbitrary source/code generation and no profit prediction.
"""
from __future__ import annotations
from datetime import datetime,timezone
from typing import Any
from urllib.parse import urlsplit

ALLOWED_REGIONS={"KR","JP","US","GLOBAL"}
MIN_MARKET_DEPTH=500
MAX_CANDIDATES=32

def _https(v:Any)->bool:
 try:p=urlsplit(str(v or ""));return p.scheme=="https" and bool(p.hostname)
 except ValueError:return False

def normalize_candidate(row:dict[str,Any], *, now:datetime|None=None)->dict[str,Any]|None:
 if not isinstance(row,dict):return None
 name=str(row.get("canonical") or "").strip()
 official=str(row.get("official_source") or ""); market=str(row.get("market_source") or "")
 if not name or len(name)>120 or not _https(official) or not _https(market):return None
 catalog=row.get("marketplace_catalog_count")
 if not isinstance(catalog,int) or isinstance(catalog,bool) or catalog<0:return None
 regions=sorted({str(r).upper() for r in row.get("regions",[]) if str(r).upper() in ALLOWED_REGIONS})
 if not regions:return None
 signals={"official_live":bool(row.get("official_live")),"organized_play":bool(row.get("organized_play")),
          "collector_rarity_signal":bool(row.get("collector_rarity_signal"))}
 independent=sum(signals.values())+(1 if catalog>=MIN_MARKET_DEPTH else 0)
 decision="WATCH_CANDIDATE" if signals["official_live"] and independent>=2 else "DISCOVERY_HOLD"
 return {"canonical":name,"decision":decision,"official_source":official,"market_source":market,
  "regions":regions,"marketplace_catalog_count":catalog,"signals":signals,
  "independent_signal_count":independent,"grading_enabled":False,"profit_guarantee":False,
  "market_direction_prediction":False,"discovered_at":(now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()}

def build_inbox(rows:list[dict[str,Any]], existing_names:set[str], *, now:datetime|None=None)->dict[str,Any]:
 seen={str(x).casefold() for x in existing_names};accepted=[];held=[]
 for row in rows[:MAX_CANDIDATES]:
  n=normalize_candidate(row,now=now)
  if n is None:held.append({"reason":"INVALID_OR_UNVERIFIED"});continue
  if n["canonical"].casefold() in seen:continue
  seen.add(n["canonical"].casefold())
  (accepted if n["decision"]=="WATCH_CANDIDATE" else held).append(n)
 return {"status":"READY","watch_candidates":accepted,"held":held,
  "policy":{"registry_review_required":True,"auto_promote":False,"auto_enable_grading":False,
  "invent_sources":False,"profit_prediction":False,"max_candidates":MAX_CANDIDATES}}
