import unittest
import multi_market_price_collector as m

class MultiMarketPriceCollectorTests(unittest.TestCase):
    def test_required_sources_present(self):
        names={x['name'] for x in m.SOURCES}
        for name in ['eBay','Amazon US','Amazon JP','KREAM','당근','번개장터','중고나라','Collectory','TCGplayer','Cardmarket','Mercari JP','Yahoo! Auctions JP','SNKRDUNK','JustTCG','TCGdex','Pavilion TCG']:
            self.assertIn(name,names)
    def test_price_parser_converts_krw_usd_jpy(self):
        fx={'KRW':1.0,'USD':1400.0,'JPY':9.0}
        self.assertEqual(m._extract_price('가격 ₩12,000',fx)['price_krw'],12000)
        self.assertEqual(m._extract_price('price $10.00',fx)['price_krw'],14000)
        self.assertEqual(m._extract_price('price ¥2,000',fx)['price_krw'],18000)
    def test_learning_health_is_bounded(self):
        self.assertGreaterEqual(m._health('x',{}),.75)
        self.assertLessEqual(m._health('x',{}),1.15)
    def test_empty_query_never_generates_price(self):
        out=m.search_multi_market('',force=True)
        self.assertFalse(out['ok'])
        self.assertEqual(out['items'],[])

if __name__=='__main__':
    unittest.main()
