#!/usr/bin/env python3
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import promoted_tcg_source_monitor_v413 as monitor
import purchase_intelligence as purchase_intelligence
import tcg_game_registry as registry
import update_purchase_sources as purchase


ROOT = Path(__file__).resolve().parent


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class PromotedTcgSourceMonitorV413Tests(unittest.TestCase):
    def setUp(self):
        self.registry = json.loads((ROOT / "tcg_game_registry.json").read_text(encoding="utf-8"))

    def test_market_depth_and_collectibility_parsers_are_bounded(self):
        self.assertEqual(7160, monitor._catalog_count("<title>7,160 results in Union Arena</title>"))
        self.assertEqual(4463, monitor._catalog_count("4,463 results in Dragon Ball"))
        self.assertIsNone(monitor._catalog_count("No matching products"))
        self.assertTrue(monitor.RARITY_RE.search("First serialized numbered card showcase"))
        hints = monitor._date_hints("October 16, 2026 and 2027-01-29 are listed.")
        self.assertIn("October 16, 2026", hints)
        self.assertIn("2027-01-29", hints)

    def test_source_status_uses_verified_page_content_without_price_prediction(self):
        html = "<html><body>7,160 results in UNION ARENA · serialized numbered card · October 16, 2026</body></html>"
        with patch.object(monitor, "_fetch", return_value=html):
            row = monitor._source_status("https://example.com/products", market=True)
        self.assertTrue(row["ok"])
        self.assertEqual(7160, row["catalog_count"])
        self.assertTrue(row["collector_rarity_signal"])
        self.assertIn("October 16, 2026", row["date_hints"])
        self.assertNotIn("price_direction", row)

    def test_collect_checks_promoted_and_watch_non_core_only_and_never_claims_profit(self):
        def fake_status(url, *, market=False):
            return {
                "ok": True, "checked_at": "2026-10-04T04:00:00+00:00", "url": url,
                "catalog_count": 1200 if market else None,
                "collector_rarity_signal": market,
                "date_hints": ["October 16, 2026"] if not market else [],
            }
        with patch.object(monitor, "_source_status", side_effect=fake_status):
            payload = monitor.collect(ROOT)
        ids = {row["id"] for row in payload["items"]}
        expected_ids = {
            row["id"] for row in self.registry["games"]
            if row["id"] not in registry.CORE_IDS
            and row["state"] in {"promoted", "watch"}
            and (row["capabilities"].get("market") is True or row["capabilities"].get("release") is True)
        }
        self.assertEqual(expected_ids, ids)
        self.assertTrue({"mtg", "yugioh", "digimon"}.issubset(ids))
        self.assertTrue({
            "flesh-and-blood", "weiss-schwarz", "cardfight-vanguard", "hololive-ocg",
            "shadowverse-evolve", "grand-archive", "final-fantasy-tcg", "sorcery-contested-realm",
        }.issubset(ids))
        self.assertTrue(payload["policy"]["promoted_and_watch_non_core_only"])
        self.assertTrue(payload["policy"]["watch_candidates_can_collect_evidence_before_promotion"])
        self.assertFalse(payload["policy"]["profit_guaranteed"])
        self.assertFalse(payload["policy"]["price_direction_inferred"])
        self.assertFalse(payload["policy"]["stock_claimed"])
        self.assertFalse(payload["policy"]["grading_enabled"])
        self.assertFalse(payload["policy"]["source_code_modified"])
        self.assertFalse(payload["policy"]["git_write"])

    def test_apply_evidence_updates_registry_only_and_preserves_grading_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(root / "tcg_game_registry.json", self.registry)
            payload = {
                "updated_at": "2026-10-04T04:00:00+00:00",
                "items": [{
                    "id": "gundam", "canonical": "GUNDAM CARD GAME", "regions": ["JP", "US"],
                    "official_live": True, "market_live": True,
                    "marketplace_catalog_count": 2500, "collector_rarity_signal": True,
                    "date_hints": ["October 30, 2026"],
                    "official": {"ok": True, "checked_at": "2026-10-04T04:00:00+00:00"},
                    "market": {"ok": True, "checked_at": "2026-10-04T04:00:00+00:00"},
                }],
            }
            result = monitor.apply_verified_evidence(root, payload)
            saved = json.loads((root / "tcg_game_registry.json").read_text(encoding="utf-8"))
            gundam = next(row for row in saved["games"] if row["id"] == "gundam")
            self.assertTrue(result["changed"])
            self.assertEqual(2500, gundam["evidence"]["marketplace_catalog_count"])
            self.assertTrue(gundam["evidence"]["official_live"])
            self.assertTrue(gundam["evidence"]["collector_rarity_signal"])
            self.assertFalse(gundam["capabilities"]["grading"])
            self.assertEqual("promoted", gundam["state"])
            self.assertFalse(result["source_code_modified"])
            self.assertFalse(result["git_write"])

    def test_failed_probe_does_not_erase_previous_verified_depth(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = deepcopy(self.registry)
            before = next(row for row in source["games"] if row["id"] == "unionarena")["evidence"]["marketplace_catalog_count"]
            write_json(root / "tcg_game_registry.json", source)
            payload = {
                "updated_at": "2026-10-04T04:00:00+00:00",
                "items": [{
                    "id": "unionarena", "official_live": False, "market_live": False,
                    "marketplace_catalog_count": None, "collector_rarity_signal": False,
                    "date_hints": [],
                    "official": {"ok": False, "checked_at": "2026-10-04T04:00:00+00:00"},
                    "market": {"ok": False, "checked_at": "2026-10-04T04:00:00+00:00"},
                }],
            }
            monitor.apply_verified_evidence(root, payload)
            saved = json.loads((root / "tcg_game_registry.json").read_text(encoding="utf-8"))
            after = next(row for row in saved["games"] if row["id"] == "unionarena")["evidence"]["marketplace_catalog_count"]
            self.assertEqual(before, after)

    def test_watch_candidate_collects_evidence_then_registry_review_controls_promotion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = deepcopy(self.registry)
            candidate = next(row for row in source["games"] if row["id"] == "shadowverse-evolve")
            candidate["activation_score"] = 0.10
            candidate["evidence"]["marketplace_catalog_count"] = 0
            candidate["evidence"]["collector_rarity_signal"] = False
            write_json(root / "tcg_game_registry.json", source)
            payload = {
                "updated_at": "2026-10-04T04:00:00+00:00",
                "items": [{
                    "id": "shadowverse-evolve",
                    "canonical": "Shadowverse: Evolve",
                    "regions": ["JP", "US"],
                    "official_live": True,
                    "market_live": True,
                    "marketplace_catalog_count": 7038,
                    "collector_rarity_signal": True,
                    "date_hints": ["November 20, 2026"],
                    "official": {"ok": True, "checked_at": "2026-10-04T04:00:00+00:00"},
                    "market": {"ok": True, "checked_at": "2026-10-04T04:00:00+00:00"},
                }],
            }
            applied = monitor.apply_verified_evidence(root, payload)
            interim = json.loads((root / "tcg_game_registry.json").read_text(encoding="utf-8"))
            row = next(item for item in interim["games"] if item["id"] == "shadowverse-evolve")
            self.assertEqual("watch", row["state"])
            self.assertFalse(row["capabilities"]["grading"])
            self.assertEqual(7038, row["evidence"]["marketplace_catalog_count"])
            self.assertTrue(applied["changed"])
            for name in registry.DISCOVERY_FILES:
                if name == "market_prices.json":
                    write_json(root / name, {"entries":{}})
                else:
                    write_json(root / name, {"items":[],"archive_items":[]})
            reviewed = registry.review_registry(
                root, now=registry.dt.datetime(2026,10,4,4,5,tzinfo=registry.dt.timezone.utc), persist=True,
            )
            final = json.loads((root / "tcg_game_registry.json").read_text(encoding="utf-8"))
            row = next(item for item in final["games"] if item["id"] == "shadowverse-evolve")
            decision = next(item for item in reviewed["reviewed"] if item["canonical"] == "Shadowverse: Evolve")
            self.assertEqual("promoted", row["state"])
            self.assertFalse(row["capabilities"]["grading"])
            self.assertEqual("evidence", decision["activation_score_source"])
            self.assertFalse(reviewed["profit_guaranteed"])
            self.assertFalse(reviewed["market_direction_inferred"])

    def test_purchase_sources_are_registry_driven_but_inventory_stays_unverified(self):
        expected = {
            str(row["purchase_value"])
            for row in registry.enabled_games("purchase", root=ROOT)
        }
        self.assertTrue(expected.issubset(purchase.GAMES))
        rows = purchase.ensure_registry_tcg_sources([])
        gundam = [row for row in rows if row.get("games") == ["GUNDAM CARD GAME"]]
        riftbound = [row for row in rows if row.get("games") == ["Riftbound: League of Legends"]]
        self.assertGreaterEqual(len(gundam), 2)
        self.assertGreaterEqual(len(riftbound), 2)
        self.assertTrue(all(row.get("inventory_verified") is False for row in rows))
        normalized = purchase.normalize_source(gundam[0])
        self.assertEqual(["GUNDAM CARD GAME"], normalized["games"])
        self.assertFalse(normalized["inventory_verified"])

    def test_purchase_intelligence_is_registry_driven_for_promoted_games_only(self):
        promoted_value, promoted_terms = purchase_intelligence._resolve_purchase_game("GUNDAM CARD GAME")
        alias_value, alias_terms = purchase_intelligence._resolve_purchase_game("건담")
        watch_value, watch_terms = purchase_intelligence._resolve_purchase_game("Godzilla Card Game")
        self.assertEqual("GUNDAM CARD GAME", promoted_value)
        self.assertEqual("GUNDAM CARD GAME", alias_value)
        self.assertIn("건담", promoted_terms)
        self.assertIn("GUNDAM CARD GAME", alias_terms)
        self.assertIsNone(watch_value)
        self.assertEqual("", watch_terms)
        self.assertEqual(12, purchase_intelligence._bounded_limit("999"))
        self.assertEqual(12, purchase_intelligence._bounded_limit("bad"))



if __name__ == "__main__":
    unittest.main(verbosity=2)
