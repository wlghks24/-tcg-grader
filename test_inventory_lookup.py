import unittest
import inventory_lookup

class InventoryLookupTests(unittest.TestCase):
    def test_only_verified_realtime_sources_are_marked(self):
        data=inventory_lookup.get_inventory_options('포켓몬 카드','Pokemon')
        self.assertTrue(data['ok'])
        self.assertGreaterEqual(len(data['items']),3)
        for row in data['items']:
            self.assertTrue(row['realtime'])
            self.assertEqual(row['verification'],'official')
            self.assertTrue(row['url'].startswith('https://'))
    def test_known_official_inventory_services_present(self):
        retailers={x['retailer'] for x in inventory_lookup.OFFICIAL_LOOKUPS}
        self.assertTrue({'CU','GS25','이마트24'}.issubset(retailers))
    def test_unsupported_sources_never_claim_stock(self):
        data=inventory_lookup.get_inventory_options('원피스','ONE PIECE')
        self.assertIn('세븐일레븐',data['unsupported'])
        self.assertNotIn('stock_qty',data)

if __name__=='__main__':
    unittest.main()
