import hashlib
import json
import subprocess
import unittest
from pathlib import Path

import tablet_autonomous_evolution_v378 as autonomy

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V378.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v378_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v378.json"
BASE_SHA = "e318e7995eb35363256901197413f34aea4facb1"
CANDIDATE_SHA = "03cd6a1a66baef13697ca9b6614bb8510a50c3fd"
LESSON_ID = "TABLET-GPT-100-1000-QUALITY-GOVERNOR-V378"
EXPECTED_WATCHED = ["main", "tablet_autonomous_evolution_v378.py", "tablet_runtime_manifest.py"]


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


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


class TabletGptTcgGraderSyncV378Tests(unittest.TestCase):
    def test_generation_binding_and_digest(self):
        c, d, r = load(CONTRACT), load(DELTA), load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V377.json", c["prior_contract"])
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v377_delta.json", c["prior_delta_snapshot"])
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v378_delta.json", c["delta_snapshot"])
        self.assertEqual("TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v378.json", c["receiver_receipt"])
        self.assertEqual(BASE_SHA, d["source_main_sha"])
        self.assertEqual(BASE_SHA, r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"], digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID], r["accepted_lesson_ids"])
        self.assertEqual("SYNCED_VERIFIED", r["status"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])

    def test_100_1000_and_safety_rules_are_fail_closed(self):
        c = load(CONTRACT)
        rules = c["rules"]
        for key in (
            "hundred_senior_prep_required_before_mutating_autonomy",
            "thousand_review_cells_required_before_mutating_autonomy",
            "hard_blocker_cannot_be_outvoted",
            "quality_governor_may_hold_but_never_bypass",
            "declarative_self_added_functions_allowlisted_only",
            "source_level_gap_requires_normal_pr_ci",
            "existing_verified_model_training_gates_must_remain_enforced",
            "neural_models_remain_advisory",
            "single_mutating_cycle_lock_required",
            "concurrent_mutating_cycle_fail_closed",
            "autonomous_source_code_generation_forbidden",
            "autonomous_git_write_forbidden",
            "autonomous_verification_bypass_forbidden",
            "autonomous_trust_or_fact_promotion_forbidden",
            "autonomous_price_or_grade_invention_forbidden",
            "physical_tablet_and_drive_results_must_not_be_invented",
        ):
            self.assertIs(rules[key], True, key)
        self.assertEqual(70, c["prior_required_lesson_count"])
        self.assertEqual(71, c["current_required_lesson_count"])
        self.assertEqual(365, c["current_required_merge_prs"][-1])
        self.assertEqual(100, autonomy.SAFETY["hundred_senior_prep_perspectives_required"])
        self.assertEqual(1000, autonomy.SAFETY["thousand_review_cells_required"])
        self.assertTrue(autonomy.SAFETY["hard_blocker_cannot_be_outvoted"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["git_write"])

    def test_candidate_exactly_covers_supported_runtime_entrypoint(self):
        contract = load(CONTRACT)
        candidate = contract["candidate_sync"]
        self.assertEqual(BASE_SHA, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, candidate["candidate_commit"])
        self.assertEqual(EXPECTED_WATCHED, candidate["watched_paths"])
        self.assertEqual(EXPECTED_WATCHED, watched_paths(contract, BASE_SHA, CANDIDATE_SHA))
        self.assertEqual([], watched_paths(contract, CANDIDATE_SHA))
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])

        generation = {
            CONTRACT.relative_to(ROOT).as_posix(),
            contract["delta_snapshot"],
            contract["receiver_receipt"],
            contract["verification_test"],
        }
        self.assertEqual(generation, set(candidate["generation_files"]))
        self.assertTrue(generation.issubset(set(contract["freshness_watch"]["exclude_paths"])))

        main = (ROOT / "main").read_text(encoding="utf-8")
        manifest = (ROOT / "tablet_runtime_manifest.py").read_text(encoding="utf-8")
        self.assertIn(
            "tablet_autonomous_evolution_v378.py --execute-safe-learning --apply-capabilities --train-meta --apply-skills",
            main,
        )
        self.assertIn('"tablet_autonomous_evolution_v378.py"', manifest)
        self.assertIn('"tablet_autonomous_evolution_v377.py"', manifest)
        self.assertIn('"tablet_autonomous_evolution_v376.py"', manifest)

    def test_generation_commits_are_ancestors(self):
        subprocess.run(["git", "merge-base", "--is-ancestor", BASE_SHA, "HEAD"], check=True)
        subprocess.run(["git", "merge-base", "--is-ancestor", CANDIDATE_SHA, "HEAD"], check=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
