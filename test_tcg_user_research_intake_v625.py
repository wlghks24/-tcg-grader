#!/usr/bin/env python3
"""V625: user leads cannot auto-promote products, prices, HIT odds, or grading."""
import copy
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent


class UserResearchIntakeV625Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.intake = json.loads((ROOT / "tcg_user_research_intake_v625.json").read_text(encoding="utf-8"))
        cls.registry = json.loads((ROOT / "tcg_game_registry.json").read_text(encoding="utf-8"))
        cls.official = json.loads((ROOT / "tcg_official_product_catalog_v599.json").read_text(encoding="utf-8"))

    def test_all_30_game_registry_entries_have_one_intake_row(self):
        rows=self.intake["records"]
        ids={r["game_id"] for r in rows}
        self.assertEqual(30,len(rows))
        self.assertEqual(30,len(ids))
        self.assertEqual({g["id"] for g in self.registry["games"]},ids)
        self.assertEqual("user_supplied_research_leads",self.intake["source_kind"])
        self.assertEqual("UNVERIFIED",self.intake["data_evidence_level"])

    def test_candidate_list_is_never_marked_as_verified_market_or_grade_data(self):
        policy=self.intake["policy"]
        for flag in ("auto_publish_as_official","auto_enable_grading","auto_publish_pricing",
                     "auto_publish_inventory","auto_publish_pull_rates","no_paid_api_or_automatic_purchase"):
            if flag=="no_paid_api_or_automatic_purchase":self.assertTrue(policy[flag])
            else:self.assertFalse(policy[flag])
        for r in self.intake["records"]:
            self.assertEqual("USER_SUBMITTED_UNVERIFIED",r["status"])
            self.assertEqual("NONE",r["market_price_evidence"])
            self.assertEqual("NOT_ESTABLISHED_BY_USER_TEXT",r["official_product_evidence"])
            self.assertTrue(r["product_name_candidates"] or r["upcoming_name_candidates"])

    def test_corrections_separate_standalone_from_collaboration(self):
        rows={r["game_id"]:r for r in self.intake["records"]}
        for game in ("gundam","godzilla-card-game"):
            correction=rows[game]["review_correction"]
            self.assertEqual("MISCLASSIFIED_STANDALONE",correction["kind"])
            self.assertTrue(correction["source"].startswith("https://"))
        for game in ("naruto","metazoo","palworld-ocg","mtg","lorcana","riftbound"):
            self.assertIsNotNone(rows[game]["review_correction"])
        self.assertIn("2027",rows["naruto"]["review_correction"]["detail"])
        self.assertIn("2025",rows["metazoo"]["review_correction"]["detail"])

    def test_official_catalog_does_not_import_user_hit_names_or_prices(self):
        for row in self.official["products"]:
            self.assertNotIn("source_kind",row)
            self.assertNotIn("USER_SUBMITTED_UNVERIFIED",row.values())
            self.assertNotIn("pull_rate",row)
            self.assertNotIn("verified_sales",row)
        self.assertEqual(47,len(self.official["products"]))
        self.assertEqual(10,len({row["game"] for row in self.official["products"]}))

    def test_hit_and_promo_leads_remain_names_not_fabricated_assessments(self):
        for r in self.intake["records"]:
            self.assertTrue(all(isinstance(x,str) and x.strip() for x in r["hit_name_candidates"]))
            self.assertTrue(all(isinstance(x,str) and x.strip() for x in r["promo_name_candidates"]))
            self.assertFalse(any("grade_probabilities" in r for r in self.intake["records"]))

    def test_all_official_product_source_records_remain_outside_candidate_file(self):
        self.assertNotIn("products",self.intake)
        self.assertNotIn("market_prices",self.intake)
        self.assertNotIn("completed_sales",self.intake)
        for row in self.intake["records"]:
            self.assertNotIn("msrp",row)
            self.assertNotIn("release_date_verified",row)

if __name__=="__main__":
    unittest.main(verbosity=2)
