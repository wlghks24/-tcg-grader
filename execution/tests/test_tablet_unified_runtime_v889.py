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
        h.do_GET()
        self.assertEqual(200, h.code)
        page = h.wfile.getvalue().decode()
        self.assertIn('data:image/', page)
        self.assertIn('001', page)
        self.assertIn('/api/local-card-images/auto-start', page)
        self.assertIn('기존 홈·이벤트', page)
        h.client_address = ('192.168.0.2', 1234)
        h.do_GET()
        self.assertEqual(403, h.code)
