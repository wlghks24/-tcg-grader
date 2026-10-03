import hashlib
import json
import subprocess
import unittest
from pathlib import Path

import tablet_autonomous_evolution_v378 as autonomy
from sync_v376_successor_test_support import assert_current_autonomy_route_v380, assert_v378_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V378.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v378_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v378.json"
BASE_SHA = "e318e7995eb35363256901197413f34aea4facb1"
CANDIDATE_SHA = "839c5890752d39343c1345c996dd8568baeecdeb"
LESSON_ID = "TABLET-GPT-100-1000-GOVERNED-AUTONOMY-V378"
EXPECTED_WATCHED = ["main", "tablet_autonomous_evolution_v378.py", "tablet_runtime_manifest.py"]


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
    return sorted(
        path for path in changed
        if path not in excluded and (path in exact or path.startswith(prefixes))
    )


class TabletGptTcgGraderSyncV378Tests(unittest.TestCase):
    def test_generation_binding_digest_and_counts(self):
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
        self.assertEqual(70, c["prior_required_lesson_count"])
        self.assertEqual(71, c["current_required_lesson_count"])
        self.assertEqual(365, c["current_required_merge_prs"][-1])
        self.assertEqual("SYNCED_VERIFIED", r["status"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])

    def test_100_plus_1000_neural_and_source_boundaries_are_fail_closed(self):
        c, d = load(CONTRACT), load(DELTA)
        rules = c["rules"]
        policy = d["share_policy"]
        for key in (
            "quality_100_senior_prep_required",
            "quality_1000_review_cells_required",
            "quality_policy_fail_closed_before_mutation",
            "quality_blocker_cannot_be_outvoted",
            "verified_neural_council_advisory_only",
            "declarative_runtime_self_extension_allowlisted_only",
            "source_level_feature_gap_requires_pr_ci",
            "market_regime_adaptation_operational_only",
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
        self.assertTrue(autonomy.SAFETY["quality_100_senior_prep_required"])
        self.assertTrue(autonomy.SAFETY["quality_1000_review_cells_required"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["git_write"])
        self.assertFalse(autonomy.SAFETY["market_direction_inferred"])

    def test_candidate_exactly_covers_current_runtime_entrypoint(self):
        c = load(CONTRACT)
        candidate = c["candidate_sync"]
        self.assertEqual(BASE_SHA, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, candidate["candidate_commit"])
        self.assertEqual(EXPECTED_WATCHED, candidate["watched_paths"])
        self.assertEqual(EXPECTED_WATCHED, watched_paths(c, BASE_SHA, CANDIDATE_SHA))
        self.assertEqual([".github/workflows/gpt-tcg-drive-package.yml","index.html","main","sw.js","tablet_autonomous_evolution_v379.py","tablet_autonomous_evolution_v380.py","tablet_autonomous_evolution_v381.py","tablet_autonomous_evolution_v382.py","tablet_autonomous_evolution_v385.py","tablet_autonomous_evolution_v386.py","tablet_autonomous_evolution_v387.py","tablet_autonomous_evolution_v388.py","tablet_autonomous_evolution_v390.py","tablet_autonomous_evolution_v391.py","tablet_autonomous_evolution_v397.py","tablet_autonomous_evolution_v398.py","tablet_autonomous_evolution_v399.py","tablet_autonomy_dashboard_v399.css","tablet_autonomy_dashboard_v399.js","tablet_autonomous_evolution_v400.py","tablet_autonomy_dashboard_v400.css","tablet_autonomy_dashboard_v400.js","tablet_runtime_manifest.py","tcg_updater.py"], watched_paths(c, CANDIDATE_SHA))
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        assert_v378_successor(self)
        main = (ROOT / "main").read_text(encoding="utf-8")
        manifest = (ROOT / "tablet_runtime_manifest.py").read_text(encoding="utf-8")
        assert_current_autonomy_route_v380(self, main, manifest)


if __name__ == "__main__":
    unittest.main(verbosity=2)
