"""Bash syntax/temp-file/Git fixtures only. No boot script, HTTP or device run."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from http.client import IncompleteRead

from execution import tablet_boot_guard_v899 as boot

FIXTURE = Path(__file__).parent / 'fixtures/tcg_boot_v898.sh'
SHA = 'f' * 40


class BootFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.user_root = self.root / 'owner'
        self.path = self.user_root / '.termux/boot/TCG_AUTO_START.sh'
        self.path.parent.mkdir(parents=True)
        self.original = FIXTURE.read_bytes()
        self.path.write_bytes(self.original)
        self.path.chmod(0o700)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        (self.repo / 'learning_store.json').write_text('{"labels":1005}')

    def install(self, **kwargs):
        with patch.object(boot, 'attest', return_value=SHA):
            return boot.install(SHA, repo=self.repo, user_root=self.user_root,
                                checker=kwargs.get('checker', lambda value: {'ok': True}))

    def test_observed_hash_matches_public_fixture_and_patch_is_idempotent(self):
        self.assertEqual(boot.OLD_SHA, boot.digest(self.original))
        proposed = boot.patch_boot(self.original)
        self.assertEqual(boot.NEW_SHA, boot.digest(proposed))
        self.assertEqual(proposed, boot.patch_boot(proposed))

    def test_patch_keeps_supervision_backoff_logging_probe_and_has_unified_health(self):
        raw = boot.patch_boot(self.original).decode()
        for keep in ('sleep 60', 'delay=30', 'delay*2', 'delay=300', 'rotate_log',
                     'tablet_runtime_probe.py', '2097152', 'TCG_ANDROID_STARTUP.log'):
            self.assertIn(keep, raw)
        self.assertIn('python -m execution.tablet_boot_guard_v899 --health', raw)
        self.assertIn('  bash execution/start_tablet_unified_v897.sh >>', raw)
        self.assertNotIn('  bash ANDROID_UPDATE_AND_START.sh >>', raw)
        self.assertIn('ANDROID_UPDATE_AND_START.sh', raw, 'original update tool remains present, separate from candidate boot')

    def test_unknown_modified_or_oversized_boot_is_never_rewritten(self):
        for raw in (self.original + b'# owner customization\n', b'unknown', b'x' * 65537, None):
            with self.assertRaises(ValueError): boot.patch_boot(raw)
        self.path.write_bytes(self.original + b'# owner customization\n')
        with self.assertRaises(ValueError): self.install()
        self.assertTrue(self.path.read_bytes().endswith(b'# owner customization\n'))

    def test_install_is_atomic_private_backed_up_outside_boot_and_keeps_data(self):
        before = (self.repo / 'learning_store.json').read_bytes()
        result = self.install()
        self.assertTrue(result['configured'])
        self.assertTrue(result['changed'])
        self.assertEqual('NOT_RUN', result['reboot_verification'])
        self.assertEqual('NOT_VERIFIED', result['boot_app_installation'])
        saved = Path(result['backup'])
        self.assertEqual(self.original, saved.read_bytes())
        self.assertNotEqual(self.path.parent, saved.parent)
        self.assertEqual(0o600, saved.stat().st_mode & 0o777)
        self.assertEqual(0o700, self.path.stat().st_mode & 0o777)
        self.assertEqual([self.path.name], sorted(p.name for p in self.path.parent.iterdir()))
        self.assertEqual(before, (self.repo / 'learning_store.json').read_bytes())

    def test_repeat_install_does_not_spawn_or_create_duplicate_backups(self):
        first = self.install()
        second = self.install()
        self.assertFalse(second['changed'])
        self.assertEqual(1, len(list(Path(first['backup']).parent.iterdir())))

    def test_unhealthy_current_server_refuses_before_backup_and_write(self):
        with self.assertRaises(ValueError): self.install(checker=lambda value: {'ok': False})
        self.assertEqual(self.original, self.path.read_bytes())
        self.assertFalse((self.path.parent.parent / 'tcg-boot-backups').exists())

    def test_symlink_boot_or_parent_is_not_followed(self):
        other = self.root / 'private-original'
        self.path.rename(other); self.path.symlink_to(other)
        with self.assertRaises(ValueError): self.install()
        self.assertEqual(self.original, other.read_bytes())

    def test_backup_collision_or_symlink_is_not_overwritten(self):
        directory = self.path.parent.parent / 'tcg-boot-backups'
        directory.mkdir()
        target = directory / ('TCG_AUTO_START.sh.' + boot.OLD_SHA + '.bak')
        target.write_bytes(b'owner backup')
        with self.assertRaises(ValueError): self.install()
        self.assertEqual(b'owner backup', target.read_bytes())
        self.assertEqual(self.original, self.path.read_bytes())

    def test_atomic_replace_failure_keeps_old_script_and_leaves_no_boot_temp(self):
        with patch.object(boot.os, 'replace', side_effect=OSError('simulated disk failure')):
            with self.assertRaises(OSError): self.install()
        self.assertEqual(self.original, self.path.read_bytes())
        self.assertEqual([self.path.name], [p.name for p in self.path.parent.iterdir()])
        self.assertEqual([], list(self.path.parent.parent.glob('.tcg-boot-v899-*.tmp')))

    def test_concurrent_owner_change_is_preserved_instead_of_clobbered(self):
        after = boot.patch_boot(self.original)
        self.path.write_bytes(b'owner new customization')
        with self.assertRaises(ValueError): boot._replace(self.path, self.original, after)
        self.assertEqual(b'owner new customization', self.path.read_bytes())

    def test_wrong_owner_is_rejected(self):
        uid = os.getuid()
        with patch.object(boot.os, 'getuid', return_value=uid + 1):
            with self.assertRaises(ValueError): boot.boot_path(self.user_root)

    def test_status_cannot_claim_reboot_or_boot_app_execution(self):
        result = boot.status(self.user_root)
        self.assertFalse(result['configured'])
        self.assertTrue(result['recognized_previous'])
        self.assertEqual('NOT_RUN', result['reboot_verification'])
        self.assertEqual('NOT_VERIFIED', result['boot_app_installation'])

    def test_status_cli_requires_execute_permission_as_well_as_configured_bytes(self):
        self.path.write_bytes(boot.patch_boot(self.original))
        self.path.chmod(0o600)
        value = boot.status(self.user_root)
        self.assertTrue(value['configured'])
        self.assertFalse(value['executable'])
        with patch.object(boot, 'status', return_value=value), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(1, boot.main(['--status']))


class HealthTests(unittest.TestCase):
    def reader(self, route):
        if route == '/api/health':
            # Data failures must not cause process-restart storms on provider403.
            payload = {'ok': True, 'collection_health': {'runtime_build_sha': SHA,
                       'runtime_build_sha_verified': True, 'healthy': False, 'requires_attention': True}}
            return 200, 'application/json', json.dumps(payload).encode()
        return 200, 'text/html', b'<a href="/index.html?target=one">tools</a>'

    def test_alive_generation_and_adapter_not_data_or_model_readiness(self):
        self.assertTrue(boot.runtime_alive(reader=self.reader, git_sha=SHA))

    def test_old_process_or_classic_only_server_is_not_healthy(self):
        self.assertFalse(boot.runtime_alive(reader=self.reader, git_sha='0' * 40))
        def classic(route):
            return self.reader(route) if route == '/api/health' else (404, 'text/html', b'classic')
        self.assertFalse(boot.runtime_alive(reader=classic, git_sha=SHA))

    def test_oversized_malformed_and_unavailable_health_fails_closed_without_text(self):
        for value in (b'[]', b'false', b' ' * 262145):
            self.assertFalse(boot.runtime_alive(reader=lambda route: (200, 'application/json', value), git_sha=SHA))
        def broken(route): raise IncompleteRead(b'PRIVATE_NAME', 50)
        self.assertFalse(boot.runtime_alive(reader=broken, git_sha=SHA))

    def test_health_cli_is_quiet_and_never_installs_or_reboots(self):
        stream = io.StringIO()
        with patch.object(boot, 'revision', return_value=SHA), patch.object(boot, 'attest'), patch.object(boot, 'runtime_alive', return_value=True), patch.object(boot, 'install') as install, contextlib.redirect_stdout(stream):
            self.assertEqual(0, boot.main(['--health']))
            install.assert_not_called()
        self.assertEqual('', stream.getvalue())

    def test_invalid_install_sha_is_reported_without_raw_error_or_any_install(self):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = boot.main(['--install', '--expected-sha', 'not-a-sha'])
        self.assertEqual(1, code)
        self.assertEqual('HOLD_BOOT_UNCHANGED_OR_REVIEW_REQUIRED', json.loads(stream.getvalue())['status'])


class AttestationTests(unittest.TestCase):
    def test_actual_git_source_and_revision_are_required(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            def git(*args):
                return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.PIPE)
            git('init', '-q'); git('config', 'user.name', 'Offline Test'); git('config', 'user.email', 'test@example.invalid')
            path = repo / boot.SELF; path.parent.mkdir()
            path.write_bytes(boot.SOURCE_BYTES)
            git('add', '.'); git('commit', '-qm', 'reviewed source')
            sha = git('rev-parse', 'HEAD').decode().strip()
            with patch.object(boot, 'LEGACY_REPO', repo):
                self.assertEqual(sha, boot.attest(repo, sha))
                with self.assertRaises(ValueError): boot.attest(repo, '0' * 40)
                path.write_bytes(boot.SOURCE_BYTES + b'# local code change\n')
                with self.assertRaises(ValueError): boot.attest(repo, sha)


if __name__ == '__main__':
    unittest.main()
