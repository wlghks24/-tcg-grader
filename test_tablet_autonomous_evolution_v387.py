import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import tablet_autonomous_evolution_v387 as autonomy


def base_fixture(*, drift=0.10, peer=True, action="REFRESH_MARKET_DATA", score=0.82):
    return {
        "controller_version": "v386",
        "v386_status": "V386_MUTUAL_ALLOW" if peer else "V386_LOCAL_ONLY_ALLOW",
        "v386_autonomous_gate": {
            "allow_execution": True,
            "status": "V386_MUTUAL_ALLOW" if peer else "V386_LOCAL_ONLY_ALLOW",
        },
        "v386_mutual_neural_policy": {
            "peer_available": peer,
            "local_regime": "NORMAL_VOLATILITY",
            "peer_regime": "NORMAL_VOLATILITY" if peer else None,
            "selected_action": action,
            "strong_divergence": False,
            "candidates": [
                {
                    "action_id": action,
                    "score": score,
                    "local_score": min(1.0, score + 0.02),
                    "peer_score": max(0.0, score - 0.02) if peer else None,
                    "mutual_neural_score": score if peer else None,
                    "local_verified_samples": 18,
                    "peer_verified_samples": 16 if peer else 0,
                    "reward_gap": 0.05 if peer else None,
                }
            ],
            "market_direction_inferred": False,
        },
        "v386_function_plan": [
            {
                "proposal_id": "SOURCE_GAP:KR:Pokemon",
                "reason": "verified source coverage gap",
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
                "source_health": 0.80,
                "neural_consensus": 0.82,
                "resource_headroom": 0.78,
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


class TabletAutonomousEvolutionV387Tests(unittest.TestCase):
    def test_safety_contract_preserves_fail_closed_boundaries(self):
        self.assertTrue(autonomy.SAFETY["uncertainty_aware_action_selection"])
        self.assertTrue(autonomy.SAFETY["verified_sample_confidence_required"])
        self.assertTrue(autonomy.SAFETY["multi_objective_verified_governor"])
        self.assertTrue(autonomy.SAFETY["declarative_feature_lifecycle"])
        self.assertFalse(autonomy.SAFETY["peer_model_weights_imported"])
        self.assertFalse(autonomy.SAFETY["peer_raw_state_imported"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_rewrite"])
        self.assertFalse(autonomy.SAFETY["arbitrary_command_execution"])
        self.assertFalse(autonomy.SAFETY["git_write"])
        self.assertFalse(autonomy.SAFETY["market_direction_inferred"])

    def test_verified_mutual_evidence_produces_bounded_confidence(self):
        state = autonomy._default_state()
        policy = autonomy.uncertainty_policy(base_fixture(), state)
        self.assertTrue(policy["peer_available"])
        self.assertEqual("REFRESH_MARKET_DATA", policy["selected_action"])
        self.assertGreaterEqual(policy["selected_confidence"], autonomy.MIN_MUTUAL_CONFIDENCE)
        self.assertLessEqual(policy["selected_uncertainty"], 1.0)
        self.assertFalse(policy["market_direction_inferred"])
        row = policy["candidates"][0]
        self.assertGreater(row["sample_support"], 0.0)
        self.assertGreater(row["verified_agreement"], 0.0)
        self.assertLessEqual(row["multi_objective_score"], 1.0)

    def test_unstable_regime_allows_recovery_but_blocks_non_recovery(self):
        state = autonomy._default_state()
        recovery = autonomy.uncertainty_policy(
            base_fixture(drift=0.80, action="REFRESH_MARKET_DATA"),
            state,
        )
        recovery_gate = autonomy.autonomous_gate(
            base_fixture(drift=0.80, action="REFRESH_MARKET_DATA"),
            recovery,
        )
        self.assertTrue(recovery_gate["allow_execution"])
        self.assertEqual("V387_RECOVERY_ALLOW", recovery_gate["status"])
        self.assertTrue(recovery_gate["recovery_only"])

        base = base_fixture(drift=0.80, action="EXPAND_MARKET_COVERAGE")
        policy = autonomy.uncertainty_policy(base, state)
        gate = autonomy.autonomous_gate(base, policy)
        self.assertFalse(gate["allow_execution"])
        self.assertEqual("V387_REGIME_TRANSITION_HOLD", gate["status"])
        self.assertIn("UNSTABLE_OPERATIONAL_REGIME", gate["reasons"])

    def test_low_confidence_non_recovery_requires_revalidation(self):
        base = base_fixture(peer=False, action="EXPAND_MARKET_COVERAGE", score=0.20)
        candidate = base["v386_mutual_neural_policy"]["candidates"][0]
        candidate["local_verified_samples"] = 1
        state = autonomy._default_state()
        policy = autonomy.uncertainty_policy(base, state)
        gate = autonomy.autonomous_gate(base, policy)
        self.assertTrue(policy["revalidation_required"])
        self.assertFalse(gate["allow_execution"])
        self.assertEqual("V387_UNCERTAINTY_HOLD", gate["status"])

    def test_feature_lifecycle_canary_and_verified_kpi_rollback(self):
        base = base_fixture()
        policy = autonomy.uncertainty_policy(base, autonomy._default_state())
        policy["selected_confidence"] = 0.76
        rows = autonomy.feature_lifecycle(base, policy, autonomy._default_state())
        self.assertEqual("canary", rows[0]["v387_status"])
        self.assertFalse(rows[0]["auto_execute"])
        self.assertFalse(rows[0]["auto_generate_source"])
        self.assertTrue(rows[0]["protected_pr_ci_required"])

        low = base_fixture()
        low["v382_kpis"]["score"] = 0.60
        state = autonomy._default_state()
        state["proposal_history"]["SOURCE_GAP:KR:Pokemon"] = {
            "status": "active_candidate",
            "observations": 5,
            "activation_kpi": 0.84,
        }
        low_policy = autonomy.uncertainty_policy(low, state)
        low_policy["selected_confidence"] = 0.90
        rolled = autonomy.feature_lifecycle(low, low_policy, state)
        self.assertEqual("rolled_back", rolled[0]["v387_status"])

    def test_regime_history_detects_transition_without_direction_inference(self):
        state = autonomy._default_state()
        state["regime_history"].append({
            "observed_at": "2026-10-01T00:00:00+00:00",
            "local_regime": "LOW_VOLATILITY",
            "peer_regime": "LOW_VOLATILITY",
            "level": "STABLE",
            "drift_score": 0.10,
        })
        base = base_fixture(drift=0.60)
        base["v386_mutual_neural_policy"]["local_regime"] = "HIGH_VOLATILITY"
        transition = autonomy.regime_transition(base, state)
        self.assertIn(transition["level"], {"TRANSITION", "UNSTABLE"})
        self.assertTrue(transition["local_regime_changed"])
        self.assertFalse(transition["market_direction_inferred"])

    def test_corrupt_state_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text('{"schema_version":1,"controller_version":"v387"}', encoding="utf-8")
            loaded = autonomy.load_state(path)
            self.assertTrue(loaded["corruption_hold"])
            self.assertEqual("corrupt", loaded["status"])

    def test_mutating_cycle_persists_state_without_git_or_source_write(self):
        base = base_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / ".state.json"
            with mock.patch.object(autonomy.v386, "run_cycle", return_value=base):
                result = autonomy.run_cycle(
                    domain="tablet_gpt",
                    execute=True,
                    apply_capabilities=True,
                    train_meta=True,
                    apply_skills=True,
                    root=root,
                    now=datetime(2026, 10, 2, 6, 0, tzinfo=timezone.utc),
                    state_path=state_path,
                    persist_outputs=False,
                )
            self.assertTrue(state_path.is_file())
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual("v387", saved["controller_version"])
            self.assertEqual("v387", result["controller_version"])
            self.assertIn("v387_uncertainty_policy", result)
            self.assertIn("v387_feature_lifecycle", result)
            self.assertFalse(result["safety"]["git_write"])
            self.assertFalse(result["safety"]["source_code_auto_generation"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
