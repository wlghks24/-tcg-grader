import unittest
import grading_proxy_costs as g

class ProxyCostTests(unittest.TestCase):
    def test_baseline_has_supported_graders(self):
        graders={x['grader'] for x in g.BASELINE}
        self.assertTrue({'PSA','BGS','CGC','BRG'}.issubset(graders))
    def test_hobby_korea_psa_public_prices(self):
        row=next(x for x in g.BASELINE if x['provider']=='HOBBY KOREA' and x['grader']=='PSA')
        prices={s['name']:s['price_krw'] for s in row['services']}
        self.assertEqual(prices['Regular'],160000)
        self.assertEqual(prices['Express'],300000)
    def test_dynamic_quotes_never_fake_numeric_price(self):
        for row in g.BASELINE:
            if row['pricing_type']=='dynamic_quote':
                self.assertFalse(row.get('proxy_fee_from_krw'))
                self.assertEqual(row.get('services',[]),[])
    def test_card_lab_separates_proxy_fee_from_actual(self):
        rows=[x for x in g.BASELINE if x['provider']=='CARD LAB BUSAN']
        self.assertTrue(rows)
        self.assertTrue(all(x['pricing_type']=='proxy_fee_plus_actual' for x in rows))
        self.assertTrue(all(x['proxy_fee_from_krw']>0 for x in rows))

if __name__=='__main__': unittest.main()
