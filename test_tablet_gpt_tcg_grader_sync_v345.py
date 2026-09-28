import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
PRIOR = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v344_delta.json"
DELTA = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v345_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v345.json"
PRIOR_CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V344.json"
CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V345.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


class TabletGptTcgGraderSyncV345(unittest.TestCase):
    def test_lineage_digest_and_current_main_anchor(self):
        prior, delta, receipt, prior_contract, contract = map(
            read, (PRIOR, DELTA, RECEIPT, PRIOR_CONTRACT, CONTRACT)
        )
        self.assertEqual(prior["lesson_digest_sha256"], delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"], receipt["prior_lesson_digest_sha256"])
        self.assertEqual("0b7b547c7fc4d12761743c5251a6db060f6c84cc", delta["source_main_sha"])
        self.assertEqual(delta["source_main_sha"], receipt["source_main_sha"])
        self.assertEqual(list(range(303, 310)), [row["pr"] for row in delta["covered_merges"]])
        self.assertEqual(
            set(contract["current_required_merge_prs"]),
            set(prior_contract["current_required_merge_prs"]) | set(range(303, 310)),
        )
        raw = json.dumps(delta["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.assertEqual("291412f4758142f3a8f36ccd8bbcce5c225fc5d9b23159f0e9b52ae78d7f4778", digest)
        self.assertEqual(digest, delta["lesson_digest_sha256"])
        self.assertEqual(digest, receipt["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in delta["lessons"]], receipt["accepted_lesson_ids"])
        self.assertEqual("SYNCED_VERIFIED", receipt["status"])
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])

    def test_candidate_sync_is_exact_for_static_candidate(self):
        contract = read(CONTRACT)
        candidate = contract["candidate_sync"]
        expected_generation = {
            "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v345_delta.json",
            "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v345.json",
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V345.json",
            "test_tablet_gpt_tcg_grader_sync_v345.py",
        }
        self.assertEqual("0b7b547c7fc4d12761743c5251a6db060f6c84cc", candidate["base_main_sha"])
        self.assertEqual(expected_generation, set(candidate["generation_files"]))
        self.assertEqual(
            {".github/workflows/tcg-static-data-refresh.yml", "grading_company_updates.json"},
            set(candidate["watched_paths"]),
        )
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        self.assertTrue(expected_generation.issubset(set(contract["freshness_watch"]["exclude_paths"])))
        self.assertTrue(contract["rules"]["static_publish_manifest_must_be_git_tracked_only"])

    def test_static_integrity_repair_keeps_fail_closed_guards(self):
        workflow = (ROOT / ".github/workflows/tcg-static-data-refresh.yml").read_text(encoding="utf-8")
        helper = (ROOT / "static_integrity_manifest.py").read_text(encoding="utf-8")
        self.assertIn("git diff --name-only -z", workflow)
        self.assertIn("git restore --worktree --", workflow)
        self.assertIn("static_integrity_manifest.py --check", workflow)
        self.assertIn("static_integrity_manifest.py --write", workflow)
        self.assertIn('["git", "ls-files", "-z"]', helper)
        self.assertIn("healing.tracked_files(root)", helper)
        self.assertNotIn("HEAD:main", workflow)
        self.assertNotIn("--force", workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
