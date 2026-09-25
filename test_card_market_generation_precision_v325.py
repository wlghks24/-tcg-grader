#!/usr/bin/env python3
import subprocess
import unittest
from unittest import mock
import multi_market_price_collector as m

class CardMarketGenerationPrecisionV325Tests(unittest.TestCase):
    def _search(self,query,region,rss,api_rows=None):
        with mock.patch.object(m,'_ebay_api',return_value=api_rows or []), mock.patch.object(m,'_justtcg_api',return_value=([],'not_configured')), mock.patch.object(m,'_tcgdex_api',return_value=([],'ok')), mock.patch.object(m,'_rss',return_value=rss), mock.patch.object(m,'_fx',return_value={'USD':1000,'JPY':10,'EUR':1500,'KRW':1}), mock.patch.object(m,'_learning',return_value={}), mock.patch.object(m,'_save_learning'), mock.patch.object(m,'_save_cache'), mock.patch.object(m,'_cached',return_value=None):
            return m.search_multi_market(query,region=region,game='pokemon',force=True)

    def test_name_only_query_never_builds_headline_or_grade_price(self):
        rows=[{'source':'eBay','source_id':'ebay','title':'Pikachu English card sold','snippet':'','url':'https://www.ebay.com/itm/1','price_krw':10000,'price_native':10,'currency':'USD','price_kind':'실거래/완료 신호','verified_api':True,'date':'','score':1}]
        result=self._search('Pikachu','US',[],rows)
        self.assertEqual('name_only_hold',result['summary']['identity_scope'])
        self.assertTrue(result['summary']['identity_ambiguous'])
        self.assertEqual(0,result['summary']['median_krw'])
        self.assertEqual([],result['grade_reference'])
        self.assertGreaterEqual(len(result['items']),1)

    def test_requested_region_is_not_self_attested_on_rss_result(self):
        result=self._search('Pikachu PAL185/193','US',[{'title':'Pikachu PAL185/193 $10','url':'https://www.ebay.com/itm/1','snippet':'current price $10','date':''}])
        matched=[row for row in result['items'] if row.get('source_id')=='ebay']
        self.assertTrue(matched)
        self.assertEqual('ALL',matched[0]['region_scope'])

    def test_explicit_rss_edition_is_preserved(self):
        result=self._search('Pikachu PAL185/193','US',[{'title':'Pikachu PAL185/193 English version $10','url':'https://www.ebay.com/itm/1','snippet':'sold $10','date':''}])
        matched=[row for row in result['items'] if row.get('source_id')=='ebay']
        self.assertTrue(matched)
        self.assertEqual('US',matched[0]['region_scope'])

    def test_generation_runtime_fail_closes_year_only_evidence(self):
        proc=subprocess.run(['node','verify_pokemon_generation_runtime.js'],capture_output=True,text=True,encoding='utf-8',errors='replace',check=False)
        self.assertEqual(0,proc.returncode,proc.stderr or proc.stdout)
        self.assertIn('v325: PASS',proc.stdout)

if __name__=='__main__':
    unittest.main(verbosity=2)
