"""Read-only localhost regression for V881's allowlisted nested tablet UI page.

This test performs no installation, model operation, collection or data writes.
"""
from __future__ import annotations

import threading
import unittest
import urllib.error
import urllib.request
from functools import partial
from pathlib import Path

import tcg_updater

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_NAME = "tablet_market_hub_v881.html"
SOURCE = ROOT / "execution" / PUBLIC_NAME


class TabletV881LocalHTTPAliasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        assert SOURCE.is_file() and not SOURCE.is_symlink(), "V881 source missing or symlinked"
        handler = partial(tcg_updater.Handler, directory=str(ROOT))
        cls.server = tcg_updater.QuietThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def test_public_get_returns_exact_review_page_without_exposing_directory(self) -> None:
        with urllib.request.urlopen(self.base + "/" + PUBLIC_NAME, timeout=10) as resp:
            content = resp.read()
            self.assertEqual(resp.status, 200)
            self.assertIn("text/html", resp.headers.get("Content-Type", ""))
            self.assertEqual(int(resp.headers.get("Content-Length", "-1")), len(content))
            self.assertIn("no-cache", resp.headers.get("Cache-Control", ""))
            self.assertIn("nosniff", resp.headers.get("X-Content-Type-Options", ""))
        self.assertEqual(content, SOURCE.read_bytes())
        self.assertIn(b"TCGReferenceHubV881", content)

    def test_head_reports_same_length_and_no_response_body(self) -> None:
        req = urllib.request.Request(self.base + "/" + PUBLIC_NAME, method="HEAD")
        with urllib.request.urlopen(req, timeout=10) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(int(resp.headers.get("Content-Length", "-1")), SOURCE.stat().st_size)
            self.assertEqual(resp.read(), b"")

    def test_nested_source_and_proof_are_not_public(self) -> None:
        for path in (
            "/execution/" + PUBLIC_NAME,
            "/.github/tablet-autonomy/video_ui_successor_v881.json",
            "/execution/tests/test_video_ui_successor_v881.py",
        ):
            with self.subTest(path=path):
                for method in ("GET", "HEAD"):
                    with self.subTest(method=method):
                        request = urllib.request.Request(self.base + path, method=method)
                        with self.assertRaises(urllib.error.HTTPError) as error:
                            urllib.request.urlopen(request, timeout=10)
                        self.assertEqual(error.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
