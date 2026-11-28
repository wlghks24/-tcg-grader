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
        import test_tablet_gpt_tcg_grader_sync_v383 as v383
        import test_tablet_gpt_tcg_grader_sync_v384 as v384
        contract = {'freshness_watch': {
            'exact_paths': [sync.V488_PACKAGE_PATH], 'path_prefixes': [], 'exclude_paths': []}}
        watchers = (sync._watched_paths, v383.watched_paths, v384.watched_paths)
        # V426 is an actual current-HEAD boundary in the shared watcher.
        # V488_PACKAGE_BASE is instead evaluated at the pinned V407 snapshot
        # there, so a later worktree mutation cannot appear in that old diff.
        current_source = sync.V426_CANDIDATE
        for watch in watchers:
            with self.subTest(watcher=watch.__module__):
                self.assertEqual([], watch(contract, sync.V488_PACKAGE_BASE))
                self.assertEqual([], watch(contract, current_source))
                # The original V383 edit remains visible: a later proof cannot
                # erase changes that predate the V488 review boundary.
                self.assertIn(sync.V488_PACKAGE_PATH, watch(contract, v383.BASE_SHA))
                self.assertIn(sync.V488_PACKAGE_PATH, watch(
                    contract, sync.V488_PACKAGE_BASE, sync.V488_PACKAGE_CANDIDATE))
        original = Path.read_bytes
        target = proof.ROOT / sync.V488_PACKAGE_PATH
        def changed(path):
            raw = original(path)
            return raw + b'\nUNREVIEWED' if path == target else raw
        with patch.object(Path, 'read_bytes', changed):
            self.assertEqual([sync.V488_PACKAGE_PATH], sync.preserve_reviewed_v488_package_scope(
                [sync.V488_PACKAGE_PATH], sync.V488_PACKAGE_BASE))
            for watch in watchers:
                with self.subTest(watcher=watch.__module__, mutation=True):
                    self.assertIn(sync.V488_PACKAGE_PATH, watch(contract, current_source))

    def test_other_checkout_cannot_borrow_this_repository_proof(self):
        with self.assertRaisesRegex(AssertionError, 'wrong review checkout'):
            proof.validate_tablet_tool_recovery(
                'execution/tablet_menu_shell_v903.py',
                proof.EXPECTED['baseline']['execution/tablet_menu_shell_v903.py']['sha256'],
                repo=proof.ROOT.parent / 'different-checkout')


def load_tests(loader, tests, pattern):
    # Run the existing composition suite as well as the exact successor tests.
    # Imported MenuTests in the old workspace module is not discovered when CI
    # explicitly loads only WorkspaceRestoreV1017Tests.
    tests.addTests(loader.loadTestsFromName('execution.tests.test_tablet_menu_shell_v903'))
    tests.addTests(loader.loadTestsFromName('execution.tests.test_tablet_sync_successor_v1037'))
    return tests


if __name__ == '__main__':
    unittest.main()
