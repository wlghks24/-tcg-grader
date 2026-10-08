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

    def test_server_and_pwa_asset_whitelist(self):
        backend = (ROOT / "tcg_updater.py").read_text(encoding="utf-8")
        sw = (ROOT / "sw.js").read_text(encoding="utf-8")
        self.assertIn("'tcg_market_expanded_v487.js'", backend)
        self.assertIn("'./tcg_market_expanded_v487.js'", sw)

    @unittest.skipUnless(shutil.which("node"), "Node.js not available")
    def test_js_syntax(self):
        for name in ("tcg_market_expanded_v487.js", "tcg_registry_ui_v469.js"):
            subprocess.run(["node", "--check", str(ROOT / name)], check=True, timeout=15)


if __name__ == "__main__":
    unittest.main()
