import hashlib
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parent
PRIOR = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v349_delta.json"
DELTA = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v350_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v350.json"
PRIOR_CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V349.json"
CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V350.json"
SOURCE = "f1e43e5b536d50e858376b88b2051257d1f2d969"

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

class TabletGptTcgGraderSyncV350(unittest.TestCase):
    def test_checkpoint_lineage_digest_and_safe_receipt(self):
        prior, delta, receipt, prior_contract, contract = map(read, (PRIOR, DELTA, RECEIPT, PRIOR_CONTRACT, CONTRACT))
        self.assertEqual(prior["lesson_digest_sha256"], delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"], receipt["prior_lesson_digest_sha256"])
        self.assertEqual(SOURCE, delta["source_main_sha"])
        self.assertEqual(SOURCE, receipt["source_main_sha"])
        self.assertEqual([316, 318], [row["pr"] for row in delta["covered_merges"]])
        self.assertEqual({316, 318}, set(contract["current_required_merge_prs"]) - set(prior_contract["current_required_merge_prs"]))
        raw = json.dumps(delta["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.assertEqual("f99cf7f6d7865136f341076f12a5f4c7777c0f6156e696ca239292e001fe7b27", digest)
        self.assertEqual(digest, delta["lesson_digest_sha256"])
        self.assertEqual(digest, receipt["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in delta["lessons"]], receipt["accepted_lesson_ids"])
        self.assertEqual("SYNCED_VERIFIED", receipt["status"])
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])

    def test_static_outputs_are_excluded_but_executable_runtime_paths_remain_watched(self):
        contract = read(CONTRACT)
        watch = contract["freshness_watch"]
        exact = set(watch["exact_paths"])
        prefixes = tuple(watch["path_prefixes"])
        excluded = set(watch["exclude_paths"])
        def watched(path):
            return path not in excluded and (path in exact or path.startswith(prefixes))
        for path in contract["static_public_outputs"]:
            self.assertIn(path, excluded)
            self.assertFalse(watched(path), path)
        self.assertTrue(watched("grading_company_watch.py"))
        self.assertTrue(watched("grade_market_flow.js"))
        self.assertTrue(watched(".github/workflows/gpt-tcg-drive-package.yml"))

    def test_checkpoint_exactly_covers_watched_changes_since_v349(self):
        prior_source = read(PRIOR)["source_main_sha"]
        contract = read(CONTRACT)
        watch = contract["freshness_watch"]
        exact = set(watch["exact_paths"])
        prefixes = tuple(watch["path_prefixes"])
        excluded = set(watch["exclude_paths"])
        def watched(path):
            return path not in excluded and (path in exact or path.startswith(prefixes))
        changed = subprocess.check_output(["git", "diff", "--name-only", f"{prior_source}..{SOURCE}"], text=True).splitlines()
        relevant = sorted(path for path in changed if watched(path))
        self.assertEqual(sorted(contract["checkpoint_covered_watched_paths"]), relevant)

    def test_generation_is_complete_and_excluded(self):
        contract = read(CONTRACT)
        expected = {
            "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v350_delta.json",
            "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v350.json",
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V350.json",
            "test_tablet_gpt_tcg_grader_sync_v350.py",
        }
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v350_delta.json", contract["delta_snapshot"])
        self.assertEqual("TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v350.json", contract["receiver_receipt"])
        self.assertEqual("test_tablet_gpt_tcg_grader_sync_v350.py", contract["verification_test"])
        self.assertTrue(expected.issubset(set(contract["freshness_watch"]["exclude_paths"])))
        for path in expected:
            self.assertTrue((ROOT / path).is_file(), path)

if __name__ == "__main__":
    unittest.main(verbosity=2)
