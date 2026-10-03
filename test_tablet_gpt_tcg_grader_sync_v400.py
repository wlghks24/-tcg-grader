import hashlib
import json
import unittest
from pathlib import Path

import tablet_autonomous_evolution_v400 as autonomy
from sync_v376_successor_test_support import assert_v400_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V400.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v400_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v400.json"
BASE_SHA = "aea7ab68f0d75c5373139141db338e9247b04770"
CANDIDATE_SHA = "78abaca8851ba0a488626bc94cc568dd454bfb1f"
LESSON_ID = "TABLET-GPT-NEURAL-POLICY-CLOSED-LOOP-V400"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TabletGptTcgGraderSyncV400Tests(unittest.TestCase):
    def test_generation_binding_digest_and_counts(self):
        c, d, r = load(CONTRACT), load(DELTA), load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V399.json", c["prior_contract"])
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v399_delta.json", c["prior_delta_snapshot"])
        self.assertEqual(BASE_SHA, d["source_main_sha"])
        self.assertEqual(BASE_SHA, r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"], digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID], r["accepted_lesson_ids"])
        self.assertEqual(92, c["prior_required_lesson_count"])
        self.assertEqual(93, c["current_required_lesson_count"])
        self.assertEqual(411, c["current_required_merge_prs"][-1])
        self.assertEqual("SYNCED_VERIFIED", r["status"])

    def test_neural_policy_closed_loop_rules_are_fail_closed(self):
        c = load(CONTRACT)
        for key in (
            "existing_v373_meta_neural_screen_policy_required",
            "meta_neural_verified_outcomes_only_required",
            "meta_neural_minimum_sample_gate_required",
            "meta_neural_feature_bias_bounded_required",
            "combined_screen_policy_bias_bounded_required",
            "verified_surface_outcome_feedback_required",
            "verified_surface_outcome_next_cycle_only_required",
            "verified_surface_outcome_causality_claim_forbidden",
            "user_behavior_tracking_for_screen_learning_forbidden",
            "screen_policy_fail_closed_required",
            "autonomous_source_code_generation_forbidden",
            "autonomous_git_write_forbidden",
            "market_direction_invention_forbidden",
        ):
            self.assertIs(c["rules"][key], True, key)
        self.assertEqual(0.06, autonomy.MAX_NEURAL_FEATURE_BIAS)
        self.assertEqual(0.04, autonomy.MAX_OUTCOME_FEATURE_BIAS)
        self.assertEqual(0.08, autonomy.MAX_COMBINED_FEATURE_BIAS)

    def test_runtime_contract_uses_existing_verified_neural_not_user_behavior(self):
        self.assertTrue(autonomy.SAFETY["meta_neural_screen_policy_enabled"])
        self.assertTrue(autonomy.SAFETY["meta_neural_screen_policy_verified_outcomes_only"])
        self.assertTrue(autonomy.SAFETY["meta_neural_screen_policy_advisory_only"])
        self.assertTrue(autonomy.SAFETY["verified_surface_outcome_feedback_enabled"])
        self.assertTrue(autonomy.SAFETY["verified_surface_outcome_feedback_no_user_behavior_tracking"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["git_write"])

    def test_candidate_exactly_covers_neural_policy_runtime_change(self):
        c = load(CONTRACT)
        candidate = c["candidate_sync"]
        self.assertEqual(BASE_SHA, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, candidate["candidate_commit"])
        self.assertEqual(["tablet_autonomous_evolution_v400.py","tablet_autonomy_dashboard_v400.js"], candidate["watched_paths"])
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        assert_v400_successor(self)

    def test_receipt_preserves_physical_and_source_boundaries(self):
        r = load(RECEIPT)
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])
        self.assertTrue(r["verification"]["device_reverification_required"])
        self.assertTrue(r["alignment_policy"]["meta_neural_verified_outcomes_only"])
        self.assertTrue(r["alignment_policy"]["verified_surface_outcome_next_cycle_only"])
        self.assertFalse(r["alignment_policy"]["user_behavior_tracking_for_screen_learning"])
        self.assertFalse(r["alignment_policy"]["source_code_auto_generation"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
