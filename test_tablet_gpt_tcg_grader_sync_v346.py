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
    def test_postmerge_checkpoint_lineage_and_digest(self):
        prior, delta, receipt, prior_contract, contract = map(
            read, (PRIOR, DELTA, RECEIPT, PRIOR_CONTRACT, CONTRACT)
        )
        expected_main = "ad9d79f1ae656145302c7e6125f3139cb5d4cee8"
        self.assertEqual(prior["lesson_digest_sha256"], delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"], receipt["prior_lesson_digest_sha256"])
        self.assertEqual(expected_main, delta["source_main_sha"])
        self.assertEqual(expected_main, receipt["source_main_sha"])
        self.assertEqual([310], [row["pr"] for row in delta["covered_merges"]])
        self.assertEqual(expected_main, delta["covered_merges"][0]["merge_sha"])
        self.assertEqual(
            set(contract["current_required_merge_prs"]),
            set(prior_contract["current_required_merge_prs"]) | {310},
        )
        raw = json.dumps(delta["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.assertEqual("4a0738e30e6d6a0ad167e1e2d813f8a350bb43491d54fd5b3d1e6f074079b303", digest)
        self.assertEqual(digest, delta["lesson_digest_sha256"])
        self.assertEqual(digest, receipt["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in delta["lessons"]], receipt["accepted_lesson_ids"])
        self.assertEqual("SYNCED_VERIFIED", receipt["status"])
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])

    def test_checkpoint_preserves_fail_closed_watch(self):
        contract = read(CONTRACT)
        self.assertNotIn("candidate_sync", contract)
        self.assertFalse(contract["rules"]["pull_request_freshness_check_is_nonblocking"])
        self.assertTrue(contract["rules"]["watched_changes_after_delta_source_main_must_report_stale_on_main"])
        self.assertTrue(contract["rules"]["post_merge_checkpoint_must_reanchor_later_pull_requests"])
        generation = {
            "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v346_delta.json",
            "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v346.json",
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V346.json",
            "test_tablet_gpt_tcg_grader_sync_v346.py",
        }
        watch = contract["freshness_watch"]
        self.assertTrue(generation.issubset(set(watch["exclude_paths"])))
        self.assertIn("grading_", watch["path_prefixes"])
        self.assertIn(".github/workflows/tcg-static-data-refresh.yml", watch["exact_paths"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
