#!/usr/bin/env python3
"""V566 exact reviewed candidate and hash-linked learning capsule; no physical device claims."""
import hashlib
import json
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parent
CP=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V566.json"
DP=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v566_delta.json"
RP=ROOT/"TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v566.json"
SOURCE="952ac438d035bfc3af01550c30d63e25fcd35ad3"
CANDIDATE="9569fc69f64453743e889ff626e43a8d04946c55"
WATCHED=["index.html","sw.js","tablet_runtime_manifest.py","tcg_updater.py"]

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

class RegistryPriceDetailSyncV566(unittest.TestCase):
    def test_exact_functional_candidate_and_safe_historical_successor(self):
        c,d,r=map(read,(CP,DP,RP))
        prior=read(ROOT/c["prior_contract"])
        previous=read(ROOT/c["prior_delta_snapshot"])
        candidate=c["candidate_sync"]
        self.assertEqual(candidate["base_main_sha"],SOURCE)
        self.assertEqual(candidate["candidate_commit"],CANDIDATE)
        self.assertEqual(candidate["functional_candidate_commit"],CANDIDATE)
        self.assertEqual(candidate["watched_paths"],WATCHED)
        self.assertEqual(c["freshness_watch"]["exact_paths"],WATCHED)
        self.assertEqual([],c["freshness_watch"]["path_prefixes"])
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        self.assertEqual(set(candidate["generation_files"]),{
            CP.relative_to(ROOT).as_posix(),DP.relative_to(ROOT).as_posix(),
            RP.relative_to(ROOT).as_posix(),"test_tablet_gpt_tcg_grader_sync_v566.py"
        })
        self.assertTrue(set(candidate["generation_files"]).issubset(
            set(c["freshness_watch"]["exclude_paths"])))
        self.assertEqual(prior["current_required_lesson_count"]+1,c["current_required_lesson_count"])
        self.assertEqual(c["prior_required_lesson_count"],prior["current_required_lesson_count"])
        self.assertEqual(c["delta_required_lesson_count"],1)
        self.assertEqual(c["current_required_merge_prs"],prior["current_required_merge_prs"])
        for commit in (SOURCE,CANDIDATE):
            subprocess.run(["git","merge-base","--is-ancestor",commit,"HEAD"],
                           cwd=ROOT,check=True,timeout=20)
        visible=subprocess.check_output(["git","diff","--name-only",f"{SOURCE}..{CANDIDATE}"],
                   cwd=ROOT,text=True,timeout=20).splitlines()
        self.assertEqual(sorted(set(WATCHED)&set(visible)),WATCHED)
        after=subprocess.check_output(["git","diff","--name-only",f"{CANDIDATE}..HEAD"],
                   cwd=ROOT,text=True,timeout=20).splitlines()
        self.assertEqual([],sorted(set(WATCHED)&set(after)),
                         "V566 runtime code changed without new audited successor")

    def test_learning_capsule_digest_and_no_live_claims(self):
        c,d,r=map(read,(CP,DP,RP))
        prior=read(ROOT/c["prior_delta_snapshot"])
        serialized=json.dumps(d["lessons"],ensure_ascii=False,sort_keys=True,
                              separators=(",",":")).encode("utf-8")
        digest=hashlib.sha256(serialized).hexdigest()
        self.assertEqual(digest,d["lesson_digest_sha256"])
        self.assertEqual(digest,r["delta_lesson_digest_sha256"])
        self.assertEqual(prior["lesson_digest_sha256"],d["prior_lesson_digest_sha256"])
        self.assertEqual(d["prior_lesson_digest_sha256"],r["prior_lesson_digest_sha256"])
        self.assertEqual(d["source_main_sha"],SOURCE)
        self.assertEqual(r["source_main_sha"],SOURCE)
        self.assertEqual([x["lesson_id"] for x in d["lessons"]],r["accepted_lesson_ids"])
        self.assertEqual("SYNCED_VERIFIED",r["status"])
        self.assertEqual("TABLET_GPT_TCG_GRADER_MATCH",r["verification"]["verified_result"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])
        self.assertFalse(d["share_policy"]["non_core_grading_enabled"])
        self.assertFalse(d["share_policy"]["cloud_upload_enabled"])
        self.assertFalse(d["share_policy"]["unverified_price_invention"])

if __name__=="__main__":
    unittest.main()
