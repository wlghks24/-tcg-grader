from __future__ import annotations

import unittest
from unittest import mock

import ocr_front_back_fallback_v148 as fallback


class OcrFrontBackFallbackV148Tests(unittest.TestCase):
    def test_back_recovers_missing_cert_but_keeps_front_grade(self):
        row = {
            'image_path': 'front.jpg',
            'back_image_path': 'back.jpg',
            'company': 'PSA',
        }
        front_result = (
            'PSA GEM MT 10', None,
            {'engine': 'front-test'},
            {'company': 'PSA', 'grade': 10.0, 'certification_id': ''},
            False,
        )
        with mock.patch.object(fallback, '_ORIGINAL_OCR_FOR_ROW', return_value=front_result), \
             mock.patch.object(fallback.boost, 'ocr_label', return_value=(
                 'BACK CERT 12345678 GRADE 7', None,
                 {'engine': 'back-test', 'pass_count': 2},
             )), \
             mock.patch.object(fallback.boost, 'fields_from_text', return_value=('PSA', '12345678', 7.0)):
            text, error, diagnostics, evidence, cache_hit = fallback._ocr_for_row_front_back(row)
        self.assertFalse(cache_hit)
        self.assertIsNone(error)
        self.assertEqual(evidence['company'], 'PSA')
        self.assertEqual(evidence['certification_id'], '12345678')
        self.assertEqual(evidence['grade'], 10.0)
        self.assertTrue(diagnostics['back_ocr_used'])
        self.assertEqual(diagnostics['back_grade_hint'], 7.0)
        self.assertIn('BACK:', text)

    def test_complete_front_does_not_spend_back_ocr(self):
        row = {'back_image_path': 'back.jpg'}
        front_result = (
            'PSA GEM MT 10 CERT 12345678', None, {},
            {'company': 'PSA', 'grade': 10.0, 'certification_id': '12345678'},
            False,
        )
        with mock.patch.object(fallback, '_ORIGINAL_OCR_FOR_ROW', return_value=front_result), \
             mock.patch.object(fallback.boost, 'ocr_label') as back_ocr:
            _, _, diagnostics, evidence, _ = fallback._ocr_for_row_front_back(row)
        back_ocr.assert_not_called()
        self.assertFalse(diagnostics['back_ocr_used'])
        self.assertEqual(evidence['certification_id'], '12345678')

    def test_missing_back_is_safe(self):
        row = {}
        front_result = (
            'PSA GEM MT 10', None, {},
            {'company': 'PSA', 'grade': 10.0, 'certification_id': ''},
            False,
        )
        with mock.patch.object(fallback, '_ORIGINAL_OCR_FOR_ROW', return_value=front_result):
            _, _, diagnostics, evidence, _ = fallback._ocr_for_row_front_back(row)
        self.assertFalse(diagnostics['back_ocr_used'])
        self.assertEqual(diagnostics['back_ocr_reason'], 'back_image_not_available')
        self.assertEqual(evidence['grade'], 10.0)


if __name__ == '__main__':
    unittest.main()
