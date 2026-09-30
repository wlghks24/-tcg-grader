import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
PRIOR = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v345_delta.json"
DELTA = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v346_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v346.json"
PRIOR_CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V345.json"
CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V346.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


class TabletGptTcgGraderSyncV346(unittest.TestCase):
    def test_lineage_digest_and_current_main_anchor(self):
        prior, delta, receipt, prior_contract, contract = map(
            read, (PRIOR, DELTA, RECEIPT, PRIOR_CONTRACT, CONTRACT)
        )
        self.assertEqual(prior["lesson_digest_sha256"], delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"], receipt["prior_lesson_digest_sha256"])
        self.assertEqual("ad9d79f1ae656145302c7e6125f3139cb5d4cee8", delta["source_main_sha"])
        self.assertEqual(delta["source_main_sha"], receipt["source_main_sha"])
        self.assertEqual([310], [row["pr"] for row in delta["covered_merges"]])
        self.assertEqual(
            set(contract["current_required_merge_prs"]),
            set(prior_contract["current_required_merge_prs"]) | {310},
        )
        raw = json.dumps(delta["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.assertEqual("3c0e2bc2795be26ce4b50acba1be4cf9d4fa1536964f3a345daa10895cc43898", digest)
        self.assertEqual(digest, delta["lesson_digest_sha256"])
        self.assertEqual(digest, receipt["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in delta["lessons"]], receipt["accepted_lesson_ids"])
        self.assertEqual("SYNCED_VERIFIED", receipt["status"])
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])

    def test_candidate_sync_is_exact_for_drive_recovery_watch(self):
        contract = read(CONTRACT)
        candidate = contract["candidate_sync"]
        expected_generation = {
            "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v346_delta.json",
            "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v346.json",
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V346.json",
            "test_tablet_gpt_tcg_grader_sync_v346.py",
        }
        self.assertEqual("ad9d79f1ae656145302c7e6125f3139cb5d4cee8", candidate["base_main_sha"])
        self.assertEqual(expected_generation, set(candidate["generation_files"]))
        self.assertEqual(
            {".github/workflows/gpt-tcg-drive-package.yml"},
            set(candidate["watched_paths"]),
        )
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        self.assertTrue(expected_generation.issubset(set(contract["freshness_watch"]["exclude_paths"])))

    def test_stale_package_recovery_preserves_fail_closed_freshness(self):
        workflow = (ROOT / ".github/workflows/gpt-tcg-drive-package.yml").read_text(encoding="utf-8")
        publisher = (ROOT / "tablet_collection_publish.py").read_text(encoding="utf-8")
        repo_guard = (ROOT / ".github/workflows/repository-integrity-guard.yml").read_text(encoding="utf-8")
        self.assertIn("STALE_AUTO_UPDATE_REPORT", workflow)
        self.assertIn("STALE_SOCIAL_SNAPSHOT", workflow)
        self.assertIn("STALE_SUPPLEMENTARY_SNAPSHOT", workflow)
        self.assertIn("critical and critical <= recoverable", workflow)
        self.assertIn("tcg_updater.update_cycle('gpt-drive-package-refresh')", workflow)
        self.assertIn("FRESH_LOCAL_COLLECTION_RETRY", workflow)
        self.assertIn("steps.package.outputs.ready == 'true'", workflow)
        self.assertNotIn("actions: write", workflow)
        self.assertNotIn("tcg-static-data-refresh.yml/dispatches", workflow)
        self.assertIn("--max-report-age-hours', '2'", publisher)
        self.assertNotIn("--max-report-age-hours 12", workflow)
        self.assertIn("protected_static_candidate_guard.py", repo_guard)
        contract = read(CONTRACT)
        self.assertTrue(contract["rules"]["static_candidate_scope_must_be_data_only"])
        self.assertTrue(contract["rules"]["stale_drive_package_must_not_upload_artifact"])
        latest = read(ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V370.json")
        self.assertTrue(latest["rules"]["drive_package_freshness_only_local_retry_required"])
        self.assertTrue(latest["rules"]["drive_package_non_freshness_critical_remains_blocking"])
        self.assertTrue(latest["rules"]["drive_package_stale_inputs_upload_forbidden"])
        self.assertTrue(latest["rules"]["freshness_threshold_widening_forbidden"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
