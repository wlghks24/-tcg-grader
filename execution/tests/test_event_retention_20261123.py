"""Pure retention boundaries; no network, source writes, photo or model changes."""
from copy import deepcopy
from datetime import date, datetime, timezone
import unittest
from execution.event_retention_20261123 import apply_retention, CATEGORIES

TODAY = date(2026, 11, 23)
BASE = dict(category='event', name_ko='행사', start_date='2026-10-01', end_date='2026-11-09', claim_deadline='2026-11-09')


class EventRetentionTests(unittest.TestCase):
    def apply(self, row=None, **kwargs):
        return apply_retention({'items': [dict(BASE, **(row or {}))]}, today=kwargs.get('today', TODAY))

    def test_fourteen_day_boundary_and_claim_deadline(self):
        self.assertEqual(len(self.apply(today=date(2026, 11, 22))['items']), 1)
        self.assertEqual(self.apply()['items'], [])
        self.assertEqual(len(self.apply({'claim_deadline': '2026-11-10'})['items']), 1)
        self.assertEqual(self.apply({'claim_deadline': '2026-11-10'}, today=date(2026, 11, 24))['items'], [])

    def test_both_active_and_archive_are_really_removed_with_counts(self):
        payload = {'items': [dict(BASE)], 'archive_items': [dict(BASE)],
                   'archive_event_count': 99, 'expired_event_count': 99, 'expired_event_names': ['행사']}
        result = apply_retention(payload, today=TODAY)
        self.assertEqual(result['items'], [])
        self.assertEqual(result['archive_items'], [])
        self.assertEqual(result['retention_removed_count'], 2)
        self.assertEqual(result['retention_remaining_count'], 0)
        self.assertEqual(result['archive_event_count'], 0)
        self.assertEqual(result['expired_event_count'], 0)
        self.assertEqual(result['expired_event_names'], [])
        self.assertNotIn('removed_rows', result)

    def test_original_payload_and_other_domains_are_deeply_unchanged(self):
        payload = {'items': [dict(BASE)], 'archive_items': [], 'photos': [{'private': [1]}], 'learning': {'grade': 9}}
        before = deepcopy(payload)
        result = apply_retention(payload, today=TODAY)
        self.assertEqual(payload, before)
        self.assertEqual(result['photos'], payload['photos'])
        result['photos'][0]['private'].append(2)
        self.assertEqual(payload, before)

    def test_current_and_future_day_events_survive(self):
        for row in [{'end_date': '2026-12-10'}, {'start_date': '2027-01-01', 'end_date': '2027-01-02'},
                    {'tracking_only': True, 'date_precision': 'day', 'end_date': '2026-12-10'}]:
            with self.subTest(row=row): self.assertEqual(len(self.apply(row)['items']), 1)

    def test_announced_month_and_season_ranges_keep_precision_and_future_window(self):
        for precision in ('month', 'season'):
            row = dict(BASE, name_ko='THE ONE PIECE', date_precision=precision, tracking_only=True,
                       start_date='2027-02-01', end_date='2027-02-28', claim_deadline='2027-02-28')
            kept = apply_retention({'items': [row]}, today=TODAY)['items'][0]
            self.assertEqual(kept['date_precision'], precision)
            self.assertEqual(len(apply_retention({'items': [row]}, today=date(2027, 3, 13))['items']), 1)
            self.assertEqual(apply_retention({'items': [row]}, today=date(2027, 3, 14))['items'], [])

    def test_playgo_start_only_does_not_use_compatibility_deadlines_or_fresh_links(self):
        row = dict(BASE, name_ko='PLAYGO', tracking_only=True, date_precision='start-only',
                   start_date='2026-09-01', end_date='2027-12-31', claim_deadline='2027-12-31',
                   link_checked_at='2026-11-23T01:00:00Z', updated_at='2026-11-23T01:00:00Z', discovered_at='2026-11-23')
        self.assertEqual(apply_retention({'items': [row]}, today=TODAY)['items'], [])
        self.assertEqual(len(apply_retention({'items': [row]}, today=date(2026, 9, 14))['items']), 1)
        self.assertEqual(apply_retention({'items': [row]}, today=date(2026, 9, 15))['items'], [])

    def test_unannounced_internal_dates_are_not_real_anchors(self):
        row = dict(BASE, tracking_only=True, date_precision='unannounced',
                   start_date='2026-08-23', end_date='2027-12-31', claim_deadline='2027-12-31',
                   announcement_date='2026-11-09', link_checked_at='2026-11-23', updated_at='2026-11-23')
        self.assertEqual(apply_retention({'items': [row]}, today=TODAY)['items'], [])

    def test_latest_valid_nonfuture_fact_wins_and_all_four_fields_work(self):
        for field in ('announcement_date', 'source_published_at', 'discovered_at', 'first_seen_at'):
            result = self.apply({'tracking_only': True, 'date_precision': 'unannounced', field: '2026-11-09'})
            self.assertEqual(result['items'], [])
        row = dict(tracking_only=True, date_precision='unannounced', announcement_date='2026-11-08',
                   source_published_at='2026-11-10', discovered_at='2027-01-01', first_seen_at='invalid')
        self.assertEqual(len(self.apply(row)['items']), 1)

    def test_missing_facts_get_one_persisted_retention_clock_not_a_schedule(self):
        result = self.apply({'tracking_only': True, 'date_precision': 'unannounced'})
        row = result['items'][0]
        self.assertEqual(row['retention_first_seen_on'], '2026-11-23')
        self.assertEqual(row['start_date'], BASE['start_date'])
        again = apply_retention(result, today=date(2026, 12, 6))
        self.assertEqual(again['items'][0]['retention_first_seen_on'], '2026-11-23')
        self.assertEqual(apply_retention(again, today=date(2026, 12, 7))['items'], [])

    def test_existing_first_seen_is_not_reset_by_rechecks_or_invalid_future_facts(self):
        row = dict(tracking_only=True, date_precision='unannounced', retention_first_seen_on='2026-11-09',
                   link_checked_at='2026-11-23', updated_at='2026-11-23', discovered_at='2099-01-01',
                   source_published_at='2026-11-23T01:00:00', announcement_date='broken')
        self.assertEqual(self.apply(row)['items'], [])

    def test_future_or_invalid_fallback_marker_cannot_slide_every_day(self):
        for marker in ('2099-01-01', 'bad', True):
            result = self.apply({'tracking_only': True, 'date_precision': 'unannounced', 'retention_first_seen_on': marker})
            self.assertEqual(result['items'][0]['retention_first_seen_on'], '2026-11-23')
            self.assertEqual(apply_retention(result, today=date(2026, 12, 7))['items'], [])

    def test_reapplied_last_good_or_reintroduced_old_seed_is_deleted_again(self):
        last_good = {'items': [dict(BASE)], 'archive_items': [dict(BASE)]}
        for _ in range(2):
            result = apply_retention(last_good, today=TODAY)
            self.assertEqual(result['items'], [])
            self.assertEqual(result['archive_items'], [])
        result['items'].append(dict(BASE))
        self.assertEqual(apply_retention(result, today=TODAY)['items'], [])

    def test_kst_boundary_for_fact_timestamps_and_clock(self):
        row = dict(tracking_only=True, date_precision='unannounced', announcement_date='2026-11-08T15:00:00Z')
        self.assertEqual(len(self.apply(row, today=datetime(2026, 11, 22, 14, 59, tzinfo=timezone.utc))['items']), 1)
        self.assertEqual(self.apply(row, today=datetime(2026, 11, 22, 15, 0, tzinfo=timezone.utc))['items'], [])
        with self.assertRaises(ValueError): self.apply(today=datetime(2026, 11, 23))

    def test_every_supported_event_category_expires_without_touching_other_rows(self):
        result = apply_retention({'items': [dict(BASE, category=c) for c in CATEGORIES] +
                                  [dict(BASE, category='private-photo'), 'malformed-row']}, today=TODAY)
        self.assertEqual(len(result['items']), 2)
        self.assertEqual(result['items'][0]['category'], 'private-photo')

    def test_malformed_container_fails_without_mutation(self):
        for payload in (None, [], {'items': None}, {'items': [], 'archive_items': None}):
            with self.assertRaises(ValueError): apply_retention(payload, today=TODAY)


if __name__ == '__main__':
    unittest.main()
