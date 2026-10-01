import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import tablet_autonomous_evolution_v375 as autonomy

NOW = datetime(2026, 10, 1, 14, 30, tzinfo=timezone.utc)


def base_plan(*, freshness="fresh", low_regions=None, degraded=0.10):
    return {
        "signals": {
            "runtime_models": {
                "status": "healthy",
                "models": {
                    "query_strategy": {"status": "active"},
                    "job_strategy": {"status": "active"},
                },
            },
            "repair_neural": {"active": True, "requires_attention": False, "label_count": 1400},
        },
        "resources": {"status": "normal"},
        "market_profile": {
            "freshness": {"status": freshness},
            "entry_count": 12,
            "low_coverage_regions": list(low_regions or []),
            "degraded_source_ratio": degraded,
            "source_date_older_than_30d_count": 0,
        },
        "state_corruption_hold": False,
        "training_budget": 1,
        "actions": [
            {"id": "TRAIN_QUERY_STRATEGY", "kind": "safe_learning", "priority": 80},
            {"id": "REFRESH_MARKET_DATA", "kind": "proposal", "priority": 60},
        ],
        "safe_learning_candidates": ["TRAIN_QUERY_STRATEGY"],
        "selected_safe_learning_actions": ["TRAIN_QUERY_STRATEGY"],
        "deferred_safe_learning_actions": [],
        "active_capabilities": [],
    }


class TabletAutonomousEvolutionV375Tests(unittest.TestCase):
    def test_safety_keeps_source_git_fact_and_market_direction_boundaries_closed(self):
        safety = autonomy.SAFETY
        self.assertTrue(safety["verified_skill_outcomes_feed_meta_neural"])
        self.assertTrue(safety["skill_outcome_corruption_is_hold"])
        self.assertTrue(safety["uncertainty_aware_candidate_selection"])
        self.assertTrue(safety["cross_gap_declarative_capability_composition"])
        self.assertFalse(safety["source_code_auto_generation"])
        self.assertFalse(safety["source_code_auto_rewrite"])
        self.assertFalse(safety["arbitrary_command_execution"])
        self.assertFalse(safety["git_write"])
        self.assertFalse(safety["verification_bypass"])
        self.assertFalse(safety["price_or_grade_invention"])
        self.assertFalse(safety["market_direction_inferred"])

    def test_corrupt_skill_outcome_store_is_fail_closed_and_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "skill.jsonl"
            original = "{not-json}\n"
            path.write_text(original, encoding="utf-8")
            loaded = autonomy.load_skill_outcomes_strict(path=path)
            self.assertTrue(loaded["corruption_hold"])
            result = autonomy.persist_skill_outcomes_fail_closed([{
                "verified": True,
                "recipe": "RECOVER_FRESHNESS",
                "skill_id": "RECOVER_FRESHNESS:MARKET",
                "reward": 1.0,
                "regression_detected": False,
                "evidence_ref": "ci:verified",
                "verified_at": NOW.isoformat(),
            }], path=path)
            self.assertFalse(result["written"])
            self.assertEqual("SKILL_OUTCOME_CORRUPTION_HOLD", result["status"])
            self.assertEqual(original, path.read_text(encoding="utf-8"))

    def test_verified_trial_feedback_bridges_only_exact_meta_features(self):
        good = {
            "verified": True,
            "recipe": "RECOVER_FRESHNESS",
            "skill_id": "RECOVER_FRESHNESS:MARKET",
            "reward": 0.9,
            "evidence_ref": "trial:1",
            "meta_action_id": "REFRESH_MARKET_DATA",
            "meta_features": [0.0] * autonomy.v374.v373.META_INPUT_DIM,
        }
        bad = dict(good, evidence_ref="trial:2", meta_features=[2.0] * autonomy.v374.v373.META_INPUT_DIM)
        rows = autonomy.meta_feedback_rows([good, bad])
        self.assertEqual(1, len(rows))
        self.assertEqual("REFRESH_MARKET_DATA", rows[0]["action_id"])
        self.assertEqual(0.9, rows[0]["reward"])
        self.assertTrue(rows[0]["evidence_ref"].startswith("v375:"))

    def test_repeated_verified_failures_hard_hold_recipe_and_choose_alternative(self):
        outcomes = [{
            "verified": True,
            "recipe": "RECOVER_SOURCE_HEALTH",
            "skill_id": "RECOVER_SOURCE_HEALTH:SOURCE_HEALTH",
            "reward": -0.4,
            "regression_detected": False,
            "evidence_ref": f"trial:{i}",
            "verified_at": NOW.isoformat(),
        } for i in range(3)]
        history = autonomy.extended_history_stats(outcomes)
        self.assertTrue(history["RECOVER_SOURCE_HEALTH"]["hard_hold"])
        candidates = [
            {"skill_id": "RECOVER_SOURCE_HEALTH:SOURCE_HEALTH", "recipe": "RECOVER_SOURCE_HEALTH", "score": 90.0, "risk": 0.15, "resource_eligible": True, "blocked_by_verified_history": False},
            {"skill_id": "EXPAND_REGION_COVERAGE:US", "recipe": "EXPAND_REGION_COVERAGE", "score": 70.0, "risk": 0.10, "resource_eligible": True, "blocked_by_verified_history": False},
        ]
        ranked = autonomy.rerank_candidates(candidates, history)
        held = next(row for row in ranked if row["recipe"] == "RECOVER_SOURCE_HEALTH")
        self.assertEqual(0.0, held["v375_score"])
        self.assertTrue(held["blocked_by_verified_history"])
        selected = autonomy.v374.select_candidate(base_plan(), ranked, skill_state=autonomy.v374._default_skill_state())
        self.assertEqual("EXPAND_REGION_COVERAGE", selected["recipe"])

    def test_cross_gap_composition_uses_only_allowlisted_bounded_capabilities(self):
        selected = {"skill_id": "RECOVER_FRESHNESS:MARKET_FRESHNESS", "recipe": "RECOVER_FRESHNESS", "gap_id": "market_freshness"}
        gaps = [{"kind": "market_freshness"}, {"kind": "source_health"}, {"kind": "region_coverage", "region": "US"}]
        caps = autonomy.compose_cross_gap_capabilities(selected, gaps, now=NOW)
        primitives = {row["primitive"] for row in caps}
        self.assertIn("REQUEST_FRESHNESS_REFRESH", primitives)
        self.assertIn("RETRY_DEGRADED_SOURCES", primitives)
        self.assertIn("PRIORITIZE_REGION", primitives)
        self.assertLessEqual(len(caps), autonomy.MAX_COMPOSED_CAPABILITIES)
        self.assertTrue(all(autonomy.v374.v373.validate_capability(row, now=NOW) for row in caps))
        self.assertTrue(all(row["source_code_change"] is False for row in caps))
        self.assertTrue(all(row["arbitrary_command"] is False for row in caps))

    def test_trial_carries_exact_meta_features_into_verified_feedback(self):
        before = base_plan(freshness="hold")
        skill = {"skill_id": "RECOVER_FRESHNESS:MARKET_FRESHNESS", "recipe": "RECOVER_FRESHNESS", "gap_id": "market_freshness", "score": 80.0}
        trial = autonomy._trial_for_skill(skill, before, now=NOW)
        self.assertEqual(autonomy.v374.v373.META_INPUT_DIM, len(trial["meta_features"]))
        result = autonomy.evaluate_trial(trial, base_plan(freshness="fresh"), now=NOW)
        self.assertIsNotNone(result)
        self.assertEqual(1.0, result["reward"])
        self.assertEqual("REFRESH_MARKET_DATA", result["meta_action_id"])
        self.assertEqual(trial["meta_features"], result["meta_features"])

    def test_meta_feedback_store_deduplicates_and_preserves_verified_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "meta.jsonl"
            row = {"verified": True, "action_id": "REFRESH_MARKET_DATA", "reward": 1.0, "features": [0.0] * autonomy.v374.v373.META_INPUT_DIM, "evidence_ref": "v375:trial:1"}
            first = autonomy.persist_meta_feedback_fail_closed([row], path=path)
            second = autonomy.persist_meta_feedback_fail_closed([row], path=path)
            self.assertTrue(first["written"])
            self.assertFalse(second["written"])
            self.assertEqual("NO_NEW_META_FEEDBACK", second["status"])
            loaded = autonomy.load_meta_outcomes_strict(path=path)
            self.assertFalse(loaded["corruption_hold"])
            self.assertEqual(1, len(loaded["rows"]))

    def test_run_cycle_market_skill_suppresses_model_training_and_never_writes_git(self):
        plan = base_plan(freshness="hold", low_regions=["US"], degraded=0.50)
        base_report = {"plan": plan, "capability_state": {"corruption_hold": False}}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(autonomy.v374.v373, "run_cycle", return_value=base_report), \
                 mock.patch.object(autonomy.v374, "load_skill_state", return_value={"state": autonomy.v374._default_skill_state(), "status": "fresh", "corruption_hold": False}), \
                 mock.patch.object(autonomy.v374, "execute_operational_skill", return_value={"status": "OPERATIONAL_REFRESH_EXECUTED", "executed": True, "recipe": "RECOVER_FRESHNESS", "git_write": False, "source_code_modified": False}) as operational, \
                 mock.patch.object(autonomy.v374.v373.v372, "execute_safe_learning", return_value={"status": "NO_SAFE_LEARNING_ACTION", "results": {}, "git_write": False, "source_code_modified": False, "proposals_executed": False}) as learning, \
                 mock.patch.object(autonomy.v374.v373, "save_capabilities", return_value={"status": "CAPABILITIES_SAVED", "written": True}), \
                 mock.patch.object(autonomy.v374, "save_skill_state", return_value={"status": "SKILL_STATE_SAVED", "written": True}):
                result = autonomy.run_cycle(execute=True, apply_capabilities=True, train_meta=False, apply_skills=True, root=root, now=NOW, proc_root=root / "proc", state_path=root / "state.json", capability_path=root / "caps.json", meta_model_path=root / "model.json", meta_outcomes_path=root / "meta.jsonl", skill_state_path=root / "skills.json", skill_outcomes_path=root / "skill.jsonl", persist_outputs=False)
        operational.assert_called_once()
        learning.assert_called_once()
        self.assertEqual([], result["plan"]["selected_safe_learning_actions"])
        self.assertFalse(result["execution"]["git_write"])
        self.assertFalse(result["execution"]["source_code_modified"])
        self.assertFalse(result["execution"]["proposals_executed"])
        self.assertEqual(1, result["skill_state"]["pending_trial_count"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
