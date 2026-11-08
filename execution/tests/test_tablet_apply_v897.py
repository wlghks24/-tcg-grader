"""Actual temporary Git histories/data backups; no device process or network."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from execution import apply_tablet_candidate_v897 as delivery

SOURCE = Path(delivery.__file__).read_bytes()


class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        self.root.mkdir()
        self.git('init', '-q')
        self.git('config', 'user.name', 'Offline Test')
        self.git('config', 'user.email', 'test@example.invalid')
        (self.root / 'data.json').write_text('{"labels":5}\n')
        (self.root / 'old.py').write_text('# unchanged\n')
        (self.root / 'integrity_manifest.json').write_text('{}\n')
        (self.root / 'execution').mkdir()
        (self.root / 'execution/existing.py').write_text('# retained\n')
        self.commit('base')
        self.base = self.git('rev-parse', 'HEAD').strip().decode()
        for name, raw in [(delivery.SELF_PATH, SOURCE), (delivery.LAUNCH, b'#!/bin/bash\nexit 0\n'), (delivery.READBACK, b'# offline stub\n')]:
            (self.root / name).write_bytes(raw)
        self.commit('candidate')
        self.target = self.git('rev-parse', 'HEAD').strip().decode()
        self.git('switch', '--detach', self.base)
        (self.root / 'data.json').write_text('{"labels":6}\n')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], stderr=subprocess.PIPE, timeout=10)

    def commit(self, message):
        self.git('add', '.')
        self.git('commit', '-qm', message)

    def plan(self):
        return delivery.plan(self.root, self.base, self.target, own_source=SOURCE)

    def new_candidate(self, change):
        self.git('switch', '--detach', self.target)
        change()
        self.commit('additional change')
        self.target = self.git('rev-parse', 'HEAD').strip().decode()
        self.git('switch', '--detach', self.base)
        (self.root / 'data.json').write_text('{"labels":6}\n')

    def test_plan_preserves_dirty_runtime_json_without_stash_or_restore(self):
        self.assertEqual(self.target, self.plan().target)
        self.assertEqual(b'{"labels":6}\n', (self.root / 'data.json').read_bytes())
        self.assertEqual(self.base, self.git('rev-parse', 'HEAD').strip().decode())

    def test_candidate_data_change_is_rejected(self):
        self.new_candidate(lambda: (self.root / 'new-data.json').write_text('{}\n'))
        with self.assertRaises(ValueError): self.plan()

    def test_candidate_outside_support_scope_is_rejected(self):
        self.new_candidate(lambda: (self.root / 'old.py').write_text('# changed\n'))
        with self.assertRaises(ValueError): self.plan()

    def test_existing_feature_removal_is_rejected(self):
        self.new_candidate(lambda: (self.root / 'execution/existing.py').unlink())
        with self.assertRaises(ValueError): self.plan()

    def test_dirty_source_or_staged_changes_are_not_discarded(self):
        (self.root / 'old.py').write_text('# local user work\n')
        with self.assertRaises(ValueError): self.plan()
        self.git('add', 'old.py')
        with self.assertRaises(ValueError): self.plan()
        self.assertEqual('# local user work\n', (self.root / 'old.py').read_text())

    def test_untracked_candidate_collision_is_preserved_and_rejected(self):
        path = self.root / delivery.READBACK
        path.write_text('# untracked owner file\n')
        with self.assertRaises(ValueError): self.plan()
        self.assertEqual('# untracked owner file\n', path.read_text())

    def test_ignored_candidate_collision_is_preserved_and_rejected(self):
        (self.root / '.git/info/exclude').write_text(delivery.READBACK + '\n')
        path = self.root / delivery.READBACK
        path.write_text('# important ignored local file\n')
        with self.assertRaises(ValueError): self.plan()
        self.assertEqual('# important ignored local file\n', path.read_text())

    def test_git_checkout_itself_refuses_late_ignored_collision(self):
        task = self.plan()
        (self.root / '.git/info/exclude').write_text(delivery.READBACK + '\n')
        path = self.root / delivery.READBACK
        path.write_text('# appeared after planning\n')
        with self.assertRaises(subprocess.SubprocessError):
            delivery.switch_and_check(task, check_runner=lambda *a, **k: None)
        self.assertEqual('# appeared after planning\n', path.read_text())
        self.assertEqual(self.base, self.git('rev-parse', 'HEAD').strip().decode())

    def test_self_source_must_equal_reviewed_blob(self):
        with self.assertRaises(ValueError):
            delivery.plan(self.root, self.base, self.target, own_source=SOURCE + b'\n')

    def test_wrong_base_or_abbreviated_revision_rejected(self):
        for base, target in [(self.target, self.base), (self.base[:8], self.target), (self.base, self.base)]:
            with self.assertRaises(ValueError): delivery.plan(self.root, base, target, own_source=SOURCE)

    def test_backup_contains_current_json_and_patch_without_touching_source(self):
        task = self.plan()
        result = delivery.backup(task)
        self.assertEqual(self.base, (result / 'BASE_SHA.txt').read_text().strip())
        self.assertIn(b'labels', (result / 'tracked-data.patch').read_bytes())
        with tarfile.open(result / 'runtime-json.tar.gz') as archive:
            self.assertEqual(b'{"labels":6}\n', archive.extractfile('data.json').read())
        self.assertEqual(self.base, self.git('rev-parse', 'HEAD').strip().decode())
        self.assertEqual(b'{"labels":6}\n', (self.root / 'data.json').read_bytes())
        self.assertEqual(0o700, result.stat().st_mode & 0o777)

    def test_real_git_switch_preserves_runtime_labels_and_local_main_ref(self):
        task = self.plan()
        old_refs = self.git('show-ref', '--heads')
        delivery.switch_and_check(task, check_runner=lambda *a, **k: None)
        self.assertEqual(self.target, self.git('rev-parse', 'HEAD').strip().decode())
        self.assertEqual(b'{"labels":6}\n', (self.root / 'data.json').read_bytes())
        self.assertEqual(old_refs, self.git('show-ref', '--heads'))

    def test_post_switch_check_failure_rolls_source_back_but_keeps_data(self):
        def fail(*args, **kwargs): raise ValueError('failed check')
        with self.assertRaises(ValueError): delivery.switch_and_check(self.plan(), check_runner=fail)
        self.assertEqual(self.base, self.git('rev-parse', 'HEAD').strip().decode())
        self.assertEqual(b'{"labels":6}\n', (self.root / 'data.json').read_bytes())

    def test_unknown_port_owner_is_not_signalled(self):
        with patch.object(delivery, 'port_open', return_value=True), patch.object(delivery.os, 'kill') as kill:
            with self.assertRaises(ValueError): delivery.stop_launcher(self.root)
            kill.assert_not_called()

    def test_malformed_pid_or_wrong_process_is_not_signalled(self):
        folder = self.root / '.tcg_android_start.lock'
        folder.mkdir()
        for value in ['-1', 'garbage', str(os.getpid())]:
            (folder / 'pid').write_text(value)
            with patch.object(delivery.os, 'kill') as kill:
                with self.assertRaises((OSError, ValueError)): delivery.stop_launcher(self.root)
                kill.assert_not_called()

    def test_v970_stop_uses_pidfd_owner_guard_not_numeric_kill(self):
        from execution import tablet_runtime_handoff as handoff
        launcher = self.root / 'START_TCG_UPDATER_ANDROID.sh'
        launcher.write_text('# owned launcher fixture\\n')
        with patch.object(handoff, 'launcher_identity', side_effect=['start-123', 'start-123']) as identity, \\
             patch.object(handoff, 'signal_launcher') as safe_signal, \\
             patch.object(delivery.os, 'kill') as numeric_kill:
            delivery.signal_verified_launcher(
                self.root, 123456, ['bash', str(launcher)], self.root)
            self.assertEqual(2, identity.call_count)
            safe_signal.assert_called_once_with(self.root, 123456, 'start-123')
            numeric_kill.assert_not_called()

    def test_v970_pid_reuse_and_missing_pidfd_stop_before_mutation(self):
        from execution import tablet_runtime_handoff as handoff
        launcher = self.root / 'START_TCG_UPDATER_ANDROID.sh'
        launcher.write_text('# owned launcher fixture\\n')
        for stamps in ([None], ['early', 'reused']):
            with self.subTest(stamps=stamps), \\
                 patch.object(handoff, 'launcher_identity', side_effect=stamps), \\
                 patch.object(handoff, 'signal_launcher') as signal, \\
                 patch.object(delivery.os, 'kill') as numeric_kill:
                with self.assertRaises(ValueError):
                    delivery.signal_verified_launcher(
                        self.root, 123456, ['bash', str(launcher)], self.root)
                signal.assert_not_called()
                numeric_kill.assert_not_called()
        with patch.object(handoff, 'launcher_identity', side_effect=['start', 'start']), \\
             patch.object(handoff, 'signal_launcher', side_effect=handoff.HandoffHold('PIDFD_UNAVAILABLE')) as signal, \\
             patch.object(delivery.os, 'kill') as numeric_kill:
            with self.assertRaisesRegex(ValueError, 'PIDFD_SAFE_STOP'):
                delivery.signal_verified_launcher(
                    self.root, 123456, ['bash', str(launcher)], self.root)
            signal.assert_called_once()
            numeric_kill.assert_not_called()

    def test_launcher_path_must_be_exact_not_just_same_basename(self):
        expected = self.root / 'START_TCG_UPDATER_ANDROID.sh'
        expected.write_text('# expected\n')
        other = Path(self.temp.name) / expected.name
        other.write_text('# other\n')
        self.assertTrue(delivery.launcher_matches(self.root, ['bash', expected.name], self.root))
        self.assertTrue(delivery.launcher_matches(self.root, ['bash', str(expected)], self.root))
        self.assertFalse(delivery.launcher_matches(self.root, ['bash', str(other)], self.root))

    def test_sourced_wrapper_owner_is_exact_repo_two_argument_bash_only(self):
        wrapper = self.root / delivery.LAUNCH
        wrapper.write_text('# reviewed wrapper\n')
        self.assertTrue(delivery.launcher_matches(self.root, ['bash', delivery.LAUNCH], self.root))
        self.assertTrue(delivery.launcher_matches(self.root, ['/bin/bash', str(wrapper)], self.root))
        other = Path(self.temp.name) / 'start_tablet_unified_v897.sh'
        other.write_text('# another project\n')
        for command, cwd in [(['bash', str(other)], self.root),
                             (['bash', '-c', 'anything'], self.root),
                             (['python', str(wrapper)], self.root),
                             (['bash', str(wrapper)], self.root.parent)]:
            self.assertFalse(delivery.launcher_matches(self.root, command, cwd))

    def test_old_bash_refuses_before_other_dependencies_or_process_control(self):
        with patch.object(delivery.shutil, 'which', return_value='/offline/bash'), patch.object(delivery.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'bash')) as run:
            with self.assertRaises(subprocess.SubprocessError):
                delivery.require_startup_readiness(self.root, user_root=Path(self.temp.name) / 'no-boot', runner=run)
            self.assertEqual(1, run.call_count)
            self.assertIn('BASH_VERSINFO', run.call_args.args[0][2])

    def test_legacy_boot_requires_review_before_any_prerequisite_call(self):
        user_root = Path(self.temp.name) / 'user-config'
        boot = user_root / '.termux/boot/TCG_AUTO_START.sh'
        boot.parent.mkdir(parents=True)
        boot.write_text('python tcg_updater.py\n')
        with patch.object(delivery.subprocess, 'run') as run:
            with self.assertRaises(ValueError): delivery.require_startup_readiness(self.root, user_root=user_root, runner=run)
            run.assert_not_called()

    def test_missing_ocr_or_korean_language_refuses_automatic_install(self):
        user_root = Path(self.temp.name) / 'no-boot'
        for executable, languages in [(None, ''), ('/offline/tesseract', 'eng\nosd')]:
            with patch.object(delivery.shutil, 'which', return_value=executable), patch.object(delivery.subprocess, 'run', return_value=SimpleNamespace(stdout=languages)) as run:
                with self.assertRaises(ValueError): delivery.require_startup_readiness(self.root, user_root=user_root, runner=run)
                self.assertLessEqual(run.call_count, 3)

    def test_present_dependencies_allow_existing_launcher_without_installer(self):
        with patch.object(delivery.shutil, 'which', return_value='/offline/tesseract'), patch.object(delivery.subprocess, 'run', return_value=SimpleNamespace(stdout='eng\nkor\n')) as run:
            delivery.require_startup_readiness(self.root, user_root=Path(self.temp.name) / 'no-boot', runner=run)
            self.assertEqual(3, run.call_count)

    def test_check_only_never_stops_process_or_creates_backup(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch.object(delivery, 'stop_launcher') as stop, patch.object(delivery, 'backup') as backup:
            result = delivery.main(['--repo', str(self.root), '--expected-base', self.base, '--target-sha', self.target, '--check-only'])
        self.assertEqual(0, result)
        self.assertIn('DELIVERY_PLAN_OK', output.getvalue())
        stop.assert_not_called(); backup.assert_not_called()

    def test_stop_or_backup_failure_never_changes_revision(self):
        args = ['--repo', str(self.root), '--expected-base', self.base, '--target-sha', self.target]
        for stage in ('stop_launcher', 'backup'):
            output = io.StringIO()
            with contextlib.redirect_stdout(output), patch.object(delivery, 'require_startup_readiness'), patch.object(delivery, 'stop_launcher') as stop, patch.object(delivery, 'backup') as backup:
                (stop if stage == 'stop_launcher' else backup).side_effect = ValueError('failed')
                self.assertEqual(1, delivery.main(args))
            self.assertEqual('HOLD_DELIVERY_NOT_COMPLETE', json.loads(output.getvalue())['status'])
            self.assertEqual(self.base, self.git('rev-parse', 'HEAD').strip().decode())

    def test_owned_legacy_restart_is_rechecked_after_switch_before_final_handoff(self):
        events = []
        args = ['--repo', str(self.root), '--expected-base', self.base, '--target-sha', self.target]
        def mark(name, value=None):
            def call(*args, **kwargs): events.append(name); return value
            return call
        def exec_fixture(*args):
            events.append('exec'); raise ValueError('offline handoff complete')
        with contextlib.redirect_stdout(io.StringIO()), patch.object(delivery, 'require_startup_readiness', side_effect=mark('ready')), patch.object(delivery, 'stop_launcher', side_effect=mark('stop')), patch.object(delivery, 'backup', side_effect=mark('backup', self.root.parent)), patch.object(delivery, 'switch_and_check', side_effect=mark('switch')), patch.object(delivery.os, 'execvp', side_effect=exec_fixture), patch.object(delivery.os, 'chdir'):
            delivery.main(args)
        self.assertEqual(['ready', 'stop', 'backup', 'switch', 'stop', 'exec'], events)


if __name__ == '__main__':
    unittest.main()
