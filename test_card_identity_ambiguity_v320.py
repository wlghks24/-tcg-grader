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

    def test_lower_score_parallel_variant_cannot_autoselect_same_card(self) -> None:
        common = {
            "game": "pokemon", "region": "KR", "card_name": "Pikachu",
            "card_number": "025/165",
        }
        normal = {**common, "confidence": 0.995,
                  "market_key": "KR|Pikachu 025/165|normal"}
        parallel = {**common, "confidence": 0.56,
                    "market_key": "KR|Pikachu 025/165|parallel"}
        payload = {
            "game": "pokemon", "region": "KR",
            "image_hash": "0000000000000001",
            "ocr_text": "한국판 Pikachu 025/165",
        }
        with mock.patch.object(identity, "match_learning", return_value=[]), mock.patch.object(
            identity, "match_catalog", return_value=[normal, parallel]
        ):
            result = identity.recognize(payload)
        self.assertTrue(result["variant_ambiguous"])
        self.assertTrue(result["identity_ambiguous"])
        self.assertTrue(result["market_ambiguous"])
        self.assertTrue(result["market_link_blocked"])
        self.assertTrue(result["auto_selection_blocked"])
        self.assertIsNone(result["best"])
        self.assertEqual(2, len(result["candidates"]))

    def test_low_score_different_card_preserves_nonvariant_auto_choice(self) -> None:
        main = self.candidate("KR", name="Pikachu", number="025/165",
                              market_key="KR|Pikachu 025/165|HIT", confidence=0.99)
        unrelated = self.candidate("KR", name="Charizard", number="006/165",
                                   market_key="KR|Charizard 006/165|HIT", confidence=0.54)
        payload = {"game": "pokemon", "region": "KR",
                   "image_hash": "0000000000000001",
                   "ocr_text": "한국판 Pikachu 025/165"}
        with mock.patch.object(identity, "match_learning", return_value=[]), mock.patch.object(
            identity, "match_catalog", return_value=[main, unrelated]
        ):
            result = identity.recognize(payload)
        self.assertFalse(result["variant_ambiguous"])
        self.assertFalse(result["auto_selection_blocked"])
        self.assertEqual(main, result["best"])
        self.assertFalse(result["market_link_blocked"])

    def test_exact_repeat_is_one_candidate_not_a_second_variant(self) -> None:
        main = self.candidate("JP", name="Pikachu", number="025/165",
                              market_key="JP|Pikachu 025/165|HIT", confidence=0.99)
        duplicate = {**main, "confidence": 0.70}
        payload = {"game": "pokemon", "region": "JP",
                   "image_hash": "0000000000000001",
                   "ocr_text": "日本版 Pikachu 025/165"}
        with mock.patch.object(identity, "match_learning", return_value=[]), mock.patch.object(
            identity, "match_catalog", return_value=[main, duplicate]
        ):
            result = identity.recognize(payload)
        self.assertEqual(1, len(result["candidates"]))
        self.assertFalse(result["variant_ambiguous"])
        self.assertFalse(result["auto_selection_blocked"])

    def test_explicit_printing_conflict_requires_confirmation_with_complete_candidates(self) -> None:
        main = self.candidate("KR", name="Pikachu", number="025/165",
                              market_key="KR|025/165|HIT", confidence=0.99)
        alternate = {**main, "printing": "parallel", "confidence": 0.52}
        main["printing"] = "normal"
        decision = identity._candidate_ambiguity([main, alternate], "KR")
        self.assertTrue(decision["variant_ambiguous"])
        self.assertTrue(decision["identity_ambiguous"])

    def test_untrusted_tiny_variant_signal_does_not_block_auto_selection(self) -> None:
        main = self.candidate("KR", market_key="KR|Pikachu|base", confidence=0.99)
        noise = self.candidate("KR", market_key="KR|Pikachu|alt", confidence=0.10)
        decision = identity._candidate_ambiguity([main, noise], "KR")
        self.assertFalse(decision["variant_ambiguous"])
        self.assertFalse(decision["identity_ambiguous"])

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

    def test_v620_reviewed_ocr_scope_is_exact_and_fail_closed(self) -> None:
        import sync_v376_successor_test_support as sync

        path = sync.V620_OCR_PATH
        self.assertEqual(path, "card_identity_recognition.py")
        for historical_source in (
            sync.V377_CANDIDATE, sync.V426_CANDIDATE,
            sync.V599_OFFICIAL_BOX_CANDIDATE,
        ):
            self.assertEqual(
                [], sync.preserve_reviewed_v620_ocr_scope(
                    [path], historical_source,
                ),
            )
        # Explicit historical candidates are never treated as HEAD.
        self.assertEqual(
            [path], sync.preserve_reviewed_v620_ocr_scope(
                [path], sync.V599_OFFICIAL_BOX_CANDIDATE,
                head=sync.V620_OCR_CANDIDATE,
            ),
        )
        # Mutation of the reviewed OCR digest must expose the change to
        # historical sync rather than suppress it.
        with mock.patch.object(sync, "V620_OCR_SHA256", "0" * 64):
            self.assertEqual(
                [path], sync.preserve_reviewed_v620_ocr_scope(
                    [path], sync.V599_OFFICIAL_BOX_CANDIDATE,
                ),
            )
        # A changed main baseline cannot be retroactively attributed to V620.
        with mock.patch.object(sync, "V620_OCR_BASE_SHA256", "0" * 64):
            self.assertEqual(
                [path], sync.preserve_reviewed_v620_ocr_scope(
                    [path], sync.V377_CANDIDATE,
                ),
            )
        # Do not conceal unrelated paths even for a valid reviewed successor.
        self.assertEqual(
            ["main"], sync.preserve_reviewed_v620_ocr_scope(
                ["main"], sync.V599_OFFICIAL_BOX_CANDIDATE,
            ),
        )

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
        self.assertIn("Pokémon generation runtime v328: PASS", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
