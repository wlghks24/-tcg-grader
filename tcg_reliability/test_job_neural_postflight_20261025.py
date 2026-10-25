"""Offline Job input guards; fixture labels never touch device learning files."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from verified_collection_job_neural import _eligible_result, ingest_verified_report, JOB_KEYS


class JobNeuralPostflightTests(unittest.TestCase):
    def test_missing_postflight_cannot_ingest(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "labels.json"
            report = {"results": [{"file": "anything.json", "ok": True}]}
            result = ingest_verified_report(report, {}, labels_path=path)
            self.assertEqual(result["added"], 0)
            self.assertEqual(result["reason"], "postflight_not_verified")
            self.assertFalse(path.exists())

    def test_preflight_blocked_and_disabled_attempts_rejected(self):
        key = next(iter(JOB_KEYS))
        self.assertFalse(_eligible_result(key, {"ok": True, "preflight_blocked": True}))
        self.assertFalse(_eligible_result(key, {"ok": True, "max_attempts": 0}))
        self.assertFalse(_eligible_result(key, {"ok": True, "status": "cooldown"}))

    def test_unknown_job_rejected(self):
        self.assertFalse(_eligible_result("__not_a_real_job__", {"ok": True}))

    def test_outcome_flag_must_be_an_actual_boolean_for_every_job(self):
        for key in JOB_KEYS:
            for payload in ({}, {"ok": None}, {"ok": "false"}, {"ok": "true"},
                            {"ok": 0}, {"ok": 1}, {"ok": []}, {"ok": {}}):
                with self.subTest(job=key, payload=payload):
                    self.assertFalse(_eligible_result(key, payload))

    def test_existing_valid_output_cannot_admit_missing_or_unfinished_results(self):
        invalid = [
            {"file": "releases.json"},
            {"file": "releases.json", "ok": "false", "max_attempts": 2},
            {"file": "releases.json", "ok": True, "status": "running"},
            {"file": "releases.json", "ok": False, "status": "queued: retry"},
            {"file": "releases.json", "ok": True, "completed": False},
            {"file": "releases.json", "ok": True, "finished": False},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            labels = Path(tmp) / "labels.json"
            report = {"postflight_monitor": {"results": [{"file": "releases.json", "ok": True}]},
                      "results": invalid,
                      "integration": {"ok": True, "status": "in_progress"},
                      "link_audit": {"ok": False, "status": "not_run"}}
            result = ingest_verified_report(report, {"jobs": {}}, labels_path=labels)
            self.assertEqual(0, result["eligible"])
            self.assertEqual(0, result["added"])
            self.assertEqual([], json.loads(labels.read_text())["labels"])

    def test_known_nonterminal_statuses_are_not_outcomes(self):
        for status in ("pending", "queued", "RUNNING", "running: fetch", "in_progress",
                       "in progress", "in-progress", "running_fetch", "not_run", "not-run",
                       "not started", "not-started", "skipped", "deferred",
                       "cancelled", "canceled", "실행 중", "수집 중 · 1/8", "대기 중",
                       "running\nfetch", "running\tfetch", "in\tprogress", "실행중", "수집중", "대기중"):
            for key in ("releases.json", "__integration__", "__link_audit__"):
                with self.subTest(status=status, job=key):
                    self.assertFalse(_eligible_result(key, {"ok": True, "status": status}))

    def test_completed_core_and_auxiliary_runner_shapes_keep_real_success_and_failure(self):
        # Core results carry max_attempts; the actual auxiliary runner instead
        # supplies duration/retry fields and does not set max_attempts.
        with tempfile.TemporaryDirectory() as tmp:
            labels = Path(tmp) / "labels.json"
            now = datetime(2026, 10, 25, 0, tzinfo=timezone.utc)
            report = {
                "postflight_monitor": {"ok": False, "results": [
                    {"file": "releases.json", "ok": True},
                    {"file": "market_prices.json", "ok": True},
                    {"file": "promo_events.json", "ok": False}]},
                "results": [
                    {"file": "releases.json", "ok": True, "status": "정상", "max_attempts": 2,
                     "retry_count": 0, "duration_seconds": 1.2, "collection_errors": []},
                    {"file": "market_prices.json", "ok": False, "status": "반영 중단", "max_attempts": 2,
                     "retry_count": 1, "duration_seconds": 3.2, "error": "TimeoutError"},
                    {"file": "promo_events.json", "ok": True, "max_attempts": 2}],
                "integration": {"ok": True, "duration_seconds": .5, "retry_count": 0, "degraded": False},
                "link_audit": {"ok": False, "duration_seconds": .7, "retry_count": 1, "error": "TimeoutError"},
            }
            before = {"jobs": {"releases.json": {"runs": 7, "successes": 6}}}
            first = ingest_verified_report(report, {"jobs": {}}, stats_before=before, labels_path=labels, now=now)
            self.assertEqual(4, first["added"])
            self.assertEqual(1, first["postflight_skipped"])
            rows = {row["job_key"]: row for row in json.loads(labels.read_text())["labels"]}
            self.assertEqual({"releases.json", "market_prices.json", "__integration__", "__link_audit__"}, set(rows))
            self.assertEqual({"releases.json": True, "market_prices.json": False,
                              "__integration__": True, "__link_audit__": False},
                             {key: row["outcome"] for key, row in rows.items()})
            self.assertEqual(7, rows["releases.json"]["runs"])
            self.assertEqual(6, rows["releases.json"]["successes"])
            self.assertEqual(0, ingest_verified_report(report, {}, labels_path=labels, now=now)["added"])
            self.assertEqual(4, ingest_verified_report(report, {}, labels_path=labels,
                                                      now=now + timedelta(hours=6))["added"])

    def test_incomplete_same_window_result_cannot_overwrite_a_verified_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            labels = Path(tmp) / "labels.json"
            now = datetime(2026, 10, 25, 0, tzinfo=timezone.utc)
            report = {"postflight_monitor": {"results": [{"file": "releases.json", "ok": True}]},
                      "results": [{"file": "releases.json", "ok": True, "max_attempts": 2}]}
            self.assertEqual(1, ingest_verified_report(report, {}, labels_path=labels, now=now)["added"])
            before = json.loads(labels.read_text())["labels"]
            report["results"] = [{"file": "releases.json", "ok": False, "status": "running"},
                                 {"file": "releases.json", "ok": "false", "max_attempts": 2}]
            result = ingest_verified_report(report, {}, labels_path=labels, now=now)
            self.assertEqual((0, 0, 0), (result["eligible"], result["added"], result["updated"]))
            self.assertEqual(before, json.loads(labels.read_text())["labels"])

    def test_recovered_and_degraded_completed_jobs_remain_negative_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            labels = Path(tmp) / "labels.json"
            report = {"postflight_monitor": {"results": []},
                      "integration": {"ok": True, "recovered_after_retry": True, "duration_seconds": 3},
                      "link_audit": {"ok": True, "degraded": True, "duration_seconds": 3}}
            result = ingest_verified_report(report, {}, labels_path=labels)
            self.assertEqual(2, result["added"])
            self.assertTrue(all(row["outcome"] is False for row in json.loads(labels.read_text())["labels"]))


if __name__ == "__main__":
    unittest.main()
