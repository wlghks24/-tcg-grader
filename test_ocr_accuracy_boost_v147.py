from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

import ocr_accuracy_boost_v147 as boost


class OcrAccuracyBoostV147Tests(unittest.TestCase):
    def test_fuzzy_psa_and_common_cert_confusions(self):
        text = 'P5A GEM MT I0 CERT 12O4S678'
        company = boost.detect_company(text)
        self.assertEqual(company, 'PSA')
        self.assertEqual(boost.normalize_cert(company, text), '12045678')
        self.assertEqual(boost.normalize_grade(text, company), 10.0)

    def test_fallback_company_guides_cert_length_without_becoming_visual_company(self):
        company, cert, grade = boost.fields_from_text('GEM MT I0 CERT 12O45678', fallback_company='PSA')
        self.assertIsNone(company)
        self.assertEqual(cert, '12045678')
        self.assertEqual(grade, 10.0)

    def test_arbitrary_word_is_not_rewritten_into_cert(self):
        self.assertIsNone(boost.normalize_cert('PSA', 'CERTIFICATION SAMPLE LABEL'))

    def test_accuracy_ocr_stops_after_complete_first_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'slab.jpg'
            Image.new('RGB', (800, 1200), 'white').save(path)
            with mock.patch.object(
                boost,
                '_run_tesseract',
                return_value=('PSA GEM MT 10 CERT 12345678', None),
            ) as run:
                text, error, diagnostics = boost.ocr_label(path, profile='accuracy')
        self.assertIsNone(error)
        self.assertIn('12345678', text)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(diagnostics['pass_count'], 1)
        self.assertEqual(diagnostics['identity_score'], 100)

    def test_accuracy_ocr_uses_fallback_pass_when_cert_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'slab.jpg'
            Image.new('RGB', (800, 1200), 'white').save(path)
            outputs = [
                ('PSA GEM MT 10', None),
                ('PSA GEM MT 10 CERT 12345678', None),
            ]
            with mock.patch.object(boost, '_run_tesseract', side_effect=outputs) as run:
                text, error, diagnostics = boost.ocr_label(path, profile='accuracy')
        self.assertIsNone(error)
        self.assertIn('12345678', text)
        self.assertEqual(run.call_count, 2)
        self.assertTrue(diagnostics['cert_resolved'])


if __name__ == '__main__':
    unittest.main()
