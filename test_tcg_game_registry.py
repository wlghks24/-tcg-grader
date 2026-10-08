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
        self.assertEqual(180, policy["auto_watch_retire_after_days"])
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
            "hololive OFFICIAL CARD GAME", "Shadowverse: Evolve", "Grand Archive TCG",
            "Final Fantasy TCG", "Sorcery: Contested Realm",
            "Godzilla Card Game", "Palworld OFFICIAL CARD GAME", "Cyberpunk TCG",
            "Elestrals", "Rush of Ikorr", "CookieRun: Braverse TCG", "UniVersus", "Alpha Clash", "MetaZoo",
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
        self.assertEqual("Shadowverse: Evolve", registry.canonical_game("섀도우버스 이볼브", root=ROOT))
        self.assertEqual("Grand Archive TCG", registry.canonical_game("그랜드 아카이브", root=ROOT))
        self.assertEqual("Final Fantasy TCG", registry.canonical_game("FFTCG", root=ROOT))
        self.assertEqual("Sorcery: Contested Realm", registry.canonical_game("Sorcery TCG", root=ROOT))
        self.assertEqual("Godzilla Card Game", registry.canonical_game("고질라 TCG", root=ROOT))
        self.assertEqual("Palworld OFFICIAL CARD GAME", registry.canonical_game("팰월드 카드게임", root=ROOT))
        self.assertEqual("Cyberpunk TCG", registry.canonical_game("사이버펑크 TCG", root=ROOT))
        self.assertEqual("Elestrals", registry.canonical_game("엘레스트럴스 TCG", root=ROOT))
        self.assertEqual("Rush of Ikorr", registry.canonical_game("러시 오브 이코르 TCG", root=ROOT))
        self.assertEqual("CookieRun: Braverse TCG", registry.canonical_game("쿠키런 브레이버스 TCG", root=ROOT))
        self.assertEqual("UniVersus", registry.canonical_game("유니버서스 CCG", root=ROOT))
        self.assertEqual("Alpha Clash", registry.canonical_game("알파 클래시 TCG", root=ROOT))

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
                    "marketplace_catalog_checked_at":"2026-10-04T03:00:00+00:00",
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

    def test_verified_evidence_can_promote_low_seed_watch_without_profit_or_direction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = deepcopy(self.source)
            data["games"].append({
                "id":"evidence-tcg",
                "canonical":"EVIDENCE TCG",
                "label_ko":"에비던스 TCG",
                "state":"watch",
                "aliases":["evidence tcg","에비던스 tcg"],
                "purchase_value":"EVIDENCE TCG",
                "promo_value":"에비던스 TCG",
                "capabilities":{"market":True,"release":True,"promo":True,"purchase":True,"grading":False},
                "regions":["KR","JP","US"],
                "activation_score":0.10,
                "evidence":{
                    "official_live":True,
                    "marketplace_catalog_count":5000,
                    "marketplace_catalog_checked_at":"2026-10-04T03:00:00+00:00",
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
            row = next(item for item in saved["games"] if item["id"] == "evidence-tcg")
            review = next(item for item in result["reviewed"] if item["canonical"] == "EVIDENCE TCG")
            self.assertEqual("promoted", row["state"])
            self.assertFalse(row["capabilities"]["grading"])
            self.assertGreaterEqual(row["evidence"]["verified_activation_score"], result["min_auto_promotion_score"])
            self.assertTrue(row["evidence"]["verified_activation_gate"]["eligible"])
            self.assertTrue(row["evidence"]["verified_activation_gate"]["catalog_ok"])
            self.assertTrue(row["evidence"]["verified_activation_gate"]["official_ok"])
            self.assertTrue(row["evidence"]["verified_activation_gate"]["market_ok"])
            self.assertGreaterEqual(review["evidence_activation_score"], result["min_auto_promotion_score"])
            self.assertEqual("evidence", review["activation_score_source"])
            self.assertTrue(result["activation_score_uses_verified_evidence"])
            self.assertFalse(result["activation_score_uses_price_direction"])
            self.assertFalse(result["activation_score_uses_profit_prediction"])
            self.assertFalse(result["activation_score_uses_user_behavior"])
            self.assertFalse(result["profit_guaranteed"])
            self.assertFalse(result["market_direction_inferred"])

    def test_persisted_verified_score_never_feeds_back_into_activation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = deepcopy(self.source)
            candidate = next(row for row in data["games"] if row["id"] == "shadowverse-evolve")
            candidate["activation_score"] = 0.10
            candidate["evidence"]["verified_activation_score"] = 0.99
            candidate["evidence"]["verified_activation_gate"] = {
                "eligible": True, "catalog_ok": True, "official_ok": True,
                "market_ok": True, "signal_count": 4,
            }
            candidate["evidence"]["official_live"] = True
            candidate["evidence"]["last_verified_at"] = "2026-01-01T00:00:00+00:00"
            candidate["evidence"]["marketplace_catalog_count"] = 7038
            candidate["evidence"]["marketplace_catalog_checked_at"] = "2026-01-01T00:00:00+00:00"
            candidate["evidence"]["organized_play"] = True
            candidate["evidence"]["collector_rarity_signal"] = True
            write_json(root / "tcg_game_registry.json", data)
            for name in registry.DISCOVERY_FILES:
                write_json(root / name, {"entries":{}} if name == "market_prices.json" else {"items":[],"archive_items":[]})
            result = registry.review_registry(
                root, now=registry.dt.datetime(2026,10,4,4,0,tzinfo=registry.dt.timezone.utc), persist=True,
            )
            saved = json.loads((root / "tcg_game_registry.json").read_text(encoding="utf-8"))
            row = next(item for item in saved["games"] if item["id"] == "shadowverse-evolve")
            review = next(item for item in result["reviewed"] if item["canonical"] == "Shadowverse: Evolve")
            self.assertEqual("watch", row["state"])
            self.assertFalse(row["evidence"]["verified_activation_gate"]["eligible"])
            self.assertLess(row["evidence"]["verified_activation_score"], result["min_auto_promotion_score"])
            self.assertEqual(
                review["evidence_activation_score"],
                review["activation_score"],
            )
            self.assertLess(review["activation_score"], 0.99)
            self.assertEqual("evidence", review["activation_score_source"])

    def test_high_seed_cannot_keep_stale_watch_promoted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = deepcopy(self.source)
            candidate = next(row for row in data["games"] if row["id"] == "shadowverse-evolve")
            candidate["activation_score"] = 0.99
            candidate["evidence"]["official_live"] = True
            candidate["evidence"]["last_verified_at"] = "2026-01-01T00:00:00+00:00"
            candidate["evidence"]["marketplace_catalog_count"] = 7038
            candidate["evidence"]["marketplace_catalog_checked_at"] = "2026-01-01T00:00:00+00:00"
            candidate["evidence"]["organized_play"] = True
            candidate["evidence"]["collector_rarity_signal"] = True
            write_json(root / "tcg_game_registry.json", data)
            for name in registry.DISCOVERY_FILES:
                write_json(
                    root / name,
                    {"entries":{}} if name == "market_prices.json"
                    else {"items":[],"archive_items":[]},
                )
            result = registry.review_registry(
                root,
                now=registry.dt.datetime(2026,10,4,4,0,tzinfo=registry.dt.timezone.utc),
                persist=True,
            )
            saved = json.loads((root / "tcg_game_registry.json").read_text(encoding="utf-8"))
            row = next(item for item in saved["games"] if item["id"] == "shadowverse-evolve")
            review = next(item for item in result["reviewed"] if item["canonical"] == "Shadowverse: Evolve")
            self.assertEqual("watch", row["state"])
            self.assertEqual(0.99, review["seed_activation_score"])
            self.assertEqual(review["evidence_activation_score"], review["activation_score"])
            self.assertLess(review["activation_score"], result["min_auto_promotion_score"])
            self.assertEqual("evidence", review["activation_score_source"])
            self.assertFalse(row["capabilities"]["grading"])

    def test_stale_market_depth_cannot_promote_watch_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = deepcopy(self.source)
            candidate = next(row for row in data["games"] if row["id"] == "shadowverse-evolve")
            candidate["activation_score"] = 0.10
            candidate["evidence"]["official_live"] = True
            candidate["evidence"]["last_verified_at"] = "2026-10-04T03:00:00+00:00"
            candidate["evidence"]["marketplace_catalog_count"] = 7038
            candidate["evidence"]["marketplace_catalog_checked_at"] = "2026-01-01T00:00:00+00:00"
            candidate["evidence"]["organized_play"] = True
            candidate["evidence"]["collector_rarity_signal"] = True
            write_json(root / "tcg_game_registry.json", data)
            for name in registry.DISCOVERY_FILES:
                if name == "market_prices.json":
                    write_json(root / name, {"entries":{}})
                else:
                    write_json(root / name, {"items":[],"archive_items":[]})
            result = registry.review_registry(
                root, now=registry.dt.datetime(2026,10,4,4,0,tzinfo=registry.dt.timezone.utc), persist=False,
            )
            row = next(item for item in result["reviewed"] if item["canonical"] == "Shadowverse: Evolve")
            self.assertEqual("watch", row["state"])
            self.assertFalse(row["catalog_ok"])
            self.assertNotIn("marketplace_depth", row["signals"])
            self.assertFalse(row["eligible"])

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
                    "sale_status":"거래중","source":"https://example.net/listing",
                    "link_checked_at":"2026-10-04T03:00:00+00:00"
                }]
            })
            write_json(root / "market_prices.json", {"entries":{}})
            result = registry.review_registry(
                root, now=registry.dt.datetime(2026,10,4,4,0,tzinfo=registry.dt.timezone.utc), persist=True,
            )
            candidate = next(row for row in result["unknown_candidates"] if row["canonical"] == "UNSEEN GAME")
            self.assertEqual("watch", candidate["state"])
            self.assertFalse(candidate["auto_promoted"])
            self.assertTrue(candidate["auto_watch_eligible"])
            self.assertTrue(candidate["auto_watch_created"])
            self.assertEqual("verified_official_and_independent_market_sources", candidate["reason"])
            saved = json.loads((root / "tcg_game_registry.json").read_text(encoding="utf-8"))
            seeded = next(row for row in saved["games"] if row["canonical"] == "UNSEEN GAME")
            self.assertEqual("watch", seeded["state"])
            self.assertEqual(0.0, seeded["activation_score"])
            self.assertFalse(seeded["capabilities"]["grading"])
            self.assertIsNone(seeded["evidence"]["marketplace_catalog_count"])
            self.assertIn("UNSEEN GAME", result["auto_watch_created_games"])


    def test_unknown_candidate_same_host_does_not_auto_seed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(root / "tcg_game_registry.json", self.source)
            write_json(root / "releases.json", {
                "items":[{
                    "game":"SAME HOST TCG","region":"US","name":"Set 1",
                    "source":"https://example.org/official",
                    "last_verified_at":"2026-10-04T03:00:00+00:00"
                }]
            })
            write_json(root / "promo_events.json", {"items":[]})
            write_json(root / "market_watch.json", {
                "items":[{
                    "game":"SAME HOST TCG","region":"US","name":"Set 1",
                    "sale_status":"거래중","source":"https://example.org/market",
                    "link_checked_at":"2026-10-04T03:00:00+00:00"
                }]
            })
            write_json(root / "market_prices.json", {"entries":{}})
            result = registry.review_registry(
                root, now=registry.dt.datetime(2026,10,4,4,0,tzinfo=registry.dt.timezone.utc), persist=True,
            )
            candidate = next(row for row in result["unknown_candidates"] if row["canonical"] == "SAME HOST TCG")
            self.assertFalse(candidate["auto_watch_eligible"])
            self.assertFalse(candidate["auto_watch_created"])
            self.assertEqual("independent_source_hosts_required", candidate["reason"])
            saved = json.loads((root / "tcg_game_registry.json").read_text(encoding="utf-8"))
            self.assertNotIn("SAME HOST TCG", {row["canonical"] for row in saved["games"]})


    def test_stale_auto_seeded_watch_is_retired_but_manual_watch_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = deepcopy(self.source)
            stale = {
                "official_live": True,
                "marketplace_catalog_count": 700,
                "marketplace_catalog_checked_at": "2026-01-01T00:00:00+00:00",
                "organized_play": False,
                "collector_rarity_signal": False,
                "last_verified_at": "2026-01-01T00:00:00+00:00",
            }
            auto = dict(stale)
            auto["auto_watch_seeded"] = True
            auto["auto_watch_seeded_at"] = "2026-01-01T00:00:00+00:00"
            data["games"].extend([
                {
                    "id":"old-auto-tcg","canonical":"OLD AUTO TCG","label_ko":"OLD AUTO TCG",
                    "state":"watch","aliases":["OLD AUTO TCG"],"purchase_value":"OLD AUTO TCG",
                    "promo_value":"OLD AUTO TCG",
                    "capabilities":{"market":True,"release":True,"promo":True,"purchase":True,"grading":False},
                    "regions":["US"],"activation_score":0.0,"evidence":auto,
                    "official_source":"https://example.org/official",
                    "market_source":"https://example.net/market",
                },
                {
                    "id":"old-manual-tcg","canonical":"OLD MANUAL TCG","label_ko":"OLD MANUAL TCG",
                    "state":"watch","aliases":["OLD MANUAL TCG"],"purchase_value":"OLD MANUAL TCG",
                    "promo_value":"OLD MANUAL TCG",
                    "capabilities":{"market":True,"release":True,"promo":True,"purchase":True,"grading":False},
                    "regions":["US"],"activation_score":0.0,"evidence":dict(stale),
                    "official_source":"https://example.com/official",
                    "market_source":"https://example.net/manual-market",
                },
            ])
            write_json(root / "tcg_game_registry.json", data)
            for name in registry.DISCOVERY_FILES:
                write_json(root / name, {"entries":{}} if name == "market_prices.json" else {"items":[],"archive_items":[]})
            result = registry.review_registry(
                root, now=registry.dt.datetime(2026,10,4,6,0,tzinfo=registry.dt.timezone.utc), persist=True,
            )
            saved = json.loads((root / "tcg_game_registry.json").read_text(encoding="utf-8"))
            canonicals = {row["canonical"] for row in saved["games"]}
            self.assertNotIn("OLD AUTO TCG", canonicals)
            self.assertIn("OLD MANUAL TCG", canonicals)
            self.assertIn("OLD AUTO TCG", result["retired_auto_watch_games"])
            self.assertEqual(180, result["auto_watch_retire_after_days"])

    def test_fresh_auto_seeded_watch_is_not_retired(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = deepcopy(self.source)
            data["games"].append({
                "id":"fresh-auto-tcg","canonical":"FRESH AUTO TCG","label_ko":"FRESH AUTO TCG",
                "state":"watch","aliases":["FRESH AUTO TCG"],"purchase_value":"FRESH AUTO TCG",
                "promo_value":"FRESH AUTO TCG",
                "capabilities":{"market":True,"release":True,"promo":True,"purchase":True,"grading":False},
                "regions":["US"],"activation_score":0.0,
                "evidence":{
                    "official_live":True,"marketplace_catalog_count":None,
                    "organized_play":False,"collector_rarity_signal":False,
                    "last_verified_at":"2026-09-25T00:00:00+00:00",
                    "auto_watch_seeded":True,"auto_watch_seeded_at":"2026-09-25T00:00:00+00:00",
                },
                "official_source":"https://example.org/official",
                "market_source":"https://example.net/market",
            })
            write_json(root / "tcg_game_registry.json", data)
            for name in registry.DISCOVERY_FILES:
                write_json(root / name, {"entries":{}} if name == "market_prices.json" else {"items":[],"archive_items":[]})
            result = registry.review_registry(
                root, now=registry.dt.datetime(2026,10,4,6,0,tzinfo=registry.dt.timezone.utc), persist=True,
            )
            saved = json.loads((root / "tcg_game_registry.json").read_text(encoding="utf-8"))
            self.assertIn("FRESH AUTO TCG", {row["canonical"] for row in saved["games"]})
            self.assertNotIn("FRESH AUTO TCG", result["retired_auto_watch_games"])

    def test_rush_of_ikorr_stays_watch_without_verified_market_depth(self):
        row = next(item for item in self.source["games"] if item["id"] == "rush-of-ikorr")
        self.assertEqual("watch", row["state"])
        self.assertEqual(0.0, row["activation_score"])
        self.assertTrue(row["evidence"]["official_live"])
        self.assertTrue(row["evidence"]["organized_play"])
        self.assertEqual(648, row["evidence"]["official_card_catalog_count"])
        self.assertIsNone(row["evidence"]["marketplace_catalog_count"])
        self.assertTrue(row["evidence"]["market_depth_unverified"])
        self.assertFalse(row["capabilities"]["grading"])
        self.assertNotIn(
            "Rush of Ikorr",
            {item["canonical"] for item in registry.enabled_games("purchase", root=ROOT)},
        )
        self.assertIn(
            "Rush of Ikorr",
            {item["canonical"] for item in registry.enabled_games("purchase", root=ROOT, include_watch=True)},
        )


    def test_metazoo_is_watch_only_with_verified_2026_market_depth(self):
        row = next(item for item in self.source["games"] if item["id"] == "metazoo")
        self.assertEqual("watch", row["state"])
        self.assertEqual(0, row["activation_score"])
        self.assertEqual(3456, row["evidence"]["marketplace_catalog_count"])
        self.assertTrue(row["evidence"]["official_live"])
        self.assertTrue(row["evidence"]["organized_play"])
        self.assertFalse(row["capabilities"]["grading"])
        self.assertNotIn(
            "MetaZoo",
            {item["canonical"] for item in registry.enabled_games("market", root=ROOT)},
        )
        self.assertIn(
            "MetaZoo",
            {item["canonical"] for item in registry.enabled_games("market", root=ROOT, include_watch=True)},
        )


    def test_elestrals_still_promotes_only_through_verified_review_gate(self):
        result = registry.review_registry(
            ROOT, now=registry.dt.datetime(2026,10,4,6,0,tzinfo=registry.dt.timezone.utc), persist=False,
        )
        checked = next(row for row in result["reviewed"] if row["canonical"] == "Elestrals")
        self.assertEqual("promoted", checked["state"])
        self.assertTrue(checked["eligible"])
        self.assertGreaterEqual(checked["evidence_activation_score"], self.source["policy"]["min_auto_promotion_score"])
        self.assertFalse(result["profit_guaranteed"])
        self.assertFalse(result["market_direction_inferred"])


    def test_stale_market_price_cannot_count_as_activation_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = deepcopy(self.source)
            data["games"].append({
                "id":"freshness-tcg","canonical":"FRESHNESS TCG","label_ko":"FRESHNESS TCG",
                "state":"watch","aliases":["FRESHNESS TCG"],"purchase_value":"FRESHNESS TCG",
                "promo_value":"FRESHNESS TCG",
                "capabilities":{"market":True,"release":True,"promo":True,"purchase":True,"grading":False},
                "regions":["US"],"activation_score":0.0,
                "evidence":{
                    "official_live":True,"marketplace_catalog_count":None,
                    "organized_play":True,"collector_rarity_signal":True,
                    "last_verified_at":"2026-10-04T03:00:00+00:00",
                },
                "official_source":"https://example.org/official",
                "market_source":"https://example.net/market",
            })
            write_json(root / "tcg_game_registry.json", data)
            write_json(root / "releases.json", {"items":[],"archive_items":[]})
            write_json(root / "promo_events.json", {"items":[],"archive_items":[]})
            write_json(root / "market_watch.json", {"items":[],"archive_items":[]})
            write_json(root / "market_prices.json", {"entries":{
                "stale":{
                    "game":"FRESHNESS TCG","source":"https://example.net/price",
                    "last_verified_at":"2026-01-01T00:00:00+00:00","price":100.0
                }
            }})
            result = registry.review_registry(
                root, now=registry.dt.datetime(2026,10,4,4,0,tzinfo=registry.dt.timezone.utc), persist=False,
            )
            review = next(row for row in result["reviewed"] if row["canonical"] == "FRESHNESS TCG")
            self.assertEqual("watch", review["state"])
            self.assertFalse(review["market_ok"])
            self.assertNotIn("market_price", review["signals"])

    def test_fresh_market_price_can_count_as_activation_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = deepcopy(self.source)
            data["games"].append({
                "id":"fresh-market-tcg","canonical":"FRESH MARKET TCG","label_ko":"FRESH MARKET TCG",
                "state":"watch","aliases":["FRESH MARKET TCG"],"purchase_value":"FRESH MARKET TCG",
                "promo_value":"FRESH MARKET TCG",
                "capabilities":{"market":True,"release":True,"promo":True,"purchase":True,"grading":False},
                "regions":["US"],"activation_score":0.0,
                "evidence":{
                    "official_live":True,"marketplace_catalog_count":None,
                    "organized_play":True,"collector_rarity_signal":True,
                    "last_verified_at":"2026-10-04T03:00:00+00:00",
                },
                "official_source":"https://example.org/official",
                "market_source":"https://example.net/market",
            })
            write_json(root / "tcg_game_registry.json", data)
            write_json(root / "releases.json", {"items":[],"archive_items":[]})
            write_json(root / "promo_events.json", {"items":[],"archive_items":[]})
            write_json(root / "market_watch.json", {"items":[],"archive_items":[]})
            write_json(root / "market_prices.json", {"entries":{
                "fresh":{
                    "game":"FRESH MARKET TCG","source":"https://example.net/price",
                    "last_verified_at":"2026-10-04T03:30:00+00:00","price":100.0
                }
            }})
            result = registry.review_registry(
                root, now=registry.dt.datetime(2026,10,4,4,0,tzinfo=registry.dt.timezone.utc), persist=False,
            )
            review = next(row for row in result["reviewed"] if row["canonical"] == "FRESH MARKET TCG")
            self.assertIn("market_price", review["signals"])
            self.assertTrue(review["market_ok"])


    def test_watch_games_cannot_enter_live_official_event_collector(self):
        import update_promo_events as promo
        from unittest.mock import patch

        active = {game for _region, game, _url in promo.INDEXES}
        watch_rows = [
            row for row in self.source["games"]
            if row.get("state") == "watch"
            and row.get("capabilities", {}).get("promo") is True
        ]
        self.assertTrue(watch_rows)
        for row in watch_rows:
            label = row.get("promo_value") or row.get("label_ko") or row["canonical"]
            self.assertNotIn(label, active)
        self.assertIn("디즈니 로카나", active)  # promoted official source remains live
        lorcana_sources = [url for _region, game, url in promo.INDEXES if game == "디즈니 로카나"]
        self.assertEqual(["https://www.disneylorcana.com/en-US/play/lorcana-challenge"], lorcana_sources)
        self.assertNotIn("플레시 앤 블러드", active)  # a WATCH 403 cannot block production

        promoted = deepcopy(self.source)
        watch = next(row for row in promoted["games"] if row["id"] == "flesh-and-blood")
        watch["state"] = "promoted"
        with patch.object(registry, "load_registry", return_value=promoted):
            promoted_indexes, _, _ = promo._registry_event_config()
        self.assertIn("플레시 앤 블러드", {game for _, game, _ in promoted_indexes})
        # Promotion never enables grading; the registry still decides separately.
        self.assertIs(watch["capabilities"]["grading"], False)

    def test_expanded_runtime_collectors_follow_registry(self):
        import urllib.parse
        import box_hit_market_discovery as market_discovery
        import update_promo_events as promo
        import update_releases as releases

        market_games = {
            row["canonical"] for row in self.source["games"]
            if row.get("capabilities", {}).get("market") is True
        }
        self.assertTrue(market_games.issubset(set(market_discovery.GAMES)))

        promo_games = {
            row.get("promo_value") or row.get("label_ko") or row.get("canonical")
            for row in self.source["games"]
            if row.get("id") not in registry.CORE_IDS
            and row.get("state") == "promoted"
            and row.get("capabilities", {}).get("promo") is True
        }
        configured_promo = {game for _region, game, _url in promo.INDEXES}
        self.assertTrue(promo_games.issubset(set(promo.GAMES)))
        self.assertTrue(promo_games.issubset(configured_promo))
        self.assertGreater(len(promo.EVENT_SCOPE_PAIRS), 9)
        coverage = promo.coverage_summary([
            {"game": "OUTSIDE", "region": "OUTSIDE", "category": "promo"},
        ])
        self.assertLessEqual(coverage["covered_game_region_pairs"], coverage["expected_game_region_pairs"])
        self.assertLessEqual(coverage["movie_game_region_pairs"], coverage["expected_game_region_pairs"])

        release_hosts = {
            (urllib.parse.urlsplit(str(row.get("official_source") or "")).hostname or "").lower()
            for row in self.source["games"]
            if row.get("id") not in registry.CORE_IDS
            and row.get("capabilities", {}).get("release") is True
        }
        self.assertTrue({host for host in release_hosts if host}.issubset(releases.ALLOWED))
        self.assertEqual(
            "2026-10-23",
            releases._parse_registry_date("Official Release Date October 23, 2026", require_cue=True),
        )
        self.assertIsNone(
            releases._parse_registry_date("Copyright 2026-10-23", require_cue=True),
        )

    def test_expanded_box_and_trading_surfaces_consume_verified_runtime_data(self):
        expander = (ROOT / "market_catalog_expander.js").read_text(encoding="utf-8")
        stats = (ROOT / "box_knowledge_stats.js").read_text(encoding="utf-8")
        page = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("releases.archive_items", expander)
        self.assertIn("['KR','JP','US','GLOBAL']", expander)
        self.assertIn('id="boxKbGame"', stats)
        self.assertIn("tcg_game_registry.json", stats)
        self.assertIn("확장 TCG 전체 수집 후 다시 확인", page)
        self.assertIn("가격 확인 중|확인 중|미정", page)


if __name__ == "__main__":
    unittest.main(verbosity=2)
