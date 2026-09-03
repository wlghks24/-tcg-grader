#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import adaptive_collection_learner
import event_source_expansion_v145 as expansion
import multi_route_event_discovery


expansion.apply()


class EventSourceExpansionV145Tests(unittest.TestCase):
    def _learner(self, root: Path):
        return adaptive_collection_learner.AdaptiveCollectionLearner(
            memory_path=root / "memory.json",
            backup_path=root / "memory.json.bak",
            report_path=root / "report.json",
        )

    def test_all_three_games_and_regions_have_expanded_discovery_targets(self):
        status = expansion.apply()
        self.assertEqual(145, status["patch"])
        self.assertEqual(9, status["static_target_cells"])
        self.assertGreaterEqual(status["static_target_count"], 60)
        self.assertIs(status["trust_auto_promotion"], False)
        self.assertEqual(0.0, status["unverified_source_learning_weight"])
        for game in ("포켓몬 카드", "원피스 카드", "나루토 카드"):
            for region in ("KR", "JP", "US"):
                self.assertTrue(multi_route_event_discovery.PARTNER_DOMAINS[(game, region)])

    def test_high_value_discovery_targets_are_present_but_not_official(self):
        self.assertIn("pokemoncenter-online.com", multi_route_event_discovery.PARTNER_DOMAINS[("포켓몬 카드", "JP")])
        self.assertIn("pokemoncenter.com", multi_route_event_discovery.PARTNER_DOMAINS[("포켓몬 카드", "US")])
        self.assertIn("shonenjump.com", multi_route_event_discovery.PARTNER_DOMAINS[("원피스 카드", "JP")])
        self.assertIn("bandai-tcg-plus.com", multi_route_event_discovery.PARTNER_DOMAINS[("나루토 카드", "JP")])
        self.assertNotIn("shonenjump.com", adaptive_collection_learner.GAME_CONFIG["원피스"]["official_hosts"])
        self.assertFalse(multi_route_event_discovery._official_for("원피스 카드", "JP", "shonenjump.com"))

    def test_verified_nike_recovery_teaches_source_targets_without_relabeling_official(self):
        targets = expansion._verified_file_targets()
        onepiece_jp = targets.get(("원피스 카드", "JP"), set())
        self.assertIn("shonenjump.com", onepiece_jp)
        self.assertNotIn("one-piece.com", onepiece_jp)
        self.assertFalse(multi_route_event_discovery._official_for("원피스 카드", "JP", "shonenjump.com"))

    def test_target_window_is_bounded_and_rotates_tail(self):
        hosts = tuple(f"source{i}.example.com" for i in range(12))
        first = expansion._target_window(hosts, "onepiece|JP|partner", slot=100)
        second = expansion._target_window(hosts, "onepiece|JP|partner", slot=101)
        self.assertEqual(8, len(first))
        self.assertEqual(8, len(second))
        self.assertEqual(hosts[:4], first[:4])
        self.assertEqual(hosts[:4], second[:4])
        self.assertNotEqual(first[4:], second[4:])

    def test_scoped_learned_host_reuses_correct_game_and_region_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            learner = self._learner(root)
            learner._learn_row(
                "원피스", "JP",
                {
                    "title": "ONE PIECE verified partner campaign",
                    "url": "https://verified-partner.example.jp/campaign",
                },
                weight=1.5,
                verified=True,
            )
            stat = learner.memory["host_stats"]["verified-partner.example.jp"]
            self.assertGreater(stat.get("game_regions", {}).get("원피스|JP", 0), 0)
            before = int(learner.memory.get("rotation") or 0)
            plan = learner.plan_queries("원피스", max_queries=8)
            after = int(learner.memory.get("rotation") or 0)
            self.assertEqual(before + 1, after, "one plan call must advance rotation exactly once")
            learned = [row for row in plan if row.get("family") == "learned-host"]
            self.assertTrue(learned)
            self.assertEqual("JP", learned[0].get("region"))
            self.assertIn("site:verified-partner.example.jp", learned[0].get("query", ""))

            pokemon_plan = learner.plan_queries("포켓몬", max_queries=8)
            self.assertFalse(any("verified-partner.example.jp" in row.get("query", "") for row in pokemon_plan))

    def test_unverified_social_payload_cannot_create_learned_source_target(self):
        with tempfile.TemporaryDirectory() as td:
            learner = self._learner(Path(td))
            learned = learner.learn_from_payload({
                "items": [{
                    "game": "원피스 카드",
                    "region": "JP",
                    "title": "rumor only collaboration",
                    "source": "https://rumor-only.example.jp/post/1",
                    "verified": False,
                    "official_account_verified": False,
                    "official_domain_match": False,
                    "cross_checked": False,
                    "confidence": 0.60,
                    "source_tier": "C-community",
                }]
            }, origin="social")
            self.assertEqual(0, learned)
            self.assertNotIn("rumor-only.example.jp", learner.memory.get("host_stats", {}))

    def test_learned_host_error_feedback_reduces_future_source_score(self):
        with tempfile.TemporaryDirectory() as td:
            learner = self._learner(Path(td))
            learner._learn_row(
                "나루토", "US",
                {"title": "NARUTO official cross-check", "url": "https://verified-source.example.com/news"},
                weight=1.5,
                verified=True,
            )
            stat = learner.memory["host_stats"]["verified-source.example.com"]
            before = float(stat.get("score") or 0.0)
            learner.observe_search(
                "나루토",
                "NARUTO CARD GAME event site:verified-source.example.com",
                [],
                error="TimeoutError: source timeout",
                family="learned-host",
                region="US",
            )
            stat = learner.memory["host_stats"]["verified-source.example.com"]
            self.assertGreaterEqual(int(stat.get("failures") or 0), 1)
            self.assertLess(float(stat.get("score") or 0.0), before)


if __name__ == "__main__":
    unittest.main()
