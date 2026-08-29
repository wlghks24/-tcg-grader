import unittest
import inventory_lookup

class InventoryLookupTests(unittest.TestCase):
    def test_all_sources_are_official_https_and_truthful(self):
        data=inventory_lookup.get_inventory_options('포켓몬 카드','Pokemon')
        self.assertTrue(data['ok'])
        self.assertGreaterEqual(len(data['items']),8)
        for row in data['items']:
            self.assertEqual(row['verification'],'official')
            self.assertTrue(row['url'].startswith('https://'))
            self.assertIn(row['capability'],{
                'realtime_stock','store_stock_lookup','guided_stock_check',
                'online_store_availability','phone_confirmation'
            })
    def test_realtime_sources_are_only_real_realtime_lookup(self):
        realtime={x['retailer'] for x in inventory_lookup.OFFICIAL_LOOKUPS if x.get('realtime')}
        self.assertTrue({'CU','GS25','이마트24','이마트'}.issubset(realtime))
        self.assertNotIn('코스트코',realtime)
        self.assertNotIn('홈플러스',realtime)
    def test_major_marts_are_present(self):
        retailers={x['retailer'] for x in inventory_lookup.OFFICIAL_LOOKUPS}
        self.assertTrue({'이마트','롯데마트','트레이더스','홈플러스','코스트코'}.issubset(retailers))
    def test_lottemart_uses_official_stock_lookup(self):
        row=next(x for x in inventory_lookup.OFFICIAL_LOOKUPS if x['retailer']=='롯데마트')
        self.assertEqual(row['capability'],'store_stock_lookup')
        self.assertIn('lottemart.com',row['url'])
    def test_unsupported_sources_never_claim_stock(self):
        data=inventory_lookup.get_inventory_options('원피스','ONE PIECE')
        self.assertIn('세븐일레븐',data['unsupported'])
        self.assertNotIn('stock_qty',data)

if __name__=='__main__':
    unittest.main()
