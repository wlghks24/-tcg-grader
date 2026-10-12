#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V650: all-30 free manufacturer-backed HIT/PROMO card-name discovery planner.

Generates 98 user-submitted card lead names x KR/JP/US = 294 manual lookup
tasks. Uses verified manufacturer card list pages where available, otherwise
registry manufacturer home-domain site search. No scraping, no price claims,
no images, no 403/429 bypass, no paid API, no automatic card identity promotion.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from urllib.parse import urlencode, urlsplit

from tcg_multi_source_queue_v639 import load_local, phrase, search_url

MARKETS=("KR","JP","US")
FIELDS=(("hit_name_candidates","HIT"),("promo_name_candidates","PROMO"))
# Real public manufacturer card galleries separately verified from sealed BOX specs.
OFFICIAL_CARD_LISTS={
    "wixoss":{"JP":"https://www.takaratomy.co.jp/products/wixoss/card/card_list"},
    "universus":{"US":"https://uvsgames.com/universus/cards/"},
    "rush-of-ikorr":{"US":"https://my.upperdeck.com/public/roi/cards"},
    "digimon":{"US":"https://world.digimoncard.com/cards/"},
}
ALLOWED_GALLERY_HOSTS={
    "wixoss":("www.takaratomy.co.jp",),
    "universus":("uvsgames.com",),
    "rush-of-ikorr":("my.upperdeck.com",),
    "digimon":("world.digimoncard.com",),
}


def safe_official_page(game,market,value):
    allowed=ALLOWED_GALLERY_HOSTS.get(game,())
    if (market not in MARKETS or
        value!=OFFICIAL_CARD_LISTS.get(game,{}).get(market) or
        not isinstance(value,str) or len(value)>500):
        raise ValueError("UNVERIFIED_CARD_GALLERY")
    u=urlsplit(value)
    if u.scheme!="https" or u.hostname not in allowed or u.username or u.password or u.fragment or u.port not in (None,443):
        raise ValueError("UNSAFE_CARD_GALLERY")
    return value


def build(*,game="ALL",market="ALL",kind="ALL"):
    reg=load_local("tcg_game_registry.json")
    intake=load_local("tcg_user_research_intake_v625.json")
    games=reg.get("games")
    leads=intake.get("records")
    if (reg.get("schema_version")!=1 or not isinstance(games,list) or len(games)!=30 or
        intake.get("data_evidence_level")!="UNVERIFIED" or not isinstance(leads,list) or
        len(leads)!=30 or len({r["game_id"] for r in leads})!=30):
        raise ValueError("INVALID_30_GAME_SNAPSHOT")
    game_ids={g["id"] for g in games}
    if game not in ({"ALL"}|game_ids) or market not in ("ALL",*MARKETS) or kind not in ("ALL","HIT","PROMO"):
        raise ValueError("INVALID_FILTER")
    by_id={r["game_id"]:r for r in leads}
    if game_ids!=set(by_id):
        raise ValueError("MISMATCHED_30_GAME_ROWS")
    rows=[]
    for g in games:
        if game!="ALL" and g["id"]!=game:continue
        for m in MARKETS:
            if market!="ALL" and m!=market:continue
            region_declared=m in g["regions"] or "GLOBAL" in g["regions"]
            home=g["official_source"]
            hu=urlsplit(home)
            if hu.scheme!="https" or not hu.hostname or hu.username or hu.password:
                raise ValueError("UNSAFE_MANUFACTURER_HOME")
            gallery=OFFICIAL_CARD_LISTS.get(g["id"],{}).get(m)
            if gallery:safe_official_page(g["id"],m,gallery)
            seed=gallery or home
            host=urlsplit(seed).hostname
            for field,item_kind in FIELDS:
                if kind not in ("ALL",item_kind):continue
                for name in by_id[g["id"]][field]:
                    if not isinstance(name,str) or not name.strip() or len(name)>230:
                        raise ValueError("INVALID_CANDIDATE")
                    target="site:"+host+" "+phrase(name)
                    rows.append({
                        "game_id":g["id"],"market":m,"kind":item_kind,"name":name,
                        "region_declared":region_declared,
                        "manufacturer_card_list":gallery,
                        "source_kind":"OFFICIAL_CARD_GALLERY" if gallery else "REGISTRY_OFFICIAL_SITE_SEARCH_ONLY",
                        "identity_confirmed":False,"card_number_verified":False,"rarity_verified":False,
                        "language_edition_verified":False,"price_verified":False,
                        "queries":{
                            "official_google":search_url("google",target),
                            "official_bing":search_url("bing",target),
                            "market_google":search_url("google",phrase(g["canonical"])+" "+phrase(name)),
                        },
                        "status":"UNVERIFIED_MANUAL_CARD_IDENTITY_REVIEW"
                    })
    return {"schema_version":1,"collector":"MANUFACTURER_CARD_NAME_DISCOVERY",
            "games":len(games),"region_scopes":90,
            "jobs":rows,"job_count":len(rows),
            "card_gallery_jobs":sum(bool(r["manufacturer_card_list"]) for r in rows),
            "summary":dict(Counter((r["kind"],r["market"]) for r in rows)),
            "network_calls":0,"paid_dependencies":0,
            "note":"No inference of card number, parallel art, rarity, PSA grade, HIT rate or price."}


def main(argv=None):
    ap=argparse.ArgumentParser(description="30-TCG HIT/promo manufacturer card list searches")
    ap.add_argument("--game",default="ALL")
    ap.add_argument("--market",default="ALL",choices=("ALL",*MARKETS))
    ap.add_argument("--kind",default="ALL",choices=("ALL","HIT","PROMO"))
    ap.add_argument("--summary-only",action="store_true")
    args=ap.parse_args(argv)
    try:
        report=build(game=args.game,market=args.market,kind=args.kind)
        if args.summary_only:report.pop("jobs")
        # tuple keys are converted to an explicit JSON-safe string.
        report["summary"]={"|".join(k):v for k,v in report["summary"].items()}
        print(json.dumps(report,ensure_ascii=False,indent=2))
        return 0
    except (ValueError,TypeError,KeyError,OSError) as error:
        ap.error(str(error))


if __name__=="__main__":
    raise SystemExit(main())
