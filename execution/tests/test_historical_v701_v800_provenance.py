"""Original Git-body/ref token provenance tests; not V7xx release verification."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_v701_v800_provenance as audit


class W701ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.email", "qa@example.invalid")
        self.git("config", "user.name", "QA")
        (self.root / "README.md").write_text("original\n", "utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "Original source")
        self.base = self.git("rev-parse", "HEAD").strip()

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, text=True).strip()

    def commit(self, subject, body):
        (self.root / "README.md").write_text(subject + body, "utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", subject, "-m", body)

    def test_full_body_token_detected_but_not_certified(self):
        self.commit("No version label in subject", "Historical note V750 about a candidate")
        o = audit.scan(self.root, self.base)
        self.assertEqual(1, len(o["commit_body_token_hints"]))
        self.assertEqual([750], o["commit_body_token_hints"][0]["version_tokens"])
        self.assertFalse(o["every_version_reviewed"])
        self.assertIsNone(o["quality_score"])

    def test_remote_or_tag_ref_names_are_only_hints(self):
        self.git("tag", "archive-v780")
        self.git("branch", "-r")  # no remote references required for tag test
        o = audit.scan(self.root, self.base)
        self.assertEqual(1, o["ref_name_token_hits"])
        self.assertEqual([780], o["tag_and_remote_ref_token_hints"][0]["version_tokens"])
        self.assertEqual("REF_NAME_TOKEN_NOT_RELEASE_PROOF",
                         o["tag_and_remote_ref_token_hints"][0]["classification"])

    def test_empty_v7xx_results_do_not_approve_absence(self):
        o = audit.scan(self.root, self.base)
        self.assertEqual(0, o["commit_body_token_hits"])
        self.assertEqual(0, o["ref_name_token_hits"])
        self.assertFalse(o["absence_of_tokens_proves_no_release"])
        self.assertFalse(o["tablet_device_verified"])

    def test_dates_and_embedded_not_fake_versions(self):
        self.commit("v20261018 maintenance", "embedded Av750Z is not a standalone marker")
        o = audit.scan(self.root, self.base)
        self.assertEqual(0, o["commit_body_token_hits"])

    def test_lower_and_upper_boundaries(self):
        self.assertEqual([], audit.tokens("V700 V801 v20261028"))
        self.assertEqual([701, 750, 799, 800], audit.tokens("v701 V750 v799 V800"))
        self.assertEqual([], audit.tokens("myV701suffix"))

    def test_current_head_must_descend_from_pinned_base(self):
        self.commit("new", "V777")
        with self.assertRaisesRegex(ValueError, "git_provenance_unavailable"):
            audit.scan(self.root, self.git("rev-parse", "HEAD"))

    def test_bad_pinned_sha_refused(self):
        with self.assertRaisesRegex(ValueError, "invalid_historical_base"):
            audit.scan(self.root, "main")
        with self.assertRaisesRegex(ValueError, "git_provenance_unavailable"):
            audit.scan(self.root, "0" * 40)

    def test_budget_limit_fails_closed(self):
        self.commit("new", "candidate")
        with patch.object(audit, "MAX_COMMITS", 1):
            with self.assertRaisesRegex(ValueError, "commit_scan_budget"):
                audit.scan(self.root, self.base)

    def test_incomplete_git_log_is_not_accepted(self):
        original = audit.git
        def truncated(root, *args, **kwargs):
            if args and args[0] == "log":
                return b""
            return original(root, *args, **kwargs)
        with patch.object(audit, "git", side_effect=truncated):
            with self.assertRaisesRegex(ValueError, "incomplete_commit_body_scan"):
                audit.scan(self.root, self.base)

    def test_read_only_does_not_modify_original_worktree(self):
        self.commit("Other work", "V745 draft")
        before = self.git("status", "--porcelain")
        one = audit.scan(self.root, self.base)
        two = audit.scan(self.root, self.base)
        self.assertEqual(before, self.git("status", "--porcelain"))
        self.assertEqual(one, two)


if __name__ == "__main__":
    unittest.main()
