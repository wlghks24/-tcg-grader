import fcntl
import json
import shutil
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock

import tablet_autonomous_evolution_v379 as v379


def healthy_preview():
    return {
        "controller_version": "v378",
        "v378_status": "PLAN_ONLY",
        "quality_governance": {
            "ok": True,
            "status": "QUALITY_100_1000_READY",
            "preparation_senior_perspectives": 100,
            "review_cells": 1000,
        },
        "neural_council": {
            "advisory_only": True,
            "confidence": 0.88,
            "agreement": 0.82,
            "readiness": "HIGH",
        },
        "adaptive_mode": {
            "mode": "STEADY_VERIFIED_EVOLUTION",
            "market_regime": "HEALTHY",
            "market_direction_inferred": False,
        },
        "safety": {
            "quality_policy_fail_closed_before_mutation": True,
            "quality_blocker_cannot_be_outvoted": True,
            "single_mutating_cycle_lock_required": True,
            "concurrent_mutating_cycle_fail_closed": True,
            "source_code_auto_generation": False,
            "source_code_auto_rewrite": False,
            "git_write": False,
            "verification_bypass": False,
            "price_or_grade_invention": False,
            "market_direction_inferred": False,
        },
        "evidence_barrier": {"ok": True, "status": "EVIDENCE_COMMIT_OK"},
        "skill_state": {"corruption_hold": False},
        "plan": {
            "resources": {"status": "normal"},
            "market_profile": {
                "freshness": {"status": "fresh"},
                "low_coverage_regions": [],
                "degraded_source_ratio": 0.05,
            },
        },
        "selected_skill": {
            "skill_id": "healthy-observe",
            "recipe": "OBSERVE_ONLY",
            "risk": 0.05,
        },
        "v378_single_run_lock": {
            "status": "V378_LOCK_NOT_REQUIRED",
            "error_code": None,
        },
        "single_run_lock": {
            "status": "LOCK_NOT_REQUIRED",
            "error_code": None,
        },
        "execution": {
            "status": "PLAN_ONLY",
            "executed": False,
            "git_write": False,
            "source_code_modified": False,
            "proposals_executed": False,
        },
        "source_feature_proposals": [],
    }


def temp_root():
    td = tempfile.TemporaryDirectory()
    root = Path(td.name)
    shutil.copy2(v379.ROOT / "quality_review_policy_v2.json", root / "quality_review_policy_v2.json")
    return td, root


class TabletAutonomousEvolutionV379Tests(unittest.TestCase):
    def test_decision_matrix_computes_actual_100_plus_1000(self):
        td, root = temp_root()
        try:
            base = healthy_preview()
            matrix = v379.decision_matrix(base, root=root)
            decision = v379.decide(base, matrix)
            self.assertEqual(100, matrix["preparation"]["perspectives"])
            self.assertEqual(25, matrix["expert_review"]["groups"])
            self.assertEqual(40, matrix["expert_review"]["lenses"])
            self.assertEqual(1000, matrix["expert_review"]["cells"])
            self.assertEqual(64, len(matrix["preparation"]["digest_sha256"]))
            self.assertEqual(64, len(matrix["expert_review"]["digest_sha256"]))
            self.assertFalse(matrix["external_human_review_claimed"])
            self.assertTrue(decision["allow_execution"])
        finally:
            td.cleanup()

    def test_hard_safety_blocker_cannot_be_outvoted(self):
        td, root = temp_root()
        try:
            base = healthy_preview()
            base["safety"]["source_code_auto_generation"] = True
            matrix = v379.decision_matrix(base, root=root)
            decision = v379.decide(base, matrix)
            self.assertFalse(decision["allow_execution"])
            self.assertIn("SAFETY_SOURCE_CODE_AUTO_GENERATION", decision["hard_blockers"])
            self.assertFalse(decision["neural_can_override_hard_blocker"])
        finally:
            td.cleanup()

    def test_low_neural_consensus_holds_non_recovery_action(self):
        td, root = temp_root()
        try:
            base = healthy_preview()
            base["neural_council"]["confidence"] = 0.10
            base["neural_council"]["agreement"] = 0.15
            base["neural_council"]["readiness"] = "LOW"
            base["selected_skill"] = {
                "skill_id": "normal-action",
                "recipe": "NON_RECOVERY_TEST_ACTION",
                "risk": 0.05,
            }
            matrix = v379.decision_matrix(base, root=root)
            decision = v379.decide(base, matrix)
            self.assertFalse(decision["allow_execution"])
            self.assertTrue(decision["neural_low_confidence_hold"])
            self.assertEqual("OBSERVE_MORE", decision["directive"])
        finally:
            td.cleanup()

    def test_freshness_hold_allows_only_bounded_recovery_recipe(self):
        td, root = temp_root()
        try:
            base = healthy_preview()
            base["adaptive_mode"] = {
                "mode": "RECOVER_FRESHNESS",
                "market_regime": "FRESHNESS_HOLD",
                "market_direction_inferred": False,
            }
            base["plan"]["market_profile"]["freshness"] = {"status": "hold"}
            base["selected_skill"] = {
                "skill_id": "freshness-recovery",
                "recipe": "RECOVER_FRESHNESS",
                "risk": 0.05,
            }
            matrix = v379.decision_matrix(base, root=root)
            decision = v379.decide(base, matrix)
            self.assertNotIn("MARKET_FRESHNESS_RECOVERY_ONLY", decision["hard_blockers"])
            self.assertEqual("RECOVERY_BOUNDED", decision["directive"])
            self.assertTrue(decision["allow_execution"])

            unsafe = deepcopy(base)
            unsafe["selected_skill"] = {
                "skill_id": "unrelated",
                "recipe": "UNRELATED_ACTION",
                "risk": 0.05,
            }
            unsafe_matrix = v379.decision_matrix(unsafe, root=root)
            unsafe_decision = v379.decide(unsafe, unsafe_matrix)
            self.assertFalse(unsafe_decision["allow_execution"])
            self.assertIn("MARKET_FRESHNESS_RECOVERY_ONLY", unsafe_decision["hard_blockers"])
        finally:
            td.cleanup()

    def test_decision_hold_prevents_mutating_v378_call(self):
        td, root = temp_root()
        try:
            preview = healthy_preview()
            preview["safety"]["verification_bypass"] = True
            with mock.patch.object(v379.v378, "run_cycle", return_value=preview) as core:
                result = v379.run_cycle(
                    execute=True,
                    apply_capabilities=True,
                    train_meta=True,
                    apply_skills=True,
                    root=root,
                    lock_path=root / v379.LOCK_PATH.name,
                    persist_outputs=False,
                )
            self.assertEqual(1, core.call_count)
            self.assertEqual("V379_QUALITY_DECISION_HOLD", result["v379_status"])
            self.assertFalse(result["execution"]["executed"])
        finally:
            td.cleanup()

    def test_allowed_cycle_delegates_mutation_to_v378(self):
        td, root = temp_root()
        try:
            preview = healthy_preview()
            executed = deepcopy(preview)
            executed["v378_status"] = "V376_EXECUTED"
            executed["execution"] = {
                "status": "V376_EXECUTED",
                "executed": True,
                "git_write": False,
                "source_code_modified": False,
                "proposals_executed": False,
            }
            with mock.patch.object(v379.v378, "run_cycle", side_effect=[preview, executed]) as core:
                result = v379.run_cycle(
                    execute=True,
                    apply_capabilities=True,
                    train_meta=True,
                    apply_skills=True,
                    root=root,
                    lock_path=root / v379.LOCK_PATH.name,
                    persist_outputs=False,
                )
            self.assertEqual(2, core.call_count)
            self.assertEqual("v379", result["controller_version"])
            self.assertEqual("V376_EXECUTED", result["v379_status"])
            second = core.call_args_list[1].kwargs
            self.assertTrue(second["execute"])
            self.assertTrue(second["apply_capabilities"])
            self.assertTrue(second["train_meta"])
            self.assertTrue(second["apply_skills"])
            self.assertEqual(100, result["decision_review_matrix"]["preparation"]["perspectives"])
            self.assertEqual(1000, result["decision_review_matrix"]["expert_review"]["cells"])
        finally:
            td.cleanup()

    def test_outer_lock_contention_is_side_effect_free(self):
        td, root = temp_root()
        try:
            lock = root / v379.LOCK_PATH.name
            fd = lock.open("a+")
            fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                with mock.patch.object(v379.v378, "run_cycle") as core:
                    result = v379.run_cycle(
                        execute=True,
                        apply_capabilities=True,
                        train_meta=True,
                        apply_skills=True,
                        root=root,
                        lock_path=lock,
                        persist_outputs=False,
                    )
                core.assert_not_called()
                self.assertEqual("V379_CONCURRENT_AUTONOMY_HOLD", result["v379_status"])
                self.assertFalse(result["execution"]["executed"])
            finally:
                fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
                fd.close()
        finally:
            td.cleanup()

    def test_source_level_new_functions_remain_proposal_only(self):
        self.assertTrue(v379.SAFETY["runtime_self_extension_allowlisted_declarative_only"])
        self.assertTrue(v379.SAFETY["source_level_new_function_pr_ci_required"])
        self.assertFalse(v379.SAFETY["source_code_auto_generation"])
        self.assertFalse(v379.SAFETY["source_code_auto_rewrite"])
        self.assertFalse(v379.SAFETY["git_write"])
        self.assertFalse(v379.SAFETY["verification_bypass"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
