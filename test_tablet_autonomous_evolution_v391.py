import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import tablet_autonomous_evolution_v391 as autonomy


NOW = datetime(2026, 10, 2, 11, 30, tzinfo=timezone.utc)


def fixture(
    *,
    upstream_allow=True,
    selected="REFRESH_MARKET_DATA",
    selected_reward=0.34,
    selected_lcb=0.12,
    freshness=0.18,
    coverage=0.82,
    source_health=0.88,
    resource_headroom=0.78,
    drift=0.12,
    uncertainty=0.14,
    existing_capability=True,
):
    candidates = [
        {
            "action_id": "REFRESH_MARKET_DATA",
            "goal_utility": 0.88,
            "goal_affinity": 1.0,
            "portfolio_score": 0.84,
            "confidence": 0.86,
            "status": "recovery",
            "recovery_action": True,
            "verified_samples": 18,
        },
        {
            "action_id": "EXPAND_MARKET_COVERAGE",
            "goal_utility": 0.62,
            "goal_affinity": 0.20,
            "portfolio_score": 0.68,
            "confidence": 0.72,
            "status": "challenger",
            "recovery_action": False,
            "verified_samples": 12,
        },
        {
            "action_id": "RECHECK_DEGRADED_SOURCES",
            "goal_utility": 0.58,
            "goal_affinity": 0.30,
            "portfolio_score": 0.64,
            "confidence": 0.70,
            "status": "challenger",
            "recovery_action": True,
            "verified_samples": 10,
        },
    ]
    reward_rows = [
        {
            "action_id": "REFRESH_MARKET_DATA",
            "long_reward": 0.34,
            "reward_lcb": 0.12,
            "verified_samples": 18,
            "status": "recovery",
        },
        {
            "action_id": "EXPAND_MARKET_COVERAGE",
            "long_reward": 0.20,
            "reward_lcb": 0.06,
            "verified_samples": 12,
            "status": "challenger",
        },
        {
            "action_id": "RECHECK_DEGRADED_SOURCES",
            "long_reward": 0.16,
            "reward_lcb": 0.04,
            "verified_samples": 10,
            "status": "recovery",
        },
    ]
    for row in reward_rows:
        if row["action_id"] == selected:
            row["long_reward"] = selected_reward
            row["reward_lcb"] = selected_lcb

    return {
        "controller_version": "v390",
        "v390_status": "PLAN_ONLY" if upstream_allow else "V390_UPSTREAM_HOLD",
        "v390_autonomous_gate": {
            "allow_execution": upstream_allow,
            "status": "V390_VERIFIED_ALLOW" if upstream_allow else "V390_UPSTREAM_HOLD",
        },
        "v390_goal_plan": {
            "primary_goal": {
                "goal_id": "RECOVER_MARKET_FRESHNESS",
                "urgency": round(1.0 - freshness, 6),
            },
            "upstream_selected_action": selected,
            "recommended_action": "REFRESH_MARKET_DATA",
            "critic_sample_count": 8,
            "candidates": candidates,
        },
        "v390_meta_critic": {
            "sample_count": 8,
            "fresh_training_rows": 1,
            "trained_this_cycle": True,
        },
        "v390_goal_capability": {
            "candidate": {"primitive": "REQUEST_FRESHNESS_REFRESH"} if existing_capability else None,
            "write": {"status": "GOAL_CAPABILITY_NOT_REQUESTED", "written": False},
        },
        "v390_state_write": {
            "status": "V390_STATE_WRITE_NOT_REQUESTED",
            "written": False,
        },
        "v390_source_feature_plan": [
            {
                "v388_proposal_id": "SOURCE_GAP:KR:Pokemon",
                "v388_priority_score": 0.82,
                "v388_recurrence": 4,
                "auto_execute": False,
                "auto_generate_source": False,
                "git_write": False,
            }
        ],
        "v388_policy_portfolio": {
            "upstream_selected_action": selected,
            "candidates": reward_rows,
        },
        "v388_resource_budget": {
            "resource_headroom": resource_headroom,
            "drift_score": drift,
            "selected_uncertainty": uncertainty,
        },
        "v382_kpis": {
            "dimensions": {
                "market_freshness": freshness,
                "market_coverage": coverage,
                "source_health": source_health,
                "neural_consensus": 0.84,
                "resource_headroom": resource_headroom,
            }
        },
        "market_adaptation_v381": {
            "degraded_source_ratio": max(0.0, 1.0 - source_health),
            "low_coverage_regions": ["KR"],
        },
        "execution": {
            "status": "PLAN_ONLY",
            "executed": False,
            "git_write": False,
            "source_code_modified": False,
        },
        "safety": {},
    }


class TabletAutonomousEvolutionV391Tests(unittest.TestCase):
    def test_safety_contract_preserves_all_hard_boundaries(self):
        self.assertTrue(autonomy.SAFETY["self_diagnosis_enabled"])
        self.assertTrue(autonomy.SAFETY["counterfactual_decision_stress_test_enabled"])
        self.assertTrue(autonomy.SAFETY["verified_regression_guard_enabled"])
        self.assertTrue(autonomy.SAFETY["feature_lifecycle_planner_enabled"])
        self.assertTrue(autonomy.SAFETY["v390_gate_cannot_be_bypassed"])
        self.assertTrue(autonomy.SAFETY["v388_gate_cannot_be_bypassed"])
        self.assertFalse(autonomy.SAFETY["peer_model_weights_imported"])
        self.assertFalse(autonomy.SAFETY["peer_raw_state_imported"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_rewrite"])
        self.assertFalse(autonomy.SAFETY["arbitrary_command_execution"])
        self.assertFalse(autonomy.SAFETY["git_write"])
        self.assertFalse(autonomy.SAFETY["market_direction_inferred"])

    def test_self_diagnosis_uses_operational_evidence_and_fault_streaks(self):
        preview = fixture(freshness=0.10, coverage=0.50, source_health=0.60)
        state = autonomy._default_state()
        state["fault_streaks"] = {"FRESHNESS_DEFICIT": 3}
        diagnosis = autonomy.self_diagnose(preview, state)
        ids = [row["fault_id"] for row in diagnosis["faults"]]
        self.assertIn("FRESHNESS_DEFICIT", ids)
        self.assertIn("COVERAGE_DEFICIT", ids)
        self.assertIn("SOURCE_DEGRADATION", ids)
        fresh = next(row for row in diagnosis["faults"] if row["fault_id"] == "FRESHNESS_DEFICIT")
        self.assertEqual(3, fresh["prior_streak"])
        self.assertGreater(fresh["effective_severity"], fresh["severity"])
        self.assertFalse(diagnosis["market_direction_inferred"])

    def test_counterfactual_panel_is_deterministic_and_stable_for_clear_recovery(self):
        preview = fixture()
        diagnosis = autonomy.self_diagnose(preview, autonomy._default_state())
        one = autonomy.counterfactual_stress_test(preview, diagnosis)
        two = autonomy.counterfactual_stress_test(preview, diagnosis)
        self.assertEqual(one, two)
        self.assertTrue(one["stable"])
        self.assertGreaterEqual(one["recommended_consensus"], 3)
        self.assertEqual("REFRESH_MARKET_DATA", one["recommended_action"])
        self.assertTrue(one["deterministic"])

    def test_verified_regression_blocks_non_recovery_but_not_recovery(self):
        non_recovery = fixture(
            selected="EXPAND_MARKET_COVERAGE",
            selected_reward=-0.40,
            selected_lcb=-0.35,
        )
        guard = autonomy.verified_regression_guard(non_recovery)
        self.assertTrue(guard["block"])
        self.assertEqual("VERIFIED_REGRESSION_BLOCK", guard["status"])

        recovery = fixture(
            selected="REFRESH_MARKET_DATA",
            selected_reward=-0.40,
            selected_lcb=-0.35,
        )
        guard2 = autonomy.verified_regression_guard(recovery)
        self.assertFalse(guard2["block"])
        self.assertEqual("RECOVERY_REGRESSION_OBSERVE_ONLY", guard2["status"])

    def test_feature_lifecycle_can_require_rework_and_never_executes_source(self):
        preview = fixture()
        state = autonomy._default_state()
        state["cycle"] = 7
        state["feature_lifecycle"] = {
            "SOURCE_GAP:KR:Pokemon": {
                "seen_cycles": 4,
                "last_priority": 0.60,
                "last_stage": "protected_pr_candidate",
                "last_seen_cycle": 7,
            }
        }
        rows, memory = autonomy.feature_lifecycle_plan(preview, state, next_cycle=8)
        self.assertEqual(1, len(rows))
        self.assertEqual("rework_required", rows[0]["v391_stage"])
        self.assertFalse(rows[0]["auto_execute"])
        self.assertFalse(rows[0]["auto_generate_source"])
        self.assertFalse(rows[0]["git_write"])
        self.assertIn("protected_pr_ci", rows[0]["promotion_requires"])
        self.assertEqual("rework_required", memory["SOURCE_GAP:KR:Pokemon"]["last_stage"])

    def test_upstream_hold_is_never_bypassed(self):
        preview = fixture(upstream_allow=False)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / ".v391-state.json"
            with mock.patch.object(autonomy.v390, "run_cycle", return_value=preview) as run:
                result = autonomy.run_cycle(
                    domain="tablet_gpt",
                    execute=True,
                    apply_capabilities=True,
                    train_meta=True,
                    apply_skills=True,
                    root=root,
                    now=NOW,
                    state_path=state_path,
                    persist_outputs=False,
                )
            self.assertEqual(1, run.call_count)
            self.assertEqual("V391_UPSTREAM_HOLD", result["v391_status"])
            self.assertFalse(result["v391_autonomous_gate"]["allow_execution"])
            self.assertFalse(result["execution"]["executed"])
            self.assertTrue(state_path.is_file())

    def test_mutating_cycle_persists_v391_state_and_calls_v390_only_after_gate(self):
        preview = fixture()
        mutated = fixture()
        mutated["v390_status"] = "V390_VERIFIED_ALLOW"
        mutated["execution"] = {
            "status": "EXECUTED",
            "executed": True,
            "git_write": False,
            "source_code_modified": False,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / ".v391-state.json"
            with mock.patch.object(autonomy.v390, "run_cycle", side_effect=[preview, mutated]) as run:
                result = autonomy.run_cycle(
                    domain="tablet_gpt",
                    execute=True,
                    apply_capabilities=True,
                    train_meta=True,
                    apply_skills=True,
                    root=root,
                    now=NOW,
                    state_path=state_path,
                    persist_outputs=False,
                )
            self.assertEqual(2, run.call_count)
            self.assertEqual("V391_VERIFIED_ALLOW", result["v391_status"])
            self.assertTrue(result["v391_autonomous_gate"]["allow_execution"])
            self.assertTrue(state_path.is_file())
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual("v391", saved["controller_version"])
            self.assertEqual(1, saved["cycle"])
            self.assertTrue(saved["feature_lifecycle"])
            self.assertFalse(result["safety"]["source_code_auto_generation"])
            self.assertFalse(result["safety"]["git_write"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
