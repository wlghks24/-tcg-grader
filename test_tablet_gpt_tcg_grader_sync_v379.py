import hashlib
import json
import subprocess
import unittest
from pathlib import Path

import tablet_autonomous_evolution_v379 as autonomy
from sync_v376_successor_test_support import V380_WATCHED, V381_WATCHED, V382_WATCHED, assert_current_autonomy_route_v380, assert_v379_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V379.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v379_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v379.json"
BASE_SHA = "3370896de0324572f7921329ba8f4582a4b56539"
CANDIDATE_SHA = "7f68e579e6cb84e65d059ec14b78d7e42e94fb0c"
LESSON_ID = "TABLET-GPT-INFORMATION-EXCHANGE-GOVERNANCE-V379"
EXPECTED_WATCHED = ["main", "tablet_autonomous_evolution_v379.py", "tablet_runtime_manifest.py"]


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


class TabletGptTcgGraderSyncV379Tests(unittest.TestCase):
    def test_generation_binding_digest_and_counts(self):
        c, d, r = load(CONTRACT), load(DELTA), load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V378.json", c["prior_contract"])
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v378_delta.json", c["prior_delta_snapshot"])
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v379_delta.json", c["delta_snapshot"])
        self.assertEqual("TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v379.json", c["receiver_receipt"])
        self.assertEqual(BASE_SHA, d["source_main_sha"])
        self.assertEqual(BASE_SHA, r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"], digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID], r["accepted_lesson_ids"])
        self.assertEqual(71, c["prior_required_lesson_count"])
        self.assertEqual(72, c["current_required_lesson_count"])
        self.assertEqual(367, c["current_required_merge_prs"][-1])
        self.assertEqual("SYNCED_VERIFIED", r["status"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])

    def test_information_exchange_rules_are_fail_closed(self):
        c, d = load(CONTRACT), load(DELTA)
        rules = c["rules"]
        policy = d["share_policy"]
        for key in (
            "information_exchange_summary_only_required",
            "information_exchange_conflict_blocks_mutation",
            "information_exchange_invalid_blocks_mutation",
            "information_exchange_input_stability_required",
            "peer_learning_requires_local_reproduction",
            "peer_fix_auto_apply_forbidden",
            "peer_content_direct_model_training_forbidden",
            "peer_exchange_fact_price_grade_promotion_forbidden",
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
        self.assertTrue(autonomy.SAFETY["information_exchange_manager_enabled"])
        self.assertTrue(autonomy.SAFETY["information_exchange_conflict_blocks_mutation"])
        self.assertTrue(autonomy.SAFETY["information_exchange_input_stability_required"])
        self.assertFalse(autonomy.SAFETY["peer_fix_auto_apply"])
        self.assertFalse(autonomy.SAFETY["peer_content_direct_model_training"])
        self.assertFalse(autonomy.SAFETY["git_write"])
        self.assertFalse(autonomy.SAFETY["market_direction_inferred"])

    def test_candidate_exactly_covers_current_runtime_entrypoint(self):
        c = load(CONTRACT)
        candidate = c["candidate_sync"]
        self.assertEqual(BASE_SHA, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, candidate["candidate_commit"])
        self.assertEqual(EXPECTED_WATCHED, candidate["watched_paths"])
        self.assertEqual(EXPECTED_WATCHED, watched_paths(c, BASE_SHA, CANDIDATE_SHA))
        self.assertEqual(sorted(set(V380_WATCHED) | set(V381_WATCHED) | set(V382_WATCHED)), watched_paths(c, CANDIDATE_SHA))
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        assert_v379_successor(self)
        assert_current_autonomy_route_v380(self)


if __name__ == "__main__":
    unittest.main(verbosity=2)
