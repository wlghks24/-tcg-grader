"""Local deterministic Git transactions, never the tablet's files or processes."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from execution import tablet_inplace_patch as m


class InplacePatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.repo = self.base / 'app'
        self.repo.mkdir()
        self.backups = self.base / 'backups'
        self.g('init', '-b', 'main')
        self.g('config', 'user.name', 'Fixture')
        self.g('config', 'user.email', 'fixture@localhost')
        self.g('remote', 'add', 'origin', m.support.OFFICIAL)
        for name, text in {'tcg_updater.py': 'original\n', 'obsolete.py': 'obsolete\n',
                           'learning_store.json': '{"old":true}\n',
                           'index.html': 'original UI\n'}.items():
            (self.repo / name).write_text(text)
        self.g('add', '.')
        self.g('commit', '-m', 'base')
        self.original_main = self.g('rev-parse', 'HEAD')
        (self.repo / 'tcg_updater.py').write_text('official code\n')
        (self.repo / 'obsolete.py').unlink()
        (self.repo / 'nested').mkdir()
        (self.repo / 'nested/new.py').write_text('new source\n')
        (self.repo / 'learning_store.json').write_text('{"upstream":true}\n')
        self.g('add', '-A')
        self.g('commit', '-m', 'official reviewed release')
        self.target = self.g('rev-parse', 'HEAD')
        self.g('update-ref', 'refs/remotes/origin/main', self.target)
        self.g('checkout', '--detach', self.original_main)
        (self.repo / 'index.html').write_text('divergent old tablet UI\n')
        self.g('add', '.')
        self.g('commit', '-m', 'tablet history divergence')
        self.before = self.g('rev-parse', 'HEAD')
        self.g('update-ref', 'refs/heads/main', self.original_main)
        (self.repo / 'learning_store.json').write_text('{"device_learning":42}\n')
        self.g('add', 'learning_store.json')
        (self.repo / 'learning_store.json').write_text('{"device_learning":43}\n')
        (self.repo / 'tcg_updater.py').write_text('local source edit\n')
        (self.repo / 'photos').mkdir()
        (self.repo / 'photos/photo.jpg').write_bytes(b'real photo fixture')
        (self.repo / '.gitignore').write_text('photos/\n')
        self.index_bytes = (self.repo / '.git/index').read_bytes()
        self.dirty_source = (self.repo / 'tcg_updater.py').read_bytes()
        self.preflight = mock.patch.object(m.support, 'verify_candidate')
        self.verify = self.preflight.start()
        self.addCleanup(self.preflight.stop)
        self.quiet = mock.patch.object(m, 'idle')
        self.quiet.start()
        self.addCleanup(self.quiet.stop)

    def g(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], stderr=subprocess.DEVNULL).decode().strip()

    def apply(self):
        return m.patch(self.repo, self.backups, self.target, apply=True)

    def retained(self):
        self.assertEqual((self.repo / 'learning_store.json').read_text(), '{"device_learning":43}\n')
        self.assertEqual((self.repo / 'photos/photo.jpg').read_bytes(), b'real photo fixture')

    def restored(self, out):
        self.assertEqual(out['status'], 'HOLD', out)
        self.assertEqual(out['rollback'], 'ORIGINAL_SOURCE_HEAD_INDEX_RESTORED', out)
        self.assertEqual(self.g('rev-parse', 'HEAD'), self.before)
        self.assertNotEqual(subprocess.run(['git', '-C', str(self.repo), 'symbolic-ref', '-q', 'HEAD'], capture_output=True).returncode, 0)
        self.assertEqual(self.g('rev-parse', 'main'), self.original_main)
        self.assertEqual((self.repo / '.git/index').read_bytes(), self.index_bytes)
        self.assertEqual((self.repo / 'tcg_updater.py').read_bytes(), self.dirty_source)
        self.assertTrue((self.repo / 'obsolete.py').is_file())
        self.assertFalse((self.repo / 'nested').exists())
        self.retained()

    def test_divergent_detached_update_preserves_data_and_old_branches(self):
        out = self.apply()
        self.assertEqual(out['status'], 'PATCHED_SOURCE_ONLY', out)
        self.assertEqual(self.g('symbolic-ref', '--short', 'HEAD'), 'main')
        self.assertEqual(self.g('rev-parse', 'HEAD'), self.target)
        self.assertEqual(self.g('rev-parse', out['backup_ref']), self.before)
        self.assertEqual(self.g('rev-parse', out['backup_ref'] + '-main'), self.original_main)
        self.assertEqual((self.repo / 'tcg_updater.py').read_text(), 'official code\n')
        self.assertEqual((self.repo / 'index.html').read_text(), 'original UI\n')
        self.assertFalse((self.repo / 'obsolete.py').exists())
        self.assertEqual((self.repo / 'nested/new.py').read_text(), 'new source\n')
        self.assertEqual((Path(out['backup']) / 'original/tcg_updater.py').read_bytes(), self.dirty_source)
        self.assertFalse(out['physical_tablet_verified'])
        self.retained()

    def test_original_staged_data_survives_git_garbage_collection(self):
        staged_blob = self.g('rev-parse', ':learning_store.json')
        out = self.apply()
        self.assertEqual(out['status'], 'PATCHED_SOURCE_ONLY', out)
        self.g('gc', '--prune=now')
        self.assertEqual(self.g('cat-file', '-p', staged_blob), '{"device_learning":42}')
        self.assertEqual(self.g('show', out['index_archive_ref'] + '^2:learning_store.json'), '{"device_learning":42}')
        self.assertEqual(self.g('show', out['index_archive_ref'] + ':learning_store.json'), '{"device_learning":43}')
        self.retained()

    def test_plan_leaves_files_index_refs_and_backups_untouched(self):
        out = m.patch(self.repo, self.backups, self.target)
        self.assertEqual(out['status'], 'PLAN_ONLY')
        self.assertFalse(self.backups.exists())
        self.assertEqual(self.g('rev-parse', 'HEAD'), self.before)
        self.assertEqual((self.repo / '.git/index').read_bytes(), self.index_bytes)
        self.retained()

    def test_wrong_release_pin_holds(self):
        with self.assertRaisesRegex(m.Hold, 'RELEASE_SHA_MISMATCH'):
            m.patch(self.repo, self.backups, 'a' * 40, apply=True)
        self.assertFalse(self.backups.exists())

    def test_unknown_modified_source_holds(self):
        (self.repo / 'obsolete.py').write_text('unknown local edit')
        with self.assertRaisesRegex(m.Hold, 'UNKNOWN_CHANGED_PATH'):
            self.apply()
        self.assertFalse(self.backups.exists())

    def test_untracked_incoming_source_collision_holds(self):
        (self.repo / 'nested').mkdir()
        (self.repo / 'nested/new.py').write_text('device data')
        with self.assertRaisesRegex(m.Hold, 'UNTRACKED_COLLISION'):
            self.apply()
        self.assertEqual((self.repo / 'nested/new.py').read_text(), 'device data')

    def test_ignored_incoming_source_collision_holds(self):
        (self.repo / '.gitignore').write_text('nested/\n')
        self.test_untracked_incoming_source_collision_holds()

    def test_symlink_parent_holds(self):
        outside = self.base / 'outside'
        outside.mkdir()
        (self.repo / 'nested').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(m.Hold, 'SYMLINK_PATH'):
            self.apply()
        self.assertEqual(list(outside.iterdir()), [])

    def test_attached_main_uses_existing_updater(self):
        self.g('symbolic-ref', 'HEAD', 'refs/heads/main')
        with self.assertRaisesRegex(m.Hold, 'DETACHED_CHECKOUT_REQUIRED'):
            self.apply()

    def test_existing_lock_is_not_removed(self):
        lock = self.repo / '.tcg_android_update.lock'
        lock.mkdir()
        with self.assertRaisesRegex(m.Hold, 'UPDATE_LOCK_BUSY'):
            self.apply()
        self.assertTrue(lock.is_dir())

    def test_running_writer_holds_without_signalling(self):
        with mock.patch.object(m, 'idle', side_effect=m.Hold('REPO_PROCESS_BUSY')):
            with self.assertRaisesRegex(m.Hold, 'REPO_PROCESS_BUSY'):
                self.apply()
        self.assertFalse(self.backups.exists())

    def test_candidate_gate_failure_does_not_modify_source(self):
        self.verify.side_effect = m.Hold('CANDIDATE_CHECK_FAILED')
        out = self.apply()
        self.assertEqual(out['reason'], 'CANDIDATE_CHECK_FAILED')
        self.assertEqual((self.repo / '.git/index').read_bytes(), self.index_bytes)
        self.assertEqual((self.repo / 'tcg_updater.py').read_bytes(), self.dirty_source)

    def test_mid_file_failure_rolls_back(self):
        actual = m.atomic_copy
        def fail(src, dst, mode):
            if 'incoming' in src.parts and dst == self.repo / 'tcg_updater.py':
                raise OSError('injected disk error')
            return actual(src, dst, mode)
        with mock.patch.object(m, 'atomic_copy', side_effect=fail):
            self.restored(self.apply())

    def test_index_install_failure_rolls_back(self):
        actual = m.git
        def fail(repo, *args, **kwargs):
            if args[0] == 'read-tree':
                raise m.Hold('INJECTED_INDEX_FAILURE')
            return actual(repo, *args, **kwargs)
        with mock.patch.object(m, 'git', side_effect=fail):
            self.restored(self.apply())

    def test_main_compare_and_swap_failure_rolls_back(self):
        actual = m.git
        def fail(repo, *args, **kwargs):
            if args[:2] == ('update-ref', 'refs/heads/main') and args[2] == self.target:
                raise m.Hold('INJECTED_MAIN_CAS_FAILURE')
            return actual(repo, *args, **kwargs)
        with mock.patch.object(m, 'git', side_effect=fail):
            self.restored(self.apply())

    def test_failure_after_head_attach_restores_detached_head(self):
        actual = m.support.receipt
        def fail(path, value):
            if value.get('phase') == 'COMPLETE':
                raise OSError('receipt disk full')
            return actual(path, value)
        with mock.patch.object(m.support, 'receipt', side_effect=fail):
            self.restored(self.apply())

    def test_ref_command_completing_then_failing_rolls_back(self):
        actual = m.git
        def fail(repo, *args, **kwargs):
            value = actual(repo, *args, **kwargs)
            if args[:2] == ('symbolic-ref', 'HEAD'):
                raise m.Hold('INJECTED_POST_REF_ERROR')
            return value
        with mock.patch.object(m, 'git', side_effect=fail):
            self.restored(self.apply())

    def test_wrong_pin_format_is_rejected(self):
        with self.assertRaisesRegex(m.Hold, 'EXACT_RELEASE_SHA_REQUIRED'):
            m.patch(self.repo, self.backups, 'main', apply=True)

    def test_staged_unknown_source_rejected(self):
        (self.repo / 'obsolete.py').write_text('unknown staged source')
        self.g('add', 'obsolete.py')
        with self.assertRaisesRegex(m.Hold, 'UNKNOWN_CHANGED_PATH'):
            self.apply()

    def test_index_lock_holds_without_source_mutation(self):
        (self.repo / '.git/index.lock').write_text('another git command')
        out = self.apply()
        self.assertEqual(out['reason'], 'INDEX_BUSY_OR_UNSAFE')
        self.assertEqual((self.repo / 'tcg_updater.py').read_bytes(), self.dirty_source)

    def test_runtime_changes_in_preflight_hold_and_keep_latest_data(self):
        def collect(*args):
            (self.repo / 'learning_store.json').write_text('latest external writer bytes')
        self.verify.side_effect = collect
        out = self.apply()
        self.assertEqual(out['reason'], 'RUNTIME_CHANGED')
        self.assertEqual((self.repo / 'learning_store.json').read_text(), 'latest external writer bytes')
        self.assertEqual((self.repo / 'tcg_updater.py').read_bytes(), self.dirty_source)

    def test_backup_inside_checkout_rejected(self):
        with self.assertRaisesRegex(m.Hold, 'BACKUP_MUST_BE_OUTSIDE'):
            m.patch(self.repo, self.repo / 'backup', self.target, apply=True)

    def test_foreign_origin_rejected(self):
        self.g('remote', 'set-url', 'origin', 'https://example.invalid/other.git')
        with self.assertRaisesRegex(m.Hold, 'UNEXPECTED_ORIGIN'):
            self.apply()


if __name__ == '__main__':
    unittest.main()

class InplaceProcessFenceTests(unittest.TestCase):
    def check_process(self, args, *, cwd_inside, busy):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / 'repo'
            repo.mkdir()
            proc = root / 'proc'
            entry = proc / '99999999'
            entry.mkdir(parents=True)
            (entry / 'cwd').symlink_to(repo if cwd_inside else root)
            (entry / 'cmdline').write_bytes(b'\0'.join(a.replace(b'REPO', str(repo).encode()) for a in args) + b'\0')
            if busy:
                with self.assertRaisesRegex(m.Hold, 'REPO_PROCESS_BUSY'):
                    m.idle(repo, proc)
            else:
                m.idle(repo, proc)

    def test_scheduler_inside_checkout_blocks(self):
        self.check_process([b'bash', b'TABLET_SCHEDULED_UPDATE.sh', b'boot-loop'], cwd_inside=True, busy=True)

    def test_absolute_launcher_from_another_cwd_blocks(self):
        self.check_process([b'python', b'REPO/tcg_updater.py'], cwd_inside=False, busy=True)

    def test_unrelated_process_does_not_block(self):
        self.check_process([b'python', b'other.py'], cwd_inside=False, busy=False)
