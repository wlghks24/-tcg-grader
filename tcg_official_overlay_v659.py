#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V659 verified Japan BOX proof overlay; offline and no paid services."""
from __future__ import annotations
import json
from pathlib import Path
from execution.official_box_coverage_audit_v623 import ROOT, CoverageError, _load_json, audit
from tcg_official_overlay_v657 import OLD_CATALOGS, OVERLAY_NAME, validate_overlay

FILE = "tcg_official_product_supplement_v659.json"
EXPECTED = {
    "pokemon-JP-SV9a-2025": {
        "game": "Pokémon", "country": "JP", "set_code": "SV9a",
        "source": "https://www.pokemon-card.com/products/sv/sv9a.html",
        "release_date": "2025-03-14", "packs_per_box": 30, "cards_per_pack": "5",
        "release_date_source": None,
    },
    "onepiece-JP-OP13-2025": {
        "game": "ONE PIECE", "country": "JP", "set_code": "OP-13",
        "source": "https://cp.onepiece-cardgame.com/festa/2025_summer/goods",
        "release_date": "2025-08-23", "packs_per_box": 24, "cards_per_pack": "6",
        "release_date_source": "https://www.bandai.co.jp/catalog/item.php?jan_cd=4582769864865000",
    },
}

def validate_additions(doc, registry):
    if not isinstance(doc, dict) or not isinstance(doc.get("policy"), dict):
        raise CoverageError("INVALID_V659_SUPPLEMENT")
    if (doc.get("schema_version") != 1 or
        doc.get("type") != "official_product_specifications_supplement" or
        doc.get("base_catalog") != OLD_CATALOGS[0] or
        doc.get("append_after") != OVERLAY_NAME or
        doc["policy"].get("no_paid_dependency") is not True or
        not isinstance(doc.get("products"), list) or
        len(doc["products"]) != len(EXPECTED)):
        raise CoverageError("INVALID_V659_SUPPLEMENT")
    if not isinstance(registry, dict) or not isinstance(registry.get("games"), list):
        raise CoverageError("INVALID_V659_REGISTRY")
    declared = {(g.get("canonical"),country) for g in registry["games"]
                for country in g.get("regions",[]) if country in ("KR","JP","US")}
    seen = set()
    for item in doc["products"]:
        if not isinstance(item,dict):
            raise CoverageError("INVALID_V659_PRODUCT")
        record = EXPECTED.get(item.get("id"))
        if not record or item["id"] in seen:
            raise CoverageError("UNTRUSTED_V659_IDENTITY")
        seen.add(item["id"])
        if (item.get("product_type") != "BOX" or
            (item.get("game"), item.get("country")) not in declared or
            not all(item.get(field) == correct for field,correct in record.items() if correct is not None) or
            item.get("release_date_source") != record["release_date_source"] or
            item.get("set_code_verified") not in (None,True) or
            any(field in item for field in ("msrp","market_price","verified_stock",
                                           "verified_sales","pull_rate","psa_grade"))):
            raise CoverageError("UNTRUSTED_V659_IDENTITY")
    return doc["products"]

def build(directory=ROOT):
    directory = Path(directory)
    reg = _load_json(directory / "tcg_game_registry.json")
    parts = [_load_json(directory / name)["products"] for name in OLD_CATALOGS]
    parent = _load_json(directory / OVERLAY_NAME)
    v657 = validate_overlay(parent,reg)
    extra = validate_additions(_load_json(directory / FILE), reg)
    old = audit(reg,{"schema_version":1,"products":sum(parts,[])+v657})
    new = audit(reg,{"schema_version":1,"products":sum(parts,[])+v657+extra})
    def counts(out):
        scope = [x for x in out["cells"] if x["region_declared"]]
        return {
            "products":out["reviewed_official_product_records"],
            "sealed_boxes":sum(x["official_box_count"] for x in out["cells"]),
            "declared_market_scopes":len(scope),
            "scopes_with_box":sum(x["official_box_count"]>0 for x in scope),
            "box_gaps":sum(x["official_box_count"]==0 for x in scope),
        }
    return {"status":"OFFLINE_MANUFACTURER_PROOFS_PENDING_CI","network_calls":0,
            "no_paid_dependency":True,"pre_v659":counts(old),
            "with_v659":counts(new),"new_box_records":len(extra),
            "warning":"Source host/schema audit only. All collectors/tablet and CI need agreement."}

if __name__ == "__main__":
    print(json.dumps(build(),ensure_ascii=False,indent=2))
