import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
PRIOR = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v334_delta.json"
DELTA = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v339_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v339.json"
PRIOR_CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V334.json"
CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V339.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


class TabletGptTcgGraderSyncV339(unittest.TestCase):
    def test_current_lineage_and_exact_covered_merges(self):
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

    def test_digest_receipt_and_no_unverified_device_claim(self):
        delta, receipt, contract = map(read, (DELTA, RECEIPT, CONTRACT))
        raw = json.dumps(delta["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.assertEqual(digest, delta["lesson_digest_sha256"])
        self.assertEqual(digest, receipt["delta_lesson_digest_sha256"])
        lesson_ids = [row["lesson_id"] for row in delta["lessons"]]
        self.assertEqual(lesson_ids, receipt["accepted_lesson_ids"])
        self.assertEqual(4, len(lesson_ids))
        self.assertTrue(all(row["regression_pass"] for row in delta["lessons"]))
        self.assertTrue(all(row["confidence_level"] == "high" for row in delta["lessons"]))
        self.assertEqual("SYNCED_VERIFIED", receipt["status"])
        self.assertEqual(28, contract["current_required_lesson_count"])
        self.assertFalse(delta["share_policy"]["chatgpt_model_weights_exported"])
        self.assertFalse(delta["share_policy"]["raw_grading_calibration_shared"])
        self.assertFalse(delta["share_policy"]["device_local_runtime_memory_overwritten"])
        self.assertTrue(receipt["alignment_policy"]["blind_overwrite_forbidden"])
        self.assertTrue(receipt["alignment_policy"]["peer_verified_never_auto_promotes_local"])
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])
        self.assertTrue(receipt["verification"]["device_reverification_required"])

    def test_v335_v337_v338_prevention_contracts_are_live(self):
        grading = (ROOT / ".github/workflows/grading-company-watch.yml").read_text(encoding="utf-8")
        schedule = (ROOT / "TABLET_SCHEDULED_UPDATE.sh").read_text(encoding="utf-8")
        drive = (ROOT / "tablet_gdrive_publish.py").read_text(encoding="utf-8")
        self.assertNotIn("git push origin HEAD:main", grading)
        self.assertIn('cron: \'23 */3 * * *\'', grading)
        self.assertIn("매일 23:00 KST 기능 업데이트 확인", schedule)
        self.assertIn("REMOTE_RETENTION_DAYS = 14", drive)
        self.assertIn("REMOTE_PACKAGE_MIN_KEEP = 4", drive)
        self.assertIn("REMOTE_PACKAGE_MAX_KEEP = 40", drive)
        self.assertIn("REMOTE_RECEIPT_MIN_KEEP = 16", drive)
        self.assertIn("REMOTE_RECEIPT_MAX_KEEP = 64", drive)
        self.assertIn("refusing to delete unknown receipt object", drive)

    def test_latest_contract_is_excluded_but_runtime_paths_remain_watched(self):
        contract = read(CONTRACT)
        watch = contract["freshness_watch"]
        for path in ("main", "TABLET_SCHEDULED_UPDATE.sh", "TABLET_GDRIVE_SYNC.md"):
            self.assertTrue(path in watch["exact_paths"] or path.startswith(tuple(watch["path_prefixes"])))
            self.assertNotIn(path, watch["exclude_paths"])
        for path in (str(DELTA.relative_to(ROOT)), str(RECEIPT.relative_to(ROOT)),
                     str(CONTRACT.relative_to(ROOT)), "test_tablet_gpt_tcg_grader_sync_v339.py"):
            self.assertIn(path, watch["exclude_paths"])
        self.assertTrue(contract["rules"]["watched_changes_after_delta_source_main_must_report_stale_on_main"])
        self.assertTrue(contract["rules"]["physical_tablet_and_drive_results_must_not_be_invented"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
