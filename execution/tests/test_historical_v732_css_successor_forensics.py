"""V732 original Git data cleanup integrity proof (not a deployed release)."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_v732_css_successor_forensics as audit

ROOT = Path(__file__).resolve().parents[2]


class V732ForensicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proof = audit.review(ROOT)

    def test_original_landing_commit_sha_is_pinned(self):
        self.assertEqual(audit.LANDING, self.proof["original_landing_sha"])
        self.assertEqual(audit.MAIN, self.proof["protected_main_sha"])

    def test_exact_nine_css_title_contaminants_removed(self):
        self.assertEqual(9, self.proof["css_title_rows_removed"])

    def test_other_original_event_rows_are_semantically_preserved(self):
        self.assertGreater(self.proof["other_event_rows_semantically_preserved"], 0)

    def test_only_three_original_changed_paths(self):
        self.assertEqual(["integrity_manifest.json", "social_event_candidates.json",
                          "sync_v376_successor_test_support.py"],
                         self.proof["original_change_paths"])

    def test_current_source_keeps_pinned_v732_successor_gate(self):
        text=audit.git_blob(ROOT,audit.MAIN,audit.PROTECT,
                            audit.PROTECT_MAIN_BLOB).decode("utf-8")
        self.assertIn(audit.LANDING,text)
        self.assertIn(audit.AFTER_BLOB,text)
        self.assertIn("V732: accept only the exact CSS-title cleanup",text)

    def test_no_rewrite_means_no_false_release_accuracy_claim(self):
        self.assertTrue(self.proof["historical_code_and_data_inspected"])
        self.assertFalse(self.proof["all_100_versions_reviewed"])
        self.assertFalse(self.proof["release_version_certified"])
        self.assertFalse(self.proof["current_head_live_event_collector_tested"])
        self.assertIsNone(self.proof["quality_score"])
        self.assertFalse(self.proof["device_verified"])

    def test_forged_baseline_blob_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"original_source_blob_mismatch"):
            audit.git_blob(ROOT,audit.BASE,audit.PATH,"0"*40)

    def test_forged_landing_blob_is_rejected(self):
        with patch.object(audit,"AFTER_BLOB","0"*40):
            with self.assertRaisesRegex(ValueError,"original_source_blob_mismatch"):
                audit.review(ROOT)

    def test_bad_duplicate_nonfinite_event_evidence_rejected(self):
        for sample,reason in [
            (b'{"items":[],"items":[]}',"duplicate_json_key"),
            (b'{"items":[],"x":NaN}',"nonfinite_source_evidence"),
            (b'{"items":{}}',"invalid_event_inventory"),
        ]:
            with self.subTest(sample=sample),self.assertRaisesRegex(ValueError,reason):
                audit.load(sample)

    def test_read_only_source_and_worktree(self):
        before=subprocess.check_output(["git","status","--porcelain"],cwd=ROOT)
        assert audit.review(ROOT)==self.proof
        self.assertEqual(before,subprocess.check_output(["git","status","--porcelain"],cwd=ROOT))


if __name__=="__main__":
    unittest.main()
