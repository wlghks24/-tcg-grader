"""Real collection orchestration with offline sources and temporary data only."""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import update_promo_events as promo
from execution.official_event_watchlist_20261123 import REVIEWED_EVENTS
from execution.tablet_event_summary_v890 import project_events

NOW = datetime(2026, 11, 23, 1, tzinfo=timezone.utc)


class EventCollectionPipelineTests(unittest.TestCase):
    def row(self, **changes):
        return dict(game='원피스 카드', region='KR', category='event',
                    name_ko='보존할 기존 행사', name_native='Existing event',
                    start_date='2026-11-01', end_date='2026-12-01',
                    source='https://onepiece-cardgame.kr/events.do?id=old',
                    reward='조건 확인', condition='공식 원문 확인',
                    source_grade='official', **changes)

    def run_collection(self, cinema_errors=None):
        import execution.official_cinema_news_20261123 as cinema
        old = self.row()
        archive = {**old, 'name_ko':'지난 행사', 'name_native':'Past event',
                   'source':old['source']+'-archive', 'start_date':'2026-11-01',
                   'end_date':'2026-11-15'}
        movie = {**old, 'name_ko':'새 공식 영화 일정', 'name_native':'New movie',
                 'category':'movie', 'date_precision':'day',
                 'start_date':'2026-11-20', 'end_date':'2026-12-06',
                 'source':'https://cjnews.cj.net/official-cinema-notice/'}
        evidence = {r['source']:' '.join(r['required_evidence']) for r in REVIEWED_EVENTS}
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder)/'promo_events.json'
            data.write_text(json.dumps({'items':[old], 'archive_items':[archive]}))
            with patch.object(promo,'DATA',data), patch.object(promo,'INDEXES',()), \
                 patch.object(promo,'REGIONAL_MOVIE_TRACKERS',()), \
                 patch.object(promo,'OFFICIAL_VERIFIED_SEEDS',REVIEWED_EVENTS), \
                 patch.object(promo,'event_today',return_value=NOW.date()), \
                 patch.object(promo,'fetch',side_effect=lambda url:evidence.get(url,'Existing event')), \
                 patch.object(cinema,'collect',return_value=([movie] if not cinema_errors else [],cinema_errors or [])) as collect:
                result=promo.main()
            self.assertEqual(result,json.loads(data.read_text()))
            collect.assert_called_once()
            return result

    def test_real_main_integrates_cinema_and_rechecks_reviewed_notices(self):
        result=self.run_collection()
        names={r['name_ko'] for r in result['items']}
        self.assertIn('새 공식 영화 일정',names)
        self.assertIn('보존할 기존 행사',names)
        self.assertTrue(any(r['name_ko']=='지난 행사' for r in result['archive_items']))
        for expected in REVIEWED_EVENTS:
            observed=next(r for r in result['items'] if r['source']==expected['source'])
            self.assertEqual(expected['start_date'],observed['start_date'])
            self.assertEqual('정상',observed['link_status'])
            self.assertIn('content_checked_at',observed)

    def test_failed_new_feed_preserves_history_and_reports_failure(self):
        result=self.run_collection(['cinema feed unavailable'])
        self.assertIn('cinema feed unavailable',result['collection_errors'])
        self.assertTrue(any(r['name_ko']=='보존할 기존 행사' for r in result['items']))
        self.assertTrue(result['archive_items'])
        self.assertNotEqual('정상',result['collection_status'])

    def test_retention_recomputes_coverage_after_removing_old_movie(self):
        row=self.row();row.update(category='movie',date_precision='day',start_date='2026-09-01',end_date='2026-09-03')
        data={'items':[row],'archive_items':[], 'coverage':promo.coverage_summary([row]),'kr_movie_tracking_count':1}
        with patch.object(promo,'event_today',return_value=NOW.date()):
            result=promo.refresh_auxiliary_coverage_metadata(data,write=False)
        self.assertEqual([],result['items'])
        self.assertEqual(promo.coverage_summary([]),result['coverage'])
        self.assertEqual(0,result['kr_movie_tracking_count'])

    def test_reviewed_notice_200_without_required_content_is_not_success(self):
        row=copy.deepcopy(REVIEWED_EVENTS[0])
        with patch.object(promo,'fetch',return_value='<html>news navigation only</html>'):
            checked,error=promo.check_existing(row)
        self.assertIn('근거 확인 실패',error)
        self.assertNotIn('content_checked_at',checked)
        self.assertNotIn('link_checked_at',checked)

    def test_reviewed_country_and_card_conditions_are_preserved(self):
        self.assertEqual(['JP','JP','KR'],[r['region'] for r in REVIEWED_EVENTS])
        birthday=REVIEWED_EVENTS[1]
        self.assertEqual('2026-11-02',birthday['announcement_date'])
        self.assertEqual('2026-11-01',birthday['start_date'])
        self.assertIn('TCG',birthday['reward'])
        self.assertTrue(all(promo.valid(r) for r in REVIEWED_EVENTS))

    def test_discovery_prioritizes_unseen_notices_with_the_same_budget(self):
        known='https://onepiece-cardgame.kr/known'
        index=('KR','원피스 카드','https://onepiece-cardgame.kr/events.do')
        markup=''.join(f'<a href="/{slug}">원피스 행사 2026.11.20 ~ 2026.12.01 {slug}</a>' for slug in ('known','new-a','new-b'))
        with tempfile.TemporaryDirectory() as folder:
            data=Path(folder)/'data.json';data.write_text(json.dumps({'items':[{'source':known}]}))
            with patch.object(promo,'DATA',data), patch.object(promo,'fetch',return_value=markup), \
                 patch.object(promo,'event_today',return_value=NOW.date()):
                rows,errors=promo.discover(index)
        self.assertEqual([],errors)
        self.assertEqual(['https://onepiece-cardgame.kr/new-a','https://onepiece-cardgame.kr/new-b'],[r['source'] for r in rows])

    def test_weekday_english_period_not_publication_date(self):
        text = '11/14/2026 Event Period: Friday, November 20th to Sunday, December 27th, 2026'
        self.assertEqual(('2026-11-20','2026-12-27'),promo.detail_date_range(text))
        self.assertEqual(('2026-11-01','2026-11-30'),promo.detail_date_range(
            '11/02/2026 Distribution Period: Sunday, November 1st to Monday, November 30th, 2026'))

    def test_recent_active_events_sort_before_old_campaigns_and_archive(self):
        old=self.row();new={**old,'name_ko':'새 영화','start_date':'2026-11-20','source':old['source']+'-new'}
        future={**old,'name_ko':'예정 행사','start_date':'2026-11-25'}
        tracking={**old,'name_ko':'확정되지 않은 추적','tracking_only':True,'date_precision':'unannounced'}
        result=project_events({'items':[old,tracking,future,new],'archive_items':[]},now=NOW)
        self.assertEqual(['새 영화','보존할 기존 행사','예정 행사','확정되지 않은 추적'],[r['name'] for r in result['rows']])
        self.assertEqual('2026-11-20 ~ 2026-12-01',result['rows'][0]['date_label'])


if __name__=='__main__':unittest.main()
