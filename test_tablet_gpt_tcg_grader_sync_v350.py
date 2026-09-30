import hashlib
import json
import math
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parent
SOURCE = "f1e43e5b536d50e858376b88b2051257d1f2d969"
DELTA = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v350_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v350.json"
CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V350.json"
PRIOR_CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V349.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


class TabletGptTcgGraderSyncV350(unittest.TestCase):
    def test_digest_lineage_receipt_and_safe_transfer_boundary(self):
        delta, receipt, contract, prior = map(read, (DELTA, RECEIPT, CONTRACT, PRIOR_CONTRACT))
        raw = json.dumps(delta["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.assertEqual("cd46abb3890edd2aca82cd2653a3330377845aa32b8f6e863c81a689e003bc17", digest)
        self.assertEqual(digest, delta["lesson_digest_sha256"])
        self.assertEqual(digest, receipt["delta_lesson_digest_sha256"])
        self.assertEqual(SOURCE, delta["source_main_sha"])
        self.assertEqual(SOURCE, receipt["source_main_sha"])
        self.assertEqual({316, 318}, {row["pr"] for row in delta["covered_merges"]})
        self.assertEqual(
            set(contract["current_required_merge_prs"]),
            set(prior["current_required_merge_prs"]) | {316, 318},
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

        candidate_commit = candidate["candidate_commit"]
        changed = subprocess.check_output(
            ["git", "diff", "--name-only", f"{SOURCE}..{candidate_commit}"], text=True
        ).splitlines()
        relevant = sorted(path for path in changed if watched(path))
        self.assertEqual(candidate["watched_paths"], relevant)
        subprocess.run(["git", "merge-base", "--is-ancestor", candidate_commit, "HEAD"], check=True)
        for path in candidate["generation_files"]:
            self.assertTrue((ROOT / path).is_file(), path)

    def test_fx_and_grading_candidate_actual_output_provenance(self):
        fx = read(ROOT / "exchange_rates.json")
        self.assertEqual("정상", fx["collection_status"])
        self.assertEqual("frankfurter-v2", fx["source_route"])
        self.assertTrue(fx["source"].startswith("https://api.frankfurter.dev/"))
        self.assertTrue(fx["source_timestamp"].endswith("+00:00"))
        self.assertTrue(fx["updated_at"].endswith("+00:00"))
        for key in ("JPY_KRW", "USD_KRW"):
            value = fx["rates"][key]
            self.assertTrue(math.isfinite(value) and value > 0)
        grading = read(ROOT / "grading_company_updates.json")
        self.assertIsInstance(grading, dict)
        self.assertNotEqual({}, grading)


if __name__ == "__main__":
    unittest.main(verbosity=2)
