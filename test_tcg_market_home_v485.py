#!/usr/bin/env python3
"""Fail-closed UI and data-contract checks for V485 market home."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class MarketHomeV485Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = (ROOT / "index.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "feature_category_nav.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "feature_category_nav.css").read_text(encoding="utf-8")
        cls.feature = cls.index.split("/* V485: Screenshot-informed, evidence-only market home.", 1)[1].split("</script>",1)[0]

    def test_pwa_cache_busters_and_existing_nav_remain(self):
        self.assertEqual(self.index.count("feature_category_nav.js?v=485"), 1)
        self.assertEqual(self.index.count("feature_category_nav.css?v=485"), 1)
        self.assertIn('id="featureCategories"', self.index)
        for feature in ("market-search", "purchase-finder", "auto-grade", "box-knowledge"):
            self.assertIn('data-feature-key="' + feature + '"', self.index)

    def test_market_home_uses_real_saved_prices_and_bounded_ui(self):
        for token in (
            'home.id = "tcgMarketHome"',
            'fetch("market_prices.json"',
            'fetch("market_watch.json"',
            'fetch("catalog_image_manifest.json"',
            'GAMES.some(g=>g.id===value.game',
            'known.get([parts[0],clean(parts[1]),parts[2]].join("|"))',
            'state.ready=true',
            '.slice(0,6)',
            '.slice(0,1500)',
            'Promise.all([',
        ):
            self.assertIn(token, self.feature)
        self.assertNotIn("Math.random", self.feature)
        self.assertNotIn("innerHTML", self.feature)
        self.assertNotIn("eval(", self.feature)
        self.assertNotIn("localStorage", self.feature)
        self.assertNotIn("fetch('https:", self.feature)
        self.assertIn('새로 확인', self.feature)

    def test_no_invented_grade_price_or_percentages(self):
        self.assertIn("근거 없는 상승률은 생성하지 않습니다", self.feature)
        self.assertIn("과거 자료는 실시간 가격이 아닙니다", self.feature)
        self.assertIn("관측일 미확인", self.feature)
        self.assertIn('new URL(String(value || ""))', self.feature)
        self.assertIn('url.protocol === "https:"', self.feature)
        self.assertIn('textContent = value', self.feature)
        self.assertIn('image.region === row.region', self.feature)
        self.assertIn('img.addEventListener("error"', self.feature)
        self.assertIn('source.rel="noopener noreferrer"', self.feature)

    def test_phone_card_accessibility_and_no_overlay(self):
        for token in (
            '.tcg-market-home-cards', '.tcg-market-game[aria-pressed=true]',
            '.tcg-market-tile-actions', '.tcg-market-home-empty',
            'max-width:100%', '@media(max-width:430px)',
            ':focus-visible', '@media(prefers-reduced-motion:reduce)',
            'body[data-feature-view-active] .tcg-market-home',
        ):
            self.assertIn(token, self.css)
        self.assertIn('setAttribute("aria-pressed"', self.feature)
        self.assertIn('setAttribute("aria-live", "polite")', self.feature)
        self.assertIn('loading="lazy"', self.feature.replace('img.loading="lazy"', 'loading="lazy"'))

    def test_saved_price_schema_and_game_fail_closed_example(self):
        prices = json.loads((ROOT / "market_prices.json").read_text(encoding="utf-8"))
        watch = json.loads((ROOT / "market_watch.json").read_text(encoding="utf-8"))
        image = json.loads((ROOT / "catalog_image_manifest.json").read_text(encoding="utf-8"))
        self.assertIsInstance(prices["entries"], dict)
        self.assertIsInstance(watch["items"], list)
        self.assertIsInstance(image["items"], dict)
        self.assertTrue(any(k.split("|")[-1] == "HIT" for k in prices["entries"]))
        self.assertTrue(any(k.split("|")[-1] == "BOX" for k in prices["entries"]))
        self.assertTrue(all(v.get("game") in ("Pokémon", "ONE PIECE", "NARUTO") for v in prices["entries"].values()))
        self.assertIn('|| "UNKNOWN"', self.feature)

    def test_curated_core_games_show_saved_card_and_box_rows(self):
        prices = json.loads((ROOT / "market_prices.json").read_text(encoding="utf-8"))
        watch = json.loads((ROOT / "market_watch.json").read_text(encoding="utf-8"))
        normalized = lambda value: str(value or "").strip().casefold()
        known = {(v["region"], normalized(v["name"]), v["asset"]): v["game"]
                 for v in watch["items"] if isinstance(v, dict)
                 and v.get("game") in ("Pokémon", "ONE PIECE", "NARUTO")}
        observed = set()
        for key, row in prices["entries"].items():
            region, name, asset = key.split("|")
            game = row.get("game") if row.get("game") in ("Pokémon", "ONE PIECE", "NARUTO") else known.get((region, normalized(name), asset))
            if game:
                observed.add((game, asset))
        for required in (("Pokémon", "HIT"), ("Pokémon", "BOX"),
                         ("ONE PIECE", "HIT"), ("ONE PIECE", "BOX"),
                         ("NARUTO", "HIT")):
            self.assertIn(required, observed, f"missing categorized market tab: {required}")

    def test_price_refresh_keeps_curated_identity_without_inventing_new_game(self):
        import update_market_prices
        tracked = {"entries": {"JP|인페르노 X|BOX": {"game": "Pokémon"}}}
        update_market_prices.set_price(tracked, "JP|인페르노 X|BOX",
                                       "¥5,000", "참고가격", "검증출처", "0", "https://example.com/")
        self.assertEqual(tracked["entries"]["JP|인페르노 X|BOX"]["game"], "Pokémon")
        unknown = {"entries": {}}
        update_market_prices.set_price(unknown, "JP|unknown|BOX",
                                       "¥5,000", "참고가격", "검증출처", "0", "https://example.com/")
        self.assertNotIn("game", unknown["entries"]["JP|unknown|BOX"])

    @unittest.skipUnless(shutil.which("node"), "Node.js syntax verifier unavailable")
    def test_javascript_syntax(self):
        subprocess.run(["node", "--check", str(ROOT / "feature_category_nav.js")],
                       check=True, timeout=15)
        subprocess.run(["node", "--check", "-"], input="/* V485: Screenshot-informed, evidence-only market home.\n"+self.feature, text=True, check=True, timeout=15)


if __name__ == "__main__":
    unittest.main(verbosity=2)
