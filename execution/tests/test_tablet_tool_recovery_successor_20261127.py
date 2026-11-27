"""Exact source history plus uncached live-file/HEAD rejection regressions."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch

from execution import tablet_tool_recovery_successor_20261127 as proof


class TabletToolRecoverySuccessorTests(unittest.TestCase):
    def validate(self, name='execution/tablet_menu_shell_v903.py'):
        return proof.validate_tablet_tool_recovery(
            name, proof.EXPECTED['baseline'][name]['sha256'])

    def test_exact_source_scope_all_three_entrypoints_and_no_device_claim(self):
        for name in proof.EXPECTED['baseline']:
            self.assertTrue(self.validate(name))
        for key in ('physical_tablet_verified', 'runtime_data_modified',
                    'main_merge_authorized', 'device_restart_authorized'):
            self.assertIs(proof.EXPECTED[key], False)

    def test_unknown_path_and_wrong_prior_digest_never_delegate(self):
        with self.assertRaises(AssertionError):
            proof.validate_tablet_tool_recovery('index.html', '0'*64)
        with self.assertRaises(AssertionError):
            proof.validate_tablet_tool_recovery('execution/tablet_menu_shell_v903.py', '0'*64)

    def test_live_mutation_after_a_success_cannot_reuse_acceptance(self):
        original = Path.read_bytes
        for name in proof.EXPECTED['baseline']:
            self.assertTrue(self.validate())
            target = proof.ROOT / name
            def changed(path):
                raw = original(path)
                return raw + b'\nUNREVIEWED' if path == target else raw
            with self.subTest(name=name), patch.object(Path, 'read_bytes', changed):
                with self.assertRaises(AssertionError):
                    self.validate()

    def test_symlink_live_source_or_proof_rejected(self):
        original = Path.is_symlink
        for name in (*proof.EXPECTED['baseline'], proof.PROOF_PATH):
            target = proof.ROOT / name
            def linked(path):
                return path == target or original(path)
            with self.subTest(name=name), patch.object(Path, 'is_symlink', linked):
                with self.assertRaises(AssertionError):
                    self.validate()

    def test_proof_tamper_and_install_authority_flag_rejected(self):
        original = Path.read_bytes
        target = proof.ROOT / proof.PROOF_PATH
        def changed(path):
            raw = original(path)
            return raw.replace(b'"physical_tablet_verified": false',
                               b'"physical_tablet_verified": true') if path == target else raw
        with patch.object(Path, 'read_bytes', changed), self.assertRaises(AssertionError):
            self.validate()
        e = copy.deepcopy(proof.EXPECTED)
        e['device_restart_authorized'] = True
        with patch.object(proof, 'EXPECTED', e), self.assertRaises(AssertionError):
            self.validate()

    def test_unreviewed_committed_head_blob_rejected(self):
        original = proof.git
        name = 'execution/tablet_menu_shell_v903.py'
        def changed(*args):
            raw = original(*args)
            return raw + b'\nUNREVIEWED' if args == ('show','HEAD:'+name) else raw
        with patch.object(proof, 'git', changed), self.assertRaises(AssertionError):
            self.validate()

    def test_unknown_source_scope_and_wrong_candidate_pin_rejected(self):
        original = proof.git
        def changed(*args):
            raw = original(*args)
            return raw + b'unknown_runtime.py\0' if args[:3] == ('diff','--no-renames','--name-only') else raw
        with patch.object(proof, 'git', changed), self.assertRaises(AssertionError):
            self.validate()
        e = copy.deepcopy(proof.EXPECTED)
        e['files']['execution/tablet_menu_shell_v903.py']['blob'] = '0'*40
        with patch.object(proof, 'EXPECTED', e), self.assertRaises(AssertionError):
            self.validate()

    def test_uncommitted_manifest_cannot_authorize_live_source(self):
        original = Path.read_bytes
        target = proof.ROOT / 'integrity_manifest.json'
        def changed(path):
            raw = original(path)
            return raw + b'\n' if path == target else raw
        with patch.object(Path, 'read_bytes', changed), self.assertRaises(AssertionError):
            self.validate()

    def test_existing_ui_proof_chain_reaches_exact_descendant(self):
        from execution.workspace_followup_successor_20261123 import (
            EXPECTED, validate_workspace_followup)
        from execution.events_collection_successor_20261123 import (
            EXPECTED as events, validate_events_collection_successor)
        self.assertTrue(validate_workspace_followup(
            'execution/tablet_menu_shell_v903.js',
            EXPECTED['baseline']['execution/tablet_menu_shell_v903.js']['sha256']))
        name = 'execution/tablet_menu_shell_v903.py'
        self.assertTrue(validate_events_collection_successor(name, events['baseline'][name]['sha256']))

    def test_historical_package_boundary_is_retained_only_for_exact_descendant(self):
        import sync_v376_successor_test_support as sync
        contract = {'freshness_watch': {
            'exact_paths': [sync.V488_PACKAGE_PATH], 'path_prefixes': [], 'exclude_paths': []}}
        self.assertEqual([], sync._watched_paths(contract, sync.V488_PACKAGE_BASE))
        original = Path.read_bytes
        target = proof.ROOT / sync.V488_PACKAGE_PATH
        def changed(path):
            raw = original(path)
            return raw + b'\nUNREVIEWED' if path == target else raw
        with patch.object(Path, 'read_bytes', changed):
            self.assertIn(sync.V488_PACKAGE_PATH, sync._watched_paths(contract, sync.V488_PACKAGE_BASE))


if __name__ == '__main__':
    unittest.main()
