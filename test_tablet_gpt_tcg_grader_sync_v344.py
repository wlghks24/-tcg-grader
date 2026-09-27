import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
PRIOR = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v343_delta.json"
DELTA = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v344_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v344.json"
PRIOR_CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V343.json"
CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V344.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


class TabletGptTcgGraderSyncV344(unittest.TestCase):
    def test_lineage_digest_and_exact_main_anchor(self):
        prior, delta, receipt, prior_contract, contract = map(
            read, (PRIOR, DELTA, RECEIPT, PRIOR_CONTRACT, CONTRACT)
        )
        self.assertEqual(prior["lesson_digest_sha256"], delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"], receipt["prior_lesson_digest_sha256"])
        self.assertEqual("21cd3ee0d7be34ff96c3098a16712d0a8debd696", delta["source_main_sha"])
        self.assertEqual([302], [row["pr"] for row in delta["covered_merges"]])
        self.assertEqual(
            set(contract["current_required_merge_prs"]),
            set(prior_contract["current_required_merge_prs"]) | {302},
        )
        raw = json.dumps(delta["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.assertEqual(digest, delta["lesson_digest_sha256"])
        self.assertEqual(digest, receipt["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in delta["lessons"]], receipt["accepted_lesson_ids"])
        self.assertEqual("SYNCED_VERIFIED", receipt["status"])
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])

    def test_postmerge_candidate_coverage_is_exact_and_fail_closed(self):
        workflow = (ROOT / ".github/workflows/tablet-gpt-tcg-grader-main-alignment.yml").read_text(
            encoding="utf-8"
        )
        for token in (
            "TABLET_GPT_PR_SYNC_CANDIDATE_COVERED",
            "TABLET_GPT_MAIN_SYNC_GENERATION_COVERED",
            "generation_files.issubset(pr_changed)",
            "generation_files.issubset(changed_set)",
            "expected_watched == set(relevant)",
            "source == base_sha == candidate_base",
            "candidate.get('post_merge_coverage_allowed') is True",
            "candidate.get('requires_exact_watched_path_match') is True",
        ):
            self.assertIn(token, workflow)
        self.assertIn("if relevant:", workflow)
        self.assertIn("TABLET_GPT_SYNC_STALE", workflow)

    def test_v344_generation_is_bound_and_excluded(self):
        contract = read(CONTRACT)
        expected = {
            "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v344_delta.json",
            "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v344.json",
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V344.json",
            "test_tablet_gpt_tcg_grader_sync_v344.py",
        }
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v344_delta.json", contract["delta_snapshot"])
        self.assertEqual("TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v344.json", contract["receiver_receipt"])
        self.assertEqual("test_tablet_gpt_tcg_grader_sync_v344.py", contract["verification_test"])
        self.assertTrue(expected.issubset(set(contract["freshness_watch"]["exclude_paths"])))
        self.assertTrue(contract["rules"]["post_merge_candidate_sync_requires_exact_base_generation_and_watched_path_set"])
        self.assertTrue(contract["rules"]["post_merge_candidate_sync_must_fail_on_any_extra_watched_path"])

    def test_manifest_sync_writer_is_exact_branch_scoped(self):
        workflow = (ROOT / ".github/workflows/repository-integrity-manifest-sync-v344.yml").read_text(
            encoding="utf-8"
        )
        for token in (
            "- 'fix/tablet-sync-postmerge-v344-main'",
            "- 'integrity_manifest.json'",
            "github.ref != 'refs/heads/main'",
            "github.actor == github.repository_owner",
            "git merge-base --is-ancestor origin/main HEAD",
            'test "$(git diff --cached --name-only)" = "integrity_manifest.json"',
            'git push origin "HEAD:${GITHUB_REF_NAME}"',
        ):
            self.assertIn(token, workflow)
        self.assertNotIn("HEAD:main", workflow)
        self.assertNotIn("'fix/**'", workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
