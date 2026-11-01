"""Repeatable V881 performance bridge checks: cached git only, fresh live bytes."""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import sync_v376_successor_test_support as sync

ROOT = Path(__file__).resolve().parents[2]


class V881CachedBridgeTests(unittest.TestCase):
    def test_exact_candidate_matches_live_bridge(self):
        from execution.tests.test_video_ui_successor_v881 import validate_candidate
        self.assertEqual(validate_candidate(), sync._v881_cached_immutable_live_verified())

    def test_runtime_tamper_rejected_after_cache_warmup(self):
        sync._v881_cached_immutable_live_verified()
        original = Path.read_bytes
        for name in ("sw.js", "tcg_updater.py", "index.html"):
            def tampered(path, target=ROOT / name):
                data = original(path)
                return data + b"\n<!--unreviewed-->" if path == target else data
            with self.subTest(path=name), patch.object(Path, "read_bytes", tampered):
                with self.assertRaises(AssertionError):
                    sync._v881_cached_immutable_live_verified()

    def test_proof_tamper_rejected_after_cache_warmup(self):
        sync._v881_cached_immutable_live_verified()
        original = Path.read_bytes
        for name in ("video_ui_successor_v881.json", "csp_hash_successor_v882.json"):
            target = ROOT / ".github/tablet-autonomy" / name
            def tampered(path):
                data = original(path)
                return data + b"\n " if path == target else data
            with self.subTest(path=name), patch.object(Path, "read_bytes", tampered):
                with self.assertRaises(AssertionError):
                    sync._v881_cached_immutable_live_verified()

    def test_non_head_and_unknown_paths_remain_visible(self):
        source = sync.V652_PROOF["base_commit"]
        self.assertEqual(["tcg_updater.py"],
                         sync.preserve_reviewed_v881_scope(["tcg_updater.py"], source, head=source))
        self.assertEqual(["unreviewed_example.py"],
                         sync.preserve_reviewed_v881_scope(["unreviewed_example.py"], source))


if __name__ == "__main__":
    unittest.main()
