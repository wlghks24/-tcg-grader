import tempfile
import unittest
from pathlib import Path
from unittest import mock

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


if __name__ == "__main__":
    unittest.main()
