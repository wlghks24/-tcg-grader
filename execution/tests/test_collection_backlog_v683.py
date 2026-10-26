import unittest
from unittest.mock import patch
from pathlib import Path
from execution.tablet_collection_backlog_v683 import build_backlog


def inputs():
    return ({'ok': True, 'version': 46, 'gap_queue': [], 'summary': {}},
            {'schema': 'tcg-tablet-learning-advisor/v676', 'mode': 'READ_ONLY_NO_TRAINING',
             'models': {'query': {'labels_missing': 994, 'positive_missing': 94, 'negative_missing': 100}},
             'image_training': {'requires_verified_raw_photos': True}},
            {'supported_sources': [{'game_id': 'pokemon', 'region': 'JP', 'source': 'TCGdex'}]})


class BacklogTests(unittest.TestCase):
    def test_missing_sources_are_distinct_from_download_success(self):
        result = build_backlog(*inputs())
        gaps = [r for r in result['tasks'] if r['priority'] == 1]
        self.assertEqual(len(gaps), 14)
        self.assertNotIn(('pokemon', 'JP'), [(r['game_id'], r['region']) for r in gaps])
        self.assertFalse(result['source_wiring_is_download_success'])
        self.assertFalse(result['product_source_coverage_verified'])

    def test_card_and_box_gaps_do_not_merge_or_duplicate(self):
        c, l, s = inputs()
        row = {'direction': 'CATALOG_NEEDS_IMAGE', 'game_id': 'pokemon', 'region': 'JP',
               'kind': 'CARD', 'source_record_id': 'a' * 32}
        c['gap_queue'] = [row, dict(row), {**row, 'kind': 'BOX'}]
        result = build_backlog(c, l, s)
        self.assertEqual(result['observed_image_gap_count'], 2)
        self.assertEqual([r['kind'] for r in result['tasks'] if r['priority'] == 2], ['BOX', 'CARD'])

    def test_unknown_is_not_zero_or_permission_to_train(self):
        r = build_backlog(None, None, None)
        self.assertIsNone(r['observed_image_gap_count'])
        self.assertEqual(r['status'], 'PARTIAL_EVIDENCE')
        self.assertTrue(all(t.get('labels_missing') is None for t in r['tasks'] if t.get('model') in ('query', 'job')))
        self.assertFalse(r['training_started'])
        self.assertFalse(r['new_scheduler_installed'])

    def test_label_shortage_and_photo_evidence_are_separate(self):
        r = build_backlog(*inputs())
        tasks = {t['model']: t for t in r['tasks'] if 'model' in t}
        self.assertEqual(tasks['query']['labels_missing'], 994)
        self.assertEqual(tasks['image']['reason'], 'REVIEWED_RAW_PHOTOS_REQUIRED')
        self.assertFalse(r['physical_tablet_verified'])

    def test_partial_and_malformed_queues_remain_partial(self):
        c, l, s = inputs()
        c.update(gap_queue=[None], summary={'queue_truncated': True})
        r = build_backlog(c, l, s)
        self.assertIn('MALFORMED_CATALOG_GAP', r['issues'])
        self.assertIn('CATALOG_COVERAGE_INCOMPLETE', r['issues'])
        self.assertEqual(r['status'], 'PARTIAL_EVIDENCE')

    def test_absent_storage_does_not_initialize_image_folders(self):
        from execution.tablet_collection_backlog_v683 import snapshot
        with patch.object(Path, 'is_dir', return_value=False), \
             patch.object(Path, 'mkdir', side_effect=AssertionError('must not create storage')), \
             patch('execution.tablet_catalog_bridge.build_report', side_effect=AssertionError('must not initialize')):
            result = snapshot()
        self.assertIn('CATALOG_GAPS_UNVERIFIED', result['issues'])

    def test_oversized_queue_and_malformed_summary_are_not_success(self):
        c, l, s = inputs()
        c['gap_queue'] = [None] * 3001
        self.assertIsNone(build_backlog(c, l, s)['observed_image_gap_count'])
        c.update(gap_queue=[], summary=None)
        self.assertIn('CATALOG_SUMMARY_UNVERIFIED', build_backlog(c, l, s)['issues'])

    def test_boolean_label_counts_are_unknown(self):
        c, l, s = inputs()
        l['models']['query']['labels_missing'] = True
        r = build_backlog(c, l, s)
        self.assertIsNone(next(t for t in r['tasks'] if t.get('model') == 'query')['labels_missing'])


if __name__ == '__main__':
    unittest.main()
