from __future__ import annotations

from pathlib import Path
import unittest

import multi_market_price_collector as market

ROOT = Path(__file__).resolve().parent


class CardMarketGradeSeparationV299Tests(unittest.TestCase):
    def test_non_psa_company_grades_are_never_classified_as_raw(self) -> None:
        cases = {
            'Pikachu BGS 9.5': 'BGS 9.5',
            'Pikachu CGC GEM MINT 10': 'CGC 10',
            'Pikachu TAG 8.5': 'TAG 8.5',
            'Pikachu BRG 9': 'BRG 9',
            'Pikachu PSA 10': 'PSA 10',
            'Pikachu raw': '미감정',
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(expected, market._grade_label({'title': title, 'price_krw': 10000}))

    def test_raw_headline_excludes_bgs_cgc_tag_brg_prices(self) -> None:
        items = [
            {'title': 'Pikachu raw', 'price_krw': 10000, 'source_id': 'raw'},
            {'title': 'Pikachu BGS 9.5', 'price_krw': 100000, 'source_id': 'bgs'},
            {'title': 'Pikachu CGC 10', 'price_krw': 120000, 'source_id': 'cgc'},
            {'title': 'Pikachu TAG 8.5', 'price_krw': 90000, 'source_id': 'tag'},
            {'title': 'Pikachu BRG 9', 'price_krw': 80000, 'source_id': 'brg'},
        ]
        comparable, basis = market._comparable_summary_items('Pikachu', items)
        self.assertEqual('미감정', basis)
        self.assertEqual([10000], [row['price_krw'] for row in comparable])

    def test_exact_non_psa_grade_query_uses_only_matching_grade(self) -> None:
        items = [
            {'title': 'Pikachu raw', 'price_krw': 10000, 'source_id': 'raw'},
            {'title': 'Pikachu BGS 9.5', 'price_krw': 100000, 'source_id': 'bgs'},
            {'title': 'Pikachu BGS 9', 'price_krw': 70000, 'source_id': 'bgs2'},
        ]
        comparable, basis = market._comparable_summary_items('Pikachu BGS 9.5', items)
        self.assertEqual('BGS 9.5', basis)
        self.assertEqual([100000], [row['price_krw'] for row in comparable])

    def test_grade_reference_keeps_dynamic_company_grades_separate(self) -> None:
        rows = market._grade_reference([
            {'title': 'Pikachu raw', 'price_krw': 10000},
            {'title': 'Pikachu BGS 9.5', 'price_krw': 100000},
            {'title': 'Pikachu CGC 10', 'price_krw': 120000},
        ])
        by_grade = {row['grade']: row for row in rows}
        self.assertEqual(10000, by_grade['미감정']['price_krw'])
        self.assertEqual(100000, by_grade['BGS 9.5']['price_krw'])
        self.assertEqual(120000, by_grade['CGC 10']['price_krw'])

    def test_frontend_never_floors_half_grade_to_integer_price(self) -> None:
        source = (ROOT / 'grade_market_flow.js').read_text(encoding='utf-8')
        start = source.index('function gradeSale(company,grade){')
        end = source.index('\nfunction updateGrades', start)
        body = source[start:end]
        self.assertNotIn('Math.floor(Number(grade))', body)
        self.assertIn('[...gr.options].some(option=>option.value===exact)', body)
        self.assertIn('finally{comp.value=oldC;gr.value=oldG}', body)
        self.assertIn('const sale=gradeSale(c,g);', source)
        self.assertNotIn('sale=gradeSale(c,rounded)', source)


if __name__ == '__main__':
    unittest.main(verbosity=2)
