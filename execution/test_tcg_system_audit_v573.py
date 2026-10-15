#!/usr/bin/env python3
"""V573 external-data-free audit fixture regressions."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tcg_system_audit_v573 import audit, catalog_rows, valid_observation_day, markdown, is_valid_price_display, sale_evidence_candidate

KST=timezone(timedelta(hours=9))
NOW=datetime(2026,10,15,12,0,tzinfo=KST)
CATALOG='''<script src="box_knowledge_stats.js"></script>
<script src="market_catalog_expander.js"></script>
<div id="box12section"><div id="boxKbCount"></div><article class="box-kb-card"></article></div>
<script>
const COUNTRY_BOX_DATA=[
 {country:"JP",game:"Pokémon",name:"메가 심포니아",native:"test"},
 {country:"KR",game:"ONE PIECE",name:"로맨스 던",native:"test"}
];
</script>'''
BASE={
 "index.html": CATALOG,
 "box_knowledge_stats.js": 'window.TCGBoxPriceProofV572={};',
 "market_catalog_expander.js": "tcg-market-catalog-expanded; CN-S; CN-T;",
 "feature_category_nav.js": "window.addEventListener('load',()=>{});",
 "market_prices.json": {
   "entries": {
     "JP|메가 심포니아|BOX": {
       "game":"Pokémon","display":"₩37,000","source_date":"2026-10-14",
       "source":"https://pokard.io/","link_status":"정상"
     }
   }
 },
 "tcg_game_registry.json": {"games":[
   {"canonical":"Pokémon"},{"canonical":"ONE PIECE"}
 ]},
 "tcg_official_product_catalog_v599.json":{"products":[]},
}

def write_fixture(root, changes=None):
    data={**BASE,**(changes or {})}
    for name,value in data.items():
        target=root/name
        target.parent.mkdir(parents=True,exist_ok=True)
        if isinstance(value,str):
            target.write_text(value,encoding="utf-8")
        else:
            target.write_text(json.dumps(value,ensure_ascii=False),encoding="utf-8")


class TcgEvidenceAuditV573(unittest.TestCase):
    def with_fixture(self,changes=None):
        td=tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        root=Path(td.name)
        write_fixture(root,changes)
        return root

    def test_product_identity_and_sale_gap_not_reported_as_verified(self):
        result=audit(self.with_fixture(),NOW)
        m=result["metrics"]
        self.assertEqual(2,m["static_box_products"])
        self.assertEqual(1,m["static_box_price_exact_matches"])
        self.assertEqual(0,m["market_box_with_sale_evidence"])
        self.assertTrue(result["audit_pass"])
        self.assertFalse(result["data_complete"])
        self.assertFalse(result["device_verified"])
        self.assertIn("HOLD",markdown(result))

    def test_different_game_same_country_and_name_is_hard_failure(self):
        items={**BASE["market_prices.json"]["entries"]}
        items["KR|로맨스 던|BOX"]={
            "game":"Pokémon","display":"₩10,000","source_date":"2026-10-14",
            "source":"https://www.ebay.com/itm/123","link_status":"정상"
        }
        out=audit(self.with_fixture({"market_prices.json":{"entries":items}}),NOW)
        self.assertFalse(out["audit_pass"])
        self.assertTrue(any("collide" in e for e in out["blocking_errors"]))

    def test_invalid_sale_provenance_fails_closed(self):
        item={**BASE["market_prices.json"]["entries"]["JP|메가 심포니아|BOX"]}
        item["box_price_evidence"]=[{
          "product_key":"JP|메가 심포니아|BOX","game":"Pokémon",
          "unit":"BOX","unit_quantity":1,"sealed":True,
          "evidence_type":"completed_sale","review_status":"unverified"
        }]
        out=audit(self.with_fixture({"market_prices.json":{
             "entries":{"JP|메가 심포니아|BOX":item}
        }}),NOW)
        self.assertFalse(out["audit_pass"])
        self.assertTrue(any("unreviewed" in s for s in out["blocking_errors"]))

    def test_invalid_catalog_duplicate_blocks(self):
        html=CATALOG.replace('{country:"KR",game:"ONE PIECE",name:"로맨스 던",native:"test"}',
                 '{country:"JP",game:"Pokémon",name:"메가 심포니아",native:"test"}')
        out=audit(self.with_fixture({"index.html":html}),NOW)
        self.assertFalse(out["audit_pass"])

    def test_no_future_and_invalid_date_as_recent(self):
        self.assertEqual(1,valid_observation_day("2026-10-14",NOW))
        self.assertEqual(-1,valid_observation_day("2026-10-16",NOW))
        self.assertIsNone(valid_observation_day("2026-02-31",NOW))
        self.assertIsNone(valid_observation_day("2026-1-3",NOW))

    def test_observed_krw_range_validation_never_accepts_malformed_numbers(self):
        for display in ("₩0", "₩50,000~₩40,000", "₩10,,000", "₩1,00,000",
                        "₩-100", "₩100,000~€500", "₩10,000/8BOX"):
            self.assertFalse(is_valid_price_display({"display": display}),display)
        for display in ("₩100", "₩1,000", "₩5,000~₩7,000", "₩25000"):
            self.assertTrue(is_valid_price_display({"display": display}),display)

    def test_recent_link_metric_rejects_bad_url_even_if_status_claims_normal(self):
        item={**BASE["market_prices.json"]["entries"]["JP|메가 심포니아|BOX"]}
        item["source"]="http://pokard.io/"
        result=audit(self.with_fixture({"market_prices.json":{
            "entries":{"JP|메가 심포니아|BOX":item}
        }}),NOW)
        self.assertEqual(0,result["metrics"]["market_box_verified_recent_links"])
        self.assertEqual(1,result["metrics"]["market_box_unconfirmed_links"])

    def test_sale_candidate_metric_does_not_count_asking_or_spoofed_source(self):
        key="JP|메가 심포니아|BOX"
        base={**BASE["market_prices.json"]["entries"][key]}
        asking=dict(product_key=key,game="Pokémon",unit="BOX",unit_quantity=1,
            sealed=True,currency="KRW",price_krw=37000,evidence_type="asking",
            observed_at="2026-10-14",source_id="ebay",
            source_url="https://www.ebay.com/itm/12345678901")
        full={**asking,
            "evidence_type":"completed_sale","verification_status":"verified",
            "review_status":"manual_verified","review_method":"source_page_crosscheck",
            "transaction_finality":"sold","reviewed_at":"2026-10-15",
            "sale_id":"ebay:12345678901","lineage_key":"ebay:12345678901"
        }
        self.assertFalse(sale_evidence_candidate(key,base,asking,NOW))
        self.assertFalse(sale_evidence_candidate(key,base,{**full,"source_url":"https://ebay.com.evil.example/itm/12345678901"},NOW))
        self.assertFalse(sale_evidence_candidate(key,base,{**full,"source_id":["ebay"]},NOW))
        self.assertFalse(sale_evidence_candidate(key,base,{**full,"price_krw":True},NOW))
        self.assertFalse(sale_evidence_candidate(key,base,{**full,"sale_id":"ebay:other"},NOW))
        self.assertFalse(sale_evidence_candidate(key,base,{**full,"reviewed_at":"2026-10-13"},NOW))
        self.assertTrue(sale_evidence_candidate(key,base,full,NOW))
        for rows, count in (([asking],0),([full],1)):
            out=audit(self.with_fixture({"market_prices.json":{
                "entries":{key:{**base,"box_price_evidence":rows}}
            }}),NOW)
            self.assertEqual(count,out["metrics"]["market_box_with_sale_evidence"])

    def test_bounded_static_catalog_not_accidental_whole_page_matches(self):
        self.assertEqual(2,len(catalog_rows(CATALOG)))
        with self.assertRaises(ValueError):
            catalog_rows("<script>const OTHER=[];</script>")

    def test_actual_checkout_contains_price_guard_and_loader(self):
        real=Path(__file__).resolve().parents[1]
        result=audit(real,NOW)
        m=result["metrics"]
        self.assertGreaterEqual(m["registry_games"],3)
        self.assertGreaterEqual(m["static_box_products"],3)
        self.assertGreaterEqual(m["box_market_entries"],1)
        self.assertLessEqual(m["static_box_price_exact_matches"],m["static_box_products"])
        self.assertTrue(result["audit_pass"],result["blocking_errors"])
        self.assertFalse(result["device_verified"])


if __name__=="__main__":
    unittest.main()
