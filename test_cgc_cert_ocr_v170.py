#!/usr/bin/env python3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import library_slab_corpus as corpus
from graded_photo_evidence import extract_label_evidence


class CgcCertificateOcrV170Tests(unittest.TestCase):
    def test_fast_profile_recovers_cgc_certificate_from_label_band(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cgc.png"
            Image.new("RGB", (852, 1536), "white").save(path)
            calls = []

            def fake_run(_image, psm, whitelist=None):
                calls.append((psm, whitelist))
                if whitelist:
                    # Simulates a CGC front label where the generic pass reads
                    # company/grade but skips the small 10-digit serial.
                    return "2024 001 6195763028", None
                return (
                    "CGC CERTIFIED GUARANTY COMPANY Monkey D. Luffy "
                    "One Piece 2024 Tournament Promos P-001 "
                    "Online Regionals Participant GEM MINT 10",
                    None,
                )

            with patch.object(corpus, "_run_tesseract", side_effect=fake_run):
                text, error, diagnostics = corpus.ocr_label(path, profile="fast")

        self.assertIsNone(error)
        self.assertIn("CGC CERT 6195763028", text)
        self.assertTrue(diagnostics["company_resolved"])
        self.assertTrue(diagnostics["cert_resolved"])
        self.assertTrue(diagnostics["grade_resolved"])
        self.assertIn("cgc_center_label_digits_psm6", diagnostics["passes_used"])
        self.assertIn((6, "0123456789"), calls)

        evidence = extract_label_evidence(text)
        self.assertEqual("CGC", evidence["company"])
        self.assertEqual("6195763028", evidence["certification_id"])
        self.assertEqual(10.0, evidence["grade"])

    def test_cgc_normalization_prefers_ten_digit_serial_over_card_numbers(self):
        self.assertEqual(
            "6195763028",
            corpus.normalize_cert("CGC", "2024 P-001 6195763028"),
        )

    def test_standalone_cgc_gem_mint_grade_is_recognized(self):
        evidence = extract_label_evidence(
            "CGC CERTIFIED GUARANTY COMPANY GEM MINT 10 CERT 6195763028"
        )
        self.assertEqual("CGC", evidence["company"])
        self.assertEqual(10.0, evidence["grade"])
        self.assertEqual("6195763028", evidence["certification_id"])


if __name__ == "__main__":
    unittest.main()
