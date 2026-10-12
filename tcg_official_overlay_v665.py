#!/usr/bin/env python3
"""V665: exact official UNION ARENA JP box proof; no inferred retail or HIT odds."""
from __future__ import annotations
import json
from pathlib import Path
from execution.official_box_coverage_audit_v623 import ROOT,CoverageError,_load_json,audit
from tcg_official_overlay_v657 import OLD_CATALOGS,OVERLAY_NAME,validate_overlay
from tcg_official_overlay_v659 import FILE as F659,validate_additions
from tcg_official_overlay_v662 import FILE as F662,validate_v662
from tcg_official_overlay_v663 import FILE as F663,PROMO,validate_v663,validate_promo

FILE="tcg_official_product_supplement_v665.json"
SPEC={
 "id":"unionarena-JP-UA50BT-inuyasha-2026",
 "game":"UNION ARENA",
 "country":"JP",
 "product_type":"BOX",
 "set_code":"UA50BT",
 "name":"UNION ARENA ブースターパック 犬夜叉 [UA50BT] Booster BOX",
 "release_date":"2026-05-29",
 "source":"https://www.unionarena-tcg.com/jp/products/boosters/iys-1.php",
 "packs_per_box":16,
 "cards_per_pack":"8",
}
ALLOWED=set(SPEC)|{"notes"}
def validate_v665(doc,registry,previous=()):
    if not isinstance(doc,dict) or not isinstance(doc.get("policy"),dict):
        raise CoverageError("INVALID_V665_DOCUMENT")
    if (doc.get("schema_version")!=1 or
        doc.get("type")!="official_product_specifications_supplement" or
        doc.get("base_catalog")!=OLD_CATALOGS[0] or
        doc.get("append_after")!=F663 or
        doc["policy"].get("no_paid_dependency") is not True or
        not isinstance(doc.get("products"),list) or len(doc["products"])!=1):
        raise CoverageError("INVALID_V665_CHAIN")
    if not isinstance(registry,dict) or not isinstance(registry.get("games"),list):
        raise CoverageError("INVALID_V665_REGISTRY")
    declared=any(x.get("canonical")=="UNION ARENA" and
        ("JP" in x.get("regions",[]) or "GLOBAL" in x.get("regions",[]))
        for x in registry["games"])
    p=doc["products"][0]
    if not isinstance(p,dict) or not declared:
        raise CoverageError("INVALID_V665_REGION_OR_PRODUCT")
    if (set(p)!=ALLOWED or any(p.get(k)!=v for k,v in SPEC.items()) or
        type(p.get("packs_per_box")) is not int or
        not isinstance(p.get("notes"),str) or
        any(isinstance(q,dict) and q.get("id")==SPEC["id"] for q in previous)):
        raise CoverageError("UNTRUSTED_V665_BOX_SPEC")
    return doc["products"]

def build(directory=ROOT):
    directory=Path(directory)
    registry=_load_json(directory/"tcg_game_registry.json")
    old=sum([_load_json(directory/name)["products"] for name in OLD_CATALOGS],[])
    old+=validate_overlay(_load_json(directory/OVERLAY_NAME),registry)
    old+=validate_additions(_load_json(directory/F659),registry)
    old+=validate_v662(_load_json(directory/F662),registry,old)
    validate_promo(_load_json(directory/PROMO))
    old+=validate_v663(_load_json(directory/F663),registry,old)
    latest=validate_v665(_load_json(directory/FILE),registry,old)
    before=audit(registry,{"schema_version":1,"products":old})
    after=audit(registry,{"schema_version":1,"products":old+latest})
    def counts(report):
        rows=[r for r in report["cells"] if r["region_declared"]]
        return {"products":report["reviewed_official_product_records"],
                "boxes":sum(r["official_box_count"] for r in report["cells"]),
                "declared_scopes":len(rows),
                "box_scopes":sum(bool(r["official_box_count"]) for r in rows),
                "box_gaps":sum(not r["official_box_count"] for r in rows)}
    return {"state":"OFFLINE_MANUFACTURER_SPEC_REVIEW",
            "prior":counts(before),"with_v665":counts(after),
            "network_calls":0,"paid_dependencies":0,
            "not_a_market_price":True,"not_numeric_hit_odds":True}

if __name__=="__main__":
    print(json.dumps(build(),ensure_ascii=False,indent=2))
