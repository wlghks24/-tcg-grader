"""V884 PWA successor: exact source/CI pins, historical watches and no device claim."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import sync_v376_successor_test_support as sync


class PwaCriticalShellSuccessorTests(unittest.TestCase):
    def test_exact_candidate_scope_delegates_only_sw(self):
        unrelated = ".github/workflows/tablet-autonomy-patch-checks.yml"
        self.assertEqual([unrelated], sync.preserve_reviewed_v884_pwa_scope(
            [unrelated, "sw.js"], sync.V884_PWA_BASE))

    def test_old_and_unknown_history_cannot_be_waived(self):
        self.assertEqual(["sw.js"], sync.preserve_reviewed_v884_pwa_scope(
            ["sw.js"], sync.V884_PWA_BASE, head=sync.V884_PWA_CANDIDATE))
        self.assertEqual(["sw.js"], sync.preserve_reviewed_v884_pwa_scope(
            ["sw.js"], "0" * 40))

    def test_invalid_receipt_or_sha_is_fail_closed(self):
        with mock.patch.object(sync, "V884_PWA_PROOF",
                               ROOT / "execution/evidence/absent_v884_proof.json"):
            self.assertEqual(["sw.js"], sync.preserve_reviewed_v884_pwa_scope(
                ["sw.js"], sync.V884_PWA_BASE))
        pin = dict(sync.V884_PWA_PINS["sw.js"])
        pin["sha256"] = "0" * 64
        with mock.patch.object(sync, "V884_PWA_PINS",
                               {**sync.V884_PWA_PINS, "sw.js": pin}):
            self.assertEqual(["sw.js"], sync.preserve_reviewed_v884_pwa_scope(
                ["sw.js"], sync.V884_PWA_BASE))

    def test_v645_original_pins_require_exact_v884_descendant(self):
        # Do not rewrite or weaken the immutable V645 source/commit proof.
        sync.assert_v645_feature_successor(self)

    def test_v646_direct_watcher_requires_exact_v884_proof(self):
        # V646's original test calls V648's public watcher directly, bypassing
        # the broader V525 path. Only an exact, reviewed sw.js descendant is safe.
        source = sync.V646_FEATURE_PROOF["candidate_commit"]
        self.assertEqual([], sync.preserve_reviewed_v648_update_scope(["sw.js"], source))
        self.assertEqual(["sw.js"], sync.preserve_reviewed_v648_update_scope(
            ["sw.js"], source, head=sync.V884_PWA_CANDIDATE))
        self.assertEqual(["sw.js"], sync.preserve_reviewed_v648_update_scope(
            ["sw.js"], "0" * 40))
        with mock.patch.object(sync, "V884_PWA_PROOF",
                               ROOT / "execution/evidence/absent_v884_proof.json"):
            self.assertEqual(["sw.js"], sync.preserve_reviewed_v648_update_scope(
                ["sw.js"], source))
        pin = dict(sync.V884_PWA_PINS["sw.js"])
        pin["sha256"] = "0" * 64
        with mock.patch.object(sync, "V884_PWA_PINS",
                               {**sync.V884_PWA_PINS, "sw.js": pin}):
            self.assertEqual(["sw.js"], sync.preserve_reviewed_v648_update_scope(
                ["sw.js"], source))

    def test_review_receipt_not_merge_or_tablet_approval(self):
        proof = json.loads(sync.V884_PWA_PROOF.read_text(encoding="utf-8"))
        self.assertEqual(["sw.js"], proof["reviewed_paths"])
        self.assertEqual(sync.V884_PWA_BASE_BLOBS, proof["baseline_git_blob_sha1"])
        for field in ("physical_tablet_verified", "auto_main_merge_allowed",
                      "full_historical_v1_current_verified"):
            self.assertIs(proof[field], False)


if __name__ == "__main__":
    unittest.main()
