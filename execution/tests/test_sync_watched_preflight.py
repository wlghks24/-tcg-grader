"""Real-Git deterministic checks for immutable watched-change preflight."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sync_watched_preflight as preflight


class WatchedPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.email", "qa@example.invalid")
        self.git("config", "user.name", "QA")
        self.write("grading_accuracy_v99.py", "risk = 100\n")
        self.write("docs/status.md", "old\n")
        def watcher(exact, prefixes):
            return {"freshness_watch": {
                "exact_paths": exact, "path_prefixes": prefixes,
                "exclude_paths": ["integrity_manifest.json"]}}
        self.write(preflight.CONTRACTS[0], json.dumps(watcher(["main"], ["grading_", "tablet_"])))
        self.write(preflight.CONTRACTS[1], json.dumps(
            watcher([".github/workflows/repository-integrity-guard.yml"], [])))
        self.git("add", ".")
        self.git("commit", "-qm", "base")
        self.base = self.git("rev-parse", "HEAD").strip()

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, text=True).strip()

    def write(self, path, content):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, "utf-8")

    def commit(self, path, content):
        self.write(path, content)
        self.git("add", "-A")
        self.git("commit", "-qm", "change")

    def test_negative_grading_candidate_is_held(self):
        self.commit("grading_accuracy_v99.py", "risk = 0\n")
        result = preflight.inspect(self.root, self.base, "HEAD")
        self.assertEqual("HOLD_REVIEW_SUCCESSOR", result["status"])
        self.assertEqual(["grading_accuracy_v99.py"], [x["path"] for x in result["watched_changes"]])
        self.assertEqual("path_prefix", result["watched_changes"][0]["matched_watch"][0]["rule"])
        self.assertEqual("DEVICE_UNVERIFIED", result["device"])

    def test_historical_workflow_edit_is_exactly_watched(self):
        self.commit(".github/workflows/repository-integrity-guard.yml", "changed\n")
        result = preflight.inspect(self.root, self.base, "HEAD")
        self.assertEqual(".github/workflows/repository-integrity-guard.yml",
                         result["watched_changes"][0]["path"])
        self.assertEqual("exact_path", result["watched_changes"][0]["matched_watch"][0]["rule"])

    def test_unwatched_read_only_doc_is_not_certified(self):
        self.commit("docs/status.md", "next\n")
        result = preflight.inspect(self.root, self.base, "HEAD")
        self.assertEqual("NO_WATCHED_DIFF_IN_TWO_CONTRACTS", result["status"])
        self.assertFalse(result["requires_successor_review"])
        self.assertTrue(result["not_a_successor_approval"])

    def test_exclusion_applies_only_to_its_watcher(self):
        self.commit("integrity_manifest.json", "{}\n")
        result = preflight.inspect(self.root, self.base, "HEAD")
        self.assertFalse(result["requires_successor_review"])
        self.assertEqual(1, result["changed_path_count"])

    def test_modified_contract_in_candidate_cannot_hide_protected_baseline(self):
        self.commit(preflight.CONTRACTS[0],
                    json.dumps({"freshness_watch": {"exact_paths": [],
                                                   "path_prefixes": [], "exclude_paths": []}}))
        self.commit("grading_accuracy_v99.py", "risk = 0\n")
        result = preflight.inspect(self.root, self.base, "HEAD")
        self.assertTrue(result["requires_successor_review"])

    def test_non_ancestor_is_fail_closed(self):
        self.commit("grading_accuracy_v99.py", "risk = 0\n")
        with self.assertRaisesRegex(ValueError, "git_preflight_failed"):
            preflight.inspect(self.root, "HEAD", self.base)

    def test_malformed_baseline_contract_fails(self):
        self.write("docs/status.md", "scratch\n")
        self.git("reset", "--hard", self.base)
        self.write(preflight.CONTRACTS[0], '{"freshness_watch":{},"freshness_watch":{}}')
        self.git("add", "-A")
        self.git("commit", "-qm", "new base")
        new_base = self.git("rev-parse", "HEAD")
        with self.assertRaisesRegex(ValueError, "duplicate_contract_key"):
            preflight.inspect(self.root, new_base, "HEAD")

    def test_read_only_git_status(self):
        self.commit("tablet_status.txt", "one\n")
        before = self.git("status", "--porcelain")
        preflight.inspect(self.root, self.base, "HEAD")
        after = self.git("status", "--porcelain")
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
