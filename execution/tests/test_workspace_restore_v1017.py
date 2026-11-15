"""Pure source/handler checks: no live HTTP, tablet runtime or user data."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from execution import tablet_unified_runtime_v889 as runtime
from execution import tablet_workspace_verify_v1017 as verify
from execution.tests.test_tablet_menu_shell_v903 import MenuTests

ROOT = Path(__file__).resolve().parents[2]
SHA = 'a' * 40


class WorkspaceRestoreV1017Tests(unittest.TestCase):
    def test_exact_source_history_and_preserved_latest_security_and_fx(self):
        proof = json.loads((ROOT / '.github/tablet-autonomy/workspace_restore_v1017.json').read_text())
        base, candidate, original = (proof[k] for k in
            ('baseline_commit', 'candidate_commit', 'original_workspace_commit'))
        self.assertEqual('ca85f2fd2b64f0f9465ddc0190badc92ac33e1fe', base)
        self.assertEqual('ba5f53c49c20378923b7d48af1380f31930af6c3', candidate)
        self.assertEqual('cd7b40afcd9bdfadb0987a70847eee1c3a9f08f8', original)
        def git(*args):
            return subprocess.check_output(['git', *args], cwd=ROOT, timeout=15)
        git('merge-base', '--is-ancestor', base, candidate)
        git('merge-base', '--is-ancestor', candidate, 'HEAD')
        self.assertEqual(sorted(proof['reviewed_files']), git('diff', '--name-only', base, candidate).decode().splitlines())
        for name, pin in proof['reviewed_files'].items():
            raw = git('show', candidate + ':' + name)
            self.assertEqual(pin['sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(pin['bytes'], len(raw))
            self.assertEqual(raw, (ROOT / name).read_bytes())
            self.assertEqual(raw, git('show', 'HEAD:' + name))
            if pin['original_sha256'] is not None:
                self.assertEqual(pin['original_sha256'], hashlib.sha256(git('show', original + ':' + name)).hexdigest())
        for name in ('main', 'multi_market_price_collector.py', 'wyyyes_market_source.py',
                     'execution/tablet_inplace_patch.py', 'execution/tablet_runtime_handoff.py',
                     'index.html', 'update_promo_events.py'):
            self.assertEqual(git('show', base + ':' + name), (ROOT / name).read_bytes())
        for key in ('physical_tablet_verified', 'model_training_authorized', 'runtime_data_modified'):
            self.assertIs(False, proof[key])

    def test_source_check_rejects_missing_changed_and_symlink_assets(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'execution').mkdir()
            pins = {}
            for name in verify.REQUIRED_SOURCE:
                raw = (ROOT / name).read_bytes()
                (root / name).write_bytes(raw)
                pins[name] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
            (root / 'integrity_manifest.json').write_text(json.dumps({'files': pins}))
            self.assertEqual('WORKSPACE_SOURCE_VERIFIED', verify.check_source(root)['status'])
            target = root / 'execution/tablet_menu_shell_v903.js'
            saved = target.read_bytes()
            target.write_bytes(saved + b'changed')
            with self.assertRaises(ValueError):
                verify.check_source(root)
            target.unlink()
            with self.assertRaises(OSError):
                verify.check_source(root)
            other = root / 'saved.js'
            other.write_bytes(saved)
            target.symlink_to(other)
            with self.assertRaises(ValueError):
                verify.check_source(root)

    def fixture(self):
        raw = (ROOT / 'execution/tablet_menu_shell_v903.js').read_text()
        ui = {'schema': verify.SCHEMA}
        for name, key in [('tablet_menu_shell_v903.py', 'shell_sha256'),
                          ('tablet_menu_shell_v903.js', 'script_sha256')]:
            ui[key] = hashlib.sha256((ROOT / 'execution' / name).read_bytes()).hexdigest()
        report = {'health': {'ok': True, 'payload': {'workspace_ui': ui}},
                  'runtime_contract': {'ok': True, 'running_build_sha': SHA, 'disk_git_sha': SHA},
                  'collection_health_ready': False}
        page = ('<html><body data-tcg903-shell="true">' + ''.join(
            '<div id="' + name + '"></div>' for name in
            ['tcg903-drawer', 'tcg903-grid', 'tcg903-game', 'tcg903-countries', 'tcg903-events'])
            + '<script>' + raw + '</script></body></html>')
        return report, page

    def assess(self, report, page):
        with patch('tablet_runtime_probe.git_state', return_value={'sha_full': SHA}):
            return verify.assess(ROOT, report, page)

    def test_workspace_matches_without_claiming_collection_or_device_verified(self):
        result = self.assess(*self.fixture())
        self.assertEqual('WORKSPACE_HTTP_VERIFIED', result['status'])
        self.assertFalse(result['physical_tablet_verified'])
        self.assertFalse(result['collection_ready'])

    def test_same_sha_basic_hub_is_rejected(self):
        report, _ = self.fixture()
        result = self.assess(report, '<html><body>TCG CARD HUB</body></html>')
        self.assertIn('WORKSPACE_NAVIGATION_MISSING', result['errors'])
        self.assertEqual('HOLD', result['status'])

    def test_missing_or_malformed_runtime_attestation_fails_closed(self):
        for value in (None, {}, [], ['bad'], 'bad', True):
            report, page = self.fixture()
            report['health']['payload']['workspace_ui'] = value
            with self.subTest(value=value):
                self.assertEqual('HOLD', self.assess(report, page)['status'])

    def test_stale_loaded_assets_and_changed_served_script_fail(self):
        report, page = self.fixture()
        report['health']['payload']['workspace_ui']['script_sha256'] = 'b' * 64
        self.assertIn('WORKSPACE_LOADED_ASSET_MISMATCH', self.assess(report, page)['errors'])
        report, page = self.fixture()
        self.assertIn('WORKSPACE_SERVED_SCRIPT_MISMATCH', self.assess(report, page.replace('</script>', '\n</script>'))['errors'])

    def test_wrong_server_build_and_invalid_documents_fail(self):
        report, page = self.fixture()
        report['runtime_contract']['running_build_sha'] = 'b' * 40
        self.assertIn('RUNNING_BUILD_MISMATCH', self.assess(report, page)['errors'])
        report, _ = self.fixture()
        for page in (None, 'x' * (verify.MAX_PAGE_BYTES + 1)):
            self.assertIn('WORKSPACE_DOCUMENT_INVALID', self.assess(report, page)['errors'])

    def test_actual_handler_attests_both_health_routes(self):
        class Base:
            def _require_request_host(self):
                return True
            def json(self, payload, status=200):
                return payload
            def do_GET(self):
                return self.json({'ok': True})
        report, _ = self.fixture()
        info = report['health']['payload']['workspace_ui']
        with patch.object(runtime, '_WORKSPACE', info):
            handler = runtime.make_handler(Base)()
            for route in ('/api/health', '/api/v135-health'):
                handler.path = route
                self.assertEqual(info, handler.do_GET()['workspace_ui'])

    def test_all_standard_start_paths_use_the_restored_server(self):
        start = (ROOT / 'START_TCG_UPDATER_ANDROID.sh').read_text()
        self.assertIn('python -m execution.tablet_unified_runtime_v889 &', start)
        self.assertIn('SERVER_PID=$!', start)
        self.assertIn('kill -TERM "$SERVER_PID"', start)
        self.assertIn("['bash','START_TCG_UPDATER_ANDROID.sh']", (ROOT / 'execution/tablet_runtime_handoff.py').read_text())
        self.assertIn('exec bash START_TCG_UPDATER_ANDROID.sh', (ROOT / 'ANDROID_UPDATE_AND_START.sh').read_text())


if __name__ == '__main__':
    unittest.main()
