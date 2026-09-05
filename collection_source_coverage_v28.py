#!/usr/bin/env python3
"""Fail-closed official collection coverage guard.

Tracks whether each Pokémon / ONE PIECE / NARUTO × KR/JP/US cell has at least
one configured official route and at least one fresh usable source-health row.
Access-restricted routes stay visible but do not count as a successful fetch.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

GAMES=("pokemon","one_piece","naruto")
REGIONS=("KR","JP","US")
EXPECTED_CELLS=tuple(f"{g}/{r}" for g in GAMES for r in REGIONS)
DEFAULT_MAX_AGE_HOURS=36.0

def _parse_time(value: object) -> dt.datetime | None:
    text=str(value or "").strip()
    if not text:return None
    try:parsed=dt.datetime.fromisoformat(text.replace("Z","+00:00"))
    except ValueError:return None
    if parsed.tzinfo is None:parsed=parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)

def _age_hours(value: object, now: dt.datetime) -> float | None:
    parsed=_parse_time(value)
    if parsed is None:return None
    if now.tzinfo is None:now=now.replace(tzinfo=dt.timezone.utc)
    return max(0.0,(now.astimezone(dt.timezone.utc)-parsed).total_seconds()/3600.0)

def configured_matrix() -> dict[str,Any]:
    import tcg_updater
    rows={cell:[] for cell in EXPECTED_CELLS}
    for name,(game,region,channel) in tcg_updater.OFFICIAL_SOURCE_SCOPE.items():
        cell=f"{game}/{region}"
        if cell in rows:
            source=next((x for x in tcg_updater.SOURCES if x[0]==name),None)
            rows[cell].append({
                "name":name,
                "url":source[1] if source else None,
                "kind":source[2] if source else None,
                "channel":channel,
                "configured":bool(source),
            })
    missing=[cell for cell,items in rows.items() if not any(x["configured"] for x in items)]
    return {
        "expected_cells":len(EXPECTED_CELLS),
        "configured_cells":len(EXPECTED_CELLS)-len(missing),
        "missing_cells":missing,
        "cells":rows,
        "ok":not missing,
    }

def direct_entry_matrix() -> dict[str,Any]:
    import official_direct_discovery
    game_map={"포켓몬":"pokemon","원피스":"one_piece","나루토":"naruto"}
    rows={cell:[] for cell in EXPECTED_CELLS}
    for short,regions in official_direct_discovery.OFFICIAL_ENTRY_PAGES.items():
        game=game_map.get(short)
        if not game:continue
        for region,pages in regions.items():
            cell=f"{game}/{region}"
            if cell in rows:
                rows[cell].extend(str(x) for x in pages if str(x).startswith("https://"))
    missing=[cell for cell,pages in rows.items() if not pages]
    return {
        "expected_cells":len(EXPECTED_CELLS),
        "configured_cells":len(EXPECTED_CELLS)-len(missing),
        "missing_cells":missing,
        "cells":rows,
        "ok":not missing,
    }

def audit_source_stats(source_stats: dict[str,Any], now: dt.datetime,
                       max_age_hours: float=DEFAULT_MAX_AGE_HOURS) -> dict[str,Any]:
    source_map=source_stats.get("sources") if isinstance(source_stats,dict) and isinstance(source_stats.get("sources"),dict) else {}
    cells={cell:{"sources":[],"fresh_usable":0,"fresh_restricted":0,"fresh_failed":0,"stale":0} for cell in EXPECTED_CELLS}
    for name,row in source_map.items():
        if not isinstance(row,dict) or row.get("official_scope") is not True:continue
        game=str(row.get("game") or "");region=str(row.get("region") or "")
        cell=f"{game}/{region}"
        if cell not in cells:continue
        age=_age_hours(row.get("last_run"),now)
        fresh=age is not None and age<=float(max_age_hours)
        result=str(row.get("last_result") or "")
        item={
            "name":str(name)[:160],
            "url":str(row.get("url") or "")[:900],
            "channel":str(row.get("channel") or "")[:40],
            "last_result":result,
            "last_run":row.get("last_run"),
            "age_hours":None if age is None else round(age,2),
            "consecutive_failures":int(row.get("consecutive_failures") or 0),
            "last_http_status":row.get("last_http_status"),
        }
        cells[cell]["sources"].append(item)
        if not fresh:
            cells[cell]["stale"]+=1
        elif result in {"success","recovered"}:
            cells[cell]["fresh_usable"]+=1
        elif result=="restricted":
            cells[cell]["fresh_restricted"]+=1
        else:
            cells[cell]["fresh_failed"]+=1

    missing=[];degraded=[];healthy=[]
    for cell,row in cells.items():
        if not row["sources"]:
            missing.append(cell)
        elif row["fresh_usable"]>0:
            healthy.append(cell)
        else:
            degraded.append(cell)
    return {
        "expected_cells":len(EXPECTED_CELLS),
        "healthy_cells":len(healthy),
        "healthy":healthy,
        "missing_cells":missing,
        "degraded_cells":degraded,
        "cells":cells,
        "max_age_hours":float(max_age_hours),
        "ok":not missing and not degraded,
    }

def self_test() -> dict[str,Any]:
    configured=configured_matrix()
    direct=direct_entry_matrix()
    assert configured["ok"],configured
    assert direct["ok"],direct
    return {"ok":True,"configured_cells":configured["configured_cells"],"direct_cells":direct["configured_cells"]}

if __name__=="__main__":
    import json
    print(json.dumps(self_test(),ensure_ascii=False))
