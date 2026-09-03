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
        self.assertIs(status["scope_evidence_isolation"], True)
        self.assertIs(status["provider_errors_do_not_demote_target_host"], True)
        self.assertIs(status["balanced_source_pool"], True)
        self.assertIs(status["www_alias_dedup"], True)
        self.assertIs(status["apply_thread_safe"], True)
        self.assertIs(status["collection_call_serialized"], True)
        self.assertIs(status["unverified_direct_learn_blocked"], True)
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
        self.assertIn("shonenjump.com", {host.removeprefix("www.") for host in onepiece_jp})
        self.assertNotIn("one-piece.com", onepiece_jp)
        self.assertFalse(multi_route_event_discovery._official_for("원피스 카드", "JP", "shonenjump.com"))

    def test_self_declared_official_flags_are_not_enough_for_source_learning(self):
        row = {
            "game": "원피스 카드",
            "region": "JP",
            "source": "https://untrusted.example.jp/post/1",
            "verified": False,
            "official_domain_match": True,
            "source_grade": "official",
            "confidence": 0.99,
        }
        self.assertFalse(expansion._strong_evidence_row(row))

        official = {
            "game": "원피스 카드",
            "region": "JP",
            "source": "https://one-piece.com/news/123",
            "verified": True,
            "confidence": 0.99,
        }
        self.assertTrue(expansion._strong_evidence_row(official))

    def test_cross_checked_source_learning_requires_two_concrete_hosts(self):
        base = {
            "game": "나루토 카드",
            "region": "US",
            "cross_checked": True,
            "confidence": 0.90,
            "source_tier": "B-news",
        }
        self.assertFalse(expansion._strong_evidence_row({**base, "evidence_hosts": ["only-one.example.com"]}))
        self.assertTrue(expansion._strong_evidence_row({
            **base,
            "evidence_hosts": ["first.example.com", "second.example.com"],
        }))
        self.assertFalse(expansion._strong_evidence_row({
            **base,
            "source_tier": "C-community",
            "evidence_hosts": ["first.example.com", "second.example.com"],
        }))

    def test_host_validation_and_www_alias_dedup(self):
        self.assertEqual("example.com", expansion._host_key("https://www.example.com/path"))
        self.assertEqual("", expansion._host("http://127.0.0.1/a"))
        self.assertEqual("", expansion._host("localhost"))
        self.assertEqual("", expansion._host("bad..example.com"))
        merged = expansion._merge_hosts(("www.example.com", "example.com", "other.example.com"), cap=8)
        self.assertEqual(2, len(merged))
        self.assertEqual("example.com", expansion._host_key(merged[0]))

    def test_target_window_is_bounded_and_rotates_tail(self):
        hosts = tuple(f"source{i}.example.com" for i in range(12))
        first = expansion._target_window(hosts, "onepiece|JP|partner", slot=100)
        second = expansion._target_window(hosts, "onepiece|JP|partner", slot=101)
        self.assertEqual(8, len(first))
        self.assertEqual(8, len(second))
        self.assertEqual(hosts[:4], first[:4])
        self.assertEqual(hosts[:4], second[:4])
        self.assertNotEqual(first[4:], second[4:])

    def test_balanced_runtime_pool_cannot_starve_new_source_families(self):
        existing = tuple(f"existing{i}.example.com" for i in range(30))
        merged = expansion._balanced_runtime_hosts(
            existing,
            ("verified.example.com",),
            ("adaptive.example.com",),
            ("static.example.com",),
            cap=24,
        )
        self.assertEqual(24, len(merged))
        self.assertEqual(existing[:4], merged[:4])
        self.assertIn("verified.example.com", merged)
        self.assertIn("adaptive.example.com", merged)
        self.assertIn("static.example.com", merged)

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
            self.assertGreater(stat.get("game_region_verified", {}).get("원피스|JP", 0), 0)
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

    def test_old_global_scope_counters_cannot_leak_evidence_to_another_region(self):
        with tempfile.TemporaryDirectory() as td:
            learner = self._learner(Path(td))
            learner.memory["host_stats"]["legacy-mixed.example.com"] = {
                "official": 1,
                "score": 10.0,
                "game_regions": {"원피스|JP": 1, "원피스|KR": 99},
                "scoped_verified": 1,
                "scoped_cross_checked": 0,
            }
            expansion._sanitize_adaptive_host_scopes(learner)
            scoped = expansion._scoped_learned_hosts(learner, "원피스", limit=12)
            self.assertFalse(any(row[2] == "legacy-mixed.example.com" for row in scoped))

    def test_single_scope_legacy_counter_migrates_fail_safe(self):
        with tempfile.TemporaryDirectory() as td:
            learner = self._learner(Path(td))
            learner.memory["host_stats"]["legacy-single.example.com"] = {
                "official": 1,
                "score": 2.0,
                "game_regions": {"원피스|JP": 3},
                "scoped_verified": 1,
                "scoped_cross_checked": 0,
            }
            expansion._sanitize_adaptive_host_scopes(learner)
            stat = learner.memory["host_stats"]["legacy-single.example.com"]
            self.assertEqual(1, stat.get("game_region_verified", {}).get("원피스|JP"))
            scoped = expansion._scoped_learned_hosts(learner, "원피스", limit=12)
            self.assertTrue(any(row[2] == "legacy-single.example.com" and row[3] == "JP" for row in scoped))

    def test_unverified_direct_learn_row_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            learner = self._learner(Path(td))
            learner._learn_row(
                "원피스", "KR",
                {"title": "rumor", "url": "https://rumor-direct.example.com/post"},
                weight=2.0,
                verified=False,
                cross_checked=False,
            )
            self.assertNotIn("rumor-direct.example.com", learner.memory.get("host_stats", {}))
            safety = learner.memory.get("channel_stats", {}).get("v145_source_scope_safety", {})
            self.assertGreaterEqual(int(safety.get("ignored_unverified_learn_rows") or 0), 1)

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

    def test_search_provider_error_does_not_demote_target_host(self):
        with tempfile.TemporaryDirectory() as td:
            learner = self._learner(Path(td))
            learner._learn_row(
                "나루토", "US",
                {"title": "NARUTO verified source", "url": "https://verified-source.example.com/news"},
                weight=1.5,
                verified=True,
            )
            stat = learner.memory["host_stats"]["verified-source.example.com"]
            before = float(stat.get("score") or 0.0)
            failures_before = int(stat.get("failures") or 0)
            learner.observe_search(
                "나루토",
                "NARUTO CARD GAME event site:verified-source.example.com",
                [],
                error="Bing learned-host: HTTP 429 · cooldown-required",
                family="learned-host",
                region="US",
            )
            stat = learner.memory["host_stats"]["verified-source.example.com"]
            self.assertEqual(failures_before, int(stat.get("failures") or 0))
            self.assertGreaterEqual(int(stat.get("probe_errors") or 0), 1)
            self.assertAlmostEqual(before, float(stat.get("score") or 0.0), places=6)
            self.assertGreaterEqual(stat.get("game_region_probe_errors", {}).get("나루토|US", 0), 1)

    def test_empty_successful_probe_reduces_only_that_scope_yield_score(self):
        with tempfile.TemporaryDirectory() as td:
            learner = self._learner(Path(td))
            learner._learn_row(
                "원피스", "JP",
                {"title": "verified source", "url": "https://quiet-source.example.jp/news"},
                weight=1.5,
                verified=True,
            )
            stat = learner.memory["host_stats"]["quiet-source.example.jp"]
            before = float(stat.get("score") or 0.0)
            learner.observe_search(
                "원피스",
                "ONE PIECE event site:quiet-source.example.jp",
                [],
                error="",
                family="learned-host",
                region="JP",
            )
            stat = learner.memory["host_stats"]["quiet-source.example.jp"]
            self.assertLess(float(stat.get("score") or 0.0), before)
            self.assertGreaterEqual(stat.get("game_region_probe_empty", {}).get("원피스|JP", 0), 1)
            self.assertEqual(0, stat.get("game_region_probe_empty", {}).get("원피스|KR", 0))

    def test_scoped_probe_is_not_dropped_when_original_plan_is_under_budget(self):
        with tempfile.TemporaryDirectory() as td:
            learner = self._learner(Path(td))
            learner._learn_row(
                "원피스", "JP",
                {"title": "verified partner", "url": "https://under-budget.example.jp/news"},
                weight=1.5,
                verified=True,
            )
            original = expansion._ORIGINAL_ADAPTIVE_PLAN
            try:
                expansion._ORIGINAL_ADAPTIVE_PLAN = lambda self, keyword, max_queries=None: [
                    {"query": "kr baseline", "family": "regional", "region": "KR"},
                    {"query": "jp baseline", "family": "regional", "region": "JP"},
                    {"query": "us baseline", "family": "regional", "region": "US"},
                ]
                plan = expansion._v145_plan_queries(learner, "원피스", max_queries=8)
            finally:
                expansion._ORIGINAL_ADAPTIVE_PLAN = original
            learned = [row for row in plan if row.get("family") == "learned-host"]
            self.assertEqual(4, len(plan))
            self.assertEqual(1, len(learned))
            self.assertIn("site:under-budget.example.jp", learned[0]["query"])


if __name__ == "__main__":
    unittest.main()
