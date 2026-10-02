import json
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import tablet_autonomous_evolution_v381 as v381


def healthy_preview():
    return {
        "controller_version": "v380",
        "v380_status": "PLAN_ONLY",
        "safety": dict(v381.v380.SAFETY),
        "quality_governance": {"ok": True, "status": "QUALITY_100_1000_READY"},
        "evidence_barrier": {"ok": True, "status": "EVIDENCE_COMMIT_OK"},
        "skill_state": {"corruption_hold": False},
        "plan": {
            "resources": {"status": "normal"},
            "market_profile": {
                "freshness": {"status": "fresh"},
                "low_coverage_regions": [],
                "degraded_source_ratio": 0.05,
                "entry_count": 100,
                "source_date_older_than_30d_count": 1,
            },
            "meta_scores": {
                "TRAIN_QUERY_STRATEGY": 0.60,
                "TRAIN_JOB_STRATEGY": 0.40,
                "TRAIN_REPAIR_PRIORITY": 0.20,
                "REFRESH_MARKET_DATA": 0.10,
                "EXPAND_MARKET_COVERAGE": 0.05,
                "RECHECK_DEGRADED_SOURCES": 0.00,
            },
        },
        "selected_skill": {"skill_id": "verified-skill", "recipe": "OBSERVE_ONLY", "risk": 0.05},
        "adaptive_mode": {"mode": "STEADY_VERIFIED_EVOLUTION", "market_regime": "HEALTHY"},
        "v378_single_run_lock": {"status": "V378_LOCK_NOT_REQUIRED", "error_code": None},
        "single_run_lock": {"status": "LOCK_NOT_REQUIRED", "error_code": None},
        "execution": {
            "status": "PLAN_ONLY", "executed": False, "git_write": False,
            "source_code_modified": False, "proposals_executed": False,
        },
        "autonomous_decision": {
            "status": "ALLOW_BOUNDED", "allow_execution": True,
            "directive": "EXECUTE_VERIFIED_SELECTION", "hard_blockers": [],
        },
        "information_exchange_manager": {
            "status": "EXCHANGE_CORROBORATED",
            "mutation_allowed": True,
            "peer_influence_allowed": True,
            "selected_management_action": "OBSERVE_CORROBORATED_PATTERNS",
            "counts": {
                "corroborated": 2, "single-system-only": 0,
                "conflicting-fix": 0, "not-applicable": 0,
            },
            "signal_score": 0.85,
            "input_digest": "a" * 64,
        },
    }


def verified_rows(action, count, reward):
    return [
        {
            "action_id": action,
            "reward": reward,
            "features": [0.2] * v381.v373.META_INPUT_DIM,
            "evidence_ref": f"verified:{action}:{i}",
        }
        for i in range(count)
    ]


class TabletAutonomousEvolutionV381Tests(unittest.TestCase):
    def test_verified_outcomes_are_the_only_policy_learning_input(self):
        fake = verified_rows("TRAIN_QUERY_STRATEGY", 8, 0.8)
        with mock.patch.object(v381.v373, "load_verified_outcomes", return_value=fake) as loader:
            stats = v381.verified_outcome_stats(Path("ignored"))
        loader.assert_called_once()
        self.assertEqual(8, stats["TRAIN_QUERY_STRATEGY"]["verified_samples"])
        self.assertEqual(0.8, stats["TRAIN_QUERY_STRATEGY"]["reward_mean"])
        self.assertEqual(0, stats["TRAIN_JOB_STRATEGY"]["verified_samples"])
        self.assertTrue(v381.SAFETY["verified_outcome_policy_learning_only"])
        self.assertFalse(v381.SAFETY["raw_peer_lessons_persisted"])

    def test_challenger_cannot_promote_below_verified_sample_gate(self):
        state = v381._default_policy_state()
        state["champion_action"] = "TRAIN_QUERY_STRATEGY"
        candidates = [
            {"action_id": "TRAIN_JOB_STRATEGY", "score": 0.99, "verified_samples": 7, "reward_mean": 0.9, "promotion_eligible": False},
            {"action_id": "TRAIN_QUERY_STRATEGY", "score": 0.60, "verified_samples": 20, "reward_mean": 0.7, "promotion_eligible": True},
        ]
        result = v381.select_champion(state, candidates)
        self.assertEqual("TRAIN_QUERY_STRATEGY", result["champion_action"])
        self.assertFalse(result["promoted"])

    def test_verified_challenger_requires_bounded_margin(self):
        state = v381._default_policy_state()
        state["champion_action"] = "TRAIN_QUERY_STRATEGY"
        candidates = [
            {"action_id": "TRAIN_JOB_STRATEGY", "score": 0.78, "verified_samples": 12, "reward_mean": 0.82, "promotion_eligible": True},
            {"action_id": "TRAIN_QUERY_STRATEGY", "score": 0.70, "verified_samples": 16, "reward_mean": 0.80, "promotion_eligible": True},
        ]
        result = v381.select_champion(state, candidates)
        self.assertTrue(result["promoted"])
        self.assertEqual("TRAIN_JOB_STRATEGY", result["champion_action"])

    def test_market_and_exchange_recipe_is_allowlisted_and_bounded(self):
        base = healthy_preview()
        base["plan"]["market_profile"].update({
            "freshness": {"status": "stale"},
            "low_coverage_regions": ["KR", "JP", "US"],
            "degraded_source_ratio": 0.8,
        })
        base["information_exchange_manager"]["status"] = "EXCHANGE_REPRODUCTION_REQUIRED"
        market = v381.market_operational_state(base)
        exchange = v381.information_exchange_memory(base)
        selection = {"champion": {
            "action_id": "REFRESH_MARKET_DATA", "promotion_eligible": True,
            "verified_samples": 20, "score": 0.9,
        }}
        recipe = v381.capability_recipe(base, market, exchange, selection, now=datetime.now(timezone.utc))
        self.assertLessEqual(len(recipe["capabilities"]), v381.MAX_RECIPE_CAPABILITIES)
        self.assertGreaterEqual(len(recipe["capabilities"]), 1)
        for row in recipe["capabilities"]:
            self.assertTrue(v381.v373.validate_capability(row))
            self.assertFalse(row["source_code_change"])
            self.assertFalse(row["arbitrary_command"])
        self.assertFalse(recipe["market_direction_inferred"])

    def test_information_exchange_memory_is_summary_only(self):
        memory = v381.information_exchange_memory(healthy_preview())
        encoded = json.dumps(memory, sort_keys=True)
        self.assertTrue(memory["summary_only"])
        self.assertFalse(memory["raw_peer_lessons_persisted"])
        self.assertNotIn("fix_pattern", encoded)
        self.assertNotIn("lessons", encoded)

    def test_corrupt_policy_memory_blocks_before_mutating_v380(self):
        preview = healthy_preview()
        corrupt = {"status": "corrupt", "corruption_hold": True, "state": v381._default_policy_state()}
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.object(v381.v380, "run_cycle", return_value=preview) as core, \
             mock.patch.object(v381, "load_policy_state", return_value=corrupt):
            result = v381.run_cycle(
                execute=True, apply_capabilities=True, train_meta=True, apply_skills=True,
                root=Path(td), persist_outputs=False,
            )
        self.assertEqual(1, core.call_count)
        self.assertEqual("V381_POLICY_MEMORY_HOLD", result["v381_status"])
        self.assertFalse(result["execution"]["executed"])

    def test_successful_core_persists_bounded_next_cycle_recipe_and_policy(self):
        preview = healthy_preview()
        executed = deepcopy(preview)
        executed["v380_status"] = "V376_EXECUTED"
        executed["execution"] = {
            "status": "V376_EXECUTED", "executed": True, "git_write": False,
            "source_code_modified": False, "proposals_executed": False,
        }
        outcomes = verified_rows("TRAIN_QUERY_STRATEGY", 10, 0.7)
        outcomes += verified_rows("TRAIN_JOB_STRATEGY", 10, 0.95)
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.object(v381.v380, "run_cycle", side_effect=[preview, executed]) as core, \
             mock.patch.object(v381.v373, "load_verified_outcomes", return_value=outcomes):
            root = Path(td)
            result = v381.run_cycle(
                execute=True, apply_capabilities=True, train_meta=True, apply_skills=True,
                root=root, capability_path=root / "caps.json",
                policy_state_path=root / "policy.json", persist_outputs=False,
            )
            self.assertTrue((root / "policy.json").is_file())
            if result["capability_recipe_v381"]["capabilities"]:
                self.assertTrue((root / "caps.json").is_file())
                saved = json.loads((root / "caps.json").read_text(encoding="utf-8"))
                self.assertLessEqual(len(saved["capabilities"]), v381.MAX_RECIPE_CAPABILITIES)
                for row in saved["capabilities"]:
                    self.assertTrue(v381.v373.validate_capability(row))
        self.assertEqual(2, core.call_count)
        self.assertTrue(result["policy_evolution_v381"]["write"]["written"])
        self.assertFalse(result["safety"]["source_code_auto_generation"])
        self.assertFalse(result["safety"]["git_write"])

    def test_source_level_gap_is_proposal_only(self):
        state = v381._default_policy_state()
        state["history"] = [
            {
                "observed_at": f"2026-10-0{i+1}T00:00:00+00:00",
                "market_regime": "SOURCE_DEGRADED",
                "exchange_status": "EXCHANGE_CORROBORATED",
                "exchange_digest": "a" * 64,
                "champion_action": None,
                "decision_status": "PLAN_ONLY",
            }
            for i in range(3)
        ]
        proposals = v381.source_gap_proposals(
            state, {"regime": "SOURCE_DEGRADED"},
            {"status": "EXCHANGE_CORROBORATED"}, {"capabilities": []},
        )
        self.assertTrue(proposals)
        self.assertFalse(proposals[0]["auto_apply"])
        self.assertTrue(proposals[0]["pr_required"])
        self.assertTrue(v381.SAFETY["source_level_gap_proposal_only"])
        self.assertFalse(v381.SAFETY["source_code_auto_rewrite"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
