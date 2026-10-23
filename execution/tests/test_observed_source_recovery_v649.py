"""Real Git recovery for all seven files reported by the tablet, together."""
import hashlib
import json
from pathlib import Path
import subprocess
import unittest
from unittest import mock

from execution.tests import test_tablet_preserved_update as fixtures

m = fixtures.m
OBSERVED = frozenset('''GRAPHIFY_UPDATE.sh code_map_intelligence.py
integrity_manifest.json market_catalog_expander.js tcg_card_detail_v566.js
tcg_photo_result_v567.js update_market_prices.py'''.split())


class ObservedSourceRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.PreservedUpdateTests(
            'test_mm_data_kept_and_both_source_versions_archived')
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.repo = self.case.repo
        # The incoming manifest is official source, unlike the locally modified
        # and deliberately invalid JSON below. No production verifier is mocked.
        self.case.g('checkout', 'candidate')
        (self.repo / 'integrity_manifest.json').write_text(
            '{"version":2,"files":{},"fixture_official":true}\n')
        self.case.g('add', 'integrity_manifest.json')
        self.case.g('commit', '-m', 'official fixture manifest')
        self.case.target = self.case.g('rev-parse', 'HEAD').strip()
        self.case.g('update-ref', 'refs/remotes/origin/main', self.case.target)
        self.case.g('checkout', 'main')

    def dirty_set(self, layer='both'):
        staged = {name: ('staged device version: ' + name + '\n').encode()
                  for name in OBSERVED}
        current = {name: ('current device version: ' + name + '\n').encode()
                   for name in OBSERVED}
        for name in OBSERVED:
            (self.repo / name).write_bytes(staged[name] if layer != 'worktree' else current[name])
        if layer != 'worktree':
            self.case.g('add', *sorted(OBSERVED))
        if layer == 'both':
            for name in OBSERVED:
                (self.repo / name).write_bytes(current[name])
        return staged, staged if layer == 'staged' else current

    def private_data(self):
        self.case.dirty()
        photos = self.case.root / 'Pictures' / 'TCG_Card_Images' / 'card.webp'
        photos.parent.mkdir(parents=True)
        photos.write_bytes(b'private compressed card image')
        model = self.repo / 'local-model.bin'
        model.write_bytes(b'private last-good model')
        paths = [photos, model, self.repo / 'learning_store.json', self.repo / 'market_prices.json']
        return {path: path.read_bytes() for path in paths}

    def assert_private(self, saved):
        self.assertEqual(saved, {path: path.read_bytes() for path in saved})

    def test_all_seven_mm_versions_archived_and_official_manifest_installed(self):
        private = self.private_data()
        staged, current = self.dirty_set()
        index = self.case.g('write-tree').strip()
        result = self.case.apply()
        self.assertEqual('UPDATED', result['status'], result)
        self.assertTrue(OBSERVED <= set(result['source_paths']))
        self.assertNotIn('integrity_manifest.json', result['runtime_paths'])
        self.assertEqual(index, result['original_index_tree'])
        self.assertEqual(self.case.target, self.case.g('rev-parse', 'HEAD').strip())
        for name in OBSERVED:
            with self.subTest(path=name):
                self.assertEqual(staged[name].decode(), self.case.g('show', result['backup_ref'] + '^2:' + name))
                self.assertEqual(current[name].decode(), self.case.g('show', result['backup_ref'] + ':' + name))
                backup = Path(result['backup_directory']) / 'source-files' / name
                self.assertEqual(current[name], backup.read_bytes())
                self.assertEqual(hashlib.sha256(current[name]).hexdigest(), result['source_before_sha256'][name])
                self.assertEqual(self.case.g('show', self.case.target + ':' + name), (self.repo / name).read_text())
        self.assertTrue(json.loads((self.repo / 'integrity_manifest.json').read_text())['fixture_official'])
        self.assertEqual([], result['runtime_changed_during_operation'])
        self.assert_private(private)
        self.assertEqual([], self.case.g('diff', '--cached', '--name-only').splitlines())

    def test_each_single_layer_update_preserves_all_seven(self):
        for layer in ('staged', 'worktree'):
            with self.subTest(layer=layer):
                _, current = self.dirty_set(layer)
                result = self.case.apply()
                self.assertEqual('UPDATED', result['status'], result)
                for name, raw in current.items():
                    self.assertEqual(raw, (Path(result['backup_directory']) / 'source-files' / name).read_bytes())

    def test_preflight_failure_leaves_every_source_index_and_private_byte(self):
        private = self.private_data()
        _, current = self.dirty_set()
        index = self.case.g('write-tree').strip()
        with mock.patch.object(m, 'verify_candidate', side_effect=m.Hold('PRECHECK_FAIL')):
            result = self.case.apply()
        self.assertEqual('HOLD', result['status'])
        self.assertEqual(index, self.case.g('write-tree').strip())
        self.assertEqual(current, {name: (self.repo / name).read_bytes() for name in OBSERVED})
        self.assertEqual(self.case.base, self.case.g('rev-parse', 'HEAD').strip())
        self.assert_private(private)

    def test_copy_corruption_stops_before_cleaning_any_source(self):
        _, current = self.dirty_set()
        index = self.case.g('write-tree').strip()
        copy = m.shutil.copy2
        def corrupt(source, destination, *args, **kwargs):
            result = copy(source, destination, *args, **kwargs)
            if Path(destination).name == 'integrity_manifest.json':
                Path(destination).write_bytes(b'corrupted backup')
            return result
        with mock.patch.object(m.shutil, 'copy2', side_effect=corrupt):
            result = self.case.apply()
        self.assertEqual('HOLD', result['status'])
        self.assertEqual('SOURCE_BACKUP_VERIFICATION_FAILED', result['reason'])
        self.assertEqual(index, self.case.g('write-tree').strip())
        self.assertEqual(current, {name: (self.repo / name).read_bytes() for name in OBSERVED})

    def test_merge_failure_restores_all_original_source_and_index(self):
        private = self.private_data()
        _, current = self.dirty_set()
        index = self.case.g('write-tree').strip()
        original = m.git
        def fail(repo, *args, **kwargs):
            if args and args[0] == 'merge':
                raise subprocess.CalledProcessError(1, args)
            return original(repo, *args, **kwargs)
        with mock.patch.object(m, 'git', side_effect=fail):
            result = self.case.apply()
        self.assertEqual('HOLD', result['status'])
        self.assertEqual('ORIGINAL_INDEX_AND_SOURCE_RESTORED', result['rollback'])
        self.assertEqual(index, self.case.g('write-tree').strip())
        self.assertEqual(current, {name: (self.repo / name).read_bytes() for name in OBSERVED})
        self.assertEqual(self.case.base, self.case.g('rev-parse', 'HEAD').strip())
        self.assert_private(private)

    def test_other_paths_still_block_before_mutation(self):
        _, current = self.dirty_set()
        (self.repo / 'VERIFY_TABLET_FINAL.sh').write_text('local verifier edit\n')
        index = self.case.g('write-tree').strip()
        with self.assertRaisesRegex(m.Hold, '^UNKNOWN_CHANGED_PATH: VERIFY_TABLET_FINAL.sh$'):
            self.case.apply()
        self.assertEqual(index, self.case.g('write-tree').strip())
        self.assertEqual(current, {name: (self.repo / name).read_bytes() for name in OBSERVED})
        self.assertFalse(self.case.backups.exists())

    def test_manifest_symlink_never_writes_private_target(self):
        private = self.case.root / 'private.json'
        private.write_bytes(b'private outside data')
        path = self.repo / 'integrity_manifest.json'
        path.unlink()
        path.symlink_to(private)
        with self.assertRaises(m.Hold):
            self.case.apply()
        self.assertEqual(b'private outside data', private.read_bytes())
        self.assertFalse(self.case.backups.exists())
