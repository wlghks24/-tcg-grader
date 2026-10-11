#!/usr/bin/env python3
"""V627: honest audited official 2026 MTG sealed BOX and evidence-gap coverage."""
import copy
from datetime import date
import json
from pathlib import Path
import unittest

from official_product_evidence_audit_v627 import build_report
from execution.official_box_coverage_audit_v623 import audit, CoverageError

ROOT = Path(__file__).resolve().parent
SET_DATES = {"FRA":"2026-10-02","SOS":"2026-04-24","ECL":"2026-01-23"}
OFFICIAL_LINK = {
    "FRA":"https://magic.wizards.com/en/news/feature/collecting-reality-fracture",
    "SOS":"https://magic.wizards.com/en/news/feature/collecting-secrets-of-strixhaven",
    "ECL":"https://magic.wizards.com/en/news/feature/collecting-lorwyn-eclipsed",
}

class OfficialMtgAndEvidenceV627(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=json.loads((ROOT/"tcg_game_registry.json").read_text(encoding="utf-8"))
        cls.catalog=json.loads((ROOT/"tcg_official_product_catalog_v599.json").read_text(encoding="utf-8"))

    def mtg(self):
        return [p for p in self.catalog["products"] if p["game"]=="Magic: The Gathering"]

    def test_six_verified_set_packaging_variants_not_six_independent_sets(self):
        rows=self.mtg()
        self.assertEqual(6,len(rows))
        self.assertEqual({f"LOCAL-{set_code}-{fmt}-BOX" for set_code in SET_DATES
                          for fmt in ("PLAY","COLLECTOR")},{p["set_code"] for p in rows})
        for row in rows:
            parts=row["id"].split("-")
            set_code,fmt=parts[2],parts[3]
            self.assertEqual("US",row["country"])
            self.assertEqual("BOX",row["product_type"])
            self.assertEqual(SET_DATES[set_code],row["release_date"])
            self.assertEqual(OFFICIAL_LINK[set_code],row["source"])
            self.assertIs(row["set_code_verified"],False)
            self.assertEqual("2026-10-12",row["source_checked_at"])
            self.assertEqual((30,"14") if fmt=="PLAY" else (12,"15"),
                             (row["packs_per_box"],row["cards_per_pack"]))
            self.assertNotIn("msrp",row)
            self.assertNotIn("pull_rate",row)
            self.assertNotIn("verified_sales",row)

    def test_actual_registry_country_coverage_is_only_us(self):
        report=audit(self.registry,self.catalog,as_of=date(2026,10,12))
        self.assertEqual(53,report["reviewed_official_product_records"])
        self.assertEqual(30,report["registry_games"])
        self.assertEqual(55,report["declared_game_country_pairs"])
        self.assertEqual(12,report["pairs_with_any_official_product"])
        self.assertEqual(43,report["game_country_product_coverage_gaps"])
        cells={(r["game_id"],r["country"]):r for r in report["cells"]}
        self.assertEqual(6,cells[("mtg","US")]["official_box_count"])
        self.assertEqual(0,cells[("mtg","JP")]["official_box_count"])
        self.assertEqual("OFFICIAL_PRODUCT_COVERAGE_GAP",cells[("mtg","JP")]["status"])
        self.assertEqual("NOT_DECLARED_FOR_GAME",cells[("mtg","KR")]["status"])

    def test_reject_mtg_impersonation_domain_and_fabricated_box_prices(self):
        bad=copy.deepcopy(self.catalog)
        row=next(p for p in bad["products"] if p["id"]=="mtg-US-FRA-PLAY-BOX")
        row["source"]="https://magic.wizards.com.evil.example/en/products"
        with self.assertRaisesRegex(CoverageError,"UNTRUSTED_OR_UNMATCHED_OFFICIAL_SOURCE"):
            audit(self.registry,bad)
        bad=copy.deepcopy(self.catalog)
        row=next(p for p in bad["products"] if p["id"]=="mtg-US-FRA-PLAY-BOX")
        row["msrp"]={"currency":"USD","amount":5.49,"unit":"PACK"}
        with self.assertRaisesRegex(CoverageError,"INVALID_MSRP_CURRENCY_OR_UNIT"):
            audit(self.registry,bad)

    def test_all_entries_still_audited_and_missing_content_is_explicit(self):
        result=build_report(self.registry,self.catalog,as_of=date(2026,10,12))
        self.assertEqual(53,result["product_sample_count"])
        self.assertEqual(12,result["pairs_with_product_sample"])
        self.assertEqual(43,result["zero_product_record_pairs"])
        self.assertEqual(53,len(result["review_queue"]))
        self.assertTrue(result["no_verified_completed_market_sales"])
        self.assertTrue(result["no_verified_hit_pull_rate"])
        self.assertTrue(result["no_independent_source_content_match_audit"])
        self.assertEqual(47,result["missing_evidence_counts"]["SOURCE_RECHECK_TIMESTAMP_NOT_RECORDED"])
        self.assertGreater(result["missing_evidence_counts"]["PRODUCT_MSRP_NOT_REVIEWED"],0)
        self.assertGreater(result["missing_evidence_counts"]["DIRECT_PRODUCT_EVIDENCE_LINK_NOT_RECORDED"],0)
        self.assertTrue(all("missing_count" in r for r in result["review_queue"]))
        for r in result["review_queue"]:
            self.assertNotIn("certified",r)
            self.assertNotIn("hit_probability",r)
            self.assertNotIn("market_price",r)

    def test_product_item_specificity_is_only_heuristic(self):
        result=build_report(self.registry,self.catalog)
        entries={row["id"]:row for row in result["review_queue"]}
        self.assertEqual("PRODUCT_OR_EDITORIAL_PAGE_UNVERIFIED_CONTENT_MATCH",
                         entries["mtg-US-FRA-PLAY-BOX"]["source_specificity"])
        self.assertEqual("CATEGORY_INDEX_ONLY",
                         entries["pk-JP-NINJA-2026"]["source_specificity"])
        self.assertIn("DIRECT_PRODUCT_EVIDENCE_LINK_NOT_RECORDED",
                      entries["pk-JP-NINJA-2026"]["missing_evidence"])
        self.assertIn("PRODUCT_MSRP_NOT_REVIEWED",
                      entries["mtg-US-FRA-COLLECTOR-BOX"]["missing_evidence"])

    def test_fake_source_recheck_date_cannot_count_as_verified(self):
        bad=copy.deepcopy(self.catalog)
        row=next(p for p in bad["products"] if p["id"]=="mtg-US-FRA-PLAY-BOX")
        row["source_checked_at"]="2027-01-01"
        with self.assertRaisesRegex(CoverageError,"INVALID_SOURCE_RECHECK_DATE"):
            build_report(self.registry,bad,as_of=date(2026,10,12))
        row["source_checked_at"]="2026-99-99"
        with self.assertRaisesRegex(CoverageError,"INVALID_SOURCE_RECHECK_DATE"):
            build_report(self.registry,bad,as_of=date(2026,10,12))

    def test_unverified_row_must_not_raise_quality_score(self):
        raw=copy.deepcopy(self.catalog)
        raw["products"].append(copy.deepcopy(raw["products"][0]))
        with self.assertRaisesRegex(CoverageError,"DUPLICATE_OFFICIAL_PRODUCT_ID"):
            build_report(self.registry,raw)

if __name__=="__main__":
    unittest.main(verbosity=2)
