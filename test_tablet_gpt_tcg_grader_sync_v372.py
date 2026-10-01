import hashlib
import json
import re
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parent
SOURCE = "a00ebfd3888740ee50c5e86c8ee6008fe8a54908"
CANDIDATE = "7df0b331aa45c2ca2d3c08cc893e2950df1e8557"
PRIOR = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v370_delta.json"
DELTA = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v372_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v372.json"
PRIOR_CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V370.json"
CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V372.json"
AUTONOMY = ROOT / "tablet_autonomy_engine.py"
UPDATER = ROOT / "auto_update_all.py"
EXPECTED_DIGEST = "97a5960b857bd52ad630097158a3c3492cf52f06fa40af77d6eca22317020340"


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


class TabletGptTcgGraderSyncV372(unittest.TestCase):
    def test_lineage_digest_receipt_and_safe_transfer_boundary(self):
        prior, delta, receipt, pc, contract = map(
            read, (PRIOR, DELTA, RECEIPT, PRIOR_CONTRACT, CONTRACT)
        )
        self.assertEqual(prior["lesson_digest_sha256"], delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"], receipt["prior_lesson_digest_sha256"])
        self.assertEqual(SOURCE, delta["source_main_sha"])
        self.assertEqual(SOURCE, receipt["source_main_sha"])
        self.assertEqual([355], [row["pr"] for row in delta["covered_merges"]])
        self.assertEqual(SOURCE, delta["covered_merges"][0]["merge_sha"])
        self.assertEqual(
            set(contract["current_required_merge_prs"]),
            set(pc["current_required_merge_prs"]) | {355},
        )
        self.assertEqual(pc["current_required_lesson_count"], contract["prior_required_lesson_count"])
        self.assertEqual(
            contract["prior_required_lesson_count"] + contract["delta_required_lesson_count"],
            contract["current_required_lesson_count"],
        )
        raw = json.dumps(delta["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.assertEqual(EXPECTED_DIGEST, digest)
        self.assertEqual(digest, delta["lesson_digest_sha256"])
        self.assertEqual(digest, receipt["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in delta["lessons"]], receipt["accepted_lesson_ids"])
        self.assertEqual("SYNCED_VERIFIED", receipt["status"])
        self.assertEqual("TABLET_GPT_TCG_GRADER_MATCH", receipt["verification"]["verified_result"])
        self.assertFalse(delta["share_policy"]["chatgpt_model_weights_exported"])
        self.assertFalse(delta["share_policy"]["raw_grading_calibration_shared"])
        self.assertFalse(delta["share_policy"]["device_local_runtime_memory_overwritten"])
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])
        for sha in (SOURCE, CANDIDATE):
            subprocess.run(["git", "merge-base", "--is-ancestor", sha, "HEAD"], check=True)

    def test_exact_candidate_scope_and_complete_generation(self):
        contract = read(CONTRACT)
        candidate = contract["candidate_sync"]
        self.assertEqual(SOURCE, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE, candidate["candidate_commit"])
        expected_watched = [
            ".github/workflows/tablet-autonomy-guard.yml",
            "tablet_autonomy_engine.py",
            "tablet_runtime_manifest.py",
            "verified_autonomy_neural.py",
            "verify_current_runtime.py",
        ]
        self.assertEqual(expected_watched, watched_paths(contract, SOURCE, CANDIDATE))
        self.assertEqual(expected_watched, sorted(candidate["watched_paths"]))
        expected_generation = {
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V372.json",
            "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v372_delta.json",
            "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v372.json",
            "test_tablet_gpt_tcg_grader_sync_v372.py",
        }
        self.assertEqual(expected_generation, set(candidate["generation_files"]))
        self.assertTrue(expected_generation.issubset(set(contract["freshness_watch"]["exclude_paths"])))
        for path in expected_generation:
            self.assertTrue((ROOT / path).is_file(), path)
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        self.assertEqual([], watched_paths(contract, CANDIDATE), "v372 successor has uncovered watched changes")

    def test_autonomy_safety_rules_are_explicit_and_fail_closed(self):
        rules = read(CONTRACT)["rules"]
        required_true = (
            "autonomy_verified_learning_only_required",
            "autonomy_unverified_learning_forbidden",
            "autonomy_source_code_auto_rewrite_forbidden",
            "autonomy_git_write_forbidden",
            "autonomy_market_fact_generation_forbidden",
            "autonomy_official_trust_auto_promotion_forbidden",
            "autonomy_candidate_database_auto_promotion_forbidden",
            "autonomy_mandatory_collector_skip_forbidden",
            "autonomy_capability_proposals_require_pr",
            "autonomy_stale_or_future_model_priority_forbidden",
            "autonomy_market_priority_boost_bounded",
            "required_checks_must_succeed_before_merge",
            "direct_main_push_forbidden",
            "force_or_admin_bypass_forbidden",
        )
        for key in required_true:
            self.assertIs(rules[key], True, key)

        autonomy = AUTONOMY.read_text(encoding="utf-8")
        updater = UPDATER.read_text(encoding="utf-8")
        self.assertIn('"source_code_auto_rewrite": False', autonomy)
        self.assertIn('"git_write": False', autonomy)
        self.assertIn('"mandatory_collectors_preserved": True', autonomy)
        self.assertIn('"new_executable_capability_requires_pr": True', autonomy)
        self.assertIn('MAX_MARKET_PRIORITY_BOOST = 0.15', autonomy)
        self.assertIn('MAX_EXPLORATION_PRIORITY_BOOST = 0.10', autonomy)
        self.assertIn('"implementation_mode": "pr_required"', autonomy)
        self.assertIn('"executable": False', autonomy)
        self.assertIn('jobs = _ordered_jobs(jobs,stats,autonomy_state)', updater)
        self.assertNotIn("git push", autonomy)


if __name__ == "__main__":
    unittest.main(verbosity=2)
