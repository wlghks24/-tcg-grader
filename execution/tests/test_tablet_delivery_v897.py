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
import sys
import time
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
           'tablet_event_coverage_v896','tablet_device_readback_v897','apply_tablet_candidate_v897',
           'tablet_live_view_v898','tablet_provider_json_v900',
           'tablet_collection_receipt_v901','tablet_display_fast_v901','tablet_menu_shell_v903')


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
        for asset in ('tablet_menu_shell_v903.js',):
            raw = (ROOT/'execution'/asset).read_bytes()
            (self.execution/asset).write_bytes(raw)
            self.files['execution/'+asset] = {'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
        for name in MODULES:
            raw = b'# Offline stub: never import the real runtime\n'
            if name == 'tablet_unified_runtime_v889':
                raw += b'''import os,time
from pathlib import Path
for unused in range(100):
    if Path('.fixture-pair-ready').exists() and Path('.fixture-raw-ready').exists():break
    time.sleep(.01)
assert Path('.fixture-pair-ready').exists() and Path('.fixture-raw-ready').exists()
owner=Path('.tcg_android_start.lock/pid').read_text().strip()
assert int(owner)==os.getppid()
print('ACTUAL:'+str(os.getpid())+' OWNER:'+owner,flush=True)
Path('.fixture-server-ready').write_text(str(os.getpid()))
if os.environ.get('TCG_FIXTURE_WAIT')=='1':
    while True:time.sleep(.05)
'''
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
        # Exercise the immutable original launcher, while every production Python
        # script/semantic import, process scan, package manager and watcher is a
        # fixture. No TCG runtime/server/collection runs on the CI machine.
        (self.root / 'index.html').write_text('manual_dual_photo_bridge.js')
        for name in ('tablet_runtime_manifest.py', 'verified_slab_raw_learning_v155.py'):
            (self.root / name).write_text('# offline fixture\n')
        fakepython = self.fakebin / 'python'
        fakepython.write_text('#!' + sys.executable + '\n' + '''import os,sys
from pathlib import Path
args=sys.argv[1:]
if args==['-']:
    sys.stdin.read();raise SystemExit(0)
name=args[0] if args else ''
if name in ('tablet_runtime_manifest.py','legacy_ocr_registry_cleanup_v149.py','storage_optimizer.py','release_tcg_port.py'):
    raise SystemExit(0)
if name in ('graded_photo_manual_pair_queue.py','verified_slab_raw_learning_v155.py'):
    print('STUB_WATCH:'+','.join(args),flush=True)
    Path('.fixture-pair-ready' if name.startswith('graded_') else '.fixture-raw-ready').write_text('ready')
    raise SystemExit(0)
if name=='tcg_updater_v135.py':
    print('CLASSIC_WRONG_ENTRY',flush=True);raise SystemExit(0)
''' + 'os.execv(' + repr(sys.executable) + ', [' + repr(sys.executable) + ']+args)\n')
        fakepython.chmod(0o755)
        for name in ('pkill', 'sleep', 'pkg'):
            command = self.fakebin / name
            command.write_text('#!' + self.bash + '\nexit ' + ('99' if name == 'pkg' else '0') + '\n')
            command.chmod(0o755)
        for name in ('termux-wake-lock', 'termux-wake-unlock'):
            command = self.fakebin / name
            command.write_text('#!' + self.bash + '\necho ' + name + ' >> .fixture-wake-log\n')
            command.chmod(0o755)

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

    def test_original_launcher_dispatch_pid_watchers_and_cleanup_without_function_import(self):
        result = subprocess.run([self.bash, '-p', str(self.launcher)], cwd=self.root,
                                env=self.env, text=True, capture_output=True, timeout=10)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn('[TCG_UNIFIED_V902]', result.stderr)
        self.assertRegex(result.stdout, r'ACTUAL:\d+ OWNER:\d+')
        self.assertNotIn('CLASSIC_WRONG_ENTRY', result.stdout)
        self.assertFalse((self.root / '.tcg_android_start.lock').exists())
        self.assertIn('--watch,--interval,60', (self.root / 'TCG_MANUAL_PAIR_QUEUE.log').read_text())
        self.assertIn('--watch,--interval,30', (self.root / 'TCG_VERIFIED_SLAB_RAW_LEARNING.log').read_text())
        self.assertEqual(['termux-wake-lock', 'termux-wake-unlock'], (self.root / '.fixture-wake-log').read_text().splitlines())
        self.assertEqual('f885535c224584ce2fb1a4bb16978e707b5661d002b9f888a524f69a34403667', hashlib.sha256((self.root / 'START_TCG_UPDATER_ANDROID.sh').read_bytes()).hexdigest())

    def test_old_export_boundary_can_silently_choose_classic_with_function_import_disabled(self):
        script = 'python(){ echo UNIFIED_EXPECTED; }; export -f python; exec "$1" -p -c "python tcg_updater_v135.py"'
        result = subprocess.run([self.bash, '-c', script, 'fixture', self.bash], cwd=self.root,
                                env=self.env, text=True, capture_output=True, timeout=5)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn('CLASSIC_WRONG_ENTRY', result.stdout)
        self.assertNotIn('UNIFIED_EXPECTED', result.stdout)

    def test_real_sourced_wrapper_owner_can_be_stopped_with_original_child_cleanup(self):
        from execution import apply_tablet_candidate_v897 as delivery
        before = (self.root / 'integrity_manifest.json').read_bytes()
        self.env['TCG_FIXTURE_WAIT'] = '1'
        process = subprocess.Popen([self.bash, str(self.launcher)], cwd=self.root,
                                   env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        def cleanup():
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=5)
        self.addCleanup(cleanup)
        marker = self.root / '.fixture-server-ready'
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline and process.poll() is None:
            time.sleep(.01)
        self.assertTrue(marker.exists(), 'stub server did not reach reviewed dispatch')
        server = int(marker.read_text())
        owner = int((self.root / '.tcg_android_start.lock/pid').read_text())
        self.assertEqual(process.pid, owner)
        if not (Path('/proc') / str(owner) / 'cmdline').exists():
            self.skipTest('native /proc process readback is unavailable in this executor')
        with patch.object(delivery, 'port_open', return_value=False):
            delivery.stop_launcher(self.root)
        process.wait(timeout=5)
        self.assertFalse((self.root / '.tcg_android_start.lock').exists())
        with self.assertRaises(ProcessLookupError): os.kill(server, 0)
        self.assertEqual(before, (self.root / 'integrity_manifest.json').read_bytes())
        self.assertEqual(['termux-wake-lock', 'termux-wake-unlock'], (self.root / '.fixture-wake-log').read_text().splitlines())


class ReadbackTests(unittest.TestCase):
    def test_adapter_health_is_redacted_and_distinct_from_checkout_identity(self):
        def reader(route):
            status, mime, raw = self.healthy(route)
            if route == '/api/health':
                payload = json.loads(raw)
                payload['unified_runtime'] = {'schema_version': 902, 'adapter_active': True,
                    'collector_hook_active': False, 'provider_json_hook_active': 'PRIVATE',
                    'startup_revision': {'private': 'PRIVATE'}, 'other': 'PRIVATE'}
                raw = json.dumps(payload).encode()
            return status, mime, raw
        result = device.probe(SHA, git_sha=SHA, reader=reader)
        info = result['route_details']['health']['unified_runtime']
        self.assertTrue(info['adapter_active'])
        self.assertFalse(info['collector_hook_active'])
        self.assertIsNone(info['provider_json_hook_active'])
        self.assertIsNone(info['startup_revision'])
        self.assertFalse(result['ok'])
        self.assertFalse(result['checks']['unified_runtime_hooks'])
        self.assertNotIn('PRIVATE', json.dumps(result))
        legacy = device.probe(SHA, git_sha=SHA, reader=self.healthy)
        self.assertEqual('NOT_PRESENT_OR_UNRECOGNIZED', legacy['route_details']['health']['unified_runtime']['state'])
        def active(route):
            status, mime, raw = self.healthy(route)
            if route == '/api/health':
                payload = json.loads(raw)
                payload['unified_runtime'] = {'schema_version': 902, 'adapter_active': True,
                    'collector_hook_active': True, 'provider_json_hook_active': True, 'startup_revision': SHA}
                raw = json.dumps(payload).encode()
            return status, mime, raw
        verified = device.probe(SHA, git_sha=SHA, reader=active)
        self.assertTrue(verified['ok'])
        self.assertTrue(verified['checks']['unified_runtime_hooks'])

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

    def test_malformed_runtime_identity_never_echoes_response_objects_or_names(self):
        for value in ({'private': 'PRIVATE_IMAGE_NAME'}, 'PRIVATE_IMAGE_NAME'):
            def invalid(route):
                status, mime, raw = self.healthy(route)
                if route == '/api/health':
                    payload = json.loads(raw); payload['collection_health']['runtime_build_sha'] = value
                    raw = json.dumps(payload).encode()
                return status, mime, raw
            result = device.probe(SHA, git_sha=SHA, reader=invalid)
            self.assertFalse(result['ok'])
            self.assertIsNone(result['runtime_build_sha'])
            self.assertNotIn('PRIVATE_IMAGE_NAME', json.dumps(result))

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
