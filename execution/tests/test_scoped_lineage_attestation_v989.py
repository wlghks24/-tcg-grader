"""V989: historical image/catalog changes need exact immutable successor proof."""
from __future__ import annotations
import json
import unittest
from pathlib import Path
from unittest.mock import patch
import sync_v376_successor_test_support as sync

ROOT=Path(__file__).resolve().parents[2]
VISIBLE=sorted(sync.V989_TABLET_SCOPED_PATHS)


class ScopedLineageV989Tests(unittest.TestCase):
    def test_v426_scope_delegate_requires_exact_original_commit_bytes(self):
        result=sync.preserve_reviewed_v989_tablet_image_scope(VISIBLE, sync.V426_CANDIDATE)
        self.assertEqual([], result, "V645-new paths should be reviewed exactly")
        self.assertEqual(VISIBLE, sync.preserve_reviewed_v989_tablet_image_scope(
            VISIBLE, sync.V426_CANDIDATE, head=sync.V645_FEATURE_PROOF["candidate_commit"]))
        self.assertEqual(["unreviewed_example.py"], sync.preserve_reviewed_v989_tablet_image_scope(
            ["unreviewed_example.py"], sync.V426_CANDIDATE))
        self.assertEqual(VISIBLE, sync.preserve_reviewed_v989_tablet_image_scope(
            VISIBLE, sync.V645_FEATURE_PROOF["candidate_commit"]))

    def test_modified_current_bytes_remain_visible_after_cache_warmup(self):
        self.assertEqual([], sync.preserve_reviewed_v989_tablet_image_scope(
            VISIBLE, sync.V426_CANDIDATE))
        original=Path.read_bytes
        for name in VISIBLE:
            def changed(path, target=ROOT/name):
                data=original(path)
                return data+b"\n# unreviewed image modification" if path==target else data
            with self.subTest(name=name),patch.object(Path,"read_bytes",changed):
                self.assertEqual(VISIBLE,sync.preserve_reviewed_v989_tablet_image_scope(
                    VISIBLE,sync.V426_CANDIDATE))

    def test_modified_review_proof_blocks_delegation(self):
        self.assertEqual([],sync.preserve_reviewed_v989_tablet_image_scope(
            VISIBLE,sync.V426_CANDIDATE))
        original=sync._read
        for name,_ in sync.V989_REVIEW_FILES:
            def changed(path, target=ROOT/name):
                data=original(path)
                if path==target:
                    data={**data,"deployment_allowed":True}
                return data
            with self.subTest(name=name),patch.object(sync,"_read",changed):
                self.assertEqual(VISIBLE,sync.preserve_reviewed_v989_tablet_image_scope(
                    VISIBLE,sync.V426_CANDIDATE))

    def test_historical_v426_and_older_are_not_rewritten(self):
        contract=json.loads((ROOT/sync.V426_CONTRACT_PATH).read_text(encoding="utf-8"))
        expected=sync.V641_GAPS
        # V641 paths continue through their existing strictly-pinned delegate.
        after=sync._watched_paths(contract,sync.V426_CANDIDATE)
        self.assertTrue(set(after).issubset(set(sync.V427_WATCHED+
            sync.V431_WATCHED+sync.V432_WATCHED+sync.V439_WATCHED+
            sync.V440_WATCHED+sync.V469_WATCHED+sync.V470_WATCHED+
            sync.V471_WATCHED+sync.V480_WATCHED)|expected),after)
        self.assertFalse(sync.V989_TABLET_SCOPED_PATHS.intersection(after))


if __name__=="__main__":unittest.main()
