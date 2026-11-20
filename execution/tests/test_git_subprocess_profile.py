"""Behavior, safety and redaction tests for Git process-family diagnostics."""
from __future__ import annotations

from collections import Counter
import shutil
import subprocess
import sys
import unittest

from execution.diagnostics.git_subprocess_profile import (
    command_family, count_subprocess_families, main,
)


class GitSubprocessProfileTests(unittest.TestCase):
    def test_family_does_not_print_secret_arguments(self):
        sha = "a" * 40
        cases = [
            (["git", "show", sha + ":secret/token"], "git.show.fixed"),
            (["git", "show", "HEAD:secret/token"], "git.show.other"),
            (["git", "-C", "/secret", "diff", "--name-only"], "git.diff"),
            (["git", "merge-base", "--is-ancestor", sha, sha], "git.merge-base"),
            (["git", "config", "--list"], "git.config"),
            ([sys.executable, "-c", "print('token')"], "non-git"),
            (["git", object()], "other"),
        ]
        for command, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(expected, command_family(command))
                self.assertNotIn("secret", command_family(command))
                self.assertNotIn("token", command_family(command))

    def test_popen_wrapper_preserves_stdio_and_exit_code(self):
        with count_subprocess_families() as counts:
            result = subprocess.run([sys.executable, "-c", "print('OK')"],
                                    capture_output=True, text=True, check=True, timeout=10)
        self.assertEqual("OK\n", result.stdout)
        self.assertEqual(0, result.returncode)
        self.assertEqual(1, counts["non-git"])

    @unittest.skipUnless(shutil.which("git"), "git unavailable")
    def test_original_git_execution_preserved(self):
        with count_subprocess_families() as counts:
            result = subprocess.run(["git", "--version"], check=True,
                                    capture_output=True, text=True, timeout=10)
        self.assertIn("git version", result.stdout)
        self.assertEqual(1, counts["git.other"])

    @unittest.skipUnless(shutil.which("git"), "git unavailable")
    def test_callsite_attribution_uses_safe_module_function_only(self):
        sites = Counter()
        with count_subprocess_families(site_counts=sites) as counts:
            result = subprocess.run(["git", "--version"], check=True,
                                    capture_output=True, text=True, timeout=10)
        self.assertIn("git version", result.stdout)
        self.assertEqual(1, counts["git.other"])
        self.assertEqual(1, sum(sites.values()))
        ((family, site), amount), = sites.items()
        self.assertEqual("git.other", family)
        self.assertEqual(1, amount)
        self.assertEqual(
            "execution.tests.test_git_subprocess_profile:"
            "test_callsite_attribution_uses_safe_module_function_only",
            site,
        )
        self.assertNotIn("/", site)
        self.assertNotIn("\\\\", site)

    def test_non_git_command_keeps_origin_histogram_empty(self):
        sites = Counter()
        with count_subprocess_families(site_counts=sites) as counts:
            result = subprocess.run(
                [sys.executable, "-c", "print('PRIVATE_PATH_OR_TOKEN')"],
                check=True, capture_output=True, text=True, timeout=10,
            )
        self.assertEqual("PRIVATE_PATH_OR_TOKEN\\n", result.stdout)
        self.assertEqual(1, counts["non-git"])
        self.assertEqual({}, dict(sites))

    def test_only_allowlisted_case_accepted(self):
        with self.assertRaises(SystemExit) as failure:
            main(["--case", "v999"])
        self.assertEqual(2, failure.exception.code)


if __name__ == "__main__":
    unittest.main()
