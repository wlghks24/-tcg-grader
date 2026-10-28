"""W401-V500 selected original test-source scope and false-proof rejection."""
from __future__ import annotations
import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_v401_v500_forensics as hist

ROOT = Path(__file__).resolve().parents[2]


class HistoricalW401Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = {p: hist.original(ROOT, p, b) for p, b in hist.PINNED.items()}
        cls.parent = json.loads(hist.git(ROOT, "show", "HEAD:" + hist.PARENT_LEDGER))
        cls.delta = json.loads(hist.git(ROOT, "show", "HEAD:" + hist.DELTA_PATH))

    def report(self):
        return hist.analyze(self.files, self.parent, self.delta)

    def test_all_13_pinned_original_blobs_exact(self):
        result = hist.inspect(ROOT)
        self.assertEqual(13, result["selected_source_and_test_blob_count"])
        self.assertTrue(result["read_only_pinned_originals"])
        self.assertFalse(result["v426_device_verified"])

    def test_seven_selected_versions_not_all_100(self):
        result = self.report()
        self.assertEqual([413,426,430,437,468,485,489], result["selected_versions"])
        self.assertEqual(7, len(result["rows"]))
        self.assertEqual(0, result["completed_full_version_reviews_in_w401"])
        self.assertIsNone(result["quality_score"])
        self.assertEqual("HOLD_DEVICE_UNVERIFIED", result["deployment"])

    def test_prior_ledger_and_successor_finding_carried_forward(self):
        result = self.report()
        self.assertEqual(17, result["previous_finding_count"])
        self.assertIn("W401-F001", result["previous_finding_ids"])
        self.assertEqual("W401-F001", result["continuing_prior_protection"])
        self.assertEqual(7, len(result["new_gap_finding_ids"]))
        self.assertEqual(24, result["cumulative_finding_count"])
        self.assertEqual(24, len(set(result["cumulative_finding_ids"])))

    def test_w413_is_source_monitor_with_state_write_not_live_proof(self):
        result = self.report()
        x = next(row for row in result["rows"] if row["version"] == 413)
        self.assertIn("MODELLED_SOURCE_FETCH_NOT_LIVE", x["evidence_scope"])
        self.assertFalse(x["complete_version_review"])
        self.assertIn(b"atomic_write_json(", self.files["promoted_tcg_source_monitor_v413.py"])

    def test_v426_prefix_and_receipt_no_real_device_claim(self):
        result = self.report()
        row = next(v for v in result["rows"] if v["version"] == 426)
        self.assertEqual("SYNC_CONTRACT_NOT_DEVICE_RECEIPT", row["evidence_scope"])
        self.assertFalse(result["v426_device_verified"])

    def test_v430_test_only_textual_visibility(self):
        result = self.report()
        row = next(v for v in result["rows"] if v["version"] == 430)
        self.assertIn("SOURCE_STRING_ASSERTIONS", row["evidence_scope"])
        self.assertGreater(row["test_functions_found"], 2)

    def test_v437_synthetic_url_not_live_official_validation(self):
        row = next(v for v in self.report()["rows"] if v["version"] == 437)
        self.assertIn("SYNTHETIC_URLS", row["evidence_scope"])
        self.assertIn(b"https://official.example/game", self.files["test_tcg_discovery_inbox_v437.py"])

    def test_v468_only_source_route_not_termux_receipt(self):
        row = next(v for v in self.report()["rows"] if v["version"] == 468)
        self.assertEqual("LOCAL_ENTRYPOINT_STRINGS_NOT_TERMUX_RUN", row["evidence_scope"])
        self.assertIn("NOT_PERFORMED", row["exact_head_runtime_execution"])

    def test_v485_node_syntax_not_visual_browser(self):
        row = next(v for v in self.report()["rows"] if v["version"] == 485)
        self.assertIn("NOT_RENDERED_SCREENSHOT", row["evidence_scope"])

    def test_v489_16_case_identity_harness_not_real_purchase(self):
        row = next(v for v in self.report()["rows"] if v["version"] == 489)
        self.assertIn("NOT_PURCHASE_OR_AVAILABILITY", row["evidence_scope"])
        self.assertIn(b"sixteen exact card and edition identity cases",
                      self.files["test_grade_context_purchase_v489.py"])

    def test_tamper_original_anchor_rejected(self):
        with self.assertRaisesRegex(ValueError, "original_git_blob_mismatch"):
            hist.original(ROOT, "test_tablet_category_focus_v430.py", "0"*40)
        with self.assertRaisesRegex(ValueError, "bad_expected_git_blob"):
            hist.original(ROOT, "test_tablet_category_focus_v430.py", "bad")

    def test_missing_test_assertion_rejected(self):
        data = dict(self.files)
        target = "test_tcg_discovery_inbox_v437.py"
        data[target] = data[target].replace(b"https://official.example/game", b"http://not-real.test")
        with self.assertRaisesRegex(ValueError, "missing_v437_synthetic_origin"):
            hist.analyze(data, self.parent, self.delta)

    def test_candidate_false_device_receipt_rejected(self):
        data = dict(self.files)
        target = "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v426.json"
        rec = json.loads(data[target])
        rec["verification"]["physical_tablet_runtime_verified"] = True
        data[target] = json.dumps(rec).encode()
        with self.assertRaisesRegex(ValueError, "unsupported_v426_device_proof"):
            hist.analyze(data, self.parent, self.delta)

    def test_broken_w426_successor_rule_rejected(self):
        data = dict(self.files)
        target = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V426.json"
        contract = json.loads(data[target])
        contract["freshness_watch"]["path_prefixes"].remove("grading_")
        data[target] = json.dumps(contract).encode()
        with self.assertRaisesRegex(ValueError, "missing_v426_protected_grading_prefix"):
            hist.analyze(data, self.parent, self.delta)

    def test_missing_parent_finding_is_rejected(self):
        ledger = copy.deepcopy(self.parent)
        ledger["findings"] = [x for x in ledger["findings"] if x["id"] != "W401-F001"]
        with self.assertRaisesRegex(ValueError, "missing_prior_w401_protection_finding"):
            hist.analyze(self.files, ledger, self.delta)

    def test_false_quality_score_in_delta_is_rejected(self):
        delta = copy.deepcopy(self.delta)
        delta["grading_quality_score"] = 100
        with self.assertRaisesRegex(ValueError, "w401_delta_false_scope_or_proof"):
            hist.analyze(self.files, self.parent, delta)

    def test_duplicate_finding_delta_is_rejected(self):
        delta = copy.deepcopy(self.delta)
        delta["findings"][1]["id"] = delta["findings"][0]["id"]
        with self.assertRaisesRegex(ValueError, "w401_duplicate_or_missing_finding_id"):
            hist.analyze(self.files, self.parent, delta)

    def test_finding_may_not_claim_runtime_bug_or_deployment(self):
        delta = copy.deepcopy(self.delta)
        delta["findings"][0]["patch_eligible"] = True
        with self.assertRaisesRegex(ValueError, "w401_false_finding_or_release_claim"):
            hist.analyze(self.files, self.parent, delta)

    def test_parent_finding_digest_is_not_silent_overwrite(self):
        delta = copy.deepcopy(self.delta)
        delta["parent_ledger_blob"] = "0"*40
        with self.assertRaisesRegex(ValueError, "w401_delta_false_scope_or_proof"):
            hist.analyze(self.files, self.parent, delta)

    def test_inspector_does_not_write_worktree(self):
        before = subprocess.check_output(["git","status","--porcelain"],cwd=ROOT)
        hist.inspect(ROOT)
        after = subprocess.check_output(["git","status","--porcelain"],cwd=ROOT)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
