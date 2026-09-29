import hashlib
import json
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parent
SOURCE="901f83e7e0e25254676f079a1b275411ff2b168d"
PRIOR=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v358_delta.json"
DELTA=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v359_delta.json"
RECEIPT=ROOT/"TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v359.json"
PRIOR_CONTRACT=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V358.json"
CONTRACT=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V359.json"
EXPECTED_DIGEST="fbf9c5bccb753feaee6a458e9c128e60e83b3629b43cec22006021c4195a355b"

def read(p): return json.loads(p.read_text(encoding="utf-8"))

class TabletGptTcgGraderSyncV359(unittest.TestCase):
    def test_postmerge_checkpoint_lineage_digest_and_safe_receipt(self):
        prior,delta,receipt,pc,c=map(read,(PRIOR,DELTA,RECEIPT,PRIOR_CONTRACT,CONTRACT))
        self.assertEqual(prior["lesson_digest_sha256"],delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"],receipt["prior_lesson_digest_sha256"])
        self.assertEqual(SOURCE,delta["source_main_sha"])
        self.assertEqual(SOURCE,receipt["source_main_sha"])
        self.assertEqual([334],[r["pr"] for r in delta["covered_merges"]])
        self.assertEqual(SOURCE,delta["covered_merges"][0]["merge_sha"])
        self.assertEqual(set(c["current_required_merge_prs"]),set(pc["current_required_merge_prs"])|{334})
        self.assertEqual(pc["current_required_lesson_count"],c["prior_required_lesson_count"])
        self.assertEqual(c["prior_required_lesson_count"]+c["delta_required_lesson_count"],c["current_required_lesson_count"])
        raw=json.dumps(delta["lessons"],ensure_ascii=False,sort_keys=True,separators=(",",":"))
        d=hashlib.sha256(raw.encode()).hexdigest()
        self.assertEqual(EXPECTED_DIGEST,d)
        self.assertEqual(d,delta["lesson_digest_sha256"])
        self.assertEqual(d,receipt["delta_lesson_digest_sha256"])
        self.assertEqual([r["lesson_id"] for r in delta["lessons"]],receipt["accepted_lesson_ids"])
        self.assertEqual("SYNCED_VERIFIED",receipt["status"])
        self.assertFalse(delta["share_policy"]["chatgpt_model_weights_exported"])
        self.assertFalse(delta["share_policy"]["raw_grading_calibration_shared"])
        self.assertFalse(delta["share_policy"]["device_local_runtime_memory_overwritten"])
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])
        subprocess.run(["git","merge-base","--is-ancestor",SOURCE,"HEAD"],check=True)

    def test_current_candidate_has_no_uncovered_watched_change(self):
        c=read(CONTRACT); w=c["freshness_watch"]
        exact=set(w["exact_paths"]); prefixes=tuple(w["path_prefixes"]); excluded=set(w["exclude_paths"])
        changed=subprocess.check_output(["git","diff","--name-only",f"{SOURCE}..HEAD"],text=True).splitlines()
        relevant=sorted(p for p in changed if p not in excluded and (p in exact or p.startswith(prefixes)))
        self.assertEqual([],relevant)
        expected={"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V359.json","TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v359_delta.json","TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v359.json","test_tablet_gpt_tcg_grader_sync_v359.py"}
        self.assertTrue(expected.issubset(excluded))
        [self.assertTrue((ROOT/p).is_file(),p) for p in expected]

    def test_checkpoint_preserves_fail_closed_watch_and_source_boundaries(self):
        c=read(CONTRACT); d=read(DELTA); r=read(RECEIPT)
        self.assertNotIn("candidate_sync",c)
        self.assertIn("grading_",c["freshness_watch"]["path_prefixes"])
        self.assertNotIn("grading_company_updates.json",c["freshness_watch"]["exclude_paths"])
        self.assertTrue(c["rules"]["grading_company_updates_require_verified_delta"])
        self.assertTrue(c["rules"]["watched_changes_after_delta_source_main_must_report_stale_on_main"])
        self.assertFalse(c["rules"]["pull_request_freshness_check_is_nonblocking"])
        self.assertEqual("TABLET_GPT_TCG_GRADER_MATCH",r["verification"]["verified_result"])
        self.assertEqual(SOURCE,d["source_main_sha"])

if __name__=="__main__": unittest.main(verbosity=2)
