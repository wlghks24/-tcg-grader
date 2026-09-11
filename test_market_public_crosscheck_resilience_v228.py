from __future__ import annotations

import http.client
import tempfile
import unittest
from pathlib import Path

import market_public_crosscheck as crosscheck


class MarketPublicCrosscheckResilienceTests(unittest.TestCase):
    def test_http_protocol_failures_are_source_level_network_errors(self):
        self.assertIn(http.client.HTTPException, crosscheck.NETWORK_ERRORS)
        self.assertTrue(issubclass(http.client.IncompleteRead, http.client.HTTPException))

    def test_incomplete_body_is_isolated_and_other_source_continues(self):
        db = {
            "entries": {
                "KR|인페르노X|HIT": {
                    "card_name": "메가리자몽X ex",
                    "card_number": "116/080",
                    "source_crosschecks": [
                        {
                            "source": "Collectory",
                            "price_krw": 375000,
                            "confidence": 0.99,
                            "url": "https://collectory.cc/cards?search=old",
                        }
                    ],
                }
            }
        }

        def fetcher(url: str) -> str:
            if "collectory.cc" in url:
                raise http.client.IncompleteRead(b"partial", 100)
            return "Pokemon TCG 메가리자몽X ex 116/080 390,000원 거래 45"

        old_state, old_watch = crosscheck.STATE, crosscheck.WATCH
        with tempfile.TemporaryDirectory() as tmp:
            crosscheck.STATE = Path(tmp) / "state.json"
            crosscheck.WATCH = Path(tmp) / "watch.json"
            try:
                summary = crosscheck.crosscheck_market_db(db, fetcher=fetcher)
            finally:
                crosscheck.STATE, crosscheck.WATCH = old_state, old_watch

        self.assertEqual(1, summary["sources"]["Collectory"]["errors"])
        self.assertEqual(1, summary["sources"]["KREAM"]["checked"])
        self.assertEqual(1, summary["sources"]["KREAM"]["matched"])
        self.assertTrue(any("IncompleteRead" in item for item in summary["errors"]))

        preserved = {
            row["source"]: row
            for row in db["entries"]["KR|인페르노X|HIT"]["source_crosschecks"]
        }
        self.assertEqual(375000, preserved["Collectory"]["price_krw"])
        self.assertEqual(390000, preserved["KREAM"]["price_krw"])


if __name__ == "__main__":
    unittest.main()
