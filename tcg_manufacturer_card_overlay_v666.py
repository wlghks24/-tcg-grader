#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V666: tiny source-bound official card-ID supplement and locale specification guard.

No HTTP requests, price/grade/HIT inference or copyrighted card text bulk harvest.
These examples prove published number/name pairs, NOT print variant or rarity.
"""
from __future__ import annotations
from pathlib import Path
from execution.official_box_coverage_audit_v623 import ROOT,_load_json
from tcg_card_trade_evidence_v660 import official_card_records

CARD_FILE="tcg_manufacturer_card_evidence_v666.json"
SPEC_FILE="tcg_country_pack_discrepancy_v666.json"
SOURCE_H="https://en.hololive-official-cardgame.com/rules/errata/"
SOURCE_D="https://www.dbs-cardgame.com/fw/en/products/01_400.html"
WARN="US-EN official manufacturer page; physical printing SKU/rarity not independently confirmed"
HOLO={
 "hEB01-010":"Tokino Sora",
 "hBP05-004":"Nekomata Okayu",
 "hBP05-087":"Jailbird",
 "hBP05-082":"Aki Rosenthal’s Axe",
 "hBP05-067":"Shiranui Flare",
 "hBP05-063":"Shiranui Flare",
 "hBP05-051":"Hiodoshi Ao",
 "hBP05-050":"Fuwawa Abyssgard",
}
DRAGON={
 "FB10-001":"Son Goku",
 "FB10-073":"Boujack",
 "FB10-097":"Cell",
}
FIELDS={"id","game_id","game","market","set_code","card_number","card_name",
        "rarity","printing","evidence_type","source_url","market_note"}
def expected():
    rows={}
    for num,name in HOLO.items():
        rid="hololive-US-"+num
        rows[rid]=( "hololive-ocg","hololive OFFICIAL CARD GAME",num.split("-")[0],num,name,
                   "MANUFACTURER_ERRATA_CARD_NUMBER",SOURCE_H)
    for num,name in DRAGON.items():
        rid="dbsfw-US-"+num
        rows[rid]=( "dbsfw","DRAGON BALL SUPER: FUSION WORLD","FB10",num,name,
                   "MANUFACTURER_PRODUCT_CARD_HIGHLIGHT",SOURCE_D)
    return rows

def validate_additional(doc, registry):
    known=expected()
    if (not isinstance(doc,dict) or doc.get("schema_version")!=1 or
        doc.get("level")!="MANUFACTURER_ADDITIVE_CARD_IDENTITY_SAMPLE" or
        doc.get("parent")!="tcg_manufacturer_card_evidence_v660.json" or
        not isinstance(doc.get("policy"),dict) or
        doc["policy"].get("no_paid_dependency") is not True or
        doc["policy"].get("no_guess_grade_price") is not True or
        not isinstance(doc.get("records"),list) or len(doc["records"])!=len(known)):
        raise ValueError("INVALID_V666_CARD_CHAIN")
    if not isinstance(registry,dict) or not isinstance(registry.get("games"),list):
        raise ValueError("INVALID_V666_REGISTRY")
    declared={(g["id"],m) for g in registry["games"] for m in g.get("regions",[])
              if m in ("KR","JP","US")}
    result={}
    for item in doc["records"]:
        if not isinstance(item,dict) or set(item)!=FIELDS:
            raise ValueError("V666_UNRECOGNIZED_CARD_FIELDS")
        rid=item["id"]
        spec=known.get(rid)
        if not spec or rid in result:
            raise ValueError("V666_UNKNOWN_DUPLICATE_ID")
        game_id,game,set_code,number,name,evidence,source=spec
        if (item.get("game_id")!=game_id or item.get("game")!=game or
            item.get("market")!="US" or (game_id,"US") not in declared or
            item.get("set_code")!=set_code or item.get("card_number")!=number or
            item.get("card_name")!=name or item.get("rarity") is not None or
            item.get("printing")!="UNKNOWN" or item.get("source_url")!=source or
            item.get("evidence_type")!=evidence or item.get("market_note")!=WARN):
            raise ValueError("V666_UNTRUSTED_CARD_IDENTITY")
        result[rid]=item
    if set(result)!=set(known):raise ValueError("V666_MISSING_CARD_ID")
    return result

def validate_country_pack_difference(doc):
    if (not isinstance(doc,dict) or doc.get("schema_version")!=1 or
        doc.get("type")!="COUNTRY_SPEC_DISCREPANCY_NEEDS_CAUTION" or
        doc.get("game")!="DRAGON BALL SUPER: FUSION WORLD" or
        doc.get("game_id")!="dbsfw" or doc.get("set_code")!="FB10"):
        raise ValueError("V666_INVALID_REGION_SPEC")
    pack=doc.get("known_pack_content")
    if not isinstance(pack,dict) or set(pack)!={"JP","US"}:
        raise ValueError("V666_INVALID_PACK_REGIONS")
    if (pack["JP"]!={"cards_per_pack":6,
                    "source":"https://www.dbs-cardgame.com/fw/jp/products/01_400.html"} or
        pack["US"]!={"cards_per_pack":12,"additional_digital_code_per_pack":1,
                    "source":SOURCE_D}):
        raise ValueError("V666_COUNTRY_PACK_MISMATCH")
    missing=doc.get("unverified")
    if (not isinstance(missing,dict) or
        set(missing)!={"us_booster_packs_per_display_box","manufacturer_us_box_msrp",
                       "verified_pack_pull_odds"} or any(x is not None for x in missing.values())):
        raise ValueError("V666_INVENTED_US_BOX_OR_PRICE")
    policy=doc.get("policy")
    if (not isinstance(policy,dict) or
        not all(policy.get(k) is True for k in
                ("do_not_inherit_japan_cards_per_pack_for_us",
                 "do_not_use_pack_price_as_box_msrp",
                 "do_not_pretend_us_box_is_verified",
                 "do_not_count_a_digital_code_as_card"))):
        raise ValueError("V666_LOCALE_GUARD_DISABLED")
    return {"JP_cards_per_pack":6,"US_cards_per_pack":12,
            "US_box_pack_count_known":False,"us_digital_code_is_tcg_card":False}

def combined_card_records(directory=ROOT,base=None,extra=None,registry=None,guard=None):
    d=Path(directory)
    original=official_card_records(_load_json(d/"tcg_manufacturer_card_evidence_v660.json") if base is None else base)
    reg=_load_json(d/"tcg_game_registry.json") if registry is None else registry
    more=validate_additional(_load_json(d/CARD_FILE) if extra is None else extra,reg)
    validate_country_pack_difference(_load_json(d/SPEC_FILE) if guard is None else guard)
    if set(original)&set(more):raise ValueError("V666_DUPLICATE_WITH_PARENT")
    from tcg_manufacturer_card_overlay_v667 import validate_ff_cards,FILE as FF_FILE
    ff=validate_ff_cards(_load_json(d/FF_FILE),reg)
    if (set(original)&set(ff)) or (set(more)&set(ff)):
        raise ValueError("V667_DUPLICATE_WITH_PARENT")
    return {**original,**more,**ff}

def report(directory=ROOT):
    records=combined_card_records(directory)
    return {"state":"MANUFACTURER_CARD_ID_SAMPLES_NOT_PUBLIC_PRICE",
            "source_bound_number_name_pairs":len(records),
            "games_with_samples":len({p["game_id"] for p in records.values()}),
            "manufacturer_verified_rarity_from_v666":0,
            "manufacturer_verified_us_fb10_box_count":0,
            "verified_sales":0,"grade_predictions":0,
            "network_calls":0,"paid_dependencies":0}

if __name__=="__main__":
    import json
    print(json.dumps(report(),ensure_ascii=False,indent=2))
