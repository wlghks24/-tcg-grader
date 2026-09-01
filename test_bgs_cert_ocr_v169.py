#!/usr/bin/env python3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import library_slab_corpus as corpus
from graded_photo_evidence import extract_label_evidence


class BgsCertificateOcrV169Tests(unittest.TestCase):
    def test_fast_profile_recovers_leading_zero_bgs_certificate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bgs.png"
            Image.new("RGB", (930, 1536), "white").save(path)

            calls = []

            def fake_run(_image, psm, whitelist=None):
                calls.append((psm, whitelist))
                if whitelist:
                    # Mirrors the Android failure mode: subgrade digits plus a
                    # small leading-zero serial at the far right of the label.
                    return "1 1 0 2 10 10 0017492225", None
                return (
                    "2011 ONE PIECE MORINAGA WAFER CHOCO VOL. 1 "
                    "#005 SANJI DAIKAIZOKU STYLE CARD BECKETT "
                    "CENTERING 9.5 CORNERS 10 EDGES 10 SURFACE 10 10 PRISTINE",
                    None,
                )

            with patch.object(corpus, "_run_tesseract", side_effect=fake_run):
                text, error, diagnostics = corpus.ocr_label(path, profile="fast")

        self.assertIsNone(error)
        self.assertIn("BECKETT CERT 0017492225", text)
        self.assertTrue(diagnostics["company_resolved"])
        self.assertTrue(diagnostics["cert_resolved"])
        self.assertTrue(diagnostics["grade_resolved"])
        self.assertIn("bgs_top_right_digits_psm6", diagnostics["passes_used"])
        self.assertIn((6, "0123456789"), calls)

        evidence = extract_label_evidence(text)
        self.assertEqual("BGS", evidence["company"])
        self.assertEqual("0017492225", evidence["certification_id"])
        self.assertEqual(10.0, evidence["grade"])

    def test_bgs_certificate_normalization_preserves_leading_zeroes(self):
        self.assertEqual("0017492225", corpus.normalize_cert("BGS", "0017492225"))

    def test_bgs_heuristic_requires_multiple_subgrade_markers(self):
        self.assertTrue(corpus._looks_like_bgs_label(
            "PRISTINE CENTERING 9.5 CORNERS 10 EDGES 10 SURFACE 10"
        ))
        self.assertFalse(corpus._looks_like_bgs_label("PRISTINE 10"))


if __name__ == "__main__":
    unittest.main()
