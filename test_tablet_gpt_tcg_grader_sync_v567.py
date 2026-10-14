#!/usr/bin/env python3
"""V567 audit: exact OCR game isolation successor, immutable V620 evidence retained."""
from __future__ import annotations
import hashlib
import json
import subprocess
import unittest
from pathlib import Path
from unittest import mock

import sync_v376_successor_test_support as sync

ROOT = Path(__file__).resolve().parent
CP = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V567.json"
DP = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v567_delta.json"
RP = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v567.json"
SOURCE = "a7f9c6e2e14770c10a8a676ee3d860e7c8aa5d13"
CANDIDATE = "a17bbe95181e519fda86d25e80de2393bf69ccdb"
OCR_SHA256 = "cce0aa138467183a02b69870e796b9aad2d90d1394e27efc2436142cd5328cf7"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


class ReviewedOcrIsolationSuccessorV567(unittest.TestCase):
    def test_exact_candidate_contract_and_digest(self):
        c, d, r = map(read, (CP, DP, RP))
        prior = read(ROOT / c["prior_contract"])
        prior_delta = read(ROOT / c["prior_delta_snapshot"])
        self.assertEqual(c["current_required_lesson_count"], prior["current_required_lesson_count"] + 1)
        self.assertEqual(c["current_required_merge_prs"], prior["current_required_merge_prs"])
        self.assertEqual(d["prior_lesson_digest_sha256"], prior_delta["lesson_digest_sha256"])
        self.assertEqual(r["prior_lesson_digest_sha256"], prior_delta["lesson_digest_sha256"])
        self.assertEqual(d["source_main_sha"], SOURCE)
        self.assertEqual(r["source_main_sha"], SOURCE)
        raw = json.dumps(d["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.assertEqual(d["lesson_digest_sha256"], digest)
        self.assertEqual(r["delta_lesson_digest_sha256"], digest)
        self.assertEqual(r["accepted_lesson_ids"], [row["lesson_id"] for row in d["lessons"]])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])
        self.assertFalse(d["share_policy"]["cloud_upload_enabled"])
        self.assertFalse(d["share_policy"]["non_core_grading_enabled"])
        self.assertEqual(c["candidate_sync"]["watched_paths"], ["card_identity_recognition.py"])
        self.assertEqual(c["candidate_sync"]["generation_files"], [
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V567.json", "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v567_delta.json", "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v567.json", "test_tablet_gpt_tcg_grader_sync_v567.py"
        ])
        self.assertEqual(c["freshness_watch"]["exact_paths"], ["card_identity_recognition.py"])
        sync.assert_v567_successor(self)

    def test_v620_reviewed_bytes_and_v567_exact_descendant_both_pinned(self):
        target = ROOT / "card_identity_recognition.py"
        self.assertIn(hashlib.sha256(target.read_bytes()).hexdigest(),
                      {OCR_SHA256, sync.V568_OCR_SHA256})
        base = subprocess.check_output(["git", "show", SOURCE + ":card_identity_recognition.py"], cwd=ROOT)
        candidate = subprocess.check_output(["git", "show", CANDIDATE + ":card_identity_recognition.py"], cwd=ROOT)
        self.assertEqual(hashlib.sha256(base).hexdigest(), sync.V620_OCR_SHA256)
        self.assertEqual(hashlib.sha256(candidate).hexdigest(), OCR_SHA256)
        changed = subprocess.check_output(["git", "diff", "--name-only", SOURCE + ".." + CANDIDATE], cwd=ROOT, text=True).splitlines()
        self.assertEqual(changed, ["card_identity_recognition.py"])
        path = "card_identity_recognition.py"
        self.assertEqual(sync.preserve_reviewed_v620_ocr_scope([path], sync.V377_CANDIDATE), [])
        # Historical guard tamper must fail closed; new exact successor is not
        # an excuse to approve arbitrary OCR changes or rewrite old hashes.
        with mock.patch.object(sync, "V567_OCR_SHA256", "0" * 64):
            self.assertEqual(sync.preserve_reviewed_v620_ocr_scope([path], sync.V377_CANDIDATE), [path])
        with mock.patch.object(sync, "V620_OCR_SHA256", "0" * 64):
            self.assertEqual(sync.preserve_reviewed_v620_ocr_scope([path], sync.V377_CANDIDATE), [path])
        with mock.patch.object(sync, "V620_OCR_BASE_SHA256", "0" * 64):
            self.assertEqual(sync.preserve_reviewed_v620_ocr_scope([path], sync.V377_CANDIDATE), [path])


if __name__ == "__main__":
    unittest.main(verbosity=2)
