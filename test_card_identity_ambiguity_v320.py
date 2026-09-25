from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest import mock

import card_identity_recognition as identity

ROOT = Path(__file__).resolve().parent


class CardIdentityAmbiguityV320Tests(unittest.TestCase):
    def candidate(self, region: str, *, name: str = "Pikachu", number: str = "025/165", market_key: str = "", confidence: float = 0.99) -> dict:
        return {
            "market_key": market_key,
            "region": region,
            "game": "pokemon",
            "card_name": name,
            "card_number": number,
            "confidence": confidence,
            "matched_by": "card_number_exact+card_name",
        }

    def test_unknown_edition_with_cross_region_top_candidates_fails_closed(self) -> None:
        kr = self.candidate("KR", market_key="KR|Pikachu 025/165|HIT", confidence=0.997)
        jp = self.candidate("JP", market_key="JP|Pikachu 025/165|HIT", confidence=0.995)
        payload = {
            "game": "pokemon",
            "region": "UNKNOWN",
            "ocr_text": "Pikachu 025/165",
            "image_hash": "0000000000000001",
        }
        with mock.patch.object(identity, "match_learning", return_value=[]), mock.patch.object(
            identity, "match_catalog", return_value=[kr, jp]
        ):
            result = identity.recognize(payload)
        self.assertTrue(result["region_ambiguous"])
        self.assertTrue(result["identity_ambiguous"])
        self.assertTrue(result["market_link_blocked"])
        self.assertTrue(result["auto_selection_blocked"])
        self.assertIsNone(result["best"])
        self.assertEqual(2, len(result["candidates"]))

    def test_same_region_near_tie_between_distinct_cards_fails_closed(self) -> None:
        first = self.candidate("KR", name="Pikachu", number="025/165", confidence=0.997)
        second = self.candidate("KR", name="Pikachu ex", number="025/165", confidence=0.996)
        payload = {
            "game": "pokemon",
            "region": "KR",
            "ocr_text": "한국판 Pikachu 025/165",
            "image_hash": "0000000000000001",
        }
        with mock.patch.object(identity, "match_learning", return_value=[]), mock.patch.object(
            identity, "match_catalog", return_value=[first, second]
        ):
            result = identity.recognize(payload)
        self.assertFalse(result["region_ambiguous"])
        self.assertTrue(result["identity_ambiguous"])
        self.assertTrue(result["auto_selection_blocked"])
        self.assertIsNone(result["best"])

    def test_clear_single_candidate_can_identify_card_but_unknown_edition_still_blocks_price_link(self) -> None:
        only = self.candidate("JP", market_key="JP|Pikachu 025/165|HIT", confidence=0.997)
        payload = {
            "game": "pokemon",
            "region": "UNKNOWN",
            "ocr_text": "Pikachu 025/165",
            "image_hash": "0000000000000001",
        }
        with mock.patch.object(identity, "match_learning", return_value=[]), mock.patch.object(
            identity, "match_catalog", return_value=[only]
        ):
            result = identity.recognize(payload)
        self.assertFalse(result["identity_ambiguous"])
        self.assertFalse(result["auto_selection_blocked"])
        self.assertEqual(only, result["best"])
        self.assertTrue(result["market_link_blocked"])
        self.assertEqual("UNKNOWN", result["region_hint"])

    def test_browser_does_not_promote_unknown_edition_from_catalog_candidate(self) -> None:
        source = (ROOT / "card_identity_recognition.js").read_text(encoding="utf-8")
        self.assertNotIn("effectiveRegion=String(best.region).toUpperCase()", source)
        self.assertIn("server?.identity_ambiguous===true", source)
        self.assertIn("server?.region_ambiguous===true", source)
        self.assertIn("autoApply:false", source)
        self.assertIn("marketLinkBlocked", source)
        self.assertIn("allowRegionAutofill:true", source)

    def test_saved_and_platform_price_links_require_known_edition(self) -> None:
        source = (ROOT / "grade_market_flow.js").read_text(encoding="utf-8")
        self.assertIn("if(wanted==='UNKNOWN')return '';", source)
        self.assertIn("if(editionCode(region)==='UNKNOWN')", source)
        self.assertIn("판본 확인 후 동일 판본 시세만 연결", source)

    @unittest.skipUnless(__import__("shutil").which("node"), "Node.js is optional on tablet runtime")
    def test_regulation_mark_is_context_not_generation_identity(self) -> None:
        proc = subprocess.run(
            ["node", "verify_pokemon_generation_runtime.js"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertIn("Pokémon generation runtime v320: PASS", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
