"""Deterministic event projection and composed-document regressions; no HTTP."""
import unittest
from unittest.mock import patch
from execution import tablet_menu_shell_v903 as shell
from execution.tablet_event_summary_v890 import project_events
from execution.tests.test_tablet_event_summary_v890 import BASE, NOW


class WorkspaceEventsV1018Tests(unittest.TestCase):
    def row(self, **changes):
        return project_events({'items': [dict(BASE, **changes)]}, now=NOW)['rows'][0]

    def document(self, data, summary=None):
        source = '<html><head></head><body><main class="app"></main></body></html>'
        with patch.object(shell, 'read_source', return_value=source), patch.object(shell, 'gallery', return_value=data), patch.object(shell, 'event_fragment', return_value='<p>DISCOVERY_ONLY</p>'), patch('execution.tablet_event_summary_v890.read_event_summary', return_value=summary or {'ok': False}):
            return shell.compose('.')

    def data(self, **changes):
        return dict({'state': 'COMPLETE', 'cards': '', 'options': '', 'count': 0, 'events': 'PREVIEW_ONLY', 'news': '<article>OFFICIAL_FULL_ONLY</article>'}, **changes)

    def test_full_official_news_is_reachable_in_event_panel(self):
        page = self.document(self.data())
        panel = page.split('<section id="tcg903-events"', 1)[1].split('</div>', 1)[0]
        self.assertIn('OFFICIAL_FULL_ONLY', panel)
        self.assertIn('tcg1018-official-events', panel)
        self.assertNotIn('기존 행사·프로모 정보', panel)

    def test_discovery_is_separate_collapsed_details(self):
        page = self.document(self.data())
        self.assertIn('<details id="tcg1018-event-discovery">', page)
        self.assertIn('DISCOVERY_ONLY', page)
        self.assertIn('검색 후보는 공식 확인 전 정보', page)

    def test_card_feed_failure_does_not_hide_readable_events(self):
        page = self.document(self.data(state='UNAVAILABLE', news='', count=None), {'ok': True, 'rows': [self.row(name_ko='독립 행사')]})
        self.assertIn('독립 행사', page)
        self.assertIn('카드 자료 읽기 보류', page)

    def test_unavailable_events_are_not_reported_as_confirmed_zero(self):
        page = self.document(self.data(news=''))
        self.assertIn('행사 자료 읽기 보류', page)
        self.assertIn('0건으로 판정하지', page)

    def test_month_precision_retains_label_without_exact_day_or_deadline(self):
        row = self.row(date_precision='month', start_date='2027-02-01', end_date='2027-02-28', date_label='2027년 2월 예정 · 정확한 날짜 미발표')
        self.assertEqual('month', row['date_precision'])
        self.assertIn('2027년 2월', row['date_label'])
        for key in ('start_date', 'end_date', 'claim_deadline'):
            self.assertIsNone(row[key])
        self.assertNotIn('2027-02-01', shell.event_news({'ok': True, 'rows': [row]}))

    def test_season_precision_has_explicit_uncertainty_fallback(self):
        row = self.row(date_precision='season', date_label='')
        self.assertIn('정확한 날짜 미발표', row['date_label'])
        self.assertIsNone(row['start_date'])

    def test_streaming_series_does_not_become_theatrical_film(self):
        row = self.row(category='movie', media_type='streaming_series', name_ko='<script>유해</script>')
        self.assertEqual('streaming_series', row['media_type'])
        rendered = shell.event_news({'ok': True, 'rows': [row]})
        self.assertIn('영상·시리즈', rendered)
        self.assertNotIn('<script>', rendered)
        self.assertIn('&lt;script&gt;', rendered)

    def test_unannounced_tracking_still_cannot_claim_real_dates(self):
        row = self.row(date_precision='unannounced', start_date='2027-01-01', end_date='2027-12-31')
        self.assertEqual('TRACKING', row['lifecycle'])
        self.assertIsNone(row['start_date'])
        self.assertIn('공식 일정 확인 중', row['date_label'])


if __name__ == '__main__':
    unittest.main()
