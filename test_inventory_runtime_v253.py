from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent


class InventoryRuntimeV253Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = (ROOT / 'inventory_lookup.js').read_text(encoding='utf-8')
        cls.html = (ROOT / 'index.html').read_text(encoding='utf-8')
        cls.server = (ROOT / 'tcg_updater.py').read_text(encoding='utf-8')

    def test_inventory_ui_is_delivered_and_mounted(self):
        self.assertIn('inventory_lookup.js', self.html)
        self.assertIn('inventory_lookup.css', self.html)
        self.assertIn("document.getElementById('purchaseLive')", self.js)
        self.assertIn("id='officialInventoryLookup'", self.js.replace('"', "'"))
        self.assertIn("window.runOfficialInventoryLookup=run", self.js)

    def test_query_and_game_are_encoded_before_api_call(self):
        self.assertIn("encodeURIComponent(q)", self.js)
        self.assertIn("encodeURIComponent(game)", self.js)
        self.assertIn("/api/inventory-lookup?q=", self.js)
        self.assertIn("if(!q)", self.js)

    def test_server_route_is_bounded_and_origin_guarded(self):
        self.assertIn("if path=='/api/inventory-lookup':", self.server)
        self.assertIn("len(q)>120 or len(game)>40", self.server)
        route = self.server.split("if path=='/api/inventory-lookup':", 1)[1].split("if path=='/api/purchase-live-search':", 1)[0]
        self.assertIn('_search_origin_allowed()', route)
        self.assertIn('get_inventory_options(q,game)', route)
        self.assertNotIn('urlopen(', route)
        self.assertNotIn('requests.', route)

    def test_ui_never_labels_all_sources_realtime(self):
        self.assertIn('store_stock_lookup', self.js)
        self.assertIn('guided_stock_check', self.js)
        self.assertIn('online_store_availability', self.js)
        self.assertIn('phone_confirmation', self.js)
        self.assertIn('실시간 재고조회', self.js)


if __name__ == '__main__':
    unittest.main()
