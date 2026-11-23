import copy
from pathlib import Path
import unittest
from unittest.mock import patch
from execution import retention_reentry_successor_20261123 as proof
from execution.workspace_review_successor_v1018 import validate_workspace_review_v1018


class RetentionReentrySuccessorTests(unittest.TestCase):
    def run_proof(self, name='execution/event_retention_20261123.py'):
        return proof.validate_retention_reentry_successor(name, proof.EXPECTED['baseline'][name]['sha256'])

    def test_exact_source_and_preserved_legacy_whole_set(self):
        for name in proof.EXPECTED['baseline']:
            self.assertTrue(self.run_proof(name))
        self.assertTrue(validate_workspace_review_v1018('index.html'))

    def test_wrong_path_and_prior_digest_rejected(self):
        with self.assertRaises(AssertionError):proof.validate_retention_reentry_successor('index.html','0'*64)
        with self.assertRaises(AssertionError):proof.validate_retention_reentry_successor('execution/event_retention_20261123.py','0'*64)

    def test_live_files_reread_after_success(self):
        original=Path.read_bytes
        for name in proof.EXPECTED['live_paths']:
            self.assertTrue(self.run_proof())
            def changed(path):
                raw=original(path)
                return raw+b'x' if path==proof.ROOT/name else raw
            with patch.object(Path,'read_bytes',changed),self.assertRaises(AssertionError):self.run_proof()

    def test_live_symlinks_rejected(self):
        original=Path.is_symlink
        for name in proof.EXPECTED['live_paths']:
            with patch.object(Path,'is_symlink',lambda p:p==proof.ROOT/name or original(p)),self.assertRaises(AssertionError):self.run_proof()

    def test_extra_source_delta_rejected(self):
        original=proof.git
        def changed(*args):
            raw=original(*args)
            return raw+b'other.py\0' if args[0]=='diff' else raw
        with patch.object(proof,'git',changed),self.assertRaises(AssertionError):self.run_proof()

    def test_forged_pin_and_device_or_data_claim_rejected(self):
        for field,value in [('physical_tablet_verified',True),('runtime_data_modified',True)]:
            e=copy.deepcopy(proof.EXPECTED);e[field]=value
            with patch.object(proof,'EXPECTED',e),self.assertRaises(AssertionError):self.run_proof()
        e=copy.deepcopy(proof.EXPECTED);e['files'][e['live_paths'][0]]['sha256']='0'*64
        with patch.object(proof,'EXPECTED',e),self.assertRaises(AssertionError):self.run_proof()

    def test_committed_head_mutation_rejected(self):
        original=proof.git
        def changed(*args):
            raw=original(*args)
            return raw+b'x' if args[0]=='show' and args[1].startswith('HEAD:') else raw
        with patch.object(proof,'git',changed),self.assertRaises(AssertionError):self.run_proof()

    def test_unrelated_original_sibling_not_relaxed(self):
        original=Path.read_bytes
        def changed(path):
            raw=original(path)
            return raw+b'x' if path==proof.ROOT/'index.html' else raw
        with patch.object(Path,'read_bytes',changed),self.assertRaises(AssertionError):validate_workspace_review_v1018('index.html')
