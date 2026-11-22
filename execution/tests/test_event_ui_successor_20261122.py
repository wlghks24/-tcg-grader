import copy
from pathlib import Path
import unittest
from unittest.mock import patch
from execution import event_ui_successor_20261122 as proof
from execution.workspace_review_successor_v1018 import validate_workspace_review_v1018


class EventUISuccessorTests(unittest.TestCase):
    def run_proof(self):
        return proof.validate_event_ui_successor(proof.EXPECTED['path'],proof.EXPECTED['baseline']['sha256'])

    def test_exact_source_and_legacy_whole_set(self):
        self.assertTrue(self.run_proof())
        self.assertTrue(validate_workspace_review_v1018('index.html'))

    def test_wrong_path_or_prior_digest(self):
        for path,digest in [('index.html',proof.EXPECTED['baseline']['sha256']), (proof.EXPECTED['path'],'0'*64)]:
            with self.assertRaises(AssertionError):proof.validate_event_ui_successor(path,digest)

    def test_each_live_runtime_is_reread_after_success(self):
        original=Path.read_bytes
        for name in proof.EXPECTED['live_paths']:
            self.assertTrue(self.run_proof())
            def altered(path):
                data=original(path)
                return data+b'changed' if path==proof.ROOT/name else data
            with patch.object(Path,'read_bytes',altered),self.assertRaises(AssertionError):self.run_proof()

    def test_live_symlink_is_rejected(self):
        original=Path.is_symlink
        for name in proof.EXPECTED['live_paths']:
            with patch.object(Path,'is_symlink',lambda p:p==proof.ROOT/name or original(p)),self.assertRaises(AssertionError):self.run_proof()

    def test_unexpected_source_delta_is_rejected(self):
        original=proof.git
        def altered(*args):
            raw=original(*args)
            return raw+b'unknown.py\n' if args[0]=='diff' else raw
        with patch.object(proof,'git',altered),self.assertRaises(AssertionError):self.run_proof()

    def test_forged_pins_and_physical_claim_are_rejected(self):
        for field in ['blob','sha256','bytes']:
            e=copy.deepcopy(proof.EXPECTED)
            e['files'][e['path']][field]=0 if field=='bytes' else '0'*40
            with patch.object(proof,'EXPECTED',e),self.assertRaises(AssertionError):self.run_proof()
        e=copy.deepcopy(proof.EXPECTED);e['physical_tablet_verified']=True
        with patch.object(proof,'EXPECTED',e),self.assertRaises(AssertionError):self.run_proof()

    def test_changed_committed_head_is_rejected(self):
        original=proof.git
        def altered(*args):
            raw=original(*args)
            return raw+b'x' if args[:2]==('show','HEAD:'+proof.EXPECTED['path']) else raw
        with patch.object(proof,'git',altered),self.assertRaises(AssertionError):self.run_proof()

    def test_other_legacy_sibling_is_not_relaxed(self):
        original=Path.read_bytes
        def altered(path):
            data=original(path)
            return data+b'x' if path==proof.ROOT/'index.html' else data
        with patch.object(Path,'read_bytes',altered),self.assertRaises(AssertionError):validate_workspace_review_v1018('index.html')
