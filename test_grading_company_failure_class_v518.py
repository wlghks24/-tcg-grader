#!/usr/bin/env python3
"""V518: source failure classifications preserve strict collection-gate semantics."""
from __future__ import annotations

import unittest
from unittest import mock

import grading_company_watch as watch


class GradingCompanyFailureClassV518Tests(unittest.TestCase):
    def _capture(self, message: str, previous=None):
        source = watch.WATCH_SOURCES["PSA"][0]
        def failing_fetcher(_url):
            raise RuntimeError(message)
        with mock.patch.object(watch, "WATCH_SOURCES", {"PSA": [source]}):
            payload = watch.collect(previous or {}, fetcher=failing_fetcher)
        return source["id"], payload

    def test_psa_403_is_blocked_not_unclassified_or_healthy(self):
        source_id, result = self._capture("HTTPError: status 403")
        row = result["sources"][source_id]
        self.assertEqual(row["failure_class"], "SOURCE_BLOCKED")
        self.assertEqual(row["status"], "degraded")
        self.assertFalse(row["verified_official_source"])
        self.assertEqual(result["summary"]["healthy_sources"], 0)
        health = result["companies"]["PSA"]["source_health"][0]
        self.assertEqual(health["failure_class"], "SOURCE_BLOCKED")
        self.assertEqual(health["status"], "degraded")

    def test_500_and_429_are_distinct_failures_without_retry_loophole(self):
        for message, expected in (
            ("HTTPError: status 500", "SOURCE_TRANSIENT"),
            ("HTTPError: status 429", "RATE_LIMIT_PRESSURE"),
            ("unexpected body format", "ROOT_CAUSE_UNRESOLVED"),
        ):
            with self.subTest(message=message):
                source_id, result = self._capture(message)
                self.assertEqual(result["sources"][source_id]["failure_class"], expected)
                self.assertEqual(result["sources"][source_id]["status"], "degraded")

    def test_retained_last_good_is_never_reclassified_as_fresh(self):
        source = watch.WATCH_SOURCES["PSA"][0]
        legacy = {
            "company": "PSA", "source_id": source["id"],
            "kind": source["kind"], "market": source["market"],
            "currency": source["currency"], "url": source["url"],
            "status": "ok", "failure_class": "HEALTHY",
            "signal_fingerprint": "verified-prior-signature",
            "verified_official_source": True,
            "services": [{"name": "Historical service", "fee": 42}],
            "announcements": [],
        }
        source_id, result = self._capture("HTTPError: status 403", {"sources": {source["id"]: legacy}})
        row = result["sources"][source_id]
        self.assertEqual(row["failure_class"], "SOURCE_BLOCKED")
        self.assertEqual(row["status"], "degraded")
        self.assertTrue(row["verified_official_source"])
        self.assertEqual(row["services"], legacy["services"])
        self.assertTrue(result["companies"]["PSA"]["markets"][source["market"]]["retained_last_good"])
        self.assertEqual(result["summary"]["healthy_sources"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
