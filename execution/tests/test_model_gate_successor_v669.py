"""Negative provenance tests for V661->V669 reviewed source changes."""
import unittest
from pathlib import Path
from unittest.mock import patch
import sync_v376_successor_test_support as historic

ROOT=Path(__file__).resolve().parents[2]
MODEL='execution/tablet_image_model_gate.py'
PROOF='.github/tablet-autonomy/image_model_gate_successor_v669.json'


class V669SourceProofTests(unittest.TestCase):
    def test_approved_lineage_and_immutable_v661(self):
        historic.assert_v669_model_gate_successor(self)
        historic.assert_v661_successor(self)
        self.assertFalse(historic.V661_PROOF['deployment_allowed'])
        self.assertFalse(historic.V669_GATE_PROOF['deployment_allowed'])

    def test_unreviewed_model_bytes_are_rejected(self):
        original=Path.read_bytes
        def modified(path):
            value=original(path)
            return value+b" # unreviewed" if path==ROOT/MODEL else value
        with patch.object(Path,'read_bytes',modified):
            with self.assertRaises(AssertionError):
                historic.assert_v669_model_gate_successor(self)

    def test_unreviewed_test_bytes_are_rejected(self):
        original=Path.read_bytes
        target=ROOT/'execution/tests/test_tablet_image_model_gate_v669.py'
        with patch.object(Path,'read_bytes',lambda p: original(p)+b" # unreviewed" if p==target else original(p)):
            with self.assertRaises(AssertionError):
                historic.assert_v669_model_gate_successor(self)

    def test_fake_proof_flags_are_rejected(self):
        original=historic._read
        def forged(path):
            value=original(path)
            return {**value,'deployment_allowed':True} if str(path).endswith('image_model_gate_successor_v669.json') else value
        with patch.object(historic,'_read',side_effect=forged):
            with self.assertRaises(AssertionError):
                historic.assert_v669_model_gate_successor(self)

    def test_unreviewed_candidate_scope_not_hidden(self):
        gate=MODEL
        base=historic.V669_GATE_PROOF['base_commit']
        self.assertEqual([],historic._preserve_v669_exact_metric_source([gate],base))
        self.assertEqual([gate],historic._preserve_v669_exact_metric_source([gate],base,head=base))
        self.assertEqual(['unrelated.py'],historic._preserve_v669_exact_metric_source(['unrelated.py'],base))


if __name__ == '__main__':
    unittest.main()
