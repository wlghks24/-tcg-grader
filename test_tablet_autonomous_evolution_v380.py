import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from copy import deepcopy
from pathlib import Path
from unittest import mock

import tablet_autonomous_evolution_v380 as v380


def healthy_preview():
    now = datetime.now(timezone.utc)
    capability = {
        "id": "REQUEST_FRESHNESS_REFRESH:TEST",
        "primitive": "REQUEST_FRESHNESS_REFRESH",
        "parameters": {"max_runs": 1},
        "evidence": {"reason": "test_verified_capability"},
        "created_at": (now - timedelta(minutes=1)).isoformat(timespec="seconds"),
        "expires_at": (now + timedelta(hours=1)).isoformat(timespec="seconds"),
        "auto_generated": True,
        "auto_active": True,
        "source_code_change": False,
        "arbitrary_command": False,
        "scope": "operational_policy",
    }
    return {
        "controller_version": "v379",
        "v379_status": "PLAN_ONLY",
        "safety": {
            "source_code_auto_generation": False,
            "source_code_auto_rewrite": False,
            "git_write": False,
            "verification_bypass": False,
            "price_or_grade_invention": False,
            "market_direction_inferred": False,
            "peer_fix_auto_apply": False,
            "peer_content_direct_model_training": False,
            "quality_policy_fail_closed_before_mutation": True,
            "quality_blocker_cannot_be_outvoted": True,
            "single_mutating_cycle_lock_required": True,
            "concurrent_mutating_cycle_fail_closed": True,
            "information_exchange_conflict_blocks_mutation": True,
            "information_exchange_invalid_blocks_mutation": True,
            "information_exchange_input_stability_required": True,
        },
        "quality_governance": {"ok": True, "status": "QUALITY_100_1000_READY"},
        "evidence_barrier": {"ok": True, "status": "EVIDENCE_COMMIT_OK"},
        "skill_state": {"corruption_hold": False},
        "plan": {
            "resources": {"status": "normal"},
            "market_profile": {"low_coverage_regions": [], "degraded_source_ratio": 0.05},
            "active_capabilities": [capability],
        },
        "selected_skill": {
            "skill_id": "verified-skill",
            "recipe": "OBSERVE_ONLY",
            "risk": 0.05,
        },
        "adaptive_mode": {"mode": "STEADY_VERIFIED_EVOLUTION", "market_regime": "HEALTHY"},
        "v378_single_run_lock": {"status": "V378_LOCK_NOT_REQUIRED", "error_code": None},
        "single_run_lock": {"status": "LOCK_NOT_REQUIRED", "error_code": None},
        "execution": {
            "status": "PLAN_ONLY",
            "executed": False,
            "git_write": False,
            "source_code_modified": False,
            "proposals_executed": False,
        },
        "information_exchange_manager": {
            "status": "EXCHANGE_CORROBORATED",
            "mutation_allowed": True,
            "peer_influence_allowed": True,
            "input_digest": "a" * 64,
        },
        "improvement_queue": [
            {"id": "untrusted-auto-apply-row", "kind": "declarative", "priority": 999, "auto_apply": True, "pr_required": False},
            {"id": "new-market-parser", "kind": "new_function", "priority": 100, "auto_apply": True, "pr_required": True},
        ],
        "information_exchange_neural_council": {
            "advisory_only": True,
            "confidence": 0.90,
            "agreement": 0.90,
            "readiness": "HIGH",
        },
    }


class TabletAutonomousEvolutionV380Tests(unittest.TestCase):
    def test_decision_matrix_computes_exact_100_plus_1000(self):
        matrix = v380.decision_matrix(healthy_preview(), root=v380.ROOT)
        self.assertEqual(100, matrix["preparation"]["perspectives"])
        self.assertEqual(25, matrix["expert_review"]["groups"])
        self.assertEqual(40, matrix["expert_review"]["lenses"])
        self.assertEqual(1000, matrix["expert_review"]["cells"])
        self.assertEqual(64, len(matrix["preparation"]["digest_sha256"]))
        self.assertEqual(64, len(matrix["expert_review"]["digest_sha256"]))
        self.assertFalse(matrix["external_human_review_claimed"])
        decision = v380.decide(healthy_preview(), matrix)
        self.assertTrue(decision["allow_execution"])
        self.assertTrue(decision["matrix_ok"])
        self.assertFalse(decision["neural_can_override_hard_blocker"])

    def test_exchange_conflict_is_hard_blocker_even_with_high_neural_score(self):
        base = healthy_preview()
        base["information_exchange_manager"] = {
            "status": "EXCHANGE_CONFLICT_HOLD",
            "mutation_allowed": False,
            "peer_influence_allowed": False,
        }
        base["information_exchange_neural_council"]["confidence"] = 1.0
        base["information_exchange_neural_council"]["agreement"] = 1.0
        matrix = v380.decision_matrix(base, root=v380.ROOT)
        decision = v380.decide(base, matrix)
        self.assertFalse(decision["allow_execution"])
        self.assertIn("EXCHANGE_CONFLICT_HOLD", decision["hard_blockers"])
        self.assertEqual("BLOCKED", decision["directive"])

    def test_safety_blocker_cannot_be_outvoted(self):
        base = healthy_preview()
        base["safety"]["verification_bypass"] = True
        matrix = v380.decision_matrix(base, root=v380.ROOT)
        decision = v380.decide(base, matrix)
        self.assertFalse(decision["allow_execution"])
        self.assertIn("SAFETY_VERIFICATION_BYPASS", decision["hard_blockers"])

    def test_low_neural_confidence_holds_non_recovery_action(self):
        base = healthy_preview()
        base["selected_skill"]["recipe"] = "NORMAL_OPTIMIZATION"
        base["information_exchange_neural_council"]["readiness"] = "LOW"
        matrix = v380.decision_matrix(base, root=v380.ROOT)
        decision = v380.decide(base, matrix)
        self.assertFalse(decision["allow_execution"])
        self.assertTrue(decision["neural_low_confidence_hold"])
        self.assertEqual("OBSERVE_MORE", decision["directive"])

    def test_mutation_is_never_called_when_decision_gate_holds(self):
        preview = healthy_preview()
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.object(v380.v379, "run_cycle", return_value=preview) as core, \
             mock.patch.object(v380, "decision_matrix", return_value={
                 "dimensions": {"proposal_boundary": 1.0},
                 "preparation": {"perspectives": 100, "pass": 100, "review": 0, "pass_ratio": 1.0, "digest_sha256": "a"*64, "lowest": []},
                 "expert_review": {"groups": 25, "lenses": 40, "cells": 1000, "pass": 1000, "review": 0, "pass_ratio": 1.0, "digest_sha256": "b"*64, "lowest": []},
                 "external_human_review_claimed": False,
             }), \
             mock.patch.object(v380, "decide", return_value={
                 "status": "V380_QUALITY_DECISION_HOLD",
                 "allow_execution": False,
                 "directive": "BLOCKED",
                 "hard_blockers": ["TEST_BLOCKER"],
                 "neural_can_override_hard_blocker": False,
             }):
            result = v380.run_cycle(
                execute=True,
                apply_capabilities=True,
                train_meta=True,
                apply_skills=True,
                root=Path(td),
                persist_outputs=False,
            )
        self.assertEqual(1, core.call_count)
        first = core.call_args_list[0].kwargs
        self.assertFalse(first["execute"])
        self.assertFalse(first["apply_capabilities"])
        self.assertFalse(first["train_meta"])
        self.assertFalse(first["apply_skills"])
        self.assertEqual("V380_QUALITY_DECISION_HOLD", result["v380_status"])
        self.assertFalse(result["execution"]["executed"])

    def test_allowed_mutation_previews_then_delegates_to_v379(self):
        preview = healthy_preview()
        executed = deepcopy(preview)
        executed["v379_status"] = "V376_EXECUTED"
        executed["execution"] = {
            "status": "V376_EXECUTED",
            "executed": True,
            "git_write": False,
            "source_code_modified": False,
            "proposals_executed": False,
        }
        matrix = v380.decision_matrix(preview, root=v380.ROOT)
        decision = v380.decide(preview, matrix)
        self.assertTrue(decision["allow_execution"])
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.object(v380.v379, "run_cycle", side_effect=[preview, executed]) as core, \
             mock.patch.object(v380.v379, "information_exchange_manager", return_value=preview["information_exchange_manager"]), \
             mock.patch.object(v380, "decision_matrix", return_value=matrix), \
             mock.patch.object(v380, "decide", return_value=decision):
            result = v380.run_cycle(
                execute=True,
                apply_capabilities=True,
                train_meta=True,
                apply_skills=True,
                root=Path(td),
                persist_outputs=False,
            )
        self.assertEqual(2, core.call_count)
        preview_args = core.call_args_list[0].kwargs
        execute_args = core.call_args_list[1].kwargs
        self.assertFalse(preview_args["execute"])
        self.assertTrue(execute_args["execute"])
        self.assertTrue(execute_args["apply_capabilities"])
        self.assertTrue(execute_args["train_meta"])
        self.assertTrue(execute_args["apply_skills"])
        self.assertEqual("V376_EXECUTED", result["v380_status"])
        self.assertEqual(100, result["decision_review_matrix"]["preparation"]["perspectives"])
        self.assertEqual(1000, result["decision_review_matrix"]["expert_review"]["cells"])

    def test_exchange_digest_drift_holds_before_mutation(self):
        preview = healthy_preview()
        changed = deepcopy(preview["information_exchange_manager"])
        changed["input_digest"] = "b" * 64
        matrix = v380.decision_matrix(preview, root=v380.ROOT)
        decision = v380.decide(preview, matrix)
        self.assertTrue(decision["allow_execution"])
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.object(v380.v379, "run_cycle", return_value=preview) as core, \
             mock.patch.object(v380.v379, "information_exchange_manager", return_value=changed), \
             mock.patch.object(v380, "decision_matrix", return_value=matrix), \
             mock.patch.object(v380, "decide", return_value=decision):
            result = v380.run_cycle(
                execute=True,
                apply_capabilities=True,
                train_meta=True,
                apply_skills=True,
                root=Path(td),
                persist_outputs=False,
            )
        self.assertEqual(1, core.call_count)
        self.assertEqual("V380_EXCHANGE_DRIFT_HOLD", result["v380_status"])
        self.assertFalse(result["execution"]["executed"])
        self.assertIn("V380_EXCHANGE_DRIFT_HOLD", result["autonomous_decision"]["hard_blockers"])

    def test_capability_selection_applies_only_allowlisted_runtime_actions(self):
        base = healthy_preview()
        matrix = v380.decision_matrix(base, root=v380.ROOT)
        decision = v380.decide(base, matrix)
        self.assertTrue(decision["allow_execution"])
        plan = v380.autonomous_capability_plan(base, decision)
        self.assertEqual("ALLOWLISTED_RUNTIME_SELECTION", plan["status"])
        self.assertEqual("REQUEST_FRESHNESS_REFRESH:TEST", plan["selected_runtime_capability"]["id"])
        self.assertEqual("REQUEST_FRESHNESS_REFRESH", plan["selected_runtime_capability"]["primitive"])
        self.assertTrue(plan["selected_runtime_capability"]["auto_apply"])
        self.assertEqual("tablet_autonomous_evolution_v373.CAPABILITY_PRIMITIVES", plan["canonical_registry"])
        self.assertEqual("tablet_autonomous_evolution_v373.validate_capability", plan["canonical_validator"])
        self.assertNotIn("untrusted-auto-apply-row", {row["id"] for row in plan["runtime_candidates"]})
        self.assertTrue(plan["protected_pr_ci_required"])
        self.assertEqual("new-market-parser", plan["source_level_proposals"][0]["id"])
        self.assertFalse(plan["source_level_proposals"][0]["auto_apply"])
        self.assertTrue(plan["source_level_proposals"][0]["pr_required"])
        self.assertFalse(plan["source_level_auto_apply"])
        self.assertFalse(plan["market_direction_inferred"])

        blocked = deepcopy(decision)
        blocked["allow_execution"] = False
        blocked_plan = v380.autonomous_capability_plan(base, blocked)
        self.assertEqual("DECISION_HOLD", blocked_plan["status"])
        self.assertFalse(blocked_plan["runtime_candidates"][0]["auto_apply"])

    def test_invalid_active_capability_is_rejected(self):
        base = healthy_preview()
        base["plan"]["active_capabilities"].append({
            "id": "ARBITRARY_COMMAND:BAD",
            "primitive": "ARBITRARY_COMMAND",
            "parameters": {},
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(timespec="seconds"),
            "auto_generated": True,
            "auto_active": True,
            "source_code_change": False,
            "arbitrary_command": True,
            "scope": "operational_policy",
        })
        matrix = v380.decision_matrix(base, root=v380.ROOT)
        decision = v380.decide(base, matrix)
        plan = v380.autonomous_capability_plan(base, decision)
        self.assertNotIn("ARBITRARY_COMMAND:BAD", {row["id"] for row in plan["runtime_candidates"]})
        self.assertIn("ARBITRARY_COMMAND:BAD", {row["id"] for row in plan["rejected_runtime_capabilities"]})

    def test_source_level_extension_remains_pr_ci_only(self):
        self.assertTrue(v380.SAFETY["runtime_self_extension_allowlisted_declarative_only"])
        self.assertTrue(v380.SAFETY["source_level_new_function_pr_ci_required"])
        self.assertFalse(v380.SAFETY["source_code_auto_generation"])
        self.assertFalse(v380.SAFETY["source_code_auto_rewrite"])
        self.assertFalse(v380.SAFETY["git_write"])
        self.assertFalse(v380.SAFETY["verification_bypass"])
        self.assertFalse(v380.SAFETY["market_direction_inferred"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
