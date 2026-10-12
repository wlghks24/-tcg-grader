#!/usr/bin/env python3
"""V667: manufacturer JP FFTCG format transition, fail-closed on MSRP/SKU."""
from __future__ import annotations
from pathlib import Path
import json
from execution.official_box_coverage_audit_v623 import ROOT,CoverageError,_load_json,audit
from tcg_official_overlay_v665 import FILE as PARENT
from tcg_official_overlay_v657 import OLD_CATALOGS,OVERLAY_NAME,validate_overlay
from tcg_official_overlay_v659 import FILE as F659,validate_additions
from tcg_official_overlay_v662 import FILE as F662,validate_v662
from tcg_official_overlay_v663 import FILE as F663,PROMO,validate_v663,validate_promo
from tcg_official_overlay_v665 import validate_v665
FILE="tcg_official_product_supplement_v667.json"
SPECS={
"fftcg-JP-2025-tears-of-the-planet-36":{
"name":"FINAL FANTASY TRADING CARD GAME 星の涙 日本語版 BOX",
"set_code":"LOCAL-FFTCG-JP-TEARS-2025","release_date":"2025-03-28",
"source":"https://jp.finalfantasy.com/news/5475","packs_per_box":36,"cards_per_pack":"12",
"msrp":{"currency":"JPY","amount":15840,"unit":"BOX"}},
"fftcg-JP-2025-gunslinger-18":{
"name":"FINAL FANTASY TRADING CARD GAME 深淵のガンスリンガー 日本語版 BOX",
"set_code":"LOCAL-FFTCG-JP-GUNSLINGER-2025","release_date":"2025-08-08",
"source":"https://jp.finalfantasy.com/news/5659","packs_per_box":18,"cards_per_pack":"12",
"msrp":{"currency":"JPY","amount":8910,"unit":"BOX"}}
}
ALLOWED={"id","game","country","product_type","set_code","set_code_verified","name","release_date","source","packs_per_box","cards_per_pack","msrp","notes"}
def validate_v667(doc,registry,previous=()):
    if (not isinstance(doc,dict) or doc.get("schema_version")!=1 or
        doc.get("type")!="official_product_specifications_supplement" or
        doc.get("base_catalog")!=OLD_CATALOGS[0] or doc.get("append_after")!=PARENT or
        not isinstance(doc.get("policy"),dict) or
        doc["policy"].get("no_paid_dependency") is not True or
        not isinstance(doc.get("products"),list) or len(doc["products"])!=2):
        raise CoverageError("INVALID_V667_CHAIN")
    if not isinstance(registry,dict) or not any(g.get("canonical")=="Final Fantasy TCG" and "JP" in g.get("regions",[]) for g in registry.get("games",[])):
        raise CoverageError("V667_UNDECLARED_JP_GAME")
    prior={p.get("id") for p in previous if isinstance(p,dict)}
    seen=set()
    for row in doc["products"]:
        if not isinstance(row,dict) or set(row)!=ALLOWED:
            raise CoverageError("V667_UNKNOWN_EXTRA_FIELDS")
        s=SPECS.get(row.get("id"))
        if not s or row["id"] in seen or row["id"] in prior:
            raise CoverageError("V667_UNKNOWN_DUPLICATE_PRODUCT")
        seen.add(row["id"])
        if (row.get("game")!="Final Fantasy TCG" or row.get("country")!="JP" or row.get("product_type")!="BOX" or
            row.get("set_code_verified") is not False or type(row.get("packs_per_box")) is not int or
            not isinstance(row.get("notes"),str) or
            any(row.get(k)!=v for k,v in s.items()) or
            not isinstance(row.get("msrp"),dict) or set(row["msrp"])!={"currency","amount","unit"} or
            type(row["msrp"]["amount"]) is not int):
            raise CoverageError("V667_INVALID_MANUFACTURER_SPEC")
    if seen!=set(SPECS):raise CoverageError("V667_INCOMPLETE_PAIR")
    return doc["products"]
def load_chain(folder=ROOT):
    folder=Path(folder); reg=_load_json(folder/"tcg_game_registry.json")
    old=sum((_load_json(folder/name)["products"] for name in OLD_CATALOGS),[])
    old+=validate_overlay(_load_json(folder/OVERLAY_NAME),reg)
    old+=validate_additions(_load_json(folder/F659),reg)
    old+=validate_v662(_load_json(folder/F662),reg,old)
    validate_promo(_load_json(folder/PROMO))
    old+=validate_v663(_load_json(folder/F663),reg,old)
    old+=validate_v665(_load_json(folder/PARENT),reg,old)
    new=validate_v667(_load_json(folder/FILE),reg,old)
    return reg,old,new
def build(directory=ROOT):
    reg,old,new=load_chain(directory)
    before=audit(reg,{"schema_version":1,"products":old})
    after=audit(reg,{"schema_version":1,"products":old+new})
    def summary(x):
        scopes=[r for r in x["cells"] if r["region_declared"]]
        return {"products":x["reviewed_official_product_records"],
         "boxes":sum(r["official_box_count"] for r in x["cells"]),
         "scopes":len(scopes),"with_box":sum(bool(r["official_box_count"]) for r in scopes),
         "box_gaps":sum(not r["official_box_count"] for r in scopes)}
    return {"state":"MANUFACTURER_VERIFIED_SAMPLE_NOT_FULL_COVERAGE",
            "prior":summary(before),"with_v667":summary(after),
            "format_transition":{"2025_03":36,"2025_08":18,"same_game_country":True},
            "network_calls":0,"verified_completed_sales":0}
if __name__=="__main__":print(json.dumps(build(),ensure_ascii=False,indent=2))
