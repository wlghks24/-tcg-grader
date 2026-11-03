"""Real shared-budget collector call, no live requests or server deployment."""
import threading
from unittest.mock import patch
from execution.tests import test_image_metadata_enrichment as fixtures
from execution import tablet_unified_runtime_v889 as runtime
import tablet_image_auto_v2 as auto
import tablet_image_library_v1 as library


class IntegratedCycleTests(fixtures.ImageMetadataTests):
    def test_existing_worker_entry_repairs_set_only_photo_and_keeps_original(self):
        saved = self.save({'set_code': 'sv1s'})
        before = library.get_image(saved['id'])
        with patch.object(auto, '_candidate_batches', return_value=[]), patch.object(auto, 'fetch_json', return_value={
                'id': 'sv1s-001', 'localId': '001', 'set': {'id': 'sv1s'}}) as fetch:
            result = runtime.collect_once(self.repo, sleeper=lambda _: None)
        self.assertEqual(1, result['metadata_enriched'])
        self.assertEqual(1, result['metadata_repair_attempted'])
        self.assertEqual(1, fetch.call_count)
        self.assertEqual(before, library.get_image(saved['id']))
        self.assertEqual('001', library.list_images()['items'][0]['card_metadata']['card_number'])
        self.assertEqual(result, auto._state(self.store)['last_result'])
        self.assertIsNone(getattr(auto._BUDGET_CONTEXT, 'current', None))

    def test_repair_and_original_collector_share_identical_budget(self):
        self.save({})
        seen = []
        def repair(*args, **kwargs):
            seen.append(auto._BUDGET_CONTEXT.current)
            return {'attempted': 0, 'enriched': 0, 'issues': [], 'deferred': False}
        original = auto._collect_once
        def collect(*args, **kwargs):
            self.assertIs(seen[0], auto._BUDGET_CONTEXT.current)
            return original(*args, **kwargs)
        with patch.object(runtime, 'repair_existing', side_effect=repair), patch.object(auto, '_collect_once', side_effect=collect), patch.object(auto, 'fetch_json', return_value={'id': 'sv1s-001', 'set': {'id': 'sv1s'}}), patch.object(auto, '_candidate_batches', return_value=[]):
            runtime.collect_once(self.repo)

    def test_install_refuses_second_scheduler(self):
        from types import SimpleNamespace
        fake = SimpleNamespace(Handler=object)
        with patch.object(runtime, '_INSTALLED', False), patch.object(auto, '_SCHEDULER', object()):
            with self.assertRaises(RuntimeError):
                runtime.install(fake)
        self.assertIs(fake.Handler, object)

    def test_install_is_idempotent_and_existing_worker_uses_new_cycle(self):
        from types import SimpleNamespace
        class Base:
            pass
        fake = SimpleNamespace(Handler=Base)
        with patch.object(runtime, '_INSTALLED', False), patch.object(auto, 'collect_once', runtime._ORIGINAL_COLLECT), patch.object(auto, '_THREAD', None), patch.object(auto, '_SCHEDULER', None):
            runtime.install(fake)
            first = fake.Handler
            runtime.install(fake)
            self.assertIs(first, fake.Handler)
            self.assertIs(auto.collect_once, runtime.collect_once)
            self.assertTrue(issubclass(first, Base))

    def test_unified_http_route_contains_real_photo_metadata_and_collection_button(self):
        import io
        self.save({'set_code': 'sv1s', 'card_number': '001'})
        class Base:
            def _require_request_host(self): return True
            def send_response(self, code): self.code = code
            def send_header(self, key, value): pass
            def end_headers(self): pass
            def json(self, payload, code=200): self.code, self.payload = code, payload
            def do_GET(self): self.fallback = True
        h = runtime.make_handler(Base)()
        h.path = '/tablet-unified'
        h.directory = str(self.repo)
        h.client_address = ('127.0.0.1', 1234)
        h.wfile = io.BytesIO()
        (self.repo / 'index.html').write_text('<body><a class="feature-shortcut" href="#releaseBoard" data-feature-key="promo-event-info">행사<small>설명</small></a></body>')
        h.do_GET()
        self.assertEqual(200, h.code)
        page = h.wfile.getvalue().decode()
        self.assertIn('data:image/', page)
        self.assertIn('001', page)
        self.assertIn('/api/local-card-images/auto-start', page)
        self.assertIn('기존 홈·이벤트', page)
        self.assertIn("connect-src 'self'", page)
        h.path = '/index.html'
        h.wfile = io.BytesIO()
        h.do_GET()
        self.assertIn('TCG 카드·BOX 라이브러리', h.wfile.getvalue().decode())
        h.path = '/index.html?view=classic'
        h.wfile = io.BytesIO()
        h.do_GET()
        self.assertIn('data-feature-key="promo-event-info"', h.wfile.getvalue().decode())
        h.client_address = ('192.168.0.2', 1234)
        h.do_GET()
        self.assertEqual(403, h.code)

    def test_all_existing_feature_menus_survive_in_new_navigation(self):
        from pathlib import Path
        import re
        root = Path(__file__).resolve().parents[2]
        original = (root / 'index.html').read_text()
        keys = set(re.findall(r'data-feature-key="([^"]+)"', original))
        navigation = runtime.feature_navigation(root)
        self.assertGreaterEqual(len(keys), 18)
        for key in keys:
            self.assertIn('/index.html?feature=' + key, navigation)
        self.assertIn('프로모', navigation)
        self.assertIn('구매', navigation)
        self.assertIn('학습', navigation)

    def test_rebound_host_is_rejected_before_any_private_data_read(self):
        import io
        class Base:
            def _require_request_host(self):
                self.code = 421
                return False
            def do_GET(self):
                raise AssertionError('rejected request reached fallback')
        h = runtime.make_handler(Base)()
        h.client_address = ('127.0.0.1', 1234)
        h.directory = str(self.repo)
        h.wfile = io.BytesIO()
        for path in ('/tablet-events-all', '/tablet-unified', '/api/local-card-images/catalog-links', '/index.html',
                     '/tablet_market_hub_v881.html', '/any-other-route'):
            h.path = path
            with patch.object(runtime, 'read_live') as read, patch.object(runtime, 'export_html') as export:
                h.do_GET()
                read.assert_not_called()
                export.assert_not_called()
            self.assertEqual(421, h.code)
        self.assertEqual(b'', h.wfile.getvalue())

    def test_registry_event_route_filters_and_preserves_loopback_guard(self):
        import io
        import shutil
        from pathlib import Path
        shutil.copyfile(Path(__file__).resolve().parents[2] / 'tcg_game_registry.json', self.repo / 'tcg_game_registry.json')
        class Base:
            def _require_request_host(self): return True
            def send_response(self, code): self.code = code
            def send_header(self, key, value): pass
            def end_headers(self): pass
            def json(self, payload, code=200): self.code, self.payload = code, payload
            def do_GET(self): raise AssertionError('event route reached fallback')
        h = runtime.make_handler(Base)()
        h.path = '/tablet-events-all?game=mtg&region=US'
        h.directory = str(self.repo)
        h.client_address = ('127.0.0.1', 1234)
        h.wfile = io.BytesIO()
        h.do_GET()
        self.assertEqual(200, h.code)
        page = h.wfile.getvalue().decode()
        self.assertIn('전체 TCG', page)
        self.assertIn('NOT_SEARCHED', page)
        self.assertIn('value="mtg" selected', page)
        self.assertIn('<option selected>US', page)
        h.client_address = ('192.168.0.2', 1234)
        h.do_GET()
        self.assertEqual(403, h.code)
