#!/usr/bin/env python3
from __future__ import annotations

import unittest

from code_map_fast_route import route


GAP = "instagram_tcg_content/collection_freshness_gap_guard.py"
RUNNER = "instagram_tcg_content/collection_recovery_runner.py"
HEALTH = "instagram_tcg_content/collection_health.py"


class InstagramCollectionCodeMapV222Tests(unittest.TestCase):
    def test_freshness_gap_promotes_guard_without_repository_search(self):
        result = route(
            "인스타 카드정보 공용 수집은 최신인데 스냅샷만 stale 수집 단절"
        )
        self.assertEqual("instagram_cardinfo_collection_health", result["entry_group"])
        self.assertEqual(GAP, result["entry_file"])
        self.assertEqual([GAP], result["entry_files"])
        self.assertIn(RUNNER, result["alternate_entry_files"])
        self.assertIn(HEALTH, result["alternate_entry_files"])
        self.assertIn(
            "instagram_tcg_content/test_collection_freshness_gap_guard.py",
            result["suggested_tests"],
        )
        self.assertFalse(result["repository_wide_search_required"])
        self.assertTrue(result["repository_wide_search_avoided"])
        self.assertEqual("direct_entrypoint", result["route_decision"])
        self.assertEqual(
            "fast_route_instagram_collection_gap_rule",
            result["entrypoint_reason"],
        )
        self.assertFalse(result["verification_authority"])

    def test_recovery_execution_promotes_runner_and_bounded_tests(self):
        result = route("인스타 카드정보 수집 복구 실행 capture packet")
        self.assertEqual("instagram_cardinfo_collection_health", result["entry_group"])
        self.assertEqual(RUNNER, result["entry_file"])
        self.assertEqual([RUNNER], result["entry_files"])
        self.assertIn(GAP, result["alternate_entry_files"])
        self.assertIn(HEALTH, result["alternate_entry_files"])
        self.assertIn(
            "instagram_tcg_content/test_collection_recovery_runner.py",
            result["suggested_tests"],
        )
        self.assertIn(
            "instagram_tcg_content/test_collection_recovery_runner.py::CollectionRecoveryRunnerTests::test_incremental_recovery_merges_only_fresh_verified_instagram_facts",
            result["suggested_test_nodes"],
        )
        self.assertEqual(
            "fast_route_instagram_collection_recovery_rule",
            result["entrypoint_reason"],
        )
        self.assertFalse(result["repository_wide_search_required"])
        self.assertFalse(result["verification_authority"])

    def test_bounded_impact_does_not_replace_promoted_gap_seed(self):
        result = route(
            "인스타 카드정보 공용 수집은 최신인데 snapshot stale persistence lag",
            include_impact=True,
        )
        self.assertEqual(GAP, result["entry_file"])
        self.assertEqual([GAP], result["entry_files"])
        self.assertEqual([GAP], result["seed_files"])
        self.assertTrue(result["graph_load_attempted"])
        self.assertEqual(GAP, result["exploration_plan"]["1_entrypoint"])
        self.assertEqual([GAP], result["exploration_plan"]["2_bounded_impact"]["seed_files"])
        self.assertFalse(result["repository_wide_search_required"])
        # The committed Graphify snapshot may predate the newly added file; that is
        # acceptable. The operational entrypoint must stay promoted even if the
        # graph reports origin_not_mapped/stale.
        self.assertIn(
            result["seed_results"][0]["status"],
            {"ok", "origin_not_mapped", "stale_for_origin", "missing_or_invalid"},
        )

    def test_unscoped_main_collection_query_is_not_hijacked(self):
        result = route("공용 수집은 최신인데 snapshot stale")
        self.assertNotEqual(GAP, result.get("entry_file"))
        self.assertFalse(result.get("code_map_override", False))


if __name__ == "__main__":
    unittest.main()
