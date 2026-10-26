"""V679 preview allowlist, traversal and method-policy regression tests."""
from __future__ import annotations

import functools
import http.client
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import urlparse

from execution.tablet_v679_preview import V679_FILES, V679PreviewHandler

FILES = {
    "/docs/tablet/v679/tablet_unified_dashboard_v679.html": b"<html>V679</html>",
    "/docs/tablet/v679/tablet_unified_dashboard_v679.css": b"body{}",
    "/docs/tablet/v679/tablet_unified_dashboard_v679.js": b"'use strict';",
}


class V679PreviewRouteTests(unittest.TestCase):
    def _fixture(self, root):
        for name, payload in FILES.items():
            path = root / name.lstrip("/")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        (root / ".git").mkdir()
        (root / ".git/config").write_text("secret")

    def _allowed(self, root, path):
        h = V679PreviewHandler.__new__(V679PreviewHandler)
        h.directory = str(root)
        h.path = path
        return h._safe_static(urlparse(path).path)

    def test_exact_static_only(self):
        self.assertEqual(set(FILES), set(V679_FILES))
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._fixture(root)
            for path in FILES:
                self.assertTrue(self._allowed(root, path), path)
            for path in (
                "/docs/tablet/v679/private.json",
                "/docs/tablet/v679/tablet_unified_dashboard_v679.js?x=1",
                "/docs/tablet/v679/tablet_unified_dashboard_v679.js%2f..",
                "/docs/tablet/v679/../v679/tablet_unified_dashboard_v679.js",
                "/.git/config",
            ):
                self.assertFalse(self._allowed(root, path), path)

    def test_symlink_denied_each_path_component(self):
        for depth in range(1, 5):
            with self.subTest(depth=depth), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                self._fixture(root)
                path = next(n for n in FILES if n.endswith(".js"))
                segments = path.lstrip("/").split("/")
                link = root.joinpath(*segments[:depth])
                link.rename(link.with_name(link.name + "-real"))
                link.symlink_to(link.with_name(link.name + "-real"), target_is_directory=depth < 4)
                self.assertFalse(self._allowed(root, path))

    def test_http_get_head_post_and_private_denial(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._fixture(root)
            h = functools.partial(V679PreviewHandler, directory=str(root))
            server = ThreadingHTTPServer(("127.0.0.1", 0), h)
            th = threading.Thread(target=server.serve_forever, daemon=True)
            th.start()
            try:
                for name, payload in FILES.items():
                    for method in ("GET", "HEAD"):
                        with self.subTest(name=name, method=method):
                            status, body = self._request(server.server_port, method, name)
                            self.assertEqual(200, status)
                            self.assertEqual(payload if method == "GET" else b"", body)
                for method, path, expected in (
                    ("GET", "/.git/config", 404),
                    ("GET", "/docs/tablet/v679/private.json", 404),
                    ("HEAD", "/api/health", 404),
                    ("GET", "/docs/tablet/v679/tablet_unified_dashboard_v679.js?x=1", 404),
                    ("POST", "/api/run-auto-update", 405),
                ):
                    with self.subTest(path=path, method=method):
                        self.assertEqual(expected, self._request(server.server_port, method, path)[0])
            finally:
                server.shutdown()
                server.server_close()
                th.join(timeout=5)

    @staticmethod
    def _request(port, method, path):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=4)
        try:
            conn.request(method, path)
            r = conn.getresponse()
            return r.status, r.read()
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
