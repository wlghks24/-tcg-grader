"""Fail-closed CLI regressions for the read-only alignment profiler."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import subprocess
import sys
import unittest
from unittest.mock import patch

from execution.diagnostics import profile_main_alignment as profiler


class AlignmentProfileCliTests(unittest.TestCase):
    def call(self, *args, side_effect=None):
        argv = ["profile_main_alignment.py", "--shard", "2",
                "--only-version", "369", *args]
        out, err = StringIO(), StringIO()
        with patch.object(sys, "argv", argv), patch.object(
                profiler.subprocess, "run",
                return_value=subprocess.CompletedProcess([], 0),
                side_effect=side_effect) as run, redirect_stdout(out), redirect_stderr(err):
            try:
                code = profiler.main()
            except SystemExit as exc:
                code = exc.code
        return code, run, out.getvalue(), err.getvalue()

    def test_method_selection_runs_exact_method_not_entire_module(self):
        method = ("test_tablet_gpt_tcg_grader_sync_v369."
                  "TabletGptTcgGraderSyncV369.test_lineage_digest_receipt_and_merge_anchor")
        code, run, output, _ = self.call("--only-test", method)
        self.assertEqual(0, code)
        run.assert_called_once()
        self.assertEqual(["-m", "unittest", "-v", method], run.call_args.args[0][-4:])
        self.assertIn("ALIGNMENT_PROFILE_START", output)
        self.assertIn("failures=0 timeouts=0", output)

    def test_cross_version_method_is_rejected_before_execution(self):
        code, run, _, error = self.call(
            "--only-test", "test_tablet_gpt_tcg_grader_sync_v370.Other.test_escape")
        self.assertEqual(2, code)
        run.assert_not_called()
        self.assertIn("--only-test must name a method", error)

    def test_bad_method_shape_is_rejected_before_execution(self):
        code, run, _, error = self.call("--only-test", "test_tablet_gpt_tcg_grader_sync_v369")
        self.assertEqual(2, code)
        run.assert_not_called()
        self.assertIn("--only-test must name a method", error)

    def test_timeout_is_reported_and_blocks_success(self):
        method = ("test_tablet_gpt_tcg_grader_sync_v369."
                  "TabletGptTcgGraderSyncV369.test_exact_candidate_scope_and_complete_generation")
        code, run, output, _ = self.call(
            "--only-test", method,
            side_effect=subprocess.TimeoutExpired(cmd=["python"], timeout=600))
        self.assertEqual(1, code)
        run.assert_called_once()
        self.assertIn("exit=124", output)
        self.assertIn("failures=1 timeouts=1", output)


if __name__ == "__main__":
    unittest.main()
