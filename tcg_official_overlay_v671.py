#!/usr/bin/env python3
"""V671: Korean publisher 12th CookieRun booster display proof, no variant bleed."""
from pathlib import Path
import json
from execution.official_box_coverage_audit_v623 import ROOT,CoverageError,_load_json,audit
from tcg_official_overlay_v667 import load_chain as load_v667
from tcg_official_overlay_v669 import FILE as PARENT,validate_v669
FILE="tcg_official_product_supplement_v671.json"
SPEC={"id":"cookierun-KR-BS12-festival-arena-2026",
 "game":"CookieRun: Braverse TCG","country":"KR","product_type":"BOX",
 "set_code":"LOCAL-COOKIE-KR-BS12","set_code_verified":False,
 "name":"쿠키런 카드 게임 부스터 팩 12탄 [페스티벌 아레나] 30팩 BOX",
 "release_date":"2026-09-11",
 "source":"https://cookierunbraverse.com/ko/product/detail?id=245",
 "packs_per_box":30,"cards_per_pack":"5",
 "msrp":{"currency":"KRW","amount":30000,"unit":"BOX"}}
ALLOWED=set(SPEC)|{"notes"}
def validate_v671(doc,registry,prior=()):
    if (not isinstance(doc,dict) or doc.get("schema_version")!=1 or
        doc.get("type")!="official_product_specifications_supplement" or
        doc.get("base_catalog")!="tcg_official_product_catalog_v599.json" or
        doc.get("append_after")!=PARENT or
        not isinstance(doc.get("policy"),dict) or
        doc["policy"].get("no_paid_dependency") is not True or
        not isinstance(doc.get("products"),list) or len(doc["products"])!=1):
        raise CoverageError("V671_INVALID_CHAIN")
    if not any(g.get("canonical")==SPEC["game"] and "KR" in g.get("regions",[])
               for g in registry.get("games",[])):
        raise CoverageError("V671_UNDECLARED_KR_SCOPE")
    p=doc["products"][0]
    if (not isinstance(p,dict) or set(p)!=ALLOWED or
        not isinstance(p.get("notes"),str) or
        type(p.get("packs_per_box")) is not int or
        any(p.get(k)!=v for k,v in SPEC.items()) or
        not isinstance(p.get("msrp"),dict) or
        set(p["msrp"])!={"currency","amount","unit"} or
        type(p["msrp"]["amount"]) is not int or
        any(x.get("id")==SPEC["id"] for x in prior if isinstance(x,dict))):
        raise CoverageError("V671_UNTRUSTED_KR_PRODUCT")
    return doc["products"]
def build(directory=ROOT):
    d=Path(directory);reg,old,ff=load_v667(d);old+=ff
    old+=validate_v669(_load_json(d/PARENT),reg,old)
    additions=validate_v671(_load_json(d/FILE),reg,old)
    before=audit(reg,{"schema_version":1,"products":old})
    after=audit(reg,{"schema_version":1,"products":old+additions})
    def counts(report):
        scopes=[x for x in report["cells"] if x["region_declared"]]
        return {"official_products":report["reviewed_official_product_records"],
                "box_samples":sum(x["official_box_count"] for x in report["cells"]),
                "declared_scopes":len(scopes),
                "scope_with_box":sum(bool(x["official_box_count"]) for x in scopes),
                "scope_gaps":sum(not x["official_box_count"] for x in scopes)}
    return {"previous":counts(before),"current":counts(after),"network_calls":0,
            "confirmed_transaction_settlements":0,"no_paid_api":True}
if __name__=="__main__":print(json.dumps(build(),ensure_ascii=False,indent=2))
