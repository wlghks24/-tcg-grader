import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import tablet_autonomous_evolution_v376 as autonomy

NOW = datetime(2026, 10, 2, 0, 30, tzinfo=timezone.utc)


def base_result():
    return {
        "plan": {
            "resources": {"status": "normal"},
            "market_profile": {
                "freshness": {"status": "fresh"},
                "entry_count": 12,
                "low_coverage_regions": [],
                "degraded_source_ratio": 0.1,
                "source_date_older_than_30d_count": 0,
            },
            "signals": {"runtime_models": {"status": "healthy", "models": {}}, "repair_neural": {"requires_attention": False}},
            "state_corruption_hold": False,
            "active_capabilities": [],
            "v374_active_capabilities": [],
            "selected_safe_learning_actions": [],
        },
        "gaps": [{"gap_id": "sync_health", "kind": "sync_health", "severity": 0.1, "confidence": 1.0}],
        "candidates": [],
        "selected_skill": None,
        "skill_state": {
            "load_status": "loaded",
            "corruption_hold": False,
            "skill_outcome_store_status": "loaded",
            "write": {"status": "SKILL_STATE_SAVED", "written": True},
            "active_count": 0,
            "pending_trial_count": 0,
            "suspended_recipes": [],
        },
        "verified_trial_outcomes": [],
        "verified_outcome_write": {"status": "NO_NEW_VERIFIED_OUTCOMES", "written": False, "count": 0},
        "meta_feedback": {
            "generated": 0,
            "write": {"status": "NO_META_FEEDBACK", "written": False, "count": 0},
            "training": {"status": "META_TRAINING_GATE_HELD", "written": False},
        },
        "skill_history": {},
        "source_feature_proposals": [],
        "safety": {},
    }


class TabletAutonomousEvolutionV376Tests(unittest.TestCase):
    def test_safety_keeps_autonomous_source_and_promotion_boundaries_closed(self):
        self.assertTrue(autonomy.SAFETY["prior_evidence_commit_required_before_new_execution"])
        self.assertTrue(autonomy.SAFETY["ambiguous_execution_retry_forbidden"])
        self.assertTrue(autonomy.SAFETY["sanitized_exchange_capsule_enabled"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_rewrite"])
        self.assertFalse(autonomy.SAFETY["arbitrary_command_execution"])
        self.assertFalse(autonomy.SAFETY["git_write"])
        self.assertFalse(autonomy.SAFETY["verification_bypass"])
        self.assertFalse(autonomy.SAFETY["price_or_grade_invention"])
        self.assertFalse(autonomy.SAFETY["market_direction_inferred"])

    def test_execute_requires_durable_skill_and_capability_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(autonomy.v375, "run_cycle", return_value=base_result()) as prior:
                result = autonomy.run_cycle(execute=True, apply_capabilities=False, apply_skills=True, root=root, now=NOW, journal_path=root / "journal.json", persist_outputs=False)
        self.assertEqual("EXECUTION_PERSISTENCE_PRECONDITION_HOLD", result["v376_status"])
        self.assertFalse(result["execution"]["executed"])
        self.assertEqual(1, prior.call_count)

    def test_corrupt_or_uncommitted_journal_blocks_automatic_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            journal = root / "journal.json"
            journal.write_text(json.dumps({
                "schema_version": autonomy.SCHEMA_VERSION,
                "controller_version": autonomy.CONTROLLER_VERSION,
                "cycle_id": "a" * 64,
                "status": "EXECUTED_UNCOMMITTED",
            }), encoding="utf-8")
            with mock.patch.object(autonomy.v375, "run_cycle", return_value=base_result()):
                result = autonomy.run_cycle(execute=True, apply_capabilities=True, apply_skills=True, root=root, now=NOW, journal_path=journal, persist_outputs=False)
        self.assertEqual("EXECUTION_RECOVERY_HOLD", result["v376_status"])
        self.assertFalse(result["execution"]["executed"])

    def test_prior_evidence_write_failure_blocks_new_action(self):
        failed = base_result()
        failed["verified_trial_outcomes"] = [{"verified": True, "evidence_ref": "trial:1"}]
        failed["verified_outcome_write"] = {"status": "SKILL_OUTCOME_WRITE_FAILED", "written": False, "count": 0}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(autonomy.v375, "run_cycle", return_value=failed), \
                 mock.patch.object(autonomy.v375.v374.v373, "load_capabilities", return_value={"status": "loaded", "capabilities": [], "corruption_hold": False}), \
                 mock.patch.object(autonomy.v375.v374.v373, "save_capabilities", return_value={"status": "CAPABILITIES_SAVED", "written": True}), \
                 mock.patch.object(autonomy.v375.v374, "execute_operational_skill") as execute_op:
                result = autonomy.run_cycle(execute=True, apply_capabilities=True, apply_skills=True, root=root, now=NOW, journal_path=root / "journal.json", persist_outputs=False)
        self.assertEqual("EVIDENCE_COMMIT_HOLD", result["v376_status"])
        execute_op.assert_not_called()

    def test_capability_corruption_is_fail_closed_before_execution(self):
        settled = base_result()
        settled["selected_skill"] = {"skill_id": "OBSERVE_ONLY:SYNC", "recipe": "OBSERVE_ONLY", "score": 70.0, "risk": 0.0, "cost": 0.0}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(autonomy.v375, "run_cycle", return_value=settled), \
                 mock.patch.object(autonomy.v375.v374.v373, "load_capabilities", return_value={"status": "corrupt", "capabilities": [], "corruption_hold": True}), \
                 mock.patch.object(autonomy.v375.v374.v373, "save_capabilities") as save_caps, \
                 mock.patch.object(autonomy.v375.v374, "execute_operational_skill") as execute_op:
                result = autonomy.run_cycle(execute=True, apply_capabilities=True, apply_skills=True, root=root, now=NOW, journal_path=root / "journal.json", persist_outputs=False)
        self.assertEqual("EVIDENCE_COMMIT_HOLD", result["v376_status"])
        save_caps.assert_not_called()
        execute_op.assert_not_called()

    def test_exchange_capsule_is_sanitized_and_digest_bound(self):
        result = base_result()
        result["selected_skill"] = {"skill_id": "OBSERVE_ONLY:SYNC", "recipe": "OBSERVE_ONLY", "v375_score": 55.0, "risk": 0.0, "cost": 0.0}
        barrier = {"ok": True, "status": "EVIDENCE_COMMIT_OK", "reasons": []}
        reliability = {"advisory_only": True, "meta_verified_samples": 8, "skill_verified_samples": 9, "covered_recipes": 3, "confidence": 0.5, "unverified_prediction_not_promoted": True}
        capsule = autonomy.build_exchange_capsule(result, cycle_id="b" * 64, journal_status="COMMITTED", barrier=barrier, reliability=reliability, now=NOW)
        self.assertFalse(capsule["exchange_policy"]["model_weights_exported"])
        self.assertFalse(capsule["exchange_policy"]["secrets_exported"])
        self.assertFalse(capsule["exchange_policy"]["raw_grading_calibration_exported"])
        digest = capsule.pop("capsule_sha256")
        self.assertEqual(digest, autonomy._canonical_digest(capsule))

    def test_successful_execution_journals_before_action_and_commits_trial_state(self):
        settled = base_result()
        settled["selected_skill"] = {"skill_id": "RECOVER_FRESHNESS:MARKET", "recipe": "RECOVER_FRESHNESS", "gap_id": "market_freshness", "score": 80.0, "risk": 0.1, "cost": 0.1}
        skill_state = autonomy.v375.v374._default_skill_state()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            journal = root / "journal.json"
            with mock.patch.object(autonomy.v375, "run_cycle", return_value=settled), \
                 mock.patch.object(autonomy.v375.v374.v373, "load_capabilities", return_value={"status": "loaded", "capabilities": [], "corruption_hold": False}), \
                 mock.patch.object(autonomy.v375.v374.v373, "save_capabilities", return_value={"status": "CAPABILITIES_SAVED", "written": True}), \
                 mock.patch.object(autonomy.v375.v374, "execute_operational_skill", return_value={"status": "OPERATIONAL_REFRESH_EXECUTED", "executed": True}), \
                 mock.patch.object(autonomy.v375.v374.v373.v372, "execute_safe_learning", return_value={"status": "NO_SAFE_LEARNING_ACTION", "results": {}}), \
                 mock.patch.object(autonomy.v375.v374, "load_skill_state", return_value={"state": skill_state, "status": "loaded", "corruption_hold": False}), \
                 mock.patch.object(autonomy.v375.v374, "save_skill_state", return_value={"status": "SKILL_STATE_SAVED", "written": True}):
                result = autonomy.run_cycle(execute=True, apply_capabilities=True, apply_skills=True, root=root, now=NOW, state_path=root / "state.json", journal_path=journal, persist_outputs=False)
            saved = json.loads(journal.read_text(encoding="utf-8"))
        self.assertEqual("V376_EXECUTED", result["v376_status"])
        self.assertEqual("COMMITTED", result["execution_journal"]["status"])
        self.assertEqual("COMMITTED", saved["status"])
        self.assertEqual(1, result["skill_state"]["pending_trial_count"])
        self.assertFalse(result["execution"]["git_write"])
        self.assertFalse(result["execution"]["source_code_modified"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
