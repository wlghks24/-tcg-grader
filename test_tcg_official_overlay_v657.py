#!/usr/bin/env python3
"""V657: additive proof, manufacturer-only identity and no older data loss."""
import copy
from datetime import date
import unittest

from execution.official_box_coverage_audit_v623 import CoverageError, ROOT, _load_json
from tcg_official_overlay_v657 import build, validate_overlay, OVERLAY_NAME


class V657FreeBoxProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = _load_json(ROOT / OVERLAY_NAME)
        cls.reg = _load_json(ROOT / "tcg_game_registry.json")

    def test_expected_three_new_us_box_scopes_are_audited(self):
        result = build(as_of=date(2026, 10, 12))
        old, updated = result["before"], result["with_overlay"]
        self.assertEqual((91, 54, 26, 29), (
            old["product_samples"], old["box_samples"],
            old["regions_with_box_sample"], old["regions_without_box_sample"]))
        self.assertEqual((94, 57, 29, 26), (
            updated["product_samples"], updated["box_samples"],
            updated["regions_with_box_sample"], updated["regions_without_box_sample"]))
        self.assertEqual(55, updated["declared_region_pairs"])
        self.assertEqual(3, result["additional_scopes_with_box"])
        self.assertEqual(0, result["network_calls"])
        self.assertEqual(0, result["paid_dependencies"])
        self.assertFalse(result["main_ui_updated"])
        self.assertEqual(
            {("Disney Lorcana", "US"), ("Digimon Card Game", "US"),
             ("Star Wars: Unlimited", "US")},
            {(row["game"], row["country"]) for row in result["sources"]})

    def test_manufacturer_box_units_and_no_fake_pricing(self):
        products = validate_overlay(self.doc, self.reg)
        self.assertEqual(3, len(products))
        self.assertTrue(all(p["product_type"] == "BOX"
                            and p["packs_per_box"] == 24 for p in products))
        by_game = {p["game"]: p for p in products}
        self.assertEqual("12", by_game["Disney Lorcana"]["cards_per_pack"])
        self.assertEqual("12", by_game["Digimon Card Game"]["cards_per_pack"])
        self.assertEqual("16", by_game["Star Wars: Unlimited"]["cards_per_pack"])
        self.assertEqual("2026-07-03", by_game["Digimon Card Game"]["release_date"])
        self.assertTrue(all("msrp" not in p for p in products))
        self.assertTrue(all(not any(k in p for k in (
            "market_price", "verified_sales", "verified_stock", "pull_rate")) for p in products))

    def test_forged_domain_and_broken_overlay_chain_hold(self):
        hacked = copy.deepcopy(self.doc)
        hacked["products"][0]["source"] = "https://www.disneylorcana.com.attacker.example/fake"
        with self.assertRaisesRegex(CoverageError, "UNTRUSTED_V657_BOX_OR_LOCALE"):
            build(overlay=hacked)
        hacked = copy.deepcopy(self.doc)
        hacked["products"][2]["release_date_source"] = "https://starwarsunlimited.com.attacker.invalid"
        with self.assertRaisesRegex(CoverageError, "UNTRUSTED_V657_RELEASE_DATE_SOURCE"):
            build(overlay=hacked)
        hacked = copy.deepcopy(self.doc)
        hacked["append_after"] = "tcg_official_product_supplement_v999.json"
        with self.assertRaisesRegex(CoverageError, "INVALID_V657_SUPPLEMENT_CHAIN"):
            build(overlay=hacked)

    def test_invalid_policy_and_identity_are_rejected(self):
        hacked = copy.deepcopy(self.doc)
        hacked["policy"] = None
        with self.assertRaisesRegex(CoverageError, "PAID_DEPENDENCY_NOT_PERMITTED"):
            build(overlay=hacked)
        hacked = copy.deepcopy(self.doc)
        hacked["products"][0]["cards_per_pack"] = "99"
        with self.assertRaisesRegex(CoverageError, "UNTRUSTED_V657_IDENTITY"):
            build(overlay=hacked)

    def test_invalid_box_size_or_unverified_price_is_rejected(self):
        hacked = copy.deepcopy(self.doc)
        hacked["products"][0]["packs_per_box"] = 0
        with self.assertRaisesRegex(CoverageError, "BOX_PACK_COUNT_REQUIRED"):
            build(overlay=hacked)
        hacked = copy.deepcopy(self.doc)
        hacked["products"][0]["market_price"] = 999
        with self.assertRaisesRegex(CoverageError, "UNSUPPORTED_V657_PRODUCT_CLAIM"):
            build(overlay=hacked)
        hacked = copy.deepcopy(self.doc)
        hacked["products"].append(copy.deepcopy(hacked["products"][0]))
        with self.assertRaisesRegex(CoverageError, "UNTRUSTED_V657_IDENTITY"):
            build(overlay=hacked)


if __name__ == "__main__":
    unittest.main(verbosity=2)
