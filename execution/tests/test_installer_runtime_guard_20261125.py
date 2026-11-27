"""Runtime-change guard regression with disposable Git and fixture verifiers."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from execution import tablet_preserved_update as m


class InstallerRuntimeGuardTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.repo = Path(temp.name) / 'repo'
        self.repo.mkdir()
        self.backup = Path(temp.name) / 'backup'
        self.lock = self.repo / '.tcg_android_update.lock'
        self.data = self.repo / 'learning_store.json'
        self.g('init', '-q', '-b', 'main')
        self.g('config', 'user.name', 'Fixture')
        self.g('config', 'user.email', 'fixture@example.invalid')
        self.g('remote', 'add', 'origin', m.OFFICIAL)
        self.data.write_text('{"base":true}\n')
        (self.repo / 'tcg_updater.py').write_text('base source\n')
        (self.repo / 'VERIFY_TABLET_FINAL.sh').write_text('#!/bin/bash\nexit 0\n')
        (self.repo / 'tablet_runtime_manifest.py').write_text('print("fixture")\n')
        self.before = self.commit()
        self.g('switch', '-qc', 'candidate')
        (self.repo / 'tcg_updater.py').write_text('candidate source\n')
        self.target = self.commit()
        self.g('update-ref', 'refs/remotes/origin/main', self.target)
        self.g('switch', '-q', 'main')
        self.photo = self.repo / 'private.jpg'
        self.photo.write_bytes(b'private fixture photo')

    def g(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], stderr=subprocess.PIPE, text=True).strip()

    def commit(self):
        self.g('add', '-A')
        self.g('commit', '-qm', 'fixture')
        return self.g('rev-parse', 'HEAD')

    def verifier(self, script):
        self.g('switch', '-q', 'candidate')
        (self.repo / 'tablet_runtime_manifest.py').write_text('from pathlib import Path\n' + script + '\n')
        self.g('add', 'tablet_runtime_manifest.py')
        self.g('commit', '-qm', 'fixture postcheck')
        self.target = self.g('rev-parse', 'HEAD')
        self.g('update-ref', 'refs/remotes/origin/main', self.target)
        self.g('switch', '-q', 'main')

    def apply(self):
        result = m.repair(self.repo, self.backup, apply=True)
        self.assertFalse(self.lock.exists())
        self.assertEqual(b'private fixture photo', self.photo.read_bytes())
        return result

    def hold_after_ff(self, result):
        self.assertEqual('HOLD', result['status'])
        self.assertEqual(self.target, result['actual_head'])
        self.assertTrue(result['head_advanced'])
        self.assertTrue(result['post_update_verification_required'])
        self.assertEqual(self.target, self.g('rev-parse', 'HEAD'))

    def test_clean_runtime_mutation_holds(self):
        self.verifier('Path("learning_store.json").write_text("{}")')
        result = self.apply()
        self.hold_after_ff(result)
        self.assertEqual('RUNTIME_CHANGED_DURING_INSTALL', result['reason'])
        self.assertEqual(['learning_store.json'], result['runtime_changed_during_operation'])
        self.assertEqual('{}', self.data.read_text())

    def test_dirty_runtime_mutation_holds(self):
        self.verifier('Path("learning_store.json").write_text("{}")')
        self.data.write_text('{"live":true}')
        result = self.apply()
        self.hold_after_ff(result)
        self.assertIn('learning_store.json', result['runtime_changed_during_operation'])

    def test_absent_runtime_created_holds(self):
        self.verifier('Path("market_prices.json").write_text("{}")')
        result = self.apply()
        self.hold_after_ff(result)
        self.assertIsNone(result['runtime_before_sha256']['market_prices.json'])
        self.assertEqual(['market_prices.json'], result['runtime_changed_during_operation'])

    def test_preflight_same_path_change_holds(self):
        self.data.write_text('{"live":true}')
        def change(repo, target, backup):
            self.data.write_text('{"concurrent":true}')
        with patch.object(m, 'verify_candidate', side_effect=change):
            result = self.apply()
        self.assertEqual('RUNTIME_CHANGED_DURING_PREFLIGHT', result['reason'])
        self.assertEqual(self.before, self.g('rev-parse', 'HEAD'))
        self.assertFalse(result['head_advanced'])
        self.assertEqual('{"concurrent":true}', self.data.read_text())

    def test_destination_capacity_holds_before_mutation(self):
        with patch.object(m.shutil, 'disk_usage', side_effect=lambda p: SimpleNamespace(free=0 if p == self.backup else 10**12)):
            with self.assertRaisesRegex(m.Hold, 'INSUFFICIENT_BACKUP_DESTINATION_SPACE'):
                self.apply()
        self.assertEqual(self.before, self.g('rev-parse', 'HEAD'))
        self.assertFalse(self.lock.exists())

    def test_postcheck_error_reports_actual_head(self):
        self.verifier('raise SystemExit(9)')
        self.hold_after_ff(self.apply())

    def test_receipt_failure_reports_actual_head(self):
        original = m.receipt
        def fail(path, value):
            if value['status'] in ('UPDATED', 'HOLD'):
                raise OSError('fixture volume unavailable')
            original(path, value)
        with patch.object(m, 'receipt', side_effect=fail):
            result = self.apply()
        self.hold_after_ff(result)
        self.assertTrue(result['receipt_write_failed'])

    def test_normal_update_keeps_data_and_photo(self):
        self.data.write_text('{"live":true}')
        result = self.apply()
        self.assertEqual('UPDATED', result['status'])
        self.assertEqual([], result['runtime_changed_during_operation'])
        self.assertEqual('{"live":true}', self.data.read_text())
        self.assertEqual(result, json.loads((Path(result['backup_directory']) / 'receipt.json').read_text()))


if __name__ == '__main__':
    unittest.main()
