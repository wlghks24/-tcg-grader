#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

import card_identity_recognition as identity
import manual_official_proof as proof


class OcrSelfrefineV15Tests(unittest.TestCase):
    def _catalog_context(self, rows):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        market = root / "market_prices.json"
        reference = root / "card_identity_reference_catalog.json"
        entries = {}
        for index, row in enumerate(rows):
            region = row.get("region", "KR")
            key = f"{region}|card-{index}|HIT"
            entries[key] = {
                "game": row["game"],
                "card_name": row["card_name"],
                "card_number": row["card_number"],
                "product_name": row.get("product_name", ""),
            }
        market.write_text(json.dumps({"entries": entries}, ensure_ascii=False), encoding="utf-8")
        reference.write_text('{"cards":[]}', encoding="utf-8")
        stack = mock.patch.multiple(
            identity,
            MARKET=market,
            REFERENCE=reference,
            _CATALOG_CACHE_SIGNATURE=None,
            _CATALOG_CACHE_ROWS=[],
        )
        return temp, stack

    def test_card_number_ocr_confusions_are_repaired_only_in_numeric_segments(self):
        self.assertIn("OP13-007", identity.extract_numbers("OP13-O07"))
        self.assertIn("065/060", identity.extract_numbers("O65/O6O"))
        self.assertEqual(identity.normalize_number("P-001"), "P-001")

    def test_ambiguous_fraction_number_is_not_scored_like_exact_identity(self):
        temp, patcher = self._catalog_context([
            {"game": "pokemon", "card_name": "Alpha", "card_number": "SV1-001/100"},
            {"game": "pokemon", "card_name": "Beta", "card_number": "SV2-001/100"},
        ])
        try:
            with patcher:
                hits = identity.match_catalog("001/100", "pokemon")
            self.assertGreaterEqual(len(hits), 2)
            self.assertTrue(all("ambiguous" in row["matched_by"] for row in hits[:2]))
            self.assertLess(max(row["confidence"] for row in hits[:2]), 0.90)
        finally:
            temp.cleanup()

    def test_region_aware_multilingual_tesseract_selection(self):
        with mock.patch.object(identity, "_tesseract_languages", return_value=frozenset({"eng", "kor", "jpn"})):
            self.assertEqual(identity._ocr_language("KR"), "eng+kor")
            self.assertEqual(identity._ocr_language("JP"), "eng+jpn")
            self.assertEqual(identity._ocr_language("US"), "eng")
            fallback = identity._ocr_language("UNKNOWN", multilingual_fallback=True)
        self.assertEqual(fallback, "eng+kor+jpn")

    def test_sufficient_browser_ocr_skips_tesseract_and_even_image_decode(self):
        temp, patcher = self._catalog_context([
            {"game": "onepiece", "card_name": "Monkey D. Luffy", "card_number": "OP13-007"},
        ])
        try:
            with patcher, mock.patch.object(identity, "_tesseract_binary") as binary:
                text, error, diag = identity.ocr_image_detailed(
                    b"not-an-image",
                    game="onepiece",
                    region="JP",
                    seed_text="MONKEY D LUFFY OP13-007",
                )
            binary.assert_not_called()
            self.assertEqual(text, "")
            self.assertIsNone(error)
            self.assertTrue(diag["seed_text_sufficient"])
            self.assertEqual(diag["pass_count"], 0)
        finally:
            temp.cleanup()

    def test_server_ocr_stops_after_first_high_confidence_pass(self):
        temp, patcher = self._catalog_context([
            {"game": "onepiece", "card_name": "Monkey D. Luffy", "card_number": "OP13-007"},
        ])
        buffer = io.BytesIO()
        Image.new("RGB", (900, 1300), "white").save(buffer, format="PNG")
        try:
            with patcher, \
                 mock.patch.object(identity, "_tesseract_binary", return_value="/usr/bin/tesseract"), \
                 mock.patch.object(identity, "_tesseract_languages", return_value=frozenset({"eng"})), \
                 mock.patch.object(identity, "_run_card_tesseract", return_value=("MONKEY D LUFFY OP13-007", None)) as run:
                text, error, diag = identity.ocr_image_detailed(
                    buffer.getvalue(), game="onepiece", region="US"
                )
            self.assertIsNone(error)
            self.assertIn("OP13-007", text)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(diag["pass_count"], 1)
            self.assertTrue(diag["early_stop"])
        finally:
            temp.cleanup()

    def test_oversized_pixel_dimensions_are_rejected_before_expensive_processing(self):
        fake = mock.Mock()
        fake.size = (8000, 8000)
        with self.assertRaises(ValueError):
            identity._validate_image_dimensions(fake)

    def test_clear_official_page_base_ocr_skips_extra_tesseract_passes(self):
        base_text = "PSA CERT 160600294 GEM MT 10"
        evidence = {"company": "PSA", "certification_id": "160600294", "grade": 10.0}
        with mock.patch.object(proof.manual_photo, "_ocr_image", return_value=(base_text, None, {}, evidence)), \
             mock.patch.object(proof, "_tesseract_page_pass") as extra:
            text, error, diag, out_evidence = proof._ocr_official_page(
                Path("unused.png"),
                expected_company="PSA",
                expected_cert="160600294",
                expected_grade=10.0,
            )
        extra.assert_not_called()
        self.assertIsNone(error)
        self.assertTrue(diag["base_ocr_sufficient"])
        self.assertEqual(diag["official_page_pass_count"], 0)
        self.assertEqual(out_evidence["certification_id"], "160600294")
        self.assertIn("GEM MT 10", text)

    def test_official_page_stops_after_first_crop_when_missing_cert_is_recovered(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "proof.png"
            Image.new("RGB", (1080, 1920), "white").save(path)
            base_text = "PSA GEM MT 10"
            evidence = {"company": "PSA", "certification_id": "", "grade": 10.0}
            with mock.patch.object(proof.manual_photo, "_ocr_image", return_value=(base_text, None, {}, evidence)), \
                 mock.patch.object(proof, "_tesseract_page_pass", return_value=("PSA CERT 160600294 GEM MT 10", None)) as run:
                _, error, diag, _ = proof._ocr_official_page(
                    path,
                    expected_company="PSA",
                    expected_cert="160600294",
                    expected_grade=10.0,
                )
        self.assertIsNone(error)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(diag["official_page_pass_count"], 1)
        self.assertTrue(diag["official_page_early_stop"])

    def test_browser_ocr_front_image_is_decoded_once_for_hash_and_upload(self):
        source = (Path(__file__).resolve().parent / "card_identity_recognition.js").read_text(encoding="utf-8")
        self.assertIn("async function imageArtifacts(file)", source)
        self.assertEqual(source.count("window.loadCardImage(file)"), 1)
        self.assertNotIn("async function imageHash(file)", source)
        self.assertNotIn("async function imageData(file)", source)
        self.assertIn("v15-ocr-selfrefine", source)


if __name__ == "__main__":
    unittest.main()
