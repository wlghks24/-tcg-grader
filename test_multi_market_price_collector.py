import unittest
from unittest import mock
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

    def test_card_number_matching_is_exact_not_substring(self):
        self.assertFalse(m._card_number_matches('001','1001'))
        self.assertTrue(m._card_number_matches('001','SV1-001'))
        self.assertTrue(m._card_number_matches('OP13-007','OP13-007'))
        self.assertFalse(m._card_number_matches('OP13-007','OP14-007'))
        self.assertFalse(m._card_number_matches('SVI001','SVI1001'))

    def test_justtcg_rejects_substring_card_number_collision(self):
        fx={'KRW':1.0,'USD':1400.0,'JPY':9.0}
        payload={'data':[{'name':'Pikachu','number':'1001','variants':[{'price':10.0,'condition':'NM','printing':'Normal'}]}]}
        with mock.patch.dict(m.os.environ,{'JUSTTCG_API_KEY':'token'}), mock.patch.object(m,'_json_request',return_value=payload):
            rows,status=m._justtcg_api('Pikachu 001','pokemon',fx,'US')
        self.assertEqual(status,'ok')
        self.assertEqual(rows,[])

    def test_tcgdex_rejects_substring_card_number_collision(self):
        fx={'KRW':1.0,'USD':1400.0,'JPY':9.0}
        def fake_json(url,*args,**kwargs):
            if '/cards?' in url:return [{'id':'sv01-1001'}]
            return {'name':'Pikachu','localId':'1001','pricing':{'tcgplayer':{'updated':'2026-09-25','normal':{'marketPrice':10.0}}}}
        with mock.patch.object(m,'_json_request',side_effect=fake_json):
            rows,status=m._tcgdex_api('Pikachu 001','pokemon',fx,'US')
        self.assertEqual(status,'ok')
        self.assertEqual(rows,[])

    def test_grade_reference_prefers_completed_sales_without_mixing_asking_prices(self):
        items=[
            {'title':'Pikachu PSA 10 sold','price_kind':'실거래/완료 신호','price_krw':100000,'verified_api':False},
            {'title':'Pikachu PSA 10','price_kind':'API 현재가','price_krw':200000,'verified_api':True},
            {'title':'Pikachu PSA 10','price_kind':'판매중','price_krw':500000,'verified_api':True},
        ]
        row=next(x for x in m._grade_reference(items) if x['grade']=='PSA 10')
        self.assertEqual(row['price_krw'],100000)
        self.assertEqual(row['basis'],'완료거래')
        self.assertEqual(row['completed_count'],1)
        self.assertEqual(row['api_reference_count'],1)
        self.assertEqual(row['asking_count'],1)
        self.assertEqual(row['total_count'],3)
        chosen,basis=m._comparable_summary_items('Pikachu PSA 10',items)
        self.assertEqual([x['price_krw'] for x in chosen],[100000])
        self.assertEqual(basis,'PSA 10 · 완료거래')

    def test_grade_reference_uses_api_reference_before_asking_when_no_completed_sale(self):
        items=[
            {'title':'Pikachu PSA 9','price_kind':'API 현재가','price_krw':180000,'verified_api':True},
            {'title':'Pikachu PSA 9','price_kind':'판매중','price_krw':400000,'verified_api':True},
        ]
        row=next(x for x in m._grade_reference(items) if x['grade']=='PSA 9')
        self.assertEqual(row['price_krw'],180000)
        self.assertEqual(row['basis'],'API 참고시세')
        self.assertEqual(row['count'],1)

if __name__=='__main__':
    unittest.main()
