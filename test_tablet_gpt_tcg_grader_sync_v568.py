#!/usr/bin/env python3
"""V568 reviewed immutable successor for confirmed-card market identity isolation."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import unittest
from unittest import mock
import sync_v376_successor_test_support as sync

ROOT = Path(__file__).resolve().parent
CP = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V568.json"
DP = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v568_delta.json"
RP = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v568.json"
SOURCE = "a7f9c6e2e14770c10a8a676ee3d860e7c8aa5d13"
OLD_OCR_CANDIDATE = "8e7722dfb50702da36d815d5dc043bbdfa4e15e5"
CANDIDATE = "c4d339a01237a115ca889302c50d1e7c603cfbbb"
OCR_SHA256 = "0c57d5ba537075380c7357682f3eb7d044fdb91fc392a0da2f544b448fe3e2a5"

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

class ConfirmedCardMarketIdentitySyncV568(unittest.TestCase):
    def test_exact_history_and_candidate(self):
        c,d,r=map(read,(CP,DP,RP))
        prior=read(ROOT / c["prior_contract"])
        prior_delta=read(ROOT / c["prior_delta_snapshot"])
        self.assertEqual(c["current_required_lesson_count"],prior["current_required_lesson_count"]+1)
        self.assertEqual(c["current_required_merge_prs"],prior["current_required_merge_prs"])
        self.assertEqual(d["prior_lesson_digest_sha256"],prior_delta["lesson_digest_sha256"])
        self.assertEqual(r["prior_lesson_digest_sha256"],prior_delta["lesson_digest_sha256"])
        self.assertEqual(d["source_main_sha"],SOURCE)
        self.assertEqual(r["source_main_sha"],SOURCE)
        payload=json.dumps(d["lessons"],ensure_ascii=False,sort_keys=True,separators=(",",":"))
        self.assertEqual(d["lesson_digest_sha256"],hashlib.sha256(payload.encode("utf-8")).hexdigest())
        self.assertEqual(r["delta_lesson_digest_sha256"],d["lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in d["lessons"]],r["accepted_lesson_ids"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])
        self.assertFalse(d["share_policy"]["cloud_upload_enabled"])
        self.assertFalse(d["share_policy"]["non_core_grading_enabled"])
        self.assertEqual(["card_identity_recognition.py"],c["candidate_sync"]["watched_paths"])
        self.assertEqual(["card_identity_recognition.py"],c["freshness_watch"]["exact_paths"])
        sync.assert_v568_successor(self)

    def test_historical_pins_and_unreviewed_edits_fail_closed(self):
        path="card_identity_recognition.py"
        current=hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
        self.assertEqual(OCR_SHA256,current)
        base=subprocess.check_output(["git","show",f"{SOURCE}:{path}"],cwd=ROOT)
        old=subprocess.check_output(["git","show",f"{OLD_OCR_CANDIDATE}:{path}"],cwd=ROOT)
        newer=subprocess.check_output(["git","show",f"{CANDIDATE}:{path}"],cwd=ROOT)
        self.assertEqual(sync.V620_OCR_SHA256,hashlib.sha256(base).hexdigest())
        self.assertEqual(sync.V567_OCR_SHA256,hashlib.sha256(old).hexdigest())
        self.assertEqual(sync.V568_OCR_SHA256,hashlib.sha256(newer).hexdigest())
        self.assertEqual([path],subprocess.check_output(["git","diff","--name-only",f"{OLD_OCR_CANDIDATE}..{CANDIDATE}"],cwd=ROOT,text=True).splitlines())
        self.assertEqual([],sync.preserve_reviewed_v620_ocr_scope([path],sync.V377_CANDIDATE))
        for name in ("V568_OCR_SHA256","V567_OCR_SHA256","V620_OCR_SHA256","V620_OCR_BASE_SHA256"):
            with self.subTest(name=name),mock.patch.object(sync,name,"0"*64):
                self.assertEqual([path],sync.preserve_reviewed_v620_ocr_scope([path],sync.V377_CANDIDATE))

if __name__=="__main__":
    unittest.main(verbosity=2)
