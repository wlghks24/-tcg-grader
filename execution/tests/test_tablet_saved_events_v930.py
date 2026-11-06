"""V930 offline proof that older KR/JP/US event records remain visible.

No network calls, camera control, real tablet files or collector writes.
"""
import json
from pathlib import Path
import tempfile
import unittest

from execution.tablet_saved_events_v930 import render_saved_events

ROOT = Path(__file__).resolve().parents[2]
BASE = {
    'game': '포켓몬 카드', 'region': 'JP', 'category': 'collaboration',
    'name_ko': '일본 카드짐 콜라보 행사 기록',
    'source': 'https://www.pokemon-card.com/info/005397.html',
    'source_grade': 'official', 'link_status': '정상',
    'link_checked_at': '2026-10-08T23:40:15+00:00',
    'start_date': '2026-03-01', 'end_date': '2026-08-31',
    'claim_deadline': '2026-10-31',
}


class SavedCountryEventsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / 'tcg_game_registry.json').write_bytes(
            (ROOT / 'tcg_game_registry.json').read_bytes())
        self.path = self.root / 'promo_events.json'

    def write(self, rows, archive=()):
        self.path.write_text(
            json.dumps({'items': rows, 'archive_items': list(archive)}, ensure_ascii=False),
            encoding='utf-8')

    def test_previous_korean_japanese_american_rows_all_visible(self):
        self.write([
            dict(BASE, game='포켓몬 카드', region='JP',
                 name_ko='일본 포켓몬 콜라보 확인'),
            dict(BASE, game='원피스 카드', region='KR',
                 name_ko='한국 원피스 프로모 확인'),
            dict(BASE, game='나루토 카드', region='US',
                 name_ko='미국 나루토 행사 확인'),
        ])
        before = self.path.read_bytes()
        all_html = render_saved_events(self.root)
        for title in ('일본 포켓몬 콜라보 확인', '한국 원피스 프로모 확인',
                      '미국 나루토 행사 확인'):
            self.assertIn(title, all_html)
        for region in ('한국', '일본', '미국'):
            self.assertIn(region + ' · ', all_html)
        self.assertIn('기존 자료 3건 중 현재 조건 3건', all_html)
        self.assertIn('출처 링크 점검은 행사 일정·증정카드·개최 확정을 의미하지 않습니다', all_html)
        self.assertEqual(before, self.path.read_bytes())

    def test_filter_by_exact_registry_game_id_and_country(self):
        self.write([
            dict(BASE, game='포켓몬 카드', region='JP',
                 name_ko='JP Pokémon collab'),
            dict(BASE, game='포켓몬 카드', region='KR',
                 name_ko='KR Pokémon event'),
            dict(BASE, game='원피스 카드', region='KR',
                 name_ko='KR One Piece promo'),
            dict(BASE, game='나루토 카드', region='US',
                 name_ko='US Naruto movie'),
        ])
        html = render_saved_events(self.root, game_id='pokemon', region='KR')
        self.assertIn('KR Pokémon event', html)
        for absent in ('JP Pokémon collab', 'KR One Piece promo', 'US Naruto movie'):
            self.assertNotIn(absent, html)
        self.assertIn('현재 조건 1건', html)
        self.assertIn('data-tcg930-game="pokemon"', html)
        other = render_saved_events(self.root, game_id='onepiece', region='KR')
        self.assertIn('KR One Piece promo', other)
        self.assertNotIn('KR Pokémon event', other)

    def test_original_archived_events_not_lost_or_misreported_as_current(self):
        self.write([], [dict(BASE, name_ko='지난 일본 콜라보 기록')])
        html = render_saved_events(self.root, game_id='pokemon', region='JP')
        self.assertIn('지난 일본 콜라보 기록', html)
        self.assertIn('지난 행사·종료 기록 1건', html)
        self.assertIn('<details>', html)
        self.assertIn('기존 자료 1건 중 현재 조건 1건', html)

    def test_unknown_game_remains_in_all_without_invented_registry_identity(self):
        self.write([dict(BASE, game='검증안된 새 카드게임',
                         region='KR', name_ko='미분류 기록')])
        all_html = render_saved_events(self.root)
        self.assertIn('미분류 기록', all_html)
        self.assertIn('게임명이 현재 등록정보와 연결되지 않은 기존 기록 1건', all_html)
        filtered = render_saved_events(self.root, game_id='pokemon', region='KR')
        self.assertNotIn('미분류 기록', filtered)
        self.assertIn('신규 검색 후보가 없다는 뜻은 아닙니다', filtered)

    def test_missing_or_bad_local_json_is_not_an_empty_verified_event_set(self):
        html = render_saved_events(self.root)
        self.assertIn('기존 행사 자료를 읽지 못했습니다', html)
        self.assertNotIn('기존 자료 0건 중', html)
        self.path.write_bytes(b'{"items":false}')
        before = self.path.read_bytes()
        self.assertIn('기존 행사 자료를 읽지 못했습니다',
                      render_saved_events(self.root))
        self.assertEqual(before, self.path.read_bytes())

    def test_untrusted_data_escaped_and_link_not_promoted_to_official(self):
        self.write([dict(BASE, name_ko='<script>alert(1)</script>',
                         source='javascript:alert(1)')])
        html = render_saved_events(self.root)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', html)
        self.assertNotIn('<script>alert(1)</script>', html)
        self.assertNotIn('href="javascript:', html)
        self.assertIn('유효한 출처 링크 없음', html)
        self.assertNotIn('공식 행사 확정', html)

    def test_partial_projection_preserves_error_counts_and_truncation(self):
        self.write([dict(BASE, name_ko='행사 ' + str(i)) for i in range(503)] + [None])
        html = render_saved_events(self.root, game_id='pokemon')
        self.assertIn('저장자료 표시 상한 500건', html)
        self.assertIn('형식·출처 확인이 필요한 기존 기록 1건', html)
        self.assertIn('기존 자료 503건 중 현재 조건 500건', html)

    def test_reject_unknown_filter_instead_of_cross_game_guess(self):
        self.write([BASE])
        with self.assertRaises(ValueError):
            render_saved_events(self.root, game_id='not-a-real-tcg')
        with self.assertRaises(ValueError):
            render_saved_events(self.root, region='KR;anything')


if __name__ == '__main__':
    unittest.main()
