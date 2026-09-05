from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import collection_verification_gate as gate


class CollectionVerificationGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.now = dt.datetime(2026, 9, 6, 0, 0, tzinfo=dt.timezone.utc)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, value):
        (self.root / name).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def valid_fixture(self):
        stamp = self.now.isoformat(timespec="seconds")
        self.write("source_collection_stats.json", {"updated_at": stamp, "sources": {"official": {"runs": 1}}})
        self.write("adaptive_collection_stats.json", {"updated_at": stamp, "jobs": {"release": {"runs": 1}}})
        self.write("market_prices.json", {"updated_at": stamp, "entries": {"KR|테스트|BOX": {"display": "₩10,000", "source": "https://example.com/item", "source_date": "2026-09-06"}}})
        self.write("releases.json", {"items": [{"game": "Pokémon", "region": "JP", "name": "Test", "release_date": "2026-09-06", "source": "https://example.com/release"}]})
        self.write("promo_events.json", {"items": [{"region": "KR", "category": "promo", "name_ko": "Test", "source": "https://example.com/event", "source_grade": "official"}]})
        self.write("auto_update_report.json", {"results": [{"file": name, "ok": True, "remaining_collection_errors": []} for name in gate.CRITICAL_FILES]})

    def test_valid_collection_passes(self):
        self.valid_fixture()
        report = gate.verify(self.root, now=self.now)
        self.assertEqual("pass", report["status"])
        self.assertEqual(0, report["counts"]["critical"])

    def test_empty_source_health_fails_closed(self):
        self.valid_fixture()
        self.write("source_collection_stats.json", {"updated_at": self.now.isoformat(), "sources": {}})
        report = gate.verify(self.root, now=self.now)
        self.assertEqual("fail_closed", report["status"])
        self.assertTrue(any(x["code"] == "EMPTY_SOURCE_HEALTH" for x in report["findings"]))

    def test_stale_health_is_degraded(self):
        self.valid_fixture()
        old = self.now - dt.timedelta(hours=2)
        self.write("source_collection_stats.json", {"updated_at": old.isoformat(), "sources": {"a": {}}})
        report = gate.verify(self.root, now=self.now, max_health_age_seconds=900)
        self.assertEqual("degraded", report["status"])
        self.assertTrue(any(x["code"] == "STALE_COLLECTION_STATE" for x in report["findings"]))

    def test_invalid_market_provenance_is_degraded(self):
        self.valid_fixture()
        self.write("market_prices.json", {"updated_at": self.now.isoformat(), "entries": {"KR|테스트|BOX": {"display": "₩10,000", "source": "http://localhost/item"}}})
        report = gate.verify(self.root, now=self.now)
        self.assertEqual("degraded", report["status"])
        self.assertTrue(any(x["code"] == "INVALID_MARKET_ENTRY" for x in report["findings"]))

    def test_missing_critical_output_report_fails_closed(self):
        self.valid_fixture()
        self.write("auto_update_report.json", {"results": []})
        report = gate.verify(self.root, now=self.now)
        self.assertEqual("fail_closed", report["status"])
        self.assertEqual(4, sum(x["code"] == "CRITICAL_OUTPUT_NOT_REPORTED" for x in report["findings"]))

    def test_429_is_degraded_not_bypassed(self):
        self.valid_fixture()
        rows = [{"file": name, "ok": True, "remaining_collection_errors": []} for name in gate.CRITICAL_FILES]
        rows[0] = {"file": "releases.json", "ok": False, "remaining_collection_errors": ["official: HTTPError: status 429; Retry-After 120s"]}
        self.write("auto_update_report.json", {"results": rows})
        report = gate.verify(self.root, now=self.now)
        self.assertEqual("degraded", report["status"])
        finding = next(x for x in report["findings"] if x["code"] == "DEGRADED_COLLECTION_OUTPUT")
        self.assertEqual(1, finding["blocked_403_429"])
        self.assertFalse(report["safety"]["bypass_403_429"])

    def test_hard_collection_failure_fails_closed(self):
        self.valid_fixture()
        rows = [{"file": name, "ok": True, "remaining_collection_errors": []} for name in gate.CRITICAL_FILES]
        rows[2] = {"file": "promo_events.json", "ok": False, "remaining_collection_errors": ["parser schema mismatch"]}
        self.write("auto_update_report.json", {"results": rows})
        report = gate.verify(self.root, now=self.now)
        self.assertEqual("fail_closed", report["status"])
        self.assertTrue(any(x["code"] == "HARD_COLLECTION_FAILURE" for x in report["findings"]))

    def test_bad_release_region_is_degraded(self):
        self.valid_fixture()
        self.write("releases.json", {"items": [{"game": "Pokémon", "region": "XX", "name": "Bad", "source": "https://example.com/r"}]})
        report = gate.verify(self.root, now=self.now)
        self.assertEqual("degraded", report["status"])
        self.assertTrue(any(x["code"] == "INVALID_RELEASE_ROW" for x in report["findings"]))


if __name__ == "__main__":
    unittest.main()
