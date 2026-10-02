import fcntl
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import tablet_autonomous_evolution_v378 as v378


def ready_policy():
    return {
        "ok": True,
        "preparation_senior_perspectives": 100,
        "preparation_before_expert_review": True,
        "expert_groups": 25,
        "review_lenses": 40,
        "review_cells": 1000,
        "errors": [],
    }


def sample_core(status="PLAN_ONLY"):
    return {
        "controller_version": "v377",
        "v377_status": status,
        "plan": {
            "signals": {
                "runtime_models": {
                    "status": "healthy",
                    "models": {
                        "query_strategy": {"status": "active"},
                        "job_strategy": {"status": "active"},
                    },
                },
                "repair_neural": {"active": True, "requires_attention": False},
            },
            "market_profile": {
                "freshness": {"status": "fresh"},
                "low_coverage_regions": [],
                "degraded_source_ratio": 0.0,
                "entry_count": 10,
                "source_date_older_than_30d_count": 0,
            },
        },
        "gaps": [],
        "neural_reliability": {"confidence": 0.8},
        "selected_skill": {"skill_id": "s1", "recipe": "OBSERVE_ONLY", "score": 80.0},
        "source_feature_proposals": [],
        "execution": {"status": status, "executed": False},
    }


class TabletAutonomousEvolutionV378Tests(unittest.TestCase):
    def test_quality_policy_blocks_mutation_before_core(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(
            v378.quality_review_policy, "validate", return_value={"ok": False, "errors": ["review_cells"]}
        ), mock.patch.object(v378.v377, "run_cycle") as core:
            result = v378.run_cycle(
                execute=True,
                apply_capabilities=True,
                train_meta=True,
                apply_skills=True,
                root=Path(td),
                quality_policy_path=Path(td) / "bad.json",
                persist_outputs=False,
            )
            core.assert_not_called()
            self.assertEqual("QUALITY_GOVERNANCE_HOLD", result["v378_status"])
            self.assertFalse(result["execution"]["executed"])
            self.assertFalse(result["safety"]["source_code_auto_generation"])

    def test_plan_only_exposes_100_plus_1000_and_neural_council(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(
            v378.quality_review_policy, "validate", return_value=ready_policy()
        ), mock.patch.object(v378.v377, "run_cycle", return_value=sample_core()) as core:
            root = Path(td)
            policy = root / "quality_review_policy_v2.json"
            policy.write_text(json.dumps({"schema_version": 2}), encoding="utf-8")
            result = v378.run_cycle(root=root, quality_policy_path=policy, persist_outputs=False)
            core.assert_called_once()
            self.assertEqual("v378", result["controller_version"])
            self.assertEqual(100, result["quality_governance"]["preparation_senior_perspectives"])
            self.assertEqual(1000, result["quality_governance"]["review_cells"])
            self.assertEqual("HIGH", result["neural_council"]["readiness"])
            self.assertEqual("STEADY_VERIFIED_EVOLUTION", result["adaptive_mode"]["mode"])
            self.assertEqual(
                "allowlisted_declarative_capabilities_only",
                result["evolution_contract"]["runtime_self_added_functions"],
            )
            self.assertFalse(result["evolution_contract"]["market_direction_prediction"])

    def test_mutating_cycle_uses_outer_lock_and_preserves_v377_lock(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(
            v378.quality_review_policy, "validate", return_value=ready_policy()
        ), mock.patch.object(v378.v377, "run_cycle", return_value=sample_core("V376_EXECUTED")) as core:
            root = Path(td)
            policy = root / "quality_review_policy_v2.json"
            policy.write_text(json.dumps({"schema_version": 2}), encoding="utf-8")
            result = v378.run_cycle(
                execute=True,
                apply_capabilities=True,
                train_meta=True,
                apply_skills=True,
                root=root,
                quality_policy_path=policy,
                persist_outputs=False,
            )
            self.assertEqual("V378_LOCK_ACQUIRED", result["v378_single_run_lock"]["status"])
            self.assertEqual("V376_EXECUTED", result["v378_status"])
            core.assert_called_once()
            kwargs = core.call_args.kwargs
            self.assertTrue(kwargs["execute"])
            self.assertTrue(kwargs["apply_capabilities"])
            self.assertTrue(kwargs["train_meta"])
            self.assertTrue(kwargs["apply_skills"])

    def test_outer_lock_contention_is_side_effect_free(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(
            v378.quality_review_policy, "validate", return_value=ready_policy()
        ), mock.patch.object(v378.v377, "run_cycle") as core:
            root = Path(td)
            policy = root / "quality_review_policy_v2.json"
            policy.write_text(json.dumps({"schema_version": 2}), encoding="utf-8")
            lock = root / v378.LOCK_PATH.name
            fd = lock.open("a+")
            fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                result = v378.run_cycle(
                    execute=True,
                    apply_capabilities=True,
                    train_meta=True,
                    apply_skills=True,
                    root=root,
                    quality_policy_path=policy,
                    lock_path=lock,
                    persist_outputs=False,
                )
            finally:
                fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
                fd.close()
            core.assert_not_called()
            self.assertEqual("V378_CONCURRENT_AUTONOMY_HOLD", result["v378_status"])
            self.assertFalse(result["execution"]["executed"])

    def test_market_stress_changes_mode_but_never_infers_direction(self):
        result = sample_core()
        result["plan"]["market_profile"]["freshness"] = {"status": "hold"}
        mode = v378.adaptive_mode(result)
        self.assertEqual("RECOVER_FRESHNESS", mode["mode"])
        self.assertFalse(mode["market_direction_inferred"])
        self.assertTrue(mode["allowlisted_runtime_capabilities_only"])

    def test_source_feature_gaps_remain_pr_only(self):
        result = sample_core()
        result["source_feature_proposals"] = [{"proposal": "new source-level parser"}]
        quality = {"ok": True}
        council = {"readiness": "HIGH"}
        mode = {"mode": "STEADY_VERIFIED_EVOLUTION"}
        queue = v378.improvement_queue(result, quality, council, mode)
        proposal = next(row for row in queue if row["id"] == "SOURCE_LEVEL_FEATURE_GAPS")
        self.assertFalse(proposal["auto_apply"])
        self.assertTrue(proposal["pr_required"])

    def test_self_test_safety_contract(self):
        v378.self_test()
        self.assertTrue(v378.SAFETY["quality_100_senior_prep_required"])
        self.assertTrue(v378.SAFETY["quality_1000_review_cells_required"])
        self.assertFalse(v378.SAFETY["git_write"])
        self.assertFalse(v378.SAFETY["verification_bypass"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
