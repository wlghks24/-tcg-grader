#!/usr/bin/env python3
"""Pinned V640 successor coverage for reviewed BOX assets, without device claims."""
from __future__ import annotations
import json
import subprocess
import unittest
from pathlib import Path
from sync_v376_successor_test_support import assert_v640_successor

ROOT=Path(__file__).resolve().parents[1]
CONTRACT=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V640.json"
DELTA=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v640_delta.json"
RECEIPT=ROOT/"TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v640.json"

class VerifiedBoxSuccessorV640(unittest.TestCase):
    def test_box_successor_only_for_exact_reviewed_candidate(self):
        assert_v640_successor(self)
    def test_boundaries_and_explicit_device_hold(self):
        c=json.loads(CONTRACT.read_text(encoding="utf-8"))
        d=json.loads(DELTA.read_text(encoding="utf-8"))
        r=json.loads(RECEIPT.read_text(encoding="utf-8"))
        self.assertEqual(["box_knowledge_stats.css","box_knowledge_stats.js"],c["candidate_sync"]["watched_paths"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])
        self.assertFalse(d["share_policy"]["unverified_price_invention"])
        self.assertFalse(d["share_policy"]["cloud_upload_enabled"])
        src=(ROOT/"box_knowledge_stats.js").read_text(encoding="utf-8")
        for token in ("boxMarketAssessment","boxSafeSource","boxParseRange","판매추천가","officialBoxPriceText"):
            self.assertIn(token,src)
        css=(ROOT/"box_knowledge_stats.css").read_text(encoding="utf-8")
        self.assertIn("boxkb-market-price-grid",css)

if __name__=="__main__":
    unittest.main(verbosity=2)
