import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import tablet_autonomous_evolution_v374 as autonomy


NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def base_plan(
    *,
    freshness="hold",
    low_regions=("US",),
    degraded_ratio=0.50,
    resource_status="normal",
    query_status="broken",
    job_status="degraded",
    repair_attention=True,
):
    return {
        "signals": {
            "runtime_models": {
                "status": "degraded",
                "models": {
                    "query_strategy": {"status": query_status, "reason": "test"},
                    "job_strategy": {"status": job_status, "reason": "test"},
                },
            },
            "repair_neural": {
                "active": False,
                "requires_attention": repair_attention,
                "label_count": 1500,
            },
        },
        "resources": {"status": resource_status},
        "market_profile": {
            "freshness": {"status": freshness},
            "entry_count": 12,
            "low_coverage_regions": list(low_regions),
            "degraded_source_ratio": degraded_ratio,
            "source_date_older_than_30d_count": 3,
        },
        "state_corruption_hold": False,
        "training_budget": 1,
        "actions": [
            {"id": "TRAIN_QUERY_STRATEGY", "kind": "safe_learning", "priority": 100, "adaptive_priority": 100},
            {"id": "TRAIN_JOB_STRATEGY", "kind": "safe_learning", "priority": 90, "adaptive_priority": 90},
            {"id": "TRAIN_REPAIR_PRIORITY", "kind": "safe_learning", "priority": 70, "adaptive_priority": 70},
        ],
        "safe_learning_candidates": [
            "TRAIN_QUERY_STRATEGY",
            "TRAIN_JOB_STRATEGY",
            "TRAIN_REPAIR_PRIORITY",
        ],
        "selected_safe_learning_actions": ["TRAIN_QUERY_STRATEGY"],
        "deferred_safe_learning_actions": [],
        "active_capabilities": [],
    }


class TabletAutonomousEvolutionV374Tests(unittest.TestCase):
    def test_safety_keeps_runtime_closed_loop_bounded(self):
        safety = autonomy.SAFETY
        self.assertTrue(safety["closed_loop_candidate_generation"])
        self.assertTrue(safety["multi_candidate_scoring"])
        self.assertTrue(safety["one_runtime_skill_per_cycle"])
        self.assertEqual(1, safety["max_heavy_operations_per_cycle"])
        self.assertTrue(safety["operational_refresh_existing_updater_only"])
        self.assertTrue(safety["verified_skill_outcome_learning_only"])
        self.assertTrue(safety["negative_history_auto_suspends_skill"])
        self.assertTrue(safety["declarative_skill_auto_composition"])
        self.assertFalse(safety["source_level_gap_auto_implementation"])
        self.assertFalse(safety["source_code_auto_generation"])
        self.assertFalse(safety["source_code_auto_rewrite"])
        self.assertFalse(safety["arbitrary_command_execution"])
        self.assertFalse(safety["git_write"])
        self.assertFalse(safety["verification_bypass"])
        self.assertFalse(safety["trust_or_fact_auto_promotion"])
        self.assertFalse(safety["price_or_grade_invention"])
        self.assertFalse(safety["market_direction_inferred"])

    def test_multi_candidate_scoring_selects_highest_safe_candidate(self):
        plan = base_plan()
        gaps = autonomy.detect_gaps(plan)
        candidates = autonomy.generate_candidates(
            plan, gaps, autonomy.skill_history_stats([])
        )
        self.assertGreaterEqual(len(candidates), 4)
        self.assertEqual("RECOVER_FRESHNESS", candidates[0]["recipe"])
        selected = autonomy.select_candidate(
            plan, candidates, skill_state=autonomy._default_skill_state()
        )
        self.assertIsNotNone(selected)
        self.assertEqual("RECOVER_FRESHNESS", selected["recipe"])

    def test_negative_verified_history_blocks_recipe(self):
        rows = [
            {
                "recipe": "RECOVER_FRESHNESS",
                "skill_id": f"x{i}",
                "reward": -0.8,
                "regression_detected": True,
                "evidence_ref": f"e{i}",
                "verified_at": NOW.isoformat(),
            }
            for i in range(autonomy.MIN_HISTORY_TO_BLOCK)
        ]
        history = autonomy.skill_history_stats(rows)
        self.assertTrue(history["RECOVER_FRESHNESS"]["blocked"])
        candidates = autonomy.generate_candidates(
            base_plan(), autonomy.detect_gaps(base_plan()), history
        )
        freshness = [row for row in candidates if row["recipe"] == "RECOVER_FRESHNESS"]
        self.assertTrue(freshness)
        self.assertTrue(all(row["score"] == 0 for row in freshness))

    def test_pending_market_trial_prevents_causal_overlap(self):
        plan = base_plan()
        candidates = autonomy.generate_candidates(
            plan, autonomy.detect_gaps(plan), autonomy.skill_history_stats([])
        )
        freshness = next(row for row in candidates if row["recipe"] == "RECOVER_FRESHNESS")
        state = autonomy._default_skill_state()
        state["pending_trials"] = [autonomy._trial_for_skill(freshness, plan, now=NOW)]
        selected = autonomy.select_candidate(plan, candidates, skill_state=state)
        self.assertIsNotNone(selected)
        self.assertEqual("RECOVER_MODEL", selected["recipe"])

    def test_market_skill_suppresses_model_training_for_one_heavy_operation(self):
        plan = base_plan()
        candidates = autonomy.generate_candidates(
            plan, autonomy.detect_gaps(plan), autonomy.skill_history_stats([])
        )
        freshness = next(row for row in candidates if row["recipe"] == "RECOVER_FRESHNESS")
        evolved = autonomy.evolve_plan(
            plan, freshness, autonomy.skill_capabilities(freshness, now=NOW)
        )
        self.assertEqual([], evolved["selected_safe_learning_actions"])

        model = next(row for row in candidates if row["recipe"] == "RECOVER_MODEL")
        model_plan = autonomy.evolve_plan(
            plan, model, autonomy.skill_capabilities(model, now=NOW)
        )
        self.assertLessEqual(len(model_plan["selected_safe_learning_actions"]), 1)

    def test_operational_skill_uses_existing_updater_only(self):
        plan = base_plan()
        candidates = autonomy.generate_candidates(
            plan, autonomy.detect_gaps(plan), autonomy.skill_history_stats([])
        )
        freshness = next(row for row in candidates if row["recipe"] == "RECOVER_FRESHNESS")
        import tcg_updater
        with mock.patch.object(
            tcg_updater, "update_cycle", return_value={"ok": True}
        ) as update_cycle:
            result = autonomy.execute_operational_skill(freshness, plan)
        update_cycle.assert_called_once_with("tablet-v374-autonomous-refresh")
        self.assertEqual("OPERATIONAL_REFRESH_EXECUTED", result["status"])
        self.assertFalse(result["git_write"])
        self.assertFalse(result["source_code_modified"])

    def test_verified_outcome_loader_rejects_unverified_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "outcomes.jsonl"
            good = {
                "verified": True,
                "recipe": "RECOVER_FRESHNESS",
                "skill_id": "s1",
                "reward": 1.0,
                "regression_detected": False,
                "evidence_ref": "v374:test",
                "verified_at": NOW.isoformat(),
            }
            bad = dict(good, verified=False, evidence_ref="v374:bad")
            path.write_text(
                "\n".join(json.dumps(row) for row in (good, bad)) + "\n",
                encoding="utf-8",
            )
            rows = autonomy.load_verified_skill_outcomes(path=path)
        self.assertEqual(1, len(rows))
        self.assertEqual("v374:test", rows[0]["evidence_ref"])

    def test_objective_trial_detects_improvement_and_regression(self):
        plan = base_plan()
        candidates = autonomy.generate_candidates(
            plan, autonomy.detect_gaps(plan), autonomy.skill_history_stats([])
        )
        freshness = next(row for row in candidates if row["recipe"] == "RECOVER_FRESHNESS")
        freshness_trial = autonomy._trial_for_skill(freshness, plan, now=NOW)
        improved = autonomy.evaluate_trial(
            freshness_trial,
            base_plan(freshness="fresh"),
            now=NOW + timedelta(hours=1),
        )
        self.assertIsNotNone(improved)
        self.assertEqual(1.0, improved["reward"])
        self.assertFalse(improved["regression_detected"])

        source = next(row for row in candidates if row["recipe"] == "RECOVER_SOURCE_HEALTH")
        source_trial = autonomy._trial_for_skill(source, plan, now=NOW)
        regressed = autonomy.evaluate_trial(
            source_trial,
            base_plan(degraded_ratio=0.80),
            now=NOW + timedelta(hours=1),
        )
        self.assertIsNotNone(regressed)
        self.assertTrue(regressed["regression_detected"])
        self.assertLess(regressed["reward"], 0)

    def test_outcome_persistence_is_deduplicated_by_evidence(self):
        row = {
            "verified": True,
            "recipe": "RECOVER_FRESHNESS",
            "skill_id": "s1",
            "reward": 1.0,
            "regression_detected": False,
            "evidence_ref": "v374:dedupe",
            "verified_at": NOW.isoformat(),
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "outcomes.jsonl"
            first = autonomy.persist_verified_outcomes([row], path=path)
            second = autonomy.persist_verified_outcomes([row], path=path)
            lines = path.read_text(encoding="utf-8").splitlines()
        self.assertTrue(first["written"])
        self.assertEqual(1, first["count"])
        self.assertFalse(second["written"])
        self.assertEqual(0, second["count"])
        self.assertEqual(1, len(lines))

    def test_corrupt_skill_state_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "skills.json"
            path.write_text("{bad", encoding="utf-8")
            loaded = autonomy.load_skill_state(path=path, now=NOW)
            write = autonomy.save_skill_state(
                loaded["state"],
                path=path,
                corruption_hold=loaded["corruption_hold"],
                now=NOW,
            )
        self.assertTrue(loaded["corruption_hold"])
        self.assertFalse(write["written"])
        self.assertEqual("SKILL_STATE_CORRUPTION_HOLD", write["status"])

    def test_regression_suspends_recipe_before_next_selection(self):
        plan = base_plan()
        candidates = autonomy.generate_candidates(
            plan, autonomy.detect_gaps(plan), autonomy.skill_history_stats([])
        )
        source = next(row for row in candidates if row["recipe"] == "RECOVER_SOURCE_HEALTH")
        state = autonomy._default_skill_state()
        state["pending_trials"] = [autonomy._trial_for_skill(source, plan, now=NOW)]
        state["pending_trials"][0]["before"]["degraded_source_ratio"] = 0.40

        regressed_plan = base_plan(degraded_ratio=0.80)
        reconciled, verified = autonomy.reconcile_skill_state(
            state,
            plan=regressed_plan,
            selected_skill=None,
            history=autonomy.skill_history_stats([]),
            now=NOW + timedelta(hours=1),
        )
        self.assertEqual(1, len(verified))
        self.assertTrue(verified[0]["regression_detected"])
        self.assertIn("RECOVER_SOURCE_HEALTH", reconciled["suspended_recipes"])

    def test_persistent_bad_skill_escalates_only_to_nonexecuting_source_proposal(self):
        gaps = [{
            "gap_id": "source_health",
            "kind": "source_health",
            "severity": 0.9,
            "confidence": 1.0,
            "evidence": {"degraded_source_ratio": 0.8},
        }]
        history = {
            "RECOVER_SOURCE_HEALTH": {
                "samples": 4,
                "mean_reward": -0.5,
                "regression_count": 2,
                "regression_rate": 0.5,
                "blocked": True,
            }
        }
        proposals = autonomy.source_feature_proposals(gaps, history)
        self.assertEqual(1, len(proposals))
        self.assertTrue(proposals[0]["normal_pr_pipeline_required"])
        self.assertFalse(proposals[0]["auto_implementation"])
        self.assertFalse(proposals[0]["source_code_generation"])
        self.assertFalse(proposals[0]["git_write"])

    def test_run_cycle_executes_bounded_skill_without_git_or_source_write(self):
        plan = base_plan()
        base_report = {
            "plan": plan,
            "capability_state": {"corruption_hold": False},
            "meta_neural": {"active": True, "sample_count": 12},
        }
        safe_result = {
            "status": "NO_SAFE_LEARNING_ACTION",
            "results": {},
            "git_write": False,
            "source_code_modified": False,
            "proposals_executed": False,
        }
        operational = {
            "status": "OPERATIONAL_REFRESH_EXECUTED",
            "executed": True,
            "recipe": "RECOVER_FRESHNESS",
            "git_write": False,
            "source_code_modified": False,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(autonomy.v373, "run_cycle", return_value=base_report), \
                 mock.patch.object(
                     autonomy.v373.v372, "execute_safe_learning", return_value=safe_result
                 ), \
                 mock.patch.object(
                     autonomy, "execute_operational_skill", return_value=operational
                 ):
                result = autonomy.run_cycle(
                    execute=True,
                    apply_capabilities=False,
                    apply_skills=True,
                    train_meta=False,
                    root=root,
                    now=NOW,
                    proc_root=root / "proc",
                    state_path=root / "state.json",
                    capability_path=root / "caps.json",
                    meta_model_path=root / "meta.json",
                    meta_outcomes_path=root / "meta-outcomes.jsonl",
                    skill_state_path=root / "skills.json",
                    skill_outcomes_path=root / "skill-outcomes.jsonl",
                    persist_outputs=False,
                )
        self.assertEqual("RECOVER_FRESHNESS", result["selected_skill"]["recipe"])
        self.assertEqual(1, result["skill_state"]["pending_trial_count"])
        self.assertFalse(result["execution"]["git_write"])
        self.assertFalse(result["execution"]["source_code_modified"])
        self.assertFalse(result["execution"]["proposals_executed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
