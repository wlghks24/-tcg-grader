"""KST event-day agreement and required EUR dependency deployment guards."""
from __future__ import annotations

import copy
import datetime as dt
from pathlib import Path
import unittest
from unittest.mock import patch

import static_data_publish_gate as gate
import tablet_runtime_manifest as runtime
import update_promo_events as promo

ROOT = Path(__file__).resolve().parents[2]
EUR_MODULE = 'tcg_reliability/fx_eur_reference_v980.py'
REAL_DATETIME = dt.datetime


def frozen_clock(instant):
    class FrozenDateTime(REAL_DATETIME):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz) if tz is not None else instant.replace(tzinfo=None)
    return FrozenDateTime


class DeploymentDatesV1001Tests(unittest.TestCase):
    def event(self):
        return {'name_ko': '일정 경계 검증', 'end_date': '2026-11-04',
                'date_precision': 'day', 'claim_deadline': '2026-11-04'}

    def test_business_day_changes_at_kst_midnight_for_every_timestamp_zone(self):
        before = REAL_DATETIME(2026, 11, 9, 14, 59, 59, tzinfo=dt.timezone.utc)
        after = before + dt.timedelta(seconds=1)
        self.assertEqual(dt.date(2026, 11, 9), promo.event_today(before))
        self.assertEqual(dt.date(2026, 11, 10), promo.event_today(after))
        for zone in (dt.timezone.utc, promo.EVENT_DAY_ZONE, dt.timezone(dt.timedelta(hours=-8))):
            with self.subTest(zone=str(zone)):
                self.assertEqual(dt.date(2026, 11, 10), promo.event_today(after.astimezone(zone)))

    def test_naive_timestamp_cannot_inherit_the_host_timezone(self):
        with self.assertRaises(ValueError):
            promo.event_today(REAL_DATETIME(2026, 11, 9, 15, 30))

    def test_default_collector_and_utc_publish_audit_agree_across_midnight(self):
        source = self.event()
        original = copy.deepcopy(source)
        for instant, expected in ((REAL_DATETIME(2026, 11, 9, 14, 59, tzinfo=dt.timezone.utc), 'recently_ended'),
                                  (REAL_DATETIME(2026, 11, 9, 15, 0, tzinfo=dt.timezone.utc), 'archive'),
                                  (REAL_DATETIME(2026, 11, 10, 0, 0, tzinfo=dt.timezone.utc), 'archive')):
            with self.subTest(instant=instant.isoformat()), patch.object(promo.dt, 'datetime', frozen_clock(instant)):
                current, archived = promo.partition_event_lifecycle([source])
                row = (current or archived)[0]
                self.assertEqual(expected, row['lifecycle'])
                self.assertEqual(expected == 'archive', promo.is_expired(source))
                self.assertEqual(expected, promo.lifecycle_state(source))
                payload = {'updated_at': instant.isoformat(), 'items': current, 'archive_items': archived}
                self.assertEqual([], gate.audit_event_lifecycle_snapshot(payload, now=instant))
        self.assertEqual(original, source, 'Partitioning must preserve the original event evidence')

    def test_explicit_today_arguments_remain_authoritative(self):
        explicit = dt.date(2026, 11, 9)
        with patch.object(promo, 'event_today', side_effect=AssertionError('explicit date must not read the clock')):
            self.assertFalse(promo.is_expired(self.event(), today=explicit))
            self.assertEqual('recently_ended', promo.lifecycle_state(self.event(), today=explicit))
            current, archived = promo.partition_event_lifecycle([self.event()], today=explicit)
            self.assertEqual([], archived)
            self.assertEqual('recently_ended', current[0]['lifecycle'])

    def test_yearless_event_parsing_uses_kst_new_year(self):
        instant = REAL_DATETIME(2026, 12, 31, 15, 0, tzinfo=dt.timezone.utc)
        with patch.object(promo.dt, 'datetime', frozen_clock(instant)):
            self.assertEqual(('2027-01-01', '2027-01-02'), promo.date_range('1월 1일 ~ 1월 2일'))

    def test_unannounced_movie_stays_tracking_on_kst_archive_boundary(self):
        instant = REAL_DATETIME(2026, 11, 9, 15, 30, tzinfo=dt.timezone.utc)
        source = {**self.event(), 'tracking_only': True, 'date_precision': 'unannounced',
                  'archive_on': '2026-11-10'}
        with patch.object(promo.dt, 'datetime', frozen_clock(instant)):
            current, archived = promo.partition_event_lifecycle([source])
        self.assertEqual([], archived)
        self.assertEqual('current', current[0]['lifecycle'])
        self.assertNotIn('archive_on', current[0])
        self.assertEqual([], gate.audit_event_lifecycle_snapshot(
            {'updated_at': instant.isoformat(), 'items': current, 'archive_items': []}, now=instant))

    def test_utc_snapshot_age_guard_remains_separate_from_kst_event_day(self):
        instant = REAL_DATETIME(2026, 11, 9, 15, 30, tzinfo=dt.timezone.utc)
        current, archived = promo.partition_event_lifecycle([self.event()], today=promo.event_today(instant))
        payload = {'updated_at': (instant - dt.timedelta(hours=3)).isoformat(),
                   'items': current, 'archive_items': archived}
        codes = {row['code'] for row in gate.audit_event_lifecycle_snapshot(payload, now=instant)}
        self.assertEqual({'STALE_EVENT_SNAPSHOT'}, codes)

    def test_missing_required_eur_dependency_fails_runtime_preflight(self):
        self.assertIn(EUR_MODULE, runtime.ACTIVE_RUNTIME_FILES)
        original = Path.is_file
        target = ROOT / EUR_MODULE
        with patch.object(Path, 'is_file', lambda p: False if p == target else original(p)):
            report = runtime.audit(ROOT)
        self.assertFalse(report['ok'])
        self.assertIn(EUR_MODULE, report['missing'])

    def test_symlinked_required_eur_dependency_fails_runtime_preflight(self):
        original = Path.is_symlink
        target = ROOT / EUR_MODULE
        with patch.object(Path, 'is_symlink', lambda p: p == target or original(p)):
            report = runtime.audit(ROOT)
        self.assertFalse(report['ok'])
        self.assertIn(EUR_MODULE, report['symlinks'])

    def test_invalid_required_eur_dependency_fails_compile_preflight(self):
        original = Path.read_text
        target = ROOT / EUR_MODULE
        def malformed(path, *a, **kw):
            return 'def broken(' if path == target else original(path, *a, **kw)
        with patch.object(Path, 'read_text', malformed):
            report = runtime.audit(ROOT, compile_python=True)
        self.assertFalse(report['ok'])
        self.assertTrue(any(row['file'] == EUR_MODULE and row['error'] == 'SyntaxError'
                            for row in report['compile_errors']))


if __name__ == '__main__':
    unittest.main()
