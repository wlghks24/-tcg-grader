from __future__ import annotations

import json
import unittest
from pathlib import Path

import tcg_game_registry
import update_purchase_sources as purchase

ROOT = Path(__file__).resolve().parent


class PurchaseRegistryRoutesV483Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.games = tcg_game_registry.enabled_games("purchase", root=ROOT)
        self.active = [row for row in self.games if row.get("state") != "watch"]
        self.watch = [row for row in self.games if row.get("state") == "watch"]

    def test_generated_routes_cover_every_active_registry_game_region(self):
        rows = purchase.ensure_registry_tcg_sources([])
        for game in self.active:
            value = str(game.get("purchase_value") or "").strip()
            for region in game.get("regions") or []:
                if region not in purchase.REGIONS:
                    continue
                scoped = [
                    row for row in rows
                    if row.get("region") == region and value in (row.get("games") or [])
                ]
                self.assertTrue(any(row.get("type") == "official" and row.get("channel") == "online" for row in scoped), (value, region, "official"))
                self.assertTrue(any(row.get("type") == "marketplace" and row.get("channel") == "online" for row in scoped), (value, region, "marketplace"))
                maps = [row for row in scoped if row.get("type") == "map" and row.get("channel") == "offline"]
                self.assertTrue(maps, (value, region, "map"))
                self.assertTrue(all(row.get("inventory_verified") is False for row in maps))
                self.assertTrue(all("미확인" in str(row.get("inventory_status") or "") for row in maps))
                self.assertTrue(all(str(row.get("url_template") or "").count("{query}") == 1 for row in maps))

    def test_watch_games_never_receive_real_purchase_routes(self):
        rows = purchase.ensure_registry_tcg_sources([])
        generated_values = {
            value
            for row in rows
            for value in (row.get("games") or [])
        }
        for game in self.watch:
            self.assertNotIn(str(game.get("purchase_value") or ""), generated_values)

    def test_committed_purchase_data_materializes_active_registry_routes(self):
        payload = json.loads((ROOT / "purchase_sources.json").read_text(encoding="utf-8"))
        rows = payload.get("sources") or []
        values = {
            value
            for row in rows
            if row.get("registry_generated") is True
            for value in (row.get("games") or [])
        }
        expected = {str(row.get("purchase_value") or "") for row in self.active}
        self.assertTrue(expected)
        self.assertTrue(expected.issubset(values))
        self.assertEqual(len(expected), int(payload.get("registry_purchase_game_count") or 0))
        self.assertIn("재고", str(payload.get("registry_purchase_policy") or ""))
        self.assertTrue(all(row.get("inventory_verified") is not True for row in rows if row.get("registry_generated") is True))

    def test_generated_map_templates_remain_public_https_and_query_bounded(self):
        rows = purchase.ensure_registry_tcg_sources([])
        maps = [row for row in rows if row.get("type") == "map" and row.get("registry_generated") is True]
        self.assertTrue(maps)
        for row in maps:
            normalized = purchase.normalize_source(row)
            self.assertTrue(str(normalized.get("url_template") or "").startswith("https://"))
            self.assertEqual(1, str(normalized.get("url_template") or "").count("{query}"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
