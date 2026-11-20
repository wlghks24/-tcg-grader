"""Verify V1001's outer history LRU cannot approve changed Git replacement refs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from execution import git_validation_cache as cache
from execution.tests import test_deployment_repairs_successor_v1001 as target


class V1001HistoryReplaceGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tcg-v1001-replace-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.addCleanup(target._history.cache_clear)
        self.addCleanup(cache._cached_object_read.cache_clear)
        self.addCleanup(cache._cached_status_read.cache_clear)
        self.addCleanup(cache._git_admin_layout.cache_clear)
        self.addCleanup(cache._packed_replace_ref_present.cache_clear)
        for clean in (target._history.cache_clear, cache._cached_object_read.cache_clear,
                      cache._cached_status_read.cache_clear, cache._git_admin_layout.cache_clear,
                      cache._packed_replace_ref_present.cache_clear):
            clean()
        self.git("init", "-q")
        self.git("config", "user.name", "TCG V1001 Regression")
        self.git("config", "user.email", "v1001@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        path = self.root / "card.txt"
        path.write_bytes(b"baseline-card\n")
        self.git("add", ".")
        self.git("commit", "-qm", "baseline")
        baseline = self.git("rev-parse", "HEAD").decode().strip()
        original = path.read_bytes()
        path.write_bytes(b"candidate-card\n")
        self.git("commit", "-qam", "candidate")
        candidate = self.git("rev-parse", "HEAD").decode().strip()
        reviewed = path.read_bytes()
        self.head = candidate
        self.baseline = baseline
        self.proof = {
            "baseline_commit": baseline,
            "candidate_commit": candidate,
            "reviewed_files": {
                "card.txt": {
                    "baseline_bytes": len(original),
                    "baseline_sha256": hashlib.sha256(original).hexdigest(),
                    "baseline_git_blob": self.git("rev-parse", baseline + ":card.txt").decode().strip(),
                    "candidate_bytes": len(reviewed),
                    "candidate_sha256": hashlib.sha256(reviewed).hexdigest(),
                    "candidate_git_blob": self.git("rev-parse", candidate + ":card.txt").decode().strip(),
                },
            },
        }
        self.key = json.dumps(self.proof, sort_keys=True)
        self.executors = (subprocess.run, subprocess.check_output)
        fix_root = patch.object(target, "ROOT", self.root)
        fix_root.start()
        self.addCleanup(fix_root.stop)

    def git(self, *args):
        return subprocess.check_output(
            ["git", "-C", str(self.root), *args], timeout=10,
        )

    def checked(self):
        return target._checked_history(self.head, self.key, self.executors)

    def test_normal_repeated_immutable_validation_reuses_cache(self):
        self.assertTrue(self.checked())
        self.assertTrue(self.checked())
        self.assertGreaterEqual(target._history.cache_info().hits, 1)

    def test_warmed_success_does_not_accept_later_loose_replace_ref(self):
        self.assertTrue(self.checked())
        # Replacement changes the result of the same fixed-SHA Git commands.
        self.git("replace", self.baseline, self.head)
        self.assertTrue(cache._mutable_git_history_override_risk(self.root))
        self.assertEqual(b"candidate-card\n",
                         self.git("show", self.baseline + ":card.txt"))
        with self.assertRaises((AssertionError, subprocess.CalledProcessError)):
            self.checked()

    def test_warmed_success_does_not_accept_packed_only_replace_ref(self):
        self.assertTrue(self.checked())
        self.git("replace", self.baseline, self.head)
        self.git("pack-refs", "--all")
        packed = self.root / ".git" / "packed-refs"
        self.assertIn(b"refs/replace/", packed.read_bytes())
        loose = self.root / ".git" / "refs" / "replace"
        self.assertEqual([], list(loose.iterdir()))
        loose.rmdir()
        self.assertTrue(cache._mutable_git_history_override_risk(self.root))
        with self.assertRaises((AssertionError, subprocess.CalledProcessError)):
            self.checked()

    def test_history_bypass_rechecks_under_risk_even_after_warm_success(self):
        self.assertTrue(self.checked())
        # Under a nonstandard Git layout, no remembered approval is accepted.
        # An actual live recheck is forced, rather than a cache hit.
        with patch.object(target, "_mutable_git_history_override_risk", return_value=True):
            before = target._history.cache_info().hits
            self.assertTrue(self.checked())
            self.assertEqual(before, target._history.cache_info().hits)


if __name__ == "__main__":
    unittest.main()
