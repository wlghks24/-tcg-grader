"""Regression for Git-config-aware immutable diffs in the common validation cache."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from execution import git_validation_cache as cache
from execution.diagnostics import immutable_diff_cache as context_cache

SOURCE = "a" * 40
CANDIDATE = "b" * 40
PAIR = ["git", "diff", "--name-only", SOURCE + ".." + CANDIDATE]


class CommonImmutableGitDiffCacheTests(unittest.TestCase):
    def setUp(self):
        cache._cached_object_read.cache_clear()

    def tearDown(self):
        cache._cached_object_read.cache_clear()

    def test_exact_pair_reuses_only_same_git_config(self):
        with patch.object(context_cache, "_git_config_digest", return_value=b"same") as digest:
            with patch.object(subprocess, "check_output", return_value="card.txt\n") as output:
                self.assertEqual("card.txt\n", cache.git_validation_output(PAIR))
                self.assertEqual("card.txt\n", cache.git_validation_output(PAIR))
        self.assertEqual(2, digest.call_count)
        output.assert_called_once()

    def test_config_change_invalidates_even_identical_pair(self):
        with patch.object(context_cache, "_git_config_digest", side_effect=[b"first", b"second"]):
            with patch.object(subprocess, "check_output",
                              side_effect=["new.txt\n", "new.txt\nold.txt\n"]) as output:
                self.assertEqual("new.txt\n", cache.git_validation_output(PAIR))
                self.assertEqual("new.txt\nold.txt\n", cache.git_validation_output(PAIR))
        self.assertEqual(2, output.call_count)

    def test_unavailable_config_bypasses_cache_without_hiding_failure(self):
        with patch.object(context_cache, "_git_config_digest", return_value=None):
            with patch.object(subprocess, "check_output",
                              side_effect=["first\n", "second\n"]) as output:
                self.assertEqual("first\n", cache.git_validation_output(PAIR))
                self.assertEqual("second\n", cache.git_validation_output(PAIR))
        self.assertEqual(2, output.call_count)

    def test_moving_refs_and_ambiguous_syntax_are_uncached(self):
        invalid = [
            ["git", "diff", "--name-only", SOURCE + "..HEAD"],
            ["git", "diff", "--name-only", SOURCE, CANDIDATE],
            ["git", "diff", "--name-only", 123],
            ["git", "diff", "--name-only", "main..main"],
            ["git", "diff", "--name-only", SOURCE + ".." + CANDIDATE, "--"],
            ["git", "diff", "--name-only", SOURCE + "..HEAD", "--", "file.txt"],
            ["git", "diff", "--name-only", SOURCE + ".." + CANDIDATE, "--", ""],
            ["git", "diff", "--name-only", SOURCE, CANDIDATE, "--", ""],
        ]
        for cmd in invalid:
            with self.subTest(cmd=cmd):
                with patch.object(context_cache, "_git_config_digest") as digest:
                    with patch.object(subprocess, "check_output",
                                      side_effect=["one\n", "two\n"]) as output:
                        self.assertEqual("one\n", cache.git_validation_output(cmd))
                        self.assertEqual("two\n", cache.git_validation_output(cmd))
                digest.assert_not_called()
                self.assertEqual(2, output.call_count)

    def test_scoped_sha_pair_and_two_explicit_shas_reuse_cached_diff(self):
        pairs = [
            ["git", "diff", "--name-only", SOURCE + ".." + CANDIDATE,
             "--", "cards/file.txt"],
            ["git", "diff", "--name-only", SOURCE, CANDIDATE,
             "--", "cards/file.txt"],
        ]
        for command in pairs:
            with self.subTest(command=command):
                with patch.object(context_cache, "_git_config_digest",
                                  return_value=b"fixed") as digest:
                    with patch.object(subprocess, "check_output",
                                      return_value="cards/file.txt\n") as output:
                        self.assertEqual("cards/file.txt\n",
                                         cache.git_validation_output(command))
                        self.assertEqual("cards/file.txt\n",
                                         cache.git_validation_output(command))
                self.assertEqual(2, digest.call_count)
                output.assert_called_once()

    def test_scoped_comparison_rechecks_changed_config(self):
        command = ["git", "diff", "--name-only",
                   SOURCE + ".." + CANDIDATE, "--", "cards"]
        with patch.object(context_cache, "_git_config_digest",
                          side_effect=[b"renames-on", b"renames-off"]):
            with patch.object(subprocess, "check_output",
                              side_effect=["cards/a.txt\n", "cards/a.txt\ncards/b.txt\n"]) as output:
                self.assertEqual("cards/a.txt\n", cache.git_validation_output(command))
                self.assertEqual("cards/a.txt\ncards/b.txt\n",
                                 cache.git_validation_output(command))
        self.assertEqual(2, output.call_count)

    def test_different_git_executor_cannot_reuse_success(self):
        with patch.object(context_cache, "_git_config_digest", return_value=b"same"):
            with patch.object(subprocess, "check_output", return_value="one\n") as first:
                self.assertEqual("one\n", cache.git_validation_output(PAIR))
            with patch.object(subprocess, "check_output", return_value="two\n") as second:
                self.assertEqual("two\n", cache.git_validation_output(PAIR))
        first.assert_called_once()
        second.assert_called_once()

    def test_pathspec_magic_never_enters_immutable_cache(self):
        pathspecs = [
            ':(attr:reviewed)',
            ':(icase)CARDS',
            ':(glob)cards/**/*.txt',
            ':!cards',
            ':(exclude)cards',
        ]
        for pattern in pathspecs:
            with self.subTest(pathspec=pattern):
                command = ["git", "diff", "--name-only",
                           SOURCE + ".." + CANDIDATE, "--", pattern]
                with patch.object(context_cache, "_git_config_digest") as digest:
                    with patch.object(subprocess, "check_output",
                                      side_effect=["one.txt\n", "two.txt\n"]) as output:
                        self.assertEqual("one.txt\n",
                                         cache.git_validation_output(command))
                        self.assertEqual("two.txt\n",
                                         cache.git_validation_output(command))
                digest.assert_not_called()
                self.assertEqual(2, output.call_count)

    @unittest.skipUnless(shutil.which("git"), "Git executable unavailable")
    def test_real_mutable_git_attributes_do_not_poison_sha_cache(self):
        with tempfile.TemporaryDirectory(prefix="tcg-git-attr-scope-") as temp:
            root = Path(temp)
            subprocess.run(["git", "init", "-q", str(root)], check=True, timeout=10)

            def git(*arguments):
                return subprocess.check_output(
                    ["git", "-C", str(root), *arguments], text=True, timeout=10,
                ).strip()

            git("config", "user.name", "TCG Attribute Regression")
            git("config", "user.email", "tcg@example.invalid")
            git("config", "commit.gpgsign", "false")
            (root / "a.txt").write_text("a\n", encoding="utf-8")
            (root / "b.txt").write_text("b\n", encoding="utf-8")
            git("add", ".")
            git("commit", "-m", "before")
            before = git("rev-parse", "HEAD")
            (root / "a.txt").write_text("a2\n", encoding="utf-8")
            (root / "b.txt").write_text("b2\n", encoding="utf-8")
            git("add", ".")
            git("commit", "-m", "after")
            after = git("rev-parse", "HEAD")

            # The commits and .git/config remain unchanged; *only* the
            # uncommitted worktree attribute file changes between the calls.
            command = ["git", "diff", "--name-only", before + ".." + after,
                       "--", ":(attr:reviewed)"]
            (root / ".gitattributes").write_text("a.txt reviewed\n", encoding="utf-8")
            first = cache.git_validation_output(command, cwd=root, text=True, timeout=10)
            (root / ".gitattributes").write_text("b.txt reviewed\n", encoding="utf-8")
            second = cache.git_validation_output(command, cwd=root, text=True, timeout=10)
            self.assertEqual(["a.txt"], first.splitlines())
            self.assertEqual(["b.txt"], second.splitlines())

    def test_original_explicit_no_rename_cache_remains_unchanged(self):
        command = ["git", "diff", "--no-renames", "--name-only",
                   SOURCE + ".." + CANDIDATE, "--", "cards"]
        with patch.object(context_cache, "_git_config_digest") as digest:
            with patch.object(subprocess, "check_output", return_value="cards\n") as output:
                self.assertEqual("cards\n", cache.git_validation_output(command))
                self.assertEqual("cards\n", cache.git_validation_output(command))
        digest.assert_not_called()
        output.assert_called_once()

    def test_live_worktree_command_remains_uncached(self):
        command = ["git", "hash-object", "--", "local-card.json"]
        with patch.object(context_cache, "_git_config_digest") as digest:
            with patch.object(subprocess, "check_output",
                              side_effect=["old\n", "changed\n"]) as output:
                self.assertEqual("old\n", cache.git_validation_output(command))
                self.assertEqual("changed\n", cache.git_validation_output(command))
        digest.assert_not_called()
        self.assertEqual(2, output.call_count)

    @unittest.skipUnless(shutil.which("git"), "Git executable unavailable")
    def test_real_git_rename_config_affects_cached_diff(self):
        with tempfile.TemporaryDirectory(prefix="tcg-git-diff-cache-") as temp:
            root = Path(temp)
            subprocess.run(["git", "init", "-q", str(root)], check=True, timeout=10)

            def git(*arguments):
                return subprocess.check_output(
                    ["git", "-C", str(root), *arguments], text=True, timeout=10,
                ).strip()

            git("config", "user.name", "TCG Diff Regression")
            git("config", "user.email", "tcg@example.invalid")
            git("config", "commit.gpgsign", "false")
            (root / "before.txt").write_text("verified\n" * 50, encoding="utf-8")
            git("add", "before.txt")
            git("commit", "-m", "before")
            before = git("rev-parse", "HEAD")
            git("mv", "before.txt", "after.txt")
            git("commit", "-m", "after")
            after = git("rev-parse", "HEAD")

            command = ["git", "diff", "--name-only", before + ".." + after]
            git("config", "--local", "diff.renames", "true")
            renamed = cache.git_validation_output(command, cwd=root, text=True, timeout=10)
            git("config", "--local", "diff.renames", "false")
            changed = cache.git_validation_output(command, cwd=root, text=True, timeout=10)
            self.assertEqual(["after.txt"], renamed.splitlines())
            self.assertEqual(["after.txt", "before.txt"], changed.splitlines())


if __name__ == "__main__":
    unittest.main()
