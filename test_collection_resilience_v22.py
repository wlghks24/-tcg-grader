#!/usr/bin/env python3
from __future__ import annotations

import concurrent.futures
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import detailed_collection_intelligence as detailed
import graded_photo_multi_source as graded
import provider_health_learning as provider


class CollectionResilienceV22Tests(unittest.TestCase):
    def detailed_paths(self, root: Path):
        return mock.patch.multiple(
            detailed,
            LEARNING=root / "detailed_collection_learning.json",
            LEARNING_BACKUP=root / "detailed_collection_learning.json.bak",
        )

    def test_route_circuit_opens_after_repeated_failures_and_success_closes_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.detailed_paths(root):
                for index in range(3):
                    detailed.record_collection_cycle(
                        "ebay", "pokemon",
                        [{"query": f"q{index}", "raw": 0, "accepted": 0, "errors": 1, "elapsed": 0.1}],
                        raw=0, accepted=0, errors=1, elapsed=0.1,
                    )
                opened = detailed.route_plan("ebay", "pokemon")
                self.assertTrue(opened["circuit_open"])
                self.assertFalse(opened["allowed"])
                self.assertGreater(opened["cooldown_remaining_seconds"], 0)
                self.assertFalse(opened["access_control_bypass"])
                self.assertFalse(opened["trust_promotion"])

                detailed.record_collection_cycle(
                    "ebay", "pokemon",
                    [{"query": "recovery", "raw": 4, "accepted": 2, "images": 1, "errors": 0, "elapsed": 0.1}],
                    raw=4, accepted=2, images=1, errors=0, elapsed=0.1,
                )
                recovered = detailed.route_plan("ebay", "pokemon")
                self.assertFalse(recovered["circuit_open"])
                self.assertTrue(recovered["allowed"])
                self.assertEqual(recovered["consecutive_failures"], 0)

    def test_route_circuit_isolated_to_source_and_game(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.detailed_paths(root):
                for _ in range(3):
                    detailed.record_collection_cycle("ebay", "pokemon", [], raw=0, accepted=0, errors=1)
                self.assertTrue(detailed.route_plan("ebay", "pokemon")["circuit_open"])
                self.assertFalse(detailed.route_plan("ebay", "onepiece")["circuit_open"])
                self.assertFalse(detailed.route_plan("kream", "pokemon")["circuit_open"])

    def test_graded_collector_defers_only_open_routes_without_network_probe(self):
        src = {"id": "ebay_public", "name": "eBay", "domain": "ebay.com", "weight": 0.9}
        def plan(_source, game):
            return {
                "circuit_open": game == "pokemon",
                "recovery_probe": False,
            }
        def discover(_src, game):
            return ([{"url": f"https://example.com/{game}", "company": "PSA", "game": game}], [], 1, {})
        with mock.patch.object(graded, "route_plan", side_effect=plan),              mock.patch.object(graded, "_discover_source_game", side_effect=discover) as call:
            source_id, rows, errors, queries, diag = graded._collect_public_source(src)
        self.assertEqual(source_id, "ebay_public")
        called_games = [args.args[1] for args in call.call_args_list]
        self.assertNotIn("pokemon", called_games)
        self.assertIn("onepiece", called_games)
        self.assertIn("naruto", called_games)
        self.assertEqual(diag["circuit_deferred_games"], 1)
        self.assertEqual(errors, [])
        self.assertEqual(queries, 2)

    def _empty_payloads(self, root: Path):
        social = root / "social.json"
        supplementary = root / "supplementary.json"
        promo = root / "promo.json"
        social.write_text(json.dumps({"items": []}), encoding="utf-8")
        supplementary.write_text(json.dumps({"items": []}), encoding="utf-8")
        promo.write_text(json.dumps({"items": []}), encoding="utf-8")
        return social, supplementary, promo

    def test_provider_rows_are_aggregated_once_per_provider_per_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "provider.json"
            backup = root / "provider.json.bak"
            social, supplementary, promo = self._empty_payloads(root)
            rows = [
                {"provider": "duckduckgo", "responded": True, "results": 4, "selected": 2, "errors": 0},
                {"provider": "duckduckgo", "responded": True, "results": 4, "selected": 2, "errors": 0},
            ]
            result = provider.observe(
                rows, memory_path=memory, backup_path=backup,
                social_path=social, supplementary_path=supplementary, promo_path=promo,
                rewrite_social_coverage=False,
            )
            stats = next(x for x in result["providers"] if x["provider"] == "duckduckgo")
            self.assertEqual(stats["runs"], 1)
            self.assertEqual(result["provider_observation_aggregation"]["provider_samples"], 1)
            self.assertEqual(result["provider_observation_aggregation"]["duplicate_or_overlapping_rows_suppressed"], 1)
            self.assertTrue(result["safety"]["process_safe_transaction"])

    def test_concurrent_provider_learning_preserves_both_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "provider.json"
            backup = root / "provider.json.bak"
            social, supplementary, promo = self._empty_payloads(root)

            def observe_once(index: int):
                return provider.observe(
                    [{"provider": "google_news", "responded": True, "results": index + 1, "selected": 1, "errors": 0}],
                    memory_path=memory, backup_path=backup,
                    social_path=social, supplementary_path=supplementary, promo_path=promo,
                    rewrite_social_coverage=False,
                )

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(observe_once, range(2)))
            payload = json.loads(memory.read_text(encoding="utf-8"))
            self.assertEqual(payload["runs"], 2)
            self.assertEqual(payload["providers"]["google_news"]["runs"], 2)


if __name__ == "__main__":
    unittest.main()
