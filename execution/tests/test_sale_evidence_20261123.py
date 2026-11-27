"""Sale-state regressions: synthetic observations, mocked search, no data writes."""
from contextlib import ExitStack
from datetime import datetime, timezone
import unittest
from unittest import mock

import multi_market_price_collector as market


class SaleEvidenceTests(unittest.TestCase):
    def item(self, text, price=100000, **extra):
        return {'title': 'Pikachu 025 PSA 10 ' + text, 'snippet': '',
                'price_krw': price, 'source_id': 'fixture',
                'source_date': datetime.now(timezone.utc).date().isoformat(), **extra}

    def assert_excluded(self, text):
        row = self.item(text, price_kind='실거래/완료 신호', verified_api=True)
        self.assertEqual('excluded', market._price_evidence_class(row))
        selected, basis, buckets = market._select_price_evidence([row])
        self.assertEqual([], selected)
        self.assertEqual('자료 없음', basis)
        self.assertEqual({'completed': [], 'api_reference': [], 'asking': []}, buckets)

    def test_unsold_is_not_a_completed_or_asking_price(self):
        self.assert_excluded('unsold $100')

    def test_not_sold_and_never_sold(self):
        for text in ('not sold', 'never sold', 'not-yet sold', 'not yet been sold'):
            with self.subTest(text=text): self.assert_excluded(text)

    def test_english_negated_completion(self):
        for text in ('not completed sale', 'uncompleted auction', "hasn't sold", 'has not been sold', "isn’t sold"):
            with self.subTest(text=text): self.assert_excluded(text)

    def test_sold_out_and_out_of_stock_are_inventory_states(self):
        for text in ('sold out', 'SOLD-OUT', 'out of stock'):
            with self.subTest(text=text): self.assert_excluded(text)

    def test_sold_by_is_seller_attribution(self):
        self.assert_excluded('sold by seller ABC')

    def test_korean_incomplete_sales(self):
        for text in ('미판매', '미체결', '미낙찰', '거래미완료', '판매 미완료'):
            with self.subTest(text=text): self.assert_excluded(text)

    def test_korean_postfixed_negation(self):
        for text in ('판매완료 아님', '판매 완료가 아닙니다', '거래완료 아닌 상품', '체결 전', '낙찰 예정'):
            with self.subTest(text=text): self.assert_excluded(text)

    def test_cancelled_transaction_does_not_become_a_price(self):
        for text in ('판매완료 취소', '거래 취소', 'sale cancelled', 'cancelled transaction', 'auction was canceled'):
            with self.subTest(text=text): self.assert_excluded(text)

    def test_no_sale_or_bids_overrides_completed_auction(self):
        for text in ('completed auction no bids', 'auction completed no sale'):
            with self.subTest(text=text): self.assert_excluded(text)

    def test_inventory_korean_is_excluded(self):
        for text in ('품절', '재고 없음'):
            with self.subTest(text=text): self.assert_excluded(text)

    def test_word_boundaries_preserve_product_names_as_asking(self):
        for text in ('Soldier', 'Bestsoldier', 'soldier completed collection', 'completed set'):
            with self.subTest(text=text):
                self.assertEqual('asking', market._price_evidence_class(self.item(text)))

    def test_affirmative_sale_signals_remain_compatible(self):
        for text in ('sold', 'SOLD $100', 'completed sale', 'transaction completed',
                     'completed auction', '판매완료', '거래 완료', '낙찰', '체결'):
            with self.subTest(text=text):
                self.assertEqual('completed', market._price_evidence_class(self.item(text)))

    def test_unrelated_no_returns_does_not_negate_a_sale(self):
        self.assertEqual('completed', market._price_evidence_class(self.item('sold no returns')))

    def test_snippet_contradiction_overrides_title_and_persisted_kind(self):
        row = self.item('sold', snippet='판매완료 아님', price_kind='실거래/완료 신호')
        self.assertEqual('excluded', market._price_evidence_class(row))

    def test_verified_api_reference_remains_available(self):
        row = self.item('', price_kind='API 현재가', verified_api=True)
        self.assertEqual('api_reference', market._price_evidence_class(row))
        asking = self.item('', price_kind='판매중', verified_api=True)
        self.assertEqual('asking', market._price_evidence_class(asking))

    def test_unsold_cannot_override_api_grade_reference(self):
        bad = self.item('unsold', price_kind='실거래/완료 신호')
        api = self.item('', 200000, price_kind='API 현재가', verified_api=True, source_id='api')
        row = next(x for x in market._grade_reference([bad, api]) if x['grade'] == 'PSA 10')
        self.assertEqual((200000, 'API 참고시세', 0, 1, 0, 2),
                         tuple(row[k] for k in ('price_krw', 'basis', 'completed_count',
                                               'api_reference_count', 'asking_count', 'total_count')))

    def test_excluded_direct_recommendation_and_breakdown_are_empty(self):
        bad = self.item('unsold')
        out = market._recommendation_from_comparable([bad], '완료거래')
        self.assertEqual(0, out['recommended_trade_krw'])
        self.assertEqual('hold', out['recommendation_confidence'])
        self.assertEqual([], market._source_price_breakdown([bad], '완료거래'))
        self.assertEqual([], market._source_evidence_breakdown([bad]))

    def search(self, titles, api=True):
        rows = [{'title': 'Pikachu 025 PSA 10 ' + title + ' $100', 'snippet': '',
                 'url': f'https://www.ebay.com/itm/{i}',
                 'date': datetime.now(timezone.utc).date().isoformat()} for i, title in enumerate(titles)]
        reference = self.item('', 200000, source_id='justtcg', source='JustTCG',
                              price_kind='API 현재가', verified_api=True,
                              url='https://justtcg.com/card/025')
        source = {'id': 'ebay', 'name': 'eBay', 'domain': 'ebay.com', 'weight': 1.0, 'kind': '판매중'}
        with ExitStack() as stack:
            for name, value in {'SOURCES': [source]}.items():
                stack.enter_context(mock.patch.object(market, name, value))
            for name, value in {'_fx': {'USD': 1000.0, 'KRW': 1.0}, '_learning': {},
                                '_cooling': False, '_health': 1.0, '_ebay_api': [],
                                '_justtcg_api': ([reference] if api else [], 'ok'),
                                '_tcgdex_api': ([], 'ok'), '_rss': rows}.items():
                stack.enter_context(mock.patch.object(market, name, return_value=value))
            stack.enter_context(mock.patch.object(market, '_save_learning'))
            stack.enter_context(mock.patch.object(market, '_save_cache'))
            stack.enter_context(mock.patch.object(market, 'safe_urlopen', side_effect=AssertionError('network forbidden')))
            return market.search_multi_market('Pikachu 025 PSA 10', force=True)

    def test_search_retains_negative_observations_without_price_contamination(self):
        out = self.search(['unsold', 'sold out', 'Soldier'])
        self.assertEqual(200000, out['summary']['median_krw'])
        self.assertEqual('PSA 10 · API 참고시세', out['summary']['basis'])
        rejected = [x for x in out['items'] if x['evidence_class'] == 'excluded']
        self.assertEqual(2, len(rejected))
        self.assertTrue(all(x['summary_eligible'] is False for x in rejected))
        self.assertTrue(all(x['price_krw'] == 100000 for x in rejected))
        self.assertTrue(all(x['price_kind'] == '미판매/취소/품절 · 요약 제외' for x in rejected))
        self.assertEqual(4, out['summary']['observed_total_count'])
        self.assertEqual(2, out['summary']['evidence_excluded_count'])
        self.assertEqual(0, out['summary']['identity_excluded_count'])
        self.assertEqual('asking', next(x for x in out['items'] if 'Soldier' in x['title'])['evidence_class'])

    def test_search_affirmative_completed_sale_is_still_preferred(self):
        out = self.search(['sold no returns'])
        self.assertEqual(100000, out['summary']['median_krw'])
        self.assertEqual('PSA 10 · 완료거래', out['summary']['basis'])
        self.assertEqual('실거래/완료 신호', next(x for x in out['items'] if not x['verified_api'])['price_kind'])

    def test_search_only_unsold_holds_price_without_deleting_observations(self):
        out = self.search(['unsold', 'sold out'], api=False)
        self.assertEqual(0, out['summary']['median_krw'])
        self.assertEqual(0, out['summary']['count'])
        self.assertEqual(2, out['summary']['observed_total_count'])
        self.assertEqual(2, out['summary']['evidence_excluded_count'])
        self.assertEqual(0, out['summary']['identity_excluded_count'])
        self.assertEqual(2, len(out['items']))


if __name__ == '__main__':
    unittest.main()
