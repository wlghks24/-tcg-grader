#!/usr/bin/env python3
"""V436 bounded market-intelligence council for tablet TCG evolution."""
from __future__ import annotations
from datetime import datetime,timezone
from typing import Any

PROMOTE_MIN=.72
WATCH_PRIORITY_MIN=.55
MAX_UI_GAMES=12

def _age_days(value:str,now:datetime)->int|None:
 try:
  d=datetime.fromisoformat(str(value).replace("Z","+00:00"))
  if d.tzinfo is None:d=d.replace(tzinfo=timezone.utc)
  return max(0,(now-d.astimezone(timezone.utc)).days)
 except (TypeError,ValueError):return None

def assess_game(game:dict[str,Any], *, now:datetime|None=None)->dict[str,Any]:
 now=(now or datetime.now(timezone.utc)).astimezone(timezone.utc);e=game.get("evidence") if isinstance(game.get("evidence"),dict) else {}
 age=_age_days(e.get("last_verified_at",""),now);catalog=e.get("marketplace_catalog_count",0)
 catalog=catalog if isinstance(catalog,int) and not isinstance(catalog,bool) and catalog>=0 else 0
 fresh=age is not None and age<=45
 official=bool(e.get("official_live")) and fresh; organized=bool(e.get("organized_play")) and fresh
 collector=bool(e.get("collector_rarity_signal")) and fresh
 depth=min(1.0,catalog/2000.0)
 regions=len({r for r in game.get("regions",[]) if r in {"KR","JP","US"}})/3.0
 score=round(.28*official+.16*organized+.10*collector+.28*depth+.10*regions+.08*fresh,4)
 if game.get("state")=="core":decision="CORE"
 elif not fresh:decision="REVERIFY"
 elif official and catalog>=500 and score>=PROMOTE_MIN:decision="PROMOTION_CANDIDATE"
 elif score>=WATCH_PRIORITY_MIN:decision="PRIORITY_WATCH"
 else:decision="WATCH"
 return {"id":game.get("id"),"canonical":game.get("canonical"),"state":game.get("state"),"score":score,
  "decision":decision,"evidence_age_days":age,"catalog_count":catalog,"grading_enabled":bool(game.get("capabilities",{}).get("grading",False)),
  "profit_guarantee":False,"market_direction_prediction":False}

def build_tablet_plan(registry:dict[str,Any], *, now:datetime|None=None)->dict[str,Any]:
 rows=[assess_game(g,now=now) for g in registry.get("games",[]) if isinstance(g,dict)]
 rank={"CORE":0,"PROMOTION_CANDIDATE":1,"PRIORITY_WATCH":2,"WATCH":3,"REVERIFY":4}
 rows.sort(key=lambda r:(rank[r["decision"]],-r["score"],str(r["canonical"])))
 visible=rows[:MAX_UI_GAMES]
 return {"status":"READY","visible_games":visible,"reverify":[r["id"] for r in rows if r["decision"]=="REVERIFY"],
  "promotion_candidates":[r["id"] for r in rows if r["decision"]=="PROMOTION_CANDIDATE"],
  "ui_policy":{"registry_driven":True,"max_games":MAX_UI_GAMES,"watch_badge_required":True,"grading_requires_calibration":True},
  "autonomy":{"may_reorder_existing_registry_games":True,"may_request_reverification":True,"may_auto_enable_grading":False,
  "may_invent_game_or_source":False,"may_predict_profit":False,"source_code_self_modification":False}}
