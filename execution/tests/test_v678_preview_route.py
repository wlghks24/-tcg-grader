"""Independent V678 preview tests: immutable updater, exact assets and HTTP behavior."""
from __future__ import annotations

import functools
import http.client
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest

from execution.tablet_v678_preview import PREVIEW_FILES, PreviewHandler

FILES = {
    "/docs/tablet/v676/tablet_unified_dashboard_v676.html": b"<html>Preview</html>",
    "/docs/tablet/v676/tablet_unified_dashboard_v676.css": b"body{margin:0}",
    "/docs/tablet/v676/tablet_unified_dashboard_v676.js": b"'use strict';",
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
