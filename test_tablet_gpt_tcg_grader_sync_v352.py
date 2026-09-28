import hashlib
import json
import math
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parent
SOURCE = "3af7e77fd74af46ce5b82289100b8763a025de6f"
CANDIDATE = "5d48e75f8570d1ee22b3f792192a705bb889fa6d"
PRIOR = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v351_delta.json"
DELTA = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v352_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v352.json"
PRIOR_CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V351.json"
CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V352.json"
EXPECTED_DIGEST = "2be936e84be1bad9eed38eb70989ada9295d393d73843ad7648c007886fe7967"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


class TabletGptTcgGraderSyncV352(unittest.TestCase):
    def test_lineage_digest_receipt_and_safe_transfer_boundary(self):
        prior, delta, receipt, prior_contract, contract = map(
            read, (PRIOR, DELTA, RECEIPT, PRIOR_CONTRACT, CONTRACT)
        )
        self.assertEqual(prior["lesson_digest_sha256"], delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"], receipt["prior_lesson_digest_sha256"])
        self.assertEqual(SOURCE, delta["source_main_sha"])
        self.assertEqual(SOURCE, receipt["source_main_sha"])
        self.assertEqual({321, 322}, {row["pr"] for row in delta["covered_merges"]})
        self.assertEqual(
            set(contract["current_required_merge_prs"]),
            set(prior_contract["current_required_merge_prs"]) | {321, 322},
        )
        self.assertEqual(
            prior_contract["current_required_lesson_count"],
            contract["prior_required_lesson_count"],
        )
        self.assertEqual(
            contract["prior_required_lesson_count"] + contract["delta_required_lesson_count"],
            contract["current_required_lesson_count"],
        )
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
        for sha in (SOURCE, CANDIDATE, *[row["merge_sha"] for row in delta["covered_merges"]]):
            subprocess.run(["git", "merge-base", "--is-ancestor", sha, "HEAD"], check=True)

    def test_exact_latest_candidate_watched_path_set_and_generation_files(self):
        contract = read(CONTRACT)
        candidate = contract["candidate_sync"]
        self.assertEqual(SOURCE, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE, candidate["candidate_commit"])
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        watch = contract["freshness_watch"]
        exact = set(watch["exact_paths"])
        prefixes = tuple(watch["path_prefixes"])
        excluded = set(watch["exclude_paths"])

        def watched(path):
            return path not in excluded and (path in exact or path.startswith(prefixes))

        changed = subprocess.check_output(
            ["git", "diff", "--name-only", f"{SOURCE}..HEAD"], text=True
        ).splitlines()
        relevant = sorted(path for path in changed if watched(path))
        self.assertEqual(candidate["watched_paths"], relevant)

        expected = {
            "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v352_delta.json",
            "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v352.json",
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V352.json",
            "test_tablet_gpt_tcg_grader_sync_v352.py",
        }
        self.assertEqual(expected, set(candidate["generation_files"]))
        self.assertTrue(expected.issubset(set(watch["exclude_paths"])))
        for path in expected:
            self.assertTrue((ROOT / path).is_file(), path)

    def test_static_candidate_output_remains_fail_closed_and_provenanced(self):
        report = read(ROOT / "auto_update_report.json")
        issues = read(ROOT / "auto_update_issues.json")
        fx = read(ROOT / "exchange_rates.json")
        grading = read(ROOT / "grading_company_updates.json")
        self.assertTrue(report["ok"])
        self.assertEqual(0, report["fresh_failure_count"])
        self.assertGreaterEqual(report["fresh_success_count"], 1)
        self.assertIsInstance(issues.get("issues"), list)
        self.assertEqual("정상", fx["collection_status"])
        for key in ("JPY_KRW", "USD_KRW"):
            value = fx["rates"][key]
            self.assertTrue(math.isfinite(value) and value > 0)
        self.assertIsInstance(grading, dict)
        self.assertNotEqual({}, grading)


if __name__ == "__main__":
    unittest.main(verbosity=2)
