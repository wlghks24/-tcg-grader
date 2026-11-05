"""Offline regressions for V928 shard timing triage; never run git or CI jobs."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from execution import tablet_sync_performance_v928 as timing


def fixture(*, elapsed="443.719", count=191, cancelled=False, failed=False):
    event = [
        "2026-11-05T14:00:00.0000000Z test_first (sync.test_fixture) ... ok",
        "2026-11-05T14:01:03.0000000Z test_legacy_v377 (sync.test_fixture) ... ok",
        "2026-11-05T14:02:02.0000000Z test_legacy_v381 (sync.test_fixture) ... ok",
    ]
    event.append(f"2026-11-05T14:05:32.1975144Z Ran {count} tests in {elapsed}s")
    event.append("2026-11-05T14:05:32.1975278Z FAILED (failures=1)" if failed
                 else "2026-11-05T14:05:32.1975278Z OK")
    if cancelled:
        event.append("2026-11-05T14:05:33.0000000Z ##[error]The operation was canceled.")
    return "\n".join(event) + "\n"


class SyncTimingV928Tests(unittest.TestCase):
    def test_verified_run_exposes_gaps_not_imaginary_profiler_durations(self):
        report = timing.analyze(fixture(), job_conclusion="success")
        self.assertTrue(report["workflow_success_verified"])
        self.assertEqual("PASSED", report["python_suite"])
        self.assertEqual(191, report["reported_test_count"])
        self.assertEqual(3, report["observed_completed_tests"])
        self.assertEqual([63.0, 59.0],
                         [g["completion_gap_seconds"] for g in report["longest_completion_gaps"]])
        self.assertEqual(122.0, report["top_four_gap_seconds"])
        self.assertEqual(156.281, report["headroom_seconds"])
        self.assertFalse(report["near_timeout"])
        self.assertIn("inter-test overhead", report["limitations"])

    def test_python_ok_does_not_override_cancelled_github_job(self):
        report = timing.analyze(fixture(elapsed="599.494", cancelled=True),
                                job_conclusion="cancelled")
        self.assertEqual("PASSED", report["python_suite"])
        self.assertFalse(report["workflow_success_verified"])
        self.assertTrue(report["runner_cancelled"])
        self.assertTrue(report["near_timeout"])
        self.assertEqual(0.506, report["headroom_seconds"])

    def test_unknown_job_conclusion_cannot_certify_green(self):
        report = timing.analyze(fixture())
        self.assertEqual("PASSED", report["python_suite"])
        self.assertFalse(report["workflow_success_verified"])

    def test_mid_suite_cancellation_never_claims_full_success(self):
        partial = fixture().split("2026-11-05T14:05:32")[0]
        partial += "2026-11-05T14:02:03.0000000Z ##[error]The operation was canceled.\n"
        report = timing.analyze(partial, job_conclusion="cancelled")
        self.assertEqual("INCOMPLETE", report["python_suite"])
        self.assertIsNone(report["reported_suite_seconds"])
        self.assertFalse(report["workflow_success_verified"])

    def test_error_and_count_mismatch_are_not_silent_pass(self):
        error = fixture(failed=True)
        self.assertEqual("FAILED", timing.analyze(error, job_conclusion="failure")["python_suite"])
        self.assertEqual("INCOMPLETE",
                         timing.analyze(fixture(count=190), job_conclusion="success")["python_suite"])
        self.assertFalse(timing.analyze(fixture(count=190),
                                        job_conclusion="success")["workflow_success_verified"])

    def test_near_timeout_and_budget_parameters_are_bounded(self):
        report = timing.analyze(fixture(elapsed="548.25"), job_conclusion="success")
        self.assertTrue(report["near_timeout"])
        self.assertEqual(51.75, report["headroom_seconds"])
        for kw in ({"expected_tests": True}, {"warning_seconds": 600},
                   {"budget_seconds": 0}, {"job_conclusion": "not-verified"}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                timing.analyze(fixture(), **kw)

    def test_monotone_timestamps_and_size_limit_fail_closed(self):
        reversed_events = "\n".join([
            "2026-11-05T14:00:05.0000000Z test_one (fixture) ... ok",
            "2026-11-05T14:00:03.0000000Z test_two (fixture) ... ok",
        ])
        with self.assertRaisesRegex(ValueError, "out of order"):
            timing.analyze(reversed_events)
        with self.assertRaisesRegex(ValueError, "size limit"):
            timing.analyze("x" * (timing.MAX_LOG_BYTES + 1))

    def test_comparison_keeps_cancelled_and_complete_independent(self):
        ok = timing.analyze(fixture(elapsed="443.719"), job_conclusion="success")
        slow = timing.analyze(fixture(elapsed="599.494", cancelled=True),
                              job_conclusion="cancelled")
        result = timing.compare([ok, slow])
        self.assertEqual(2, result["measured_suites"])
        self.assertEqual(155.775, result["spread_seconds"])
        self.assertEqual(1, result["verified_successes"])
        self.assertEqual(1, result["cancelled_jobs"])
        with self.assertRaises(ValueError):
            timing.compare([])

    def test_read_only_cli_and_no_symlink_following(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            job = root / "job.log"
            job.write_text(fixture(), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()) as capture:
                code = timing.main([str(job), "--conclusion", "success"])
            self.assertEqual(0, code)
            report = json.loads(capture.getvalue())
            self.assertTrue(report["runs"][0]["workflow_success_verified"])
            self.assertEqual(fixture(), job.read_text(encoding="utf-8"))
            link = root / "alias.log"
            link.symlink_to(job)
            with self.assertRaisesRegex(ValueError, "symlink"):
                timing.read_log(link)


if __name__ == "__main__":
    unittest.main()
