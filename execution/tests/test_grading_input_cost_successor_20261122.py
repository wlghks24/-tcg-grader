"""Authentic source ancestry plus fail-closed tamper/delegation regressions."""
from contextlib import contextmanager
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from execution import grading_input_cost_successor_20261122 as successor
import sync_v376_successor_test_support as support

REAL_ROOT = successor.ROOT
BASE = successor.EXPECTED['baseline_commit']
FIRST = successor.EXPECTED['source_commit']
FINAL = successor.EXPECTED['final_source_commit']
PATHS = successor.EXPECTED['reviewed_paths']
OLDER_SOURCE = '839c5890752d39343c1345c996dd8568baeecdeb'


def authentic_git(*args):
    return subprocess.check_output(['git', *args], cwd=REAL_ROOT, timeout=30)


class GradingInputCostSuccessorTests(unittest.TestCase):
    def validate(self, source=OLDER_SOURCE):
        return successor.validate_grading_input_cost_successor_20261122(source)

    @contextmanager
    def local_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in PATHS:
                (root / name).write_bytes((REAL_ROOT / name).read_bytes())
            proof = root / '.github/tablet-autonomy/grading_input_cost_successor_20261122.json'
            proof.parent.mkdir(parents=True)
            proof.write_bytes(successor.PROOF.read_bytes())
            with patch.object(successor, 'ROOT', root), patch.object(successor, 'PROOF', proof), \
                    patch.object(successor, '_git', side_effect=authentic_git):
                yield root, proof

    def test_exact_real_initial_and_final_history_and_only_two_path_delegation(self):
        self.assertEqual(self.validate(), frozenset(PATHS))
        self.assertEqual(self.validate(BASE), frozenset(PATHS))
        visible = sorted(PATHS + ['index.html', 'update_promo_events.py'])
        self.assertEqual(support.preserve_reviewed_grading_input_cost_scope_20261122(visible, OLDER_SOURCE),
                         ['index.html', 'update_promo_events.py'])
        self.assertEqual(len(successor.EXPECTED['source_scope']), 8)
        for field in ('physical_tablet_verified', 'main_merge_authorized',
                      'model_training_authorized', 'runtime_data_modified'):
            self.assertIs(successor.EXPECTED[field], False)
        self.assertEqual(successor.EXPECTED['reviewed'][PATHS[0]],
                         successor.EXPECTED['source_scope'][PATHS[0]])

    def test_invalid_source_and_non_head_delegate_leave_full_scope_visible(self):
        for source in (True, None, '', 'main', '0' * 39, '0' * 41, '--all'):
            with self.subTest(source=source), self.assertRaises(AssertionError):
                self.validate(source)
            self.assertEqual(support.preserve_reviewed_grading_input_cost_scope_20261122(PATHS, source), PATHS)
        for head in (BASE, FIRST, FINAL, 'main'):
            self.assertEqual(support.preserve_reviewed_grading_input_cost_scope_20261122(PATHS, BASE, head), PATHS)

    def test_older_edits_cannot_be_hidden(self):
        def changed(*args):
            if args == ('diff', '--no-renames', '--name-only', '-z', OLDER_SOURCE, BASE, '--', *PATHS):
                return (PATHS[0] + '\0').encode()
            return authentic_git(*args)
        with patch.object(successor, '_git', side_effect=changed), self.assertRaises(AssertionError):
            self.validate()
        with patch.object(successor, '_git', side_effect=changed):
            self.assertEqual(support.preserve_reviewed_grading_input_cost_scope_20261122(PATHS, OLDER_SOURCE), PATHS)

    def test_every_ancestry_edge_is_required(self):
        head = authentic_git('rev-parse', 'HEAD').decode().strip()
        for edge in ((OLDER_SOURCE, BASE), (BASE, FIRST), (FIRST, FINAL), (FINAL, head)):
            def changed(*args):
                if args == ('merge-base', '--is-ancestor', *edge):
                    raise subprocess.CalledProcessError(1, ['git', *args])
                return authentic_git(*args)
            with self.subTest(edge=edge), patch.object(successor, '_git', side_effect=changed), \
                    self.assertRaises(subprocess.CalledProcessError):
                self.validate()

    def test_initial_and_final_delta_scopes_are_exact(self):
        for before, after, key in ((BASE, FIRST, 'source_scope'), (FIRST, FINAL, 'final_scope')):
            rows = sorted(successor.EXPECTED[key])
            for altered in (rows + ['update_promo_events.py'], rows[:-1], list(reversed(rows))):
                def changed(*args):
                    if args == ('diff', '--no-renames', '--name-only', '-z', before, after):
                        return ('\0'.join(altered) + '\0').encode()
                    return authentic_git(*args)
                with self.subTest(stage=key, scope=altered), patch.object(successor, '_git', side_effect=changed), \
                        self.assertRaises(AssertionError):
                    self.validate()

    def test_baseline_initial_and_final_blob_and_bytes_are_pinned(self):
        for ref, name in ((BASE, PATHS[0]), (FIRST, PATHS[1]), (FINAL, PATHS[1])):
            target = ref + ':' + name
            for command in ('rev-parse', 'show'):
                def changed(*args):
                    raw = authentic_git(*args)
                    if args == (command, target):
                        return b'0' * 40 + b'\n' if command == 'rev-parse' else raw + b'changed'
                    return raw
                with self.subTest(ref=ref, command=command), patch.object(successor, '_git', side_effect=changed), \
                        self.assertRaises(AssertionError):
                    self.validate()

    def test_changed_committed_head_is_rejected_for_each_runtime(self):
        virtual_head = 'f' * 40
        for name in PATHS:
            def changed(*args):
                if args == ('rev-parse', 'HEAD'):
                    return (virtual_head + '\n').encode()
                if args == ('merge-base', '--is-ancestor', FINAL, virtual_head):
                    return b''
                if args[0] in ('rev-parse', 'show') and args[1].startswith(virtual_head + ':'):
                    path = args[1].split(':', 1)[1]
                    if path == name and args[0] == 'rev-parse':
                        return b'0' * 40 + b'\n'
                    return authentic_git(args[0], FINAL + ':' + path)
                if args[:3] == ('ls-tree', '-z', virtual_head):
                    return authentic_git('ls-tree', '-z', FINAL, *args[3:])
                return authentic_git(*args)
            with self.subTest(path=name), patch.object(successor, '_git', side_effect=changed), \
                    self.assertRaises(AssertionError):
                self.validate()

    def test_committed_symlink_mode_is_rejected(self):
        def changed(*args):
            raw = authentic_git(*args)
            return raw.replace(b'100644 blob ', b'120000 blob ', 1) if args[0] == 'ls-tree' else raw
        with patch.object(successor, '_git', side_effect=changed), self.assertRaises(AssertionError):
            self.validate()

    def test_each_live_file_is_reread_and_same_size_tamper_is_rejected(self):
        for name in PATHS:
            with self.subTest(path=name), self.local_copy() as (root, _):
                self.assertEqual(self.validate(), frozenset(PATHS))
                path = root / name
                raw = path.read_bytes()
                path.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
                with self.assertRaises(AssertionError):
                    self.validate()
                self.assertEqual(support.preserve_reviewed_grading_input_cost_scope_20261122(PATHS, OLDER_SOURCE), PATHS)

    def test_each_live_symlink_and_missing_file_are_rejected(self):
        for name in PATHS:
            with self.subTest(path=name), self.local_copy() as (root, _):
                path = root / name
                saved = root / 'saved'
                saved.write_bytes(path.read_bytes())
                path.unlink()
                with self.assertRaises(AssertionError):
                    self.validate()
                path.symlink_to(saved)
                with self.assertRaises(AssertionError):
                    self.validate()

    def test_proof_pins_scope_and_claim_types_are_immutable(self):
        for key, value in (('baseline_commit', '0' * 40), ('source_commit', '0' * 40),
                           ('final_source_commit', '0' * 40), ('reviewed_paths', PATHS + ['index.html']),
                           ('reviewed', {}), ('final_scope', {}), ('source_scope', {}),
                           ('physical_tablet_verified', True), ('physical_tablet_verified', 0)):
            with self.subTest(field=key), self.local_copy() as (_, proof):
                payload = copy.deepcopy(successor.EXPECTED)
                payload[key] = value
                proof.write_text(json.dumps(payload))
                with self.assertRaises(AssertionError):
                    self.validate()

    def test_proof_symlink_is_rejected(self):
        with self.local_copy() as (root, proof):
            saved = root / 'saved-proof'
            saved.write_bytes(proof.read_bytes())
            proof.unlink()
            proof.symlink_to(saved)
            with self.assertRaises(AssertionError):
                self.validate()

    def test_delegate_refuses_widened_or_failed_validator_results(self):
        original = PATHS + ['index.html']
        for result in (frozenset(PATHS + ['index.html']), frozenset([PATHS[0]]), False):
            with patch.object(successor, 'validate_grading_input_cost_successor_20261122', return_value=result):
                self.assertEqual(support.preserve_reviewed_grading_input_cost_scope_20261122(original, OLDER_SOURCE), original)
        for failure in (AssertionError('tamper'), ValueError('proof'), OSError('unavailable'),
                        subprocess.CalledProcessError(1, ['git'])):
            with patch.object(successor, 'validate_grading_input_cost_successor_20261122', side_effect=failure):
                self.assertEqual(support.preserve_reviewed_grading_input_cost_scope_20261122(original, OLDER_SOURCE), original)


if __name__ == '__main__':
    unittest.main()
