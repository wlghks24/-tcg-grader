#!/usr/bin/env python3
import unittest
from unittest import mock
import multi_market_price_collector as m

class CardVariantMarketPrecisionV323Tests(unittest.TestCase):
    def test_variant_normalization_separates_finishes_and_art(self):
        self.assertEqual('standard',m._card_variant('normal'))
        self.assertEqual('reverse_holo',m._card_variant('ReverseHolofoil'))
        self.assertEqual('holo',m._card_variant('Holofoil'))
        self.assertEqual('parallel',m._card_variant('Parallel card'))
        self.assertEqual('manga',m._card_variant('Manga Rare'))
        self.assertEqual('alt_art',m._card_variant('Alternate Art'))

    def test_exact_card_number_still_rejects_wrong_variant(self):
        item={'title':'Pikachu PAL 185/193 Holofoil','snippet':'','card_number':'PAL185/193'}
        ok,basis=m._item_identity_eligibility('Pikachu PAL185/193 Reverse Holo',item,'US')
        self.assertFalse(ok)
        self.assertEqual('variant_mismatch',basis)

    def test_explicit_wrong_edition_is_excluded(self):
        item={'title':'Pikachu PAL 185/193 Japanese version','snippet':'','card_number':'PAL185/193'}
        ok,basis=m._item_identity_eligibility('Pikachu PAL185/193',item,'US')
        self.assertFalse(ok)
        self.assertEqual('edition_explicit_mismatch',basis)

    def test_variant_unspecified_is_ambiguous_when_multiple_finishes_exist(self):
        rows=[{'title':'Pikachu PAL185/193 normal','price_krw':10000},{'title':'Pikachu PAL185/193 reverse holo','price_krw':20000}]
        state=m._variant_summary_state('Pikachu PAL185/193',rows)
        self.assertTrue(state['ambiguous'])
        self.assertEqual({'standard','reverse_holo'},set(state['observed']))

    def test_search_suppresses_mixed_variant_headline_and_grade_reference(self):
        ebay=[
            {'source':'eBay','source_id':'ebay','title':'Pikachu PAL185/193 normal sold','snippet':'','url':'https://www.ebay.com/itm/1','price_krw':10000,'price_native':10,'currency':'USD','price_kind':'실거래/완료 신호','verified_api':True,'date':'','score':1},
            {'source':'eBay','source_id':'ebay','title':'Pikachu PAL185/193 reverse holo sold','snippet':'','url':'https://www.ebay.com/itm/2','price_krw':20000,'price_native':20,'currency':'USD','price_kind':'실거래/완료 신호','verified_api':True,'date':'','score':1},
        ]
        with mock.patch.object(m,'_ebay_api',return_value=ebay), mock.patch.object(m,'_justtcg_api',return_value=([],'not_configured')), mock.patch.object(m,'_tcgdex_api',return_value=([],'ok')), mock.patch.object(m,'_rss',return_value=[]), mock.patch.object(m,'_fx',return_value={'USD':1000,'JPY':10,'EUR':1500,'KRW':1}), mock.patch.object(m,'_learning',return_value={}), mock.patch.object(m,'_save_learning'), mock.patch.object(m,'_save_cache'), mock.patch.object(m,'_cached',return_value=None):
            result=m.search_multi_market('Pikachu PAL185/193',region='US',game='pokemon',force=True)
        self.assertTrue(result['summary']['variant_ambiguous'])
        self.assertEqual(0,result['summary']['median_krw'])
        self.assertEqual([],result['grade_reference'])

    def test_requested_variant_keeps_only_matching_finish(self):
        reverse={'title':'Pikachu PAL185/193 reverse holo sold','snippet':'','card_number':'PAL185/193','price_krw':20000}
        normal={'title':'Pikachu PAL185/193 normal sold','snippet':'','card_number':'PAL185/193','price_krw':10000}
        self.assertTrue(m._item_identity_eligibility('Pikachu PAL185/193 reverse holo',reverse,'US')[0])
        self.assertFalse(m._item_identity_eligibility('Pikachu PAL185/193 reverse holo',normal,'US')[0])

if __name__=='__main__':
    unittest.main(verbosity=2)
