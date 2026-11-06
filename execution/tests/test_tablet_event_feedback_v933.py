"""Offline V933: learn safe scan health, keep all 79 targets and 403/429 gates."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from execution import tablet_event_coverage_v896 as coverage
from execution import tablet_event_kr_supplement_v932 as kr
from execution import tablet_event_feedback_v933 as feedback
from execution import tablet_event_matrix_v931 as matrix
from tcg_game_registry import load_registry

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 6, 0, 0, tzinfo=timezone.utc)


class EventFeedbackV933Tests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / 'tcg_game_registry.json').write_bytes(
            (ROOT / 'tcg_game_registry.json').read_bytes())
        (self.root / 'promo_events.json').write_text(
            '{"items":[],"archive_items":[]}', encoding='utf-8')
        self.registry = load_registry(self.root)
        self.original = coverage.cells
        while (getattr(self.original, '_tcg_feedback_v933', False) or
               getattr(self.original, '_tcg_kr_v932', False)):
            self.original = self.original.__wrapped__

    def collector(self):
        fake = SimpleNamespace(cells=self.original)
        self.assertTrue(kr.install(fake))
        self.assertTrue(feedback.install(fake, self.root))
        self.assertFalse(feedback.install(fake, self.root))
        self.assertEqual(55, len(self.original(self.registry)))
        self.assertEqual(79, len(fake.cells(self.registry)))
        return fake

    def test_learning_priority_does_not_confuse_unsearched_with_failed_or_verified(self):
        original = kr.supplement_cells(self.registry, self.original)
        by = {cell['key']: cell for cell in original}
        keys = ['gundam/JP', 'gundam/KR', 'gundam/US',
                'pokemon/JP', 'pokemon/KR']
        items = [by[k] for k in keys]
        history = {
            'gundam/JP': {'attempted_at': NOW.isoformat(), 'requests': 2, 'successes': 0, 'results': 0},
            'gundam/US': {'attempted_at': NOW.isoformat(), 'requests': 2, 'successes': 1, 'results': 0},
            'pokemon/JP': {'attempted_at': NOW.isoformat(), 'requests': 2, 'successes': 2, 'results': 0},
            'pokemon/KR': {'attempted_at': NOW.isoformat(), 'requests': 2, 'successes': 2, 'results': 3},
        }
        order = feedback.ranked_cells(items, history)
        self.assertEqual(keys[1], order[0]['key'])
        self.assertEqual(keys[0], order[1]['key'])
        self.assertEqual(keys[2], order[2]['key'])
        self.assertEqual(keys[3], order[3]['key'])
        self.assertEqual(keys[4], order[4]['key'])
        self.assertEqual(['gundam/JP', 'gundam/KR', 'gundam/US', 'pokemon/JP', 'pokemon/KR'], keys)

    def test_first_collection_to_next_collection_reuses_real_saved_search_outcomes(self):
        fake = self.collector()
        paths = []
        def record(cell, scoped, now):
            paths.append((cell['key'], scoped))
            return []
        for cycle in range(20):
            with patch.object(coverage, 'cells', fake.cells):
                summary = coverage.collect(self.root, fetcher=record,
                                           now=NOW + timedelta(minutes=31*cycle),
                                           clock=lambda: 0)
                self.assertLessEqual(summary['requests_this_run'], coverage.MAX_REQUESTS)
        self.assertEqual(79, len({x[0] for x in paths}))
        self.assertEqual(79, len(coverage._load(self.root)['cells']))
        before = (self.root / coverage.STATE).read_bytes()
        obs = feedback.feedback_summary(self.root)
        self.assertEqual('SEARCH_FEEDBACK_ONLY', obs['status'])
        self.assertEqual(79, obs['observed_cells'])
        self.assertEqual(79, obs['empty_success_cells'])
        self.assertEqual(0, obs['candidate_result_cells'])
        self.assertEqual(before, (self.root / coverage.STATE).read_bytes())
        page = matrix.render(self.root, now=NOW + timedelta(hours=10))
        self.assertIn('검색 결과 기반 순서 조정', page)
        self.assertIn('학습은 검색 효율에만 반영', page)
        self.assertNotIn('공식행사 79건 확인', page)

    def test_provider_429_cooldown_still_blocks_new_requests_after_learning(self):
        fake = self.collector()
        def fail(*args):
            raise HTTPError('https://www.bing.com', 429, 'provider block', {}, None)
        with patch.object(coverage, 'cells', fake.cells):
            first = coverage.collect(self.root, fetcher=fail, now=NOW, clock=lambda: 0)
            self.assertEqual(1, first['requests_this_run'])
            second = coverage.collect(self.root, fetcher=fail,
                                      now=NOW+timedelta(hours=1), clock=lambda: 0)
            self.assertEqual(0, second['requests_this_run'])
            self.assertIn('PROVIDER_COOLDOWN', second['errors_this_run'])
        self.assertEqual(0, feedback.feedback_summary(self.root)['candidate_result_cells'])

    def test_corrupt_search_history_does_not_rewrite_source_or_fake_zeros(self):
        fake = self.collector()
        path = self.root / coverage.STATE
        path.write_text('{"version":896,"cells":false}')
        before = path.read_bytes()
        original = kr.supplement_cells(self.registry, self.original)
        self.assertEqual(original, fake.cells(self.registry))
        self.assertEqual('READ_ERROR', feedback.feedback_summary(self.root)['status'])
        page = matrix.render(self.root, now=NOW)
        self.assertIn('검색 결과 학습 상태 확인 보류', page)
        self.assertEqual(before, path.read_bytes())

    def test_candidate_count_is_not_new_verified_event_or_learning_term(self):
        self.collector()
        candidate = {
            'version': 896, 'cursor':'pokemon/US',
            'cells': {'pokemon/US': {
                'attempted_at':NOW.isoformat(), 'requests':2,
                'successes':2,'results':1,'errors':[],
            }}, 'items': [],
        }
        p = self.root / coverage.STATE
        p.write_text(json.dumps(candidate))
        state = feedback.feedback_summary(self.root)
        self.assertEqual(1, state['candidate_result_cells'])
        self.assertEqual(0, state['confirmed_events_learned'])
        self.assertEqual(0, state['unverified_terms_added_to_trusted_vocabulary'])
        self.assertFalse((self.root / 'event_gap_learning.json').exists())
        self.assertFalse((self.root / 'event_collection_learning_v933.json').exists())

    def test_invalid_feedback_and_duplicate_search_cells_fail_closed(self):
        items = kr.supplement_cells(self.registry, self.original)
        with self.assertRaises(ValueError):
            feedback.ranked_cells(items + [items[0]], {})
        with self.assertRaises(ValueError):
            feedback.ranked_cells(items, {'pokemon/KR': {
                'attempted_at':NOW.isoformat(), 'requests':2,
                'successes':3,'results':0}})
        with self.assertRaises(ValueError):
            feedback.ranked_cells([], {})

    def test_no_state_file_or_background_worker_created_at_install(self):
        fake = self.collector()
        self.assertEqual(79,len(fake.cells(self.registry)))
        self.assertFalse((self.root/coverage.STATE).exists())
        self.assertEqual('NOT_RECORDED',feedback.feedback_summary(self.root)['status'])


if __name__ == '__main__':
    unittest.main()
