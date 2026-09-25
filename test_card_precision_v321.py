from __future__ import annotations

import unittest
from pathlib import Path

import card_grading_valuation as valuation
import card_identity_recognition as identity

ROOT = Path(__file__).resolve().parent


class CardPrecisionV321Tests(unittest.TestCase):
    def test_explicit_en_label_is_english_edition_evidence(self) -> None:
        evidence = identity.infer_region_evidence("EN Pikachu collector card")
        self.assertEqual("US", evidence["region"])
        self.assertFalse(evidence["conflict"])
        self.assertIn("explicit_region_label", evidence["basis"])
        browser = (ROOT / "card_identity_recognition.js").read_text(encoding="utf-8")
        self.assertIn("US|USA|EN|ENGLISH", browser)

    def test_ocr_stage_consensus_does_not_merge_cross_edition_identity(self) -> None:
        base = {
            "card_name": "Pikachu",
            "card_number": "025/165",
            "market_key": "",
            "confidence": 0.997,
            "matched_by": "card_number_exact+card_name",
        }
        summaries = [
            {"best_candidate": {**base, "region": "KR"}, "numbers_detected": ["025/165"]},
            {"best_candidate": {**base, "region": "JP"}, "numbers_detected": []},
        ]
        result = identity._identity_stage_consensus(summaries)
        self.assertFalse(result["cross_validated"])
        self.assertEqual(1, result["identity_consensus"]["stage_votes"])
        self.assertIn(result["identity_consensus"]["region"], {"KR", "JP"})

    def _perfect_card(self) -> dict:
        return {
            "centering_front": 50,
            "centering_back": 50,
            "corners": 10,
            "edges": 10,
            "surface": 10,
            "micro_flaws": 0,
            "is_authentic": True,
        }

    def test_public_exact_grade_price_without_provenance_fails_closed(self) -> None:
        result = valuation.verified_card_valuation(
            "Pikachu",
            self._perfect_card(),
            {"PSA": {"10": 123000}},
        )
        psa = result["valuations"]["PSA"]
        self.assertFalse(psa["available"])
        self.assertIsNone(psa["krw"])
        self.assertIn("출처", psa["reason"])

    def test_public_exact_grade_price_with_provenance_is_available(self) -> None:
        result = valuation.verified_card_valuation(
            "Pikachu",
            self._perfect_card(),
            {"PSA": {"10": 123000}},
            {"PSA": {"10": {
                "source": "https://example.com/sold/pikachu",
                "price_type": "sold",
                "observed_on": "2026-09-25",
            }}},
        )
        psa = result["valuations"]["PSA"]
        self.assertTrue(psa["available"])
        self.assertEqual(123000, psa["krw"])
        self.assertTrue(psa["evidence_verified"])

    def test_manual_exact_grade_price_remains_explicit_user_provided_path(self) -> None:
        result = valuation.verified_card_valuation(
            "Pikachu",
            self._perfect_card(),
            {"PSA": {"10": 123000}},
            price_source="user_provided_exact_grade",
        )
        psa = result["valuations"]["PSA"]
        self.assertTrue(psa["available"])
        self.assertEqual("user_provided_exact_grade", psa["source"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
