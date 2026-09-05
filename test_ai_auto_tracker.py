from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path

import ai_auto_tracker as tracker


class FakeHTTPError(Exception):
    def __init__(self, code, retry_after=None):
        super().__init__(f"http {code}")
        self.code = code
        self.headers = {"Retry-After": retry_after} if retry_after is not None else {}


class AutoTrackerTests(unittest.TestCase):
    def test_domain_routing_isolated(self):
        self.assertEqual(tracker.classify_domain({"message":"Termux tablet reboot autostart failed"}), "tablet")
        self.assertEqual(tracker.classify_domain({"message":"KRW price collector 429 source failed"}), "market")
        self.assertEqual(tracker.classify_domain({"message":"GitHub Actions CI syntax test failed"}), "github")

    def test_explicit_domain_wins(self):
        self.assertEqual(tracker.classify_domain({"domain":"market","message":"tablet"}), "market")

    def test_fingerprint_is_stable(self):
        row = {"stage":"X","path":"a.py","message":"token=abc https://example.com/x"}
        self.assertEqual(tracker.fingerprint(row), tracker.fingerprint(row))

    def test_retry_after_honored(self):
        d = tracker.retry_decision(FakeHTTPError(429, "12"), 0, rng=lambda: 1.0)
        self.assertTrue(d.retryable)
        self.assertEqual(d.delay_seconds, 12.0)
        self.assertEqual(d.reason, "retry_after")

    def test_non_transient_not_retried(self):
        self.assertFalse(tracker.retry_decision(FakeHTTPError(404), 0).retryable)

    def test_retry_bounded_then_success(self):
        calls = {"n": 0}
        sleeps = []
        def op():
            calls["n"] += 1
            if calls["n"] < 3:
                raise TimeoutError("temporary")
            return "ok"
        self.assertEqual(tracker.call_with_retry(op, attempts=4, sleeper=sleeps.append), "ok")
        self.assertEqual(calls["n"], 3)
        self.assertEqual(len(sleeps), 2)

    def test_dedupe_and_cross_domain_handoff(self):
        with tempfile.TemporaryDirectory() as td:
            state = Path(td)/"state.json"
            event = {"stage":"COLLECTOR_HTTP_429","path":"collector.py","message":"price source 429"}
            first = tracker.observe([event], state_path=state)
            second = tracker.observe([event], state_path=state)
            self.assertEqual(first["incidents"][0]["status"], "new")
            self.assertEqual(second["incidents"][0]["status"], "recurring")
            self.assertEqual(second["incidents"][0]["occurrences"], 2)
            self.assertEqual(second["incidents"][0]["domain"], "market")
            self.assertEqual(second["main_selfrefine"], [])
            forbidden = {"retry_count","learning_state","error_ledger","quarantine","raw_log"}
            self.assertFalse(forbidden & set(second["handoffs"][0]))

    def test_corrupt_state_fails_closed_to_fresh_state(self):
        with tempfile.TemporaryDirectory() as td:
            state = Path(td)/"state.json"
            state.write_text("{bad", encoding="utf-8")
            out = tracker.observe([{"message":"CI test error"}], state_path=state)
            self.assertEqual(out["summary"]["new"], 1)
            raw = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(raw["schema"], tracker.SCHEMA)

    def test_dry_run_does_not_write_state(self):
        with tempfile.TemporaryDirectory() as td:
            state = Path(td)/"state.json"
            out = tracker.observe([{"message":"tablet Termux failed"}], state_path=state, dry_run=True)
            self.assertTrue(out["summary"]["dry_run"])
            self.assertFalse(state.exists())

    def test_secret_redaction(self):
        value = tracker._clean("Bearer abc.def token=123 password=xyz https://example.com/a")
        self.assertNotIn("abc.def", value)
        self.assertNotIn("123", value)
        self.assertNotIn("xyz", value)
        self.assertNotIn("example.com", value)


if __name__ == "__main__":
    unittest.main()
