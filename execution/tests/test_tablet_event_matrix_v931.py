"""V931 independent evidence-lane regressions; all input fixtures are offline."""
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from xml.sax.saxutils import escape

from execution import tablet_event_coverage_v896 as discovery
from execution import tablet_event_matrix_v931 as matrix

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 6, 0, 30, tzinfo=timezone.utc)


class EventMatrixV931Tests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / 'tcg_game_registry.json').write_bytes(
            (ROOT / 'tcg_game_registry.json').read_bytes())

    def store(self, items=None, archive=()):
        payload = {'items': items or [], 'archive_items': list(archive)}
        (self.root / 'promo_events.json').write_text(
            json.dumps(payload, ensure_ascii=False), encoding='utf-8')

    def event(self, game, region, name):
        return {'game': game, 'region': region, 'category': 'collaboration',
                'name_ko': name,
                'source': 'https://www.pokemon-card.com/info/005397.html',
                'source_grade': 'official', 'link_status': '정상',
                'link_checked_at': '2026-11-05T00:30:00+00:00',
                'start_date': '2026-11-01', 'end_date': '2026-11-10'}

    def test_full_registry_not_inferred_as_events_or_successful_queries(self):
        self.store([])
        before = (self.root/'promo_events.json').read_bytes()
        snapshot = matrix.summarize(self.root, now=NOW)
        self.assertEqual(30, snapshot['registered_games'])
        self.assertEqual(55, snapshot['search_cells'])
        self.assertEqual(3, sum(x['state']=='core' for x in snapshot['game_rows']))
        self.assertEqual(9, sum(x['state']=='promoted' for x in snapshot['game_rows']))
        self.assertEqual(18, sum(x['state']=='watch' for x in snapshot['game_rows']))
        self.assertEqual('NOT_RECORDED', snapshot['discovery_status'])
        self.assertEqual(0, snapshot['saved_total'])
        self.assertTrue(all(c['search_status']=='NOT_SEARCHED'
                            for g in snapshot['game_rows'] for c in g['cells']
                            if c['configured']))
        kr = [c for g in snapshot['game_rows'] for c in g['cells']
              if c['region'] == 'KR']
        self.assertEqual(30, len(kr))
        self.assertEqual(6, sum(c['configured'] for c in kr))
        self.assertEqual(24, sum(c['search_status']=='KR_NOT_CONFIGURED' for c in kr))
        page = matrix.render(self.root, now=NOW)
        self.assertIn('등록 30종 · 검색 대상 55개 국가 조합', page)
        self.assertIn('한국 검색 범위 미설정 · 실제 행사 유무 미확인', page)
        self.assertIn('신규 검색 기록 파일 없음', page)
        self.assertIn('공식 승격 전 · 검색 후보만 표시', page)
        self.assertEqual(before,(self.root/'promo_events.json').read_bytes())

    def test_noncore_saved_and_archived_country_rows_are_retained(self):
        self.store([
            self.event('건담 카드', 'JP', '일본 건담 행사'),
            self.event('유니버서스', 'US', '미국 유니버서스 행사'),
        ], [
            self.event('고질라 카드게임', 'GLOBAL', '고질라 글로벌 기록'),
        ])
        value = matrix.summarize(self.root, now=NOW)
        by_id = {g['id']: g for g in value['game_rows']}
        self.assertEqual(1, next(c for c in by_id['gundam']['cells']
                                 if c['region']=='JP')['saved_active'])
        self.assertEqual(1, next(c for c in by_id['universus']['cells']
                                 if c['region']=='US')['saved_active'])
        extra = next(c for c in by_id['godzilla-card-game']['cells']
                     if c['region']=='GLOBAL')
        self.assertEqual(1, extra['saved_archive'])
        self.assertFalse(extra['configured'])
        self.assertEqual('NOT_CONFIGURED', extra['search_status'])
        self.assertEqual(2, sum(c['configured'] for c in by_id['godzilla-card-game']['cells']))
        page = matrix.render(self.root, now=NOW)
        self.assertIn('검색 대상 외 기존 저장 지역',page)
        self.assertIn('고질라 카드게임',page)
        self.assertNotIn('공식 확인 행사 3건',page)

    def test_unconfirmed_bing_candidate_not_promoted_to_saved_events(self):
        self.store([])
        cell = next(c for c in discovery.cells(
            __import__('tcg_game_registry').load_registry(self.root))
                    if c['game_id']=='gundam' and c['region']=='JP')
        title='GUNDAM CARD GAME collaboration promo'
        rss = ('<rss><channel><item><title>' + escape(title) +
               '</title><link>https://example.org/gundam-event</link>'
               '</item></channel></rss>').encode()
        lead = discovery.parse_rss(rss, cell, NOW)[0]
        self.assertFalse(lead['verified'])
        self.assertEqual('UNKNOWN',lead['region'])
        payload = {'version':896,'cursor':'gundam/JP',
                   'cells':{'gundam/JP':{
                       'attempted_at': NOW.isoformat(),
                       'requests':2,'successes':2,'results':1,'errors':[]
                   }},'items':[lead]}
        p = self.root / discovery.STATE
        p.write_text(json.dumps(payload),encoding='utf-8')
        original=p.read_bytes()
        x=matrix.summarize(self.root,now=NOW)
        g=next(g for g in x['game_rows'] if g['id']=='gundam')
        jp=next(c for c in g['cells'] if c['region']=='JP')
        self.assertEqual('SEARCHED_UNCONFIRMED',jp['search_status'])
        self.assertEqual(1,jp['candidate_leads'])
        self.assertEqual(0,jp['saved_active'])
        page=matrix.render(self.root,now=NOW)
        self.assertIn('1건 (미확인 후보)',page)
        self.assertIn('검색 완료 · 행사 미검증',page)
        self.assertEqual(original,p.read_bytes())

    def test_invalid_coverage_and_missing_saved_are_not_empty_success(self):
        p = self.root / discovery.STATE
        p.write_text('{"version":896,"items":false}')
        r=matrix.summarize(self.root,now=NOW)
        self.assertEqual('READ_ERROR',r['discovery_status'])
        self.assertEqual('READ_ERROR',r['saved_status'])
        page=matrix.render(self.root,now=NOW)
        self.assertIn('검색 기록 읽기 오류',page)
        self.assertIn('기존 행사 저장소 읽기 오류',page)
        self.assertIn('확인 보류',page)
        self.assertNotIn('기존 저장 0건',page)

    def test_stale_search_not_reported_as_verified_or_current(self):
        self.store([])
        p=self.root/discovery.STATE
        p.write_text(json.dumps({'version':896,'cursor':'',
                    'cells':{'gundam/JP':{'attempted_at':'2026-10-01T00:00:00+00:00',
                    'requests':2,'successes':2,'results':0,'errors':[]}},
                    'items':[]}))
        page=matrix.render(self.root,now=NOW)
        self.assertIn('재검색 필요',page)
        self.assertNotIn('공식 행사 확인 완료',page)

    def test_unmapped_saved_game_is_not_silently_attributed_to_other_tcg(self):
        self.store([self.event('알 수 없는 새 게임','US','불분명 행사')])
        v=matrix.summarize(self.root,now=NOW)
        self.assertEqual(1,v['saved_unmapped'])
        self.assertEqual(1,v['saved_total'])
        self.assertIn('등록 게임명에 정확히 연결되지 않은 저장 기록 1건',
                      matrix.render(self.root,now=NOW))
        self.assertEqual(0,sum(c['saved_active'] or 0
                               for g in v['game_rows'] for c in g['cells']))

    def test_invalid_clock_is_rejected(self):
        self.store([])
        with self.assertRaises(ValueError):
            matrix.summarize(self.root,now=datetime(2026,11,6))


if __name__=='__main__':
    unittest.main()
