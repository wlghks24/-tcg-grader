import hashlib
import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PRIOR = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v354_delta.json"
DELTA = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v355_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v355.json"
PRIOR_CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V354.json"
CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V355.json"
SOURCE = "e5d6dce608a3c0e6b737cce8a68e026069c7c2eb"
EXPECTED_DIGEST = "2bf50a1ddf13fc2a46240ef8b3d817c96f913e001c69e5b1cd2fc8a140ff94f4"

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

class TabletGptTcgGraderSyncV355(unittest.TestCase):
    def test_postmerge_checkpoint_lineage_digest_and_safe_receipt(self):
        prior, delta, receipt, prior_contract, contract = map(
            read, (PRIOR, DELTA, RECEIPT, PRIOR_CONTRACT, CONTRACT)
        )
        self.assertEqual(prior["lesson_digest_sha256"], delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"], receipt["prior_lesson_digest_sha256"])
        self.assertEqual(SOURCE, delta["source_main_sha"])
        self.assertEqual(SOURCE, receipt["source_main_sha"])
        self.assertEqual([329], [row["pr"] for row in delta["covered_merges"]])
        self.assertEqual(SOURCE, delta["covered_merges"][0]["merge_sha"])
        self.assertEqual(set(contract["current_required_merge_prs"]),
                         set(prior_contract["current_required_merge_prs"]) | {329})
        self.assertEqual(prior_contract["current_required_lesson_count"],
                         contract["prior_required_lesson_count"])
        self.assertEqual(contract["prior_required_lesson_count"] + 1,
                         contract["current_required_lesson_count"])
        raw = json.dumps(delta["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.assertEqual(EXPECTED_DIGEST, digest)
        self.assertEqual(digest, delta["lesson_digest_sha256"])
        self.assertEqual(digest, receipt["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in delta["lessons"]], receipt["accepted_lesson_ids"])
        self.assertEqual("SYNCED_VERIFIED", receipt["status"])
        self.assertFalse(delta["share_policy"]["chatgpt_model_weights_exported"])
        self.assertFalse(delta["share_policy"]["raw_grading_calibration_shared"])
        self.assertFalse(delta["share_policy"]["device_local_runtime_memory_overwritten"])
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])
        subprocess.run(["git", "merge-base", "--is-ancestor", SOURCE, "HEAD"], check=True)

    def test_checkpoint_keeps_future_watched_changes_fail_closed(self):
        contract = read(CONTRACT)
        self.assertNotIn("candidate_sync", contract)
        self.assertTrue(contract["rules"]["post_merge_checkpoint_must_anchor_future_pr_freshness"])
        self.assertTrue(contract["rules"]["subsequent_watched_change_requires_new_generation"])
        self.assertIn("grading_", contract["freshness_watch"]["path_prefixes"])
        self.assertNotIn("grading_company_updates.json", contract["freshness_watch"]["exclude_paths"])

    def test_generation_files_are_bound_and_excluded(self):
        contract = read(CONTRACT)
        expected = {
            "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v355_delta.json",
            "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v355.json",
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V355.json",
            "test_tablet_gpt_tcg_grader_sync_v355.py",
        }
        self.assertEqual(expected, expected & set(contract["freshness_watch"]["exclude_paths"]))
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v355_delta.json", contract["delta_snapshot"])
        self.assertEqual("TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v355.json", contract["receiver_receipt"])
        self.assertEqual("test_tablet_gpt_tcg_grader_sync_v355.py", contract["verification_test"])
        for path in expected:
            self.assertTrue((ROOT / path).is_file(), path)

if __name__ == "__main__":
    unittest.main(verbosity=2)
