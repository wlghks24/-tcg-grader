"""Live V1018 proof gate survives warm, bounded immutable Git object reuse."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from execution import git_validation_cache as cache
from execution import workspace_review_successor_v1018 as workspace


class V1018ImmutableGitReadthroughTests(unittest.TestCase):
    def setUp(self):
        cache._cached_object_read.cache_clear()
        cache._cached_status_read.cache_clear()
        self.temp = tempfile.TemporaryDirectory(prefix="tcg-v1018-git-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, timeout=10)

        def git(*args):
            return subprocess.check_output(
                ["git", "-C", str(self.root), *args], timeout=10,
            ).decode().strip()

        git("config", "user.name", "TCG V1018 Regression")
        git("config", "user.email", "v1018@example.invalid")
        git("config", "commit.gpgsign", "false")
        self.target = self.root / "cards" / "card.txt"
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(b"prior-card\n")
        for path in (
            "main",
            ".github/tablet-autonomy/workspace_restore_v1017.json",
            ".github/tablet-autonomy/deployment_repairs_successor_v1001.json",
        ):
            dest = self.root / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"pinned-history\n")
        git("add", ".")
        git("commit", "-q", "-m", "v1018 baseline")
        before = git("rev-parse", "HEAD")
        self.target.write_bytes(b"reviewed-card\n")
        git("add", ".")
        git("commit", "-q", "-m", "v1018 candidate")
        after = git("rev-parse", "HEAD")
        self.expected = {
            "schema": "tcg-workspace-review/v1018",
            "baseline_commit": before,
            "candidate_commit": after,
            "files": {
                "cards/card.txt": {
                    "before_sha256": hashlib.sha256(b"prior-card\n").hexdigest(),
                    "sha256": hashlib.sha256(b"reviewed-card\n").hexdigest(),
                    "bytes": len(b"reviewed-card\n"),
                }
            },
            "physical_tablet_verified": False,
            "runtime_data_modified": False,
        }
        self.proof = self.root / ".github/tablet-autonomy/workspace_review_v1018.json"
        self.proof.write_text(json.dumps(self.expected), encoding="utf-8")
        root_patch = patch.object(workspace, "ROOT", self.root)
        expected_patch = patch.object(workspace, "EXPECTED", self.expected)
        root_patch.start()
        expected_patch.start()
        self.addCleanup(root_patch.stop)
        self.addCleanup(expected_patch.stop)
        self.addCleanup(cache._cached_object_read.cache_clear)
        self.addCleanup(cache._cached_status_read.cache_clear)

    def test_fixed_history_is_reused_while_head_is_checked_each_time(self):
        original = subprocess.check_output
        with patch.object(subprocess, "check_output", wraps=original) as executor:
            self.assertTrue(workspace.validate_workspace_review_v1018("cards/card.txt"))
            self.assertTrue(workspace.validate_workspace_review_v1018("cards/card.txt"))
        calls = [list(item.args[0]) for item in executor.call_args_list]
        base, candidate = self.expected["baseline_commit"], self.expected["candidate_commit"]
        self.assertEqual(1, calls.count(["git", "show", base + ":cards/card.txt"]))
        self.assertEqual(1, calls.count(["git", "show", candidate + ":cards/card.txt"]))
        self.assertEqual(1, calls.count(["git", "diff", "--name-only", base + ".." + candidate]))
        self.assertEqual(2, calls.count(["git", "show", "HEAD:cards/card.txt"]))
        self.assertEqual(2, calls.count(["git", "merge-base", "--is-ancestor", candidate, "HEAD"]))

    def test_changed_proof_rejected_after_warming_git_history(self):
        self.assertTrue(workspace.validate_workspace_review_v1018("cards/card.txt"))
        changed = {**self.expected, "physical_tablet_verified": True}
        self.proof.write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaises(AssertionError):
            workspace.validate_workspace_review_v1018("cards/card.txt")

    def test_changed_live_bytes_rejected_after_warming_git_history(self):
        self.assertTrue(workspace.validate_workspace_review_v1018("cards/card.txt"))
        self.target.write_bytes(b"tampered-card\n")
        with self.assertRaises(AssertionError):
            workspace.validate_workspace_review_v1018("cards/card.txt")

    def test_changed_head_commit_rejected_after_warming_git_history(self):
        self.assertTrue(workspace.validate_workspace_review_v1018("cards/card.txt"))
        self.target.write_bytes(b"newer-unreviewed-card\n")
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True, timeout=10)
        subprocess.run(["git", "-C", str(self.root), "commit", "-q", "-m", "unreviewed"],
                       check=True, timeout=10)
        with self.assertRaises(AssertionError):
            workspace.validate_workspace_review_v1018("cards/card.txt")


if __name__ == "__main__":
    unittest.main()
