"""Offline source-field fixtures; no provider calls or original-file writes."""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from execution.tablet_event_summary_v890 import project_events, read_event_summary

NOW = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
BASE = {'game': '포켓몬 카드', 'region': 'JP', 'category': 'collaboration',
        'name_ko': '실제 필드 형식 행사', 'source': 'https://www.pokemon-card.com/info/005397.html',
        'source_grade': 'official', 'link_status': '정상', 'link_checked_at': '2026-11-01T12:00:00+00:00',
        'start_date': '2026-11-01', 'end_date': '2026-11-03', 'claim_deadline': '2026-11-03'}


class EventSummaryTests(unittest.TestCase):
    def result(self, rows=None, archive=None):
        return project_events({'items': rows if rows is not None else [copy.deepcopy(BASE)],
                               'archive_items': archive or []}, now=NOW)

    def test_actual_field_schema_keeps_identity_lineage_and_freshness(self):
        r = self.result()['rows'][0]
        self.assertEqual('CURRENT', r['lifecycle'])
        self.assertEqual('FRESH_OFFICIAL', r['evidence_state'])
        self.assertEqual('JP', r['region'])
        self.assertEqual('collaboration', r['category'])
        self.assertEqual(24, len(r['lineage_id']))

    def test_tracking_internal_2027_horizon_never_becomes_announced_date(self):
        r = dict(BASE, tracking_only=True, date_precision='unannounced',
                 start_date='2026-08-23', end_date='2027-12-31', claim_deadline='2027-12-31')
        row = self.result([r])['rows'][0]
        self.assertEqual('TRACKING', row['lifecycle'])
        self.assertIsNone(row['start_date'])
        self.assertIsNone(row['end_date'])
        self.assertIsNone(row['claim_deadline'])

    def test_archive_preserved_even_without_current_rows(self):
        row = self.result([], [BASE])['rows'][0]
        self.assertTrue(row['archived'])
        self.assertEqual('ARCHIVED', row['lifecycle'])

    def test_current_upcoming_recent_expired_and_unknown_dates(self):
        for changes, expected in [({'start_date': '2026-11-03'}, 'UPCOMING'),
                ({'end_date': '2026-11-01', 'claim_deadline': '2026-11-01'}, 'RECENTLY_ENDED'),
                ({'start_date': '2026-10-01', 'end_date': '2026-10-20', 'claim_deadline': '2026-10-20'}, 'ARCHIVED'),
                ({'start_date': '2026-11-03', 'end_date': '2026-11-01'}, 'UNKNOWN_DATE'),
                ({'start_date': 'bad'}, 'UNKNOWN_DATE')]:
            with self.subTest(expected=expected):
                self.assertEqual(expected, self.result([dict(BASE, **changes)])['rows'][0]['lifecycle'])

    def test_v943_ended_event_with_later_claim_deadline_is_not_current(self):
        event = dict(BASE, start_date='2026-10-01',
                     end_date='2026-10-31', claim_deadline='2026-11-30')
        row = self.result([event])['rows'][0]
        self.assertEqual('RECENTLY_ENDED', row['lifecycle'])
        self.assertEqual('2026-10-31', row['end_date'])
        self.assertEqual('2026-11-30', row['claim_deadline'])
        self.assertFalse(row['archived'])
        later = datetime(2026, 12, 7, 12, tzinfo=timezone.utc)
        self.assertEqual('ARCHIVED', project_events(
            {'items': [event]}, now=later)['rows'][0]['lifecycle'])

    def test_v956_calendar_only_date_and_max_year_do_not_blank_valid_events(self):
        # datetime.date.fromisoformat accepts 2026-W45-3 as Nov 4. It must
        # not become an apparently announced event end date in saved sources.
        week = dict(BASE, end_date='2026-W45-3',
                    claim_deadline='2026-W45-3')
        projected = self.result([week])['rows'][0]
        self.assertEqual('UNKNOWN_DATE', projected['lifecycle'])
        self.assertIsNone(projected['start_date'])
        self.assertIsNone(projected['end_date'])

        # A stored distant-future date must not overflow date + five days,
        # and must not cause a valid adjacent event to disappear.
        distant = dict(BASE, name_ko='극단 날짜의 별도 보관 행사',
                       start_date='9999-12-29', end_date='9999-12-31',
                       claim_deadline='9999-12-31')
        summary = self.result([dict(BASE), distant])
        self.assertEqual(2, summary['summary']['loaded_rows'])
        by_name = {row['name']: row for row in summary['rows']}
        self.assertEqual('CURRENT', by_name[BASE['name_ko']]['lifecycle'])
        self.assertEqual('UPCOMING', by_name[distant['name_ko']]['lifecycle'])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'promo_events.json'
            path.write_text(json.dumps({'items': [BASE, distant]}), encoding='utf-8')
            before = path.read_bytes()
            readback = read_event_summary(root, now=NOW)
            self.assertTrue(readback['ok'])
            self.assertEqual(2, readback['summary']['loaded_rows'])
            self.assertEqual(before, path.read_bytes())

    def test_reachable_old_link_is_stale_not_currently_verified(self):
        row = self.result([dict(BASE, link_checked_at='2026-10-08T23:40:15+00:00')])['rows'][0]
        self.assertEqual('STALE_OFFICIAL', row['evidence_state'])
        for stamp in ('2026-11-02T12:00:00', None, '2027-01-01T00:00:00Z'):
            with self.subTest(stamp=stamp):
                row = self.result([dict(BASE, link_checked_at=stamp)])['rows'][0]
                self.assertEqual('UNKNOWN_FRESHNESS', row['evidence_state'])

    def test_unsupported_sources_do_not_become_clickable_official_evidence(self):
        for source in ('http://127.0.0.1/private', 'https://evil.invalid/events', 'javascript:alert(1)'):
            row = self.result([dict(BASE, source=source)])['rows'][0]
            self.assertIsNone(row['source'])
            self.assertEqual('INVALID_SOURCE', row['evidence_state'])

    def test_lineage_deduplication_ignores_tracking_parameters(self):
        other = dict(BASE, source=BASE['source'] + '?utm_source=mirror')
        result = self.result([BASE, other])
        self.assertEqual(1, result['summary']['loaded_rows'])
        self.assertEqual(1, result['summary']['unique_lineages'])

    def test_invalid_schema_and_bounded_rows(self):
        for value in ({'items': None}, {'items': [BASE] * 3001}, {'items': [], 'archive_items': None}):
            with self.assertRaises(ValueError):
                project_events(value, now=NOW)
        result = self.result([None, {}, dict(BASE, region='bad')])
        self.assertEqual(3, result['summary']['rejected_rows'])

    def test_unavailable_duplicate_json_and_symlink_are_not_zero_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertIsNone(read_event_summary(root, now=NOW)['summary'])
            path = root / 'promo_events.json'
            path.write_text('{"items":[],"items":[]}')
            self.assertFalse(read_event_summary(root, now=NOW)['ok'])
            path.unlink()
            target = root / 'other.json'; target.write_text('{"items":[]}')
            path.symlink_to(target)
            self.assertFalse(read_event_summary(root, now=NOW)['ok'])

    def test_read_only_real_file_roundtrip_and_kst_day_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = root / 'promo_events.json'
            path.write_text(json.dumps({'items': [BASE]}))
            before = path.read_bytes()
            result = read_event_summary(root, now=NOW)
            self.assertTrue(result['ok'])
            self.assertEqual(before, path.read_bytes())
        row = dict(BASE, start_date='2026-11-03')
        late = datetime(2026, 11, 2, 16, tzinfo=timezone.utc)
        self.assertEqual('CURRENT', project_events({'items': [row]}, now=late)['rows'][0]['lifecycle'])

    def test_global_and_asia_events_retained_without_country_substitution(self):
        rows = self.result([dict(BASE, region='GLOBAL'), dict(BASE, region='ASIA')])['rows']
        self.assertEqual({'GLOBAL', 'ASIA'}, {r['region'] for r in rows})
