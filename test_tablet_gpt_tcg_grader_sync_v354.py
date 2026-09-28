import hashlib
import json
import math
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parent
SOURCE = "59fa7664f54413900c66fc0c2552baaf25e6309b"
CANDIDATE = "11adfc9594fc5305632ec2c16e6cc52519f5f162"
PRIOR = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v353_delta.json"
DELTA = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v354_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v354.json"
PRIOR_CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V353.json"
CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V354.json"
EXPECTED_DIGEST = "64ebdc33098d255ab6acb0ec638aaaa3a8342c622f4f0beb23c757a2e32a6566"

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

class TabletGptTcgGraderSyncV354(unittest.TestCase):
    def test_lineage_digest_receipt_and_safe_transfer_boundary(self):
        prior, delta, receipt, prior_contract, contract = map(read, (PRIOR, DELTA, RECEIPT, PRIOR_CONTRACT, CONTRACT))
        self.assertEqual(prior["lesson_digest_sha256"], delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"], receipt["prior_lesson_digest_sha256"])
        self.assertEqual(SOURCE, delta["source_main_sha"])
        self.assertEqual(SOURCE, receipt["source_main_sha"])
        self.assertEqual([325], [row["pr"] for row in delta["covered_merges"]])
        self.assertEqual(SOURCE, delta["covered_merges"][0]["merge_sha"])
        self.assertEqual(set(contract["current_required_merge_prs"]), set(prior_contract["current_required_merge_prs"]) | {325})
        self.assertEqual(prior_contract["current_required_lesson_count"], contract["prior_required_lesson_count"])
        self.assertEqual(contract["prior_required_lesson_count"] + contract["delta_required_lesson_count"], contract["current_required_lesson_count"])
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
        for sha in (SOURCE, CANDIDATE):
            subprocess.run(["git", "merge-base", "--is-ancestor", sha, "HEAD"], check=True)

    def test_exact_latest_candidate_watched_path_set_and_generation_files(self):
        contract = read(CONTRACT)
        candidate = contract["candidate_sync"]
        self.assertEqual(SOURCE, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE, candidate["candidate_commit"])
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        watch = contract["freshness_watch"]
        exact, prefixes, excluded = set(watch["exact_paths"]), tuple(watch["path_prefixes"]), set(watch["exclude_paths"])
        changed = subprocess.check_output(["git", "diff", "--name-only", f"{SOURCE}..HEAD"], text=True).splitlines()
        relevant = sorted(p for p in changed if p not in excluded and (p in exact or p.startswith(prefixes)))
        self.assertEqual(candidate["watched_paths"], relevant)
        expected = set(candidate["generation_files"])
        self.assertEqual(set(["TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V354.json","TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v354_delta.json","TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v354.json","test_tablet_gpt_tcg_grader_sync_v354.py"]), expected)
        self.assertTrue(expected.issubset(excluded))
        for path in expected:
            self.assertTrue((ROOT / path).is_file(), path)

    def test_static_candidate_output_remains_fail_closed_and_provenanced(self):
        report = read(ROOT / "auto_update_report.json")
        fx = read(ROOT / "exchange_rates.json")
        grading = read(ROOT / "grading_company_updates.json")
        self.assertTrue(report["ok"])
        self.assertEqual(0, report["fresh_failure_count"])
        self.assertGreaterEqual(report["fresh_success_count"], 1)
        self.assertEqual("정상", fx["collection_status"])
        for key in ("JPY_KRW", "USD_KRW"):
            value = fx["rates"][key]
            self.assertTrue(math.isfinite(value) and value > 0)
        self.assertIsInstance(grading, dict)
        self.assertNotEqual({}, grading)

if __name__ == "__main__":
    unittest.main(verbosity=2)
