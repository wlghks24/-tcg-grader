# -*- coding: utf-8 -*-
"""Regression: promoted market/purchase routes are real discovery, never inventory proof."""
import json
import unittest
from pathlib import Path

import update_purchase_sources
import tcg_game_registry

ROOT = Path(__file__).resolve().parent

class PromotedPurchaseMaterializationV500Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = json.loads((ROOT / "purchase_sources.json").read_text(encoding="utf-8"))["sources"]
        cls.registry = tcg_game_registry.load_registry(ROOT)

    def test_all_eligible_games_have_three_honest_routes_per_region(self):
        for game in tcg_game_registry.enabled_games("purchase", root=ROOT):
            for region in game.get("regions", ()):
                if region not in {"KR", "JP", "US"}:
                    continue
                matches = [row for row in self.sources
                           if row.get("registry_generated") is True
                           and row.get("region") == region
                           and game.get("purchase_value") in row.get("games", [])]
                self.assertEqual({"official", "marketplace", "map"},
                                 {row.get("type") for row in matches},
                                 (game.get("id"), region))
                self.assertEqual(3, len(matches))
                self.assertTrue(all(row.get("inventory_verified") is False for row in matches))
                self.assertTrue(all("미확인" in row.get("note", "") or "확인" in row.get("note", "") for row in matches))

    def test_global_links_not_falsely_labeled_verified_local_retailers(self):
        for row in self.sources:
            if row.get("registry_generated") is not True:
                continue
            if row.get("type") in {"marketplace", "official"}:
                self.assertIn("글로벌" if row["type"] == "marketplace" else "해외", row["name"])
                self.assertIn("미확인" if row["type"] == "official" else "보장", row["note"])
                self.assertTrue(row["url"].startswith("https://"))
            if row.get("type") == "map":
                self.assertFalse(row.get("inventory_verified"))
                self.assertIn("{query}", row["url_template"])

    def test_watch_games_not_promoted_to_purchase(self):
        watches = {g.get("purchase_value") for g in self.registry.get("games", ())
                   if g.get("state") == "watch"}
        for row in self.sources:
            if row.get("registry_generated") is True:
                self.assertFalse(set(row.get("games") or []) & watches)

    def test_generated_sources_are_idempotent(self):
        self.assertEqual(self.sources, update_purchase_sources.ensure_registry_tcg_sources(self.sources))
        keys = [(r["name"], r["region"], r.get("channel", "online")) for r in self.sources]
        self.assertEqual(len(keys), len(set(keys)))

if __name__ == "__main__":
    unittest.main()
