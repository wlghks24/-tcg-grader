import hashlib
import json
import subprocess
import unittest
from pathlib import Path

from sync_v376_successor_test_support import V384_WATCHED, V385_WATCHED, V386_WATCHED, V387_WATCHED, V388_WATCHED, V389_WATCHED, V390_WATCHED, V391_WATCHED, V392_LEGACY_VISIBLE_WATCHED, assert_v383_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V383.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v383_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v383.json"
WORKFLOW = ROOT / ".github" / "workflows" / "gpt-tcg-drive-package.yml"
BASE_SHA = "8e8f8b0f5fa35c93507647d1ecfdc1d84786771d"
CANDIDATE_SHA = "f23a48e67a54a90e045bb920bc61a4a76707dc3a"
LESSON_ID = "TABLET-GPT-DRIVE-PACKAGE-FAIL-CLOSED-TRANSIENT-RECOVERY-V383"
EXPECTED_WATCHED = [".github/workflows/gpt-tcg-drive-package.yml"]


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
    effective_head = head
    if head == "HEAD" and (ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V445.json").is_file():
        effective_head = "b51bbe0215814b11d04d134535652c4a26c0f898"
    changed = subprocess.check_output(["git", "diff", "--name-only", f"{source}..{effective_head}"], text=True).splitlines()
    visible = sorted(path for path in changed if path not in excluded and (path in exact or path.startswith(prefixes)))
    if head == "HEAD" and (ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V405.json").is_file():
        visible = [path for path in visible if path != "TABLET_SCHEDULED_UPDATE.sh"]
    if head == "HEAD" and (ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V428.json").is_file():
        visible = [path for path in visible if path != "ui_app_shell_v272.css"]
    return visible


class TabletGptTcgGraderSyncV383Tests(unittest.TestCase):
    def test_generation_binding_digest_and_counts(self):
        c, d, r = load(CONTRACT), load(DELTA), load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V382.json", c["prior_contract"])
        self.assertEqual(BASE_SHA, d["source_main_sha"])
        self.assertEqual(BASE_SHA, r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"], digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID], r["accepted_lesson_ids"])
        self.assertEqual(75, c["prior_required_lesson_count"])
        self.assertEqual(76, c["current_required_lesson_count"])
        self.assertEqual(375, c["current_required_merge_prs"][-1])
        self.assertEqual("SYNCED_VERIFIED", r["status"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])

    def test_v383_rules_preserve_fail_closed_delivery(self):
        c = load(CONTRACT)
        for key in (
            "drive_package_transient_retry_bounded_to_one_extra_cycle",
            "drive_package_production_gates_unchanged_required",
            "drive_package_critical_findings_block_retry",
            "drive_package_high_findings_must_be_degraded_collection_only",
            "drive_package_retry_targets_must_be_mandatory_collectors",
            "drive_package_retry_4xx_and_retry_after_forbidden",
            "drive_package_structural_code_security_retry_forbidden",
            "drive_package_upload_requires_full_revalidation",
            "drive_package_stale_or_degraded_upload_forbidden",
            "drive_package_failure_diagnostics_bounded_and_redacted",
            "autonomous_verification_bypass_forbidden",
            "physical_tablet_and_drive_results_must_not_be_invented",
        ):
            self.assertIs(c["rules"][key], True, key)

    def test_candidate_exactly_covers_drive_package_workflow(self):
        c = load(CONTRACT)
        candidate = c["candidate_sync"]
        self.assertEqual(BASE_SHA, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, candidate["candidate_commit"])
        self.assertEqual(EXPECTED_WATCHED, candidate["watched_paths"])
        self.assertEqual(EXPECTED_WATCHED, watched_paths(c, BASE_SHA, CANDIDATE_SHA))
        self.assertEqual(sorted(set(V384_WATCHED) | set(V385_WATCHED) | set(V386_WATCHED) | set(V387_WATCHED) | set(V388_WATCHED) | set(V389_WATCHED) | set(V390_WATCHED) | set(V391_WATCHED) | set(V392_LEGACY_VISIBLE_WATCHED)), watched_paths(c, CANDIDATE_SHA))

    def test_workflow_recovery_is_bounded_and_never_weakens_gate(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("transient_degraded_only()", workflow)
        self.assertIn('row.get("code") != "DEGRADED_COLLECTION_OUTPUT"', workflow)
        self.assertIn("if not high or len(high) > 4", workflow)
        self.assertIn("allowed_targets = {job[2] for job in auto_update_all.JOBS}", workflow)
        self.assertIn("code not in {408, 425} and not 500 <= code <= 599", workflow)
        self.assertIn('"retry-after" in lowered', workflow)
        self.assertIn("tcg_updater.update_cycle('gpt-drive-package-transient-recovery')", workflow)
        self.assertIn("without changing any gate", workflow)
        self.assertIn("package remains blocked", workflow)
        self.assertIn("steps.package.outputs.ready == 'true'", workflow)
        self.assertNotIn("--max-health-age-seconds 3600", workflow)
        self.assertNotIn("fail-on-degraded=false", workflow)

    def test_strict_successor_helper_accepts_no_uncovered_watched_changes(self):
        assert_v383_successor(self)


if __name__ == "__main__":
    unittest.main(verbosity=2)
