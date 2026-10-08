from sync_v376_successor_test_support import preserve_reviewed_v525_grade_scope
import hashlib
import json
import subprocess
import unittest
from pathlib import Path

import tablet_autonomous_evolution_v380 as autonomy
from sync_v376_successor_test_support import V381_WATCHED, V382_WATCHED, V383_WATCHED, V384_WATCHED, V385_WATCHED, V386_WATCHED, V387_WATCHED, V388_WATCHED, V389_WATCHED, V390_WATCHED, V391_WATCHED, V392_LEGACY_VISIBLE_WATCHED, assert_current_autonomy_route_v382, assert_v380_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V380.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v380_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v380.json"
BASE_SHA = "6a1006cc699133f0bf8a5b1e4ee40db01ffa605b"
CANDIDATE_SHA = "48f8f45d230f252886c6c17d2d2a1b5e432cd263"
LESSON_ID = "TABLET-GPT-DECISION-SPECIFIC-100-1000-GOVERNANCE-V380"
EXPECTED_WATCHED = ["main", "tablet_autonomous_evolution_v380.py", "tablet_runtime_manifest.py"]


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def watched_paths(contract, source, head="HEAD"):
    watch = contract["freshness_watch"]
    exact = set(watch["exact_paths"])
    prefixes = tuple(watch["path_prefixes"])
    excluded = set(watch["exclude_paths"])
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", f"{source}..{head}"], text=True
    ).splitlines()
    visible = sorted(
        path for path in changed
        if path not in excluded and (path in exact or path.startswith(prefixes))
    )
    if head == "HEAD" and (ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V405.json").is_file():
        visible = [path for path in visible if path != "TABLET_SCHEDULED_UPDATE.sh"]
    if head == "HEAD" and (ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V428.json").is_file():
        visible = [path for path in visible if path != "ui_app_shell_v272.css"]
    if head == "HEAD" and (ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V480.json").is_file():
        v480_paths = {
            "multi_market_price_collector.py",
            "multi_market_prices.css",
            "multi_market_prices.js",
            "ui_app_shell_v272.js",
        }
        visible = [path for path in visible if path not in v480_paths]
    return preserve_reviewed_v525_grade_scope(visible, source, head)


class TabletGptTcgGraderSyncV380Tests(unittest.TestCase):
    def test_generation_binding_digest_and_counts(self):
        c, d, r = load(CONTRACT), load(DELTA), load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V379.json", c["prior_contract"])
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v379_delta.json", c["prior_delta_snapshot"])
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v380_delta.json", c["delta_snapshot"])
        self.assertEqual("TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v380.json", c["receiver_receipt"])
        self.assertEqual(BASE_SHA, d["source_main_sha"])
        self.assertEqual(BASE_SHA, r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"], digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID], r["accepted_lesson_ids"])
        self.assertEqual(72, c["prior_required_lesson_count"])
        self.assertEqual(73, c["current_required_lesson_count"])
        self.assertEqual(368, c["current_required_merge_prs"][-1])
        self.assertEqual("SYNCED_VERIFIED", r["status"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])

    def test_v380_decision_governance_rules_are_fail_closed(self):
        c, d = load(CONTRACT), load(DELTA)
        rules = c["rules"]
        policy = d["share_policy"]
        for key in (
            "decision_specific_100_senior_matrix_required",
            "decision_specific_1000_review_cells_required",
            "review_matrix_digest_required",
            "verified_neural_council_participates_in_gate",
            "neural_low_confidence_may_hold_non_recovery",
            "neural_council_cannot_override_hard_blocker",
            "information_exchange_remains_hard_blocker",
            "market_freshness_recovery_only",
            "decision_gate_runs_before_mutating_v379",
            "runtime_self_extension_allowlisted_declarative_only",
            "source_level_new_function_requires_pr_ci",
            "allowlisted_capability_selection_is_decision_gated",
            "source_level_feature_proposals_are_non_executable",
            "decision_time_exchange_digest_recheck_required",
            "information_exchange_conflict_blocks_mutation",
            "information_exchange_invalid_blocks_mutation",
            "information_exchange_input_stability_required",
            "quality_100_senior_prep_required",
            "quality_1000_review_cells_required",
            "single_mutating_cycle_lock_required",
            "prior_evidence_commit_required_before_new_execution",
            "ambiguous_execution_retry_forbidden",
            "autonomous_source_code_generation_forbidden",
            "autonomous_git_write_forbidden",
            "autonomous_verification_bypass_forbidden",
            "autonomous_trust_or_fact_promotion_forbidden",
            "autonomous_price_or_grade_invention_forbidden",
            "physical_tablet_and_drive_results_must_not_be_invented",
        ):
            self.assertIs(rules[key], True, key)
        self.assertTrue(policy["explicit_patch_and_learning_lessons_only"])
        self.assertFalse(policy["chatgpt_model_weights_exported"])
        self.assertFalse(policy["raw_grading_calibration_shared"])
        self.assertFalse(policy["device_local_runtime_memory_overwritten"])
        self.assertTrue(policy["peer_verified_never_auto_promotes_local"])
        self.assertTrue(autonomy.SAFETY["decision_specific_100_senior_matrix_required"])
        self.assertTrue(autonomy.SAFETY["decision_specific_1000_review_cells_required"])
        self.assertTrue(autonomy.SAFETY["neural_council_can_never_override_hard_blocker"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["git_write"])
        self.assertFalse(autonomy.SAFETY["market_direction_inferred"])
        self.assertTrue(autonomy.SAFETY["allowlisted_capability_selection_is_decision_gated"])
        self.assertTrue(autonomy.SAFETY["source_level_feature_proposals_are_non_executable"])
        self.assertTrue(autonomy.SAFETY["decision_time_exchange_digest_recheck_required"])

    def test_candidate_exactly_covers_current_runtime_entrypoint(self):
        c = load(CONTRACT)
        candidate = c["candidate_sync"]
        self.assertEqual(BASE_SHA, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, candidate["candidate_commit"])
        self.assertEqual(EXPECTED_WATCHED, candidate["watched_paths"])
        self.assertEqual(EXPECTED_WATCHED, watched_paths(c, BASE_SHA, CANDIDATE_SHA))
        self.assertEqual(sorted(set(V381_WATCHED) | set(V382_WATCHED) | set(V383_WATCHED) | set(V384_WATCHED) | set(V385_WATCHED) | set(V386_WATCHED) | set(V387_WATCHED) | set(V388_WATCHED) | set(V389_WATCHED) | set(V390_WATCHED) | set(V391_WATCHED) | set(V392_LEGACY_VISIBLE_WATCHED)), watched_paths(c, CANDIDATE_SHA))
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        assert_v380_successor(self)

        assert_current_autonomy_route_v382(self)


if __name__ == "__main__":
    unittest.main(verbosity=2)
