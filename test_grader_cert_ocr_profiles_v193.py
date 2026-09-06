#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import library_slab_corpus as corpus
import manual_graded_photo_registration as manual


class GraderCertOcrV193Tests(unittest.TestCase):
    def _ocr_case(
        self, company: str, generic_text: str, targeted_text: str,
        expected_cert: str, expected_pass: str,
    ):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / f"{company.lower()}.png"
            Image.new("RGB", (900, 1500), "white").save(path)
            calls = []

            def fake_run(_image, psm, whitelist=None):
                calls.append((psm, whitelist))
                if whitelist is None:
                    return generic_text, None
                return targeted_text, None

            with patch.object(corpus, "_run_tesseract", side_effect=fake_run):
                text, error, diagnostics = corpus.ocr_label(path, profile="fast")

        self.assertIsNone(error)
        self.assertEqual(expected_cert, corpus.normalize_cert(company, text))
        self.assertTrue(diagnostics["cert_resolved"])
        self.assertIn(expected_pass, diagnostics["targeted_passes"])
        self.assertGreaterEqual(len(calls), 14)
        return text, diagnostics

    def test_psa_targeted_profile_repairs_numericish_confusions(self):
        text, diagnostics = self._ocr_case(
            "PSA", "PSA GEM MT 10", "871O5158",
            "87105158", "psa_top_right_numericish_psm7",
        )
        self.assertIn("PSA CERT 87105158", text)
        self.assertTrue(diagnostics["company_resolved"])

    def test_bgs_existing_leading_zero_recovery_is_preserved(self):
        text, _ = self._ocr_case(
            "BGS",
            "BECKETT CENTERING 9.5 CORNERS 10 EDGES 10 SURFACE 10 PRISTINE 10",
            "0017492225",
            "0017492225",
            "bgs_top_right_digits_psm6",
        )
        self.assertIn("BECKETT CERT 0017492225", text)

    def test_cgc_targeted_profile_is_preserved(self):
        text, _ = self._ocr_case(
            "CGC", "CGC CERTIFIED GUARANTY GEM MINT 10", "6195763028",
            "6195763028", "cgc_center_label_digits_psm6",
        )
        self.assertIn("CGC CERT 6195763028", text)

    def test_tag_preserves_letter_prefix_and_repairs_tail_confusion(self):
        text, diagnostics = self._ocr_case(
            "TAG", "TAG GRADING GEM MINT 10", "X949I558",
            "X9491558", "tag_cert_left_of_qr_psm7",
        )
        self.assertIn("TAG CERT X9491558", text)
        self.assertEqual("X9491558", corpus.normalize_cert("TAG", "CERT X949I558"))
        self.assertTrue(diagnostics["company_resolved"])

    def test_brg_targeted_profile_preserves_seven_digits_and_leading_zero(self):
        text, _ = self._ocr_case(
            "BRG", "BREAK GRADING GRADE 10", "O175992",
            "0175992", "brg_top_right_numericish_psm7",
        )
        self.assertIn("BRG CERT 0175992", text)
        self.assertIsNone(corpus.normalize_cert("BRG", "2024 001"))

    def test_manual_company_hint_selects_profile_but_is_not_visual_company_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hint.png"
            Image.new("RGB", (900, 1500), "white").save(path)

            def fake_run(_image, _psm, whitelist=None):
                if whitelist is None:
                    return "GEM MT 10", None
                return "87105158", None

            with patch.object(corpus, "_run_tesseract", side_effect=fake_run):
                text, error, diagnostics = corpus.ocr_label(
                    path, profile="fast", fallback_company="PSA",
                )

        self.assertIsNone(error)
        self.assertIn("CERT 87105158", text)
        self.assertNotIn("PSA CERT 87105158", text)
        self.assertFalse(diagnostics["company_resolved"])
        self.assertTrue(diagnostics["cert_resolved"])
        self.assertTrue(diagnostics["fallback_company_used_for_parsing"])

    def test_manual_row_passes_selected_grader_as_hint_only(self):
        row = {
            "image_path": "GRADE_TRAINING_INBOX/drop/pokemon/example.png",
            "image_sha256": "a" * 64,
            "company": "TAG",
        }
        with patch.object(
            manual, "_ocr_image",
            return_value=("CERT X9491558", None, {}, {
                "company": "", "grade": None, "certification_id": "X9491558",
            }),
        ) as ocr:
            text, error, diagnostics, evidence, cache_hit = manual._ocr_for_row(row)
        self.assertFalse(cache_hit)
        self.assertEqual("X9491558", evidence["certification_id"])
        self.assertEqual("", evidence["company"])
        self.assertEqual("TAG", ocr.call_args.kwargs["fallback_company"])


if __name__ == "__main__":
    unittest.main()
