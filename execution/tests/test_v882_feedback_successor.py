"""V882 descendant proof keeps historical V652 pins and refuses tampering."""
import unittest
from pathlib import Path
from unittest.mock import patch
from execution.v882_feedback_verified_successor import assert_v882_feedback_successor, ROOT
import sync_v376_successor_test_support as sync


class V882FeedbackSuccessorTests(unittest.TestCase):
    def test_exact_reviewed_candidate_and_original_v652_contract(self):
        assert_v882_feedback_successor(self)
        sync.assert_v652_successor(self)

    def test_current_feedback_code_tampering_is_rejected(self):
        original = Path.read_bytes
        target = ROOT/'adaptive_collection_learner.py'
        with patch.object(Path, 'read_bytes', lambda p: original(p)+b'\n#modified' if p==target else original(p)):
            with self.assertRaises(AssertionError):
                assert_v882_feedback_successor(self)
            with self.assertRaises(AssertionError):
                sync.assert_v652_successor(self)

    def test_immutable_v652_proof_is_not_rewritten(self):
        self.assertEqual('38683fbf72ef892f3b401b47ffa044236d6667ed516ea157aec92e1de90a0b37',
                         sync.V652_PROOF['reviewed_sha256']['adaptive_collection_learner.py'])


if __name__ == '__main__':
    unittest.main()
