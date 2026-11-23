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

    def test_verification_requires_literal_true_for_confirmed_rows(self):
        for flag in ("false", "true", "0", 1, 0, None, [], {}):
            with self.subTest(flag=flag):
                row = {"company": "PSA", "actual": 9, "pred": 8, "verified": flag}
                with self.assertRaises(ValueError):
                    gsl.sanitize_sample(row)
                store = gsl.rebuild_store({"confirmed_samples": [row]})
                self.assertEqual(store["confirmed_samples"], [])
                self.assertEqual(store["calibration"]["PSA"]["n"], 0)

    def test_legacy_missing_verification_is_compatible_but_explicit_false_is_not(self):
        row = {"company": "CGC", "actual": 9.5, "pred": 10}
        self.assertEqual(len(gsl.sanitize_legacy_rows([row])), 1)
        for flag in (False, "false", 1):
            with self.subTest(flag=flag):
                self.assertEqual(gsl.sanitize_legacy_rows([{**row, "verified": flag}]), [])

    def test_boolean_grade_fields_cannot_become_one_or_fall_back(self):
        for field in ("actual", "actual_grade", "raw_pred", "predicted_raw", "pred", "predicted_grade"):
            for flag in (True, False):
                with self.subTest(field=field, flag=flag):
                    row = {"company": "PSA", "actual": 9, "pred": 8, "verified": True}
                    row[field] = flag
                    with self.assertRaises(ValueError):
                        gsl.sanitize_sample(row)

    def test_oversized_and_nonfinite_grade_rows_do_not_abort_store_rebuild(self):
        good = {"id": "good", "company": "PSA", "actual": 9, "pred": 8, "verified": True,
                "time": "2026-11-01T00:00:00+00:00", "game": "pokemon", "card_key": "fixture-good"}
        for field in ("actual", "raw_pred", "pred"):
            for value in (10 ** 400, float("inf"), float("nan")):
                with self.subTest(field=field, kind=type(value).__name__):
                    bad = {**good, "id": "bad", field: value}
                    with self.assertRaises(ValueError):
                        gsl.sanitize_sample(bad)
                    store = gsl.rebuild_store({"confirmed_samples": [bad, good]})
                    self.assertEqual(len(store["confirmed_samples"]), 1)
                    self.assertEqual(store["confirmed_samples"][0]["id"], "good")
                    self.assertEqual(store["calibration"]["PSA"]["n"], 1)

    def test_existing_numeric_text_grades_still_work(self):
        row = gsl.sanitize_sample({"company": "BGS", "actual": "9.5", "pred": "10", "verified": True})
        self.assertEqual(row["actual"], 9.5)
        self.assertEqual(row["raw_pred"], 10.0)

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


def load_tests(loader, tests, pattern):
    # Existing root entrypoint owns these extra focused regressions; no new
    # GitHub root entry or historical test removal is needed.
    tests.addTests(loader.loadTestsFromName("execution.tests.test_video_review_repairs_20261122"))
    tests.addTests(loader.loadTestsFromName("execution.tests.test_menu_resize_successor_20261122"))
    tests.addTests(loader.loadTestsFromName("execution.tests.test_grading_input_cost_successor_20261122"))
    tests.addTests(loader.loadTestsFromName("execution.tests.test_tablet_event_labels_20261122"))
    tests.addTests(loader.loadTestsFromName("execution.tests.test_event_ui_successor_20261122"))
    tests.addTests(loader.loadTestsFromName("execution.tests.test_tablet_event_filters_20261122"))
    tests.addTests(loader.loadTestsFromName("execution.tests.test_event_filter_successor_20261122"))
    tests.addTests(loader.loadTestsFromName("execution.tests.test_successor_git_reads_20261122"))
    tests.addTests(loader.loadTestsFromName("execution.tests.test_tablet_workspace_truth_20261123"))
    tests.addTests(loader.loadTestsFromName("execution.tests.test_workspace_followup_successor_20261123"))
    tests.addTests(loader.loadTestsFromName("execution.tests.test_sale_evidence_20261123"))
    tests.addTests(loader.loadTestsFromName("execution.tests.test_video_market_successor_20261123"))
    tests.addTests(loader.loadTestsFromName("execution.tests.test_official_cinema_news_20261123"))
    tests.addTests(loader.loadTestsFromName("execution.tests.test_event_collection_pipeline_20261123"))
    tests.addTests(loader.loadTestsFromName("execution.tests.test_tablet_event_refresh_20261123"))
    tests.addTests(loader.loadTestsFromName("execution.tests.test_event_retention_20261123"))
    tests.addTests(loader.loadTestsFromName("execution.tests.test_events_collection_successor_20261123"))
    tests.addTests(loader.loadTestsFromName("execution.tests.test_tablet_sync_successor_v1003"))
    tests.addTests(loader.loadTestsFromName("execution.tests.test_event_retention_reentry_20261123"))
    return tests
