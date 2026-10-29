#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import unittest

import grading_self_learning as gsl


class SelfLearningTests(unittest.TestCase):
    def test_unverified_sample_rejected(self):
        with self.assertRaises(ValueError):
            gsl.sanitize_sample({"company": "PSA", "actual": 9, "pred": 10})

    def test_strict_verified_rejects_false_strings_and_numeric_flags(self):
        row = {"company": "PSA", "actual": 9, "pred": 9}
        for value in ("false", "False", "0", "true", 1, 0, None, [], {}):
            with self.subTest(verified=value):
                with self.assertRaisesRegex(ValueError, "only verified"):
                    gsl.sanitize_sample({**row, "verified": value})

    def test_explicit_untrusted_verified_cannot_use_legacy_bypass(self):
        row = {"company": "PSA", "actual": 9, "pred": 9}
        for value in ("false", False, 1, None):
            with self.subTest(verified=value):
                with self.assertRaisesRegex(ValueError, "only verified"):
                    gsl.sanitize_sample({**row, "verified": value}, legacy_verified=True)

    def test_explicit_true_and_absent_legacy_keep_compatibility(self):
        row = {"company": "PSA", "actual": 9, "pred": 9}
        self.assertTrue(gsl.sanitize_sample({**row, "verified": True})["verified"])
        self.assertTrue(gsl.sanitize_sample(row, legacy_verified=True)["verified"])
        with self.assertRaisesRegex(ValueError, "only verified"):
            gsl.sanitize_sample(row)

    def test_append_confirmed_sample_requires_literal_true(self):
        row = {"company": "PSA", "actual": 9, "pred": 9}
        original = gsl.empty_store()
        for flag in ("false", "0", "true", False, 1, 0, None, [], {}):
            with self.subTest(verified=flag):
                with self.assertRaisesRegex(ValueError, "only verified"):
                    gsl.append_confirmed_sample(original, {**row, "verified": flag})
                self.assertEqual(original["confirmed_samples"], [])
        with self.assertRaisesRegex(ValueError, "only verified"):
            gsl.append_confirmed_sample(original, row)
        accepted = gsl.append_confirmed_sample(original, {**row, "verified": True})
        self.assertEqual(len(accepted["confirmed_samples"]), 1)
        self.assertTrue(accepted["confirmed_samples"][0]["verified"])
        self.assertEqual(original["confirmed_samples"], [])

    def test_all_companies_supported(self):
        for company in gsl.COMPANIES:
            sample = gsl.sanitize_sample(
                {"company": company, "actual": 9, "pred": 9, "verified": True}
            )
            self.assertEqual(sample["company"], company)

    def test_boolean_numeric_fields_cannot_be_training_values(self):
        base = {"company": "PSA", "actual": 9, "pred": 9, "verified": True}
        for field in ("actual", "pred"):
            for flag in (True, False):
                with self.subTest(field=field, value=flag):
                    with self.assertRaisesRegex(ValueError, "actual/raw prediction"):
                        gsl.sanitize_sample({**base, field: flag})
        bgs = gsl.sanitize_sample({
            "company": "BGS", "actual": 9, "pred": 9, "verified": True,
            "subgrades": {"centering": True, "corners": 9, "edges": 9, "surface": 9},
            "features": {"confidence": True, "photo_quality": 0.9},
        })
        self.assertNotIn("centering", bgs.get("subgrades", {}))
        self.assertNotIn("confidence", bgs.get("features", {}))

    def test_calibration_direct_input_cannot_upgrade_unverified_rows(self):
        raw = {"company": "PSA", "actual": 9, "pred": 10, "card_key": "a"}
        for bad in ({}, {"verified": "false"}, {"verified": 1}, {"verified": None},
                    {"verified": False}):
            with self.subTest(flag=bad):
                rows = [{**raw, "card_key": f"card-{i}", **bad} for i in range(10)]
                self.assertEqual(gsl.build_calibration(rows)["PSA"]["n"], 0)
        approved = [{**raw, "card_key": f"card-{i}", "verified": True} for i in range(10)]
        self.assertEqual(gsl.build_calibration(approved)["PSA"]["n"], 10)
        historical = gsl.sanitize_legacy_rows(
            [{**raw, "card_key": f"old-{i}"} for i in range(10)]
        )
        self.assertEqual(gsl.build_calibration(historical)["PSA"]["n"], 10)

    def test_bgs_summary_requires_upstream_verified_or_legacy_normalization(self):
        raw = {
            "company": "BGS", "actual": 10, "pred": 10,
            "subgrades": {"centering": 10, "corners": 10,
                          "edges": 10, "surface": 10},
        }
        self.assertEqual(gsl.bgs_empirical_summary([raw])["n"], 0)
        self.assertEqual(
            gsl.bgs_empirical_summary([{**raw, "verified": "false"}])["n"], 0
        )
        self.assertEqual(
            gsl.bgs_empirical_summary([{**raw, "verified": True}])["n"], 1
        )
        normalized = gsl.sanitize_legacy_rows([raw])
        self.assertEqual(gsl.bgs_empirical_summary(normalized)["n"], 1)

    def test_no_correction_under_five_samples(self):
        store = gsl.empty_store()
        for i in range(4):
            store = gsl.append_confirmed_sample(
                store,
                {"company": "BGS", "actual": 9, "pred": 10, "verified": True,
                 "card_key": f"bgs-{i}"}
            )
        self.assertEqual(store["calibration"]["BGS"]["state"], "observe")
        self.assertEqual(store["calibration"]["BGS"]["correction"], 0)

    def test_overgrading_is_corrected_downward(self):
        store = gsl.empty_store()
        for i in range(10):
            store = gsl.append_confirmed_sample(
                store,
                {"company": "PSA", "actual": 9, "pred": 10, "verified": True,
                 "card_key": f"psa-{i}"}
            )
        model = store["calibration"]["PSA"]
        self.assertLess(model["correction"], 0)
        result = gsl.calibrate_prediction(store, "PSA", 10)
        self.assertEqual(result["grade"], 9)

    def test_company_models_do_not_leak(self):
        store = gsl.empty_store()
        for i in range(10):
            store = gsl.append_confirmed_sample(
                store,
                {"company": "TAG", "actual": 8, "pred": 9, "verified": True,
                 "card_key": f"tag-{i}"}
            )
        self.assertLess(store["calibration"]["TAG"]["correction"], 0)
        self.assertEqual(store["calibration"]["PSA"]["correction"], 0)

    def test_same_card_samples_are_tracked(self):
        store = gsl.empty_store()
        for i in range(3):
            store = gsl.append_confirmed_sample(
                store,
                {"company": "BRG", "actual": 10, "pred": 9.5, "verified": True,
                 "card_key": "umbreon-ex-217", "cert_no": f"cert-{i}"}
            )
        self.assertEqual(store["calibration"]["BRG"]["same_card_groups"], 1)

    def test_cert_number_deduplicates(self):
        store = gsl.empty_store()
        sample = {
            "company": "BGS", "actual": 9.5, "pred": 10, "verified": True,
            "cert_no": "0012345"
        }
        store = gsl.append_confirmed_sample(store, sample)
        store = gsl.append_confirmed_sample(store, {**sample, "note": "duplicate"})
        self.assertEqual(len(store["confirmed_samples"]), 1)

    def test_bgs_subgrade_summary_is_empirical_only(self):
        store = gsl.empty_store()
        samples = [
            {
                "company": "BGS", "actual": 10, "pred": 10, "verified": True,
                "cert_no": "a", "subgrades": {
                    "centering": 10, "corners": 10, "edges": 10, "surface": 10
                },
            },
            {
                "company": "BGS", "actual": 10, "pred": 9.5, "verified": True,
                "cert_no": "b", "subgrades": {
                    "centering": 9.5, "corners": 10, "edges": 10, "surface": 10
                },
            },
            {
                "company": "BGS", "actual": 8, "pred": 8.5, "verified": True,
                "cert_no": "c", "subgrades": {
                    "centering": 9.5, "corners": 9.5, "edges": 7, "surface": 9.5
                },
            },
        ]
        for sample in samples:
            store = gsl.append_confirmed_sample(store, sample)
        summary = store["bgs_subgrade_summary"]
        self.assertEqual(summary["n"], 3)
        self.assertEqual(summary["all_10_final_10_cases"], 1)
        self.assertEqual(summary["three_10_one_9_5_final_10_cases"], 1)
        self.assertIn("경험 통계", summary["note"])

    def test_legacy_rows_are_preserved_and_deduplicated(self):
        row = {"time": "2026-01-01", "company": "CGC", "actual": 9.5, "pred": 10}
        store = gsl.rebuild_store({"v30_validation": [row], "v11_validation": [row]})
        self.assertEqual(store["calibration"]["CGC"]["n"], 1)
        self.assertEqual(len(store["v30_validation"]), 1)
        self.assertEqual(len(store["v11_validation"]), 1)


if __name__ == "__main__":
    unittest.main()
