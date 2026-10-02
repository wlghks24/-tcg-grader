import hashlib
import json
import unittest
from pathlib import Path

import tablet_autonomous_evolution_v387 as autonomy
from sync_v376_successor_test_support import assert_v386_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V386.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v386_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v386.json"
BASE_SHA = "67e656cd5f2e159b156292e3f597f79fbd4e2033"
CANDIDATE_SHA = "ea265236e81a19101a08906989f624511ab823ff"
LESSON_ID = "TABLET-GPT-TCG-GRADER-UNCERTAINTY-AWARE-MUTUAL-AUTONOMY-V387"
EXPECTED_WATCHED = ["main", "tablet_autonomous_evolution_v387.py", "tablet_runtime_manifest.py"]


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TabletGptTcgGraderSyncV386Tests(unittest.TestCase):
    def test_generation_binding_digest_and_counts(self):
        c, d, r = load(CONTRACT), load(DELTA), load(RECEIPT)
        self.assertEqual(
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V385.json",
            c["prior_contract"],
        )
        self.assertEqual(
            "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v385_delta.json",
            c["prior_delta_snapshot"],
        )
        self.assertEqual(BASE_SHA, d["source_main_sha"])
        self.assertEqual(BASE_SHA, r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"], digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID], r["accepted_lesson_ids"])
        self.assertEqual(78, c["prior_required_lesson_count"])
        self.assertEqual(79, c["current_required_lesson_count"])
        self.assertEqual(383, c["current_required_merge_prs"][-1])
        self.assertEqual("SYNCED_VERIFIED", r["status"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])

    def test_v387_rules_preserve_uncertainty_aware_fail_closed_autonomy(self):
        c = load(CONTRACT)
        for key in (
            "uncertainty_aware_action_selection_required",
            "verified_sample_confidence_required",
            "mutual_uncertainty_calibration_required",
            "operational_regime_transition_hold_required",
            "low_confidence_revalidation_required",
            "unstable_regime_recovery_only_required",
            "feature_shadow_canary_active_candidate_rollback_required",
            "source_level_activation_protected_pr_ci_required",
            "v386_gate_cannot_be_bypassed",
            "autonomous_source_code_generation_forbidden",
            "autonomous_git_write_forbidden",
            "autonomous_verification_bypass_forbidden",
            "market_direction_invention_forbidden",
        ):
            self.assertIs(c["rules"][key], True, key)

        self.assertTrue(autonomy.SAFETY["uncertainty_aware_action_selection"])
        self.assertTrue(autonomy.SAFETY["multi_objective_verified_governor"])
        self.assertTrue(autonomy.SAFETY["feature_shadow_canary_active_candidate_rollback"])
        self.assertFalse(autonomy.SAFETY["peer_model_weights_imported"])
        self.assertFalse(autonomy.SAFETY["peer_raw_state_imported"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_rewrite"])
        self.assertFalse(autonomy.SAFETY["arbitrary_command_execution"])
        self.assertFalse(autonomy.SAFETY["git_write"])
        self.assertFalse(autonomy.SAFETY["market_direction_inferred"])

    def test_candidate_exactly_covers_current_v387_route(self):
        c = load(CONTRACT)
        candidate = c["candidate_sync"]
        self.assertEqual(BASE_SHA, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, candidate["candidate_commit"])
        self.assertEqual(EXPECTED_WATCHED, candidate["watched_paths"])
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        assert_v386_successor(self)

    def test_main_and_runtime_manifest_use_v387(self):
        main = (ROOT / "main").read_text(encoding="utf-8")
        manifest = (ROOT / "tablet_runtime_manifest.py").read_text(encoding="utf-8")
        self.assertIn(
            "tablet_autonomous_evolution_v387.py --domain tablet_gpt --execute-safe-learning --apply-capabilities --train-meta --apply-skills",
            main,
        )
        for version in ("v387", "v386", "v385", "v382", "v381", "v380", "v379", "v378", "v377", "v376"):
            self.assertIn(f'"tablet_autonomous_evolution_{version}.py"', manifest)

    def test_exchange_contract_never_claims_physical_device_success(self):
        r = load(RECEIPT)
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])
        self.assertTrue(r["verification"]["device_reverification_required"])
        self.assertTrue(r["alignment_policy"]["peer_model_weights_import_forbidden"])
        self.assertTrue(r["alignment_policy"]["peer_raw_state_import_forbidden"])
        self.assertTrue(r["alignment_policy"]["uncertainty_confidence_gate_required"])
        self.assertTrue(r["alignment_policy"]["unstable_regime_recovery_only_required"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
