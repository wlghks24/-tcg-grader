"""Reproduce the tablet's dirty Graphify config in real local Git checkouts."""
import hashlib
from pathlib import Path
import subprocess
import unittest
from unittest import mock

from execution.tests import test_tablet_preserved_update as fixtures

m = fixtures.m


class GraphifyPreservedUpdateTests(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.PreservedUpdateTests(
            'test_mm_data_kept_and_both_source_versions_archived')
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.repo = self.case.repo

    def dirty_config(self):
        path = self.repo / '.graphifyignore'
        path.write_text('# staged local exclusions\nprivate-photos/\n')
        self.case.g('add', '.graphifyignore')
        path.write_text('# current local exclusions\nprivate-photos/\nlocal-reports/\n')
        return path.read_bytes()

    def test_staged_and_worktree_config_are_archived_before_official_install(self):
        self.case.dirty()
        runtime = (self.repo / 'learning_store.json').read_bytes()
        before = self.dirty_config()
        index = self.case.g('write-tree').strip()
        photo = self.case.root / 'private-photos' / 'original.jpg'
        photo.parent.mkdir()
        photo.write_bytes(b'device-only original photo')
        result = self.case.apply()
        self.assertEqual('UPDATED', result['status'], result)
        self.assertIn('.graphifyignore', result['source_paths'])
        self.assertEqual(index, result['original_index_tree'])
        self.assertEqual('# staged local exclusions\nprivate-photos/\n',
                         self.case.g('show', result['backup_ref'] + '^2:.graphifyignore'))
        self.assertEqual(before.decode(),
                         self.case.g('show', result['backup_ref'] + ':.graphifyignore'))
        backup = Path(result['backup_directory']) / 'source-files' / '.graphifyignore'
        self.assertEqual(before, backup.read_bytes())
        self.assertEqual(hashlib.sha256(before).hexdigest(),
                         result['source_before_sha256']['.graphifyignore'])
        self.assertEqual(self.case.g('show', self.case.target + ':.graphifyignore'),
                         (self.repo / '.graphifyignore').read_text())
        self.assertEqual(runtime, (self.repo / 'learning_store.json').read_bytes())
        self.assertEqual(b'device-only original photo', photo.read_bytes())
        self.assertEqual([], result['runtime_changed_during_operation'])

    def test_single_layer_config_changes_are_preserved(self):
        for staged in (False, True):
            with self.subTest(staged=staged):
                case = fixtures.PreservedUpdateTests(
                    'test_mm_data_kept_and_both_source_versions_archived')
                case.setUp()
                self.addCleanup(case.doCleanups)
                path = case.repo / '.graphifyignore'
                path.write_text('# device scope\nprivate/\n')
                if staged:
                    case.g('add', '.graphifyignore')
                before = path.read_bytes()
                result = case.apply()
                self.assertEqual('UPDATED', result['status'], result)
                self.assertEqual(before, (Path(result['backup_directory']) /
                                         'source-files' / '.graphifyignore').read_bytes())

    def test_failed_merge_restores_exact_config_and_index(self):
        before = self.dirty_config()
        index = self.case.g('write-tree').strip()
        original = m.git

        def failed_merge(repo, *args, **kwargs):
            if args and args[0] == 'merge':
                raise subprocess.CalledProcessError(1, args)
            return original(repo, *args, **kwargs)

        with mock.patch.object(m, 'git', side_effect=failed_merge):
            result = self.case.apply()
        self.assertEqual('HOLD', result['status'])
        self.assertEqual('ORIGINAL_INDEX_AND_SOURCE_RESTORED', result['rollback'])
        self.assertEqual(index, self.case.g('write-tree').strip())
        self.assertEqual(before, (self.repo / '.graphifyignore').read_bytes())
        self.assertEqual(self.case.base, self.case.g('rev-parse', 'HEAD').strip())

    def test_failed_backup_keeps_config_and_index(self):
        before = self.dirty_config()
        index = self.case.g('write-tree').strip()
        with mock.patch.object(m, 'verify_candidate', side_effect=m.Hold('PRECHECK_FAIL')):
            result = self.case.apply()
        self.assertEqual('HOLD', result['status'])
        self.assertEqual(before, (self.repo / '.graphifyignore').read_bytes())
        self.assertEqual(index, self.case.g('write-tree').strip())

    def test_symlink_config_does_not_modify_its_target(self):
        target = self.case.root / 'private-config'
        target.write_text('keep private bytes\n')
        path = self.repo / '.graphifyignore'
        path.unlink()
        path.symlink_to(target)
        with self.assertRaises(m.Hold):
            self.case.apply()
        self.assertEqual('keep private bytes\n', target.read_text())
        self.assertFalse(self.case.backups.exists())

    def test_unreviewed_paths_are_all_reported_without_mutation(self):
        before = self.case.g('write-tree').strip()
        with mock.patch.object(m, 'git', return_value=' M VERIFY_TABLET_FINAL.sh\0 M .env\0'):
            with self.assertRaises(m.Hold) as caught:
                m.changes(self.repo)
        self.assertEqual('UNKNOWN_CHANGED_PATH: .env, VERIFY_TABLET_FINAL.sh',
                         str(caught.exception))
        self.assertEqual(before, self.case.g('write-tree').strip())
        self.assertFalse(self.case.backups.exists())
