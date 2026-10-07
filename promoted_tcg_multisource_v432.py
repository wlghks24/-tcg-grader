#!/usr/bin/env python3
"""V432 promoted-TCG multisource coverage planner.

Builds a fail-closed collection queue for every promoted game.  It does not
invent URLs or facts: known registry sources seed official/market lanes and
missing lanes/regions are emitted as explicit coverage gaps for collectors.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parent
REGISTRY=ROOT/"tcg_game_registry.json"
OUT=ROOT/"promoted_tcg_multisource_coverage_v432.json"
CORE_REGIONS=("KR","JP","US")
SOURCE_LANES=(
 "official_home","official_news","official_social","publisher",
 "tournament_event","collaboration","promo_distribution","limited_product","retailer",
)
DISCOVERY_LANES=SOURCE_LANES[1:-1]
SOCIAL_HOSTS={"x.com","www.x.com","instagram.com","www.instagram.com","youtube.com","www.youtube.com"}
def _https(value: Any)->bool:
 try:
  p=urlsplit(str(value or ""))
  return p.scheme=="https" and bool(p.hostname)
 except ValueError:
  return False
def _load(path:Path)->dict:
 return json.loads(path.read_text(encoding="utf-8"))
def promoted_games(registry:dict)->list[dict]:
 return [g for g in registry.get("games",[]) if g.get("state")=="promoted" and isinstance(g.get("capabilities"),dict)]
def _seed_sources(game:dict)->dict[str,list[str]]:
 out={lane:[] for lane in SOURCE_LANES}
 official=str(game.get("official_source") or "")
 market=str(game.get("market_source") or "")
 if _https(official):
  out["official_home"].append(official)
  # The official root is a bounded discovery seed, not evidence that each lane is covered.
  for lane in DISCOVERY_LANES:
   out[lane].append(official)
 if _https(market):
  out["retailer"].append(market)
 return out
def build_plan(registry:dict)->dict:
 rows=[]; total_expected=0; total_covered=0
 for game in promoted_games(registry):
  caps=game["capabilities"]
  regions=[r for r in game.get("regions",[]) if r in CORE_REGIONS]
  regions=regions or list(CORE_REGIONS)
  seeds=_seed_sources(game)
  required=[]
  if caps.get("release"): required += ["official_home","official_news","publisher","limited_product"]
  if caps.get("promo"): required += ["official_social","tournament_event","collaboration","promo_distribution"]
  if caps.get("purchase") or caps.get("market"): required += ["retailer"]
  required=list(dict.fromkeys(required))
  lane_rows=[]
  for lane in required:
   urls=seeds.get(lane,[])
   # discovery seeds are queued, not counted as covered until a collector verifies a lane-specific result.
   verified = lane in {"official_home","retailer"} and bool(urls)
   lane_rows.append({"lane":lane,"status":"covered" if verified else "queued","seed_urls":urls,
                     "needs_verified_result":not verified})
  expected=len(required)*len(regions); covered=sum(1 for x in lane_rows if x["status"]=="covered")*len(regions)
  total_expected+=expected; total_covered+=covered
  region_gaps=[{"region":r,"missing_lanes":[x["lane"] for x in lane_rows if x["status"]!="covered"]} for r in regions]
  rows.append({"id":game.get("id"),"canonical":game.get("canonical"),"label_ko":game.get("label_ko"),
               "regions":regions,"required_lanes":required,"lanes":lane_rows,"region_gaps":region_gaps,
               "coverage_expected_cells":expected,"coverage_verified_cells":covered,
               "coverage_ratio":round(covered/expected,4) if expected else 1.0,
               "coverage_gap":covered<expected,"grading_enabled":bool(caps.get("grading",False))})
 return {"schema_version":1,"version":"v432","regions":list(CORE_REGIONS),"source_lanes":list(SOURCE_LANES),
         "games":rows,"summary":{"promoted_games":len(rows),"expected_cells":total_expected,
         "verified_cells":total_covered,"missing_cells":max(0,total_expected-total_covered),
         "coverage_ratio":round(total_covered/total_expected,4) if total_expected else 1.0},
         "safety":{"invent_urls":False,"invent_events":False,"profit_guarantee":False,
         "market_direction_prediction":False,"grading_auto_enable":False,
         "lane_specific_verification_required":True}}
def main(root:Path=ROOT)->dict:
 payload=build_plan(_load(root/"tcg_game_registry.json"))
 (root/"promoted_tcg_multisource_coverage_v432.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 return payload
if __name__=="__main__": main()
