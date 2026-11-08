"""V971 diagnosis tests against throwaway Git repos, never the Lenovo checkout."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from execution.tablet_update_status_diagnostic_v971 import diagnose, _reported_status


class TabletUpdateStatusV971Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tcg-v971-git-')
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'TCG CI fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        (self.repo / 'source.py').write_text('print("v1")\n', encoding='utf-8')
        (self.repo / 'learning_store.json').write_text('{}\n', encoding='utf-8')
        self.git('add', '--', 'source.py', 'learning_store.json')
        self.git('commit', '-qm', 'fixture base main')

    def git(self, *args):
        result = subprocess.run(
            ['git', '-C', str(self.repo), *args],
            capture_output=True, text=True, check=False, timeout=15)
        if result.returncode:
            self.fail('fixture git failed: ' + ' '.join(args) + '\n' + result.stderr)
        return result.stdout.strip()

    def test_detached_ahead_runtime_data_does_not_blame_learning_json(self):
        self.git('checkout', '-q', '--detach')
        (self.repo / 'source.py').write_text('print("candidate")\n',
                                            encoding='utf-8')
        self.git('add', '--', 'source.py')
        self.git('commit', '-qm', 'fixture V927 device candidate')
        (self.repo / 'learning_store.json').write_text('{"learned":true}\n',
                                                      encoding='utf-8')
        status = self.repo / 'status.env'
        status.write_text('RESULT=LOCAL_CHANGES_HOLD\n', encoding='utf-8')
        before = (self.git('rev-parse', 'HEAD'), self.git('status', '--porcelain'))
        report = diagnose(self.repo, status)
        after = (self.git('rev-parse', 'HEAD'), self.git('status', '--porcelain'))
        self.assertEqual(before, after)
        self.assertEqual(report['classification'], 'DETACHED_HEAD_HOLD')
        self.assertEqual(report['branch'], '(detached)')
        self.assertEqual(report['ahead_of_local_main'], 1)
        self.assertEqual(report['behind_local_main'], 0)
        self.assertEqual(report['scheduled_reported_status'], 'LOCAL_CHANGES_HOLD')
        self.assertTrue(report['scheduled_status_mismatch'])
        self.assertTrue(report['tracked_modified'])
        self.assertFalse(report['installation_permitted'])

    def test_missing_main_ref_is_hold_without_false_remote_claim(self):
        # Explicitly model tablets where the local main name is absent.
        self.git('checkout', '-q', '--detach')
        self.git('branch', '-D', 'main')
        r = diagnose(self.repo)
        self.assertEqual(r['classification'], 'DETACHED_HEAD_HOLD')
        self.assertIsNone(r['local_main'])
        self.assertIsNone(r['origin_main_cached'])
        self.assertIsNone(r['ahead_of_local_main'])
        self.assertIsNone(r['behind_local_main'])
        self.assertFalse(r['installation_permitted'])

    def test_detached_without_runtime_edits_is_still_detached(self):
        self.git('checkout', '-q', '--detach')
        r = diagnose(self.repo)
        self.assertEqual(r['classification'], 'DETACHED_HEAD_HOLD')
        self.assertFalse(r['tracked_modified'])

    def test_nonmain_branch_reports_branch_without_data_mutation(self):
        self.git('switch', '-q', '-c', 'tablet-v927-preserved')
        (self.repo / 'learning_store.json').write_text('{"count":1}\n',
                                                      encoding='utf-8')
        r = diagnose(self.repo)
        self.assertEqual(r['classification'], 'NON_MAIN_BRANCH_HOLD')
        self.assertEqual(r['branch'], 'tablet-v927-preserved')

    def test_main_staged_edited_file_is_distinguished(self):
        (self.repo / 'source.py').write_text('print("unstable")\n',
                                            encoding='utf-8')
        self.git('add', '--', 'source.py')
        r = diagnose(self.repo)
        self.assertEqual(r['classification'], 'STAGED_CHANGES_HOLD')
        self.assertTrue(r['staged_changes'])
        self.assertFalse(r['installation_permitted'])

    def test_main_dirty_does_not_claim_root_cause_without_log(self):
        (self.repo / 'learning_store.json').write_text('{"count":2}\n',
                                                      encoding='utf-8')
        status = self.repo / 'status.env'
        status.write_text('RESULT=LOCAL_CHANGES_HOLD\n', encoding='utf-8')
        r = diagnose(self.repo, status)
        self.assertEqual(r['classification'], 'MAIN_DIRTY_REVIEW_REQUIRED')
        self.assertFalse(r['scheduled_status_mismatch'])

    def test_clean_main_does_not_authorize_install(self):
        r = diagnose(self.repo)
        self.assertEqual(r['classification'], 'MAIN_CLEAN_REVIEW_REQUIRED')
        self.assertFalse(r['installation_permitted'])
        self.assertEqual(r['head'], r['local_main'])

    def test_never_follows_untrusted_status_symlink(self):
        target = self.repo / 'sensitive.txt'
        target.write_text('RESULT=LOCAL_CHANGES_HOLD\n', encoding='utf-8')
        link = self.repo / 'status.env'
        link.symlink_to(target)
        self.assertEqual(_reported_status(link), 'UNAVAILABLE')

    def test_invalid_status_content_is_not_executed(self):
        status = self.repo / 'status.env'
        status.write_text('RESULT=$(touch bad-file)\n', encoding='utf-8')
        r = diagnose(self.repo, status)
        self.assertEqual(r['scheduled_reported_status'], 'UNAVAILABLE')
        self.assertFalse((self.repo / 'bad-file').exists())

    def test_only_repository_root_accepted(self):
        nested = self.repo / 'subfolder'
        nested.mkdir()
        with self.assertRaises(RuntimeError):
            diagnose(nested)


if __name__ == '__main__':
    unittest.main()
