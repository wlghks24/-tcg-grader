import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import tablet_autonomous_evolution_v390 as autonomy


NOW = datetime(2026, 10, 2, 8, 0, tzinfo=timezone.utc)


def fixture(*, upstream_allow=True, freshness=0.10, backlog_priority=0.72):
    return {
        "controller_version": "v388",
        "v388_status": "V388_VERIFIED_ALLOW" if upstream_allow else "V388_UPSTREAM_HOLD",
        "v388_autonomous_gate": {
            "allow_execution": upstream_allow,
            "status": "V388_VERIFIED_ALLOW" if upstream_allow else "V388_UPSTREAM_HOLD",
        },
        "v388_policy_portfolio": {
            "regime": "NORMAL_VOLATILITY",
            "upstream_selected_action": "REFRESH_MARKET_DATA",
            "champion_action": "REFRESH_MARKET_DATA",
            "upstream_portfolio_status": "recovery",
            "upstream_portfolio_score": 0.82,
            "champion_score": 0.82,
            "candidates": [
                {
                    "action_id": "REFRESH_MARKET_DATA",
                    "portfolio_score": 0.82,
                    "reward_lcb": 0.18,
                    "long_reward": 0.38,
                    "confidence": 0.84,
                    "verified_samples": 18,
                    "observations": 5,
                    "status": "recovery",
                },
                {
                    "action_id": "EXPAND_MARKET_COVERAGE",
                    "portfolio_score": 0.68,
                    "reward_lcb": 0.08,
                    "long_reward": 0.20,
                    "confidence": 0.72,
                    "verified_samples": 12,
                    "observations": 4,
                    "status": "challenger",
                },
                {
                    "action_id": "UNVERIFIED_ACTION",
                    "portfolio_score": 0.99,
                    "reward_lcb": 0.90,
                    "long_reward": 0.90,
                    "confidence": 0.99,
                    "verified_samples": 0,
                    "observations": 1,
                    "status": "challenger",
                },
            ],
        },
        "v388_resource_budget": {
            "resource_state": "NORMAL",
            "resource_headroom": 0.80,
            "drift_score": 0.12,
            "selected_uncertainty": 0.14,
            "exploration_budget": 0.10,
            "learning_budget": 0.40,
            "revalidation_budget": 0.20,
        },
        "v388_feature_backlog": [
            {
                "v388_proposal_id": "SOURCE_GAP:KR:Pokemon",
                "v388_priority_score": backlog_priority,
                "v388_priority_band": "HIGH" if backlog_priority >= 0.72 else "MEDIUM",
                "v388_recurrence": 3,
                "v387_status": "canary",
                "auto_execute": False,
                "auto_generate_source": False,
                "git_write": False,
                "protected_pr_ci_required": True,
            }
        ],
        "v382_kpis": {
            "score": 0.80,
            "dimensions": {
                "market_freshness": freshness,
                "market_coverage": 0.82,
                "source_health": 0.90,
                "neural_consensus": 0.86,
                "resource_headroom": 0.80,
            },
        },
        "v382_drift": {
            "score": 0.12,
            "level": "LOW",
            "market_regime": "NORMAL_VOLATILITY",
        },
        "market_adaptation_v381": {
            "regime": "UNDERCOVERED",
            "low_coverage_regions": ["KR"],
            "degraded_source_ratio": 0.10,
        },
        "execution": {
            "status": "PLAN_ONLY",
            "executed": False,
            "git_write": False,
            "source_code_modified": False,
        },
        "safety": {},
    }


class TabletAutonomousEvolutionV390Tests(unittest.TestCase):
    def test_safety_contract_preserves_hard_boundaries(self):
        self.assertTrue(autonomy.SAFETY["goal_directed_self_improvement"])
        self.assertTrue(autonomy.SAFETY["verified_meta_critic_enabled"])
        self.assertTrue(autonomy.SAFETY["verified_meta_critic_training_only"])
        self.assertTrue(autonomy.SAFETY["goal_capability_canonical_allowlist_only"])
        self.assertTrue(autonomy.SAFETY["source_feature_plan_non_executable"])
        self.assertTrue(autonomy.SAFETY["v388_gate_cannot_be_bypassed"])
        self.assertFalse(autonomy.SAFETY["peer_model_weights_imported"])
        self.assertFalse(autonomy.SAFETY["peer_raw_state_imported"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_rewrite"])
        self.assertFalse(autonomy.SAFETY["arbitrary_command_execution"])
        self.assertFalse(autonomy.SAFETY["git_write"])
        self.assertFalse(autonomy.SAFETY["market_direction_inferred"])

    def test_critic_trains_only_when_verified_sample_count_increases(self):
        base = fixture()
        rows = autonomy._critic_training_rows(base)
        model = autonomy._default_critic()
        trained, fresh, info = autonomy.train_critic(model, rows)
        self.assertTrue(fresh)
        self.assertEqual("TRAINED_NEW_VERIFIED_SAMPLES", info["status"])
        self.assertGreater(trained["sample_count"], 0)
        self.assertEqual(18, trained["seen_verified_samples"]["REFRESH_MARKET_DATA"])

        trained2, fresh2, info2 = autonomy.train_critic(trained, rows)
        self.assertEqual([], fresh2)
        self.assertEqual("NO_NEW_VERIFIED_TRAINING_SET", info2["status"])
        self.assertEqual(trained["sample_count"], trained2["sample_count"])
        self.assertEqual(trained["w1"], trained2["w1"])
        self.assertEqual(trained["w2"], trained2["w2"])

    def test_goal_planner_prioritizes_freshness_and_builds_allowlisted_capability(self):
        base = fixture(freshness=0.05, backlog_priority=0.40)
        rows = autonomy._critic_training_rows(base)
        critic, _, _ = autonomy.train_critic(autonomy._default_critic(), rows)
        goals = autonomy.derive_goals(base)
        self.assertEqual("RECOVER_MARKET_FRESHNESS", goals[0]["goal_id"])
        plan = autonomy.goal_plan(base, critic, goals)
        self.assertEqual("REFRESH_MARKET_DATA", plan["recommended_action"])
        capability = autonomy.goal_capability(plan, base, now=NOW)
        self.assertIsNotNone(capability)
        self.assertEqual("REQUEST_FRESHNESS_REFRESH", capability["primitive"])
        self.assertTrue(autonomy.v373.validate_capability(capability, now=NOW))

    def test_source_feature_plan_has_shadow_canary_pr_pipeline_and_never_executes(self):
        base = fixture(backlog_priority=0.85)
        plan = {
            "primary_goal": {
                "goal_id": "RESOLVE_PERSISTENT_FEATURE_GAPS",
                "urgency": 0.85,
            }
        }
        rows = autonomy.source_feature_plan(base, plan)
        self.assertEqual(1, len(rows))
        self.assertEqual("protected_pr_candidate", rows[0]["v390_stage"])
        self.assertFalse(rows[0]["auto_execute"])
        self.assertFalse(rows[0]["auto_generate_source"])
        self.assertFalse(rows[0]["git_write"])
        self.assertIn("shadow_spec", rows[0]["promotion_requires"])
        self.assertIn("canary_validation", rows[0]["promotion_requires"])
        self.assertIn("actual_output_validation", rows[0]["promotion_requires"])
        self.assertIsNone(autonomy.goal_capability(
            {
                "primary_goal": {
                    "goal_id": "RESOLVE_PERSISTENT_FEATURE_GAPS",
                    "urgency": 0.90,
                },
                "recommended_action": "REFRESH_MARKET_DATA",
            },
            base,
            now=NOW,
        ))

    def test_upstream_hard_hold_cannot_write_goal_capability_or_execute(self):
        base = fixture(upstream_allow=False, freshness=0.05, backlog_priority=0.40)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / ".v390-state.json"
            cap_path = root / "caps.json"
            with mock.patch.object(autonomy.v388, "run_cycle", return_value=base):
                result = autonomy.run_cycle(
                    domain="tablet_gpt",
                    execute=True,
                    apply_capabilities=True,
                    train_meta=True,
                    apply_skills=True,
                    root=root,
                    now=NOW,
                    state_path=state_path,
                    capability_path=cap_path,
                    persist_outputs=False,
                )
            self.assertEqual("V390_UPSTREAM_HOLD", result["v390_status"])
            self.assertFalse(result["v390_autonomous_gate"]["allow_execution"])
            self.assertFalse(cap_path.exists())
            self.assertFalse(result["execution"]["executed"])
            self.assertFalse(result["safety"]["git_write"])

    def test_mutating_cycle_persists_critic_goal_state_and_next_cycle_capability(self):
        base = fixture(freshness=0.05, backlog_priority=0.40)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / ".v390-state.json"
            cap_path = root / "caps.json"
            with mock.patch.object(autonomy.v388, "run_cycle", return_value=base):
                result = autonomy.run_cycle(
                    domain="tablet_gpt",
                    execute=True,
                    apply_capabilities=True,
                    train_meta=True,
                    apply_skills=True,
                    root=root,
                    now=NOW,
                    state_path=state_path,
                    capability_path=cap_path,
                    persist_outputs=False,
                )
            self.assertTrue(state_path.is_file())
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual("v390", saved["controller_version"])
            self.assertEqual(1, saved["cycle"])
            self.assertGreater(saved["critic"]["sample_count"], 0)
            self.assertTrue(saved["critic"]["seen_verified_samples"])
            self.assertTrue(cap_path.is_file())
            capabilities = json.loads(cap_path.read_text(encoding="utf-8"))["capabilities"]
            self.assertTrue(any(row["primitive"] == "REQUEST_FRESHNESS_REFRESH" for row in capabilities))
            self.assertEqual("v390", result["controller_version"])
            self.assertIn("v390_goal_plan", result)
            self.assertIn("v390_meta_critic", result)
            self.assertIn("v390_source_feature_plan", result)
            self.assertFalse(result["safety"]["source_code_auto_generation"])
            self.assertFalse(result["safety"]["git_write"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
