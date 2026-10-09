#!/usr/bin/env python3
"""V550: never bypass blocked storefronts or lose previously verified price evidence."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import market_public_crosscheck as market


KEY = "KR|인페르노X|HIT"
OLD = {
    "source": "KREAM", "price_krw": 380000, "observed_at": "2026-10-01T10:00:00+00:00",
    "url": "https://kream.co.kr/search?keyword=old", "confidence": 0.99,
}
ROW = {"card_name": "메가리자몽X ex", "card_number": "116/080"}
COLLECTORY = "🇰🇷 메가리자몽X ex 116/080 MUR 현재 시세 ₩375,000"
KREAM = "Pokemon TCG 메가리자몽X ex 인페르노X 116/080 390,000원 거래 45"


class FreeSourceFallbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.h = mock.patch.object(market, "HEALTH", root / "links.json")
        self.s = mock.patch.object(market, "STATE", root / "state.json")
        self.w = mock.patch.object(market, "WATCH", root / "watch.json")
        self.h.start();self.s.start();self.w.start()
        self.addCleanup(self.h.stop);self.addCleanup(self.s.stop);self.addCleanup(self.w.stop)
        market.WATCH.write_text('{"items":[]}', encoding="utf-8")
        self.now = dt.datetime.now(dt.timezone.utc)

    def report(self, stamp=None, failures=5, url="https://kream.co.kr/products/123"):
        stamp = stamp or self.now.isoformat(timespec="seconds")
        market.HEALTH.write_text(json.dumps({
            "updated_at": stamp,
            "transient_details": [{"url": url, "detail": "TimeoutError"} for _ in range(failures)]
        }), encoding="utf-8")

    def fetch(self, calls):
        def go(url):
            calls.append(url)
            return COLLECTORY if "collectory.cc" in url else KREAM
        return go

    def test_kream_is_deferred_collectory_runs_and_old_price_is_retained(self):
        self.report()
        db = {"entries": {KEY: {**ROW, "source_crosschecks": [dict(OLD)]}}}
        calls = []
        with mock.patch.dict("os.environ", {"TCG_MARKET_CROSSCHECK_QUERIES": "1"}, clear=False):
            result = market.crosscheck_market_db(db, fetcher=self.fetch(calls))
        self.assertEqual(len(calls), 1)
        self.assertIn("collectory.cc", calls[0])
        self.assertIn("KREAM", result["provider_cooldowns"])
        self.assertEqual(result["sources"]["KREAM"]["checked"], 0)
        self.assertEqual(result["sources"]["KREAM"]["cooldown_skipped"], 1)
        found = {row["source"]: row for row in db["entries"][KEY]["source_crosschecks"]}
        self.assertEqual(found["KREAM"]["observed_at"], OLD["observed_at"])
        self.assertEqual(found["KREAM"]["price_krw"], OLD["price_krw"])
        self.assertEqual(found["Collectory"]["price_krw"], 375000)
        self.assertTrue(result["previous_verified_observations_preserved"])

    def test_old_report_does_not_disable_provider(self):
        self.report(stamp=(self.now - dt.timedelta(hours=2)).isoformat(timespec="seconds"))
        db = {"entries": {KEY: dict(ROW)}}
        calls = []
        result = market.crosscheck_market_db(db, fetcher=self.fetch(calls))
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["provider_cooldowns"], {})
        self.assertEqual(result["sources"]["KREAM"]["checked"], 1)

    def test_future_report_is_not_authoritative(self):
        self.report(stamp=(self.now + dt.timedelta(hours=1)).isoformat(timespec="seconds"))
        self.assertEqual(market._free_provider_cooldown(self.now), {})

    def test_single_timeout_or_other_domain_does_not_disable_kream(self):
        self.report(failures=2)
        self.assertEqual(market._free_provider_cooldown(self.now), {})
        self.report(failures=8, url="https://notkream.co.kr/products/123")
        self.assertEqual(market._free_provider_cooldown(self.now), {})
        self.report(failures=8, url="http://kream.co.kr/products/123")
        self.assertEqual(market._free_provider_cooldown(self.now), {})

    def test_corrupt_report_fails_open_for_collection_not_evidence(self):
        market.HEALTH.write_text('{"transient_details":', encoding="utf-8")
        self.assertEqual(market._free_provider_cooldown(self.now), {})


if __name__ == "__main__":
    unittest.main()
