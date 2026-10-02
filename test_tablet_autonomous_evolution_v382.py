import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import tablet_autonomous_evolution_v382 as autonomy


class TabletAutonomousEvolutionV382Tests(unittest.TestCase):
    def test_safety_boundary_is_fail_closed(self):
        self.assertTrue(autonomy.SAFETY["multi_objective_verified_feedback_governor"])
        self.assertTrue(autonomy.SAFETY["concept_drift_detection_enabled"])
        self.assertTrue(autonomy.SAFETY["verified_regression_quarantine_enabled"])
        self.assertTrue(autonomy.SAFETY["shadow_challenger_advisory_only"])
        self.assertTrue(autonomy.SAFETY["feature_contracts_non_executable"])
        self.assertTrue(autonomy.SAFETY["feature_contracts_require_protected_pr_ci"])
        self.assertTrue(autonomy.SAFETY["v381_gate_cannot_be_bypassed"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_rewrite"])
        self.assertFalse(autonomy.SAFETY["arbitrary_command_execution"])
        self.assertFalse(autonomy.SAFETY["git_write"])
        self.assertFalse(autonomy.SAFETY["market_direction_inferred"])

    def test_verified_policy_regression_recommends_quarantine(self):
        base = {
            "policy_evolution_v381": {
                "selection": {"champion_action": "TRAIN_QUERY_STRATEGY"},
                "verified_outcome_stats": {
                    "TRAIN_QUERY_STRATEGY": {
                        "verified_samples": 16,
                        "reward_mean": -0.40,
                        "reward_min": -1.0,
                        "reward_max": 0.20,
                    }
                },
            }
        }
        result = autonomy.reliability(base)
        self.assertEqual(16, result["samples"])
        self.assertTrue(result["quarantine_recommended"])
        self.assertLess(result["lower_confidence_bound"], -0.20)

    def test_high_drift_allows_only_recovery_actions(self):
        state = autonomy._default()
        kpi = {"score": 0.8, "dimensions": {}}
        drift = {"level": "HIGH", "score": 0.8}
        reliability = {"quarantine_recommended": False}
        now = datetime(2026, 10, 2, tzinfo=timezone.utc)

        non_recovery = {
            "v381_status": "PLAN_ONLY",
            "autonomous_decision": {"allow_execution": True},
            "policy_evolution_v381": {"selection": {"champion_action": "TRAIN_QUERY_STRATEGY"}},
        }
        held = autonomy.gate(non_recovery, state, drift, reliability, kpi, now)
        self.assertFalse(held["allow_execution"])
        self.assertIn("HIGH_DRIFT_RECOVERY_ONLY", held["reasons"])

        recovery = {
            "v381_status": "PLAN_ONLY",
            "autonomous_decision": {"allow_execution": True},
            "policy_evolution_v381": {"selection": {"champion_action": "REFRESH_MARKET_DATA"}},
        }
        allowed = autonomy.gate(recovery, state, drift, reliability, kpi, now)
        self.assertTrue(allowed["allow_execution"])

    def test_shadow_challenger_uses_v381_verified_policy_candidates(self):
        base = {
            "policy_evolution_v381": {
                "selection": {"champion_action": "TRAIN_QUERY_STRATEGY"},
                "candidate_actions": [
                    {"action_id": "TRAIN_QUERY_STRATEGY", "score": 0.80, "verified_samples": 20, "reward_mean": 0.20},
                    {"action_id": "REFRESH_MARKET_DATA", "score": 0.77, "verified_samples": 14, "reward_mean": 0.30},
                    {"action_id": "RECHECK_DEGRADED_SOURCES", "score": 0.70, "verified_samples": 16, "reward_mean": 0.25},
                ],
            }
        }
        result = autonomy.challenger(base)
        self.assertTrue(result["available"])
        self.assertFalse(result["auto_execute"])
        self.assertEqual("v381_verified_policy_candidates", result["source"])
        self.assertEqual("REFRESH_MARKET_DATA", result["candidate"]["action_id"])
        self.assertEqual(14, result["candidate"]["verified_samples"])

    def test_feature_contracts_never_auto_execute(self):
        base = {
            "source_feature_proposals_v381": [
                {"proposal_id": "source-gap-1", "gap_kind": "coverage"},
            ]
        }
        contracts = autonomy.contracts(base)
        self.assertEqual(1, len(contracts))
        contract = contracts[0]
        self.assertFalse(contract["auto_execute"])
        self.assertFalse(contract["auto_generate_source"])
        self.assertFalse(contract["git_write"])
        self.assertTrue(contract["protected_pr_ci_required"])
        self.assertIn("repository_integrity", contract["acceptance_sequence"])
        self.assertIn("security_boundary_regression", contract["rollback_triggers"])

    def test_corrupt_state_blocks_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text("{not-json", encoding="utf-8")
            loaded = autonomy.load_state(path)
        self.assertTrue(loaded["corruption_hold"])
        self.assertEqual("corrupt", loaded["status"])

    def test_drift_never_infers_market_direction(self):
        state = autonomy._default()
        state["last_kpis"] = {
            "score": 0.9,
            "dimensions": {
                "market_freshness": 1.0,
                "market_coverage": 1.0,
                "source_health": 1.0,
                "neural_consensus": 1.0,
                "resource_headroom": 1.0,
            },
        }
        current = {
            "score": 0.5,
            "dimensions": {
                "market_freshness": 0.2,
                "market_coverage": 0.3,
                "source_health": 0.4,
                "neural_consensus": 0.5,
                "resource_headroom": 0.6,
            },
        }
        base = {
            "market_adaptation_v381": {"regime": "SOURCE_DEGRADED"},
            "information_exchange_memory_v381": {"input_digest": "abc"},
            "policy_evolution_v381": {"candidate_actions": []},
        }
        result = autonomy.drift(state, current, base)
        self.assertEqual("HIGH", result["level"])
        self.assertFalse(result["market_direction_inferred"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
