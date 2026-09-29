import hashlib
import json
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parent
SOURCE="14a509e5e594711be8b851f1942f2270cb1b3d69"
CANDIDATE="25a3e635475da4615095f471b74b186fba5e4260"
PRIOR=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v360_delta.json"
DELTA=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v361_delta.json"
RECEIPT=ROOT/"TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v361.json"
PRIOR_CONTRACT=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V360.json"
CONTRACT=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V361.json"
WORKFLOW=ROOT/".github/workflows/gpt-tcg-drive-package.yml"
EXPECTED_DIGEST="5b144584a3740b5025223295b626da0818549256d31fa9331087b3324935c961"

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

class TabletGptTcgGraderSyncV361(unittest.TestCase):
    def test_lineage_digest_receipt_and_safe_transfer_boundary(self):
        prior,delta,receipt,pc,c=map(read,(PRIOR,DELTA,RECEIPT,PRIOR_CONTRACT,CONTRACT))
        self.assertEqual(prior["lesson_digest_sha256"],delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"],receipt["prior_lesson_digest_sha256"])
        self.assertEqual(SOURCE,delta["source_main_sha"])
        self.assertEqual(SOURCE,receipt["source_main_sha"])
        self.assertEqual([338],[r["pr"] for r in delta["covered_merges"]])
        self.assertEqual(SOURCE,delta["covered_merges"][0]["merge_sha"])
        self.assertEqual(set(c["current_required_merge_prs"]),set(pc["current_required_merge_prs"])|{338})
        self.assertEqual(pc["current_required_lesson_count"],c["prior_required_lesson_count"])
        self.assertEqual(c["prior_required_lesson_count"]+c["delta_required_lesson_count"],c["current_required_lesson_count"])
        raw=json.dumps(delta["lessons"],ensure_ascii=False,sort_keys=True,separators=(",",":"))
        digest=hashlib.sha256(raw.encode()).hexdigest()
        self.assertEqual(EXPECTED_DIGEST,digest)
        self.assertEqual(digest,delta["lesson_digest_sha256"])
        self.assertEqual(digest,receipt["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in delta["lessons"]],receipt["accepted_lesson_ids"])
        self.assertEqual("SYNCED_VERIFIED",receipt["status"])
        self.assertFalse(delta["share_policy"]["chatgpt_model_weights_exported"])
        self.assertFalse(delta["share_policy"]["raw_grading_calibration_shared"])
        self.assertFalse(delta["share_policy"]["device_local_runtime_memory_overwritten"])
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])
        for sha in (SOURCE,CANDIDATE):
            subprocess.run(["git","merge-base","--is-ancestor",sha,"HEAD"],check=True)

    def test_exact_watched_path_and_complete_generation(self):
        c=read(CONTRACT); cand=c["candidate_sync"]; watch=c["freshness_watch"]
        self.assertEqual(SOURCE,cand["base_main_sha"])
        self.assertEqual(CANDIDATE,cand["candidate_commit"])
        changed=subprocess.check_output(["git","diff","--name-only",f"{SOURCE}..HEAD"],text=True).splitlines()
        exact=set(watch["exact_paths"]); prefixes=tuple(watch["path_prefixes"]); excluded=set(watch["exclude_paths"])
        relevant=sorted(p for p in changed if p not in excluded and (p in exact or p.startswith(prefixes)))
        self.assertEqual(cand["watched_paths"],relevant)
        expected=set(cand["generation_files"])
        self.assertEqual({"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V361.json","TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v361_delta.json","TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v361.json","test_tablet_gpt_tcg_grader_sync_v361.py"},expected)
        self.assertTrue(expected.issubset(excluded))
        [self.assertTrue((ROOT/path).is_file(),path) for path in expected]

    def test_upload_artifact_explicitly_includes_hidden_outbox_without_weakening_gates(self):
        workflow=WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",workflow)
        self.assertIn("path: .tcg_drive_outbox/*",workflow)
        self.assertIn("include-hidden-files: true",workflow)
        self.assertIn("if-no-files-found: error",workflow)
        self.assertIn("STALE_AUTO_UPDATE_REPORT",workflow)
        self.assertIn("FRESH_STATIC_REFRESH_DISPATCHED",workflow)
        self.assertIn("never widen the two-hour report freshness gate",workflow)

if __name__=="__main__":
    unittest.main(verbosity=2)
