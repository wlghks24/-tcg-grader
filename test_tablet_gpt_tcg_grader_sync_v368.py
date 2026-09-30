import hashlib
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parent
SOURCE = "c6e7f04b998348f5cfc47b6cd9dc7adc14182a18"
CANDIDATE = "c89faa771503cd82fffb1c129fb53deaa6c0fd5f"
PRIOR = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v367_delta.json"
DELTA = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v368_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v368.json"
PRIOR_CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V367.json"
CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V368.json"
WORKFLOW = ROOT / ".github/workflows/gpt-tcg-drive-package.yml"
EXPECTED_DIGEST = "24321d13b13ce2f3665ca054dfd29b9fff1e1d47f06a92c186a2eb4d4de08f82"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def watched_paths(contract, source, head="HEAD"):
    watch = contract["freshness_watch"]
    exact = set(watch["exact_paths"])
    prefixes = tuple(watch["path_prefixes"])
    excluded = set(watch["exclude_paths"])
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", f"{source}..{head}"], text=True
    ).splitlines()
    return sorted(
        path
        for path in changed
        if path not in excluded and (path in exact or path.startswith(prefixes))
    )


class TabletGptTcgGraderSyncV368(unittest.TestCase):
    def test_lineage_digest_receipt_and_merge_anchor(self):
        prior, delta, receipt, pc, contract = map(
            read, (PRIOR, DELTA, RECEIPT, PRIOR_CONTRACT, CONTRACT)
        )
        self.assertEqual(prior["lesson_digest_sha256"], delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"], receipt["prior_lesson_digest_sha256"])
        self.assertEqual(SOURCE, delta["source_main_sha"])
        self.assertEqual(SOURCE, receipt["source_main_sha"])
        self.assertEqual([351], [row["pr"] for row in delta["covered_merges"]])
        self.assertEqual(SOURCE, delta["covered_merges"][0]["merge_sha"])
        self.assertEqual(
            set(contract["current_required_merge_prs"]),
            set(pc["current_required_merge_prs"]) | {351},
        )
        self.assertEqual(
            pc["current_required_lesson_count"], contract["prior_required_lesson_count"]
        )
        self.assertEqual(
            contract["prior_required_lesson_count"] + contract["delta_required_lesson_count"],
            contract["current_required_lesson_count"],
        )
        raw = json.dumps(
            delta["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.assertEqual(EXPECTED_DIGEST, digest)
        self.assertEqual(digest, delta["lesson_digest_sha256"])
        self.assertEqual(digest, receipt["delta_lesson_digest_sha256"])
        self.assertEqual(
            [row["lesson_id"] for row in delta["lessons"]], receipt["accepted_lesson_ids"]
        )
        self.assertEqual("SYNCED_VERIFIED", receipt["status"])
        self.assertEqual(
            "TABLET_GPT_TCG_GRADER_MATCH", receipt["verification"]["verified_result"]
        )
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])
        subprocess.run(["git", "merge-base", "--is-ancestor", SOURCE, "HEAD"], check=True)
        subprocess.run(["git", "merge-base", "--is-ancestor", CANDIDATE, "HEAD"], check=True)

    def test_exact_candidate_scope_and_complete_generation(self):
        contract = read(CONTRACT)
        candidate = contract["candidate_sync"]
        self.assertEqual(SOURCE, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE, candidate["candidate_commit"])
        expected_watched = [".github/workflows/gpt-tcg-drive-package.yml"]
        self.assertEqual(expected_watched, watched_paths(contract, SOURCE, CANDIDATE))
        self.assertEqual(sorted(candidate["watched_paths"]), expected_watched)
        expected_generation = {
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V368.json",
            "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v368_delta.json",
            "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v368.json",
            "test_tablet_gpt_tcg_grader_sync_v368.py",
        }
        self.assertEqual(expected_generation, set(candidate["generation_files"]))
        self.assertTrue(expected_generation.issubset(set(contract["freshness_watch"]["exclude_paths"])))
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        self.assertEqual([], watched_paths(contract, CANDIDATE))

    def test_supplementary_freshness_recovery_is_explicit_and_fail_closed(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(
            'recoverable = {"STALE_AUTO_UPDATE_REPORT", "STALE_SOCIAL_SNAPSHOT"}', workflow
        )
        self.assertIn("critical and critical <= recoverable", workflow)
        self.assertIn(
            'expanded_recoverable = recoverable | {"STALE_SUPPLEMENTARY_SNAPSHOT"}', workflow
        )
        self.assertIn("critical and critical <= expanded_recoverable", workflow)
        self.assertIn("FRESH_STATIC_REFRESH_DISPATCHED", workflow)
        self.assertIn("tcg-static-data-refresh.yml/dispatches", workflow)
        self.assertIn('echo "ready=false"', workflow)
        self.assertIn('exit "${rc}"', workflow)
        self.assertIn("never widen the two-hour report freshness gate", workflow)
        self.assertNotIn("publish_allowed = true", workflow)
        rules = read(CONTRACT)["rules"]
        self.assertIs(rules["supplementary_staleness_may_only_request_protected_refresh"], True)
        self.assertIs(rules["non_freshness_critical_findings_must_remain_blocking"], True)
        self.assertIs(rules["freshness_threshold_widening_forbidden"], True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
