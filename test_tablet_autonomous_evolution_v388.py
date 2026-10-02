import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import tablet_autonomous_evolution_v388 as autonomy


def fixture(*, action="REFRESH_MARKET_DATA", reward=0.35, samples=18, confidence=0.78,
            resource=0.80, drift=0.12, upstream_allow=True):
    return {
        "controller_version": "v387",
        "v387_status": "V387_VERIFIED_ALLOW" if upstream_allow else "V387_UPSTREAM_HOLD",
        "v387_autonomous_gate": {
            "allow_execution": upstream_allow,
            "status": "V387_VERIFIED_ALLOW" if upstream_allow else "V387_UPSTREAM_HOLD",
            "selected_action": action,
        },
        "v387_uncertainty_policy": {
            "selected_action": action,
            "selected_confidence": confidence,
            "selected_uncertainty": 1.0 - confidence,
            "regime_transition": {
                "level": "STABLE" if drift < autonomy.HIGH_DRIFT else "TRANSITION",
                "local_regime": "NORMAL_VOLATILITY",
                "peer_regime": "NORMAL_VOLATILITY",
                "drift_score": drift,
                "market_direction_inferred": False,
            },
            "candidates": [
                {
                    "action_id": action,
                    "confidence": confidence,
                    "uncertainty": 1.0 - confidence,
                    "multi_objective_score": 0.80,
                    "local_verified_samples": samples,
                    "peer_verified_samples": 12,
                },
                {
                    "action_id": "EXPAND_MARKET_COVERAGE",
                    "confidence": 0.70,
                    "uncertainty": 0.30,
                    "multi_objective_score": 0.66,
                    "local_verified_samples": 10,
                    "peer_verified_samples": 8,
                },
            ],
            "market_direction_inferred": False,
        },
        "v385_verified_neural_policy": {
            "regime": "NORMAL_VOLATILITY",
            "candidates": [
                {
                    "action_id": action,
                    "score": 0.82,
                    "verified_samples": samples,
                    "reward_mean": reward,
                },
                {
                    "action_id": "EXPAND_MARKET_COVERAGE",
                    "score": 0.68,
                    "verified_samples": 10,
                    "reward_mean": 0.10,
                },
                {
                    "action_id": "UNVERIFIED_ACTION",
                    "score": 0.99,
                    "verified_samples": 0,
                    "reward_mean": 1.0,
                },
            ],
        },
        "v387_feature_lifecycle": [
            {
                "v387_proposal_id": "SOURCE_GAP:KR:Pokemon",
                "v387_status": "canary",
                "v387_confidence": confidence,
                "auto_execute": False,
                "auto_generate_source": False,
                "git_write": False,
                "protected_pr_ci_required": True,
            }
        ],
        "v382_kpis": {
            "score": 0.84,
            "dimensions": {
                "market_freshness": 0.86,
                "market_coverage": 0.76,
                "source_health": 0.81,
                "neural_consensus": 0.82,
                "resource_headroom": resource,
            },
        },
        "v382_drift": {
            "score": drift,
            "level": "LOW" if drift < 0.25 else "HIGH",
            "market_regime": "NORMAL_VOLATILITY",
        },
        "execution": {
            "status": "PLAN_ONLY",
            "executed": False,
            "git_write": False,
            "source_code_modified": False,
        },
        "safety": {},
    }


class TabletAutonomousEvolutionV388Tests(unittest.TestCase):
    def test_safety_contract_preserves_hard_boundaries(self):
        self.assertTrue(autonomy.SAFETY["regime_conditioned_policy_portfolio"])
        self.assertTrue(autonomy.SAFETY["verified_reward_memory_only"])
        self.assertTrue(autonomy.SAFETY["resource_budget_autonomy"])
        self.assertTrue(autonomy.SAFETY["feature_backlog_non_executable"])
        self.assertTrue(autonomy.SAFETY["v387_gate_cannot_be_bypassed"])
        self.assertFalse(autonomy.SAFETY["peer_model_weights_imported"])
        self.assertFalse(autonomy.SAFETY["peer_raw_state_imported"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_rewrite"])
        self.assertFalse(autonomy.SAFETY["arbitrary_command_execution"])
        self.assertFalse(autonomy.SAFETY["git_write"])
        self.assertFalse(autonomy.SAFETY["market_direction_inferred"])

    def test_portfolio_learns_only_verified_reward_rows(self):
        base = fixture()
        state = autonomy._default_state()
        projected = autonomy.update_portfolio(state, base)
        rows = projected["portfolios"]["NORMAL_VOLATILITY"]
        self.assertIn("REFRESH_MARKET_DATA", rows)
        self.assertIn("EXPAND_MARKET_COVERAGE", rows)
        self.assertNotIn("UNVERIFIED_ACTION", rows)
        self.assertEqual(1, rows["REFRESH_MARKET_DATA"]["observations"])
        self.assertEqual(18, rows["REFRESH_MARKET_DATA"]["verified_samples"])
        self.assertEqual("recovery", rows["REFRESH_MARKET_DATA"]["status"])

    def test_non_recovery_policy_is_quarantined_after_repeated_verified_regression(self):
        base = fixture(action="OPTIMIZE_MARKET_COVERAGE", reward=-0.70, confidence=0.75)
        state = autonomy._default_state()
        for _ in range(autonomy.QUARANTINE_BAD_STREAK):
            state = autonomy.update_portfolio(state, base)
        row = state["portfolios"]["NORMAL_VOLATILITY"]["OPTIMIZE_MARKET_COVERAGE"]
        self.assertEqual("quarantined", row["status"])
        self.assertGreaterEqual(row["bad_streak"], autonomy.QUARANTINE_BAD_STREAK)
        policy = autonomy.portfolio_policy(base, state)
        gate = autonomy.autonomous_gate(base, policy, autonomy.resource_budget(base))
        self.assertFalse(gate["allow_execution"])
        self.assertEqual("V388_POLICY_QUARANTINE_HOLD", gate["status"])

    def test_recovery_actions_are_not_quarantined(self):
        base = fixture(action="REVALIDATE_MARKET_DATA", reward=-0.90, confidence=0.65)
        base["v385_verified_neural_policy"]["candidates"][0]["action_id"] = "REVALIDATE_MARKET_DATA"
        state = autonomy._default_state()
        for _ in range(autonomy.RETIRE_BAD_STREAK + 1):
            state = autonomy.update_portfolio(state, base)
        row = state["portfolios"]["NORMAL_VOLATILITY"]["REVALIDATE_MARKET_DATA"]
        self.assertEqual("recovery", row["status"])
        self.assertEqual(0, row["bad_streak"])

    def test_resource_budget_throttles_optional_learning_under_pressure(self):
        low = fixture(resource=0.20, drift=0.20)
        budget = autonomy.resource_budget(low)
        self.assertEqual("LOW", budget["resource_state"])
        self.assertLessEqual(budget["exploration_budget"], 0.04)
        self.assertLessEqual(budget["learning_budget"], 0.15)

        critical = fixture(resource=0.05, drift=0.70)
        budget2 = autonomy.resource_budget(critical)
        self.assertEqual("CRITICAL", budget2["resource_state"])
        self.assertEqual(0.0, budget2["exploration_budget"])
        self.assertEqual(0.0, budget2["learning_budget"])
        self.assertGreaterEqual(budget2["revalidation_budget"], 0.55)

    def test_upstream_hold_cannot_be_bypassed(self):
        base = fixture(upstream_allow=False)
        projected = autonomy.update_portfolio(autonomy._default_state(), base)
        policy = autonomy.portfolio_policy(base, projected)
        gate = autonomy.autonomous_gate(base, policy, autonomy.resource_budget(base))
        self.assertFalse(gate["allow_execution"])
        self.assertEqual("V388_UPSTREAM_HOLD", gate["status"])
        self.assertFalse(gate["hard_blocker_override"])

    def test_feature_backlog_is_prioritized_but_non_executable(self):
        base = fixture()
        state = autonomy._default_state()
        backlog = autonomy.feature_backlog(base, state, autonomy.resource_budget(base))
        self.assertEqual(1, len(backlog))
        row = backlog[0]
        self.assertIn(row["v388_priority_band"], {"HIGH", "MEDIUM", "LOW"})
        self.assertFalse(row["auto_execute"])
        self.assertFalse(row["auto_generate_source"])
        self.assertFalse(row["source_code_generated"])
        self.assertFalse(row["git_write"])
        self.assertTrue(row["protected_pr_ci_required"])
        self.assertIn("actual_output_validation", row["promotion_requires"])

    def test_mutating_cycle_persists_portfolio_without_git_or_source_write(self):
        base = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / ".v388-state.json"
            with mock.patch.object(autonomy.v387, "run_cycle", return_value=base):
                result = autonomy.run_cycle(
                    domain="tablet_gpt",
                    execute=True,
                    apply_capabilities=True,
                    train_meta=True,
                    apply_skills=True,
                    root=root,
                    now=datetime(2026, 10, 2, 7, 0, tzinfo=timezone.utc),
                    state_path=state_path,
                    persist_outputs=False,
                )
            self.assertTrue(state_path.is_file())
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual("v388", saved["controller_version"])
            self.assertEqual(1, saved["cycle"])
            self.assertIn("NORMAL_VOLATILITY", saved["portfolios"])
            self.assertEqual("v388", result["controller_version"])
            self.assertIn("v388_policy_portfolio", result)
            self.assertIn("v388_resource_budget", result)
            self.assertIn("v388_feature_backlog", result)
            self.assertFalse(result["safety"]["git_write"])
            self.assertFalse(result["safety"]["source_code_auto_generation"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
