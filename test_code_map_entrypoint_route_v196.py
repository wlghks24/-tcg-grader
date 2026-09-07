#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from code_map_fast_route import route
from code_map_intelligence import CodeMapIndex, resolve_feature_query, validation_plan_for_route


class CodeMapEntrypointRouteV196Tests(unittest.TestCase):
    def test_pause_recovery_routes_directly_to_guard(self):
        result = resolve_feature_query("인스타 카드정보 일시정지 원인 찾고 재활성화")
        groups = [row["group"] for row in result["matched_feature_groups"]]
        self.assertEqual("instagram_cardinfo_pause_recovery", groups[0])
        self.assertEqual(
            "instagram_tcg_content/automation_state_guard.py",
            result["entry_files"][0],
        )
        self.assertTrue(result["repository_wide_search_avoided"])
        self.assertFalse(result["repository_wide_search_required"])
        self.assertEqual("direct_entrypoint", result["route_decision"])

    def test_crosscheck_routes_to_runtime_bridge_first(self):
        result = resolve_feature_query("인스타 카드정보 자료 비교 교차확인 오류")
        groups = [row["group"] for row in result["matched_feature_groups"]]
        self.assertEqual("instagram_cardinfo_crosscheck", groups[0])
        self.assertEqual("crosscheck_runtime_bridge.py", result["entry_files"][0])
        self.assertIn(
            "test_crosscheck_runtime_bridge_v26.py",
            result["suggested_tests"],
        )

    def test_source_verification_routes_to_verification_engine(self):
        result = resolve_feature_query("인스타 카드정보 공식 출처 검증")
        self.assertEqual(
            "instagram_tcg_content/source_verification_engine.py",
            result["entry_files"][0],
        )
        self.assertIn(
            "instagram_tcg_content/test_source_verification_engine.py",
            result["suggested_tests"],
        )

    def test_low_severity_avoids_unconditional_full_ci(self):
        result = route("업체별 인증번호 OCR 인식률 개선", severity="low")
        plan = result["validation_plan"]
        self.assertEqual("targeted", plan["initial_scope"])
        self.assertTrue(plan["avoids_unconditional_full_ci"])
        self.assertFalse(plan["full_chain_immediate"])
        self.assertNotIn("Exhaustive", plan["initial_checks"])

    def test_fast_route_emits_complete_exploration_plan(self):
        result = route("인스타 카드정보 일시정지 재활성화", severity="low")
        plan = result["exploration_plan"]
        self.assertEqual(
            ["instagram_tcg_content/automation_state_guard.py"],
            plan["1_entrypoint"],
        )
        self.assertFalse(plan["2_bounded_impact"]["requested"])
        self.assertIn(
            "instagram_tcg_content/test_automation_pause_recovery_v30.py",
            plan["3_recommended_tests"],
        )
        self.assertEqual("targeted", plan["4_validation_scope"])
        self.assertFalse(plan["fallback_repo_search"])
        self.assertEqual("fallback_only", result["repository_search_policy"])
        self.assertLess(result["route_ms"], 100.0)
        self.assertLess(result["candidate_files_scanned"], 20)

    def test_medium_severity_adds_repository_verify_only(self):
        raw = resolve_feature_query("행사 프로모 재발매 정보 수집")
        plan = validation_plan_for_route(raw, "medium")
        self.assertEqual("targeted_plus_repository_verify", plan["initial_scope"])
        self.assertIn("Repository Verify", plan["initial_checks"])
        self.assertNotIn("Exhaustive", plan["initial_checks"])

    def test_high_severity_escalates_immediately_to_full_chain(self):
        result = route("코드지도 영향분석 오류", severity="high")
        plan = result["validation_plan"]
        self.assertEqual("full_chain", plan["initial_scope"])
        self.assertTrue(plan["full_chain_immediate"])
        self.assertEqual(
            ["Repository Verify", "Deep Audit", "Exhaustive", "Build/Deploy"],
            plan["initial_checks"],
        )

    def test_feature_impact_uses_entrypoint_as_seed(self):
        with tempfile.TemporaryDirectory() as td:
            index = CodeMapIndex(Path(td))
            result = index.feature_impact(
                "인스타 카드정보 일시정지 재활성화",
                depth=1,
                max_seed_files=1,
            )
        self.assertEqual(
            ["instagram_tcg_content/automation_state_guard.py"],
            result["seed_files"],
        )
        self.assertEqual("entrypoint_then_bounded_impact", result["diagnostic_strategy"])

    def test_unknown_feature_still_requests_fallback_search(self):
        result = resolve_feature_query("totally_unknown_feature_xyz_196")
        self.assertTrue(result["repository_wide_search_required"])
        self.assertFalse(result["repository_wide_search_avoided"])
        self.assertEqual("fallback_search_required", result["route_decision"])
        self.assertEqual([], result["entry_files"])


if __name__ == "__main__":
    unittest.main()
