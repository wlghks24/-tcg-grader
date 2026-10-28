"""Selected W201–W300 historical source proof, without executing old scripts."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_v201_v300_forensics as hist

ROOT = Path(__file__).resolve().parents[2]


class HistoricalV201V300ForensicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = {v: hist.read_blob(ROOT, hist.BASE, e[0], e[1])
                    for v, e in hist.CASES.items()}
        cls.py = hist.read_blob(ROOT, hist.BASE, hist.V291_SOURCE_PATH,
                                hist.V99_MAIN_BLOB)
        cls.js = hist.read_blob(ROOT, hist.BASE, "grading_accuracy_v99.js",
                                hist.V99_JS_MAIN_BLOB)
        cls.original = hist.git(ROOT, "show",
                                hist.V99_ORIGINAL + ":" + hist.V291_SOURCE_PATH)
        cls.repaired = hist.git(ROOT, "show",
                                hist.V291_REPAIR + ":" + hist.V291_SOURCE_PATH)

    def checked(self, data=None, py=None, js=None, original=None, repaired=None):
        return hist.inspect_evidence(
            self.data if data is None else data,
            self.py if py is None else py,
            self.js if js is None else js,
            self.original if original is None else original,
            self.repaired if repaired is None else repaired,
        )

    def test_real_git_pins_and_no_false_full_review(self):
        report = hist.inspect(ROOT)
        self.assertEqual(8, report["inspected_test_sources"])
        self.assertEqual([201, 209, 211, 262, 273, 291, 299, 300],
                         report["inspected_numeric_versions"])
        self.assertEqual(0, report["complete_versions_reviewed"])
        self.assertIsNone(report["quality_score"])
        self.assertEqual("DEVICE_UNVERIFIED", report["device"])
        self.assertEqual("SELECTED_TEST_EVIDENCE_ONLY_REVIEW_INCOMPLETE",
                         report["status"])

    def test_existing_pinned_base_blob_tamper_refused(self):
        with self.assertRaisesRegex(ValueError, "pinned_blob_changed"):
            hist.read_blob(ROOT, hist.BASE, "test_card_core_crosscheck_v291.py",
                           "0"*40)

    def test_all_source_claims_are_only_test_source_not_executed(self):
        report = self.checked()
        self.assertEqual(8, len(report["test_source_rows"]))
        self.assertTrue(all(r["test_run"] == "NOT_EXECUTED_BY_FORENSIC_TOOL"
                            and r["review_score"] is None for r in report["test_source_rows"]))

    def test_v201_standalone_no_untrusted_legacy_execution(self):
        report = self.checked()
        self.assertEqual("standalone", report["test_source_rows"][0]["test_style"])
        self.assertIn("PATCHED_URLLIB_NOT_EXECUTED", report["v201_probe"])

    def test_missing_test_file_rejected(self):
        data = copy.deepcopy(self.data)
        del data[273]
        with self.assertRaisesRegex(ValueError, "incomplete_sampled_slice"):
            self.checked(data=data)

    def test_missing_expected_method_rejected(self):
        data = copy.deepcopy(self.data)
        data[209] = data[209].replace(
            b"def test_event_is_current_through_fifth_day_and_archived_on_sixth",
            b"def obsolete_event_window")
        with self.assertRaisesRegex(ValueError, "expected_historical_test_removed:v209"):
            self.checked(data=data)

    def test_false_v209_five_day_claim_rejected(self):
        data = copy.deepcopy(self.data)
        data[209] = data[209].replace(b'dt.date(2026, 9, 11)',
                                      b'dt.date(2026, 9, 12)')
        with self.assertRaisesRegex(ValueError, "v209_five_day_contract_missing"):
            self.checked(data=data)

    def test_v211_threshold_test_removal_rejected(self):
        data = copy.deepcopy(self.data)
        data[211] = data[211].replace(b"MIN_INDEPENDENT_LABELS",
                                      b"OTHER_TOKEN")
        with self.assertRaisesRegex(ValueError, "v211_label_threshold_tests_missing"):
            self.checked(data=data)

    def test_v273_sha_target_assertions_removal_rejected(self):
        data = copy.deepcopy(self.data)
        data[273] = data[273].replace(b"TCG_TARGET_MAIN_SHA", b"TCG_ANY_SHA")
        with self.assertRaisesRegex(ValueError, "v273_pinned_target_test_missing"):
            self.checked(data=data)

    def test_v291_omitted_channel_regression_removal_rejected(self):
        data = copy.deepcopy(self.data)
        data[291] = data[291].replace(
            b"accuracy.combine_defect_risk(None, 0, 0)",
            b"accuracy.combine_defect_risk(0, 0, 0)")
        with self.assertRaisesRegex(ValueError, "v291_missing_channel_regression_missing"):
            self.checked(data=data)

    def test_v299_registration_removal_rejected(self):
        data = copy.deepcopy(self.data)
        data[299] = data[299].replace(
            b"card_core_node_regressions", b"other_regressions")
        with self.assertRaisesRegex(ValueError, "v299_runtime_registration_guard_missing"):
            self.checked(data=data)

    def test_older_v99_behavior_cannot_be_invented(self):
        fake = self.original.replace(b"if x is not None:values.append(x*weight)",
                                     b"if x is None:return 100")
        with self.assertRaisesRegex(ValueError, "not_original_v99_missing_evidence_behavior"):
            self.checked(original=fake)

    def test_v291_missing_evidence_repair_must_be_preserved(self):
        fake = self.repaired.replace(b"if x is None:return 100",
                                      b"if x is None:continue")
        with self.assertRaisesRegex(ValueError, "v291_fail_closed_successor_not_preserved"):
            self.checked(repaired=fake)

    def test_negative_bounds_gap_is_never_called_a_pass(self):
        report = self.checked()
        self.assertTrue(report["uncovered_negative_defect_bound_by_old_v291_tests"])
        self.assertEqual("NOT_IMPLEMENTED_IN_PROTECTED_BASE",
                         report["current_main_python_js_negative_input_guard"])
        self.assertEqual("PR_903_DRAFT_HOLD_REQUIRES_WATCHED_SUCCESSOR",
                         report["related_candidate"])

    def test_source_code_parsing_rejects_syntax_errors(self):
        data = copy.deepcopy(self.data)
        data[300] = b"def broken(\n"
        with self.assertRaises(SyntaxError):
            self.checked(data=data)

    def test_read_only_git_status_unchanged(self):
        before = subprocess.check_output(["git", "status", "--porcelain"],
                                         cwd=ROOT, text=True)
        hist.inspect(ROOT)
        after = subprocess.check_output(["git", "status", "--porcelain"],
                                        cwd=ROOT, text=True)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
