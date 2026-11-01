"""Regression guard for the V881 read-only tablet UI preview.

This file intentionally does not require a physical Lenovo, network, or paid APIs.
It rejects silent promotion of the preview to production.
"""
from __future__ import annotations
from html.parser import HTMLParser
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "execution" / "tablet_video_ui_reference_v881.html"

class Elements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.buttons = []
        self.duplicate_ids = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        ident = attrs.get("id")
        if ident:
            if ident in self.ids:
                self.duplicate_ids.append(ident)
            self.ids.add(ident)
        if tag == "button":
            self.buttons.append(attrs)

class TabletVideoUIV881Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = PAGE.read_text(encoding="utf-8")
        cls.dom = Elements()
        cls.dom.feed(cls.html)

    def test_five_reference_surfaces_and_unique_ids(self):
        self.assertFalse(self.dom.duplicate_ids, self.dom.duplicate_ids)
        for name in ("home", "market", "scanner", "news", "portfolio"):
            self.assertIn("page-" + name, self.dom.ids)
            self.assertTrue(any(b.get("data-view") == name for b in self.dom.buttons))
        for ident in ("gamePills", "homeSearch", "marketSearch", "marketRegion",
                      "marketType", "frontFile", "backFile", "portfolioStats"):
            self.assertIn(ident, self.dom.ids)

    def test_read_only_and_no_invented_trades_or_training(self):
        js = self.html.split("<script>", 1)[1].split("</script>", 1)[0]
        self.assertNotIn("innerHTML", js)
        self.assertNotRegex(js, r"\b(?:eval|Function)\s*\(")
        self.assertNotIn("localStorage", js)
        self.assertNotIn("sessionStorage", js)
        self.assertNotIn("serviceWorker.register", js)
        self.assertNotIn("method:'POST'", js)
        self.assertNotIn("method:\"POST\"", js)
        self.assertNotIn("navigator.mediaDevices", js)
        self.assertIn("Promise.allSettled", js)
        self.assertIn("URL.revokeObjectURL", js)
        self.assertIn("state.photos.delete(id)", js)
        self.assertIn("x.game", js)
        self.assertIn("same.length!==1", js)
        self.assertIn("row.kind==='BOX'", js)
        self.assertIn("r.kind==='BOX'", js)
        self.assertIn("credentials:'same-origin'", js)

    def test_market_url_and_missing_state_controls(self):
        js = self.html.split("<script>", 1)[1].split("</script>", 1)[0]
        self.assertIn("v.protocol==='https:'", js)
        self.assertIn("!v.username", js)
        self.assertIn("!v.password", js)
        self.assertIn("Date.parse", js)
        self.assertIn("'UNKNOWN'", js)
        self.assertIn("가격 확인 중", self.html)
        self.assertIn("실시간 체결가 보장 안 됨", self.html)
        self.assertIn("₩—", self.html)
        for target in ("market_prices.json", "market_watch.json",
                       "catalog_image_manifest.json", "releases.json",
                       "api/local-card-images/cross-status"):
            self.assertIn(target, js)

    @unittest.skipUnless(shutil.which("node"), "Node needed to syntax-check inline JS")
    def test_javascript_parses(self):
        js = self.html.split("<script>", 1)[1].split("</script>", 1)[0]
        result = subprocess.run(["node", "--check", "--input-type=commonjs"],
                                input=js, text=True, capture_output=True, timeout=10)
        self.assertEqual(0, result.returncode, result.stderr)

if __name__ == "__main__":
    unittest.main()
