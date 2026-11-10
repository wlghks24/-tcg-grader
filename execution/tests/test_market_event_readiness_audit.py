"""Synthetic-only market/event readiness tests; no network and no writes to source."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from execution.market_event_readiness_audit import audit, day, https_source, stamp

NOW = dt.datetime(2026, 11, 10, 2, 0, tzinfo=dt.timezone.utc)


def data(root, *, old_fx=False, only_source_date=False, expired=False):
    t = "2026-10-08T00:00:00+00:00" if old_fx else "2026-11-10T00:00:00+00:00"
    files = {
        "exchange_rates.json": {"updated_at": t, "source_timestamp": t,
            "source": "https://api.frankfurter.dev/v2/rates?base=USD&quotes=KRW,JPY",
            "source_route": "frankfurter-v2", "rates": {"USD_KRW": 1370.0, "JPY_KRW": 8.75}},
        "market_prices.json": {"entries": {"JP|테스트박스|BOX": {
            "market_observed_at": None if only_source_date else "2026-11-10",
            "source_date": "2026-11-10", "source": "https://example.org/item",
            "link_status": "정상", "display": "₩30,000"}}},
        "promo_events.json": {"items": [{"category": "promo",
            "end_date": "2026-10-01" if expired else "2026-11-30",
            "status": "진행 중"}, {"category": "movie", "tracking_only": True,
            "status": "한국 개봉일 미발표"}]},
    }
    for name, payload in files.items():
        (root / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class ReadinessTests(unittest.TestCase):
    def test_old_fx_is_unavailable_not_converted_to_krw(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data(root, old_fx=True)
            report = audit(root, now=NOW)
            self.assertEqual("UNAVAILABLE", report["fx_status"])
            self.assertIn("FX_UNVERIFIED_OR_STALE", [r["code"] for r in report["issues"]])
            self.assertFalse(report["auto_install_allowed"])

    def test_fresh_observation_is_not_sale_or_prediction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data(root)
            report = audit(root, now=NOW)
            self.assertEqual(1, report["counts"]["market_fresh_observed"])
            self.assertEqual("NOT_AUTHORIZED_FROM_SNAPSHOT", report["hot_price_prediction"])
            self.assertEqual("NOT_MEASURED", report["grading_accuracy"])
            self.assertFalse(report["physical_tablet_verified"])

    def test_source_date_does_not_count_as_hot_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data(root, only_source_date=True)
            report = audit(root, now=NOW)
            self.assertEqual(0, report["counts"]["market_fresh_observed"])
            self.assertEqual(1, report["counts"]["market_source_date_only"])
            self.assertEqual("HOLD", report["status"])

    def test_expired_active_event_and_movie_watch_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data(root, expired=True)
            report = audit(root, now=NOW)
            self.assertEqual(1, report["counts"]["event_expired_active"])
            self.assertEqual(1, report["counts"]["movie_watch_only"])
            self.assertIn("EVENT_EXPIRED_BUT_ACTIVE", [r["code"] for r in report["issues"]])

    def test_corrupt_or_symlink_fx_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data(root)
            (root / "exchange_rates.json").write_text("{invalid", encoding="utf-8")
            self.assertEqual("UNAVAILABLE", audit(root, now=NOW)["fx_status"])
            (root / "exchange_rates.json").unlink()
            (root / "exchange_rates.json").symlink_to(root / "market_prices.json")
            self.assertEqual("UNAVAILABLE", audit(root, now=NOW)["fx_status"])

    def test_future_invalid_and_insecure_inputs(self):
        self.assertIsNone(day("2026-02-30"))
        self.assertIsNone(stamp("2026-11-10T10:00:00"))
        self.assertFalse(https_source("http://example.org/"))
        self.assertFalse(https_source("https://user:pass@example.org/"))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data(root)
            p = root / "market_prices.json"
            doc = json.loads(p.read_text(encoding="utf-8"))
            doc["entries"]["JP|테스트박스|BOX"]["market_observed_at"] = "2026-11-11"
            p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(1, audit(root, now=NOW)["counts"]["market_future"])


if __name__ == "__main__":
    unittest.main()
