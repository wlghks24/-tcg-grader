import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import tablet_autonomous_evolution_v373 as autonomy


NOW = datetime(2026, 10, 1, 8, 30, tzinfo=timezone.utc)


def base_plan():
    return {
        "signals": {
            "runtime_models": {
                "status": "degraded",
                "models": {
                    "query_strategy": {"status": "broken", "reason": "model_json_invalid"},
                    "job_strategy": {"status": "degraded", "reason": "active_model_stale"},
                },
            },
            "repair_neural": {
                "active": False,
                "requires_attention": True,
                "label_count": 1400,
            },
        },
        "resources": {"status": "normal"},
        "market_profile": {
            "freshness": {"status": "fresh"},
            "entry_count": 12,
            "low_coverage_regions": ["US"],
            "degraded_source_ratio": 0.50,
            "source_date_older_than_30d_count": 3,
        },
        "state_corruption_hold": False,
        "training_budget": 1,
        "actions": [
            {"id": "TRAIN_QUERY_STRATEGY", "kind": "safe_learning", "priority": 100},
            {"id": "TRAIN_JOB_STRATEGY", "kind": "safe_learning", "priority": 90},
            {"id": "TRAIN_REPAIR_PRIORITY", "kind": "safe_learning", "priority": 70},
            {"id": "EXPAND_MARKET_COVERAGE", "kind": "proposal", "priority": 55},
            {"id": "RECHECK_DEGRADED_SOURCES", "kind": "proposal", "priority": 65},
        ],
        "safe_learning_candidates": [
            "TRAIN_QUERY_STRATEGY",
            "TRAIN_JOB_STRATEGY",
            "TRAIN_REPAIR_PRIORITY",
        ],
        "selected_safe_learning_actions": ["TRAIN_QUERY_STRATEGY"],
        "deferred_safe_learning_actions": [
            {"id": "TRAIN_JOB_STRATEGY", "reason": "per_cycle_training_budget"},
            {"id": "TRAIN_REPAIR_PRIORITY", "reason": "per_cycle_training_budget"},
        ],
    }


class TabletAutonomousEvolutionV373Tests(unittest.TestCase):
    def test_safety_keeps_code_git_and_fact_boundaries_closed(self):
        safety = autonomy.SAFETY
        self.assertTrue(safety["meta_neural_verified_outcomes_only"])
        self.assertTrue(safety["declarative_capability_auto_generation"])
        self.assertTrue(safety["declarative_capability_auto_activation"])
        self.assertFalse(safety["source_code_auto_generation"])
        self.assertFalse(safety["source_code_auto_rewrite"])
        self.assertFalse(safety["git_write"])
        self.assertFalse(safety["verification_bypass"])
        self.assertFalse(safety["trust_or_fact_auto_promotion"])
        self.assertFalse(safety["market_direction_inferred"])

    def test_market_regime_and_capability_synthesis_follow_operational_evidence(self):
        plan = base_plan()
        regime = autonomy.market_regime(plan)
        self.assertEqual("COVERAGE_AND_SOURCE_STRESS", regime["regime"])
        self.assertFalse(regime["market_direction_inferred"])
        caps = autonomy.synthesize_capabilities(plan, now=NOW)
        ids = {row["id"] for row in caps}
        self.assertIn("PRIORITIZE_REGION:US", ids)
        self.assertIn("RETRY_DEGRADED_SOURCES:MARKET", ids)
        self.assertIn("PRIORITIZE_SAFE_LEARNING:TRAIN_QUERY_STRATEGY", ids)
        self.assertTrue(all(autonomy.validate_capability(row, now=NOW) for row in caps))
        self.assertTrue(all(row["source_code_change"] is False for row in caps))
        self.assertTrue(all(row["arbitrary_command"] is False for row in caps))

    def test_invalid_or_overpowered_capability_is_rejected(self):
        row = autonomy._capability(
            "PRIORITIZE_REGION",
            "US",
            {"region": "US", "boost": autonomy.MAX_OPERATIONAL_BOOST + 0.01},
            {"reason": "test"},
            now=NOW,
        )
        self.assertFalse(autonomy.validate_capability(row, now=NOW))

    def test_verified_outcome_loader_rejects_unverified_and_bad_features(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "outcomes.jsonl"
            good = {
                "verified": True,
                "action_id": "TRAIN_QUERY_STRATEGY",
                "reward": 0.8,
                "features": [0.0] * autonomy.META_INPUT_DIM,
                "evidence_ref": "ci:123",
            }
            bad_unverified = dict(good, verified=False, evidence_ref="ci:124")
            bad_features = dict(good, features=[2.0] * autonomy.META_INPUT_DIM, evidence_ref="ci:125")
            path.write_text(
                "\n".join(json.dumps(row) for row in (good, bad_unverified, bad_features)),
                encoding="utf-8",
            )
            rows = autonomy.load_verified_outcomes(path=path)
        self.assertEqual(1, len(rows))
        self.assertEqual("TRAIN_QUERY_STRATEGY", rows[0]["action_id"])

    def test_meta_neural_trains_only_after_verified_sample_gate(self):
        rows = []
        for i in range(autonomy.MIN_META_OUTCOMES):
            rows.append({
                "action_id": "TRAIN_QUERY_STRATEGY",
                "reward": 1.0 if i % 2 == 0 else 0.7,
                "features": [1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.1, 0.0, 1.0, 0.0],
                "evidence_ref": f"ci:{i}",
            })
        self.assertIsNone(autonomy.train_meta_model(rows[:-1], now=NOW))
        model = autonomy.train_meta_model(rows, now=NOW)
        self.assertIsNotNone(model)
        self.assertTrue(autonomy.validate_meta_model(model, now=NOW))
        scores = autonomy.meta_scores(model, rows[0]["features"])
        self.assertGreater(scores["TRAIN_QUERY_STRATEGY"], -1.0)
        self.assertLessEqual(scores["TRAIN_QUERY_STRATEGY"], 1.0)

    def test_adaptive_plan_stays_within_priority_and_one_model_budget(self):
        plan = base_plan()
        caps = autonomy.synthesize_capabilities(plan, now=NOW)
        model = autonomy._default_meta_model(NOW)
        ranked = autonomy.adaptive_rank_plan(plan, model=model, capabilities=caps)
        selected = ranked["selected_safe_learning_actions"]
        self.assertEqual(1, len(selected))
        self.assertIn(selected[0], autonomy.v372.SAFE_LEARNING_ACTIONS)
        for row in ranked["actions"]:
            self.assertLessEqual(abs(row["neural_priority_delta"]), autonomy.MAX_NEURAL_PRIORITY_DELTA)
            self.assertLessEqual(row["capability_priority_delta"], int(autonomy.MAX_OPERATIONAL_BOOST * 100))

    def test_capability_state_persists_only_valid_allowlisted_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "caps.json"
            caps = autonomy.synthesize_capabilities(base_plan(), now=NOW)
            result = autonomy.save_capabilities(caps, path=path, now=NOW)
            self.assertTrue(result["written"])
            loaded = autonomy.load_capabilities(path=path, now=NOW)
            self.assertFalse(loaded["corruption_hold"])
            self.assertEqual(len(caps), len(loaded["capabilities"]))

    def test_run_cycle_never_executes_source_patch_or_git_write(self):
        plan = base_plan()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(autonomy.v372, "plan_cycle", return_value=plan), \
                 mock.patch.object(
                     autonomy.v372,
                     "execute_safe_learning",
                     return_value={
                         "status": "SAFE_LEARNING_EXECUTED",
                         "results": {"TRAIN_QUERY_STRATEGY": {"status": "TRAINING_GATE_HELD"}},
                         "proposals_executed": False,
                         "git_write": False,
                         "source_code_modified": False,
                     },
                 ) as execute:
                result = autonomy.run_cycle(
                    execute=True,
                    apply_capabilities=True,
                    train_meta=False,
                    root=root,
                    now=NOW,
                    proc_root=root / "proc",
                    state_path=root / "state.json",
                    capability_path=root / "caps.json",
                    meta_model_path=root / "model.json",
                    outcomes_path=root / "outcomes.jsonl",
                    persist_outputs=False,
                )
        execute.assert_called_once()
        self.assertFalse(result["execution"]["git_write"])
        self.assertFalse(result["execution"]["source_code_modified"])
        self.assertFalse(result["execution"]["proposals_executed"])
        self.assertTrue(result["capability_state"]["write"]["written"])


if __name__ == "__main__":
    unittest.main(verbosity=2)