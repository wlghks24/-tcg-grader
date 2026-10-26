"""V677 exact static gallery route regression (GET/HEAD, negative security cases)."""
from __future__ import annotations

import functools
import http.client
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest

from tcg_updater import Handler, V677_PREVIEW_STATIC_FILES


ASSETS = {
    "docs/tablet/v676/tablet_unified_dashboard_v676.html": b"<!doctype html><title>Safe review</title>",
    "docs/tablet/v676/tablet_unified_dashboard_v676.css": b"body{color:#123456}",
    "docs/tablet/v676/tablet_unified_dashboard_v676.js": b"'use strict';",
}


def prepare(root):
    for name, value in {**ASSETS, "index.html": b"legacy-index"}.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(value)
    (root / "docs/tablet/v676/private-model.json").write_text('{"secret":1}')
    (root / ".git").mkdir()
    (root / ".git/config").write_text("private")


def check(root, request):
    # Check the real Handler predicate, not a reimplemented copy.
    h = Handler.__new__(Handler)
    h.directory = str(root)
    h.path = request
    from urllib.parse import urlparse
    return h._safe_static(urlparse(request).path)


class V677StaticGuardTests(unittest.TestCase):
    def test_only_exact_three_nested_assets_are_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            prepare(base)
            self.assertEqual(set(ASSETS), V677_PREVIEW_STATIC_FILES)
            for name in ASSETS:
                with self.subTest(name=name):
                    self.assertTrue(check(base, "/" + name))
            self.assertTrue(check(base, "/index.html"))
            for name in (
                "/docs/tablet/v676/private-model.json",
                "/docs/tablet/v676/other.css",
                "/docs/tablet/v676/",
                "/docs/tablet/v676/../v676/tablet_unified_dashboard_v676.js",
                "/docs/tablet/v676/%2e%2e/index.html",
                "/docs/tablet/v676/tablet_unified_dashboard_v676.js?version=2",
                "//docs/tablet/v676/tablet_unified_dashboard_v676.js",
                "/docs/tablet/v676/tablet_unified_dashboard_v676.js#fragment",
                "/docs/tablet/v676/tablet_unified_dashboard_v676.js/extra",
                "/docs/tablet/v676/tablet_unified_dashboard_v676.js%2f..",
                "/.git/config",
            ):
                with self.subTest(name=name):
                    self.assertFalse(check(base, name))

    def test_intermediate_and_final_symlinks_denied(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            prepare(base)
            target = base / "docs/tablet/v676/tablet_unified_dashboard_v676.js"
            target.unlink()
            target.symlink_to(base / "index.html")
            self.assertFalse(check(base, "/" + list(ASSETS)[2]))
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            (base / "docs").symlink_to(base / "outside")
            (base / "outside/tablet/v676").mkdir(parents=True)
            (base / "outside/tablet/v676/tablet_unified_dashboard_v676.js").write_text("bad")
            self.assertFalse(check(base, "/docs/tablet/v676/tablet_unified_dashboard_v676.js"))

    def test_http_get_head_and_404_public_boundary(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            prepare(root)
            handler = functools.partial(Handler, directory=str(root))
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                for name, payload in ASSETS.items():
                    for method in ("GET", "HEAD"):
                        with self.subTest(name=name, method=method):
                            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                            try:
                                conn.request(method, "/" + name)
                                response = conn.getresponse()
                                body = response.read()
                                self.assertEqual(200, response.status)
                                self.assertEqual(str(len(payload)), response.getheader("Content-Length"))
                                self.assertEqual(payload if method == "GET" else b"", body)
                            finally:
                                conn.close()
                for method in ("GET", "HEAD"):
                    for bad in (
                        "/docs/tablet/v676/private-model.json",
                        "/docs/tablet/v676/tablet_unified_dashboard_v676.js?cache=x",
                        "/docs/tablet/v676/../v676/tablet_unified_dashboard_v676.js",
                        "/.git/config",
                    ):
                        with self.subTest(method=method, path=bad):
                            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                            try:
                                conn.request(method, bad)
                                response = conn.getresponse()
                                response.read()
                                self.assertEqual(404, response.status)
                            finally:
                                conn.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
