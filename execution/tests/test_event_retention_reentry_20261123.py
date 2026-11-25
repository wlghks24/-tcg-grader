"""A deleted undated seed must not regain fourteen days on reinsertion."""
import copy
from datetime import date
import unittest
from unittest.mock import patch
from execution import event_retention_20261123 as retention

SEED = dict(game='원피스 카드',region='KR',category='movie',name_ko='일정 미정 추적',
            source='https://daewonmedia.com/business',tracking_only=True,date_precision='unannounced')


class RetentionReentryTests(unittest.TestCase):
    def expired(self):
        first=retention.apply_retention({'items':[copy.deepcopy(SEED)],'archive_items':[]},today=date(2026,11,1))
        return retention.apply_retention(first,today=date(2026,11,15))

    def test_identical_seed_stays_deleted_after_next_collection(self):
        payload=self.expired();self.assertEqual([],payload['items'])
        payload['items']=[copy.deepcopy(SEED)]
        result=retention.apply_retention(payload,today=date(2026,11,16))
        self.assertEqual([],result['items'])
        self.assertEqual(1,result['retention_removed_count'])

    def test_newer_local_marker_and_tracking_query_cannot_renew_old_seed(self):
        payload=self.expired();row=copy.deepcopy(SEED)
        row.update(retention_first_seen_on='2026-11-16',link_checked_at='2026-11-16T12:00:00+09:00',
                   source=SEED['source']+'?utm_source=new#section')
        payload['items']=[row]
        self.assertEqual([],retention.apply_retention(payload,today=date(2026,11,16))['items'])

    def test_rediscovery_timestamp_does_not_renew_the_same_undated_notice(self):
        payload=self.expired();payload['items']=[{**SEED,'discovered_at':'2026-11-16T10:00:00+09:00'}]
        self.assertEqual([],retention.apply_retention(payload,today=date(2026,11,16))['items'])

    def test_new_factual_announcement_or_confirmed_future_event_can_replace_watch(self):
        for changes in ({'announcement_date':'2026-11-16'},
                        {'tracking_only':False,'date_precision':'day','start_date':'2026-12-01','end_date':'2026-12-03'}):
            payload=self.expired();payload['items']=[{**SEED,**changes}]
            self.assertEqual(1,len(retention.apply_retention(payload,today=date(2026,11,16))['items']))

    def test_duplicate_first_seen_is_independent_of_list_order(self):
        old = {**SEED, 'retention_first_seen_on': '2026-11-01'}
        recent = {**SEED, 'discovered_at': '2026-11-25'}
        for items, archive in (([recent], [old]), ([old], [recent]),
                               ([recent, old], []), ([old, recent], []),
                               ([{**old, **{'discovered_at': '2026-11-25'}}], [])):
            with self.subTest(items=items, archive=archive):
                payload = {'items': items, 'archive_items': archive}
                before = copy.deepcopy(payload)
                result = retention.apply_retention(payload, today=date(2026,11,25))
                self.assertEqual([], result['items'])
                self.assertEqual([], result['archive_items'])
                self.assertEqual(before, payload)

    def test_duplicate_old_marker_does_not_hide_new_official_announcement(self):
        old = {**SEED, 'retention_first_seen_on': '2026-11-01'}
        recent = {**SEED, 'announcement_date': '2026-11-25'}
        result = retention.apply_retention({'items': [recent], 'archive_items': [old]},
                                           today=date(2026,11,25))
        self.assertEqual(1, len(result['items']))
        self.assertEqual([], result['archive_items'])

    def test_ledger_retains_only_hashes_and_dates_not_deleted_rows(self):
        result=self.expired();ledger=result[retention.LEDGER]
        self.assertEqual(1,len(ledger))
        for key,value in ledger.items():
            self.assertRegex(key,r'^[0-9a-f]{64}$');self.assertEqual('2026-11-01',value)
        self.assertNotIn(SEED['name_ko'],str(result))
        self.assertNotIn(SEED['source'],str(result))

    def test_malformed_future_and_over_capacity_ledgers_hold_without_modifying_input(self):
        cases=[[],{'not-a-hash':'2026-11-01'},{'a'*64:'2027-01-01'},{'a'*64:'bad'}]
        for ledger in cases:
            payload={'items':[copy.deepcopy(SEED)],retention.LEDGER:ledger};before=copy.deepcopy(payload)
            with self.subTest(ledger=ledger),self.assertRaises(ValueError):
                retention.apply_retention(payload,today=date(2026,11,16))
            self.assertEqual(before,payload)
        with patch.object(retention,'MAX_UNDATED_KEYS',0),self.assertRaises(ValueError):
            retention.apply_retention({'items':[SEED]},today=date(2026,11,16))


if __name__=='__main__':unittest.main()
