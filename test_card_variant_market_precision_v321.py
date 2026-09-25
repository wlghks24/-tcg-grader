from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

import card_identity_recognition as identity

ROOT = Path(__file__).resolve().parent


class CardVariantMarketPrecisionV321Tests(unittest.TestCase):
    def row(self, variant: str, *, finish: str = "UNKNOWN", rarity: str = "UNKNOWN", set_code: str = "OP13", confidence: float = 0.997) -> dict:
        return {
            "market_key": f"JP|Ace {variant}|HIT",
            "region": "JP",
            "game": "onepiece",
            "card_name": "Portgas D. Ace",
            "card_number": "OP13-119",
            "set_code": set_code,
            "variant": variant,
            "finish": finish,
            "rarity": rarity,
            "card_family": "BOOSTER",
            "confidence": confidence,
            "matched_by": "card_number_exact+card_name",
        }

    def test_set_code_and_family_are_game_specific(self) -> None:
        self.assertEqual("SV8A", identity.infer_set_code("SV8A 217/187", "pokemon"))
        self.assertEqual("SM1M", identity.infer_set_code("SM1M 065/060", "pokemon"))
        self.assertEqual("OP13", identity.infer_set_code("OP13-119", "onepiece"))
        self.assertEqual("CP", identity.infer_set_code("CP-001", "naruto"))
        self.assertEqual("BOOSTER", identity.infer_card_family("onepiece", "OP13"))
        self.assertEqual("STARTER", identity.infer_card_family("onepiece", "ST01"))
        self.assertEqual("EXTRA_BOOSTER", identity.infer_card_family("onepiece", "EB03"))
        self.assertEqual("PREMIUM_BOOSTER", identity.infer_card_family("onepiece", "PRB02"))
        self.assertEqual("PROMO", identity.infer_card_family("naruto", "CP"))

    def test_variant_finish_and_rarity_are_separate_axes(self) -> None:
        meta = identity.classify_identity_metadata(
            "Portgas D. Ace MANGA PARALLEL SEC HOLO OP13-119", "onepiece", "OP13-119"
        )
        self.assertEqual("MANGA", meta["variant"])
        self.assertEqual("HOLO", meta["finish"])
        self.assertEqual("SEC", meta["rarity"])
        self.assertEqual("OP13", meta["set_code"])
        self.assertEqual("BOOSTER", meta["card_family"])
        self.assertEqual("REVERSE_HOLO", identity.infer_finish("reverse holofoil"))
        self.assertEqual("FULL_ART", identity.infer_variant("Lillie Full Art"))
        self.assertEqual("PROMO", identity.infer_variant("Gen Con 2026 Promo"))
        self.assertEqual("UNKNOWN", identity.infer_variant("parallelism worker policy"))

    def test_catalog_matching_rejects_wrong_variant_when_variant_is_explicit(self) -> None:
        manga = self.row("MANGA")
        parallel = self.row("PARALLEL", confidence=0.996)
        with mock.patch.object(identity, "catalog", return_value=[manga, parallel]):
            hits = identity.match_catalog(
                "Portgas D. Ace OP13-119 manga parallel SEC", "onepiece", region="JP"
            )
        self.assertTrue(hits)
        self.assertEqual("MANGA", hits[0]["variant"])
        self.assertTrue(all(row["variant"] != "PARALLEL" for row in hits))

    def test_same_card_number_different_variants_fail_closed_without_variant_evidence(self) -> None:
        manga = self.row("MANGA")
        parallel = self.row("PARALLEL", confidence=0.996)
        payload = {
            "game": "onepiece",
            "region": "JP",
            "ocr_text": "Portgas D. Ace OP13-119",
            "image_hash": "0000000000000001",
        }
        with mock.patch.object(identity, "match_learning", return_value=[]), mock.patch.object(
            identity, "match_catalog", return_value=[manga, parallel]
        ):
            result = identity.recognize(payload)
        self.assertTrue(result["identity_ambiguous"])
        self.assertTrue(result["metadata_ambiguous"])
        self.assertTrue(result["variant_ambiguous"])
        self.assertTrue(result["market_link_blocked"])
        self.assertIsNone(result["best"])

    def test_browser_and_market_flow_track_variant_metadata(self) -> None:
        page = (ROOT / "index.html").read_text(encoding="utf-8")
        identity_js = (ROOT / "card_identity_recognition.js").read_text(encoding="utf-8")
        market_js = (ROOT / "grade_market_flow.js").read_text(encoding="utf-8")
        auto_market = (ROOT / "auto_market_center.js").read_text(encoding="utf-8")
        validation = (ROOT / "auto_validation_flow.js").read_text(encoding="utf-8")
        for token in (
            'id="identitySetCode"', 'id="identityVariant"', 'id="identityFinish"',
            'id="identityRarity"', 'id="identityClassification"',
        ):
            self.assertIn(token, page)
        for token in (
            "TCGCardIdentityMeta", "version:'v321'", "identitySetCode", "identityVariant",
            "identityFinish", "identityRarity", "card_family",
        ):
            self.assertIn(token, identity_js)
        for token in (
            "currentIdentityMeta", "marketMetadataCompatible", "identityVariant",
            "identityFinish", "identityRarity", "identitySetCode",
        ):
            self.assertIn(token, market_js)
        self.assertIn("identityVariant", auto_market)
        self.assertIn("identityFinish", auto_market)
        self.assertIn("identityRarity", auto_market)
        self.assertIn("identitySetCode", validation)
        self.assertIn("identityVariant", validation)


if __name__ == "__main__":
    unittest.main(verbosity=2)
