"""Provider-label drift must not turn historical/graded prices into raw asks."""
import copy
import unittest
from unittest.mock import patch

import update_market_prices as market
from safe_runtime import html_to_text

KEY='US|NARUTO CP-001 Gen Con 2026|HIT'
PREFIX='Card language English Card Chakra Card CP-001 · Gen Con 2026 Ver. Price summary '
# Minimal synthetic fixture using observed labels, not provider price observations.
CURRENT=PREFIX+('Median of listings $120.25 Median of 4 eBay listings · updated today '
    'Lowest listed price $100.10 On eBay TCGplayer market price $70.00 '
    'PSA 10 (eBay) $999.00 Market data updated January 2, 2020 '
    'Price history 2020-01-01 Ungraded $1.00 $0.50')


class NarutoMarketSummaryTests(unittest.TestCase):
    def test_current_labels_select_raw_asking_summary_only(self):
        row=market.naruto_cp001_listing_summary(CURRENT)
        self.assertEqual(100.10,row['lowest_listing_usd'])
        self.assertEqual(120.25,row['reference_listing_usd'])
        self.assertEqual('median',row['reference_kind'])
        self.assertEqual(4,row['listing_count'])
        self.assertEqual('2020-01-02',row['source_date'])

    def test_legacy_labels_are_still_distinct_reference_prices(self):
        old=PREFIX+'Reference listing price $1,200.50 Cheapest listing $1,000.25 Listings 5 Market data updated January 2, 2020 Price history'
        row=market.naruto_cp001_listing_summary(old)
        self.assertEqual('reference',row['reference_kind'])
        self.assertEqual(5,row['listing_count'])
        self.assertEqual(1200.50,row['reference_listing_usd'])

    def test_actual_html_normalization_preserves_heading_and_labels(self):
        raw='<div>Card language</div><span>English</span><div>Card</div><h1>Chakra Card CP-001 &middot; Gen Con 2026 Ver.</h1><h2>Price summary</h2>'
        raw+='<p>'+CURRENT.split('Price summary ',1)[1].replace('Price history','</p><h2>Price history</h2>')+'</p>'
        self.assertIsNotNone(market.naruto_cp001_listing_summary(html_to_text(raw)))

    def test_different_card_edition_or_language_never_matches(self):
        for before,after in [('CP-001','CP-002'),('Gen Con 2026','Gen Con 2025'),('English','Japanese')]:
            with self.subTest(after=after):
                self.assertIsNone(market.naruto_cp001_listing_summary(CURRENT.replace(before,after)))

    def test_missing_duplicate_or_mixed_labels_do_not_fall_into_other_sections(self):
        for text in [CURRENT.replace('Lowest listed price $100.10',''),
                     CURRENT.replace('Median of listings','Reference listing price'),
                     CURRENT.replace('Price history','Missing history marker'),
                     CURRENT.replace('Lowest listed price $100.10','Lowest listed price $100.10 Lowest listed price $101.00'),
                     PREFIX+'PSA 10 $200.00 Market data updated January 2, 2020 Price history Cheapest listing $1 Reference listing price $2']:
            with self.subTest(text=text):self.assertIsNone(market.naruto_cp001_listing_summary(text))

    def test_zero_negative_inverted_and_malformed_amounts_fail_closed(self):
        for price in ['$0.00','$-1.00','$121.00','$NaN','$1,2,3.00','$1.234','$100000001.00','€100.10']:
            with self.subTest(price=price):
                self.assertIsNone(market.naruto_cp001_listing_summary(CURRENT.replace('$100.10',price)))

    def test_source_date_is_required_real_not_future_and_not_replaced_by_today(self):
        for before,after in [('January 2, 2020','February 31, 2020'),('January 2, 2020','January 2, 2099'),
                             ('Market data updated January 2, 2020',''),('Market data updated January 2, 2020','Market data updated January 2, 2020 Market data updated January 3, 2020')]:
            with self.subTest(after=after):self.assertIsNone(market.naruto_cp001_listing_summary(CURRENT.replace(before,after)))

    def test_refresh_records_asking_basis_cents_actual_date_and_exact_identity(self):
        db={'entries':{KEY:{'source_date':'2019-01-01','game':'NARUTO'}}}
        self.assertTrue(market.refresh_naruto_cp001_listing(db,CURRENT))
        row=db['entries'][KEY]
        self.assertEqual('$100.10~$120.25',row['display'])
        self.assertEqual('2020-01-02',row['source_date'])
        self.assertEqual('CP-001',row['card_number']);self.assertEqual('EN',row['language'])
        self.assertEqual(market.NARUTO_CP001_URL,row['source'])
        self.assertEqual('ungraded_asking_listings',row['price_basis'])
        self.assertIn('체결 확정가 아님',row['kind'])
        self.assertIn('중앙값',row['kind'])
        self.assertRegex(row['observed_at'],r'\+00:00$')
        self.assertNotIn('graded_prices',row)

    def test_failed_or_older_input_preserves_last_good_and_other_cards(self):
        for text in ['unknown page',CURRENT]:
            db={'entries':{KEY:{'source_date':'2020-01-03','display':'old'},'other':{'display':'unrelated'}}}
            prior=copy.deepcopy(db)
            with patch.object(market,'set_price',side_effect=AssertionError('must not modify last-good')):
                self.assertFalse(market.refresh_naruto_cp001_listing(db,text))
            self.assertEqual(prior,db)

    def test_unknown_listing_count_remains_unknown(self):
        row=market.naruto_cp001_listing_summary(CURRENT.replace('Median of 4 eBay listings','count unavailable'))
        self.assertIsNone(row['listing_count'])

    def test_zero_listing_count_cannot_support_a_median(self):
        self.assertIsNone(market.naruto_cp001_listing_summary(CURRENT.replace('Median of 4 eBay listings','Median of 0 eBay listings')))

    def test_unbounded_or_non_text_input_is_rejected(self):
        for text in [None,{},'x'*2_000_001,CURRENT.replace('Price history','x'*6001+'Price history')]:
            self.assertIsNone(market.naruto_cp001_listing_summary(text))


if __name__=='__main__':unittest.main()
