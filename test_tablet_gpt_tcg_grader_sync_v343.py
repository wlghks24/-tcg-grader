import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
PRIOR = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v341_delta.json"
DELTA = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v343_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v343.json"
PRIOR_CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V341.json"
CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V343.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


class TabletGptTcgGraderSyncV343(unittest.TestCase):
    def test_lineage_digest_and_exact_base(self):
        prior, delta, receipt, prior_contract, contract = map(
            read, (PRIOR, DELTA, RECEIPT, PRIOR_CONTRACT, CONTRACT)
        )
        self.assertEqual(prior["lesson_digest_sha256"], delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"], receipt["prior_lesson_digest_sha256"])
        self.assertEqual("e6c09a75f5906aa4b7490577decebb1dc424e2f8", delta["source_main_sha"])
        self.assertEqual([299], [row["pr"] for row in delta["covered_merges"]])
        self.assertEqual(
            set(contract["current_required_merge_prs"]),
            set(prior_contract["current_required_merge_prs"]) | {299},
        )
        raw = json.dumps(delta["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.assertEqual(digest, delta["lesson_digest_sha256"])
        self.assertEqual(digest, receipt["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in delta["lessons"]], receipt["accepted_lesson_ids"])
        self.assertTrue(all(row["regression_pass"] for row in delta["lessons"]))
        self.assertEqual("SYNCED_VERIFIED", receipt["status"])
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])

    def test_candidate_generation_binds_exact_watched_paths_for_pr_and_main(self):
        contract = read(CONTRACT)
        candidate = contract["candidate_sync"]
        expected_generation = {
            "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v343_delta.json",
            "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v343.json",
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V343.json",
            "test_tablet_gpt_tcg_grader_sync_v343.py",
        }
        self.assertEqual("e6c09a75f5906aa4b7490577decebb1dc424e2f8", candidate["base_main_sha"])
        self.assertEqual(expected_generation, set(candidate["generation_files"]))
        self.assertEqual(
            {
                ".github/workflows/repository-integrity-manifest-sync.yml",
                "TABLET_SCHEDULED_UPDATE.sh",
                "sw.js",
            },
            set(candidate["watched_paths"]),
        )
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        self.assertTrue(expected_generation.issubset(set(contract["freshness_watch"]["exclude_paths"])))

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
        ):
            self.assertIn(token, workflow)

    def test_runtime_hardening_lessons_match_live_code(self):
        schedule = (ROOT / "TABLET_SCHEDULED_UPDATE.sh").read_text(encoding="utf-8")
        sw = (ROOT / "sw.js").read_text(encoding="utf-8")
        for token in (
            'SCHEDULER_VERSION="daily-2300-kst-v2"',
            "stop_verified_loop_process()",
            "run_and_reconcile_schedule()",
            "ensure_schedule || true",
            "pid_matches_mode()",
        ):
            self.assertIn(token, schedule)
        exact = "const exact=await caches.match(request);"
        broad = "const cached=await caches.match(request,{ignoreSearch:true});"
        self.assertIn(exact, sw)
        self.assertIn(broad, sw)
        self.assertLess(sw.index(exact), sw.index(broad))

    def test_fix_branch_manifest_sync_is_fail_closed_and_never_targets_main(self):
        workflow = (ROOT / ".github/workflows/repository-integrity-manifest-sync.yml").read_text(
            encoding="utf-8"
        )
        for token in (
            "- 'fix/**'",
            "paths-ignore:",
            "- 'integrity_manifest.json'",
            "github.ref != 'refs/heads/main'",
            "github.actor == github.repository_owner",
            "git merge-base --is-ancestor origin/main HEAD",
            'test "$(git diff --cached --name-only)" = "integrity_manifest.json"',
            'git push origin "HEAD:${GITHUB_REF_NAME}"',
        ):
            self.assertIn(token, workflow)
        self.assertNotIn("HEAD:main", workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
