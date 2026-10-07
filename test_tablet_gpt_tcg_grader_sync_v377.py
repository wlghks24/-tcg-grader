import hashlib
import json
import subprocess
import unittest
from pathlib import Path

from sync_v376_successor_test_support import assert_current_autonomy_route_v380, assert_v378_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V377.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v377_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v377.json"
BASE_SHA = "24cad558d756d57e06a8309c8d5fbc73626f1d45"
CANDIDATE_SHA = "b1000eb9f155ce343fc3bc59bcc0c35c5efb19c3"
LESSON_ID = "TABLET-GPT-SINGLE-RUN-AUTONOMY-GUARD-V377"
EXPECTED_WATCHED = ["main", "tablet_autonomous_evolution_v377.py", "tablet_runtime_manifest.py"]


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


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
    return visible


class TabletGptTcgGraderSyncV377Tests(unittest.TestCase):
    def test_generation_binding_and_digest(self):
        c, d, r = load(CONTRACT), load(DELTA), load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v377_delta.json", c["delta_snapshot"])
        self.assertEqual("TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v377.json", c["receiver_receipt"])
        self.assertEqual(BASE_SHA, d["source_main_sha"])
        self.assertEqual(BASE_SHA, r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"], digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID], r["accepted_lesson_ids"])
        self.assertEqual("SYNCED_VERIFIED", r["status"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])

    def test_legacy_safety_and_new_concurrency_guards_are_fail_closed(self):
        c, d = load(CONTRACT), load(DELTA)
        p, rules = d["share_policy"], c["rules"]
        self.assertTrue(p["explicit_patch_and_learning_lessons_only"])
        self.assertFalse(p["chatgpt_model_weights_exported"])
        self.assertFalse(p["raw_grading_calibration_shared"])
        self.assertFalse(p["device_local_runtime_memory_overwritten"])
        self.assertTrue(p["peer_verified_never_auto_promotes_local"])
        for key in (
            "single_mutating_cycle_lock_required",
            "concurrent_mutating_cycle_fail_closed",
            "concurrent_mutating_cycle_state_write_forbidden",
            "concurrent_mutating_cycle_execution_forbidden",
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
        self.assertEqual(69, c["prior_required_lesson_count"])
        self.assertEqual(70, c["current_required_lesson_count"])
        self.assertEqual(364, c["current_required_merge_prs"][-1])

    def test_candidate_exactly_covers_supported_runtime_entrypoint(self):
        contract = load(CONTRACT)
        c = contract["candidate_sync"]
        self.assertEqual(BASE_SHA, c["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, c["candidate_commit"])
        self.assertEqual(EXPECTED_WATCHED, c["watched_paths"])
        self.assertEqual(EXPECTED_WATCHED, watched_paths(contract, BASE_SHA, CANDIDATE_SHA))
        self.assertEqual([".github/workflows/gpt-tcg-drive-package.yml","index.html","main","sw.js","tablet_autonomous_evolution_v378.py","tablet_autonomous_evolution_v379.py","tablet_autonomous_evolution_v380.py","tablet_autonomous_evolution_v381.py","tablet_autonomous_evolution_v382.py","tablet_autonomous_evolution_v385.py","tablet_autonomous_evolution_v386.py","tablet_autonomous_evolution_v387.py","tablet_autonomous_evolution_v388.py","tablet_autonomous_evolution_v390.py","tablet_autonomous_evolution_v391.py","tablet_autonomous_evolution_v397.py","tablet_autonomous_evolution_v398.py","tablet_autonomous_evolution_v399.py","tablet_autonomous_evolution_v400.py","tablet_autonomy_dashboard_v399.css","tablet_autonomy_dashboard_v399.js","tablet_autonomy_dashboard_v400.css","tablet_autonomy_dashboard_v400.js","tablet_runtime_manifest.py","tcg_updater.py"], watched_paths(contract, CANDIDATE_SHA))
        assert_v378_successor(self)
        self.assertTrue(c["requires_exact_watched_path_match"])
        self.assertTrue(c["post_merge_coverage_allowed"])
        main = (ROOT / "main").read_text(encoding="utf-8")
        manifest = (ROOT / "tablet_runtime_manifest.py").read_text(encoding="utf-8")
        assert_current_autonomy_route_v380(self, main, manifest)


if __name__ == "__main__":
    unittest.main(verbosity=2)
