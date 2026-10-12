#!/usr/bin/env python3
"""V669: strictly validated Japan Godzilla 12-pack display, not a box HIT."""
from __future__ import annotations
import json
from pathlib import Path
from execution.official_box_coverage_audit_v623 import ROOT,CoverageError,_load_json,audit
from tcg_official_overlay_v667 import FILE as PARENT,load_chain
FILE="tcg_official_product_supplement_v669.json"
ID="godzilla-JP-BP01-godzilla-vs-godzilla-2025"
SPEC={"id":ID,"game":"Godzilla Card Game","country":"JP","product_type":"BOX",
      "set_code":"LOCAL-GODZILLA-BP01-JP","set_code_verified":False,
      "name":"ゴジラ カードゲーム ブースターパック ゴジラVSゴジラ 日本語版 BOX",
      "release_date":"2025-07-05","source":"https://godzilla-cardgame.com/products/bp01/",
      "packs_per_box":12,"cards_per_pack":"7",
      "msrp":{"currency":"JPY","amount":5280,"unit":"BOX"}}
ALLOWED=set(SPEC)|{"notes"}
def validate_v669(doc,registry,prior=()):
    if (not isinstance(doc,dict) or doc.get("schema_version")!=1 or
        doc.get("type")!="official_product_specifications_supplement" or
        doc.get("append_after")!=PARENT or
        doc.get("base_catalog")!="tcg_official_product_catalog_v599.json" or
        not isinstance(doc.get("policy"),dict) or
        doc["policy"].get("no_paid_dependency") is not True or
        not isinstance(doc.get("products"),list) or len(doc["products"])!=1):
        raise CoverageError("V669_INVALID_CHAIN")
    if not isinstance(registry,dict) or not any(
        g.get("canonical")=="Godzilla Card Game" and "JP" in g.get("regions",[])
        for g in registry.get("games",[])):
        raise CoverageError("V669_UNDECLARED_REGION")
    p=doc["products"][0]
    if (not isinstance(p,dict) or set(p)!=ALLOWED or
        type(p.get("packs_per_box")) is not int or
        not isinstance(p.get("notes"),str) or
        any(p.get(k)!=v for k,v in SPEC.items()) or
        not isinstance(p.get("msrp"),dict) or
        set(p["msrp"])!={"currency","amount","unit"} or
        type(p["msrp"]["amount"]) is not int or
        any(row.get("id")==ID for row in prior if isinstance(row,dict))):
        raise CoverageError("V669_UNTRUSTED_JP_BOX")
    return doc["products"]
def build(directory=ROOT):
    d=Path(directory); reg,old,prev=load_chain(d); old+=prev
    new=validate_v669(_load_json(d/FILE),reg,old)
    before=audit(reg,{"schema_version":1,"products":old})
    after=audit(reg,{"schema_version":1,"products":old+new})
    def counts(result):
        declared=[r for r in result["cells"] if r["region_declared"]]
        return {"products":result["reviewed_official_product_records"],
                "boxes":sum(r["official_box_count"] for r in result["cells"]),
                "scopes":len(declared),
                "with_box":sum(bool(r["official_box_count"]) for r in declared),
                "gaps":sum(not r["official_box_count"] for r in declared)}
    return {"status":"OFFICIAL_JP_GODZILLA_SOURCE_LOCKED",
            "previous":counts(before),"current":counts(after),
            "verified_completed_sales":0,"network_calls":0}
if __name__=="__main__":print(json.dumps(build(),ensure_ascii=False,indent=2))
