"""Only immutable full-commit object lookup may reuse a rev-parse result.

The tests make a disposable local Git repository and never touch card data,
the user's checkout, any network source, or a physical Lenovo tablet.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from execution import git_validation_cache as cache


class FixedShaRevParseCacheTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="tcg-revparse-proof-")
        self.addCleanup(folder.cleanup)
        self.repo = Path(folder.name)
        cache._cached_object_read.cache_clear()
        self.addCleanup(cache._cached_object_read.cache_clear)
        self.git("init", "-q")
        self.git("config", "user.email", "ci@example.invalid")
        self.git("config", "user.name", "CI")
        (self.repo / "card.txt").write_text("first", encoding="utf-8")
        self.git("add", "card.txt")
        self.git("commit", "-qm", "first")
        self.first = self.git("rev-parse", "HEAD").decode().strip()

    def git(self, *args):
        return subprocess.check_output(
            ["git", *args], cwd=self.repo, stderr=subprocess.DEVNULL
        )

    def cached(self, ref):
        return cache.git_validation_output(
            ["git", "rev-parse", ref], cwd=self.repo, timeout=30
        )

    def next_commit(self):
        (self.repo / "card.txt").write_text("second", encoding="utf-8")
        self.git("add", "card.txt")
        self.git("commit", "-qm", "second")
        return self.git("rev-parse", "HEAD").decode().strip()

    def test_repeated_exact_sha_path_lookup_uses_bounded_cache(self):
        ref = self.first + ":card.txt"
        expected = self.git("rev-parse", ref)
        self.assertEqual(expected, self.cached(ref))
        before = cache._cached_object_read.cache_info().hits
        self.assertEqual(expected, self.cached(ref))
        if not cache._mutable_git_history_override_risk(self.repo):
            self.assertGreater(cache._cached_object_read.cache_info().hits, before)

    def test_moving_head_path_is_always_live(self):
        before = self.cached("HEAD:card.txt")
        self.next_commit()
        after = self.cached("HEAD:card.txt")
        self.assertNotEqual(before, after)
        self.assertEqual(self.git("rev-parse", "HEAD:card.txt"), after)

    def test_replacement_ref_bypasses_warmed_cache(self):
        ref = self.first + ":card.txt"
        original = self.cached(ref)
        self.assertEqual(original, self.cached(ref))
        second = self.next_commit()
        self.git("replace", self.first, second)
        self.addCleanup(lambda: self.git("replace", "-d", self.first))
        altered = self.cached(ref)
        self.assertNotEqual(original, altered)
        self.assertEqual(self.git("rev-parse", ref), altered)

    def test_missing_path_and_flagged_lookup_are_not_approved(self):
        bad = self.first + ":missing-card.txt"
        for _ in range(2):
            with self.assertRaises(subprocess.CalledProcessError):
                self.cached(bad)
        self.assertIsNone(cache._immutable_command(
            ["git", "rev-parse", "--verify", self.first + ":card.txt"],
            str(self.repo), subprocess.run, allow_head=False,
        ))


if __name__ == "__main__":
    unittest.main()
