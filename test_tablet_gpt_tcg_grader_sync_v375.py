import hashlib
import json
from pathlib import Path
import subprocess
import unittest

from sync_v376_successor_test_support import assert_current_autonomy_route_v377

import tablet_autonomous_evolution_v375 as autonomy

ROOT = Path(__file__).resolve().parent
SOURCE = "2b1112318fa23f4e8edd525695ee3711ea715e18"
CANDIDATE = "d7c8577b514abdbbc15ba9323c4c0deb1945efed"
PRIOR = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v374_delta.json"
DELTA = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v375_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v375.json"
PRIOR_CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V374.json"
CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V375.json"
SUCCESSOR_CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V376.json"
SUCCESSOR_DELTA = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v376_delta.json"
SUCCESSOR_RECEIPT = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v376.json"
SUCCESSOR_TEST = ROOT / "test_tablet_gpt_tcg_grader_sync_v376.py"
EXPECTED_DIGEST = "7b6bd4191984bc6582121fa79518ebf6f5513f09a9b68454fad2e8115abf38c4"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def watched_paths(contract, source, head="HEAD"):
    watch = contract["freshness_watch"]
    exact = set(watch["exact_paths"])
    prefixes = tuple(watch["path_prefixes"])
    excluded = set(watch["exclude_paths"])
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", f"{source}..{head}"], text=True
    ).splitlines()
    return sorted(
        path for path in changed
        if path not in excluded and (path in exact or path.startswith(prefixes))
    )


def complete_v376_successor():
    files = (SUCCESSOR_CONTRACT, SUCCESSOR_DELTA, SUCCESSOR_RECEIPT, SUCCESSOR_TEST)
    if any(not path.is_file() for path in files):
        return False
    contract, delta, receipt = map(read, (SUCCESSOR_CONTRACT, SUCCESSOR_DELTA, SUCCESSOR_RECEIPT))
    if contract.get("prior_contract") != "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V375.json":
        return False
    if contract.get("prior_delta_snapshot") != "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v375_delta.json":
        return False
    if contract.get("verification_test") != "test_tablet_gpt_tcg_grader_sync_v376.py":
        return False
    if delta.get("prior_delta") != "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v375_delta.json":
        return False
    if delta.get("source_main_sha") != receipt.get("source_main_sha"):
        return False
    if delta.get("lesson_digest_sha256") != receipt.get("delta_lesson_digest_sha256"):
        return False
    raw = json.dumps(delta.get("lessons"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if hashlib.sha256(raw.encode("utf-8")).hexdigest() != delta.get("lesson_digest_sha256"):
        return False
    if [row.get("lesson_id") for row in delta.get("lessons", [])] != receipt.get("accepted_lesson_ids"):
        return False
    if receipt.get("status") != "SYNCED_VERIFIED":
        return False
    if receipt.get("verification", {}).get("verified_result") != "TABLET_GPT_TCG_GRADER_MATCH":
        return False
    candidate = contract.get("candidate_sync") or {}
    base = str(candidate.get("base_main_sha") or "")
    functional = str(candidate.get("candidate_commit") or "")
    if not base or not functional or candidate.get("requires_exact_watched_path_match") is not True:
        return False
    try:
        subprocess.run(["git", "merge-base", "--is-ancestor", CANDIDATE, base], check=True)
        subprocess.run(["git", "merge-base", "--is-ancestor", base, "HEAD"], check=True)
        subprocess.run(["git", "merge-base", "--is-ancestor", functional, "HEAD"], check=True)
    except subprocess.CalledProcessError:
        return False
    return True


class TabletGptTcgGraderSyncV375(unittest.TestCase):
    def test_lineage_digest_receipt_and_merge_anchor(self):
        prior, delta, receipt, pc, contract = map(
            read, (PRIOR, DELTA, RECEIPT, PRIOR_CONTRACT, CONTRACT)
        )
        self.assertEqual(prior["lesson_digest_sha256"], delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"], receipt["prior_lesson_digest_sha256"])
        self.assertEqual(SOURCE, delta["source_main_sha"])
        self.assertEqual(SOURCE, receipt["source_main_sha"])
        self.assertEqual([361], [row["pr"] for row in delta["covered_merges"]])
        self.assertEqual(SOURCE, delta["covered_merges"][0]["merge_sha"])
        self.assertEqual(
            set(contract["current_required_merge_prs"]),
            set(pc["current_required_merge_prs"]) | {361},
        )
        self.assertEqual(pc["current_required_lesson_count"], contract["prior_required_lesson_count"])
        self.assertEqual(
            contract["prior_required_lesson_count"] + contract["delta_required_lesson_count"],
            contract["current_required_lesson_count"],
        )
        raw = json.dumps(delta["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        value = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.assertEqual(EXPECTED_DIGEST, value)
        self.assertEqual(value, delta["lesson_digest_sha256"])
        self.assertEqual(value, receipt["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in delta["lessons"]], receipt["accepted_lesson_ids"])
        self.assertEqual("SYNCED_VERIFIED", receipt["status"])
        self.assertEqual("TABLET_GPT_TCG_GRADER_MATCH", receipt["verification"]["verified_result"])
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])
        subprocess.run(["git", "merge-base", "--is-ancestor", SOURCE, "HEAD"], check=True)
        subprocess.run(["git", "merge-base", "--is-ancestor", CANDIDATE, "HEAD"], check=True)

    def test_exact_candidate_scope_and_complete_generation(self):
        contract = read(CONTRACT)
        candidate = contract["candidate_sync"]
        self.assertEqual(SOURCE, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE, candidate["candidate_commit"])
        expected_watched = ["main", "tablet_autonomous_evolution_v375.py", "tablet_runtime_manifest.py"]
        self.assertEqual(expected_watched, watched_paths(contract, SOURCE, CANDIDATE))
        self.assertEqual(sorted(candidate["watched_paths"]), expected_watched)
        expected_generation = {
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V375.json",
            "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v375_delta.json",
            "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v375.json",
            "test_tablet_gpt_tcg_grader_sync_v375.py",
        }
        self.assertEqual(expected_generation, set(candidate["generation_files"]))
        self.assertTrue(expected_generation.issubset(set(contract["freshness_watch"]["exclude_paths"])))
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        remaining = watched_paths(contract, CANDIDATE)
        if remaining:
            self.assertTrue(complete_v376_successor(), f"uncovered v375 watched changes: {remaining}")
        else:
            self.assertEqual([], remaining)

    def test_verified_feedback_uncertainty_and_fail_closed_safety(self):
        rules = read(CONTRACT)["rules"]
        required = (
            "closed_loop_prior_trials_must_be_evaluated_before_next_selection",
            "closed_loop_one_runtime_skill_per_cycle",
            "closed_loop_max_one_heavy_operation_per_cycle",
            "verified_skill_outcomes_may_feed_meta_neural_only_with_exact_trial_features",
            "skill_outcome_corruption_must_fail_closed",
            "meta_outcome_corruption_must_fail_closed",
            "candidate_uncertainty_exploration_must_be_bounded",
            "verified_failure_penalty_must_be_bounded",
            "three_consecutive_verified_negative_outcomes_hard_hold_recipe",
            "cross_gap_capability_composition_allowlisted_only",
            "source_level_gap_auto_implementation_forbidden",
            "source_level_gap_requires_normal_pr_ci",
            "autonomous_source_code_generation_forbidden",
            "autonomous_source_code_rewrite_forbidden",
            "autonomous_arbitrary_command_execution_forbidden",
            "autonomous_git_write_forbidden",
            "autonomous_verification_bypass_forbidden",
            "autonomous_trust_or_fact_promotion_forbidden",
            "autonomous_price_or_grade_invention_forbidden",
            "required_checks_must_succeed_before_merge",
            "direct_main_push_forbidden",
            "force_or_admin_bypass_forbidden",
        )
        for key in required:
            self.assertIs(rules[key], True, key)

        safety = autonomy.SAFETY
        self.assertTrue(safety["verified_skill_outcomes_feed_meta_neural"])
        self.assertTrue(safety["skill_outcome_corruption_is_hold"])
        self.assertTrue(safety["meta_outcome_corruption_is_hold"])
        self.assertTrue(safety["uncertainty_aware_candidate_selection"])
        self.assertTrue(safety["cross_gap_declarative_capability_composition"])
        self.assertEqual(3, safety["negative_streak_hard_hold"])
        self.assertFalse(safety["source_code_auto_generation"])
        self.assertFalse(safety["source_code_auto_rewrite"])
        self.assertFalse(safety["arbitrary_command_execution"])
        self.assertFalse(safety["git_write"])
        self.assertFalse(safety["verification_bypass"])
        self.assertFalse(safety["trust_or_fact_auto_promotion"])
        self.assertFalse(safety["price_or_grade_invention"])
        self.assertFalse(safety["market_direction_inferred"])

        main_text = (ROOT / "main").read_text(encoding="utf-8")
        manifest_text = (ROOT / "tablet_runtime_manifest.py").read_text(encoding="utf-8")
        if "tablet_autonomous_evolution_v375.py --execute-safe-learning --apply-capabilities --train-meta --apply-skills" in main_text:
            self.assertIn('"tablet_autonomous_evolution_v375.py"', manifest_text)
        else:
            self.assertTrue(complete_v376_successor())
            assert_current_autonomy_route_v377(self, main_text, manifest_text)
            self.assertIn('"tablet_autonomous_evolution_v375.py"', manifest_text)
        self.assertIn('"tablet_autonomous_evolution_v374.py"', manifest_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
