"""V994 exact SHA and ancestry evidence for the V426 neural descendants."""
from __future__ import annotations
import unittest
from pathlib import Path
from unittest.mock import patch
import sync_v376_successor_test_support as sync
from execution.tests.test_hot_sale_successor_v993 import HotSaleSuccessorV993Tests

ROOT=Path(__file__).resolve().parent


class VerifiedNeuralSuccessorV994Tests(unittest.TestCase):
    def test_exact_v426_neural_bridge(self):
        paths=sorted(sync.V994_NEURAL_PROOF["reviewed_paths"])
        self.assertEqual(["verified_collection_job_neural.py","verified_collection_neural.py"],paths)
        self.assertIs(sync.V994_NEURAL_PROOF["physical_tablet_runtime_verified"],False)
        self.assertIs(sync.V994_NEURAL_PROOF["deployment_allowed"],False)
        self.assertEqual([],sync.preserve_reviewed_v994_neural_scope(
            paths,sync.V426_CANDIDATE))
        self.assertEqual(paths,sync.preserve_reviewed_v994_neural_scope(
            paths,sync.V426_CANDIDATE,head=sync.V994_NEURAL_PROOF["candidate_commit"]))

    def test_mutated_live_bytes_remain_unreviewed(self):
        paths=sorted(sync.V994_NEURAL_PROOF["reviewed_paths"])
        self.assertEqual([],sync.preserve_reviewed_v994_neural_scope(
            paths,sync.V426_CANDIDATE))
        original=Path.read_bytes
        for path in paths:
            def tampered(self_path,target=ROOT/path):
                data=original(self_path)
                return data+b"\\n# unreviewed" if self_path==target else data
            with self.subTest(path=path),patch.object(Path,"read_bytes",tampered):
                self.assertEqual(paths,sync.preserve_reviewed_v994_neural_scope(
                    paths,sync.V426_CANDIDATE))

    def test_modified_proof_is_fail_closed(self):
        paths=sorted(sync.V994_NEURAL_PROOF["reviewed_paths"])
        original=sync._read
        target=ROOT/".github/tablet-autonomy/verified_neural_successor_v994.json"
        def tampered(path):
            data=original(path)
            return {**data,"deployment_allowed":True} if path==target else data
        with patch.object(sync,"_read",tampered):
            self.assertEqual(paths,sync.preserve_reviewed_v994_neural_scope(
                paths,sync.V426_CANDIDATE))


if __name__=="__main__":unittest.main()
