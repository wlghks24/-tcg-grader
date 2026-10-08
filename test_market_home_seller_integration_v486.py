#!/usr/bin/env python3
"""Reviewed two-parent local-only market home and seller pricing integration."""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAIN_UI = "b1e3c61e496495c826695bb47cb835cd37ca74b5"
PR_SELLER = "f4a909380c337c0a42218e30f93e76839928eece"


class MarketHomeSellerIntegrationV486Tests(unittest.TestCase):
    def test_both_reviewed_histories_reachable(self):
        for commit in (MAIN_UI, PR_SELLER):
            subprocess.run(["git", "merge-base", "--is-ancestor", commit, "HEAD"],
                           cwd=ROOT, check=True, timeout=15)

    def test_market_home_and_condition_filter_coexist(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        backend = (ROOT / "tcg_updater.py").read_text(encoding="utf-8")
        js = (ROOT / "multi_market_prices.js").read_text(encoding="utf-8")
        self.assertIn('id="tcgMarketHome"', html) if 'id="tcgMarketHome"' in html else self.assertIn('home.id = "tcgMarketHome"', html)
        self.assertIn('id="market12"', html)
        self.assertIn("한국판", html)
        self.assertIn("condition=condition,printing=printing", backend)
        self.assertIn("catalog_image_manifest.json", backend)
        for token in ("multiMarketCondition", "multiMarketEvidence", "HISTORY_KEY"):
            self.assertIn(token, js)

    def test_explicit_printing_remains_fail_closed(self):
        import multi_market_price_collector as prices
        valid = {"condition": "Near Mint", "printing": "Holo", "title": "Pikachu 025"}
        unknown = {"title": "Pikachu 025"}
        self.assertEqual(prices._market_filter_eligibility(valid, "NM", "holo"),
                         (True, "market_filter_match"))
        self.assertEqual(prices._market_filter_eligibility(unknown, "ALL", "holo"),
                         (False, "printing_unknown"))


if __name__ == "__main__":
    unittest.main()
