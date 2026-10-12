#!/usr/bin/env python3
"""V670 free public eBay SOLD-page sample audit; sold page != settled payment.

All observations require exact URL/item/title/date/displayed USD amount.
Never automatically publish a verified market price, delivery or payout.
"""
from __future__ import annotations
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
from execution.official_box_coverage_audit_v623 import ROOT,_load_json
FILE="tcg_public_sold_listing_observations_v670.json"
SPEC={
 "336825478808":("2026-10-03","Pokémon TCG Mega Evolution Perfect Order English Booster Box 2026",Decimal("169.99")),
 "366663297662":("2026-09-12","Pokémon TCG Mega Evolution Perfect Order Booster Box 36 Packs English 2026",Decimal("170.00")),
 "206440921471":("2026-08-01","Perfect Order Display Booster Box 36 Packs Pokémon TCG Brand New",Decimal("159.99")),
 "287489659057":("2026-07-28","Pokemon Mega Evolution Perfect Order Booster Box Sealed",Decimal("189.99")),
}
EXACT={"ebay_item_id","source_url","sold_marked_date","listing_title","displayed_price_usd",
       "currency","quantity","listing_status_observed","settlement_verified",
       "delivery_verified","returned_or_cancelled_unknown","shipping_tax_fees_unknown",
       "product_identity","eligible_for_public_price_index"}
def validate_sold_listing_observations(doc):
    if (not isinstance(doc,dict) or doc.get("schema_version")!=1 or
        doc.get("type")!="PUBLIC_SOLD_LISTING_OBSERVATIONS_NOT_SETTLEMENT_VERIFIED" or
        doc.get("game")!="Pokémon" or doc.get("country")!="US" or
        doc.get("manufacturer_product_id")!="pokemon-US-me-perfect-order-2026" or
        not isinstance(doc.get("policy"),dict) or
        not all(doc["policy"].get(k) is True for k in (
            "free_public_web_only","never_market_index_from_observation",
            "no_claim_of_captured_funds","fees_tax_shipping_unknown")) or
        not isinstance(doc.get("records"),list) or len(doc["records"])!=len(SPEC)):
        raise ValueError("INVALID_V670_EVIDENCE_POLICY")
    seen=set(); rows=[]
    for p in doc["records"]:
        if not isinstance(p,dict) or set(p)!=EXACT:
            raise ValueError("V670_UNKNOWN_SALE_FIELDS")
        item=p["ebay_item_id"]
        info=SPEC.get(item)
        if not info or item in seen:raise ValueError("V670_DUPLICATE_OR_UNVERIFIED_ITEM")
        seen.add(item)
        if (p.get("source_url")!="https://www.ebay.com/itm/"+item or
            p.get("sold_marked_date")!=info[0] or
            p.get("listing_title")!=info[1] or
            type(p.get("displayed_price_usd")) not in (int,float) or
            Decimal(str(p["displayed_price_usd"]))!=info[2] or
            p.get("currency")!="USD" or type(p.get("quantity")) is not int or
            p["quantity"]!=1 or p.get("listing_status_observed")!="SOLD" or
            p.get("settlement_verified") is not False or
            p.get("delivery_verified") is not False or
            p.get("returned_or_cancelled_unknown") is not True or
            p.get("shipping_tax_fees_unknown") is not True or
            p.get("product_identity")!="SEALED_BOOSTER_DISPLAY_SELLER_CLAIM" or
            p.get("eligible_for_public_price_index") is not False):
            raise ValueError("V670_UNTRUSTED_SOLD_OBSERVATION")
        if date.fromisoformat(info[0])>date.fromisoformat(doc["checked_at"]):
            raise ValueError("V670_FUTURE_SALE")
        rows.append(p)
    if seen!=set(SPEC):raise ValueError("V670_MISSING_SOLD_OBSERVATIONS")
    return rows
def report(directory=ROOT):
    records=validate_sold_listing_observations(_load_json(Path(directory)/FILE))
    amounts=sorted(Decimal(str(x["displayed_price_usd"])) for x in records)
    median_sample=(amounts[1]+amounts[2])/2
    return {"evidence_type":"PUBLIC_SOLD_LISTINGS_NOT_VERIFIED_PAYMENTS",
            "sold_page_observations":len(records),
            "displayed_usd_sample_min":str(amounts[0]),
            "displayed_usd_sample_max":str(amounts[-1]),
            "displayed_usd_sample_median":str(median_sample),
            "sample_is_not_market_index":True,
            "settlement_verified_count":0,"eligible_index_count":0,
            "unobserved_shipping_tax_fees":True,"network_calls":0,"paid_apis":0}
if __name__=="__main__":print(json.dumps(report(),ensure_ascii=False,indent=2))
