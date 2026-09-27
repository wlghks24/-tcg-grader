import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
PRIOR = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v339_delta.json"
DELTA = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v341_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v341.json"
PRIOR_CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V339.json"
CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V341.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


class TabletGptTcgGraderSyncV341(unittest.TestCase):
    def test_lineage_digest_and_exact_covered_merges(self):
        prior, delta, receipt, prior_contract, contract = map(read, (PRIOR, DELTA, RECEIPT, PRIOR_CONTRACT, CONTRACT))
        self.assertEqual(prior["lesson_digest_sha256"], delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"], receipt["prior_lesson_digest_sha256"])
        self.assertEqual("be144184da52d16ccde3d7d2c65fa37953d55bac", delta["source_main_sha"])
        self.assertEqual([294, 297], [row["pr"] for row in delta["covered_merges"]])
        self.assertEqual(set(contract["current_required_merge_prs"]), set(prior_contract["current_required_merge_prs"]) | {294, 297})
        raw = json.dumps(delta["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.assertEqual(digest, delta["lesson_digest_sha256"])
        self.assertEqual(digest, receipt["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in delta["lessons"]], receipt["accepted_lesson_ids"])
        self.assertTrue(all(row["regression_pass"] for row in delta["lessons"]))
        self.assertEqual("SYNCED_VERIFIED", receipt["status"])
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])

    def test_pr_freshness_is_blocking_and_exact_base_bound(self):
        contract = read(CONTRACT)
        workflow = (ROOT / ".github/workflows/tablet-gpt-tcg-grader-main-alignment.yml").read_text(encoding="utf-8")
        self.assertFalse(contract["rules"]["pull_request_freshness_check_is_nonblocking"])
        self.assertTrue(contract["rules"]["pull_request_candidate_sync_requires_exact_base_and_generation_files"])
        self.assertNotIn("if: github.event_name != 'pull_request'", workflow)
        for token in ("GITHUB_EVENT_PATH", "generation_files.issubset(pr_changed)", "source == base_sha", "TABLET_GPT_PR_SYNC_CANDIDATE_COVERED"):
            self.assertIn(token, workflow)

    def test_latest_generation_files_are_bound_and_excluded(self):
        contract = read(CONTRACT)
        watch = contract["freshness_watch"]
        expected = {
            "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v341_delta.json",
            "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v341.json",
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V341.json",
            "test_tablet_gpt_tcg_grader_sync_v341.py",
        }
        self.assertTrue(expected.issubset(set(watch["exclude_paths"])))
        workflow = (ROOT / ".github/workflows/tablet-gpt-tcg-grader-main-alignment.yml").read_text(encoding="utf-8")
        for token in ("expected_delta", "expected_receipt", "expected_test", "assert contract['delta_snapshot'] == expected_delta"):
            self.assertIn(token, workflow)

    def test_integrity_guard_has_git_index_completeness(self):
        guard = (ROOT / "repository_integrity_guard.py").read_text(encoding="utf-8")
        tests = (ROOT / "test_repository_selfrefine_v13.py").read_text(encoding="utf-8")
        self.assertIn("_git_tracked_paths", guard)
        self.assertIn("current - listed", guard)
        self.assertIn("listed - current", guard)
        self.assertIn("test_integrity_manifest_rejects_new_unlisted_git_tracked_file", tests)
        self.assertIn("test_integrity_manifest_ignores_untracked_runtime_artifact", tests)


if __name__ == "__main__":
    unittest.main(verbosity=2)
