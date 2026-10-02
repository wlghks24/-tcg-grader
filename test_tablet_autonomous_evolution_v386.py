import json
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import tablet_autonomous_evolution_v386 as autonomy


NOW = datetime(2026, 10, 2, 6, 0, tzinfo=timezone.utc)


def base_fixture():
    return {
        "controller_version": "v385",
        "v385_status": "PLAN_ONLY",
        "v382_kpis": {
            "score": 0.84,
            "dimensions": {
                "market_freshness": 0.88,
                "market_coverage": 0.76,
                "source_health": 0.81,
                "neural_consensus": 0.79,
                "resource_headroom": 0.85,
            },
        },
        "v382_drift": {"score": 0.10, "level": "LOW", "market_regime": "NORMAL_VOLATILITY"},
        "v385_verified_neural_policy": {
            "regime": "NORMAL_VOLATILITY",
            "candidates": [
                {
                    "action_id": "REFRESH_MARKET_DATA",
                    "score": 0.82,
                    "verified_samples": 12,
                    "reward_mean": 0.60,
                },
                {
                    "action_id": "EXPAND_MARKET_COVERAGE",
                    "score": 0.67,
                    "verified_samples": 9,
                    "reward_mean": 0.25,
                },
                {
                    "action_id": "UNVERIFIED_ACTION",
                    "score": 0.99,
                    "verified_samples": 0,
                    "reward_mean": 1.0,
                },
            ],
        },
        "v385_autonomous_gate": {
            "allow_execution": True,
            "status": "ALLOW_BOUNDED",
            "upstream_action": "REFRESH_MARKET_DATA",
        },
        "v385_source_feature_plan": [
            {
                "proposal_id": "V385:gap",
                "upstream_contract_id": "V382:SOURCE_GAP",
                "priority": "MEDIUM",
                "auto_execute": False,
                "auto_generate_source": False,
                "git_write": False,
                "protected_pr_ci_required": True,
            }
        ],
        "execution": {"status": "PLAN_ONLY", "executed": False},
    }


def peer_summary(*, reward=0.55, score=0.78, generated_at=NOW):
    base = base_fixture()
    summary = autonomy.build_summary(base, "tcg_grader", now=generated_at)
    for row in summary["candidates"]:
        if row["action_id"] == "REFRESH_MARKET_DATA":
            row["reward_mean"] = reward
            row["score"] = score
    return summary


class MutualNeuralCoevolutionV386Tests(unittest.TestCase):
    def test_network_shape_and_safety(self):
        network = autonomy._initial_network()
        self.assertTrue(autonomy._valid_network(network))
        self.assertEqual(autonomy.HIDDEN_DIM, len(network["w1"]))
        self.assertEqual(autonomy.INPUT_DIM, len(network["w1"][0]))
        self.assertTrue(autonomy.SAFETY["bidirectional_verified_learning_summary"])
        self.assertTrue(autonomy.SAFETY["mutual_training_requires_matching_verified_outcomes"])
        self.assertFalse(autonomy.SAFETY["peer_model_weights_imported"])
        self.assertFalse(autonomy.SAFETY["peer_raw_state_imported"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["git_write"])
        self.assertFalse(autonomy.SAFETY["market_direction_inferred"])

    def test_summary_exports_only_verified_candidates_and_strict_safety(self):
        summary = autonomy.build_summary(base_fixture(), "tablet_gpt", now=NOW)
        self.assertEqual("tablet_gpt", summary["domain"])
        self.assertEqual(
            {"REFRESH_MARKET_DATA", "EXPAND_MARKET_COVERAGE"},
            {row["action_id"] for row in summary["candidates"]},
        )
        self.assertFalse(summary["safety"]["raw_model_weights_shared"])
        self.assertFalse(summary["safety"]["raw_state_shared"])
        self.assertFalse(summary["safety"]["grading_raw_shared"])
        self.assertFalse(summary["safety"]["grading_calibration_shared"])

    def test_peer_summary_extra_state_and_stale_data_fail_closed(self):
        value = peer_summary()
        value["raw_log"] = {"secret": True}
        with self.assertRaises(ValueError):
            autonomy.validate_summary(value, "tcg_grader", now=NOW)

        stale = peer_summary(generated_at=NOW - timedelta(hours=49))
        with self.assertRaises(ValueError):
            autonomy.validate_summary(stale, "tcg_grader", now=NOW)

    def test_mutual_network_trains_only_on_matching_verified_actions(self):
        state = autonomy._default_state()
        result = autonomy.train_mutual_network(state["network"], base_fixture(), peer_summary())
        self.assertTrue(result["trained"])
        self.assertEqual(2, result["examples"])
        self.assertGreater(result["network"]["updates"], 0)

        no_match = peer_summary()
        for row in no_match["candidates"]:
            row["action_id"] = "PEER_ONLY_" + row["action_id"]
        blocked = autonomy.train_mutual_network(state["network"], base_fixture(), no_match)
        self.assertFalse(blocked["trained"])
        self.assertEqual(0, blocked["examples"])
        self.assertEqual(state["network"], blocked["network"])

    def test_strong_verified_peer_divergence_blocks_before_v385_mutation(self):
        base = base_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            peer_path = root / "peer.json"
            peer_path.write_text(
                json.dumps(peer_summary(reward=-0.80), ensure_ascii=False),
                encoding="utf-8",
            )
            with mock.patch.object(autonomy.v385, "run_cycle", return_value=base) as run:
                result = autonomy.run_cycle(
                    execute=True,
                    apply_capabilities=True,
                    train_meta=True,
                    apply_skills=True,
                    root=root,
                    now=NOW,
                    state_path=root / ".state.json",
                    peer_summary_path=peer_path,
                    local_summary_path=root / "local.json",
                    persist_outputs=False,
                )
            self.assertEqual("V386_PEER_DIVERGENCE_HOLD", result["v386_status"])
            self.assertFalse(result["v386_autonomous_gate"]["allow_execution"])
            self.assertEqual(1, run.call_count)
            self.assertFalse(result["execution"]["executed"])

    def test_verified_peer_agreement_allows_v385_mutating_cycle(self):
        base = base_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            peer_path = root / "peer.json"
            peer_path.write_text(
                json.dumps(peer_summary(reward=0.58), ensure_ascii=False),
                encoding="utf-8",
            )
            with mock.patch.object(autonomy.v385, "run_cycle", return_value=base) as run:
                result = autonomy.run_cycle(
                    execute=True,
                    apply_capabilities=True,
                    train_meta=True,
                    apply_skills=True,
                    root=root,
                    now=NOW,
                    state_path=root / ".state.json",
                    peer_summary_path=peer_path,
                    local_summary_path=root / "local.json",
                    persist_outputs=False,
                )
            self.assertEqual("V386_MUTUAL_ALLOW", result["v386_status"])
            self.assertTrue(result["v386_autonomous_gate"]["allow_execution"])
            self.assertEqual(2, run.call_count)
            self.assertTrue(result["v386_mutual_neural_policy"]["trained_this_cycle"])

    def test_missing_peer_is_local_only_and_never_fabricates_peer_evidence(self):
        base = base_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(autonomy.v385, "run_cycle", return_value=base):
                result = autonomy.run_cycle(
                    root=root,
                    now=NOW,
                    state_path=root / ".state.json",
                    peer_summary_path=root / "missing.json",
                    local_summary_path=root / "local.json",
                    persist_outputs=False,
                )
            self.assertEqual("PLAN_ONLY", result["v386_status"])
            self.assertEqual("PEER_SUMMARY_MISSING", result["v386_peer_exchange"]["peer_status"]["status"])
            self.assertFalse(result["v386_mutual_neural_policy"]["peer_available"])
            self.assertFalse(result["v386_mutual_neural_policy"]["trained_this_cycle"])

    def test_function_plan_never_auto_generates_or_writes_git(self):
        policy = autonomy.mutual_policy(
            autonomy._initial_network(),
            base_fixture(),
            peer_summary(),
        )
        plans = autonomy.function_plan(base_fixture(), policy)
        self.assertEqual(1, len(plans))
        row = plans[0]
        self.assertFalse(row["auto_execute"])
        self.assertFalse(row["auto_generate_source"])
        self.assertFalse(row["git_write"])
        self.assertTrue(row["protected_pr_ci_required"])
        self.assertIn("repository_integrity", row["required_promotion_gates"])
        self.assertIn("tablet_gpt_alignment", row["required_promotion_gates"])
        self.assertIn("actual_output_validation", row["required_promotion_gates"])

    def test_persisted_cycle_exports_local_summary_without_peer_raw_state(self):
        base = base_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            peer_path = root / "peer.json"
            local_path = root / "local.json"
            peer_path.write_text(json.dumps(peer_summary(), ensure_ascii=False), encoding="utf-8")
            with mock.patch.object(autonomy.v385, "run_cycle", return_value=base):
                result = autonomy.run_cycle(
                    root=root,
                    now=NOW,
                    state_path=root / ".state.json",
                    peer_summary_path=peer_path,
                    local_summary_path=local_path,
                    persist_outputs=True,
                )
            self.assertTrue(local_path.is_file())
            payload = json.loads(local_path.read_text(encoding="utf-8"))
            autonomy.validate_summary(payload, "tablet_gpt", now=NOW)
            self.assertEqual("SAVED", result["v386_runtime_output"]["status"])
            self.assertFalse(result["safety"]["peer_raw_state_imported"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
