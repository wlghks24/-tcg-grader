from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import tablet_autonomous_evolution_v386 as mutual
import tcg_grader_autonomous_evolution_v396 as autonomy

NOW = datetime(2026, 10, 2, 11, 50, tzinfo=timezone.utc)


def core_fixture(
    *,
    reward=0.60,
    samples=8,
    blocked=False,
    allow_mutation=True,
    market_mode="COVERAGE_EXPANSION",
    degraded=0.05,
):
    ranked = [
        {"action_id": "REFRESH_MARKET_EVIDENCE", "utility": 0.82, "verified_reward_prior": reward},
        {"action_id": "PRIORITIZE_LOW_COVERAGE_REGION", "utility": 0.71, "verified_reward_prior": 0.30},
        {"action_id": "INCREASE_MARKET_OBSERVATION", "utility": 0.66, "verified_reward_prior": 0.24},
        {"action_id": "RETRY_DEGRADED_SOURCES", "utility": 0.58, "verified_reward_prior": 0.10},
        {"action_id": "PRIORITIZE_REPAIR_LEARNING", "utility": 0.52, "verified_reward_prior": 0.08},
        {"action_id": "REVALIDATE_ONLY", "utility": 0.20, "verified_reward_prior": -0.05},
    ]
    return {
        "controller_version": "tcg-grader-v395",
        "market_adaptation_v381": {
            "regime": "UNDERCOVERED",
            "low_coverage_regions": ["KR"],
        },
        "tcg_grader_autonomy_v392": {
            "quality_score": 0.84,
            "observation": {
                "market_age_hours": 2.0,
                "market_stale_after_hours": 6.0,
                "low_coverage_regions": ["KR"],
                "drift": 0.14,
                "dimensions": {
                    "market_coverage": 0.62,
                    "source_health": 0.83,
                    "neural_consensus": 0.79,
                    "resource_headroom": 0.88,
                },
            },
            "neural_plan": {
                "model_sample_count": samples,
                "ranked_actions": ranked,
                "selected_actions": ["REFRESH_MARKET_EVIDENCE"],
            },
        },
        "tcg_grader_autonomy_v394": {
            "recovery_plan": [
                {"action": "EXPAND_VERIFIED_LABELS", "company": "BGS", "priority": 0.82}
            ],
        },
        "tcg_grader_autonomy_v395": {
            "blocked": blocked,
            "resource_schedule": {
                "allow_mutation": allow_mutation,
                "resource_headroom": 0.88,
                "mode": "INTENSIVE_VERIFIED_LEARNING",
            },
            "market_operating_mode": {
                "mode": market_mode,
                "regime": "UNDERCOVERED",
            },
            "source_reliability": {
                "degraded_or_cooldown_ratio": degraded,
            },
            "source_feature_contracts": [
                {
                    "feature_id": "TCG_V395_ACTIVE_VERIFIED_LABEL_ACQUISITION",
                    "reason": "verified evidence gap",
                }
            ],
        },
        "execution": {"status": "PLAN_ONLY", "executed": False},
        "safety": dict(autonomy.v395.SAFETY),
    }


def peer_summary(*, reward=0.55, score=0.79):
    adapter = autonomy.build_mutual_adapter(core_fixture())
    summary = mutual.build_summary(adapter, "tablet_gpt", now=NOW)
    for row in summary["candidates"]:
        if row["action_id"] == "REFRESH_MARKET_DATA":
            row["reward_mean"] = reward
            row["score"] = score
    return summary


class TcgGraderMutualSyncV396Tests(unittest.TestCase):
    def test_safety_contract(self):
        self.assertTrue(autonomy.SAFETY["bidirectional_verified_outcome_summary"])
        self.assertTrue(autonomy.SAFETY["mutual_consensus_neural_policy"])
        self.assertTrue(autonomy.SAFETY["peer_summary_invalid_blocks_mutation"])
        self.assertTrue(autonomy.SAFETY["v395_resource_protection_preserved"])
        self.assertTrue(autonomy.SAFETY["v395_active_learning_rules_preserved"])
        self.assertFalse(autonomy.SAFETY["peer_model_weights_imported"])
        self.assertFalse(autonomy.SAFETY["peer_raw_state_imported"])
        self.assertFalse(autonomy.SAFETY["peer_grading_calibration_imported"])
        self.assertFalse(autonomy.SAFETY["peer_evidence_can_force_mutation"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["git_write"])
        self.assertFalse(autonomy.SAFETY["market_direction_inferred"])

    def test_shared_adapter_uses_verified_reward_history_and_v395_operational_context(self):
        rows = autonomy._shared_candidates(
            core_fixture(reward=0.44, samples=mutual.MIN_VERIFIED_SAMPLES, market_mode="COVERAGE_EXPANSION", degraded=0.05)
        )
        by_action = {row["action_id"]: row for row in rows}
        self.assertIn("REFRESH_MARKET_DATA", by_action)
        self.assertIn("EXPAND_MARKET_COVERAGE", by_action)
        self.assertIn("RETRY_DEGRADED_SOURCES", by_action)
        self.assertEqual(mutual.MIN_VERIFIED_SAMPLES, by_action["REFRESH_MARKET_DATA"]["verified_samples"])
        self.assertEqual(0.44, by_action["REFRESH_MARKET_DATA"]["reward_mean"])
        self.assertEqual(0.79, by_action["EXPAND_MARKET_COVERAGE"]["score"])
        self.assertEqual(0.59, by_action["RETRY_DEGRADED_SOURCES"]["score"])

    def test_no_peer_training_candidate_without_verified_history(self):
        self.assertEqual([], autonomy._shared_candidates(core_fixture(samples=0)))

    def test_adapter_exports_strict_summary_without_grading_state(self):
        adapter = autonomy.build_mutual_adapter(core_fixture())
        summary = mutual.build_summary(adapter, "tcg_grader", now=NOW)
        mutual.validate_summary(summary, "tcg_grader", now=NOW)
        encoded = json.dumps(summary, ensure_ascii=False)
        self.assertNotIn("global_models", encoded)
        self.assertNotIn("vision_profiles", encoded)
        self.assertNotIn("certification_id", encoded)
        self.assertFalse(summary["safety"]["raw_model_weights_shared"])
        self.assertFalse(summary["safety"]["raw_state_shared"])
        self.assertFalse(summary["safety"]["grading_raw_shared"])
        self.assertFalse(summary["safety"]["grading_calibration_shared"])

    def test_verified_peer_divergence_blocks_before_v395_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            peer = root / "peer.json"
            peer.write_text(json.dumps(peer_summary(reward=-0.85), ensure_ascii=False), encoding="utf-8")
            with mock.patch.object(autonomy.v395, "run_cycle", return_value=core_fixture()) as run:
                result = autonomy.run_cycle(
                    execute=True,
                    apply_capabilities=True,
                    train_meta=True,
                    apply_skills=True,
                    root=root,
                    now=NOW,
                    state_path=root / "mutual-state.json",
                    peer_summary_path=peer,
                    local_summary_path=root / "local.json",
                    persist_outputs=False,
                )
            sync = result["tcg_grader_autonomy_v396"]["mutual_sync"]
            self.assertEqual("V386_PEER_DIVERGENCE_HOLD", sync["gate"]["status"])
            self.assertFalse(sync["gate"]["allow_execution"])
            self.assertEqual(1, run.call_count)
            self.assertFalse(result["execution"]["executed"])

    def test_verified_peer_agreement_allows_v395_mutating_cycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            peer = root / "peer.json"
            peer.write_text(json.dumps(peer_summary(reward=0.58), ensure_ascii=False), encoding="utf-8")
            with mock.patch.object(autonomy.v395, "run_cycle", return_value=core_fixture()) as run:
                result = autonomy.run_cycle(
                    execute=True,
                    apply_capabilities=True,
                    train_meta=True,
                    apply_skills=True,
                    root=root,
                    now=NOW,
                    state_path=root / "mutual-state.json",
                    peer_summary_path=peer,
                    local_summary_path=root / "local.json",
                    persist_outputs=False,
                )
            sync = result["tcg_grader_autonomy_v396"]["mutual_sync"]
            self.assertEqual("V386_MUTUAL_ALLOW", sync["gate"]["status"])
            self.assertTrue(sync["gate"]["allow_execution"])
            self.assertTrue(sync["trained_this_cycle"])
            self.assertGreater(sync["training_examples"], 0)
            self.assertEqual(2, run.call_count)

    def test_invalid_peer_summary_blocks_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            peer = root / "peer.json"
            value = peer_summary()
            value["raw_log"] = {"must": "reject"}
            peer.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
            with mock.patch.object(autonomy.v395, "run_cycle", return_value=core_fixture()) as run:
                result = autonomy.run_cycle(
                    execute=True,
                    root=root,
                    now=NOW,
                    state_path=root / "mutual-state.json",
                    peer_summary_path=peer,
                    local_summary_path=root / "local.json",
                    persist_outputs=False,
                )
            sync = result["tcg_grader_autonomy_v396"]["mutual_sync"]
            self.assertEqual("PEER_SUMMARY_REJECTED", sync["peer_status"])
            self.assertEqual("V396_PEER_SUMMARY_INVALID_HOLD", sync["gate"]["status"])
            self.assertFalse(sync["gate"]["allow_execution"])
            self.assertEqual(1, run.call_count)

    def test_missing_peer_is_local_only_without_fake_confidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(autonomy.v395, "run_cycle", return_value=core_fixture()):
                result = autonomy.run_cycle(
                    root=root,
                    now=NOW,
                    state_path=root / "mutual-state.json",
                    peer_summary_path=root / "missing.json",
                    local_summary_path=root / "local.json",
                    persist_outputs=False,
                )
            sync = result["tcg_grader_autonomy_v396"]["mutual_sync"]
            self.assertEqual("PEER_SUMMARY_MISSING", sync["peer_status"])
            self.assertFalse(sync["peer_available"])
            self.assertFalse(sync["trained_this_cycle"])
            self.assertFalse(sync["strong_divergence"])

    def test_v395_resource_protection_blocks_mutation(self):
        protected = core_fixture(allow_mutation=False)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            peer = root / "peer.json"
            peer.write_text(json.dumps(peer_summary(), ensure_ascii=False), encoding="utf-8")
            with mock.patch.object(autonomy.v395, "run_cycle", return_value=protected) as run:
                result = autonomy.run_cycle(
                    execute=True,
                    root=root,
                    now=NOW,
                    state_path=root / "mutual-state.json",
                    peer_summary_path=peer,
                    local_summary_path=root / "local.json",
                    persist_outputs=False,
                )
            sync = result["tcg_grader_autonomy_v396"]["mutual_sync"]
            self.assertFalse(sync["gate"]["allow_execution"])
            self.assertEqual("V386_UPSTREAM_HOLD", sync["gate"]["status"])
            self.assertEqual(1, run.call_count)

    def test_source_feature_plan_is_proposal_only(self):
        adapter = autonomy.build_mutual_adapter(core_fixture())
        policy = mutual.mutual_policy(mutual._initial_network(), adapter, peer_summary())
        rows = mutual.function_plan(adapter, policy)
        self.assertTrue(rows)
        for row in rows:
            self.assertFalse(row["auto_execute"])
            self.assertFalse(row["auto_generate_source"])
            self.assertFalse(row["git_write"])
            self.assertTrue(row["protected_pr_ci_required"])

    def test_persisted_cycle_writes_strict_local_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            peer = root / "peer.json"
            local = root / "local.json"
            peer.write_text(json.dumps(peer_summary(), ensure_ascii=False), encoding="utf-8")
            with mock.patch.object(autonomy.v395, "run_cycle", return_value=core_fixture()):
                result = autonomy.run_cycle(
                    root=root,
                    now=NOW,
                    state_path=root / "mutual-state.json",
                    peer_summary_path=peer,
                    local_summary_path=local,
                    persist_outputs=True,
                )
            self.assertTrue(local.is_file())
            payload = json.loads(local.read_text(encoding="utf-8"))
            mutual.validate_summary(payload, "tcg_grader", now=NOW)
            self.assertEqual("SAVED", result["tcg_grader_v396_runtime_output"]["status"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
