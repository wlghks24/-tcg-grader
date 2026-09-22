from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class UiVersionCoherenceV276Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (ROOT / "index.html").read_text(encoding="utf-8")
        cls.nav_js = (ROOT / "feature_category_nav.js").read_text(encoding="utf-8")
        cls.sw = (ROOT / "sw.js").read_text(encoding="utf-8")
        cls.manifest = (ROOT / "manifest.webmanifest").read_text(encoding="utf-8")

    def test_component_versions_are_explicit_but_not_forced_to_match(self) -> None:
        self.assertIn('uiVersion: "v276-motion-pwa-hardening"', self.nav_js)
        self.assertIn("const CACHE='tcg-v292-card-core-runtime';", self.sw)
        # Manifest/app-shell versions are independent component generations.
        # Do not force unrelated components to share the v276 number.
        self.assertRegex(self.manifest, r'"version"\s*:\s*"?\d+"?')

    def test_feature_nav_assets_have_single_numeric_cache_busters(self) -> None:
        for asset in ("feature_category_nav.css", "feature_category_nav.js"):
            matches = re.findall(re.escape(asset) + r"\?v=(\d+)", self.html)
            self.assertEqual(len(matches), 1, f"{asset} must load exactly once with one numeric cache-buster")
            self.assertGreaterEqual(int(matches[0]), 206, f"{asset} cache-buster regressed: {matches[0]}")

    def test_runtime_delivery_does_not_depend_on_cache_buster_label(self) -> None:
        # Static query labels are not the runtime source of truth: mutable app assets
        # are network-first/no-store and the SW generation controls offline refresh.
        self.assertIn("fetch(event.request,{cache:'no-store'})", self.sw)
        self.assertIn("caches.match(request,{ignoreSearch:true})", self.sw)
        self.assertIn("await self.skipWaiting()", self.sw)
        self.assertIn("self.clients.claim()", self.sw)
        self.assertIn("requestServiceWorkerRefresh", self.nav_js)

    def test_v276_accessibility_contract_is_preserved(self) -> None:
        self.assertIn('aria-current", "location"', self.nav_js)
        self.assertIn('link.setAttribute("aria-controls", item.target)', self.nav_js)
        self.assertIn('reducedMotionPreferred()', self.nav_js)
        self.assertNotIn('aria-current", "page"', self.nav_js)


if __name__ == "__main__":
    unittest.main()
