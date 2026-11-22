"""Stored projection rendering tests; no browser or device verification."""
import copy
import unittest
from execution.tablet_event_labels_20261122 import labels, LIFECYCLE, EVIDENCE
from execution.tablet_menu_shell_v903 import event_news


class EventLabelTests(unittest.TestCase):
    def row(self, **changes):
        row = dict(game='pokemon', region='JP', category='movie', name='영화 소식',
                   source='https://www.pokemon.co.jp/', lifecycle='CURRENT',
                   evidence_state='STALE_OFFICIAL', date_label='공식 일정 확인 중')
        row.update(changes)
        return row

    def test_all_schedule_states_are_korean_and_separate_from_freshness(self):
        for state, expected in LIFECYCLE.items():
            with self.subTest(state=state):
                r=labels(self.row(lifecycle=state))
                self.assertIn(expected,r['schedule'])
                self.assertEqual(r['evidence'],'출처: 공식 출처 재확인 필요')

    def test_evidence_states_do_not_change_schedule(self):
        for state, expected in EVIDENCE.items():
            r=labels(self.row(evidence_state=state))
            self.assertEqual(r['schedule'],'일정: 진행 중')
            self.assertIn(expected,r['evidence'])

    def test_tracking_never_claims_confirmed_movie_schedule(self):
        for row in (self.row(tracking_only=True),self.row(lifecycle='TRACKING')):
            r=labels(row)
            self.assertIn('일정 추적',r['category'])
            self.assertEqual(r['schedule'],'일정: 일정 확인 중')

    def test_streaming_and_theatrical_are_separate(self):
        self.assertEqual(labels(self.row(media_type='streaming_series'))['category'],'스트리밍·시리즈')
        self.assertEqual(labels(self.row(media_type='theatrical_film'))['category'],'극장 영화 소식')
        self.assertEqual(labels(self.row())['category'],'영화·영상 소식')

    def test_unknown_and_malformed_status_never_become_current_or_fresh(self):
        for value in (None, 'evil', [], {}, True):
            r=labels(self.row(category=value,lifecycle=value,evidence_state=value))
            self.assertEqual(r,dict(category='기타 소식',schedule='일정: 상태 확인 필요',evidence='출처: 근거 검증 필요'))

    def test_renderer_preserves_evidence_and_escapes_all_untrusted_details(self):
        row=self.row(name='<script>alert(1)</script>',reward='<img src=x onerror=bad>',condition='<b>조건</b>')
        before=copy.deepcopy(row)
        result=event_news(dict(ok=True,rows=[row]))
        self.assertIn('일정: 진행 중 · 출처: 공식 출처 재확인 필요', result)
        self.assertIn('특전 안내(원문):',result)
        self.assertIn('참여 조건(원문):',result)
        self.assertIn('&lt;img',result)
        self.assertNotIn('<script>',result)
        self.assertNotIn('<img',result)
        self.assertNotIn('STALE_OFFICIAL',result)
        self.assertEqual(before,row)

    def test_missing_evidence_does_not_report_zero_success(self):
        self.assertIn('읽기 보류',event_news({}))
        self.assertIn('더 수집',event_news(dict(ok=True,rows=[])))

    def test_collaboration_category_is_readable(self):
        self.assertEqual(labels(self.row(category='collaboration'))['category'],'콜라보')
        self.assertEqual(labels(self.row(category='collab'))['category'],'콜라보')
