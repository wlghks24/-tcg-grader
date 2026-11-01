"""V881 screen-recording-inspired UI: static, read-only, and packaging checks."""
from __future__ import annotations

import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class TabletMarketHubV881Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = (ROOT / "tablet_market_hub_v881.html").read_text(encoding="utf-8")
        cls.server = (ROOT / "tcg_updater.py").read_text(encoding="utf-8")
        cls.runtime = (ROOT / "tablet_runtime_manifest.py").read_text(encoding="utf-8")
        cls.main = (ROOT / "index.html").read_text(encoding="utf-8")

    def test_page_registered_without_replacing_existing_app(self):
        self.assertIn("'tablet_market_hub_v881.html'", self.server)
        self.assertIn('"tablet_market_hub_v881.html"', self.runtime)
        self.assertIn('id="tcgV881HubLink"', self.main)
        self.assertIn('href="tablet_market_hub_v881.html"', self.main)
        for preserved in ('id="featureCategories"', 'id="simpleGradeV32"', 'id="box12section"'):
            self.assertIn(preserved, self.main)

    def test_video_navigation_search_and_filters(self):
        for page in ("home", "market", "scanner", "portfolio", "news"):
            self.assertIn('id="page-' + page + '"', self.page)
            self.assertIn('data-page="' + page + '"', self.page)
        for selector in ('homeQuery', 'marketQuery', 'marketGame', 'marketRegion',
                         'marketKind', 'scanFront', 'scanBack', 'frontPreview',
                         'backPreview', 'portfolioStats'):
            self.assertIn('id="' + selector + '"', self.page)
        for region in ('KR', 'JP', 'US', 'CN-S', 'CN-T'):
            self.assertIn('value="' + region + '"', self.page)
        self.assertIn('index.html#simpleGradeV32', self.page)

    def test_read_only_and_evidence_honest_states(self):
        for asset in ('market_prices.json', 'market_watch.json', 'catalog_image_manifest.json',
                      'releases.json', '/api/local-card-images/cross-status'):
            self.assertIn(asset, self.page)
        for token in ('시세 확인 중', '보유 평가금액', '정확 연결', '공식', '실시간'):
            if token == '공식':
                continue
            self.assertIn(token, self.page)
        self.assertNotIn("method:'POST'", self.page)
        self.assertNotIn("method:'DELETE'", self.page)
        self.assertNotIn('innerHTML=', self.page)
        self.assertIn('text=(e,v)=>', self.page)
        self.assertIn('safeUrl', self.page)
        self.assertIn('URL.revokeObjectURL', self.page)
        self.assertIn('prefers-reduced-motion', self.page)
        self.assertIn(':focus-visible', self.page)

    @unittest.skipUnless(shutil.which("node"), "Node syntax check requires Node")
    def test_javascript_syntax(self):
        source = re.search(r"<script>(.*?)</script>", self.page, flags=re.S)
        self.assertIsNotNone(source)
        check = subprocess.run(['node', '--check'], input=source.group(1),
                               text=True, capture_output=True, timeout=20)
        self.assertEqual(check.returncode, 0, check.stderr)


if __name__ == "__main__":
    unittest.main()
