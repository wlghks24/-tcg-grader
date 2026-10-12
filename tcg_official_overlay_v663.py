#!/usr/bin/env python3
"""V663: safe manufacturer US sealed booster and retailer-promo evidence separation.

Manufacturer proof is an *individual SKU family sample*, not all products or
prices. Promotions are not sealed booster inserts or random HIT evidence.
"""
from __future__ import annotations
from pathlib import Path
import json
from execution.official_box_coverage_audit_v623 import ROOT, CoverageError, _load_json, audit
from tcg_official_overlay_v662 import FILE as PARENT, validate_v662
from tcg_official_overlay_v659 import FILE as V659,validate_additions
from tcg_official_overlay_v657 import OLD_CATALOGS, OVERLAY_NAME,validate_overlay

FILE="tcg_official_product_supplement_v663.json"
PROMO="tcg_official_promo_evidence_v663.json"
EXPECTED={
 "id":"pokemon-US-me-perfect-order-2026",
 "game":"Pokémon",
 "country":"US",
 "product_type":"BOX",
 "set_code":"LOCAL-POK-ME-PO-US",
 "set_code_verified":False,
 "name":"Pokémon TCG: Mega Evolution—Perfect Order Booster Display Box",
 "release_date":"2026-03-27",
 "source":"https://www.pokemon.com/us/news/pokemon-tcg-mega-evolution-perfect-order-product-showcase",
 "packs_per_box":36,
 "cards_per_pack":"10",
}
PROMO_EXPECTED={
 "pokemon-US-perfect-order-gengar-gamestop-2026":("Gengar","GameStop"),
 "pokemon-US-perfect-order-luxray-bestbuy-2026":("Luxray","Best Buy"),
 "pokemon-US-perfect-order-aurorus-retail-2026":("Aurorus","Hot Topic / Barnes & Noble"),
}
FORBIDDEN=("market_price","verified_sales","verified_stock","psa_grade",
           "hit_probability","pull_rate","msrp","card_number")
def validate_v663(doc,registry,previous=()):
    if not isinstance(doc,dict) or not isinstance(doc.get("policy"),dict):
        raise CoverageError("INVALID_V663_SUPPLEMENT")
    if (doc.get("schema_version")!=1 or
        doc.get("type")!="official_product_specifications_supplement" or
        doc.get("base_catalog")!=OLD_CATALOGS[0] or
        doc.get("append_after")!=PARENT or
        doc["policy"].get("no_paid_dependency") is not True or
        not isinstance(doc.get("products"),list) or len(doc["products"])!=1):
        raise CoverageError("INVALID_V663_CHAIN")
    p=doc["products"][0]
    if not isinstance(p,dict) or not isinstance(registry,dict) or not isinstance(registry.get("games"),list):
        raise CoverageError("INVALID_V663_RECORD")
    games=[g for g in registry["games"] if g.get("canonical")==EXPECTED["game"]]
    if not games or not any("US" in g.get("regions",[]) for g in games):
        raise CoverageError("V663_REGION_NOT_DECLARED")
    allowed=set(EXPECTED)|{"notes"}
    if (set(p)!=allowed or type(p.get("packs_per_box")) is not int or
        any(p.get(k)!=v for k,v in EXPECTED.items())
        or any(k in p for k in FORBIDDEN)
        or any(x.get("id")==EXPECTED["id"] for x in previous)):
        raise CoverageError("UNTRUSTED_V663_PRODUCT")
    return doc["products"]

def validate_promo(doc):
    if not isinstance(doc,dict) or not isinstance(doc.get("purchase_threshold"),dict):
        raise CoverageError("INVALID_V663_PROMO")
    if (doc.get("schema_version")!=1 or doc.get("type")!="OFFICIAL_PROMO_CAMPAIGN_NAME_ONLY"
        or doc.get("game")!="Pokémon" or doc.get("market")!="US"
        or doc.get("campaign_release_date")!="2026-03-27"
        or doc.get("source")!="https://www.pokemon.com/us/news/celebrate-pokemon-tcg-mega-evolution-perfect-order-with-promo-cards"
        or doc.get("evidence_policy")!="OFFICIAL_PROMO_PROGRAM_NOT_BOX_HIT_OR_CARD_NUMBER"
        or doc["purchase_threshold"]!={"amount":15,"currency":"USD","unit":"ELIGIBLE_TCG_PURCHASE"}
        or not isinstance(doc.get("records"),list) or len(doc["records"])!=3):
        raise CoverageError("INVALID_V663_PROMO_SCHEMA")
    ids=set()
    for p in doc["records"]:
        if not isinstance(p,dict):raise CoverageError("INVALID_V663_PROMO_ROW")
        exp=PROMO_EXPECTED.get(p.get("id"))
        if (not exp or set(p)!={"id","card_name","retailer","market","card_number","printing","eligibility"} or p["id"] in ids or
            p.get("card_name")!=exp[0] or p.get("retailer")!=exp[1] or
            p.get("market")!="US" or p.get("card_number") is not None or
            p.get("printing")!="PROMO_CARD_NUMBER_UNVERIFIED" or
            p.get("eligibility")!="Eligible Pokémon TCG purchase of at least USD 15, while supplies last" or
            any(k in p for k in ("verified_stock","market_price","hit_probability","pull_rate","psa_grade"))):
            raise CoverageError("UNTRUSTED_V663_PROMO")
        ids.add(p["id"])
    if ids!=set(PROMO_EXPECTED):raise CoverageError("MISSING_V663_PROMO")
    return doc["records"]

def build(directory=ROOT):
    folder=Path(directory);registry=_load_json(folder/"tcg_game_registry.json")
    old=sum([_load_json(folder/name)["products"] for name in OLD_CATALOGS],[])
    old+=validate_overlay(_load_json(folder/OVERLAY_NAME),registry)
    old+=validate_additions(_load_json(folder/V659),registry)
    old+=validate_v662(_load_json(folder/PARENT),registry,old)
    added=validate_v663(_load_json(folder/FILE),registry,old)
    promos=validate_promo(_load_json(folder/PROMO))
    before=audit(registry,{"schema_version":1,"products":old})
    after=audit(registry,{"schema_version":1,"products":old+added})
    def summary(r):
        declared=[x for x in r["cells"] if x["region_declared"]]
        return {"products":r["reviewed_official_product_records"],
                "boxes":sum(x["official_box_count"] for x in r["cells"]),
                "region_pairs":len(declared),
                "with_box":sum(bool(x["official_box_count"]) for x in declared),
                "gaps":sum(not x["official_box_count"] for x in declared)}
    return {"status":"MANUFACTURER_AND_PROMO_REVIEW_READY_NOT_MAIN_MERGED",
            "prior":summary(before),"with_v663":summary(after),
            "official_promo_name_samples":len(promos),
            "official_promo_card_numbers_verified":0,
            "market_prices_verified":0,"network_calls":0,"paid_dependencies":0}

if __name__=="__main__":
    print(json.dumps(build(),ensure_ascii=False,indent=2))
