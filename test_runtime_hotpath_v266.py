from __future__ import annotations

import concurrent.futures
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import tcg_updater_v135


class RuntimeHotpathV266Tests(unittest.TestCase):
    def _handler(self, directory: str, headers: dict[str, str]):
        handler = object.__new__(tcg_updater_v135.Handler)
        handler.directory = directory
        handler.headers = headers
        handler.responses = []
        handler.sent_headers = []
        handler.body = bytearray()
        handler.send_response = lambda code: handler.responses.append(code)
        handler.send_header = lambda key, value: handler.sent_headers.append((key, value))
        handler.end_headers = lambda: None

        class Writer:
            def write(_self, value):
                handler.body.extend(value)

        handler.wfile = Writer()
        handler.json = lambda data, status=200: (data, status)
        return handler

    def _reset_dashboard_cache(self):
        with tcg_updater_v135.DASHBOARD_BUNDLE_LOCK:
            tcg_updater_v135.DASHBOARD_BUNDLE_CACHE['signature'] = None
            tcg_updater_v135.DASHBOARD_BUNDLE_CACHE['body'] = None
            tcg_updater_v135.DASHBOARD_BUNDLE_CACHE['etag'] = None

    def _reset_health_cache(self):
        with tcg_updater_v135.HEALTH_SNAPSHOT_LOCK:
            tcg_updater_v135.HEALTH_SNAPSHOT_CACHE['expires_at'] = 0.0
            tcg_updater_v135.HEALTH_SNAPSHOT_CACHE['value'] = None

    def test_dashboard_uses_strong_etag_and_304_without_body(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            names = (
                'graded_photo_dashboard.js',
                'manual_dual_photo_bridge.js',
                'manual_official_verify_bridge.js',
                'pending_official_candidate_bridge_v161.js',
            )
            for index, name in enumerate(names):
                (root / name).write_text(f'// {index}\n', encoding='utf-8')
            self._reset_dashboard_cache()

            first = self._handler(directory, {})
            tcg_updater_v135.Handler._serve_dashboard_with_manual_fallback(first)
            self.assertEqual(first.responses, [200])
            first_headers = dict(first.sent_headers)
            self.assertIn('ETag', first_headers)
            self.assertTrue(first_headers['ETag'].startswith('"'))
            self.assertTrue(first_headers['ETag'].endswith('"'))
            self.assertIn('no-cache', first_headers['Cache-Control'])
            self.assertNotIn('no-store', first_headers['Cache-Control'])
            self.assertGreater(len(first.body), 0)

            second = self._handler(directory, {'If-None-Match': first_headers['ETag']})
            tcg_updater_v135.Handler._serve_dashboard_with_manual_fallback(second)
            self.assertEqual(second.responses, [304])
            self.assertEqual(dict(second.sent_headers)['ETag'], first_headers['ETag'])
            self.assertEqual(len(second.body), 0)

    def test_dashboard_etag_changes_when_bundle_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            names = (
                'graded_photo_dashboard.js',
                'manual_dual_photo_bridge.js',
                'manual_official_verify_bridge.js',
                'pending_official_candidate_bridge_v161.js',
            )
            for index, name in enumerate(names):
                (root / name).write_text(f'// {index}\n', encoding='utf-8')
            self._reset_dashboard_cache()

            first = self._handler(directory, {})
            tcg_updater_v135.Handler._serve_dashboard_with_manual_fallback(first)
            old_etag = dict(first.sent_headers)['ETag']
            (root / names[0]).write_text('// changed payload\n', encoding='utf-8')

            changed = self._handler(directory, {'If-None-Match': old_etag})
            tcg_updater_v135.Handler._serve_dashboard_with_manual_fallback(changed)
            self.assertEqual(changed.responses, [200])
            self.assertNotEqual(dict(changed.sent_headers)['ETag'], old_etag)
            self.assertIn(b'changed payload', changed.body)

    def test_health_snapshot_cache_collapses_concurrent_poll_burst(self):
        self._reset_health_cache()
        original_ttl = tcg_updater_v135.HEALTH_SNAPSHOT_TTL_SECONDS
        tcg_updater_v135.HEALTH_SNAPSHOT_TTL_SECONDS = 5.0

        def slow_health():
            time.sleep(0.02)
            return {'healthy': True, 'requires_attention': False}

        def slow_neural():
            time.sleep(0.02)
            return {'ok': True, 'active': False}

        try:
            with mock.patch.object(tcg_updater_v135.core, 'collection_health_status', side_effect=slow_health) as health, \
                 mock.patch.object(tcg_updater_v135.core, 'collection_neural_status', side_effect=slow_neural) as neural:
                with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
                    rows = list(executor.map(lambda _: tcg_updater_v135._runtime_health_snapshot(), range(32)))
            self.assertEqual(health.call_count, 1)
            self.assertEqual(neural.call_count, 1)
            self.assertEqual(len(rows), 32)
            self.assertTrue(all(row['collection_health']['healthy'] for row in rows))
        finally:
            tcg_updater_v135.HEALTH_SNAPSHOT_TTL_SECONDS = original_ttl
            self._reset_health_cache()

    def test_health_snapshot_refreshes_after_expiry(self):
        self._reset_health_cache()
        original_ttl = tcg_updater_v135.HEALTH_SNAPSHOT_TTL_SECONDS
        tcg_updater_v135.HEALTH_SNAPSHOT_TTL_SECONDS = 5.0
        try:
            with mock.patch.object(tcg_updater_v135.core, 'collection_health_status', return_value={'healthy': True}) as health, \
                 mock.patch.object(tcg_updater_v135.core, 'collection_neural_status', return_value={'ok': True, 'active': False}) as neural:
                tcg_updater_v135._runtime_health_snapshot()
                tcg_updater_v135._runtime_health_snapshot()
                with tcg_updater_v135.HEALTH_SNAPSHOT_LOCK:
                    tcg_updater_v135.HEALTH_SNAPSHOT_CACHE['expires_at'] = 0.0
                tcg_updater_v135._runtime_health_snapshot()
            self.assertEqual(health.call_count, 2)
            self.assertEqual(neural.call_count, 2)
        finally:
            tcg_updater_v135.HEALTH_SNAPSHOT_TTL_SECONDS = original_ttl
            self._reset_health_cache()


if __name__ == '__main__':
    unittest.main()
