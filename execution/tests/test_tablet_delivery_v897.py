"""Real Bash dispatch with stub server only; readback HTTP is mocked/offline."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from execution import tablet_device_readback_v897 as device

ROOT = Path(__file__).resolve().parents[2]
SHA = '96ed808772d8b2f8074b74f78158322230cf719b'
MODULES = ('tablet_unified_runtime_v889','tablet_image_unified_v888',
           'tablet_image_recheck_review_v887','tablet_image_reciprocity_v887',
           'tablet_image_recheck_cycle_v887','tablet_unified_ui_v890',
           'tablet_event_summary_v890','tablet_event_freshness_v891',
           'tablet_entity_store_v892','tablet_backlog_priority_v893',
           'tablet_feature_inventory_v894','tablet_target_image_v895',
           'tablet_event_coverage_v896','tablet_device_readback_v897','apply_tablet_candidate_v897')


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.execution = self.root / 'execution'
        self.execution.mkdir()
        (self.execution / '__init__.py').write_text('')
        self.launcher = self.execution / 'start_tablet_unified_v897.sh'
        self.launcher.write_bytes((ROOT / 'execution/start_tablet_unified_v897.sh').read_bytes())
        shutil.copyfile(ROOT / 'START_TCG_UPDATER_ANDROID.sh', self.root / 'START_TCG_UPDATER_ANDROID.sh')
        self.files = {}
        for name in MODULES:
            raw = b'# Offline stub: never import the real runtime\n'
            if name == 'tablet_unified_runtime_v889':
                raw += b'import os\nprint("ACTUAL:"+str(os.getpid()),flush=True)\n'
            if name == 'apply_tablet_candidate_v897':
                raw = (ROOT / 'execution/apply_tablet_candidate_v897.py').read_bytes()
            path = self.execution / (name + '.py')
            path.write_bytes(raw)
            self.files['execution/' + path.name] = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
        (self.root / 'integrity_manifest.json').write_text(json.dumps({'files': self.files}))
        self.bash = shutil.which('bash')
        self.env = dict(os.environ, PYTHONPATH='')
        self.fakebin = self.root / 'bin'
        self.fakebin.mkdir()
        tesseract = self.fakebin / 'tesseract'
        tesseract.write_text('#!' + self.bash + '\necho kor\n')
        tesseract.chmod(0o755)
        self.env['PATH'] = str(self.fakebin) + os.pathsep + self.env['PATH']

    def run_launcher(self, *args):
        return subprocess.run([self.bash, str(self.launcher), *args], cwd=self.root,
                              env=self.env, text=True, capture_output=True, timeout=10)

    def test_check_verifies_code_without_executing_server_or_changing_sources(self):
        before = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result = self.run_launcher('--check')
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn('CODE_CHECK_OK', result.stdout)
        self.assertNotIn('ACTUAL:', result.stdout)
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_incompatible_existing_launcher_is_refused_before_start(self):
        (self.root / 'START_TCG_UPDATER_ANDROID.sh').write_text('# changed launcher\n')
        result = self.run_launcher('--check')
        self.assertNotEqual(0, result.returncode)
        self.assertIn('HOLD', result.stderr)

    def test_module_hash_change_is_refused(self):
        (self.execution / 'tablet_unified_runtime_v889.py').write_text('raise Exception("must not run")\n')
        result = self.run_launcher('--check')
        self.assertNotEqual(0, result.returncode)
        self.assertIn('HOLD', result.stderr)

    def test_symlinked_module_is_refused(self):
        path = self.execution / 'tablet_unified_runtime_v889.py'
        path.rename(self.root / 'outside.py')
        path.symlink_to(self.root / 'outside.py')
        result = self.run_launcher('--check')
        self.assertNotEqual(0, result.returncode)
        self.assertIn('symlink', result.stderr)

    def test_unknown_arguments_do_not_start(self):
        self.assertEqual(2, self.run_launcher('--unsafe').returncode)
        self.assertEqual(2, self.run_launcher('--check', 'extra').returncode)

    def test_real_exported_function_dispatches_server_and_preserves_server_pid(self):
        fakebin = self.fakebin
        fakebash = fakebin / 'bash'
        # Intercept only the final exec of the original Bash launcher. Its full
        # reviewed source was hash-checked, but must not run on the CI host.
        fakebash.write_text('#!' + self.bash + '\nset -eu\n'
            'test "$1" = "$PWD/START_TCG_UPDATER_ANDROID.sh"\n'
            'python -c \'print("OTHER_PYTHON_CALL_OK")\'\n'
            'python tcg_updater_v135.py &\n'
            'server=$!\necho "EXPECTED:$server"\nwait "$server"\n')
        fakebash.chmod(0o755)
        self.env['PATH'] = str(fakebin) + os.pathsep + self.env['PATH']
        result = self.run_launcher()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn('OTHER_PYTHON_CALL_OK', result.stdout)
        expected = re.search(r'EXPECTED:(\d+)', result.stdout).group(1)
        actual = re.search(r'ACTUAL:(\d+)', result.stdout).group(1)
        self.assertEqual(expected, actual, 'exec must preserve PID tracked by original cleanup')


class ReadbackTests(unittest.TestCase):
    def healthy(self, route):
        if route == '/api/health':
            payload = {'ok': True, 'collection_health': {'runtime_build_sha': SHA,
                'runtime_build_sha_verified': True, 'healthy': True, 'requires_attention': False}}
            return 200, 'application/json', json.dumps(payload).encode()
        marker = {'/tablet-unified': 'TCG 카드·BOX 라이브러리',
                  '/tablet-events-all': '전체 TCG · 행사·콜라보·영화·프로모',
                  '/tablet-features': '<a href="/index.html?target=one">도구</a>'}[route]
        return 200, 'text/html', ('<html>' + marker + ' PRIVATE_IMAGE_NAME_OR_ID </html>').encode()

    def test_revision_and_new_routes_pass_without_claiming_touch_or_collection(self):
        result = device.probe(SHA, git_sha=SHA, reader=self.healthy)
        self.assertTrue(result['ok'])
        self.assertEqual('HTTP_READBACK_OK_TOUCH_UNVERIFIED', result['status'])
        self.assertEqual('NOT_RUN', result['touch_camera_verification'])
        self.assertEqual('NOT_VERIFIED', result['event_collection_cycle'])
        self.assertEqual('NOT_VERIFIED', result['image_metadata_repair_cycle'])
        self.assertNotIn('PRIVATE_IMAGE_NAME_OR_ID', json.dumps(result))

    def test_old_running_process_fails_even_after_working_copy_update(self):
        def old(route):
            status, mime, raw = self.healthy(route)
            if route == '/api/health': raw = raw.replace(SHA.encode(), b'c7486f46997f4034e41d7f18d5a2f5e94c4de4d8')
            return status, mime, raw
        result = device.probe(SHA, git_sha=SHA, reader=old)
        self.assertFalse(result['ok'])
        self.assertFalse(result['checks']['runtime_revision'])

    def test_old_working_copy_fails_even_if_http_revision_is_new(self):
        result = device.probe(SHA, git_sha='0' * 40, reader=self.healthy)
        self.assertFalse(result['ok'])
        self.assertFalse(result['checks']['working_copy_revision'])

    def test_fallback_html_or_wrong_mime_cannot_pass_new_route_checks(self):
        for reply in [(200, 'text/html', b'<html>old home</html>'), (200, 'application/json', b'{}'),
                      (404, 'text/html', b'not found')]:
            with self.subTest(reply=reply):
                result = device.probe(SHA, git_sha=SHA, reader=lambda route: self.healthy(route) if route == '/api/health' else reply)
                self.assertFalse(result['ok'])

    def test_malformed_or_oversized_health_is_a_hold(self):
        for raw in [b'false', b'[]', b'not json', b' ' * 262145]:
            result = device.probe(SHA, git_sha=SHA, reader=lambda route: (200, 'application/json', raw))
            self.assertFalse(result['ok'])

    def test_unverified_runtime_attestation_or_unhealthy_collection_fails(self):
        for field in ('runtime_build_sha_verified', 'healthy'):
            def invalid(route):
                status, mime, raw = self.healthy(route)
                if route == '/api/health':
                    data = json.loads(raw); data['collection_health'][field] = False; raw = json.dumps(data).encode()
                return status, mime, raw
            self.assertFalse(device.probe(SHA, git_sha=SHA, reader=invalid)['ok'])

    def test_expected_sha_must_be_full_not_branch_name(self):
        for value in ('main', SHA[:8], True, None, 'f' * 41):
            with self.assertRaises(ValueError): device.probe(value, git_sha=SHA, reader=self.healthy)

    def test_request_errors_are_redacted_and_unavailable_never_passes(self):
        def offline(route): raise OSError('PRIVATE_PATH_OR_TOKEN')
        result = device.probe(SHA, git_sha=SHA, reader=offline)
        self.assertFalse(result['ok'])
        self.assertNotIn('PRIVATE_PATH_OR_TOKEN', json.dumps(result))

    def test_read_function_refuses_unapproved_route_before_network(self):
        with patch.object(device, 'build_opener') as opener:
            with self.assertRaises(ValueError): device.read('/api/run-auto-update')
            opener.assert_not_called()

    def test_redirect_cannot_escape_local_readback(self):
        with self.assertRaises(ValueError):
            device.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.com')

    def test_cli_outputs_only_summary_and_fails_closed(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), patch.object(device, 'probe', side_effect=OSError('private')):
            code = device.main(['--expected-sha', SHA])
        self.assertEqual(1, code)
        self.assertEqual('HOLD_READBACK_UNAVAILABLE', json.loads(out.getvalue())['status'])
        self.assertNotIn('private', out.getvalue())


if __name__ == '__main__':
    unittest.main()
