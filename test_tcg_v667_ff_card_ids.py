#!/usr/bin/env python3
"""V667: new 5 official Japanese card IDs; never treat box bonus as booster HIT."""
import copy
import unittest
from execution.official_box_coverage_audit_v623 import ROOT,_load_json
from tcg_manufacturer_card_overlay_v667 import validate_ff_cards,report,FILE
from tcg_manufacturer_card_overlay_v666 import combined_card_records
class V667FFOfficialCards(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.reg=_load_json(ROOT/"tcg_game_registry.json")
  cls.doc=_load_json(ROOT/FILE)
 def test_5_exact_ff_ids_and_19_across_5_games(self):
  r=validate_ff_cards(self.doc,self.reg)
  self.assertEqual(5,len(r))
  all_records=combined_card_records()
  self.assertEqual(19,len(all_records))
  self.assertEqual(5,len({p["game_id"] for p in all_records.values()}))
  self.assertIn("fftcg-JP-25-035L",r)
  self.assertEqual("UNKNOWN",r["fftcg-JP-25-035L"]["printing"])
  self.assertIsNone(r["fftcg-JP-25-035L"]["rarity"])
 def test_box_purchase_bonus_vs_legacy_and_pack_hits(self):
  docs=validate_ff_cards(self.doc,self.reg)
  bonus=docs["fftcg-JP-PR-182_25-073L"]
  self.assertEqual("BOX_PURCHASE_BONUS_FIRST_PRINT_ONLY",bonus["evidence_type"])
  self.assertNotIn("pull_odds",bonus)
  self.assertEqual(1,report()["first_print_only_buy_a_box_promos"])
  self.assertEqual(0,report()["random_pack_hit_probability_verified"])
 def test_tampered_price_code_identity_and_nonbonus_rejected(self):
  for key,value in (("card_name","假的卡"),
                    ("source_url","https://jp.finalfantasy.com.evil.example/news/5475"),
                    ("printing","PSA10"),("rarity","SECRET"),("hit_probability",0.95)):
   with self.subTest(key=key):
    bad=copy.deepcopy(self.doc);bad["records"][0][key]=value
    with self.assertRaises(ValueError):validate_ff_cards(bad,self.reg)
  bad=copy.deepcopy(self.doc)
  bad["records"][4]["evidence_type"]="GUARANTEED_BOX_HIT"
  with self.assertRaisesRegex(ValueError,"V667_UNTRUSTED_FF_CARD"):validate_ff_cards(bad,self.reg)
 def test_exact_market_and_registry(self):
  bad=copy.deepcopy(self.doc);bad["records"][1]["market"]="US"
  with self.assertRaises(ValueError):validate_ff_cards(bad,self.reg)
if __name__=="__main__":unittest.main(verbosity=2)
