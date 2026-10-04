#!/usr/bin/env python3
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

import tcg_game_registry as registry


ROOT = Path(__file__).resolve().parent


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class TcgGameRegistryTests(unittest.TestCase):
    def setUp(self):
        self.source = json.loads((ROOT / "tcg_game_registry.json").read_text(encoding="utf-8"))

    def test_seed_registry_is_strict_verified_and_not_profit_prediction(self):
        self.assertTrue(registry.validate_registry(self.source))
        policy = self.source["policy"]
        self.assertFalse(policy["profit_guarantee"])
        self.assertFalse(policy["investment_return_prediction"])
        self.assertFalse(policy["market_direction_prediction"])
        self.assertTrue(policy["category_auto_promotion_requires_verified_evidence"])
        self.assertTrue(policy["grading_requires_separate_calibration"])
        promoted = {row["canonical"] for row in self.source["games"] if row["state"] in {"core", "promoted"}}
        self.assertTrue({
            "Pokémon", "ONE PIECE", "NARUTO", "GUNDAM CARD GAME", "UNION ARENA",
            "DRAGON BALL SUPER: FUSION WORLD", "Disney Lorcana",
            "Star Wars: Unlimited", "Riftbound: League of Legends",
            "Magic: The Gathering", "Yu-Gi-Oh!", "Digimon Card Game",
        }.issubset(promoted))
        watch = {row["canonical"] for row in self.source["games"] if row["state"] == "watch"}
        self.assertTrue({
            "Flesh and Blood TCG", "Weiß Schwarz", "Cardfight!! Vanguard",
            "hololive OFFICIAL CARD GAME",
        }.issubset(watch))

    def test_new_games_get_market_surfaces_but_not_unverified_grading(self):
        market = registry.enabled_games("market", root=ROOT)
        grading = registry.enabled_games("grading", root=ROOT)
        self.assertGreaterEqual(len(market), 9)
        self.assertEqual({"pokemon", "onepiece", "naruto"}, {row["id"] for row in grading})
        self.assertTrue(all(row["capabilities"]["grading"] is False for row in market if row["id"] not in registry.CORE_IDS))

    def test_aliases_canonicalize_new_games(self):
        self.assertEqual("GUNDAM CARD GAME", registry.canonical_game("건담 카드", root=ROOT))
        self.assertEqual("UNION ARENA", registry.canonical_game("Union Arena Solo Leveling", root=ROOT))
        self.assertEqual("DRAGON BALL SUPER: FUSION WORLD", registry.canonical_game("드래곤볼 퓨전월드", root=ROOT))
        self.assertEqual("Disney Lorcana", registry.canonical_game("Disney Lorcana Hyperia City", root=ROOT))
        self.assertEqual("Star Wars: Unlimited", registry.canonical_game("Star Wars Unlimited", root=ROOT))
        self.assertEqual("Riftbound: League of Legends", registry.canonical_game("리프트바운드", root=ROOT))
        self.assertEqual("Magic: The Gathering", registry.canonical_game("MTG", root=ROOT))
        self.assertEqual("Yu-Gi-Oh!", registry.canonical_game("유희왕 카드", root=ROOT))
        self.assertEqual("Digimon Card Game", registry.canonical_game("디지몬 카드게임", root=ROOT))

    def test_watch_candidate_can_promote_declaratively_after_verified_depth_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = deepcopy(self.source)
            data["games"].append({
                "id":"future-tcg",
                "canonical":"FUTURE TCG",
                "label_ko":"퓨처 TCG",
                "state":"watch",
                "aliases":["future tcg","퓨처 tcg"],
                "purchase_value":"FUTURE TCG",
                "promo_value":"퓨처 TCG",
                "capabilities":{"market":True,"release":True,"promo":True,"purchase":True,"grading":False},
                "regions":["US"],
                "activation_score":0.84,
                "evidence":{
                    "official_live":True,
                    "marketplace_catalog_count":900,
                    "organized_play":True,
                    "collector_rarity_signal":True,
                    "last_verified_at":"2026-10-04T03:00:00+00:00"
                },
                "official_source":"https://example.com/official",
                "market_source":"https://example.net/market"
            })
            write_json(root / "tcg_game_registry.json", data)
            for name in registry.DISCOVERY_FILES:
                if name == "market_prices.json":
                    write_json(root / name, {"entries":{}})
                else:
                    write_json(root / name, {"items":[],"archive_items":[]})
            result = registry.review_registry(
                root, now=registry.dt.datetime(2026,10,4,4,0,tzinfo=registry.dt.timezone.utc), persist=True,
            )
            saved = json.loads((root / "tcg_game_registry.json").read_text(encoding="utf-8"))
            future = next(row for row in saved["games"] if row["id"] == "future-tcg")
            self.assertEqual("promoted", future["state"])
            self.assertTrue(result["persisted"])
            self.assertFalse(result["profit_guaranteed"])
            self.assertFalse(result["market_direction_inferred"])
            self.assertFalse(result["source_code_modified"])
            self.assertFalse(result["git_write"])
            self.assertFalse(result["grading_auto_enabled_for_new_games"])

    def test_unknown_local_name_stays_watch_without_marketplace_depth(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(root / "tcg_game_registry.json", self.source)
            write_json(root / "releases.json", {
                "items":[{
                    "game":"UNSEEN GAME","region":"US","name":"Set 1",
                    "source":"https://example.org/official",
                    "last_verified_at":"2026-10-04T03:00:00+00:00"
                }]
            })
            write_json(root / "promo_events.json", {"items":[]})
            write_json(root / "market_watch.json", {
                "items":[{
                    "game":"UNSEEN GAME","region":"US","name":"Set 1",
                    "sale_status":"거래중","source":"https://example.net/listing"
                }]
            })
            write_json(root / "market_prices.json", {"entries":{}})
            result = registry.review_registry(
                root, now=registry.dt.datetime(2026,10,4,4,0,tzinfo=registry.dt.timezone.utc), persist=True,
            )
            candidate = next(row for row in result["unknown_candidates"] if row["canonical"] == "UNSEEN GAME")
            self.assertEqual("watch", candidate["state"])
            self.assertFalse(candidate["auto_promoted"])
            self.assertEqual("marketplace_depth_and_explicit_official_identity_required", candidate["reason"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
