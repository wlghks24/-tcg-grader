"""V1026: old V655 watches accept only V1021 exact browser review, never tampering."""
import unittest
from pathlib import Path
from unittest.mock import patch

import sync_v376_successor_test_support as sync

BROWSER='verify_browser_runtime.js'
V655_CANDIDATE='627e4727eae2b69ee4a96e3671928282eaffe849'
V657_CANDIDATE='4a1baf4fc3b52b1a81829b02070a58452854b33e'
V658_CANDIDATE='8990c3ecb0e7c42f38a2ce1fcbfa94fd9ae6dc63'
V1021_CANDIDATE='3aacfbeef3436837ac47b80f9785cd3898e3d67d'


class BrowserLegacyReviewTests(unittest.TestCase):
    def test_v655_direct_legacy_scope_accepts_exact_reviewed_descendant(self):
        self.assertEqual([],sync.preserve_reviewed_v656_scope(
            [BROWSER],V655_CANDIDATE))
        self.assertEqual([],sync.preserve_reviewed_v1021_browser_scope(
            [BROWSER],V655_CANDIDATE))

    def test_v658_direct_legacy_scope_accepts_only_exact_v1021_browser(self):
        self.assertEqual([], sync.preserve_reviewed_v658_scope(
            [BROWSER], V658_CANDIDATE))

    def test_v658_scope_rejects_live_browser_tampering(self):
        original = Path.read_bytes
        def tampered(path):
            data = original(path)
            return data + b'\n// unreviewed' if path == sync.ROOT / BROWSER else data
        with patch.object(Path, 'read_bytes', tampered):
            self.assertEqual([BROWSER], sync.preserve_reviewed_v658_scope(
                [BROWSER], V658_CANDIDATE))

    def test_v658_scope_rejects_non_head_or_newer_source(self):
        self.assertEqual([BROWSER], sync.preserve_reviewed_v658_scope(
            [BROWSER], V658_CANDIDATE, head=V658_CANDIDATE))
        self.assertEqual([BROWSER], sync.preserve_reviewed_v658_scope(
            [BROWSER], V1021_CANDIDATE))

    def test_v657_legacy_scope_accepts_exact_reviewed_descendant(self):
        self.assertEqual([],sync.preserve_reviewed_v657_scope(
            [BROWSER],V657_CANDIDATE))

    def test_v657_scope_rejects_live_tampering(self):
        original=Path.read_bytes
        def tampered(path):
            data=original(path)
            return data+b'\\n// unreviewed' if path==sync.ROOT/BROWSER else data
        with patch.object(Path,'read_bytes',tampered):
            self.assertEqual([BROWSER],sync.preserve_reviewed_v657_scope(
                [BROWSER],V657_CANDIDATE))

    def test_v657_scope_never_exempts_non_head_or_newer_source(self):
        self.assertEqual([BROWSER],sync.preserve_reviewed_v657_scope(
            [BROWSER],V657_CANDIDATE,head=V657_CANDIDATE))
        self.assertEqual([BROWSER],sync.preserve_reviewed_v657_scope(
            [BROWSER],V1021_CANDIDATE))

    def test_non_head_and_non_ancestor_do_not_exempt(self):
        self.assertEqual([BROWSER],sync.preserve_reviewed_v1021_browser_scope(
            [BROWSER],V655_CANDIDATE,head=V655_CANDIDATE))
        self.assertEqual([BROWSER],sync.preserve_reviewed_v1021_browser_scope(
            [BROWSER],V1021_CANDIDATE))

    def test_live_browser_tampering_remains_visible(self):
        original=Path.read_bytes
        def tampered(path):
            data=original(path)
            return data+b'\n// unreviewed' if path==sync.ROOT/BROWSER else data
        with patch.object(Path,'read_bytes',tampered):
            self.assertEqual([BROWSER],sync.preserve_reviewed_v656_scope(
                [BROWSER],V655_CANDIDATE))

    def test_unrelated_path_remains_visible(self):
        name='unreviewed_other.js'
        self.assertEqual([name],sync.preserve_reviewed_v1021_browser_scope(
            [name],V655_CANDIDATE))


if __name__=='__main__':
    unittest.main()
