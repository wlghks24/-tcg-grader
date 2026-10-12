#!/usr/bin/env python3
"""V667: Japanese Square Enix FF-TCG card-number samples; bonus≠pack HIT."""
from pathlib import Path
import json
from execution.official_box_coverage_audit_v623 import ROOT,_load_json
FILE="tcg_manufacturer_card_evidence_v667.json"
SOURCE="https://jp.finalfantasy.com/news/5475"
EXPECTED={
"25-035L":("エアリス","SET_SPECIAL_HIGHLIGHT"),
"13-090L":("オヴェリア","LEGACY_REPRINT_HIGHLIGHT"),
"16-011L":("スコール","LEGACY_REPRINT_HIGHLIGHT"),
"21-027L":("グリーヴァ","LEGACY_REPRINT_HIGHLIGHT"),
"PR-182/25-073L":("ザックス","BOX_PURCHASE_BONUS_FIRST_PRINT_ONLY")
}
FIELDS={"id","game_id","game","market","set_code","card_number","card_name",
        "rarity","printing","evidence_type","source_url","notes"}
def validate_ff_cards(doc,registry):
    if (not isinstance(doc,dict) or doc.get("schema_version")!=1 or
      doc.get("type")!="MANUFACTURER_ADDITIVE_CARD_IDENTITY_SAMPLE" or
      doc.get("append_after")!="tcg_manufacturer_card_evidence_v666.json" or
      doc.get("source")!=SOURCE or not isinstance(doc.get("policy"),dict) or
      not all(doc["policy"].get(k) is True for k in
          ("no_bulk_copyright_copying","no_verified_market_prices","no_in_pack_probability_inferred","no_grade_predictions")) or
      not isinstance(doc.get("records"),list) or len(doc["records"])!=5):
        raise ValueError("INVALID_V667_CARD_EVIDENCE_CHAIN")
    if not isinstance(registry,dict) or not any(
      g.get("id")=="final-fantasy-tcg" and g.get("canonical")=="Final Fantasy TCG" and "JP" in g.get("regions",[])
      for g in registry.get("games",[])):
        raise ValueError("INVALID_V667_FF_REGISTRY")
    found={}
    for p in doc["records"]:
        if not isinstance(p,dict) or set(p)!=FIELDS:
            raise ValueError("V667_INVALID_CARD_EVIDENCE_KEYS")
        number=p["card_number"];wanted=EXPECTED.get(number)
        if not wanted or number in found:raise ValueError("V667_UNKNOWN_DUPLICATE_NUMBER")
        note="First-production display bonus, NOT a random pack pull" if number=="PR-182/25-073L" else "Official Square Enix article number/name identity, not an assertion of particular art, printing or sold value"
        if (p.get("id")!="fftcg-JP-"+number.replace("/","_") or
          p.get("game_id")!="final-fantasy-tcg" or p.get("game")!="Final Fantasy TCG" or
          p.get("market")!="JP" or p.get("set_code")!="LOCAL-FFTCG-JP-TEARS-2025" or
          p.get("card_name")!=wanted[0] or p.get("evidence_type")!=wanted[1] or
          p.get("source_url")!=SOURCE or p.get("notes")!=note or
          p.get("rarity") is not None or p.get("printing")!="UNKNOWN"):
            raise ValueError("V667_UNTRUSTED_FF_CARD")
        found[number]=p
    if set(found)!=set(EXPECTED):raise ValueError("V667_MISSING_FF_CARD")
    return {p["id"]:p for p in found.values()}
def report():
    r=_load_json(ROOT/"tcg_game_registry.json")
    cards=validate_ff_cards(_load_json(ROOT/FILE),r)
    return {"manufacturer_number_name_samples":len(cards),
            "random_pack_hit_probability_verified":0,
            "first_print_only_buy_a_box_promos":1,
            "verified_completed_market_sales":0,"network_calls":0}
if __name__=="__main__":print(json.dumps(report(),ensure_ascii=False,indent=2))
