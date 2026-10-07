#!/usr/bin/env python3
"""V429 regression guard: registry-driven market lens and WATCH safety boundaries."""
import json
import unittest
from pathlib import Path

import tcg_game_registry as registry

ROOT = Path(__file__).resolve().parent
JS = (ROOT / "tablet_autonomy_dashboard_v400.js").read_text(encoding="utf-8")


class TabletRegistryMarketLensV429Tests(unittest.TestCase):
    def test_market_lens_uses_registry_as_ssot(self):
        self.assertIn("function registryMarketLensRows(registry, includeWatch = true)", JS)
        self.assertIn("registryMarketLensRows(gameRegistryCache, true)", JS)
        self.assertIn("row?.capabilities?.market === true", JS)
        self.assertIn(
            'state === "core" || state === "promoted" || (includeWatch && state === "watch")',
            JS,
        )

    def test_registry_label_helper_is_actually_used(self):
        # One definition plus four UI call sites. This prevents the CodeQL
        # regression where the helper existed but every consumer duplicated it.
        self.assertGreaterEqual(JS.count("registryGameLabel("), 5)
        self.assertIn('node("button", "video-market-lens-chip", registryGameLabel(key))', JS)
        self.assertIn('registryGameLabel(String(state.plan.focus_game || "ALL"))', JS)
        self.assertIn("registryGameLabel(lensState.game)", JS)

    def test_hardcoded_noncore_market_catalog_removed(self):
        marker = 'const MARKET_LENS_GAMES = Object.freeze(["ALL","Pokémon","ONE PIECE","NARUTO"]);'
        self.assertIn(marker, JS)
        block = JS[JS.index("const MARKET_LENS_GAMES"):JS.index("const MARKET_LENS_REGIONS")]
        for legacy in (
            "GUNDAM CARD GAME",
            "UNION ARENA",
            "Disney Lorcana",
            "Riftbound: League of Legends",
            "WIXOSS",
        ):
            self.assertNotIn(legacy, block)

    def test_invalid_or_missing_registry_fails_closed_to_core_not_stale_plan(self):
        block = JS[JS.index("function marketLensState(plan)"):JS.index("function marketLensControls(")]
        self.assertIn("registryMarketLensRows(gameRegistryCache, true)", block)
        self.assertIn('MARKET_LENS_GAMES.filter((value) => value !== "ALL")', block)
        self.assertNotIn("safe.allowed_games", block)

    def test_watch_is_market_visible_but_not_default_purchase_or_grading(self):
        data = json.loads((ROOT / "tcg_game_registry.json").read_text(encoding="utf-8"))
        watch_market = {
            row["canonical"]
            for row in data["games"]
            if row["state"] == "watch" and row["capabilities"].get("market") is True
        }
        self.assertTrue(watch_market)

        market_with_watch = {
            row["canonical"] for row in registry.enabled_games("market", root=ROOT, include_watch=True)
        }
        purchase_default = {
            row["canonical"] for row in registry.enabled_games("purchase", root=ROOT)
        }
        grading_default = {
            row["canonical"] for row in registry.enabled_games("grading", root=ROOT)
        }

        self.assertLessEqual(watch_market, market_with_watch)
        self.assertFalse(watch_market & purchase_default)
        self.assertFalse(watch_market & grading_default)
        self.assertTrue(
            all(
                row["capabilities"].get("grading") is False
                for row in data["games"]
                if row["state"] == "watch"
            )
        )

        controls = JS[JS.index("async function applyGameRegistryToControls()"):JS.index("function marketLensState(plan)")]
        self.assertIn('promotedRegistryGames(registry, "purchase")', controls)
        self.assertNotIn('watchRegistryGames(registry, "purchase")', controls)


if __name__ == "__main__":
    unittest.main(verbosity=2)
