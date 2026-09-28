import hashlib
import json
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parent
SOURCE="c5b464830b251b23be3337118f5bc93518f7dc7e"
DELTA=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v348_delta.json"
RECEIPT=ROOT/"TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v348.json"
CONTRACT=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V348.json"

def read(path):return json.loads(path.read_text(encoding="utf-8"))

class TabletGptTcgGraderSyncV348(unittest.TestCase):
    def test_digest_receipt_and_safe_transfer_boundary(self):
        delta,receipt,contract=map(read,(DELTA,RECEIPT,CONTRACT))
        raw=json.dumps(delta["lessons"],ensure_ascii=False,sort_keys=True,separators=(",",":"))
        digest=hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.assertEqual("8c320d96ee70d10eedfc1f45e2cbcc111e569776eda5642c6608b9110e774d09",digest)
        self.assertEqual(digest,delta["lesson_digest_sha256"])
        self.assertEqual(digest,receipt["delta_lesson_digest_sha256"])
        self.assertEqual(SOURCE,delta["source_main_sha"])
        self.assertEqual(SOURCE,receipt["source_main_sha"])
        self.assertEqual([row["lesson_id"] for row in delta["lessons"]],receipt["accepted_lesson_ids"])
        self.assertEqual("SYNCED_VERIFIED",receipt["status"])
        self.assertFalse(delta["share_policy"]["chatgpt_model_weights_exported"])
        self.assertFalse(delta["share_policy"]["raw_grading_calibration_shared"])
        self.assertFalse(delta["share_policy"]["device_local_runtime_memory_overwritten"])
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])
        self.assertTrue(contract["rules"]["fx_collection_and_source_timestamps_must_both_be_fresh"])

    def test_exact_candidate_watched_path_set(self):
        contract=read(CONTRACT)
        candidate=contract["candidate_sync"]
        self.assertEqual(SOURCE,candidate["base_main_sha"])
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        watch=contract["freshness_watch"]
        exact=set(watch["exact_paths"]);prefixes=tuple(watch["path_prefixes"]);excluded=set(watch["exclude_paths"])
        def watched(path):return path not in excluded and (path in exact or path.startswith(prefixes))
        changed=subprocess.check_output(["git","diff","--name-only",f"{SOURCE}..HEAD"],text=True).splitlines()
        relevant=sorted(path for path in changed if watched(path))
        self.assertEqual(candidate["watched_paths"],relevant)
        for path in candidate["generation_files"]:self.assertTrue((ROOT/path).is_file(),path)

    def test_unrelated_pr_reuses_exact_verified_mainline_candidate_without_weakening_watch(self):
        workflow=(ROOT/".github/workflows/tablet-gpt-tcg-grader-main-alignment.yml").read_text(encoding="utf-8")
        self.assertIn("if relevant and candidate:",workflow)
        self.assertNotIn("if event_name != 'pull_request' and relevant and candidate:",workflow)
        self.assertIn("later_watched.update(path for path in touched if watched(path))",workflow)
        self.assertIn("and not later_watched",workflow)
        self.assertIn("expected_watched == set(relevant)",workflow)
        self.assertIn("source == base_sha == candidate_base",workflow)
        self.assertIn("TABLET_GPT_SYNC_STALE",workflow)

if __name__=="__main__":unittest.main(verbosity=2)
