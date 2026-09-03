import unittest

import release_history_backfill as backfill


class ReleaseHistoryCoverageV4Tests(unittest.TestCase):
    def test_expected_matrix_is_three_games_by_three_regions(self):
        self.assertEqual(len(backfill.EXPECTED_CELLS), 9)
        self.assertEqual(
            set(backfill.EXPECTED_CELLS),
            {(game, region) for game in ("Pokémon", "ONE PIECE", "NARUTO") for region in ("KR", "JP", "US")},
        )

    def test_korean_pokemon_exact_release_date_is_kept(self):
        rows = backfill.parse_pokemon_kr(
            'MEGA 확장팩 「스톰에메랄다」 2026년 9월 16일 발매 가격 30,000원'
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['region'], 'KR')
        self.assertEqual(rows[0]['release_date'], '2026-09-16')

    def test_korean_pokemon_month_does_not_invent_a_day(self):
        rows = backfill.parse_pokemon_kr(
            'MEGA 확장팩 「테스트팩」 2027년 3월 발매 예정'
        )
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0].get('release_date'))
        self.assertEqual(rows[0]['release_window'], '2027-03')
        self.assertEqual(rows[0]['release_precision'], 'month')

    def test_event_only_korean_date_is_not_a_release(self):
        rows = backfill.parse_pokemon_kr(
            '포켓몬 카드 게임 챔피언십 2026년 9월 16일 개최 참가 접수 이벤트'
        )
        self.assertEqual(rows, [])

    def test_us_pokemon_launch_date_is_parsed(self):
        rows = backfill.parse_pokemon_us(
            'Pokémon TCG: 30th Celebration Launch: September 16, 2026 '
            'This Pokémon TCG expansion includes booster packs.'
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['region'], 'US')
        self.assertEqual(rows[0]['release_date'], '2026-09-16')

    def test_naruto_requires_release_confirmation(self):
        self.assertEqual(backfill.parse_naruto_region('NARUTO CARD GAME tutorial sessions 2026', 'US'), [])
        rows = backfill.parse_naruto_region(
            'Arriving in Summer 2027 NARUTO CARD GAME GLOBAL RELEASE CONFIRMED', 'US'
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['release_window'], '2027년 여름')
        self.assertEqual(rows[0]['region'], 'US')

    def test_progress_reports_missing_cells_without_fabricating_rows(self):
        progress = backfill.coverage_progress([])
        self.assertEqual(progress['expected_cells'], 9)
        self.assertEqual(progress['verified_cells'], 0)
        self.assertEqual(len(progress['missing_verified_cells']), 9)


if __name__ == '__main__':
    unittest.main()
