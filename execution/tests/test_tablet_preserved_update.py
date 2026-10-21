"""Real temporary Git repositories; no network, production data or training."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location('preserved_update', Path(__file__).resolve().parents[1] / 'tablet_preserved_update.py')
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class PreservedUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'app'
        self.repo.mkdir()
        self.backups = self.root / 'backups'
        self.g('init', '-b', 'baseline')
        self.g('config', 'user.name', 'Fixture')
        self.g('config', 'user.email', 'fixture@localhost')
        self.g('remote', 'add', 'origin', m.OFFICIAL)
        for name, content in {'tcg_updater.py':'baseline code\n', 'index.html':'baseline UI\n',
                              'learning_store.json':'{"version":0}\n',
                              'market_prices.json':'{"price":1}\n',
                              'VERIFY_TABLET_FINAL.sh':'#!/bin/bash\nexit 0\n',
                              'tablet_runtime_manifest.py':'print("fixture manifest checked")\n'}.items():
            (self.repo / name).write_text(content)
        for name in m.SOURCE_PATHS | m.RUNTIME_PATHS:
            path = self.repo / name
            if not path.exists():
                path.write_text('{"baseline":true}\n' if name in m.RUNTIME_PATHS else 'baseline source\n')
        self.g('add', '.')
        self.g('commit', '-m', 'base')
        self.base = self.g('rev-parse', 'HEAD').strip()
        self.g('checkout', '-b', 'candidate')
        (self.repo / 'tcg_updater.py').write_text('verified new code\n')
        self.g('add', '.')
        self.g('commit', '-m', 'verified candidate')
        self.target = self.g('rev-parse', 'HEAD').strip()
        self.g('update-ref', 'refs/remotes/origin/main', self.target)
        self.g('checkout', '-b', 'main', self.base)

    def g(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], stderr=subprocess.DEVNULL).decode()

    def dirty(self):
        (self.repo / 'tcg_updater.py').write_text('staged local code\n')
        (self.repo / 'learning_store.json').write_text('{"version":1}\n')
        self.g('add', 'tcg_updater.py', 'learning_store.json')
        (self.repo / 'tcg_updater.py').write_text('unstaged local code\n')
        (self.repo / 'learning_store.json').write_text('{"version":2,"live":true}\n')
        return self.g('write-tree').strip()

    def apply(self):
        return m.repair(self.repo, self.backups, apply=True)

    def test_mm_data_kept_and_both_source_versions_archived(self):
        tree = self.dirty()
        data = (self.repo / 'learning_store.json').read_bytes()
        out = self.apply()
        self.assertEqual(out['status'], 'UPDATED', out)
        self.assertEqual(self.g('rev-parse', 'HEAD').strip(), self.target)
        self.assertEqual((self.repo / 'learning_store.json').read_bytes(), data)
        self.assertEqual((self.repo / 'tcg_updater.py').read_text(), 'verified new code\n')
        self.assertEqual(self.g('write-tree').strip(), self.g('rev-parse', 'HEAD^{tree}').strip())
        ref = out['backup_ref']
        self.assertEqual(self.g('show', ref + '^2:tcg_updater.py'), 'staged local code\n')
        self.assertEqual(self.g('show', ref + ':tcg_updater.py'), 'unstaged local code\n')
        self.assertEqual(self.g('rev-parse', ref + '^2^{tree}').strip(), tree)
        self.assertEqual(self.g('show', ref + '^2:learning_store.json'), '{"version":1}\n')
        self.assertEqual(out['runtime_changed_during_operation'], [])
        self.assertFalse((self.repo / '.tcg_android_update.lock').exists())

    def test_data_only_staging_is_unstaged_without_rewriting_data(self):
        (self.repo / 'learning_store.json').write_text('{"version":8}\n')
        self.g('add', 'learning_store.json')
        out = self.apply()
        self.assertEqual(out['status'], 'UPDATED', out)
        self.assertEqual((self.repo / 'learning_store.json').read_text(), '{"version":8}\n')
        self.assertIn('learning_store.json', self.g('diff', '--name-only'))

    def test_plan_does_not_clean_index_or_create_backups(self):
        tree = self.dirty()
        out = m.repair(self.repo, self.backups)
        self.assertEqual(out['status'], 'PLAN_ONLY')
        self.assertEqual(self.g('write-tree').strip(), tree)
        self.assertFalse(self.backups.exists())

    def test_unknown_source_holds_before_mutation(self):
        self.dirty()
        (self.repo / 'VERIFY_TABLET_FINAL.sh').write_text('changed trusted verifier\n')
        with self.assertRaisesRegex(m.Hold, 'UNKNOWN_CHANGED_PATH'):
            self.apply()
        self.assertEqual(self.g('rev-parse', 'HEAD').strip(), self.base)

    def test_remote_runtime_change_is_not_silently_applied(self):
        self.g('checkout', 'candidate')
        (self.repo / 'market_prices.json').write_text('{"price":999}\n')
        self.g('add', '.')
        self.g('commit', '-m', 'data/schema change')
        self.g('update-ref', 'refs/remotes/origin/main', self.g('rev-parse', 'HEAD').strip())
        self.g('checkout', 'main')
        tree = self.dirty()
        with self.assertRaisesRegex(m.Hold, 'REMOTE_RUNTIME_CHANGE'):
            self.apply()
        self.assertEqual(self.g('write-tree').strip(), tree)

    def test_preflight_failure_keeps_index_and_files(self):
        tree = self.dirty()
        with mock.patch.object(m, 'verify_candidate', side_effect=m.Hold('PRECHECK_FAIL')):
            out = self.apply()
        self.assertEqual(out['status'], 'HOLD')
        self.assertEqual(self.g('write-tree').strip(), tree)
        self.assertEqual((self.repo / 'tcg_updater.py').read_text(), 'unstaged local code\n')

    def test_merge_failure_restores_exact_original_index_and_source(self):
        self.g('checkout', 'candidate')
        (self.repo / 'new-file.txt').write_text('official new file')
        self.g('add', '.')
        self.g('commit', '-m', 'new tracked file')
        self.g('update-ref', 'refs/remotes/origin/main', self.g('rev-parse', 'HEAD').strip())
        self.g('checkout', 'main')
        (self.repo / 'new-file.txt').write_text('device untracked content')
        tree = self.dirty()
        out = self.apply()
        self.assertEqual(out['status'], 'HOLD', out)
        self.assertEqual(out['rollback'], 'ORIGINAL_INDEX_AND_SOURCE_RESTORED')
        self.assertEqual(self.g('rev-parse', 'HEAD').strip(), self.base)
        self.assertEqual(self.g('write-tree').strip(), tree)
        self.assertEqual((self.repo / 'tcg_updater.py').read_text(), 'unstaged local code\n')
        self.assertEqual((self.repo / 'learning_store.json').read_text(), '{"version":2,"live":true}\n')
        self.assertEqual((self.repo / 'new-file.txt').read_text(), 'device untracked content')

    def test_existing_lock_is_not_removed(self):
        self.dirty()
        lock = self.repo / '.tcg_android_update.lock'
        lock.mkdir()
        (lock / 'pid').write_text('12345')
        with self.assertRaisesRegex(m.Hold, 'UPDATE_LOCK_BUSY'):
            self.apply()
        self.assertEqual((lock / 'pid').read_text(), '12345')

    def test_archive_failure_never_cleans_source(self):
        tree = self.dirty()
        actual = m.git
        def fail(repo, *args, **kwargs):
            if 'stash' in args:
                raise m.Hold('BACKUP_FAILURE')
            return actual(repo, *args, **kwargs)
        with mock.patch.object(m, 'git', side_effect=fail):
            out = self.apply()
        self.assertEqual(out['status'], 'HOLD')
        self.assertEqual(self.g('write-tree').strip(), tree)
        self.assertEqual((self.repo / 'tcg_updater.py').read_text(), 'unstaged local code\n')

    def test_symlink_modified_source_is_rejected(self):
        source = self.repo / 'tcg_updater.py'
        source.unlink()
        outside = self.root / 'outside.py'
        outside.write_text('outside')
        source.symlink_to(outside)
        with self.assertRaises(m.Hold):
            self.apply()
        self.assertEqual(outside.read_text(), 'outside')

    def test_backup_inside_checkout_is_rejected(self):
        self.dirty()
        with self.assertRaisesRegex(m.Hold, 'BACKUP_MUST_BE_OUTSIDE'):
            m.repair(self.repo, self.repo / 'backup', apply=True)

    def test_concurrent_runtime_activity_is_preserved_and_reported(self):
        self.dirty()
        actual = m.git
        def concurrent(repo, *args, **kwargs):
            value = actual(repo, *args, **kwargs)
            if args[:2] == ('merge', '--ff-only'):
                (repo / 'learning_store.json').write_text('{"new_normal_collection":true}\n')
            return value
        with mock.patch.object(m, 'git', side_effect=concurrent):
            out = self.apply()
        self.assertEqual(out['status'], 'UPDATED', out)
        self.assertEqual(out['runtime_changed_during_operation'], ['learning_store.json'])
        self.assertEqual((self.repo / 'learning_store.json').read_text(), '{"new_normal_collection":true}\n')

    def test_source_deleted_or_index_renamed_is_rejected(self):
        self.g('rm', 'tcg_updater.py')
        with self.assertRaises(m.Hold):
            self.apply()

    def test_origin_substitution_is_rejected(self):
        self.g('remote', 'set-url', 'origin', 'https://example.invalid/other/repo')
        with self.assertRaisesRegex(m.Hold, 'OFFICIAL_ORIGIN_REQUIRED'):
            self.apply()



    def test_insufficient_space_holds_before_any_source_mutation(self):
        self.dirty()
        usage = type('Usage', (), {'free':0})()
        with mock.patch.object(m.shutil, 'disk_usage', return_value=usage):
            with self.assertRaisesRegex(m.Hold, 'INSUFFICIENT_FREE_SPACE'):
                self.apply()
        self.assertEqual((self.repo / 'tcg_updater.py').read_text(), 'unstaged local code\n')

    def test_installed_manifest_failure_retains_backup_and_blocks_start(self):
        self.g('checkout', 'candidate')
        (self.repo / 'tablet_runtime_manifest.py').write_text('raise SystemExit(3)\n')
        self.g('add', '.')
        self.g('commit', '-m', 'simulate installed verification failure')
        self.g('update-ref', 'refs/remotes/origin/main', self.g('rev-parse', 'HEAD').strip())
        self.g('checkout', 'main')
        self.dirty()
        out = self.apply()
        self.assertEqual(out['status'], 'HOLD', out)
        self.assertTrue(out.get('backup_ref'))
        self.assertEqual((self.repo / 'learning_store.json').read_text(), '{"version":2,"live":true}\n')



    def test_observed_device_pattern_keeps_all_runtime_bytes(self):
        runtime_names = ['adaptive_collection_stats.json', 'auto_repair_memory.json', 'auto_update_issues.json', 'auto_update_report.json', 'card_identity_learning.json', 'ebay_grader_candidates.json', 'exchange_rates.json', 'graded_photo_candidates.json', 'graded_photo_reference_learning.json', 'grading_company_updates.json', 'learning_store.json', 'library_verified_slab_references.json', 'link_health_report.json', 'market_prices.json', 'market_watch.json', 'promo_events.json', 'purchase_signals.json', 'purchase_sources.json', 'release_parser_learning.json', 'releases.json', 'social_event_candidates.json', 'social_source_registry.json', 'social_stock_signals.json', 'source_collection_stats.json', 'supplementary_candidates.json', 'tcg_game_registry.json', 'tcg_live_data.json', 'verified_certifications.json', 'vision_self_learning_report.json', 'web_discovery_candidates.json']
        for name in m.SOURCE_PATHS:
            (self.repo / name).write_text('device source changes\n')
        for name in runtime_names:
            (self.repo / name).write_text('{"staged_device_state":true}\n')
        self.g('add', *sorted(m.SOURCE_PATHS), *runtime_names)
        for name in runtime_names:
            (self.repo / name).write_text('{"live_device_state":true}\n')
        saved_index = self.g('write-tree').strip()
        before = {name:(self.repo / name).read_bytes() for name in runtime_names}
        out = self.apply()
        self.assertEqual(out['status'], 'UPDATED', out)
        self.assertEqual(len(out['source_paths']), 16)
        self.assertEqual(len(out['runtime_paths']), len(runtime_names))
        self.assertEqual(out['original_index_tree'], saved_index)
        self.assertEqual(before, {name:(self.repo / name).read_bytes() for name in runtime_names})



    def test_existing_stash_stack_and_untracked_photos_are_untouched(self):
        self.dirty()
        old_stash = self.g('stash', 'create', 'prior-user-snapshot').strip()
        self.g('update-ref', 'refs/stash', old_stash)
        photos = self.repo / 'device-photos'
        photos.mkdir()
        (photos / 'original.jpg').write_bytes(b'original device photo')
        out = self.apply()
        self.assertEqual(out['status'], 'UPDATED', out)
        self.assertEqual(self.g('rev-parse', 'refs/stash').strip(), old_stash)
        self.assertEqual((photos / 'original.jpg').read_bytes(), b'original device photo')


if __name__ == '__main__':
    unittest.main()
