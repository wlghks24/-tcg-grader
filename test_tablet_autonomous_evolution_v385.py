import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import tablet_autonomous_evolution_v385 as autonomy


def base_fixture(*, resource=0.8, drift=0.1, upstream_allow=True):
    return {
        "controller_version": "v382",
        "v382_status": "PLAN_ONLY",
        "v382_kpis": {
            "score": 0.82,
            "dimensions": {
                "market_freshness": 0.86,
                "market_coverage": 0.72,
                "source_health": 0.78,
                "neural_consensus": 0.74,
                "resource_headroom": resource,
            },
        },
        "v382_drift": {
            "level": "LOW" if drift < 0.25 else "HIGH",
            "score": drift,
            "market_regime": "NORMAL_VOLATILITY",
        },
        "v382_neural_calibration": {
            "mean_absolute_error": 0.12,
            "verified_samples": 12,
        },
        "v382_autonomous_gate": {
            "allow_execution": upstream_allow,
            "status": "ALLOW_BOUNDED" if upstream_allow else "V382_UPSTREAM_HOLD",
            "selected_action": "REFRESH_MARKET_DATA",
        },
        "policy_evolution_v381": {
            "candidate_actions": [
                {
                    "action_id": "REFRESH_MARKET_DATA",
                    "score": 0.78,
                    "verified_samples": 12,
                    "reward_mean": 0.45,
                },
                {
                    "action_id": "EXPAND_MARKET_COVERAGE",
                    "score": 0.63,
                    "verified_samples": 8,
                    "reward_mean": 0.20,
                },
                {
                    "action_id": "UNVERIFIED_ACTION",
                    "score": 0.99,
                    "verified_samples": 0,
                    "reward_mean": 1.0,
                },
            ],
        },
        "market_adaptation_v381": {"regime": "NORMAL_VOLATILITY"},
        "v382_feature_contracts": [
            {
                "contract_id": "V382:SOURCE_GAP",
                "gap_kind": "source_health",
                "reason": "persistent verified source gap",
            }
        ],
        "execution": {"status": "PLAN_ONLY", "executed": False},
    }


class TabletAutonomousEvolutionV385Tests(unittest.TestCase):
    def test_network_shape_and_safety_contract(self):
        network = autonomy._initial_network()
        self.assertTrue(autonomy._valid_network(network))
        self.assertEqual(autonomy.HIDDEN_DIM, len(network["w1"]))
        self.assertEqual(autonomy.INPUT_DIM, len(network["w1"][0]))
        self.assertTrue(autonomy.SAFETY["verified_outcomes_only_training"])
        self.assertTrue(autonomy.SAFETY["capability_self_extension_declarative_only"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_rewrite"])
        self.assertFalse(autonomy.SAFETY["arbitrary_command_execution"])
        self.assertFalse(autonomy.SAFETY["git_write"])
        self.assertFalse(autonomy.SAFETY["market_direction_inferred"])

    def test_verified_network_ignores_unverified_candidate(self):
        base = base_fixture()
        initial = autonomy._initial_network()
        result = autonomy.train_verified_network(initial, base, learning_rate=autonomy.BASE_LR)
        self.assertTrue(result["trained"])
        self.assertEqual(2, result["examples"])
        self.assertGreater(result["network"]["updates"], 0)
        self.assertTrue(result["verified_outcomes_only"])

        only_unverified = base_fixture()
        only_unverified["policy_evolution_v381"]["candidate_actions"] = [{
            "action_id": "UNVERIFIED_ACTION",
            "score": 0.99,
            "verified_samples": 0,
            "reward_mean": 1.0,
        }]
        blocked = autonomy.train_verified_network(initial, only_unverified, learning_rate=autonomy.BASE_LR)
        self.assertFalse(blocked["trained"])
        self.assertEqual(0, blocked["examples"])
        self.assertEqual(initial, blocked["network"])

    def test_regime_conditioned_policy_never_infers_direction(self):
        base = base_fixture()
        state = autonomy._default_state()
        state["regime_memory"] = autonomy.regime_memory_update(state, base)
        result = autonomy.neural_policy_scores(state["network"], state, base)
        self.assertEqual("NORMAL_VOLATILITY", result["regime"])
        self.assertFalse(result["market_direction_inferred"])
        self.assertTrue(result["candidates"])
        self.assertIn(result["selected_action"], {
            "REFRESH_MARKET_DATA", "EXPAND_MARKET_COVERAGE", "UNVERIFIED_ACTION"
        })

    def test_capability_forge_uses_only_allowlisted_declarative_primitives(self):
        base = base_fixture(resource=0.2, drift=0.4)
        base["v382_kpis"]["dimensions"]["source_health"] = 0.2
        state = autonomy._default_state()
        recipe = autonomy.forge_capability(
            state,
            base,
            {"detected": True},
        )
        self.assertTrue(recipe["all_primitives_allowlisted"])
        self.assertLessEqual(len(recipe["steps"]), 3)
        self.assertTrue(all(step in autonomy.PRIMITIVE_NAMES for step in recipe["steps"]))
        self.assertFalse(recipe["auto_execute_commands"])
        self.assertFalse(recipe["source_code_generated"])
        self.assertEqual("shadow", recipe["status"])

    def test_capability_recipe_promotes_by_observation_and_rolls_back_on_kpi_drop(self):
        base = base_fixture()
        state = autonomy._default_state()
        first = autonomy.forge_capability(state, base, {"detected": False})
        state["capability_registry"][first["recipe_id"]] = {
            "steps": first["steps"],
            "status": "shadow",
            "observations": 1,
            "activation_kpi": None,
        }
        second = autonomy.forge_capability(state, base, {"detected": False})
        self.assertEqual("canary", second["status"])

        state["capability_registry"][first["recipe_id"]] = {
            "steps": first["steps"],
            "status": "canary",
            "observations": 2,
            "activation_kpi": 0.82,
        }
        third = autonomy.forge_capability(state, base, {"detected": False})
        self.assertEqual("active", third["status"])

        low = base_fixture()
        low["v382_kpis"]["score"] = 0.60
        state["capability_registry"][first["recipe_id"]] = {
            "steps": first["steps"],
            "status": "active",
            "observations": 4,
            "activation_kpi": 0.82,
        }
        rolled = autonomy.forge_capability(state, low, {"detected": False})
        self.assertEqual("rolled_back", rolled["status"])

    def test_resource_scheduler_disables_optional_learning_when_low(self):
        base = base_fixture(resource=0.2)
        recipe = {"status": "active"}
        result = autonomy.resource_scheduler(
            base,
            {"detected": False},
            recipe,
            execute=True,
            apply_capabilities=True,
            train_meta=True,
            apply_skills=True,
        )
        self.assertEqual("LOW", result["resource_state"])
        self.assertTrue(result["allowed"]["execute"])
        self.assertFalse(result["allowed"]["apply_capabilities"])
        self.assertFalse(result["allowed"]["train_meta"])
        self.assertFalse(result["allowed"]["apply_skills"])

    def test_source_feature_plan_is_non_executable_pr_contract(self):
        plan = autonomy.source_feature_plan(autonomy._default_state(), base_fixture())
        self.assertEqual(1, len(plan))
        row = plan[0]
        self.assertFalse(row["auto_execute"])
        self.assertFalse(row["auto_generate_source"])
        self.assertFalse(row["git_write"])
        self.assertTrue(row["protected_pr_ci_required"])
        self.assertIn("repository_integrity", row["acceptance_sequence"])
        self.assertIn("actual_output_validation", row["acceptance_sequence"])

    def test_upstream_hold_cannot_be_bypassed(self):
        base = base_fixture(upstream_allow=False)
        state = autonomy._default_state()
        policy = autonomy.neural_policy_scores(state["network"], state, base)
        cp = autonomy.change_point(state, base)
        recipe = autonomy.forge_capability(state, base, cp)
        scheduler = autonomy.resource_scheduler(
            base, cp, recipe,
            execute=True, apply_capabilities=True, train_meta=True, apply_skills=True,
        )
        gate = autonomy.autonomous_gate(base, policy, cp, scheduler)
        self.assertFalse(gate["allow_execution"])
        self.assertEqual("V385_UPSTREAM_HOLD", gate["status"])
        self.assertFalse(gate["hard_blocker_override"])

    def test_mutating_cycle_persists_bounded_state_without_git_or_source_write(self):
        base = base_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / ".state.json"
            lock_path = root / ".lock"
            with mock.patch.object(autonomy.v382, "run_cycle", return_value=base):
                result = autonomy.run_cycle(
                    execute=True,
                    apply_capabilities=True,
                    train_meta=True,
                    apply_skills=True,
                    root=root,
                    now=datetime(2026, 10, 2, 4, 0, tzinfo=timezone.utc),
                    v385_state_path=state_path,
                    v385_lock_path=lock_path,
                    persist_outputs=False,
                )
            self.assertTrue(state_path.is_file())
            self.assertFalse(result["safety"]["git_write"])
            self.assertFalse(result["safety"]["source_code_auto_generation"])
            self.assertEqual("v385", result["controller_version"])
            self.assertIn("v385_verified_neural_policy", result)
            self.assertIn("v385_capability_forge", result)
            self.assertIn("v385_resource_scheduler", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
