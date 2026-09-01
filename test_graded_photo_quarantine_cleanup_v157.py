import unittest

from graded_photo_multi_source import _review_and_prune_quarantine_v157


class QuarantineCleanupV157Tests(unittest.TestCase):
    def row(self, **changes):
        value = {
            'url': 'https://example.com/item/1',
            'image_url': 'https://img.example.com/1.jpg',
            'image_validated': True,
            'image_probe_status': 'validated',
            'ocr_label_text': 'PSA GEM MT 10',
            'company': 'PSA',
            'grade': 10.0,
            'certification_id': '',
            'official_result': False,
            'status': 'quarantine_candidate',
            'evidence_conflicts': [],
        }
        value.update(changes)
        return value

    def test_new_unresolved_candidate_gets_one_grace_pass(self):
        current = self.row()
        kept, stats, audit = _review_and_prune_quarantine_v157([current], [])
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]['quarantine_review_count'], 1)
        self.assertEqual(stats['pruned'], 0)
        self.assertEqual(audit, [])

    def test_old_ocr_readable_candidate_without_cert_is_pruned_after_recheck(self):
        previous = self.row()
        current = self.row()
        kept, stats, audit = _review_and_prune_quarantine_v157([current], [previous])
        self.assertEqual(kept, [])
        self.assertEqual(stats['pruned'], 1)
        self.assertEqual(audit[0]['reason'], 'certification_unresolved')

    def test_temporary_official_block_is_retained(self):
        previous = self.row(certification_id='12345678')
        current = self.row(certification_id='12345678', official_lookup_status='HTTPError')
        kept, stats, audit = _review_and_prune_quarantine_v157([current], [previous])
        self.assertEqual(len(kept), 1)
        self.assertEqual(stats['retained_retryable'], 1)
        self.assertEqual(audit, [])

    def test_verified_reference_is_never_pruned(self):
        previous = self.row(certification_id='12345678')
        current = self.row(certification_id='12345678', official_result=True, status='verified_reference')
        kept, stats, audit = _review_and_prune_quarantine_v157([current], [previous])
        self.assertEqual(len(kept), 1)
        self.assertNotIn('quarantine_review_count', kept[0])
        self.assertEqual(audit, [])

    def test_repeat_official_not_found_is_pruned(self):
        previous = self.row(certification_id='12345678')
        current = self.row(certification_id='12345678', official_lookup_status='공식 페이지에서 해당 인증번호를 찾지 못했습니다.')
        kept, stats, audit = _review_and_prune_quarantine_v157([current], [previous])
        self.assertEqual(kept, [])
        self.assertEqual(audit[0]['reason'], 'official_not_found_or_mismatch')

    def test_repeat_conflicting_label_is_pruned(self):
        previous = self.row(evidence_conflicts=['cross_source_grade_conflict'])
        current = self.row(evidence_conflicts=['cross_source_grade_conflict'])
        kept, stats, audit = _review_and_prune_quarantine_v157([current], [previous])
        self.assertEqual(kept, [])
        self.assertEqual(audit[0]['reason'], 'evidence_conflict')


if __name__ == '__main__':
    unittest.main()
