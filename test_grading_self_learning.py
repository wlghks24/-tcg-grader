#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import unittest

import grading_self_learning as gsl


class SelfLearningTests(unittest.TestCase):
    def test_unverified_sample_rejected(self):
        with self.assertRaises(ValueError):
            gsl.sanitize_sample({"company": "PSA", "actual": 9, "pred": 10})

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
