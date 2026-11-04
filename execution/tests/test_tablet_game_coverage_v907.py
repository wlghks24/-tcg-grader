"""All-game, all-country coverage cannot turn missing providers into fake evidence."""
import unittest

from execution.tablet_game_coverage_v907 import snapshot, render

GAMES = {
    'pokemon': {'label_ko': '포켓몬', 'state': 'core'},
    'onepiece': {'label_ko': '원피스', 'state': 'core'},
    'naruto': {'label_ko': '나루토', 'state': 'core'},
    'watchgame': {'label_ko': '<미확인&게임>', 'state': 'watch'},
}
PROVIDERS = {('pokemon', 'JP'): 'TCGdex', ('onepiece', 'US'): 'PunkRecords'}


class CoverageTests(unittest.TestCase):
    def test_every_game_and_five_edition_buckets_exist_even_with_no_cards(self):
        data = snapshot(GAMES, [], providers=PROVIDERS, view_state='COMPLETE')
        self.assertEqual(4, data['game_count'])
        self.assertEqual(20, sum(len(game['cells']) for game in data['games']))
        self.assertEqual(2, data['configured_pairs'])
        self.assertEqual(['naruto', 'onepiece', 'pokemon', 'watchgame'],
                         [game['game_id'] for game in data['games']])
        naruto = next(game for game in data['games'] if game['game_id'] == 'naruto')
        self.assertTrue(all(cell['provider'] == '' and cell['observed']['rows'] == 0
                            for cell in naruto['cells']))
        page = render(data)
        self.assertIn('나루토', page)
        self.assertIn('자동수집기 미연결', page)
        self.assertIn('중국 간체', page)
        self.assertIn('대만 번체', page)
        self.assertIn('&lt;미확인&amp;게임&gt;', page)
        self.assertNotIn('<미확인&게임>', page)

    def test_crossgame_country_and_product_numbers_never_merge(self):
        rows = [
            {'game_id': 'pokemon', 'region': 'JP', 'kind': 'CARD', 'image_id': 'photo',
             'source_record_id': 'source', 'link_status': 'VERIFIED_PAIR',
             'card_facts': {'prices': [{'amount': 1}]}, 'observed_release_date': '2026-01-01'},
            {'game_id': 'onepiece', 'region': 'US', 'kind': 'BOX', 'source_record_id': 'source2',
             'link_status': 'NEEDS_IMAGE', 'market_quote': {'display': '$20'}},
            {'game_id': 'naruto', 'region': 'CN-S', 'kind': 'PROMO', 'image_id': 'photo3',
             'link_status': 'NEEDS_EXACT_IDENTITY'},
        ]
        data = snapshot(GAMES, rows, providers=PROVIDERS, view_state='COMPLETE')
        def cell(game, region):
            return next(c for g in data['games'] if g['game_id'] == game
                        for c in g['cells'] if c['region'] == region)
        self.assertEqual(1, cell('pokemon', 'JP')['observed']['exact_pairs'])
        self.assertEqual(1, cell('pokemon', 'JP')['observed']['price_refs'])
        self.assertEqual(1, cell('onepiece', 'US')['observed']['products'])
        self.assertEqual(0, cell('onepiece', 'US')['observed']['images'])
        self.assertEqual(1, cell('naruto', 'CN-S')['observed']['cards'])
        self.assertEqual('', cell('naruto', 'CN-S')['provider'])
        self.assertEqual(0, cell('naruto', 'CN-T')['observed']['rows'])
        self.assertEqual(0, cell('pokemon', 'US')['observed']['rows'])

    def test_subset_registry_does_not_require_unrelated_configured_providers(self):
        providers = {**PROVIDERS, ('extra-game', 'KR'): 'OtherApprovedProvider'}
        data = snapshot(GAMES, [], providers=providers, view_state='COMPLETE')
        self.assertEqual(2, data['configured_pairs'])
        self.assertNotIn('extra-game', [game['game_id'] for game in data['games']])


    def test_partial_view_never_claims_complete_coverage(self):
        data = snapshot(GAMES, [], providers=PROVIDERS, view_state='PARTIAL_READ_ONLY')
        self.assertIn('부분 조회 · 미확인', render(data))
        self.assertIn('비어 있는 칸을 카드 부재로 판단하지 않습니다', render(data))

    def test_unknown_game_region_and_provider_are_fail_closed(self):
        for row in ({'game_id': 'unknown', 'region': 'JP'}, {'game_id': 'naruto', 'region': 'JP2'}):
            with self.assertRaises(ValueError):
                snapshot(GAMES, [row], providers=PROVIDERS, view_state='COMPLETE')
        for providers in ({('naruto', 'XX'): 'unknown'}, {('not<script>', 'JP'): 'unknown'}):
            with self.assertRaises(ValueError):
                snapshot(GAMES, [], providers=providers, view_state='COMPLETE')


if __name__ == '__main__':
    unittest.main()
