import hashlib
import json
import subprocess
import unittest
from pathlib import Path

from sync_v376_successor_test_support import assert_v383_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V383.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v383_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v383.json"
WORKFLOW = ROOT / ".github" / "workflows" / "gpt-tcg-drive-package.yml"
PUBLISHER = ROOT / "tablet_collection_publish.py"
BASE_SHA = "8e8f8b0f5fa35c93507647d1ecfdc1d84786771d"
CANDIDATE_SHA = "278b50321eb87d7801f55d4b1cf955bc71874b63"
LESSON_ID = "TABLET-GPT-BOUNDED-DRIVE-PACKAGE-RECOVERY-V383"
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
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", f"{source}..{head}"], text=True
    ).splitlines()
    return sorted(
        path for path in changed
        if path not in excluded and (path in exact or path.startswith(prefixes))
    )


class TabletGptTcgGraderSyncV383Tests(unittest.TestCase):
    def test_generation_binding(self):
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

    def test_recovery_is_bounded_and_fail_closed(self):
        c = load(CONTRACT)
        for key in (
            "drive_package_stale_only_recovery_required",
            "drive_package_recovery_attempts_bounded",
            "drive_package_max_fresh_collection_attempts_two",
            "drive_package_recovery_must_keep_fail_on_degraded",
            "drive_package_failed_attempt_findings_required",
            "drive_package_upload_requires_verified_ready",
            "drive_package_stale_or_degraded_upload_forbidden",
            "drive_package_freshness_threshold_widening_forbidden",
            "drive_package_blocked_provider_bypass_forbidden",
        ):
            self.assertIs(c["rules"][key], True, key)
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("for recovery_attempt in 1 2", workflow)
        publisher = PUBLISHER.read_text(encoding="utf-8")\n        self.assertIn("--fail-on-degraded", publisher)
        self.assertIn('"findings": [', workflow)
        self.assertIn("Fresh local collection did not satisfy the unchanged production gates after 2 bounded attempts", workflow)
        self.assertIn("steps.package.outputs.ready == 'true'", workflow)
        self.assertNotIn("publish_allowed = true", workflow)
        self.assertNotIn("actions: write", workflow)

    def test_candidate_exactly_covers_workflow_change(self):
        c = load(CONTRACT)
        candidate = c["candidate_sync"]
        self.assertEqual(BASE_SHA, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, candidate["candidate_commit"])
        self.assertEqual(EXPECTED_WATCHED, candidate["watched_paths"])
        self.assertEqual(EXPECTED_WATCHED, watched_paths(c, BASE_SHA, CANDIDATE_SHA))
        self.assertEqual([], watched_paths(c, CANDIDATE_SHA))
        assert_v383_successor(self)


if __name__ == "__main__":
    unittest.main(verbosity=2)
