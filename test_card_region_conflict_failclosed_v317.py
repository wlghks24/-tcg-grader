from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

import card_identity_recognition as identity

ROOT = Path(__file__).resolve().parent


class CardRegionConflictFailClosedV317Tests(unittest.TestCase):
    def test_server_conflicting_edition_never_returns_automatic_best(self) -> None:
        candidate = {
            "market_key": "KR|PIKACHU|HIT",
            "region": "KR",
            "game": "pokemon",
            "card_name": "Pikachu",
            "card_number": "025",
            "confidence": 0.999,
            "matched_by": "confirmed_exact_image",
        }
        payload = {
            "game": "pokemon",
            "region": "KR",
            "ocr_text": "日本版 ポケモンカード ピカチュウ 025",
            "image_hash": "0000000000000001",
        }
        with mock.patch.object(identity, "match_learning", return_value=[candidate]), mock.patch.object(
            identity, "match_catalog", return_value=[candidate]
        ):
            result = identity.recognize(payload)
        self.assertTrue(result["region_conflict"])
        self.assertTrue(result["auto_selection_blocked"])
        self.assertIsNone(result["best"])
        self.assertEqual([candidate], result["candidates"])
        self.assertTrue(result["requires_confirmation"])

    def test_non_conflicting_edition_keeps_normal_best_candidate(self) -> None:
        candidate = {
            "market_key": "KR|PIKACHU|HIT",
            "region": "KR",
            "game": "pokemon",
            "card_name": "Pikachu",
            "card_number": "025",
            "confidence": 0.99,
            "matched_by": "card_number_exact+card_name",
        }
        payload = {
            "game": "pokemon",
            "region": "KR",
            "ocr_text": "한국판 포켓몬 카드 피카츄 025",
            "image_hash": "0000000000000001",
        }
        with mock.patch.object(identity, "match_learning", return_value=[]), mock.patch.object(
            identity, "match_catalog", return_value=[candidate]
        ):
            result = identity.recognize(payload)
        self.assertFalse(result["region_conflict"])
        self.assertFalse(result["auto_selection_blocked"])
        self.assertEqual(candidate, result["best"])

    def test_browser_blocks_conflict_before_generation_or_market_autofill(self) -> None:
        source = (ROOT / "card_identity_recognition.js").read_text(encoding="utf-8")
        self.assertIn("const browserConflict=browserRegion.conflict===true", source)
        self.assertIn("const identityConflict=browserConflict||server?.region_conflict===true", source)
        self.assertIn("if(server&&!identityConflict)candidates=mergeCandidates", source)
        self.assertIn("if(identityConflict){", source)
        self.assertIn("candidates=[];effectiveRegion='UNKNOWN'", source)
        self.assertIn("byId('identityCardName').value=''", source)
        self.assertIn("byId('identityCardNumber').value=''", source)
        self.assertIn("byId('identityMarketKey').value=''", source)
        self.assertIn("region_conflict:true", source)
        self.assertIn("자동 카드 선택·세대·시세 연결을 중단", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
