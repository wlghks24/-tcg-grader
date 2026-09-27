import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import auto_repair_engine as repair
import auto_update_all as update_all
import fx_policy
import update_exchange_rates as exchange


class FxIntegrityV346Tests(unittest.TestCase):
    def _run_failed_refresh(self, raw: str):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / "exchange_rates.json"
            data.write_text(raw, encoding="utf-8")
            with mock.patch.object(exchange, "DATA", data), mock.patch.object(
                exchange, "fetch", side_effect=TimeoutError("timeout")
            ):
                result = exchange.main()
            return result

    def _trusted_payload(self, stamp: str):
        return {
            "updated_at": stamp,
            "base": "KRW",
            "rates": {"JPY_KRW": 9.1, "USD_KRW": 1400.0},
            "source": "https://api.frankfurter.dev/v2/rates?base=USD&quotes=KRW,JPY",
            "source_route": "frankfurter-v2",
        }

    def test_duplicate_key_current_state_fails_closed(self):
        result = self._run_failed_refresh(
            '{"base":"KRW","rates":{"JPY_KRW":9.0,"USD_KRW":1350.0,'
            '"USD_KRW":999.0}}'
        )
        self.assertEqual(result["rates"], {"JPY_KRW": 0.0, "USD_KRW": 0.0})
        self.assertEqual(result["collection_status"], "유효 환율 없음")

    def test_nonstandard_number_current_state_fails_closed(self):
        result = self._run_failed_refresh(
            '{"base":"KRW","rates":{"JPY_KRW":NaN,"USD_KRW":1350.0}}'
        )
        self.assertEqual(result["rates"], {"JPY_KRW": 0.0, "USD_KRW": 0.0})
        self.assertEqual(result["collection_status"], "유효 환율 없음")

    def test_malformed_current_state_fails_closed(self):
        result = self._run_failed_refresh('{"rates":')
        self.assertEqual(result["rates"], {"JPY_KRW": 0.0, "USD_KRW": 0.0})
        self.assertEqual(result["collection_status"], "유효 환율 없음")

    def test_corrupt_current_state_can_recover_from_trusted_refresh(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / "exchange_rates.json"
            data.write_text('{"rates":{"USD_KRW":1,"USD_KRW":2}}', encoding="utf-8")
            with mock.patch.object(exchange, "DATA", data), mock.patch.object(
                exchange, "fetch", return_value={"rates": {"KRW": 1400, "JPY": 140}}
            ):
                result = exchange.main()
            self.assertEqual(result["base"], "KRW")
            self.assertEqual(result["source_route"], "frankfurter-v2")
            self.assertEqual(result["rates"], {"JPY_KRW": 10.0, "USD_KRW": 1400.0})
            self.assertEqual(result["collection_status"], "정상")

    def test_shared_policy_rejects_stale_future_and_untrusted_sources(self):
        now = dt.datetime(2026, 9, 27, 16, 0, tzinfo=dt.timezone.utc)
        valid = self._trusted_payload((now - dt.timedelta(hours=1)).isoformat())
        self.assertTrue(fx_policy.validate_exchange_payload(valid, now=now)[0])

        stale = dict(valid, updated_at=(now - dt.timedelta(hours=73)).isoformat())
        self.assertFalse(fx_policy.validate_exchange_payload(stale, now=now)[0])
        future = dict(valid, updated_at=(now + dt.timedelta(hours=7)).isoformat())
        self.assertFalse(fx_policy.validate_exchange_payload(future, now=now)[0])
        untrusted = dict(valid, source="https://example.com/v2/rates")
        self.assertFalse(fx_policy.validate_exchange_payload(untrusted, now=now)[0])
        mismatch = dict(valid, source_route="frankfurter-legacy")
        self.assertFalse(fx_policy.validate_exchange_payload(mismatch, now=now)[0])
        query_tamper = dict(
            valid,
            source="https://api.frankfurter.dev/v2/rates?base=EUR&quotes=KRW,JPY",
        )
        self.assertFalse(fx_policy.validate_exchange_payload(query_tamper, now=now)[0])

    def test_shared_loader_rejects_ambiguous_json(self):
        now = dt.datetime(2026, 9, 27, 16, 0, tzinfo=dt.timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "exchange_rates.json"
            valid = self._trusted_payload((now - dt.timedelta(hours=1)).isoformat())
            path.write_text(json.dumps(valid), encoding="utf-8")
            self.assertEqual(fx_policy.load_krw_rates(path, now=now)["USD"], 1400.0)
            path.write_text(
                '{"base":"KRW","base":"KRW","rates":{"JPY_KRW":9.1,"USD_KRW":1400},'
                '"updated_at":"2026-09-27T15:00:00+00:00",'
                '"source":"https://api.frankfurter.dev/v2/rates?base=USD&quotes=KRW,JPY",'
                '"source_route":"frankfurter-v2"}',
                encoding="utf-8",
            )
            self.assertEqual(fx_policy.load_krw_rates(path, now=now)["USD"], 0.0)

    def test_auto_repair_and_orchestrator_use_same_fx_policy(self):
        now = dt.datetime.now(dt.timezone.utc)
        trusted = self._trusted_payload((now - dt.timedelta(minutes=5)).isoformat())
        self.assertTrue(repair._valid_project_payload("exchange_rates.json", trusted))
        update_all.validate_json("exchange_rates.json", trusted)

        untrusted = dict(trusted, source="https://example.com/v2/rates")
        self.assertFalse(repair._valid_project_payload("exchange_rates.json", untrusted))
        with self.assertRaisesRegex(ValueError, "provenance/freshness"):
            update_all.validate_json("exchange_rates.json", untrusted)

        stale = dict(trusted, updated_at=(now - dt.timedelta(hours=73)).isoformat())
        self.assertFalse(repair._valid_project_payload("exchange_rates.json", stale))
        with self.assertRaisesRegex(ValueError, "provenance/freshness"):
            update_all.validate_json("exchange_rates.json", stale)

    def test_adaptive_stats_duplicate_keys_recover_from_last_good(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            primary = root / "adaptive_collection_stats.json"
            backup = root / "adaptive_collection_stats.json.bak"
            primary.write_text(
                '{"jobs":{"first":{"runs":1}},"jobs":{"poison":{"runs":999}}}',
                encoding="utf-8",
            )
            backup.write_text(
                json.dumps({"version":1,"jobs":{"good":{"runs":2,"successes":2}},"updated_at":None}),
                encoding="utf-8",
            )
            with mock.patch.object(update_all, "ADAPTIVE_STATS", primary), mock.patch.object(
                update_all, "ADAPTIVE_STATS_BAK", backup
            ):
                loaded = update_all._load_adaptive_stats()
            self.assertIn("good", loaded["jobs"])
            self.assertNotIn("poison", loaded["jobs"])


if __name__ == "__main__":
    unittest.main()
