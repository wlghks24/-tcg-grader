from __future__ import annotations

import json
from pathlib import Path
import datetime as dt
import unittest

import card_grading_valuation as valuation
import collection_verification_gate as gate
import tablet_runtime_manifest as manifest

ROOT = Path(__file__).resolve().parent


class CardCoreProvenanceV296Tests(unittest.TestCase):
    def pristine(self):
        return {
            "centering_front": 50, "centering_back": 50, "corners": 10,
            "edges": 10, "surface": 10, "micro_flaws": 0, "is_authentic": True,
        }

    def test_positive_static_exact_grade_prices_have_structured_provenance(self):
        db = json.loads((ROOT / "market_prices.json").read_text(encoding="utf-8"))
        allowed = {"sold", "auction_result", "official_example", "market_guide"}
        positives = 0
        for market_key, profile in (db.get("graded_prices") or {}).items():
            if not isinstance(profile, dict):
                continue
            evidence = profile.get("grade_price_evidence") or {}
            for company, grades in (profile.get("grade_prices_krw") or {}).items():
                if not isinstance(grades, dict):
                    continue
                for grade, price in grades.items():
                    if float(price or 0) <= 0:
                        continue
                    positives += 1
                    row = ((evidence.get(company) or {}).get(str(grade)) or {})
                    self.assertTrue(str(row.get("source") or "").startswith("https://"), (market_key, company, grade))
                    self.assertIn(row.get("price_type"), allowed, (market_key, company, grade))
                    self.assertTrue(row.get("observed_on") or row.get("observed_period"), (market_key, company, grade))
        self.assertGreaterEqual(positives, 3)

    def test_public_exact_price_without_provenance_is_suppressed(self):
        result = valuation.verified_card_valuation(
            "test", self.pristine(), {"PSA": {"10": 123456}},
            grade_price_evidence={}, price_source="exact_company_grade_observation", exchange_rate=1400,
        )
        row = result["valuations"]["PSA"]
        self.assertFalse(row["available"])
        self.assertIsNone(row["krw"])
        self.assertFalse(row["evidence_verified"])
        self.assertIn("근거 부족", row["reason"])

    def test_public_exact_price_with_provenance_is_available(self):
        evidence = {"PSA": {"10": {
            "source": "https://example.com/sold/1", "price_type": "sold",
            "observed_on": "2026-09-22", "label": "exact sold",
        }}}
        result = valuation.verified_card_valuation(
            "test", self.pristine(), {"PSA": {"10": 123456}},
            grade_price_evidence=evidence, price_source="exact_company_grade_observation", exchange_rate=1400,
        )
        row = result["valuations"]["PSA"]
        self.assertTrue(row["available"])
        self.assertEqual(123456, row["krw"])
        self.assertTrue(row["evidence_verified"])
        self.assertEqual("sold", row["evidence"]["price_type"])

    def test_missing_or_invalid_fx_never_fabricates_usd_value(self):
        evidence = {"PSA": {"10": {
            "source": "https://example.com/sold/1", "price_type": "sold", "observed_on": "2026-09-22",
        }}}
        for bad in (None, "", False, "nan", float("inf"), 0, 99, 10001):
            with self.subTest(rate=bad):
                result = valuation.verified_card_valuation(
                    "test", self.pristine(), {"PSA": {"10": 140000}},
                    grade_price_evidence=evidence, exchange_rate=bad,
                )
                self.assertEqual(140000, result["valuations"]["PSA"]["krw"])
                self.assertIsNone(result["valuations"]["PSA"]["usd"])
                self.assertIsNone(result["exchange_rate"])
                self.assertFalse(result["exchange_rate_available"])

    def test_manual_exact_price_stays_user_provided_not_publicly_verified(self):
        result = valuation.verified_card_valuation(
            "manual", self.pristine(), {"PSA": {"10": 100000}},
            price_source="user_provided_exact_grade", exchange_rate=None,
        )
        row = result["valuations"]["PSA"]
        self.assertTrue(row["available"])
        self.assertEqual("user_provided_exact_grade", row["source"])
        self.assertFalse(row["evidence_verified"])

    def test_runtime_manifest_fail_closes_card_core_dependencies(self):
        required = {
            "grading_accuracy_v99.py", "card_grading_valuation.py", "card_identity_recognition.py",
            "server_security_guard.py", "grading_vision_engine.js", "grading_accuracy_v99.js",
            "card_metadata_classifier_v326.js", "card_identity_recognition.js",
        }
        self.assertTrue(required.issubset(set(manifest.ACTIVE_RUNTIME_FILES)))

    def test_collection_gate_accepts_current_static_grade_provenance(self):
        findings = []
        summary = gate._audit_market(ROOT, dt.datetime.now(dt.timezone.utc), findings)
        self.assertGreaterEqual(summary["positive_grade_prices"], 3)
        self.assertEqual(0, summary["invalid_graded_price_evidence"])
        self.assertFalse(any(row.get("code") == "INVALID_GRADED_PRICE_EVIDENCE" for row in findings))


if __name__ == "__main__":
    unittest.main(verbosity=2)
