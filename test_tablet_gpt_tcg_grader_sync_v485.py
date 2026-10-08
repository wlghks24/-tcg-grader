#!/usr/bin/env python3
"""Exact candidate, evidence scope and receipt lock for V485."""
import hashlib
import json
import unittest
from pathlib import Path

from sync_v376_successor_test_support import assert_v485_successor

ROOT=Path(__file__).resolve().parent
C=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V485.json"
D=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v485_delta.json"
R=ROOT/"TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v485.json"

class SyncV485(unittest.TestCase):
    def test_generation_exact_and_evidence_only(self):
        c,d,r=(json.loads(p.read_text(encoding="utf-8")) for p in (C,D,R))
        h=hashlib.sha256(json.dumps(d["lessons"],ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")).hexdigest()
        self.assertEqual(h,d["lesson_digest_sha256"])
        self.assertEqual(h,r["delta_lesson_digest_sha256"])
        self.assertEqual(d["source_main_sha"],r["source_main_sha"])
        self.assertEqual(["feature_category_nav.css","feature_category_nav.js","index.html"],c["candidate_sync"]["watched_paths"])
        self.assertFalse(d["share_policy"]["cloud_upload_enabled"])
        self.assertFalse(d["share_policy"]["unverified_price_invention"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        assert_v485_successor(self)

if __name__=="__main__":
    unittest.main(verbosity=2)
