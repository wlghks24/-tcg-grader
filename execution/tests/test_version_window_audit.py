"""Isolated real-Git regression tests for the read-only version-window inventory."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import version_window_audit as audit


class WindowAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.run_git("init", "-q")
        self.run_git("config", "user.name", "Tester")
        self.run_git("config", "user.email", "tester@example.invalid")
        self.put("README_v31.md", "old information")
        self.put("v100_reference/V100_FINAL_VERIFICATION_REPORT.json", '{"ok":true}')
        self.put("verify_v99_accuracy.py", "assert True")
        self.put("instagram_tcg_content/test_v8.py", "assert True")
        self.put("TCG_CROSSCHECK/IG_CARDINFO/history_v8.json", '{"project":"instagram_card"}')
        self.put("TCG_CROSSCHECK/TCG_GRADER/AI_RELIABILITY_V8_BINDING.json",
                 '{"project":"tcg_grader"}')
        self.put("tcg_reliability/ai_reliability_v8/bridge.py", "assert True")
        self.put("ai_reliability_v8/workflow.py", "assert True")
        self.put("test_v20261018.py", "assert True")
        self.run_git("add", ".")
        self.run_git("commit", "-qm", "V75 redirect, V100 legacy report")
        self.head = self.run_git("rev-parse", "HEAD").strip()

    def run_git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, text=True)

    def put(self, path, content):
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    def test_filename_is_not_verified_release(self):
        result = audit.inventory(self.root, 1)
        self.assertEqual(result["status"], "INVENTORY_ONLY_NOT_RELEASE_VERIFIED")
        self.assertEqual(result["candidate_version_tokens"], [8, 31, 75, 99, 100])
        self.assertEqual(result["excluded_cross_project_paths"], 2)
        self.assertTrue(all(p["classification"] == "filename_hint_only"
                            for p in result["path_hints"]))
        self.assertIsNone(result["score"])
        self.assertEqual(result["device"], "DEVICE_UNVERIFIED")
        self.assertEqual(result["source"]["head"], self.head)

    def test_tcg_reliability_stays_in_scope(self):
        payload = audit.inventory(self.root, 1)
        paths = {row["path"] for row in payload["path_hints"]}
        self.assertIn("tcg_reliability/ai_reliability_v8/bridge.py", paths)
        self.assertIn("TCG_CROSSCHECK/TCG_GRADER/AI_RELIABILITY_V8_BINDING.json", paths)
        self.assertIn("ai_reliability_v8/workflow.py", paths)
        self.assertNotIn("instagram_tcg_content/test_v8.py", paths)
        self.assertNotIn("TCG_CROSSCHECK/IG_CARDINFO/history_v8.json", paths)

    def test_false_numeric_and_embedded_tokens(self):
        self.assertEqual(audit.versions("v20261018 V1000 v99 v099 v0 alphaV5", 1, 100),
                         [99])
        self.assertEqual(audit.versions("pr #100 and V100, V101", 1, 100), [100])

    def test_carry_forward_contiguous_and_replay_digest(self):
        prior = audit.inventory(self.root, 1)
        prior["carry_forward"] = [{"id": "W001-F001", "status": "OPEN"}]
        prior["checkpoint_sha256"] = audit.canonical_sha256(prior)
        next_window = audit.inventory(self.root, 101, prior)
        self.assertEqual(next_window["previous_checkpoint_sha256"], prior["checkpoint_sha256"])
        self.assertEqual(next_window["carry_forward"], prior["carry_forward"])
        self.assertEqual(next_window["checkpoint_sha256"], audit.canonical_sha256(next_window))
        with self.assertRaisesRegex(ValueError, "non_contiguous_windows"):
            audit.inventory(self.root, 301, prior)

    def test_tamper_and_head_drift_hold(self):
        prior = audit.inventory(self.root, 1)
        prior["path_hints"].append({"path": "fake_v99.py", "tokens": [99]})
        with self.assertRaisesRegex(ValueError, "tampered_previous_checkpoint"):
            audit.inventory(self.root, 101, prior)
        prior = audit.inventory(self.root, 1)
        self.put("new.txt", "changed")
        self.run_git("add", ".")
        self.run_git("commit", "-qm", "V101 new state")
        with self.assertRaisesRegex(ValueError, "source_head_changed"):
            audit.inventory(self.root, 101, prior)

    def test_previous_checkpoint_duplicate_json_and_symlink(self):
        prior = audit.inventory(self.root, 1)
        path = self.root / "prior.json"
        path.write_text(json.dumps(prior), encoding="utf-8")
        self.assertEqual(audit.read_previous(path, first=101, head=self.head), prior)
        path.write_text('{"schema":"x","schema":"y"}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate_previous_key"):
            audit.read_previous(path, first=101, head=self.head)
        path.unlink()
        path.symlink_to(self.root / "README_v31.md")
        with self.assertRaisesRegex(ValueError, "unsafe_previous_checkpoint"):
            audit.read_previous(path, first=101, head=self.head)

    def test_malformed_checkpoint_shapes_fail_closed(self):
        prior = audit.inventory(self.root, 1)
        prior["window"] = None
        prior["checkpoint_sha256"] = audit.canonical_sha256(prior)
        with self.assertRaisesRegex(ValueError, "non_contiguous_windows"):
            audit.inventory(self.root, 101, prior)
        prior = audit.inventory(self.root, 1)
        prior["source"] = None
        prior["checkpoint_sha256"] = audit.canonical_sha256(prior)
        with self.assertRaisesRegex(ValueError, "source_head_changed"):
            audit.inventory(self.root, 101, prior)

    def test_zero_evidence_window_is_not_a_passed_release_batch(self):
        window = audit.inventory(self.root, 701)
        self.assertEqual([], window["candidate_version_tokens"])
        truth = window["coverage_truth"]
        self.assertEqual(100, len(truth["unrepresented_number_hints"]))
        self.assertEqual(list(range(701, 801)), truth["unrepresented_number_hints"])
        self.assertEqual("AUDIT_NOT_DONE_NOT_A_RELEASE_PASS", truth["classification"])
        self.assertFalse(truth["version_by_version_source_review_performed"])
        self.assertFalse(truth["version_by_version_regressions_executed"])
        self.assertIsNone(truth["version_quality_score"])
        self.assertIsNone(window["score"])

    def test_nonempty_filename_hints_still_not_quality_scored(self):
        window = audit.inventory(self.root, 1)
        truth = window["coverage_truth"]
        self.assertGreater(truth["matched_version_token_hints"], 0)
        self.assertEqual(100, truth["version_slots"])
        self.assertEqual(
            100,
            truth["matched_version_token_hints"] + len(truth["unrepresented_number_hints"]),
        )
        self.assertEqual("AUDIT_NOT_DONE_NOT_A_RELEASE_PASS", truth["classification"])
        self.assertIsNone(truth["version_quality_score"])

    def test_bad_windows_and_budget(self):
        for start in (0, 2, 100, 9902):
            with self.subTest(start=start), self.assertRaises(ValueError):
                audit.inventory(self.root, start)
        with self.assertRaisesRegex(ValueError, "invalid_commit_budget"):
            audit.inventory(self.root, 1, max_commits=0)

    def test_read_only_inventory(self):
        before = self.run_git("status", "--porcelain")
        result = audit.inventory(self.root, 1)
        after = self.run_git("status", "--porcelain")
        self.assertEqual(before, after)
        self.assertFalse(result["source"]["is_shallow"])


if __name__ == "__main__":
    unittest.main()
