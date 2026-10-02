from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import tcg_grader_autonomous_evolution_v397 as autonomy

NOW = datetime(2026, 10, 2, 12, 45, tzinfo=timezone.utc)


def core_fixture(
    *,
    selected="EXPAND_MARKET_COVERAGE",
    reward=0.35,
    samples=12,
    upstream_allow=True,
    peer_status="PEER_SUMMARY_VERIFIED",
    strong_divergence=False,
    coverage=0.54,
    source_health=0.88,
    headroom=0.86,
    drift=0.18,
):
    actions = [
        {
            "action_id": "EXPAND_MARKET_COVERAGE",
            "score": 0.82,
            "verified_samples": samples,
            "reward_mean": reward,
        },
        {
            "action_id": "REFRESH_MARKET_DATA",
            "score": 0.76,
            "verified_samples": 18,
            "reward_mean": 0.42,
        },
        {
            "action_id": "RETRY_DEGRADED_SOURCES",
            "score": 0.60,
            "verified_samples": 10,
            "reward_mean": 0.20,
        },
        {
            "action_id": "REVALIDATE_ONLY",
            "score": 0.42,
            "verified_samples": 22,
            "reward_mean": 0.12,
        },
    ]
    return {
        "controller_version": "tcg-grader-v396",
        "tcg_grader_autonomy_v392": {
            "quality_score": 0.84,
            "observation": {
                "drift": drift,
                "dimensions": {
                    "market_coverage": coverage,
                    "source_health": source_health,
                    "neural_consensus": 0.82,
                    "resource_headroom": headroom,
                },
            },
        },
        "tcg_grader_autonomy_v395": {
            "resource_schedule": {
                "allow_mutation": upstream_allow,
                "resource_headroom": headroom,
            },
            "source_reliability": {
                "degraded_or_cooldown_ratio": 0.08,
            },
        },
        "tcg_grader_autonomy_v396": {
            "mutual_sync": {
                "peer_status": peer_status,
                "peer_available": peer_status == "PEER_SUMMARY_VERIFIED",
                "trained_this_cycle": True,
                "training_examples": 4,
                "training_loss": 0.04,
                "selected_action": selected,
                "strong_divergence": strong_divergence,
                "max_reward_gap": 0.10,
                "gate": {
                    "status": "V386_MUTUAL_ALLOW" if upstream_allow else "V386_UPSTREAM_HOLD",
                    "allow_execution": upstream_allow,
                },
            },
            "shared_verified_actions": actions,
            "source_feature_plan": [
                {
                    "proposal_id": "TCG_TEST_FEATURE",
                    "upstream_contract_id": "TCG_TEST_FEATURE",
                    "priority": "HIGH",
                    "reason": "verified evidence gap",
                    "auto_execute": False,
                    "auto_generate_source": False,
                    "git_write": False,
                    "protected_pr_ci_required": True,
                }
            ],
        },
        "execution": {"status": "PLAN_ONLY", "executed": False},
        "safety": dict(autonomy.v396.SAFETY),
    }


class TcgGraderLocalMutualAutonomyV397Tests(unittest.TestCase):
    def test_no_cloud_contract(self):
        self.assertFalse(autonomy.SAFETY["cloud_learning_used"])
        self.assertFalse(autonomy.SAFETY["cloud_parallel_learning_used"])
        self.assertTrue(autonomy.SAFETY["v396_mutual_mlp_preserved"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["git_write"])

    def test_self_diagnosis_detects_market_coverage_gap(self):
        result = autonomy.self_diagnose(core_fixture(coverage=0.40), autonomy._default_state())
        ids = {row["fault_id"] for row in result["faults"]}
        self.assertIn("MARKET_COVERAGE_DEFICIT", ids)
        self.assertEqual("MARKET_EVIDENCE_RECOVERY", result["operational_regime"])

    def test_invalid_peer_is_critical_diagnostic(self):
        result = autonomy.self_diagnose(
            core_fixture(peer_status="PEER_SUMMARY_REJECTED"),
            autonomy._default_state(),
        )
        self.assertEqual("PEER_SUMMARY_INVALID", result["top_fault"]["fault_id"])

    def test_verified_negative_non_recovery_reward_blocks(self):
        core = core_fixture(
            selected="EXPAND_MARKET_COVERAGE",
            reward=-0.60,
            samples=20,
        )
        guard = autonomy.verified_regression_guard(core)
        self.assertTrue(guard["block"])
        self.assertEqual("VERIFIED_REGRESSION_BLOCK", guard["status"])

    def test_recovery_action_negative_reward_is_observe_only(self):
        core = core_fixture(selected="REVALIDATE_ONLY")
        for row in core["tcg_grader_autonomy_v396"]["shared_verified_actions"]:
            if row["action_id"] == "REVALIDATE_ONLY":
                row["reward_mean"] = -0.70
                row["verified_samples"] = 20
        guard = autonomy.verified_regression_guard(core)
        self.assertFalse(guard["block"])
        self.assertEqual("RECOVERY_REGRESSION_OBSERVE_ONLY", guard["status"])

    def test_feature_lifecycle_promotes_recurring_high_priority_contract(self):
        core = core_fixture()
        state = autonomy._default_state()
        first, memory = autonomy.feature_lifecycle_plan(core, state, next_cycle=1)
        self.assertEqual("canary_spec_candidate", first[0]["v397_stage"])
        state["feature_lifecycle"] = memory
        second, _ = autonomy.feature_lifecycle_plan(core, state, next_cycle=2)
        self.assertEqual("protected_pr_candidate", second[0]["v397_stage"])
        self.assertFalse(second[0]["auto_generate_source"])
        self.assertTrue(second[0]["protected_pr_ci_required"])

    def test_counterfactual_panel_is_deterministic(self):
        core = core_fixture()
        diagnosis = autonomy.self_diagnose(core, autonomy._default_state())
        a = autonomy.counterfactual_stress_test(core, diagnosis)
        b = autonomy.counterfactual_stress_test(core, diagnosis)
        self.assertEqual(a, b)
        self.assertTrue(a["deterministic"])

    def test_upstream_hold_cannot_be_bypassed(self):
        core = core_fixture(upstream_allow=False)
        diagnosis = autonomy.self_diagnose(core, autonomy._default_state())
        stress = autonomy.counterfactual_stress_test(core, diagnosis)
        regression = autonomy.verified_regression_guard(core)
        gate = autonomy.autonomous_gate(
            core, diagnosis, stress, regression, corruption_hold=False
        )
        self.assertFalse(gate["allow_execution"])
        self.assertEqual("V397_UPSTREAM_HOLD", gate["status"])

    def test_corrupt_state_holds_mutation(self):
        core = core_fixture()
        diagnosis = autonomy.self_diagnose(core, autonomy._default_state())
        stress = autonomy.counterfactual_stress_test(core, diagnosis)
        regression = autonomy.verified_regression_guard(core)
        gate = autonomy.autonomous_gate(
            core, diagnosis, stress, regression, corruption_hold=True
        )
        self.assertFalse(gate["allow_execution"])
        self.assertEqual("V397_STATE_CORRUPTION_HOLD", gate["status"])

    def test_mutating_cycle_preserves_v396_execution_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = core_fixture(selected="REFRESH_MARKET_DATA", coverage=0.90)
            with mock.patch.object(autonomy.v396, "run_cycle", return_value=fixture) as run:
                result = autonomy.run_cycle(
                    execute=True,
                    apply_capabilities=True,
                    train_meta=True,
                    apply_skills=True,
                    root=root,
                    now=NOW,
                    state_path=root / "state.json",
                    persist_outputs=False,
                )
            self.assertEqual(2, run.call_count)
            payload = result["tcg_grader_autonomy_v397"]
            self.assertFalse(payload["cloud_used"])
            self.assertEqual("V397_VERIFIED_ALLOW", payload["autonomous_gate"]["status"])
            self.assertTrue(payload["state_write"]["written"])

    def test_persisted_cycle_writes_plan_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(autonomy.v396, "run_cycle", return_value=core_fixture()):
                result = autonomy.run_cycle(
                    root=root,
                    now=NOW,
                    state_path=root / "state.json",
                    persist_outputs=True,
                )
            self.assertEqual("SAVED", result["tcg_grader_v397_runtime_output"]["status"])
            plan = json.loads((root / autonomy.PLAN_PATH.name).read_text(encoding="utf-8"))
            self.assertFalse(plan["cloud_used"])
            self.assertFalse(plan["source_code_auto_generation"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
