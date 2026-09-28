import hashlib
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parent
SOURCE = "c649f79f3183d615171a79a89af8731cc19c2398"
DELTA = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v351_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v351.json"
CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V351.json"
PRIOR_CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V350.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


class TabletGptTcgGraderSyncV351(unittest.TestCase):
    def test_digest_lineage_receipt_and_safe_transfer_boundary(self):
        delta, receipt, contract, prior = map(read, (DELTA, RECEIPT, CONTRACT, PRIOR_CONTRACT))
        raw = json.dumps(delta["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.assertEqual("2329aa215e51444f3271717924409549883865ccb88fd1878d6ce2aff2323025", digest)
        self.assertEqual(digest, delta["lesson_digest_sha256"])
        self.assertEqual(digest, receipt["delta_lesson_digest_sha256"])
        self.assertEqual(SOURCE, delta["source_main_sha"])
        self.assertEqual(SOURCE, receipt["source_main_sha"])
        self.assertEqual({320}, {row["pr"] for row in delta["covered_merges"]})
        self.assertEqual(
            set(contract["current_required_merge_prs"]),
            set(prior["current_required_merge_prs"]) | {320},
        )
        self.assertEqual([row["lesson_id"] for row in delta["lessons"]], receipt["accepted_lesson_ids"])
        self.assertEqual("SYNCED_VERIFIED", receipt["status"])
        self.assertFalse(delta["share_policy"]["chatgpt_model_weights_exported"])
        self.assertFalse(delta["share_policy"]["raw_grading_calibration_shared"])
        self.assertFalse(delta["share_policy"]["device_local_runtime_memory_overwritten"])
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])

    def test_exact_candidate_watched_path_set_and_generation_files(self):
        contract = read(CONTRACT)
        candidate = contract["candidate_sync"]
        self.assertEqual(SOURCE, candidate["base_main_sha"])
        self.assertTrue(candidate["requires_exact_watched_path_match"])
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
        for path in candidate["generation_files"]:
            self.assertTrue((ROOT / path).is_file(), path)

    def test_drive_package_external_hold_stays_fail_closed(self):
        workflow = (ROOT / ".github/workflows/gpt-tcg-drive-package.yml").read_text(encoding="utf-8")
        policy = (ROOT / "drive_package_hold_policy.py").read_text(encoding="utf-8")
        self.assertIn("EXTERNAL_PROVIDER_DEGRADED_HOLD", workflow)
        self.assertIn("python drive_package_hold_policy.py COLLECTION_VERIFICATION_REPORT.json", workflow)
        self.assertIn("ready=false", workflow)
        self.assertIn("steps.package.outputs.ready == 'true'", workflow)
        self.assertIn("STALE_AUTO_UPDATE_REPORT", workflow)
        self.assertIn("FRESH_STATIC_REFRESH_DISPATCHED", workflow)
        self.assertNotIn("--max-report-age-hours 12", workflow)
        self.assertIn("GRADING_COMPANY_NO_HEALTHY_SOURCE", policy)
        self.assertIn("DEGRADED_COLLECTION_OUTPUT", policy)
        self.assertIn("INVALID_MARKET_ENTRY", (ROOT / "test_drive_package_hold_policy_v351.py").read_text(encoding="utf-8"))
        rules = read(CONTRACT)["rules"]
        self.assertTrue(rules["degraded_drive_package_must_not_upload_artifact"])
        self.assertTrue(rules["external_provider_hold_requires_whitelisted_evidence"])
        self.assertTrue(rules["unknown_or_data_quality_degradation_must_remain_failure"])
        self.assertTrue(rules["freshness_threshold_widening_forbidden"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
