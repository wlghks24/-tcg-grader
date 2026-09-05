#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

import ai_auto_tracker as tracker


class AIAutoTrackerV27Tests(unittest.TestCase):
    def test_latest_success_supersedes_older_workflow_failure(self):
        runs = [
            {"id": "2", "name": "Main SELFREFINE", "status": "completed", "conclusion": "success", "head_sha": "new"},
            {"id": "1", "name": "Main SELFREFINE", "status": "completed", "conclusion": "failure", "head_sha": "old"},
        ]
        with mock.patch.object(tracker, "_github_runs", return_value=(runs, None)):
            issues = tracker._github_signals("wlghks24/-tcg-grader", None, None)
        self.assertEqual(issues, [])

    def test_latest_critical_workflow_failure_is_high(self):
        runs = [
            {"id": "3", "name": "Repository Integrity Guard", "status": "completed", "conclusion": "failure", "head_sha": "abc"},
        ]
        with mock.patch.object(tracker, "_github_runs", return_value=(runs, None)):
            issues = tracker._github_signals("wlghks24/-tcg-grader", None, None)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["severity"], "high")
        self.assertEqual(issues[0]["safe_auto_action"], "verified_selfrefine_only")

    def test_three_critical_workflow_failures_trigger_fail_closed_critical(self):
        names = ["Main SELFREFINE", "Repository Integrity Guard", "Exhaustive SELFREFINE Guard"]
        runs = [
            {"id": str(i), "name": name, "status": "completed", "conclusion": "failure", "head_sha": f"s{i}"}
            for i, name in enumerate(names, 1)
        ]
        with mock.patch.object(tracker, "_github_runs", return_value=(runs, None)):
            issues = tracker._github_signals("wlghks24/-tcg-grader", None, None)
        critical = [x for x in issues if x["severity"] == "critical"]
        self.assertEqual(len(critical), 1)
        self.assertEqual(critical[0]["safe_auto_action"], "fail_closed")

    def test_source_failure_streak_only_acts_on_fresh_health(self):
        now = dt.datetime(2026, 9, 5, 15, 0, tzinfo=dt.timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "source_collection_stats.json").write_text(json.dumps({
                "updated_at": "2026-09-05T14:30:00+00:00",
                "sources": {
                    "official-a": {"consecutive_failures": 3, "last_http_status": 503}
                },
            }), encoding="utf-8")
            with mock.patch.object(tracker, "ROOT", root):
                issues = tracker._source_health_signals(now, runtime_live=True)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["severity"], "high")
        self.assertEqual(issues[0]["code"], "SOURCE_REPEATED_FAILURE")

    def test_stale_committed_snapshot_is_not_false_actionable_in_github_mode(self):
        now = dt.datetime(2026, 9, 5, 15, 0, tzinfo=dt.timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "source_collection_stats.json").write_text(json.dumps({
                "updated_at": "2026-08-20T00:00:00+00:00",
                "sources": {
                    "old": {"consecutive_failures": 10, "last_http_status": 503}
                },
            }), encoding="utf-8")
            with mock.patch.object(tracker, "ROOT", root):
                issues = tracker._source_health_signals(now, runtime_live=False)
        self.assertEqual(issues, [])

    def test_429_github_api_is_not_retried_or_bypassed(self):
        headers = {"Retry-After": "60"}
        error = urllib.error.HTTPError(
            "https://api.github.com/repos/a/b/actions/runs",
            429,
            "rate limited",
            headers,
            None,
        )
        with mock.patch("urllib.request.urlopen", side_effect=error) as opened:
            runs, detail = tracker._github_runs("a/b", "secret-token", None)
        self.assertEqual(runs, [])
        self.assertIn("HTTP 429", detail)
        self.assertIn("Retry-After=60", detail)
        self.assertEqual(opened.call_count, 1)

    def test_market_tracker_findings_are_supervised_not_repaired_here(self):
        with mock.patch("market_ai_auto_tracker.scan_static", return_value=[{
            "code": "MARKET_API_ROUTE_DUPLICATE",
            "path": "tcg_updater.py",
            "severity": "critical",
        }]):
            issues = tracker._market_ai_signals()
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["severity"], "high")
        self.assertEqual(issues[0]["safe_auto_action"], "market_ai_tracker")

    def test_integrated_tracker_ignores_its_own_latest_run(self):
        runs = [
            {"id": "7", "name": "Integrated AI Auto Tracking", "status": "completed", "conclusion": "failure", "head_sha": "self"},
            {"id": "8", "name": "Main SELFREFINE", "status": "completed", "conclusion": "success", "head_sha": "ok"},
        ]
        with mock.patch.object(tracker, "_github_runs", return_value=(runs, None)):
            issues = tracker._github_signals("wlghks24/-tcg-grader", None, None)
        self.assertEqual(issues, [])

    def test_runtime_state_counts_repeat_and_resolution(self):
        now = dt.datetime(2026, 9, 5, 15, 0, tzinfo=dt.timezone.utc)
        issue = tracker._issue("high", "X", "component", "same evidence", "fix", "verify")
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            with mock.patch.object(tracker, "STATE", state):
                _, first = tracker._update_state([issue], now)
                _, second = tracker._update_state([issue], now + dt.timedelta(hours=1))
                final, third = tracker._update_state([], now + dt.timedelta(hours=2))
        self.assertEqual(first["new_issue_count"], 1)
        self.assertEqual(second["repeat_issue_count"], 1)
        self.assertEqual(third["resolved_since_last"], 1)
        row = final["observations"][issue["signature"]]
        self.assertTrue(row["resolved"])
        self.assertEqual(row["resolved_count"], 1)

    def test_public_report_strips_internal_signature(self):
        payload = {
            "ok": False,
            "status": "high",
            "generated_at": "2026-09-05T15:00:00+00:00",
            "summary": {"high": 1},
            "issues": [{
                "signature": "internal",
                "severity": "high",
                "code": "X",
                "component": "c",
                "evidence": "e",
                "next_action": "a",
                "verification": "v",
                "safe_auto_action": "verified_selfrefine_only",
            }],
            "safety": {"github_write": False},
        }
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report.json"
            report.write_text(json.dumps(payload), encoding="utf-8")
            with mock.patch.object(tracker, "REPORT", report):
                public = tracker.public_report()
        self.assertNotIn("signature", public["issues"][0])
        self.assertFalse(public["safety"]["github_write"])

    def test_run_once_never_claims_code_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report.json"
            state = Path(tmp) / "state.json"
            with (
                mock.patch.object(tracker, "REPORT", report),
                mock.patch.object(tracker, "STATE", state),
                mock.patch.object(tracker, "_feature_contract_signal", return_value=[]),
                mock.patch.object(tracker, "_source_health_signals", return_value=[]),
                mock.patch.object(tracker, "_auto_update_signals", return_value=[]),
                mock.patch.object(tracker, "_link_signals", return_value=[]),
                mock.patch.object(tracker, "_event_signals", return_value=[]),
                mock.patch.object(tracker, "_market_ai_signals", return_value=[]),
                mock.patch.object(tracker, "_selfrefine_signals", return_value=[]),
            ):
                result = tracker.run_once(trigger="test", runtime_live=False)
        self.assertEqual(result["status"], "pass")
        self.assertFalse(result["safety"]["github_write"])
        self.assertFalse(result["safety"]["http_403_429_bypass"])
        self.assertTrue(result["safety"]["verified_selfrefine_only_for_code_repair"])


if __name__ == "__main__":
    unittest.main()
