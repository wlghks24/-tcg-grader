#!/usr/bin/env python3
"""V572 exact BOX UI successor: prove historical main ancestry and pinned bytes.

Not a claim of runtime Lenovo installation. No historical gate is waived.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import sync_v376_successor_test_support as support

BASE = "a7f9c6e2e14770c10a8a676ee3d860e7c8aa5d13"
CANDIDATE = "be58c58f3c7f879776c0759652d04464c9f72e71"
WATCHED = ["box_knowledge_stats.css", "box_knowledge_stats.js"]
CP = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V572.json"
DP = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v572_delta.json"
RP = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v572.json"
OWN = "execution/test_tablet_gpt_tcg_grader_sync_v572.py"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class VerifiedBoxMarketQuoteSuccessorV572(unittest.TestCase):
    def test_exact_candidate_frozen_before_new_generation(self):
        c, d, r = load(CP), load(DP), load(RP)
        prev_c = load(ROOT / c["prior_contract"])
        prev_d = load(ROOT / c["prior_delta_snapshot"])
        candidate = c["candidate_sync"]
        self.assertEqual(BASE, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE, candidate["candidate_commit"])
        self.assertEqual(CANDIDATE, candidate["functional_candidate_commit"])
        self.assertEqual(WATCHED, candidate["watched_paths"])
        self.assertEqual(WATCHED, c["freshness_watch"]["exact_paths"])
        self.assertEqual([], c["freshness_watch"]["path_prefixes"])
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertEqual(set([CP.relative_to(ROOT).as_posix(),
                              DP.relative_to(ROOT).as_posix(),
                              RP.relative_to(ROOT).as_posix(), OWN]),
                         set(candidate["generation_files"]))
        self.assertTrue(set(candidate["generation_files"]).issubset(set(c["freshness_watch"]["exclude_paths"])))
        self.assertEqual(prev_c["current_required_lesson_count"] + 1, c["current_required_lesson_count"])
        self.assertEqual(c["prior_required_lesson_count"], prev_c["current_required_lesson_count"])
        self.assertEqual(1, c["delta_required_lesson_count"])
        self.assertEqual(c["current_required_merge_prs"], prev_c["current_required_merge_prs"])
        for commit in (BASE, CANDIDATE):
            subprocess.run(["git","merge-base","--is-ancestor",commit,"HEAD"],
                           cwd=ROOT, check=True,timeout=20)
        scope = subprocess.check_output(["git","diff","--name-only",
            f"{BASE}..{CANDIDATE}","--",*WATCHED],cwd=ROOT,text=True,timeout=20).splitlines()
        self.assertEqual(WATCHED,scope)
        subsequent = subprocess.check_output(["git","diff","--name-only",
            f"{CANDIDATE}..HEAD","--",*WATCHED],cwd=ROOT,text=True,timeout=20).splitlines()
        self.assertEqual([],subsequent)
        self.assertEqual(support.V572_BOX_BASE, BASE)
        self.assertEqual(support.V572_BOX_CANDIDATE, CANDIDATE)

    def test_verified_lesson_digest_and_separate_device_hold(self):
        c,d,r=load(CP),load(DP),load(RP)
        prior=load(ROOT/c["prior_delta_snapshot"])
        raw=json.dumps(d["lessons"],ensure_ascii=False,sort_keys=True,
                       separators=(",",":")).encode("utf-8")
        sha=hashlib.sha256(raw).hexdigest()
        self.assertEqual(sha,d["lesson_digest_sha256"])
        self.assertEqual(sha,r["delta_lesson_digest_sha256"])
        self.assertEqual(prior["lesson_digest_sha256"],d["prior_lesson_digest_sha256"])
        self.assertEqual(prior["lesson_digest_sha256"],r["prior_lesson_digest_sha256"])
        self.assertEqual(d["source_main_sha"],BASE)
        self.assertEqual(r["source_main_sha"],BASE)
        self.assertEqual([x["lesson_id"] for x in d["lessons"]],r["accepted_lesson_ids"])
        self.assertEqual("SYNCED_VERIFIED",r["status"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])
        self.assertFalse(d["share_policy"]["non_core_grading_enabled"])
        self.assertFalse(d["share_policy"]["cloud_upload_enabled"])
        self.assertFalse(d["share_policy"]["unverified_price_invention"])

    def test_approved_successor_is_exact_scoped_and_tamper_rejected(self):
        visible=WATCHED+["unreviewed_change.py"]
        reviewed=support.preserve_reviewed_v572_box_scope(visible,support.V479_CANDIDATE)
        self.assertEqual(["unreviewed_change.py"],reviewed)
        self.assertEqual(visible,support.preserve_reviewed_v572_box_scope(visible,support.V479_CANDIDATE,head=BASE))
        self.assertEqual(visible,support.preserve_reviewed_v572_box_scope(visible,"unknown-history"))
        with mock.patch.object(support,"V572_BOX_BLOBS",
                               {"box_knowledge_stats.css":"invalid","box_knowledge_stats.js":"invalid"}):
            self.assertEqual(visible,support.preserve_reviewed_v572_box_scope(visible,support.V479_CANDIDATE))
        with mock.patch.object(support,"V572_BOX_CANDIDATE","0"*40):
            self.assertEqual(visible,support.preserve_reviewed_v572_box_scope(visible,support.V479_CANDIDATE))
        with mock.patch.object(support,"V572_BOX_BASE","0"*40):
            self.assertEqual(visible,support.preserve_reviewed_v572_box_scope(visible,support.V479_CANDIDATE))

    def test_ui_source_read_only_unchanged_grading(self):
        js=(ROOT/"box_knowledge_stats.js").read_text(encoding="utf-8")
        self.assertIn("window.TCGBoxPriceProofV572",js)
        self.assertIn("판매추천가 보류",js)
        self.assertIn("new MutationObserver",js)
        self.assertNotIn("eval(",js[js.index("/* V572: BOX observed"):])
        self.assertNotIn("localStorage.setItem",js[js.index("/* V572: BOX observed"):])


if __name__ == "__main__":
    unittest.main()
