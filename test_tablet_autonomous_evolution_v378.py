import unittest
from copy import deepcopy
from unittest import mock

import tablet_autonomous_evolution_v378 as v378


def healthy_preview():
    return {
        "controller_version": "v377",
        "v377_status": "PLAN_ONLY",
        "safety": {
            "source_code_auto_generation": False,
            "source_code_auto_rewrite": False,
            "git_write": False,
            "verification_bypass": False,
            "price_or_grade_invention": False,
            "market_direction_inferred": False,
            "single_mutating_cycle_lock_required": True,
            "concurrent_mutating_cycle_fail_closed": True,
        },
        "evidence_barrier": {"ok": True, "status": "EVIDENCE_COMMIT_OK"},
        "skill_state": {"corruption_hold": False},
        "neural_reliability": {"confidence": 0.9},
        "plan": {"resources": {"status": "normal"}},
        "selected_skill": {"skill_id": "s1", "recipe": "OBSERVE_ONLY", "risk": 0.05},
        "single_run_lock": {"status": "LOCK_NOT_REQUIRED", "error_code": None},
        "execution": {
            "status": "PLAN_ONLY",
            "executed": False,
            "git_write": False,
            "source_code_modified": False,
            "proposals_executed": False,
        },
        "exchange_capsule": {
            "market_context": {
                "regime": "HEALTHY",
                "low_coverage_regions": [],
                "degraded_source_ratio": 0.05,
                "market_direction_inferred": False,
            }
        },
        "source_feature_proposals": [],
    }


class TabletAutonomousEvolutionV378Tests(unittest.TestCase):
    def test_quality_framework_is_exact_100_plus_1000_and_truthful(self):
        result = v378.governance(healthy_preview(), root=v378.ROOT)
        self.assertEqual(100, result["preparation"]["perspectives"])
        self.assertEqual(25, result["expert_review"]["groups"])
        self.assertEqual(40, result["expert_review"]["lenses"])
        self.assertEqual(1000, result["expert_review"]["cells"])
        self.assertFalse(result["external_humans_claimed"])
        self.assertTrue(result["allow_execution"])

    def test_hard_safety_blocker_cannot_be_outvoted(self):
        base = healthy_preview()
        base["safety"]["source_code_auto_generation"] = True
        result = v378.governance(base, root=v378.ROOT)
        self.assertFalse(result["allow_execution"])
        self.assertIn("SAFETY_SOURCE_CODE_AUTO_GENERATION", result["hard_blockers"])
        self.assertEqual("OBSERVE_MORE", result["directive"])

    def test_stale_market_allows_only_bounded_recovery_path(self):
        base = healthy_preview()
        base["selected_skill"]["recipe"] = "RECOVER_FRESHNESS"
        base["exchange_capsule"]["market_context"]["regime"] = "FRESHNESS_HOLD"
        result = v378.governance(base, root=v378.ROOT)
        self.assertEqual("RECOVER_MARKET", result["directive"])
        self.assertNotIn("MARKET_FRESHNESS_RECOVERY_ONLY", result["hard_blockers"])
        self.assertTrue(result["allow_execution"])

        unsafe = deepcopy(base)
        unsafe["selected_skill"]["recipe"] = "UNRELATED_ACTION"
        held = v378.governance(unsafe, root=v378.ROOT)
        self.assertFalse(held["allow_execution"])
        self.assertIn("MARKET_FRESHNESS_RECOVERY_ONLY", held["hard_blockers"])

    def test_quality_hold_prevents_mutating_core_call(self):
        base = healthy_preview()
        base["safety"]["verification_bypass"] = True
        with mock.patch.object(v378.v377, "run_cycle", return_value=base) as core:
            result = v378.run_cycle(
                execute=True,
                apply_capabilities=True,
                train_meta=True,
                apply_skills=True,
                persist_outputs=False,
            )
        self.assertEqual(1, core.call_count)
        self.assertEqual("QUALITY_GOVERNANCE_HOLD", result["v378_status"])
        self.assertFalse(result["execution"]["executed"])

    def test_allowed_cycle_delegates_mutation_to_v377(self):
        preview = healthy_preview()
        executed = deepcopy(preview)
        executed["v377_status"] = "V376_EXECUTED"
        executed["execution"] = {
            "status": "V376_EXECUTED",
            "executed": True,
            "git_write": False,
            "source_code_modified": False,
            "proposals_executed": False,
        }
        with mock.patch.object(v378.v377, "run_cycle", side_effect=[preview, executed]) as core:
            result = v378.run_cycle(
                execute=True,
                apply_capabilities=True,
                train_meta=True,
                apply_skills=True,
                persist_outputs=False,
            )
        self.assertEqual(2, core.call_count)
        self.assertEqual("v378", result["controller_version"])
        self.assertEqual("V376_EXECUTED", result["v378_status"])
        second = core.call_args_list[1].kwargs
        self.assertTrue(second["execute"])
        self.assertTrue(second["apply_capabilities"])
        self.assertTrue(second["train_meta"])
        self.assertTrue(second["apply_skills"])

    def test_self_extension_remains_declarative_and_pr_gated(self):
        result = v378.governance(healthy_preview(), root=v378.ROOT)
        self.assertTrue(result["self_extension"]["declarative_capabilities_may_auto_compose"])
        self.assertTrue(result["self_extension"]["allowlisted_primitives_only"])
        self.assertFalse(result["self_extension"]["source_feature_proposals_executed"])
        self.assertTrue(result["self_extension"]["source_change_requires_protected_pr_ci"])
        self.assertFalse(v378.SAFETY["source_code_auto_generation"])
        self.assertFalse(v378.SAFETY["git_write"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
