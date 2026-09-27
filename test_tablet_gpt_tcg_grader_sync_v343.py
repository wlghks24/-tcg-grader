import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
PRIOR = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v342_delta.json"
DELTA = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v343_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v343.json"
PRIOR_CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V342.json"
CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V343.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


class TabletGptTcgGraderSyncV343(unittest.TestCase):
    def test_post_merge_lineage_digest_and_exact_main_anchor(self):
        prior, delta, receipt, prior_contract, contract = map(read, (PRIOR, DELTA, RECEIPT, PRIOR_CONTRACT, CONTRACT))
        self.assertEqual(prior["lesson_digest_sha256"], delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"], receipt["prior_lesson_digest_sha256"])
        self.assertEqual("fd52a17e817cfd8e057893bea91a0047858ce853", delta["source_main_sha"])
        self.assertEqual(delta["source_main_sha"], receipt["source_main_sha"])
        self.assertEqual([301], [row["pr"] for row in delta["covered_merges"]])
        self.assertEqual(set(contract["current_required_merge_prs"]), set(prior_contract["current_required_merge_prs"]) | {301})
        raw = json.dumps(delta["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.assertEqual(digest, delta["lesson_digest_sha256"])
        self.assertEqual(digest, receipt["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in delta["lessons"]], receipt["accepted_lesson_ids"])
        self.assertTrue(all(row["regression_pass"] for row in delta["lessons"]))
        self.assertEqual("SYNCED_VERIFIED", receipt["status"])
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])

    def test_post_merge_anchor_rule_is_preserved(self):
        delta = read(DELTA)
        lesson = delta["lessons"][0]
        self.assertEqual("TABLET-GPT-POST-MERGE-FRESHNESS-ANCHOR-V343", lesson["lesson_id"])
        self.assertEqual("candidate_base_anchor_is_not_post_merge_main_anchor", lesson["root_cause_class"])
        self.assertTrue(lesson["physical_tablet_runtime_reverification_required"])

    def test_generation_files_are_excluded_but_watched_runtime_paths_remain_watched(self):
        contract = read(CONTRACT)
        watch = contract["freshness_watch"]
        expected = {
            "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v343_delta.json",
            "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v343.json",
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V343.json",
            "test_tablet_gpt_tcg_grader_sync_v343.py",
        }
        self.assertTrue(expected.issubset(set(watch["exclude_paths"])))
        self.assertIn("sw.js", watch["exact_paths"])
        self.assertIn("TABLET_", watch["path_prefixes"])
        self.assertFalse(contract["rules"]["pull_request_freshness_check_is_nonblocking"])
        self.assertTrue(contract["rules"]["watched_changes_after_delta_source_main_must_report_stale_on_main"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
