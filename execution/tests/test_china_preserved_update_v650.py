"""The tablet's native Git collision, with real Git backup and rollback."""
import hashlib
import json
from pathlib import Path
import subprocess
import unittest
from unittest import mock

from execution.tests import test_tablet_preserved_update as fixtures

m = fixtures.m
NAME = 'tcg_reliability/china_official_catalog_v571.py'


class ChinaPreservedUpdateTests(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.PreservedUpdateTests('test_mm_data_kept_and_both_source_versions_archived')
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.repo = self.case.repo
        self.case.g('checkout', 'candidate')
        path = self.repo / NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('official reviewed Chinese catalog\n')
        self.case.g('add', NAME)
        self.case.g('commit', '-m', 'incoming Chinese catalog')
        self.case.target = self.case.g('rev-parse', 'HEAD').strip()
        self.case.g('update-ref', 'refs/remotes/origin/main', self.case.target)
        self.case.g('checkout', 'main')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'private original Chinese catalog\n')

    def test_untracked_chinese_module_is_hash_verified_then_official_source_adopted(self):
        index = self.case.dirty()
        runtime = (self.repo / 'learning_store.json').read_bytes()
        photo = self.case.root / 'private.webp'
        photo.write_bytes(b'device-only original photo')
        out = self.case.apply()
        self.assertEqual('UPDATED', out['status'], out)
        self.assertEqual([NAME], out['untracked_source_paths'])
        self.assertEqual(index, out['original_index_tree'])
        original = b'private original Chinese catalog\n'
        self.assertEqual(hashlib.sha256(original).hexdigest(), out['untracked_source_sha256'][NAME])
        self.assertEqual(original, (Path(out['backup_directory']) / 'untracked-source-files' / NAME).read_bytes())
        self.assertEqual('official reviewed Chinese catalog\n', (self.repo / NAME).read_text())
        self.assertEqual(runtime, (self.repo / 'learning_store.json').read_bytes())
        self.assertEqual(b'device-only original photo', photo.read_bytes())

    def test_native_failure_reports_other_collision_and_restores_original_module_and_index(self):
        original_module = (self.repo / NAME).read_bytes()
        (self.repo / NAME).unlink()
        self.case.g('checkout', 'candidate')
        (self.repo / 'unreviewed.txt').write_text('incoming official file')
        self.case.g('add', 'unreviewed.txt')
        self.case.g('commit', '-m', 'another incoming collision')
        self.case.target = self.case.g('rev-parse', 'HEAD').strip()
        self.case.g('update-ref', 'refs/remotes/origin/main', self.case.target)
        self.case.g('checkout', 'main')
        (self.repo / NAME).parent.mkdir(parents=True, exist_ok=True)
        (self.repo / NAME).write_bytes(original_module)
        (self.repo / 'unreviewed.txt').write_text('keep unrelated private file')
        index = self.case.dirty()
        out = self.case.apply()
        self.assertEqual('HOLD', out['status'], out)
        self.assertEqual('ORIGINAL_INDEX_AND_SOURCE_RESTORED', out['rollback'])
        self.assertEqual('ORIGINAL_UNTRACKED_SOURCE_RESTORED', out['untracked_rollback'])
        self.assertEqual(b'private original Chinese catalog\n', (self.repo / NAME).read_bytes())
        self.assertEqual(index, self.case.g('write-tree').strip())
        self.assertEqual(self.case.base, self.case.g('rev-parse', 'HEAD').strip())
        self.assertIn('unreviewed.txt', out['git_failure']['stderr'])
        self.assertTrue(out['git_failure']['operation'].startswith('merge --ff-only'))
        self.assertEqual(1, out['git_failure']['exit_code'])
        self.assertEqual('keep unrelated private file', (self.repo / 'unreviewed.txt').read_text())
        receipt = json.loads((Path(out['backup_directory']) / 'receipt.json').read_text())
        self.assertEqual(out['git_failure'], receipt['git_failure'])

    def test_corrupt_backup_never_removes_original_module(self):
        copy = m.shutil.copy2
        def corrupt(source, target, *args, **kwargs):
            result = copy(source, target, *args, **kwargs)
            if Path(target).name == Path(NAME).name:
                Path(target).write_bytes(b'corrupted copy')
            return result
        with mock.patch.object(m.shutil, 'copy2', side_effect=corrupt):
            out = self.case.apply()
        self.assertEqual('HOLD', out['status'])
        self.assertEqual('UNTRACKED_BACKUP_VERIFICATION_FAILED', out['reason'])
        self.assertEqual(b'private original Chinese catalog\n', (self.repo / NAME).read_bytes())

    def test_symlink_module_cannot_read_or_overwrite_private_target(self):
        path = self.repo / NAME
        path.unlink()
        outside = self.case.root / 'outside-private.py'
        outside.write_bytes(b'private outside bytes')
        path.symlink_to(outside)
        with self.assertRaises(m.Hold):
            self.case.apply()
        self.assertEqual(b'private outside bytes', outside.read_bytes())
        self.assertFalse(self.case.backups.exists())

    def test_parent_symlink_is_rejected_before_backup_or_file_mutation(self):
        path = self.repo / NAME
        path.unlink()
        path.parent.rmdir()
        outside = self.case.root / 'outside-private'
        outside.mkdir()
        (outside / path.name).write_bytes(b'private parent bytes')
        path.parent.symlink_to(outside, target_is_directory=True)
        original = m.git
        def inventory(repo, *args, **kwargs):
            if args[:2] == ('ls-files', '--others'):
                return NAME + '\0'
            return original(repo, *args, **kwargs)
        with mock.patch.object(m, 'git', side_effect=inventory):
            with self.assertRaisesRegex(m.Hold, 'UNSAFE_UNTRACKED_SOURCE_PARENT'):
                self.case.apply()
        self.assertEqual(b'private parent bytes', (outside / path.name).read_bytes())
        self.assertFalse(self.case.backups.exists())

    def test_failure_diagnostics_are_bounded_and_credentials_redacted(self):
        exc = subprocess.CalledProcessError(1, ['git', '-C', '/local', 'merge', '--ff-only', 'a'*40],
            output=b'x'*10000,
            stderr=b'https://user:secret@example.test/?token=bad ghp_secret123 password=secret\n' + b'z'*10000)
        details = m.failure_details(exc)['git_failure']
        self.assertTrue(details['operation'].startswith('merge --ff-only'))
        self.assertLessEqual(len(details['stderr']), 4096)
        self.assertLessEqual(len(details['stdout']), 1024)
        self.assertNotIn('secret', json.dumps(details))
        exc.stderr = b'https://user:secret@example.test/ ghp_secret123 token=secret'
        self.assertNotIn('secret', json.dumps(m.failure_details(exc)))
        self.assertEqual({}, m.failure_details(m.Hold('unchanged hold')))
