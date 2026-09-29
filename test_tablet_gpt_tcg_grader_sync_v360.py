import hashlib
import json
import math
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parent
SOURCE="90576f8d33680470cca3a1e770618132a995b93e"
CANDIDATE="2186be2fcc11a084e5700eef6ead3b2b8b13702f"
PRIOR=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v359_delta.json"
DELTA=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v360_delta.json"
RECEIPT=ROOT/"TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v360.json"
PRIOR_CONTRACT=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V359.json"
CONTRACT=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V360.json"
EXPECTED_DIGEST="25a57897537a216f61620ce5e99bf761ea824067199a24a54653eb6e258897fd"

def read(p):
    return json.loads(p.read_text(encoding="utf-8"))

class TabletGptTcgGraderSyncV360(unittest.TestCase):
    def test_lineage_digest_receipt_and_safe_transfer_boundary(self):
        prior,delta,receipt,pc,c=map(read,(PRIOR,DELTA,RECEIPT,PRIOR_CONTRACT,CONTRACT))
        self.assertEqual(prior["lesson_digest_sha256"],delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"],receipt["prior_lesson_digest_sha256"])
        self.assertEqual(SOURCE,delta["source_main_sha"])
        self.assertEqual(SOURCE,receipt["source_main_sha"])
        self.assertEqual([335,337],[r["pr"] for r in delta["covered_merges"]])
        self.assertEqual(set(c["current_required_merge_prs"]),set(pc["current_required_merge_prs"])|{335,337})
        self.assertEqual(pc["current_required_lesson_count"],c["prior_required_lesson_count"])
        self.assertEqual(c["prior_required_lesson_count"]+c["delta_required_lesson_count"],c["current_required_lesson_count"])
        raw=json.dumps(delta["lessons"],ensure_ascii=False,sort_keys=True,separators=(",",":"))
        digest=hashlib.sha256(raw.encode()).hexdigest()
        self.assertEqual(EXPECTED_DIGEST,digest)
        self.assertEqual(digest,delta["lesson_digest_sha256"])
        self.assertEqual(digest,receipt["delta_lesson_digest_sha256"])
        self.assertEqual([r["lesson_id"] for r in delta["lessons"]],receipt["accepted_lesson_ids"])
        self.assertEqual("SYNCED_VERIFIED",receipt["status"])
        self.assertFalse(delta["share_policy"]["chatgpt_model_weights_exported"])
        self.assertFalse(delta["share_policy"]["raw_grading_calibration_shared"])
        self.assertFalse(delta["share_policy"]["device_local_runtime_memory_overwritten"])
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])
        for sha in (SOURCE,CANDIDATE,"cf721e4367cb982733958076165c26ae92773abf"):
            subprocess.run(["git","merge-base","--is-ancestor",sha,"HEAD"],check=True)

    def test_exact_candidate_watched_path_set_and_generation_files(self):
        c=read(CONTRACT); cand=c["candidate_sync"]
        self.assertEqual(SOURCE,cand["base_main_sha"])
        self.assertEqual(CANDIDATE,cand["candidate_commit"])
        self.assertTrue(cand["requires_exact_watched_path_match"])
        self.assertTrue(cand["post_merge_coverage_allowed"])
        w=c["freshness_watch"]; exact=set(w["exact_paths"]); prefixes=tuple(w["path_prefixes"]); excluded=set(w["exclude_paths"])
        changed=subprocess.check_output(["git","diff","--name-only",f"{SOURCE}..HEAD"],text=True).splitlines()
        relevant=sorted(p for p in changed if p not in excluded and (p in exact or p.startswith(prefixes)))
        self.assertEqual(cand["watched_paths"],relevant)
        expected=set(cand["generation_files"])
        self.assertEqual({'TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v360_delta.json', 'TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v360.json', 'test_tablet_gpt_tcg_grader_sync_v360.py', 'TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V360.json'},expected)
        self.assertTrue(expected.issubset(excluded))
        [self.assertTrue((ROOT/p).is_file(),p) for p in expected]

    def test_static_candidate_is_fresh_and_fail_closed(self):
        report=read(ROOT/"auto_update_report.json")
        fx=read(ROOT/"exchange_rates.json")
        grading=read(ROOT/"grading_company_updates.json")
        self.assertTrue(report["ok"])
        self.assertEqual(0,report["fresh_failure_count"])
        self.assertGreaterEqual(report["fresh_success_count"],1)
        self.assertEqual("정상",fx["collection_status"])
        for key in ("JPY_KRW","USD_KRW"):
            self.assertTrue(math.isfinite(fx["rates"][key]) and fx["rates"][key]>0)
        self.assertIsInstance(grading,dict)
        self.assertNotEqual({},grading)

if __name__=="__main__":
    unittest.main(verbosity=2)
