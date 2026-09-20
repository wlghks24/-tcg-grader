from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import tcg_updater_v135


class DashboardEtagV265Tests(unittest.TestCase):
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

    def test_dashboard_etag_revalidation_avoids_second_body_transfer(self):
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
            with tcg_updater_v135.DASHBOARD_BUNDLE_LOCK:
                tcg_updater_v135.DASHBOARD_BUNDLE_CACHE['signature'] = None
                tcg_updater_v135.DASHBOARD_BUNDLE_CACHE['body'] = None
                tcg_updater_v135.DASHBOARD_BUNDLE_CACHE['etag'] = None

            first = self._handler(directory, {})
            tcg_updater_v135.Handler._serve_dashboard_with_manual_fallback(first)
            self.assertEqual(first.responses, [200])
            first_headers = dict(first.sent_headers)
            self.assertIn('ETag', first_headers)
            self.assertIn('no-cache', first_headers['Cache-Control'])
            self.assertNotIn('no-store', first_headers['Cache-Control'])
            self.assertGreater(len(first.body), 0)

            second = self._handler(directory, {'If-None-Match': first_headers['ETag']})
            tcg_updater_v135.Handler._serve_dashboard_with_manual_fallback(second)
            self.assertEqual(second.responses, [304])
            self.assertEqual(dict(second.sent_headers)['ETag'], first_headers['ETag'])
            self.assertEqual(len(second.body), 0)


if __name__ == '__main__':
    unittest.main()
