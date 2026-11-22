"""Offline authentic-Git lineage and targeted tamper tests; no device actions."""
from contextlib import contextmanager
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from execution import menu_resize_successor_20261122 as successor
from execution import workspace_review_successor_v1018 as legacy

REAL_ROOT = successor.ROOT
MENU = successor.EXPECTED['reviewed_path']
SOURCE = successor.EXPECTED['candidate_commit']
BASE = successor.EXPECTED['baseline_commit']


def authentic_git(*args):
    return subprocess.check_output(['git', *args], cwd=REAL_ROOT, timeout=30)


class MenuResizeSuccessorTests(unittest.TestCase):
    @contextmanager
    def local_copy(self):
        # Only the mutable proof/live path use a temporary real filesystem.
        # Provenance still comes from the actual repository's immutable Git.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            live = root / MENU
            live.parent.mkdir(parents=True)
            live.write_bytes((REAL_ROOT / MENU).read_bytes())
            proof = root / '.github/tablet-autonomy/menu_resize_successor_20261122.json'
            proof.parent.mkdir(parents=True)
            proof.write_bytes(successor.PROOF.read_bytes())
            with patch.object(successor, 'ROOT', root), patch.object(successor, 'PROOF', proof), \
                    patch.object(successor, '_git', side_effect=authentic_git):
                yield root, live, proof

    def validate(self):
        return successor.validate_menu_resize_successor_20261122(MENU)

    def test_exact_real_candidate_and_legacy_whole_set_remain_valid(self):
        self.assertTrue(self.validate())
        self.assertTrue(legacy.validate_workspace_review_v1018('index.html'))
        self.assertEqual(BASE, '3809492f45159d03c41bc18cb7daa0b11b64e6d4')
        self.assertEqual(len(successor.EXPECTED['source_scope']), 8)
        self.assertEqual(legacy.EXPECTED['files'][MENU]['sha256'], successor.EXPECTED['baseline']['sha256'])
        for key in ('physical_tablet_verified', 'main_merge_authorized',
                    'model_training_authorized', 'runtime_data_modified'):
            self.assertIs(successor.EXPECTED[key], False)

    def test_wrong_path_and_prior_digest_are_rejected(self):
        for name, digest in [('index.html', None), (MENU, '0' * 64), (MENU, True)]:
            with self.subTest(name=name, digest=digest), self.assertRaises(AssertionError):
                successor.validate_menu_resize_successor_20261122(name, digest)
        with self.assertRaises(AssertionError):
            legacy.validate_workspace_review_v1018('index.html', '0' * 64)

    def test_added_missing_and_reordered_source_scope_are_rejected(self):
        rows = sorted(successor.EXPECTED['source_scope'])
        for altered in (rows + ['update_promo_events.py'], rows[:-1], list(reversed(rows))):
            def changed(*args):
                if args == ('diff', '--no-renames', '--name-only', '-z', BASE, SOURCE):
                    return ('\0'.join(altered) + '\0').encode()
                return authentic_git(*args)
            with self.subTest(scope=altered), patch.object(successor, '_git', side_effect=changed), \
                    self.assertRaises(AssertionError):
                self.validate()

    def test_wrong_baseline_and_candidate_ancestry_are_rejected(self):
        head = authentic_git('rev-parse', 'HEAD').decode().strip()
        for edge in ((BASE, SOURCE), (SOURCE, head)):
            def changed(*args):
                if args == ('merge-base', '--is-ancestor', *edge):
                    raise subprocess.CalledProcessError(1, ['git', *args])
                return authentic_git(*args)
            with self.subTest(edge=edge), patch.object(successor, '_git', side_effect=changed), \
                    self.assertRaises(subprocess.CalledProcessError):
                self.validate()

    def test_changed_candidate_blob_or_raw_source_is_rejected(self):
        target = SOURCE + ':grading_self_learning.py'
        for command in ('rev-parse', 'show'):
            def changed(*args):
                raw = authentic_git(*args)
                if args == (command, target):
                    return b'0' * 40 + b'\n' if command == 'rev-parse' else raw + b'changed'
                return raw
            with self.subTest(command=command), patch.object(successor, '_git', side_effect=changed), \
                    self.assertRaises(AssertionError):
                self.validate()

    def test_changed_committed_head_menu_is_rejected(self):
        # Negative-only virtual HEAD maps to authentic source objects, except
        # for its forged menu blob. Positive tests use no Git mocks.
        virtual_head = 'f' * 40
        def changed(*args):
            if args == ('rev-parse', 'HEAD'):
                return (virtual_head + '\n').encode()
            if args == ('merge-base', '--is-ancestor', SOURCE, virtual_head):
                return b''
            if args == ('rev-parse', virtual_head + ':' + MENU):
                return b'0' * 40 + b'\n'
            return authentic_git(*args)
        with patch.object(successor, '_git', side_effect=changed), self.assertRaises(AssertionError):
            self.validate()

    def test_committed_symlink_mode_is_rejected(self):
        def changed(*args):
            raw = authentic_git(*args)
            return raw.replace(b'100644 blob ', b'120000 blob ', 1) if args[0] == 'ls-tree' else raw
        with patch.object(successor, '_git', side_effect=changed), self.assertRaises(AssertionError):
            self.validate()

    def test_second_call_rereads_real_live_bytes_and_rejects_same_size_tamper(self):
        with self.local_copy() as (_, live, __):
            self.assertTrue(self.validate())
            raw = live.read_bytes()
            live.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
            with self.assertRaises(AssertionError):
                self.validate()

    def test_live_symlink_and_missing_file_are_rejected(self):
        with self.local_copy() as (root, live, _):
            saved = root / 'saved.js'
            saved.write_bytes(live.read_bytes())
            live.unlink()
            with self.assertRaises(AssertionError):
                self.validate()
            live.symlink_to(saved)
            with self.assertRaises(AssertionError):
                self.validate()

    def test_changed_proof_scope_or_device_claim_is_rejected(self):
        with self.local_copy() as (_, __, proof):
            for key, value in (('reviewed_path', 'index.html'), ('candidate_commit', '0' * 40),
                               ('physical_tablet_verified', True), ('baseline_commit', '0' * 40)):
                payload = copy.deepcopy(successor.EXPECTED)
                payload[key] = value
                proof.write_text(json.dumps(payload))
                with self.subTest(key=key), self.assertRaises(AssertionError):
                    self.validate()

    def test_proof_symlink_is_rejected(self):
        with self.local_copy() as (root, _, proof):
            saved = root / 'saved-proof.json'
            saved.write_bytes(proof.read_bytes())
            proof.unlink()
            proof.symlink_to(saved)
            with self.assertRaises(AssertionError):
                self.validate()

    def test_other_four_legacy_siblings_still_reject_live_tamper(self):
        original = Path.read_bytes
        for name in sorted(set(legacy.EXPECTED['files']) - {MENU}):
            def changed(path, name=name):
                raw = original(path)
                return raw + b'changed' if path == REAL_ROOT / name else raw
            with self.subTest(path=name), patch.object(Path, 'read_bytes', changed), \
                    self.assertRaises(AssertionError):
                legacy.validate_workspace_review_v1018('index.html')


if __name__ == '__main__':
    unittest.main()
