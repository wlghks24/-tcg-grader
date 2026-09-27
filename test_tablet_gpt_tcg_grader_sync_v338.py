import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
PRIOR = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v334_delta.json"
DELTA = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v338_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v338.json"
PRIOR_CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V334.json"
CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V338.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


class TabletGptTcgGraderSyncV338(unittest.TestCase):
    def test_verified_operational_lessons_and_source_lineage(self):
        prior, delta, receipt, prior_contract, contract = map(
            read, (PRIOR, DELTA, RECEIPT, PRIOR_CONTRACT, CONTRACT)
        )
        self.assertEqual(prior["lesson_digest_sha256"], delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"], receipt["prior_lesson_digest_sha256"])
        self.assertEqual(delta["schema_version"], receipt["schema_version"])
        self.assertEqual(delta["schema_version"], contract["schema_version"])
        self.assertEqual(delta["source_repository"], receipt["source_repository"])
        self.assertEqual(delta["source_main_sha"], receipt["source_main_sha"])
        self.assertEqual("1705e419c79772d5439dc473ee64e9e627b42b34", delta["source_main_sha"])
        self.assertEqual([288, 289, 290, 291, 292, 293], [row["pr"] for row in delta["covered_merges"]])
        self.assertEqual(
            set(contract["current_required_merge_prs"]),
            set(prior_contract["current_required_merge_prs"]) | {288, 289, 290, 291, 292, 293},
        )

    def test_lesson_digest_receipt_and_safety_boundaries(self):
        delta, receipt, contract = map(read, (DELTA, RECEIPT, CONTRACT))
        raw = json.dumps(delta["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.assertEqual(digest, delta["lesson_digest_sha256"])
        self.assertEqual(digest, receipt["delta_lesson_digest_sha256"])
        lesson_ids = [row["lesson_id"] for row in delta["lessons"]]
        self.assertEqual(
            [
                "TABLET-GPT-PROTECTED-MAIN-PUBLISH-V335",
                "TABLET-GPT-DAILY-UPDATE-SCHEDULER-V337",
                "TABLET-GPT-GDRIVE-RETENTION-V338",
            ],
            lesson_ids,
        )
        self.assertEqual(lesson_ids, receipt["accepted_lesson_ids"])
        self.assertTrue(all(row["regression_pass"] for row in delta["lessons"]))
        self.assertTrue(all(row["confidence_level"] == "high" for row in delta["lessons"]))
        self.assertEqual("SYNCED_VERIFIED", receipt["status"])
        self.assertEqual(27, contract["current_required_lesson_count"])
        self.assertFalse(delta["share_policy"]["chatgpt_model_weights_exported"])
        self.assertFalse(delta["share_policy"]["raw_grading_calibration_shared"])
        self.assertFalse(delta["share_policy"]["device_local_runtime_memory_overwritten"])
        self.assertTrue(receipt["alignment_policy"]["blind_overwrite_forbidden"])
        self.assertTrue(receipt["alignment_policy"]["peer_verified_never_auto_promotes_local"])
        self.assertFalse(receipt["verification"]["device_visual_rendering_verified"])
        self.assertTrue(receipt["verification"]["device_visual_reverification_required"])

    def test_protected_main_grading_watch_contract(self):
        workflow = (ROOT / ".github/workflows/grading-company-watch.yml").read_text(encoding="utf-8")
        self.assertIn("candidate_branch=", workflow)
        self.assertIn('HEAD:refs/heads/${candidate_branch}', workflow)
        self.assertIn('gh api --method POST "repos/${REPO}/pulls"', workflow)
        self.assertIn("required_checks=(", workflow)
        self.assertIn("Tablet GPT TCG Grader Main Alignment", workflow)
        self.assertIn("Repository Integrity Guard", workflow)
        self.assertIn('git rev-parse origin/main', workflow)
        self.assertNotIn("HEAD:refs/heads/main", workflow)
        self.assertNotIn("git push origin main", workflow)

    def test_daily_2300_scheduler_contract(self):
        scheduler = (ROOT / "TABLET_SCHEDULED_UPDATE.sh").read_text(encoding="utf-8")
        main = (ROOT / "main").read_text(encoding="utf-8")
        self.assertIn('SCHEDULE_HOUR="23"', scheduler)
        self.assertIn('SCHEDULE_MINUTE="00"', scheduler)
        self.assertIn("next_run_kst()", scheduler)
        self.assertIn("seconds_until_next_run()", scheduler)
        self.assertIn("BOOT_LOOP_PID_FILE=", scheduler)
        self.assertIn("start_loop_if_needed()", scheduler)
        self.assertIn('bash "$ROOT/TABLET_SCHEDULED_UPDATE.sh" run', scheduler)
        self.assertNotIn("TCG_UPDATE_INTERVAL_HOURS", scheduler)
        self.assertIn("bash TABLET_SCHEDULED_UPDATE.sh ensure || true", main)

    def test_gdrive_retention_is_bounded_and_owned_only(self):
        drive = (ROOT / "tablet_gdrive_publish.py").read_text(encoding="utf-8")
        self.assertIn("REMOTE_RETENTION_DAYS = 14", drive)
        self.assertIn("REMOTE_PACKAGE_MIN_KEEP = 4", drive)
        self.assertIn("REMOTE_PACKAGE_MAX_KEEP = 40", drive)
        self.assertIn("REMOTE_RECEIPT_MIN_KEEP = 16", drive)
        self.assertIn("REMOTE_RECEIPT_MAX_KEEP = 64", drive)
        self.assertIn('"rclone", "deletefile"', drive)
        self.assertNotIn('"rclone", "purge"', drive)
        self.assertIn("refusing to delete unknown to_tablet object", drive)
        self.assertIn("refusing to delete unknown receipt object", drive)
        self.assertIn("return prune_remote_drive(remote, remote_root)", drive)
        self.assertLess(drive.index("sync.extract_bundle(read_bundle"), drive.index("return prune_remote_drive(remote, remote_root)"))

    def test_v338_freshness_watch_covers_new_operational_paths(self):
        contract = read(CONTRACT)
        watch = contract["freshness_watch"]
        for path in (
            ".github/workflows/grading-company-watch.yml",
            "TABLET_SCHEDULED_UPDATE.sh",
            "ANDROID_UPDATE_AND_START.sh",
            "tablet_gdrive_publish.py",
            "tablet_gdrive_sync.py",
            ".github/workflows/tablet-gdrive-sync-guard.yml",
        ):
            self.assertIn(path, watch["exact_paths"])
            self.assertNotIn(path, watch["exclude_paths"])
        self.assertIn("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v338_delta.json", watch["exclude_paths"])
        self.assertTrue(contract["rules"]["watched_changes_after_delta_source_main_must_report_stale_on_main"])
        self.assertTrue(contract["rules"]["protected_main_publish_must_use_candidate_pr_and_required_checks"])
        self.assertTrue(contract["rules"]["tablet_daily_update_schedule_must_remain_23_kst"])
        self.assertTrue(contract["rules"]["gdrive_retention_must_preserve_unknown_user_files"])
        self.assertTrue(contract["rules"]["gdrive_retention_runs_only_after_verified_readback"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
