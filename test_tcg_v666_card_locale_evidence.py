#!/usr/bin/env python3
"""V666: cross-edition pack specs and official card IDs without print/price hallucination."""
import copy
import csv
from datetime import date
import io
import unittest

from execution.official_box_coverage_audit_v623 import ROOT,_load_json
from tcg_manufacturer_card_overlay_v666 import (
   CARD_FILE,SPEC_FILE,validate_additional,validate_country_pack_difference,
   combined_card_records,report,
)
from tcg_card_trade_evidence_v660 import CSV_FIELDS,stage_csv

def read(name):return _load_json(ROOT/name)

class CardIdentityAndCountryGuardV666(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=read("tcg_game_registry.json")
        cls.base=read("tcg_manufacturer_card_evidence_v660.json")
        cls.extra=read(CARD_FILE)
        cls.pack=read(SPEC_FILE)

    def test_card_pair_count_is_four_games_and_not_product_or_price(self):
        all_items=combined_card_records()
        self.assertEqual(19,len(all_items))
        self.assertEqual({"digimon","onepiece","hololive-ocg","dbsfw","final-fantasy-tcg"},
                         {i["game_id"] for i in all_items.values()})
        self.assertEqual(11,len(validate_additional(self.extra,self.registry)))
        self.assertEqual("Nekomata Okayu",all_items["hololive-US-hBP05-004"]["card_name"])
        self.assertIsNone(all_items["hololive-US-hBP05-004"]["rarity"])
        self.assertEqual("UNKNOWN",all_items["dbsfw-US-FB10-001"]["printing"])
        self.assertEqual(0,report()["verified_sales"])
        self.assertEqual(0,report()["network_calls"])

    def test_pack_japan_six_vs_us_twelve_no_box_fabricated(self):
        result=validate_country_pack_difference(self.pack)
        self.assertEqual((6,12),(result["JP_cards_per_pack"],result["US_cards_per_pack"]))
        self.assertFalse(result["US_box_pack_count_known"])
        for kind,value in (("JP",12),("US",6)):
            tampered=copy.deepcopy(self.pack)
            tampered["known_pack_content"][kind]["cards_per_pack"]=value
            with self.assertRaises(ValueError):validate_country_pack_difference(tampered)
        tampered=copy.deepcopy(self.pack)
        tampered["unverified"]["us_booster_packs_per_display_box"]=24
        with self.assertRaisesRegex(ValueError,"V666_INVENTED_US_BOX_OR_PRICE"):
            validate_country_pack_difference(tampered)

    def test_card_name_set_evidence_and_unknown_fields_are_bound(self):
        for field,value in (("card_name","Nekomata Koyori"),
                            ("printing","ALT_ART"),
                            ("rarity","SEC"),
                            ("card_number","hBP05-999"),
                            ("source_url","https://en.hololive-official-cardgame.com.evil.test/")):
            corrupted=copy.deepcopy(self.extra)
            corrupted["records"][1][field]=value
            with self.assertRaisesRegex(ValueError,"V666_UNTRUSTED_CARD_IDENTITY"):
                validate_additional(corrupted,self.registry)
        corrupted=copy.deepcopy(self.extra)
        corrupted["records"][2]["market_price"]=20000
        with self.assertRaisesRegex(ValueError,"V666_UNRECOGNIZED_CARD_FIELDS"):
            validate_additional(corrupted,self.registry)

    def test_english_card_can_be_staged_but_claim_not_verified_sale(self):
        out=io.StringIO()
        writer=csv.DictWriter(out,fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerow(dict(card_ref="hololive-US-hBP05-004",market="US",
            source_type="COMPLETED_SALE_CLAIM",
            source_url="https://example.org/report/123",
            observed_at="2026-10-12",currency="USD",amount="30",
            condition="NM",grade_service="RAW",grade=""))
        result=stage_csv(out.getvalue(),as_of=date(2026,10,12))
        self.assertEqual((1,0,0),(result["accepted_count"],result["rejected_count"],
                                  result["verified_sale_count"]))
        row=result["accepted"][0]
        self.assertEqual("USER_SUPPLIED_UNVERIFIED",row["evidence_status"])
        self.assertFalse(row["eligible_for_public_price_index"])
        self.assertFalse(row["is_completed_sale_verified"])

    def test_explicit_base_only_fixture_remains_three_cards(self):
        output=io.StringIO()
        writer=csv.DictWriter(output,fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerow(dict(card_ref="hololive-US-hBP05-004",market="US",
            source_type="SALE_LISTING",source_url="https://example.org/sale",
            observed_at="2026-10-12",currency="USD",amount="10",
            condition="NM",grade_service="RAW",grade=""))
        r=stage_csv(output.getvalue(),self.base,as_of=date(2026,10,12))
        self.assertEqual(0,r["accepted_count"])
        self.assertEqual("UNVERIFIED_CARD_NUMBER_OR_PRINTING",r["rejected"][0]["reason"])

if __name__=="__main__":
    unittest.main(verbosity=2)
