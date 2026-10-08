from sync_v376_successor_test_support import preserve_reviewed_v525_grade_scope
import hashlib
import json
from pathlib import Path
import subprocess
import unittest

from sync_v376_successor_test_support import assert_v376_successor

import tablet_autonomous_evolution_v374 as autonomy

ROOT = Path(__file__).resolve().parent
SOURCE = "514886ebad7209abb85e891fdd5d7ddbdc8561c4"
CANDIDATE = "af47dc6e95735be99800669f57610069865efca6"
PRIOR = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v373_delta.json"
DELTA = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v374_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v374.json"
PRIOR_CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V373.json"
CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V374.json"
SUCCESSOR_CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V375.json"
EXPECTED_DIGEST = "f52e3713a2363886e4b0af707c15c12eb61f1b0a3aea41733393932d686c45ce"


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


class TabletGptTcgGraderSyncV374(unittest.TestCase):
    def _assert_v375_successor(self, relevant):
        successor = read(SUCCESSOR_CONTRACT)
        delta = read(ROOT / successor["delta_snapshot"])
        receipt = read(ROOT / successor["receiver_receipt"])
        candidate = successor["candidate_sync"]
        raw = json.dumps(delta["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.assertEqual(digest, delta["lesson_digest_sha256"])
        self.assertEqual(digest, receipt["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in delta["lessons"]], receipt["accepted_lesson_ids"])
        self.assertEqual("SYNCED_VERIFIED", receipt["status"])
        self.assertEqual("TABLET_GPT_TCG_GRADER_MATCH", receipt["verification"]["verified_result"])
        self.assertEqual(delta["source_main_sha"], receipt["source_main_sha"])
        self.assertEqual(candidate["base_main_sha"], delta["source_main_sha"])
        expected_generation = {
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V375.json",
            "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v375_delta.json",
            "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v375.json",
            "test_tablet_gpt_tcg_grader_sync_v375.py",
        }
        self.assertEqual(expected_generation, set(candidate["generation_files"]))
        self.assertTrue(expected_generation.issubset(set(successor["freshness_watch"]["exclude_paths"])))
        successor_relevant = watched_paths(successor, candidate["base_main_sha"], candidate["candidate_commit"])
        self.assertEqual(sorted(candidate["watched_paths"]), successor_relevant)
        after375 = watched_paths(successor, candidate["candidate_commit"])
        self.assertEqual(
            sorted(relevant), sorted(set(successor_relevant) | set(after375))
        )
        if after375:
            assert_v376_successor(self, after375)
        else:
            self.assertEqual([], after375)
        subprocess.run(["git", "merge-base", "--is-ancestor", candidate["base_main_sha"], "HEAD"], check=True)
        subprocess.run(["git", "merge-base", "--is-ancestor", candidate["candidate_commit"], "HEAD"], check=True)

    def test_lineage_digest_receipt_and_merge_anchor(self):
        prior, delta, receipt, pc, contract = map(
            read, (PRIOR, DELTA, RECEIPT, PRIOR_CONTRACT, CONTRACT)
        )
        self.assertEqual(prior["lesson_digest_sha256"], delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"], receipt["prior_lesson_digest_sha256"])
        self.assertEqual(SOURCE, delta["source_main_sha"])
        self.assertEqual(SOURCE, receipt["source_main_sha"])
        self.assertEqual([360], [row["pr"] for row in delta["covered_merges"]])
        self.assertEqual(SOURCE, delta["covered_merges"][0]["merge_sha"])
        self.assertEqual(set(contract["current_required_merge_prs"]), set(pc["current_required_merge_prs"]) | {360})
        self.assertEqual(pc["current_required_lesson_count"], contract["prior_required_lesson_count"])
        self.assertEqual(contract["prior_required_lesson_count"] + contract["delta_required_lesson_count"], contract["current_required_lesson_count"])
        raw = json.dumps(delta["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest_value = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.assertEqual(EXPECTED_DIGEST, digest_value)
        self.assertEqual(digest_value, delta["lesson_digest_sha256"])
        self.assertEqual(digest_value, receipt["delta_lesson_digest_sha256"])
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
        expected_watched = ["main", "tablet_autonomous_evolution_v374.py", "tablet_runtime_manifest.py"]
        self.assertEqual(expected_watched, watched_paths(contract, SOURCE, CANDIDATE))
        self.assertEqual(sorted(candidate["watched_paths"]), expected_watched)
        expected_generation = {
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V374.json",
            "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v374_delta.json",
            "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v374.json",
            "test_tablet_gpt_tcg_grader_sync_v374.py",
        }
        self.assertEqual(expected_generation, set(candidate["generation_files"]))
        self.assertTrue(expected_generation.issubset(set(contract["freshness_watch"]["exclude_paths"])))
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        relevant = watched_paths(contract, CANDIDATE)
        if relevant:
            self._assert_v375_successor(relevant)

    def test_closed_loop_order_and_safety_remain_fail_closed(self):
        rules = read(CONTRACT)["rules"]
        required = (
            "closed_loop_prior_trials_must_be_evaluated_before_next_selection",
            "closed_loop_multi_candidate_scoring_required",
            "closed_loop_one_runtime_skill_per_cycle",
            "closed_loop_max_one_heavy_operation_per_cycle",
            "closed_loop_verified_skill_outcomes_only",
            "closed_loop_negative_history_must_suspend_recipe",
            "closed_loop_pending_trial_causal_overlap_forbidden",
            "declarative_skill_allowlisted_primitives_only",
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
        self.assertTrue(safety["closed_loop_candidate_generation"])
        self.assertTrue(safety["multi_candidate_scoring"])
        self.assertTrue(safety["verified_skill_outcome_learning_only"])
        self.assertTrue(safety["negative_history_auto_suspends_skill"])
        self.assertEqual(1, safety["max_heavy_operations_per_cycle"])
        self.assertFalse(safety["source_code_auto_generation"])
        self.assertFalse(safety["source_code_auto_rewrite"])
        self.assertFalse(safety["arbitrary_command_execution"])
        self.assertFalse(safety["git_write"])
        self.assertFalse(safety["verification_bypass"])
        self.assertFalse(safety["trust_or_fact_auto_promotion"])
        self.assertFalse(safety["price_or_grade_invention"])
        self.assertFalse(safety["market_direction_inferred"])

        source = (ROOT / "tablet_autonomous_evolution_v374.py").read_text(encoding="utf-8")
        run = source[source.index("def run_cycle("):]
        self.assertLess(run.index("reconcile_skill_state("), run.index("generate_candidates("))
        self.assertLess(run.index("generate_candidates("), run.index("select_candidate("))

        main_text = (ROOT / "main").read_text(encoding="utf-8")
        manifest_text = (ROOT / "tablet_runtime_manifest.py").read_text(encoding="utf-8")
        ignore_text = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("python tablet_autonomous_evolution_v", main_text)
        self.assertIn("--execute-safe-learning --apply-capabilities --train-meta --apply-skills", main_text)
        self.assertIn('"tablet_autonomous_evolution_v374.py"', manifest_text)
        for name in (
            "tablet_autonomy_skills_v374.json",
            "tablet_autonomy_verified_skill_outcomes_v374.jsonl",
            "tablet_autonomy_source_feature_proposals_v374.json",
            "tablet_autonomy_v374_report.json",
        ):
            self.assertIn(name, ignore_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
