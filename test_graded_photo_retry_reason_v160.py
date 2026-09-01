import unittest

import graded_photo_retry_reason_v160 as rr


class RetryReasonV160Tests(unittest.TestCase):
    def test_429_and_missing_identity_are_explained(self):
        rows = [{
            'status': 'quarantine_candidate',
            'official_result': False,
            'image_probe_status': 'retryable_failed',
            'image_revalidation_retryable': True,
            'image_probe_error': 'HTTPError 429 rate limited',
            'company': 'PSA',
            'game': 'onepiece',
            'certification_id': '',
            'grade': None,
            'ocr_label_text': '',
        }]
        result = rr.summarize_rows(rows)
        labels = {item['label'] for item in result['reason_counts']}
        self.assertIn('사이트 429/요청제한', labels)
        self.assertIn('인증번호 미확인', labels)
        self.assertIn('등급 미확인', labels)
        self.assertIn('OCR 판독 부족', labels)
        self.assertEqual(result['retryable_count'], 1)

    def test_verified_reference_is_not_reported_as_retryable(self):
        rows = [{
            'status': 'verified_reference',
            'official_result': True,
            'company': 'PSA',
            'certification_id': '160600294',
            'grade': 10,
            'ocr_label_text': 'PSA GEM MT 10 160600294',
        }]
        result = rr.summarize_rows(rows)
        self.assertEqual(result['retryable_count'], 0)
        self.assertEqual(result['reason_counts'], [])
        self.assertEqual(result['details'], [])

    def test_cooldown_is_shown_without_duplicate_generic_official_reason(self):
        rows = [{
            'status': 'quarantine_candidate',
            'official_result': False,
            'verification_state': 'deferred_by_cooldown',
            'company': 'BGS',
            'certification_id': '0012345678',
            'grade': 9.5,
            'ocr_label_text': 'BGS 9.5 0012345678',
        }]
        result = rr.summarize_rows(rows)
        labels = [item['label'] for item in result['reason_counts']]
        self.assertIn('등급사 조회 쿨다운', labels)
        self.assertNotIn('공식검증 미완료', labels)


if __name__ == '__main__':
    unittest.main()
