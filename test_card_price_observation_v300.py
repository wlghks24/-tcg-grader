from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import card_grading_valuation as valuation
import collection_verification_gate as gate


class CardPriceObservationV300Tests(unittest.TestCase):
    def pristine(self):
        return {
            "centering_front": 50, "centering_back": 50, "corners": 10,
            "edges": 10, "surface": 10, "micro_flaws": 0, "is_authentic": True,
        }

    @staticmethod
    def evidence(**overrides):
        row = {
            "source": "https://example.com/sold/1",
            "price_type": "sold",
            "observed_on": "2026-09-22",
            "label": "exact sold",
        }
        row.update(overrides)
        return row

    def test_runtime_rejects_malformed_and_future_observation_dates(self):
        for bad in ("not-a-date", "2026-02-30", "2099-12-31"):
            with self.subTest(observed_on=bad):
                result = valuation.verified_card_valuation(
                    "test", self.pristine(), {"PSA": {"10": 123456}},
                    grade_price_evidence={"PSA": {"10": self.evidence(observed_on=bad)}},
                    price_source="exact_company_grade_observation", exchange_rate=1400,
                )
                row = result["valuations"]["PSA"]
                self.assertFalse(row["available"])
                self.assertFalse(row["evidence_verified"])

    def test_runtime_rejects_invalid_or_future_period_but_preserves_historical_evidence(self):
        for bad in ("2026-99", "bad-period", "2099-12"):
            with self.subTest(observed_period=bad):
                evidence = self.evidence(observed_on="", observed_period=bad)
                self.assertIsNone(valuation._clean_grade_price_evidence(evidence))
        historical = self.evidence(observed_on="2020-01-01")
        cleaned = valuation._clean_grade_price_evidence(historical)
        self.assertIsNotNone(cleaned)
        self.assertEqual("2020-01-01", cleaned["observed_on"])

    def test_collection_gate_rejects_invalid_month_and_future_observation(self):
        now = dt.datetime(2026, 9, 23, tzinfo=dt.timezone.utc)
        base_entry = {"display": "x", "source": "https://example.com/item", "source_date": "2026-09-23"}
        for timestamp_key, timestamp_value, expected_reason in (
            ("observed_period", "2026-99", "invalid_observed_period"),
            ("observed_on", "2099-12-31", "future_observed_on"),
        ):
            with self.subTest(value=timestamp_value), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                evidence_row = {"source": "https://example.com/sold/1", "price_type": "sold", timestamp_key: timestamp_value}
                payload = {
                    "updated_at": now.isoformat(),
                    "entries": {"KR|x|HIT": base_entry},
                    "graded_prices": {
                        "KR|x|HIT": {
                            "grade_prices_krw": {"PSA": {"10": 100000}},
                            "grade_price_evidence": {"PSA": {"10": evidence_row}},
                        }
                    },
                }
                (root / "market_prices.json").write_text(json.dumps(payload), encoding="utf-8")
                findings = []
                summary = gate._audit_market(root, now, findings)
                self.assertEqual(1, summary["invalid_graded_price_evidence"])
                self.assertTrue(any(expected_reason in row.get("reasons", []) for row in findings))


if __name__ == "__main__":
    unittest.main(verbosity=2)
