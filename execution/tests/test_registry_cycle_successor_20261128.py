"""Exact lineage plus live mutation rejection after a successful warm call."""
import unittest
from pathlib import Path
from unittest.mock import patch
from execution import registry_cycle_successor_20261128 as proof
class RegistryCycleSuccessorTests(unittest.TestCase):
    def test_exact_current_source(self):
        self.assertTrue(proof.validate_registry_cycle_successor(proof.EXPECTED['baseline']['auto_update_all.py']['sha256']))
    def test_wrong_prior_never_delegates(self):
        with self.assertRaises(AssertionError): proof.validate_registry_cycle_successor('0'*64)
    def test_each_live_source_mutation_after_warmup_is_rejected(self):
        prior=proof.EXPECTED['baseline']['auto_update_all.py']['sha256']
        proof.validate_registry_cycle_successor(prior)
        original=Path.read_bytes
        for name in proof.EXPECTED['files']:
            with self.subTest(path=name),patch.object(Path,'read_bytes',lambda p: original(p)+b' unreviewed' if p==proof.ROOT/name else original(p)):
                with self.assertRaises((AssertionError,ValueError)): proof.validate_registry_cycle_successor(prior)
    def test_changed_committed_source_is_rejected(self):
        prior=proof.EXPECTED['baseline']['auto_update_all.py']['sha256'];native=proof.git
        def changed(*args):
            if args==('show','HEAD:auto_update_all.py'): return b'unreviewed'
            return native(*args)
        with patch.object(proof,'git',side_effect=changed):
            with self.assertRaises(AssertionError): proof.validate_registry_cycle_successor(prior)
