"""V995: exact later UI/promo evidence without weakening V881/V882/V884 history."""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import sync_v376_successor_test_support as sync
from execution.tests.test_csp_hash_successor_v882 import validate_csp_successor
from execution.tests.test_video_ui_successor_v881 import validate_candidate

ROOT = Path(__file__).resolve().parents[2]
V883 = "742751dce03c711f7a4ca7a882d2fec69fb3ac55"


class ExactPostV884SuccessorTests(unittest.TestCase):
    def test_reviewed_exact_descendants_and_legacy_csp(self):
        expected = ["index.html", "update_promo_events.py"]
        self.assertEqual(expected, sync.verify_v995_post_v884())
        self.assertIs(sync.V995_POST_V884_PROOF["deployment_allowed"], False)
        self.assertIs(sync.V995_POST_V884_PROOF["physical_tablet_runtime_verified"], False)
        self.assertEqual("index.html", validate_csp_successor())
        self.assertIn("index.html", validate_candidate())

    def test_v883_scope_only_delegates_the_two_newly_reviewed_changes(self):
        self.assertEqual([], sync.preserve_reviewed_v884_scope(
            ["index.html", "update_promo_events.py"], V883))
        self.assertEqual(["unknown-extra.py"], sync.preserve_reviewed_v884_scope(
            ["index.html", "update_promo_events.py", "unknown-extra.py"], V883))

    def test_tampered_live_files_fail_closed(self):
        original = Path.read_bytes
        for name in sync.V995_POST_V884_PROOF["reviewed_paths"]:
            target = ROOT / name

            def tampered(path, target=target):
                data = original(path)
                return data + b"UNREVIEWED" if path == target else data

            with self.subTest(name=name), patch.object(Path, "read_bytes", tampered):
                with self.assertRaises(AssertionError):
                    sync.verify_v995_post_v884()

    def test_unapproved_proof_flags_fail_closed(self):
        original = sync._read
        target = ROOT / ".github/tablet-autonomy/post_v884_runtime_successor_v995.json"

        def forged(path):
            data = original(path)
            if path == target:
                return {**data, "deployment_allowed": True}
            return data

        with patch.object(sync, "_read", forged):
            with self.assertRaises(AssertionError):
                sync.verify_v995_post_v884()


if __name__ == "__main__":
    unittest.main()
