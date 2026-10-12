#!/usr/bin/env python3
"""V662: manufacturer-spec sealed BOX proof; reject SKU and price fabrication.

Japan-market product page evidence, not proof of every language-print SKU.
Standard-library-only and entirely offline.
"""
from __future__ import annotations
from pathlib import Path
import json
from execution.official_box_coverage_audit_v623 import ROOT, CoverageError, _load_json, audit
from tcg_official_overlay_v657 import OLD_CATALOGS, OVERLAY_NAME, validate_overlay
from tcg_official_overlay_v659 import FILE as V659_NAME, validate_additions as validate_v659

FILE="tcg_official_product_supplement_v662.json"
EXPECTED={
  "mtg-JP-ECL-play-booster-2026":{
    "game":"Magic: The Gathering", "country":"JP", "product_type":"BOX",
    "set_code":"LOCAL-MTG-ECL-JP", "set_code_verified":False,
    "name":"Magic: The Gathering Lorwyn Eclipsed Play Booster Display (Japanese market)",
    "release_date":"2026-01-23", "packs_per_box":30, "cards_per_pack":"14",
    "source":"https://magic.wizards.com/ja/news/feature/collecting-lorwyn-eclipsed",
    "release_date_source":"https://magic.wizards.com/ja/news/announcements/everything-announced-for-magic-the-gathering-in-2026"
  },
  "ws-JP-ALL-bplb-2026":{
    "game":"Weiß Schwarz", "country":"JP", "product_type":"BOX",
    "set_code":"LOCAL-WS-ALL-LB-JP", "set_code_verified":False,
    "name":"Weiß Schwarz アサルトリリィ Last Bullet Booster BOX",
    "release_date":"2026-02-27", "packs_per_box":12, "cards_per_pack":"8",
    "source":"https://ws-tcg.com/products/all_bplb/",
    "msrp":{"currency":"JPY","amount":5280,"unit":"BOX"}
  },
  "dbsfw-JP-FB10-cross-force-2026":{
    "game":"DRAGON BALL SUPER: FUSION WORLD", "country":"JP",
    "product_type":"BOX", "set_code":"FB10",
    "name":"Dragon Ball Super Fusion World CROSS FORCE [FB10] Booster BOX",
    "release_date":"2026-06-13", "packs_per_box":24, "cards_per_pack":"6",
    "source":"https://www.dbs-cardgame.com/fw/jp/events/01_446.html",
    "release_date_source":"https://www.dbs-cardgame.com/fw/jp/products/01_400.html"
  }
}
FORBIDDEN=("market_price","verified_sales","verified_stock","pull_rate","psa_grade","hit_probability")
def validate_v662(doc,registry,previous=()):
    if not isinstance(doc,dict) or not isinstance(doc.get("policy"),dict):
        raise CoverageError("INVALID_V662_DOCUMENT")
    if (doc.get("schema_version")!=1 or
        doc.get("type")!="official_product_specifications_supplement" or
        doc.get("base_catalog")!=OLD_CATALOGS[0] or
        doc.get("append_after")!=V659_NAME or
        doc["policy"].get("no_paid_dependency") is not True or
        not isinstance(doc.get("products"),list) or
        len(doc["products"])!=len(EXPECTED)):
        raise CoverageError("INVALID_V662_CHAIN")
    if not isinstance(registry,dict) or not isinstance(registry.get("games"),list):
        raise CoverageError("INVALID_REGISTRY")
    declared={(g["canonical"],c) for g in registry["games"] for c in g.get("regions",[])
              if c in ("KR","JP","US")}
    old_ids={p["id"] for p in previous}
    observed=set()
    for product in doc["products"]:
        if not isinstance(product,dict):
            raise CoverageError("INVALID_V662_ROW")
        name=product.get("id")
        expected=EXPECTED.get(name)
        if name in observed or name in old_ids or not expected:
            raise CoverageError("UNAPPROVED_OR_DUPLICATE_V662_PRODUCT")
        observed.add(name)
        if ((product.get("game"),product.get("country")) not in declared or
            any(product.get(k)!=v for k,v in expected.items()) or
            any(field in product for field in FORBIDDEN) or
            (product.get("set_code","").startswith("LOCAL-") and
             product.get("set_code_verified") is not False) or
            ("msrp" in product and product["id"]!="ws-JP-ALL-bplb-2026")):
            raise CoverageError("UNTRUSTED_V662_PRODUCT")
    if observed!=set(EXPECTED):
        raise CoverageError("MISSING_V662_PRODUCT")
    return doc["products"]

def build(directory=ROOT):
    folder=Path(directory)
    reg=_load_json(folder/"tcg_game_registry.json")
    products=sum([_load_json(folder/name)["products"] for name in OLD_CATALOGS],[])
    v657=validate_overlay(_load_json(folder/OVERLAY_NAME),reg)
    v659=validate_v659(_load_json(folder/V659_NAME),reg)
    old=products+v657+v659
    extra=validate_v662(_load_json(folder/FILE),reg,old)
    original=audit(reg,{"schema_version":1,"products":old})
    updated=audit(reg,{"schema_version":1,"products":old+extra})
    def summarize(report):
        declared=[x for x in report["cells"] if x["region_declared"]]
        return {
          "official_products":report["reviewed_official_product_records"],
          "official_boxes":sum(x["official_box_count"] for x in report["cells"]),
          "region_scopes":len(declared),
          "scopes_with_box":sum(bool(x["official_box_count"]) for x in declared),
          "scopes_without_box":sum(not x["official_box_count"] for x in declared)
        }
    return {"status":"V662_REVIEW_ONLY_NO_MAIN_PROMOTION","network_calls":0,
            "paid_api_calls":0,"original":summarize(original),
            "candidate":summarize(updated),"added_count":len(extra)}
if __name__=="__main__":
    print(json.dumps(build(),ensure_ascii=False,indent=2))
