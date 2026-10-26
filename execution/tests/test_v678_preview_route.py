"""Independent V678 preview tests: immutable updater, exact assets and HTTP behavior."""
from __future__ import annotations

import functools
import http.client
import json
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from execution.tablet_v678_preview import PREVIEW_FILES, PreviewHandler

FILES = {
    "/docs/tablet/v676/tablet_unified_dashboard_v676.html": b"<html>Preview</html>",
    "/docs/tablet/v676/tablet_unified_dashboard_v676.css": b"body{margin:0}",
    "/docs/tablet/v676/tablet_unified_dashboard_v676.js": b"'use strict';",
    "/docs/tablet/v679/tablet_unified_dashboard_v679.html": b"<html>V679 Preview</html>",
    "/docs/tablet/v679/tablet_unified_dashboard_v679.js": b"v679-code",
}


def prepare(root):
    for path, contents in {**FILES, "/index.html": b"legacy-home",
                           "/promo_events.json": b"[]"}.items():
        dest = root / path.lstrip("/")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(contents)
    hidden = root / "docs/tablet/v676/private-model.json"
    hidden.write_text('{"secret":1}')
    (root / ".git").mkdir()
    (root / ".git/config").write_text("no-peek")


def predicate(root, path):
    handler = PreviewHandler.__new__(PreviewHandler)
    handler.directory = str(root)
    handler.path = path
    from urllib.parse import urlparse
    return handler._safe_static(urlparse(path).path)


@contextmanager
def local_preview(root):
    handler = functools.partial(PreviewHandler, directory=str(root))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def response_details(port, method, path, headers=(), *, default_host=True):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=4)
    try:
        conn.putrequest(method, path, skip_host=not default_host)
        for name, value in headers:
            conn.putheader(name, value)
        conn.endheaders()
        response = conn.getresponse()
        return response.status, response.read(), response.headers
    finally:
        conn.close()


class ImmutablePreviewTests(unittest.TestCase):
    def test_exact_nested_allowlist_and_default_private_paths(self):
        self.assertEqual(PREVIEW_FILES, frozenset(FILES))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare(root)
            for name in FILES:
                with self.subTest(path=name):
                    self.assertTrue(predicate(root, name))
            for name in (
                "/docs/tablet/v676/private-model.json",
                "/docs/tablet/v679/private-model.json",
                "/docs/tablet/v679/tablet_unified_dashboard_v679.js?x=1",
                "/docs/tablet/v676/tablet_unified_dashboard_v676.html?x=1",
                "/docs/tablet/v676/tablet_unified_dashboard_v676.js#fragment",
                "/docs/tablet/v676/tablet_unified_dashboard_v676.js%2f..",
                "/docs/tablet/v676/../v676/tablet_unified_dashboard_v676.js",
                "/docs/tablet/v676/%2e%2e/index.html",
                "//docs/tablet/v676/tablet_unified_dashboard_v676.html",
                "/.git/config",
            ):
                with self.subTest(path=name):
                    self.assertFalse(predicate(root, name))

    def test_symlink_denied_at_any_depth(self):
        for index in (1, 2, 3, 4):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                prepare(root)
                target = "/docs/tablet/v676/tablet_unified_dashboard_v676.js"
                parts = target.lstrip("/").split("/")
                link = root.joinpath(*parts[:index])
                link.rename(link.with_name(link.name + "-old"))
                link.symlink_to(link.with_name(link.name + "-old"), target_is_directory=index < len(parts))
                self.assertFalse(predicate(root, target))

    def test_loopback_get_head_and_post_restrictions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare(root)
            handler = functools.partial(PreviewHandler, directory=str(root))
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                for path, payload in FILES.items():
                    for method in ("GET", "HEAD"):
                        with self.subTest(path=path, method=method):
                            status, body = self.request(server.server_port, method, path)
                            self.assertEqual(200, status)
                            self.assertEqual(payload if method == "GET" else b"", body)
                for method, path, expect in (
                    ("GET", "/docs/tablet/v676/private-model.json", 404),
                    ("HEAD", "/.git/config", 404),
                    ("GET", "/api/health", 404),
                    ("GET", "/docs/tablet/v676/tablet_unified_dashboard_v676.js?x=1", 404),
                    ("POST", "/api/run-auto-update", 405),
                ):
                    with self.subTest(path=path, method=method):
                        status, _ = self.request(server.server_port, method, path)
                        self.assertEqual(expect, status)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_fixed_security_headers_and_no_origin_reflection_on_all_statuses(self):
        from tcg_updater import TRUSTED_PAGES_ORIGIN
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare(root)
            with local_preview(root) as port:
                target = next(iter(FILES))
                for origin in ('https://evil.example', TRUSTED_PAGES_ORIGIN):
                    for method, path, expected in (
                        ('GET', target, 200), ('HEAD', target, 200),
                        ('GET', '/not-allowlisted', 404), ('POST', target, 405),
                        ('HEAD', '/api/local-card-images', 405), ('TRACE', target, 501),
                        ('OPTIONS', target, 405), ('GET', '/', 302),
                    ):
                        with self.subTest(origin=origin, method=method, path=path):
                            status, body, headers = response_details(
                                port, method, path,
                                (('Origin', origin), ('Access-Control-Request-Private-Network', 'true')),
                            )
                            self.assertEqual(status, expected)
                            self.assertIsNone(headers.get('Access-Control-Allow-Origin'))
                            self.assertIsNone(headers.get('Access-Control-Allow-Private-Network'))
                            self.assertEqual(headers['Cross-Origin-Resource-Policy'], 'same-origin')
                            self.assertEqual(headers['Cross-Origin-Opener-Policy'], 'same-origin')
                            self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
                            self.assertEqual(headers['X-Frame-Options'], 'DENY')
                            self.assertIn("script-src 'self'", headers['Content-Security-Policy'])
                            self.assertNotIn('unsafe-inline', headers['Content-Security-Policy'])
                            self.assertNotIn('https:', headers['Content-Security-Policy'])
                            if method == 'HEAD':
                                self.assertEqual(body, b'')

    def test_etag_and_head_serve_same_literal_asset_without_reflecting_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare(root)
            path = '/docs/tablet/v676/tablet_unified_dashboard_v676.js'
            with local_preview(root) as port:
                status, body, headers = response_details(port, 'GET', path)
                self.assertEqual((status, body), (200, FILES[path]))
                etag = headers['ETag']
                self.assertTrue(etag.startswith('"') and etag.endswith('"'))
                status, body, head = response_details(port, 'HEAD', path)
                self.assertEqual((status, body), (200, b''))
                self.assertEqual(head['ETag'], etag)
                self.assertEqual(head['Content-Length'], str(len(FILES[path])))
                status, body, cached = response_details(
                    port, 'GET', path, (('If-None-Match', etag),),
                )
                self.assertEqual((status, body), (304, b''))
                self.assertEqual(cached['ETag'], etag)
                self.assertEqual(cached['Cache-Control'], 'private, no-cache, must-revalidate, max-age=0')
                self.assertIn("object-src 'none'", cached['Content-Security-Policy'])
                status, _, unchanged = response_details(
                    port, 'GET', path, (('If-None-Match', 'attacker-controlled-tag'),),
                )
                self.assertEqual(status, 200)
                self.assertEqual(unchanged['ETag'], etag)
                (root / path.lstrip('/')).write_bytes(b'new-version-with-new-size')
                status, body, changed = response_details(
                    port, 'GET', path, (('If-None-Match', etag),),
                )
                self.assertEqual((status, body), (200, b'new-version-with-new-size'))
                self.assertNotEqual(changed['ETag'], etag)

    def test_host_forgery_duplicate_and_missing_host_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare(root)
            with local_preview(root) as port:
                for hosts in (
                    (), ('evil.example',), ('127.0.0.1:1',),
                    ('127.0.0.1@evil.example',), ('localhost/path',),
                    (f'127.0.0.1:{port}', f'127.0.0.1:{port}'),
                ):
                    with self.subTest(hosts=hosts):
                        status, _, headers = response_details(
                            port, 'GET', '/', [('Host', host) for host in hosts], default_host=False,
                        )
                        self.assertEqual(status, 421)
                        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')

    def test_encoded_traversal_and_query_paths_never_serve_static_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare(root)
            with local_preview(root) as port:
                for path in (
                    '/docs/tablet/v676/../v676/tablet_unified_dashboard_v676.js',
                    '/docs/tablet/v676/%2e%2e/v676/tablet_unified_dashboard_v676.js',
                    '/docs%2ftablet/v676/tablet_unified_dashboard_v676.js',
                    '/docs/tablet/v676/tablet_unified_dashboard_v676.js%00',
                    '/docs/tablet/v676/tablet_unified_dashboard_v676.js?x=1',
                    '/promo_events.json?', '/index.html#fragment',
                    '/api/local-card-images?limit=1',
                    '/api/local-card-images/catalog-links?path=../../.git/config',
                ):
                    with self.subTest(path=path):
                        status, _, _ = response_details(port, 'GET', path)
                        self.assertEqual(status, 404)
                # Valid-looking file route prefix must still go through the
                # image ID validator, never the static-path resolver.
                import tablet_image_library_v1 as images
                with patch.object(images, 'storage_root', side_effect=AssertionError('unexpected storage access')):
                    for image_id in ('../index.html', '%2e%2e', 'a' * 33, 'A' * 32):
                        with self.subTest(image_id=image_id):
                            status, _, _ = response_details(port, 'GET', '/api/local-card-images/file/' + image_id)
                            self.assertEqual(status, 503)

    def test_learning_gap_endpoint_is_read_only_and_does_not_dispatch_other_apis(self):
        from execution import tablet_learning_gap_advisor_v676 as adviser
        payload = {'ok': True, 'query': {'remaining': 994}, 'physical_tablet_verified': False}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare(root)
            with local_preview(root) as port, patch.object(adviser, 'snapshot', return_value=payload) as snapshot:
                status, body, headers = response_details(port, 'GET', '/api/verified-learning-gaps')
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(body), payload)
                self.assertEqual(headers['Cache-Control'], 'no-store')
                snapshot.assert_called_once()
                for method, path, expected in (
                    ('POST', '/api/verified-learning-gaps', 405),
                    ('HEAD', '/api/verified-learning-gaps', 405),
                    ('GET', '/api/verified-learning-gaps?train=true', 404),
                    ('GET', '/api/train', 404), ('GET', '/api/health', 404),
                ):
                    with self.subTest(method=method, path=path):
                        status, _, _ = response_details(port, method, path)
                        self.assertEqual(status, expected)
                snapshot.assert_called_once()

    def test_legacy_home_redirects_only_to_literal_gallery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare(root)
            with local_preview(root) as port:
                for method in ('GET', 'HEAD'):
                    for path in ('/', '/index.html'):
                        with self.subTest(method=method, path=path):
                            status, body, headers = response_details(port, method, path)
                            self.assertEqual((status, body), (302, b''))
                            self.assertEqual(headers['Location'],
                                             '/docs/tablet/v679/tablet_unified_dashboard_v679.html')
                            self.assertEqual(headers['Content-Length'], '0')
                            self.assertEqual(headers['Cache-Control'], 'no-store')

    @staticmethod
    def request(port, method, path):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=4)
        try:
            conn.request(method, path)
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
