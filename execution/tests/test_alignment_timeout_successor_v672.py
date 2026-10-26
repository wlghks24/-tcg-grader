"""V672 negative-first CI timeout provenance: historical proof remains immutable."""
import unittest
from pathlib import Path
from unittest.mock import patch
import sync_v376_successor_test_support as proof


class V672TimeoutSuccessorTests(unittest.TestCase):
    def test_exact_reviewed_timeout_and_git_ancestry(self):
        proof.assert_v672_alignment_timeout_successor(self)
        proof.assert_v659_ci_successor(self)
        proof.assert_v647_ci_successor(self)

    def test_historic_v659_sha_still_pinned(self):
        self.assertEqual(
            proof.V659_CI_PROOF['reviewed_sha256']['.github/workflows/tablet-gpt-tcg-grader-main-alignment.yml'],
            proof.V672_ALIGNMENT_TIMEOUT_PROOF['workflow_review']['baseline_sha256']['.github/workflows/tablet-gpt-tcg-grader-main-alignment.yml'])

    def test_tampered_live_workflow_rejected(self):
        original=Path.read_bytes
        path=proof.ROOT/'.github/workflows/tablet-gpt-tcg-grader-main-alignment.yml'
        with patch.object(Path,'read_bytes',lambda p:original(p)+b' # unreviewed' if p==path else original(p)):
            with self.assertRaises(AssertionError):
                proof.assert_v672_alignment_timeout_successor(self)

    def test_tampered_v659_fixture_rejected(self):
        original=Path.read_bytes
        path=proof.ROOT/'execution/tests/test_alignment_partitions_v659.py'
        with patch.object(Path,'read_bytes',lambda p:original(p)+b' # unreviewed' if p==path else original(p)):
            with self.assertRaises(AssertionError):
                proof.assert_v672_alignment_timeout_successor(self)

    def test_forged_device_approval_denied(self):
        original=proof._read
        path=proof.ROOT/'.github/tablet-autonomy/alignment_timeout_successor_v672.json'
        with patch.object(proof,'_read',side_effect=lambda p:{**original(p),'deployment_allowed':True} if p==path else original(p)):
            with self.assertRaises(AssertionError):
                proof.assert_v672_alignment_timeout_successor(self)


if __name__=='__main__':
    unittest.main()
