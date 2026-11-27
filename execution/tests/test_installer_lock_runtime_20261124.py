"""Regression against the actual installer, using existing real local Git fixtures."""
import unittest
from unittest.mock import patch
from execution.tests import test_china_preserved_update_v650 as fixtures


class InstallerLockRuntimeTests(unittest.TestCase):
    def check_retry(self, error):
        case = fixtures.ChinaPreservedUpdateTests('test_untracked_chinese_module_is_hash_verified_then_official_source_adopted')
        case.setUp()
        self.addCleanup(case.doCleanups)
        repo = case.repo
        index = case.case.dirty()
        name = fixtures.NAME
        data = (repo / 'learning_store.json').read_bytes()
        source = (repo / name).read_bytes()
        lock = repo / '.tcg_android_update.lock'
        original = fixtures.m.digest
        def fail_after_lock(path):
            if path == repo / name and lock.exists():
                raise error
            return original(path)
        with patch.object(fixtures.m, 'digest', side_effect=fail_after_lock):
            result = case.case.apply()
        self.assertEqual('HOLD', result['status'])
        self.assertFalse(lock.exists())
        self.assertEqual(case.case.base, case.case.g('rev-parse', 'HEAD').strip())
        self.assertEqual(index, case.case.g('write-tree').strip())
        self.assertEqual(source, (repo / name).read_bytes())
        self.assertEqual(data, (repo / 'learning_store.json').read_bytes())
        retry = case.case.apply()
        self.assertEqual('UPDATED', retry['status'], retry)
        self.assertEqual(data, (repo / 'learning_store.json').read_bytes())
        self.assertFalse(lock.exists())

    def test_hold_after_lock_releases_and_retry_preserves_data(self):
        self.check_retry(fixtures.m.Hold('INJECTED_POST_LOCK_FAILURE'))

    def test_oserror_after_lock_releases_and_retry_preserves_data(self):
        self.check_retry(OSError('injected read failure'))
