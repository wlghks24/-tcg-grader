import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V376.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v376_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v376.json"
BASE_SHA = "d2813d753a2c5babcc014d3e8a28374fadd887bb"
CANDIDATE_SHA = "372e8fb1f1c546120fb49db3fea52d59129319ca"
LESSON_ID = "TABLET-GPT-TRANSACTIONAL-AUTONOMOUS-EVOLUTION-V376"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class TabletGptTcgGraderSyncV376Tests(unittest.TestCase):
    def test_generation_files_bind_same_delta_and_receipt(self):
        contract = load(CONTRACT)
        delta = load(DELTA)
        receipt = load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v376_delta.json", contract["delta_snapshot"])
        self.assertEqual("TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v376.json", contract["receiver_receipt"])
        self.assertEqual(BASE_SHA, delta["source_main_sha"])
        self.assertEqual(BASE_SHA, receipt["source_main_sha"])
        self.assertEqual(delta["lesson_digest_sha256"], receipt["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID], receipt["accepted_lesson_ids"])
        self.assertEqual(1, len(delta["lessons"]))
        self.assertEqual(LESSON_ID, delta["lessons"][0]["lesson_id"])
        self.assertEqual(delta["lesson_digest_sha256"], digest(delta["lessons"][0]))
        self.assertEqual("SYNCED_VERIFIED", receipt["status"])
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])

    def test_contract_preserves_fail_closed_autonomy_boundaries(self):
        contract = load(CONTRACT)
        rules = contract["rules"]
        required_true = [
            "prior_evidence_commit_required_before_new_execution",
            "meta_feedback_requires_skill_evidence_commit",
            "execution_requires_skill_state_persistence",
            "execution_requires_capability_persistence",
            "ambiguous_execution_retry_forbidden",
            "execution_journal_fail_closed",
            "sanitized_exchange_capsule_required",
            "autonomous_learning_allowlisted_only",
            "existing_verified_model_training_gates_must_remain_enforced",
            "neural_models_remain_advisory",
            "source_level_gap_requires_normal_pr_ci",
            "autonomous_source_code_generation_forbidden",
            "autonomous_source_code_rewrite_forbidden",
            "autonomous_arbitrary_command_execution_forbidden",
            "autonomous_git_write_forbidden",
            "autonomous_verification_bypass_forbidden",
            "autonomous_trust_or_fact_promotion_forbidden",
            "autonomous_price_or_grade_invention_forbidden",
            "market_direction_invention_forbidden",
            "physical_tablet_and_drive_results_must_not_be_invented",
        ]
        for key in required_true:
            self.assertIs(rules[key], True, key)
        self.assertEqual(68, contract["prior_required_lesson_count"])
        self.assertEqual(1, contract["delta_required_lesson_count"])
        self.assertEqual(69, contract["current_required_lesson_count"])
        self.assertEqual(362, contract["current_required_merge_prs"][-1])

    def test_candidate_binding_covers_exact_watched_runtime_changes(self):
        contract = load(CONTRACT)
        candidate = contract["candidate_sync"]
        self.assertEqual(BASE_SHA, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, candidate["candidate_commit"])
        self.assertEqual(
            ["main", "tablet_autonomous_evolution_v376.py", "tablet_runtime_manifest.py"],
            candidate["watched_paths"],
        )
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])

    def test_runtime_route_manifest_and_local_evidence_policy_use_v376(self):
        main = (ROOT / "main").read_text(encoding="utf-8")
        runtime = (ROOT / "tablet_runtime_manifest.py").read_text(encoding="utf-8")
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        controller = (ROOT / "tablet_autonomous_evolution_v376.py").read_text(encoding="utf-8")
        self.assertIn("tablet_autonomous_evolution_v376.py --execute-safe-learning --apply-capabilities --train-meta --apply-skills", main)
        self.assertIn('"tablet_autonomous_evolution_v376.py"', runtime)
        self.assertIn("tablet_autonomy_execution_journal_v376.json", ignore)
        self.assertIn("tablet_autonomy_exchange_capsule_v376.json", ignore)
        self.assertIn("prior_evidence_commit_required_before_new_execution", controller)
        self.assertIn("ambiguous_execution_retry_forbidden", controller)
        self.assertIn("CAPABILITY_CORRUPTION_HOLD", controller)
        self.assertIn("EXECUTED_UNCOMMITTED", controller)


if __name__ == "__main__":
    unittest.main(verbosity=2)
