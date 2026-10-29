#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import unittest

import grading_self_learning as gsl


class SelfLearningTests(unittest.TestCase):
    def test_unverified_sample_rejected(self):
        with self.assertRaises(ValueError):
            gsl.sanitize_sample({"company": "PSA", "actual": 9, "pred": 10})

    def test_p0_verified_requires_literal_boolean_true(self):
        values = (False, None, 0, 1, "false", "true", "", [], {}, 2.0)
        for value in values:
            with self.subTest(verified=repr(value)):
                row = {"company": "PSA", "actual": 9, "pred": 10,
                       "verified": value}
                with self.assertRaises(ValueError):
                    gsl.sanitize_sample(row)
        accepted = gsl.sanitize_sample(
            {"company": "PSA", "actual": 9, "pred": 10, "verified": True})
        self.assertIs(accepted["verified"], True)

    def test_p0_explicit_false_never_overridden_by_legacy_flag(self):
        row = {"company": "PSA", "actual": 9, "pred": 10}
        # Existing legacy validation arrays may be trusted by explicit importer.
        self.assertIs(gsl.sanitize_sample(row, legacy_verified=True)["verified"], True)
        for value in (False, "false", 1, None):
            with self.subTest(verified=repr(value)):
                with self.assertRaises(ValueError):
                    gsl.sanitize_sample({**row, "verified": value},
                                        legacy_verified=True)

    def test_p0_append_cannot_force_invalid_or_missing_verification(self):
        row = {"company": "CGC", "actual": 9, "pred": 9}
        initial = gsl.empty_store()
        for value in (None, False, "false", "true", 1):
            with self.subTest(value=repr(value)):
                candidate = dict(row)
                if value is not None:
                    candidate["verified"] = value
                with self.assertRaises(ValueError):
                    gsl.append_confirmed_sample(initial, candidate)
                self.assertEqual([], initial["confirmed_samples"])
        saved = gsl.append_confirmed_sample(initial, {**row, "verified": True})
        self.assertEqual(1, len(saved["confirmed_samples"]))
        self.assertIs(saved["confirmed_samples"][0]["verified"], True)

    def test_p0_direct_calibration_does_not_trust_missing_verified_flag(self):
        row = {"company": "BGS", "actual": 9, "pred": 10, "card_key": "bgs-p0"}
        unverified = [dict(row), {**row, "verified": "false"},
                      {**row, "verified": 1}, {**row, "verified": False}]
        self.assertEqual(0, gsl.build_calibration(unverified)["BGS"]["n"])
        verified = gsl.build_calibration([{**row, "verified": True}])
        self.assertEqual(1, verified["BGS"]["n"])

    def test_p0_rebuild_filters_nonboolean_confirmations_and_preserves_legacy(self):
        row = {"company": "PSA", "actual": 9, "pred": 10}
        source = {"v30_validation": [dict(row), {**row, "verified": "false"}],
                  "confirmed_samples": [{**row, "verified": "false"},
                                        {**row, "verified": 1},
                                        {**row, "verified": True}]}
        result = gsl.rebuild_store(source)
        self.assertEqual(1, len(result["v30_validation"]))
        self.assertEqual(1, len(result["confirmed_samples"]))
        self.assertEqual(1, result["calibration"]["PSA"]["n"])
        self.assertTrue(all(x["verified"] is True for x in result["confirmed_samples"]))

    def test_all_companies_supported(self):
        for company in gsl.COMPANIES:
            sample = gsl.sanitize_sample(
                {"company": company, "actual": 9, "pred": 9, "verified": True}
            )
            self.assertEqual(sample["company"], company)

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
