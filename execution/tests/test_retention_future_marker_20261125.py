import unittest
from datetime import date
from copy import deepcopy
from execution.event_retention_20261123 import apply_retention, LEDGER

TODAY = date(2026,11,25)
SEED = dict(game='ONE PIECE',region='KR',category='movie',name_ko='테스트',source='https://example.org/news',tracking_only=True,date_precision='unannounced')

class Tests(unittest.TestCase):
    def test_future_marker_with_valid_fact(self):
        row = dict(SEED, retention_first_seen_on='2099-01-01', announcement_date='2026-11-24')
        result = apply_retention({'items':[row]},today=TODAY)
        self.assertEqual(list(result[LEDGER].values()),['2026-11-24'])
        self.assertEqual(result,apply_retention(result,today=TODAY))
    def test_future_marker_with_confirmed_event(self):
        row = dict(SEED,tracking_only=False,date_precision='day',start_date='2026-12-01',end_date='2026-12-02',retention_first_seen_on='2099-01-01')
        result = apply_retention({'items':[row]},today=TODAY)
        self.assertEqual(result[LEDGER],{})
        self.assertNotIn('retention_first_seen_on',result['items'][0])
        self.assertEqual(result,apply_retention(result,today=TODAY))
    def test_expired_fact_cannot_poison_ledger(self):
        row = dict(SEED,retention_first_seen_on='2099-01-01',announcement_date='2026-11-01')
        result = apply_retention({'items':[], 'archive_items':[row]},today=TODAY)
        self.assertEqual(result['archive_items'],[])
        self.assertEqual(list(result[LEDGER].values()),['2026-11-01'])
        apply_retention(result,today=TODAY)
    def test_existing_ledger_not_renewed(self):
        first = apply_retention({'items':[SEED]},today=date(2026,11,1))
        first['items']=[dict(SEED,retention_first_seen_on='2099-01-01',discovered_at='2026-11-25')]
        result=apply_retention(first,today=TODAY)
        self.assertEqual(result['items'],[])
        self.assertEqual(list(result[LEDGER].values()),['2026-11-01'])
    def test_valid_new_announcement(self):
        first=apply_retention({'items':[SEED]},today=date(2026,11,1))
        first['items']=[dict(SEED,announcement_date='2026-11-25')]
        self.assertEqual(len(apply_retention(first,today=TODAY)['items']),1)
    def test_bad_persisted_ledger_still_fails_closed(self):
        with self.assertRaises(ValueError):
            apply_retention({'items':[SEED],LEDGER:{'a'*64:'2099-01-01'}},today=TODAY)
    def test_input_and_learning_unchanged(self):
        payload={'items':[dict(SEED,retention_first_seen_on='2099-01-01',announcement_date='2026-11-24')],'learning':{'labels':[1]},'photos':['x']}
        before=deepcopy(payload); result=apply_retention(payload,today=TODAY)
        self.assertEqual(payload,before); self.assertEqual(result['learning'],before['learning']); self.assertEqual(result['photos'],before['photos'])
    def test_future_marker_no_facts(self):
        result=apply_retention({'items':[dict(SEED,retention_first_seen_on='2099-01-01')]},today=TODAY)
        self.assertEqual(list(result[LEDGER].values()),[TODAY.isoformat()])
        self.assertEqual(result,apply_retention(result,today=TODAY))
    def test_fourteen_day_boundary(self):
        first=apply_retention({'items':[SEED]},today=date(2026,11,11))
        self.assertEqual(len(apply_retention(first,today=date(2026,11,24))['items']),1)
        self.assertEqual(apply_retention(first,today=TODAY)['items'],[])
    def test_future_zoned_marker(self):
        row=dict(SEED,retention_first_seen_on='2026-11-25T15:00:00Z',source_published_at='2026-11-24')
        result=apply_retention({'items':[row]},today=TODAY)
        self.assertEqual(list(result[LEDGER].values()),['2026-11-24'])
        apply_retention(result,today=TODAY)
