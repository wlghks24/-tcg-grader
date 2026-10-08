from __future__ import annotations

import json
import unittest
from pathlib import Path

import tcg_game_registry
import update_purchase_sources as purchase

ROOT = Path(__file__).resolve().parent
REGIONS = {"KR", "JP", "US"}


class PurchaseRegistryRoutesV491Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads((ROOT / "purchase_sources.json").read_text(encoding="utf-8"))
        cls.enabled = tcg_game_registry.enabled_games("purchase", root=ROOT)
        cls.rows = cls.payload["sources"]
        cls.generated = [row for row in cls.rows if row.get("registry_generated") is True]

    def test_every_enabled_region_has_three_distinct_discovery_types(self):
        for game in self.enabled:
            value = game["purchase_value"]
            for region in game.get("regions", []):
                if region not in REGIONS:
                    continue
                rows = [
                    row for row in self.generated
                    if region == row.get("region") and value in row.get("games", [])
                ]
                with self.subTest(game=game["id"], region=region):
                    self.assertEqual({"official", "marketplace", "map"}, {row["type"] for row in rows})
                    self.assertEqual(3, len(rows))
                    maps = [row for row in rows if row["type"] == "map"]
                    self.assertEqual("offline", maps[0]["channel"])
                    self.assertFalse(maps[0]["inventory_verified"])
                    self.assertIn("미확인", maps[0]["inventory_status"])
                    self.assertEqual(1, maps[0]["url_template"].count("{query}"))
                    self.assertTrue(maps[0]["url_template"].startswith("https://"))
                    for row in rows:
                        self.assertIs(row["inventory_verified"], False)
                        self.assertEqual(row, purchase.normalize_source(row))

    def test_watch_games_never_appear_in_generated_inventory(self):
        raw = tcg_game_registry.load_registry(ROOT)
        watch = {
            row.get("purchase_value")
            for row in raw["games"] if row.get("state") == "watch"
        }
        represented = {value for row in self.generated for value in row.get("games", [])}
        self.assertFalse(watch & represented)
        self.assertTrue(represented)

    def test_static_snapshot_has_no_unverified_stock_claim(self):
        self.assertEqual(12, self.payload["registry_purchase_game_count"])
        self.assertEqual(75, len(self.generated))
        self.assertEqual(280, len(self.rows))
        self.assertEqual("2026-09-30T07:12:37+00:00", self.payload["updated_at"])
        self.assertTrue(all(row.get("inventory_verified") is False for row in self.generated))
        self.assertTrue(all(row.get("inventory_checked_at") is None for row in self.generated if row["type"] == "map"))
        self.assertTrue(all("미검증" in row["data_basis"] for row in self.generated))
        self.assertIn("검증되지 않았습니다", self.payload["registry_purchase_policy"])

    def test_generator_is_idempotent_and_preserves_original_rows(self):
        updated = purchase.ensure_registry_tcg_sources(self.rows)
        self.assertEqual(len(self.rows), len(updated))
        self.assertEqual(self.rows, updated)
        self.assertEqual(205, len([row for row in self.rows if not row.get("registry_generated")]))

    def test_generated_links_remain_https_only_with_explicit_state(self):
        for row in self.generated:
            with self.subTest(name=row["name"]):
                self.assertIn(row["channel"], ("online", "offline"))
                if row["type"] == "map":
                    self.assertIn("지도 검색", row["data_basis"])
                else:
                    self.assertTrue(row["url"].startswith("https://"))
                    self.assertNotIn("{query}", row["url"])
                self.assertNotIn("재고확인됨", str(row))


if __name__ == "__main__":
    unittest.main(verbosity=2)
