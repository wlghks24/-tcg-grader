import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class MarketExpandedV487(unittest.TestCase):
    def test_registry_only_promoted_games_and_no_fake_prices(self):
        js = (ROOT / "tcg_market_expanded_v487.js").read_text(encoding="utf-8")
        registry = (ROOT / "tcg_registry_ui_v469.js").read_text(encoding="utf-8")
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('src="tcg_registry_ui_v469.js?v=469"', html)
        self.assertIn('script.src = "tcg_market_expanded_v487.js?v=487"', registry)
        self.assertIn('document.getElementById("tcgMarketHome")', registry)
        self.assertNotIn('src="tcg_market_expanded_v487.js?v=487"', html)
        for token in ('tcg_game_registry.json', 'x.state==="promoted"',
                      'x.capabilities?.market===true', 'data-feature-key="market-search"',
                      'min-height:44px', 'aria-live', 'v12Game'):
            self.assertIn(token, js)
        self.assertNotIn('innerHTML', js)
        self.assertNotIn('Math.random', js)
        self.assertNotIn('gradeResult', js)

    def test_market_home_touch_readability(self):
        """Screenshot parity: controls remain tappable and evidence readable."""
        js = (ROOT / "tcg_market_expanded_v487.js").read_text(encoding="utf-8")
        style = js.split("// V516: screenshot readability and touch-safe controls.", 1)[1].split("document.head.append(style);", 1)[0]
        for selector in (".tcg-market-refresh", ".tcg-market-game",
                         ".tcg-market-more", ".tcg-market-tile-actions :is(button,a)"):
            self.assertIn(selector, style)
        self.assertIn("min-height:48px", style)
        self.assertIn("min-width:44px", style)
        self.assertIn("font-size:12px", style)
        self.assertIn("font-variant-numeric:tabular-nums", style)
        self.assertIn("overflow-wrap:anywhere", style)
        self.assertIn("@media(max-width:430px)", style)
        self.assertIn("touch-action:manipulation", style)
        self.assertNotIn("innerHTML", style)
        self.assertNotIn("fetch(", style)

    def test_server_and_pwa_asset_whitelist(self):
        backend = (ROOT / "tcg_updater.py").read_text(encoding="utf-8")
        sw = (ROOT / "sw.js").read_text(encoding="utf-8")
        self.assertIn("'tcg_market_expanded_v487.js'", backend)
        self.assertIn("'./tcg_market_expanded_v487.js'", sw)


    def test_market_home_source_links_fail_closed(self):
        js = (ROOT / "tcg_market_expanded_v487.js").read_text(encoding="utf-8")
        self.assertIn("verifiedMarketSourceUrl(link.getAttribute", js)
        self.assertIn("new MutationObserver(protectMarketHomeLinks)", js)
        self.assertIn("event.stopImmediatePropagation()", js)
        self.assertIn("출처 URL 확인 필요", js)
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js required for executable URL contract")
        section = js.split("  const VERIFIED_MARKET_SOURCE_HOSTS =", 1)[1].split("  function protectMarketHomeLinks()", 1)[0]
        payload = (
            "const assert=require('node:assert/strict');\n"
            "const VERIFIED_MARKET_SOURCE_HOSTS =" + section + "\n"
            "for(const url of ['javascript:alert(1)','http://pokard.io/x',"
            "'https://pokard.io.evil.test/x','https://evil.test/',"
            "'https://user:pass@pokard.io/x','https://localhost/x',"
            "'https://pokard.io:4040/x','//pokard.io/x']) "
            "assert.equal(verifiedMarketSourceUrl(url),'',url);\n"
            "for(const url of ['https://pokard.io/jpcard/SV8a-217/',"
            "'https://kream.co.kr/products/959332',"
            "'https://www.tcgplayer.com/product/123']) "
            "assert.equal(verifiedMarketSourceUrl(url),url,url);\n"
        )
        result = subprocess.run([node, "-e", payload], capture_output=True, text=True, timeout=15)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    @unittest.skipUnless(shutil.which("node"), "Node.js not available")
    def test_js_syntax(self):
        for name in ("tcg_market_expanded_v487.js", "tcg_registry_ui_v469.js"):
            subprocess.run(["node", "--check", str(ROOT / name)], check=True, timeout=15)


if __name__ == "__main__":
    unittest.main()
