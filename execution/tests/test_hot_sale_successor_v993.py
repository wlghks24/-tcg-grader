"""V993: HOT successors remain fail-closed, with all V645 history intact."""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch
import sync_v376_successor_test_support as sync

ROOT=Path(__file__).resolve().parents[2]


class HotSaleSuccessorV993Tests(unittest.TestCase):
    def test_exact_hot_candidate_matches_immutable_review(self):
        self.assertEqual("box_knowledge_stats.js",sync.V993_HOT_SUCCESSOR["path"])
        self.assertEqual(sync.V645_FEATURE_PROOF["candidate_commit"],
                         sync.V993_HOT_SUCCESSOR["baseline_commit"])
        self.assertEqual(sync.V645_FEATURE_PROOF["reviewed_sha256"]["box_knowledge_stats.js"],
                         sync.V993_HOT_SUCCESSOR["baseline_sha256"])
        self.assertFalse(sync.V993_HOT_SUCCESSOR["deployment_allowed"])
        self.assertFalse(sync.V993_HOT_SUCCESSOR["physical_tablet_runtime_verified"])
        self.assertTrue(sync._v993_hot_live_verified())

    def test_modified_hot_bytes_cannot_use_successor(self):
        self.assertTrue(sync._v993_hot_live_verified())
        original=Path.read_bytes
        target=ROOT/"box_knowledge_stats.js"
        def modified(path):
            data=original(path)
            return data+b"\\n// unreviewed change" if path==target else data
        with patch.object(Path,"read_bytes",modified):
            self.assertFalse(sync._v993_hot_live_verified())

    def test_modified_review_file_blocks_successor(self):
        self.assertTrue(sync._v993_hot_live_verified())
        original=sync._read
        proof_file=ROOT/".github/tablet-autonomy/hot_sale_successor_v993.json"
        def tampered(path):
            data=original(path)
            return {**data,"deployment_allowed":True} if path==proof_file else data
        with patch.object(sync,"_read",tampered):
            self.assertFalse(sync._v993_hot_live_verified())

    def test_no_downgrade_to_original_without_full_ancestry(self):
        with patch.object(sync.subprocess,"run",return_value=type("Result",(),{"returncode":1})()):
            self.assertFalse(sync._v993_hot_live_verified())


if __name__=="__main__":
    unittest.main()
