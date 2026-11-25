"""Real-Git regression: fixed SHA objects can change under mutable replace refs."""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from execution import git_validation_cache as cache


class GitHistoryOverrideCacheTests(unittest.TestCase):
    def setUp(self):
        cache._cached_object_read.cache_clear()
        cache._cached_status_read.cache_clear()
        cache._git_admin_layout.cache_clear()
        cache._packed_replace_ref_present.cache_clear()
        self.addCleanup(cache._cached_object_read.cache_clear)
        self.addCleanup(cache._cached_status_read.cache_clear)
        self.addCleanup(cache._git_admin_layout.cache_clear)
        self.addCleanup(cache._packed_replace_ref_present.cache_clear)
        self.temp = tempfile.TemporaryDirectory(prefix='tcg-replace-ref-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'TCG History Guard')
        self.git('config', 'user.email', 'tcg@example.invalid')
        self.git('config', 'commit.gpgsign', 'false')
        self.file = self.root / 'card.txt'
        self.file.write_bytes(b'ORIGINAL\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'baseline')
        self.base = self.git('rev-parse', 'HEAD').decode().strip()
        self.file.write_bytes(b'REPLACEMENT\n')
        self.git('commit', '-qam', 'alternative')
        self.candidate = self.git('rev-parse', 'HEAD').decode().strip()
        self.command = ['git', 'show', self.base + ':card.txt']

    def git(self, *args):
        return subprocess.check_output(
            ['git', '-C', str(self.root), *args], timeout=10,
        )

    def read_cached(self):
        return cache.git_validation_output(
            self.command, cwd=self.root, timeout=10,
        )

    def test_normal_fixed_sha_reuse_still_works_without_overrides(self):
        self.assertFalse(cache._mutable_git_history_override_risk(self.root))
        self.assertEqual(b'ORIGINAL\n', self.read_cached())
        self.assertEqual(b'ORIGINAL\n', self.read_cached())
        self.assertGreaterEqual(cache._cached_object_read.cache_info().hits, 1)

    def test_external_git_object_alternates_cannot_cache_stale_success(self):
        # Only the alternate repo owns the requested commit. If its mutable
        # alternate pointer disappears, an old successful SHA read is unsafe.
        with tempfile.TemporaryDirectory(prefix='tcg-object-alternates-') as temp:
            consumer = Path(temp)
            subprocess.run(['git', 'init', '-q', str(consumer)], check=True, timeout=10)
            pointer = consumer / '.git' / 'objects' / 'info' / 'alternates'
            pointer.write_text(str((self.root / '.git' / 'objects').resolve()) + '\n',
                               encoding='utf-8')
            command = ['git', 'show', self.base + ':card.txt']

            def read():
                return cache.git_validation_output(command, cwd=consumer, timeout=10)

            self.assertTrue(cache._mutable_git_history_override_risk(consumer))
            self.assertEqual(b'ORIGINAL\n', read())
            self.assertEqual(b'ORIGINAL\n', read())
            self.assertEqual(0, cache._cached_object_read.cache_info().hits,
                             'live alternate objects must not enter the LRU')
            pointer.unlink()
            with self.assertRaises(subprocess.CalledProcessError):
                read()

    def test_linked_worktree_common_object_alternates_disable_cache(self):
        with tempfile.TemporaryDirectory(prefix='tcg-alternates-worktree-') as other:
            self.git('worktree', 'add', '-q', '--detach', other, self.candidate)
            worktree = Path(other)
            self.assertFalse(cache._mutable_git_history_override_risk(worktree))
            pointer = self.root / '.git' / 'objects' / 'info' / 'alternates'
            pointer.write_text('/nonexistent-object-store\n', encoding='utf-8')
            self.assertTrue(cache._mutable_git_history_override_risk(worktree))
            pointer.unlink()
            self.assertFalse(cache._mutable_git_history_override_risk(worktree))

    def test_custom_object_directory_alternates_never_cache_stale_sha(self):
        # The alternate pointer exists outside the standard .git admin dir.
        # A stable environment value must not imply stable Git objects.
        with tempfile.TemporaryDirectory(prefix='tcg-custom-objects-') as tmp:
            consumer = Path(tmp) / 'consumer'
            store = Path(tmp) / 'objects'
            subprocess.run(['git', 'init', '-q', str(consumer)], check=True, timeout=10)
            (store / 'info').mkdir(parents=True)
            pointer = store / 'info' / 'alternates'
            pointer.write_text(str((self.root / '.git' / 'objects').resolve()) + '\n',
                               encoding='utf-8')
            command = ['git', 'show', self.base + ':card.txt']
            with patch.dict(os.environ, {'GIT_OBJECT_DIRECTORY': str(store)}):
                self.assertTrue(cache._mutable_git_history_override_risk(consumer))
                self.assertEqual(b'ORIGINAL\n', cache.git_validation_output(
                    command, cwd=consumer, timeout=10,
                ))
                self.assertEqual(b'ORIGINAL\n', cache.git_validation_output(
                    command, cwd=consumer, timeout=10,
                ))
                self.assertEqual(0, cache._cached_object_read.cache_info().hits)
                pointer.unlink()
                with self.assertRaises(subprocess.CalledProcessError):
                    cache.git_validation_output(command, cwd=consumer, timeout=10)

    def test_alternate_object_dirs_env_revalidates_live_objects(self):
        with tempfile.TemporaryDirectory(prefix='tcg-env-alternates-') as tmp:
            consumer = Path(tmp)
            subprocess.run(['git', 'init', '-q', str(consumer)], check=True, timeout=10)
            other_objects = self.root / '.git' / 'objects'
            hidden = self.root / '.git' / 'objects-hidden'
            command = ['git', 'show', self.base + ':card.txt']
            with patch.dict(os.environ, {
                'GIT_ALTERNATE_OBJECT_DIRECTORIES': str(other_objects),
            }):
                self.assertTrue(cache._mutable_git_history_override_risk(consumer))
                self.assertEqual(b'ORIGINAL\n', cache.git_validation_output(
                    command, cwd=consumer, timeout=10,
                ))
                self.assertEqual(b'ORIGINAL\n', cache.git_validation_output(
                    command, cwd=consumer, timeout=10,
                ))
                self.assertEqual(0, cache._cached_object_read.cache_info().hits)
                other_objects.rename(hidden)
                try:
                    with self.assertRaises(subprocess.CalledProcessError):
                        cache.git_validation_output(command, cwd=consumer, timeout=10)
                finally:
                    hidden.rename(other_objects)

    def test_reftable_replace_refs_bypass_immutable_cache(self):
        with tempfile.TemporaryDirectory(prefix='tcg-reftable-') as tmp:
            root = Path(tmp) / 'repo'
            result = subprocess.run(
                ['git', 'init', '-q', '--ref-format=reftable', str(root)],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode:
                if 'unknown option' in result.stderr and 'ref-format' in result.stderr:
                    self.skipTest('Git does not support reftable repositories')
                raise subprocess.CalledProcessError(
                    result.returncode, result.args, result.stdout, result.stderr,
                )

            def git(*args):
                return subprocess.check_output(
                    ['git', '-C', str(root), *args], timeout=10,
                )

            git('config', 'user.name', 'TCG History Guard')
            git('config', 'user.email', 'tcg@example.invalid')
            git('config', 'commit.gpgsign', 'false')
            card = root / 'card.txt'
            card.write_bytes(b'ORIGINAL\n')
            git('add', '.')
            git('commit', '-qm', 'baseline')
            base = git('rev-parse', 'HEAD').decode().strip()
            card.write_bytes(b'REPLACEMENT\n')
            git('commit', '-qam', 'alternative')
            candidate = git('rev-parse', 'HEAD').decode().strip()
            command = ['git', 'show', base + ':card.txt']

            def read(cwd):
                return cache.git_validation_output(command, cwd=cwd, timeout=10)

            worktree = Path(tmp) / 'worktree'
            git('worktree', 'add', '-q', '--detach', str(worktree), candidate)
            for cwd in (root, worktree):
                self.assertTrue(cache._mutable_git_history_override_risk(cwd))
                self.assertEqual(b'ORIGINAL\n', read(cwd))
            git('replace', base, candidate)
            self.assertFalse((root / '.git/refs/replace').exists())
            for cwd in (root, worktree):
                self.assertEqual(b'REPLACEMENT\n', read(cwd))
            git('replace', '-d', base)
            for cwd in (root, worktree):
                self.assertEqual(b'ORIGINAL\n', read(cwd))
            self.assertEqual(0, cache._cached_object_read.cache_info().currsize)

    def test_nested_repository_discovery_does_not_reuse_parent_objects(self):
        for bare in (False, True):
            with self.subTest(bare=bare):
                nested = self.root / ('nested-bare' if bare else 'nested-worktree')
                nested.mkdir()
                def read():
                    return cache.git_validation_output(
                        self.command, cwd=nested, timeout=10,
                    )
                self.assertEqual(b'ORIGINAL\n', read())
                self.assertTrue(cache._mutable_git_history_override_risk(nested))
                self.assertEqual(0, cache._cached_object_read.cache_info().currsize)
                args = ['git', '-C', str(nested), 'init', '-q']
                if bare:
                    args.append('--bare')
                subprocess.run(args, check=True, timeout=10)
                self.assertTrue(cache._mutable_git_history_override_risk(nested))
                with self.assertRaises(subprocess.CalledProcessError):
                    read()
        # An explicit root still reuses immutable objects.
        self.assertEqual(b'ORIGINAL\n', self.read_cached())
        self.assertEqual(b'ORIGINAL\n', self.read_cached())
        self.assertGreaterEqual(cache._cached_object_read.cache_info().hits, 1)

    def test_common_object_store_removal_and_replacement_bypass_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / 'work'
            self.git('worktree', 'add', '-q', '--detach', str(work), self.candidate)
            objects = self.root / '.git' / 'objects'
            saved = objects.with_name('objects-saved')
            def read(cwd):
                return cache.git_validation_output(self.command, cwd=cwd, timeout=10)
            for cwd in (self.root, work):
                self.assertFalse(cache._mutable_git_history_override_risk(cwd))
                self.assertEqual(b'ORIGINAL\n', read(cwd))
            objects.rename(saved)
            try:
                for cwd in (self.root, work):
                    self.assertTrue(cache._mutable_git_history_override_risk(cwd))
                    with self.assertRaises(subprocess.CalledProcessError):
                        read(cwd)
                (objects / 'info').mkdir(parents=True)
                (objects / 'pack').mkdir()
                for cwd in (self.root, work):
                    self.assertTrue(cache._mutable_git_history_override_risk(cwd))
                    with self.assertRaises(subprocess.CalledProcessError):
                        read(cwd)
                (objects / 'info').rmdir()
                (objects / 'pack').rmdir()
                objects.rmdir()
                objects.symlink_to(saved, target_is_directory=True)
                for cwd in (self.root, work):
                    self.assertTrue(cache._mutable_git_history_override_risk(cwd))
                    self.assertEqual(b'ORIGINAL\n', read(cwd))
            finally:
                if objects.is_symlink():
                    objects.unlink()
                elif objects.exists():
                    import shutil
                    shutil.rmtree(objects)
                saved.rename(objects)
            for cwd in (self.root, work):
                self.assertFalse(cache._mutable_git_history_override_risk(cwd))
                self.assertEqual(b'ORIGINAL\n', read(cwd))
            self.git('worktree', 'remove', '--force', str(work))

    def test_initial_symlink_object_store_never_enters_cache(self):
        objects = self.root / '.git' / 'objects'
        saved = objects.with_name('objects-saved')
        objects.rename(saved)
        objects.symlink_to(saved, target_is_directory=True)
        try:
            self.assertTrue(cache._mutable_git_history_override_risk(self.root))
            self.assertEqual(b'ORIGINAL\n', self.read_cached())
            self.assertEqual(0, cache._cached_object_read.cache_info().currsize)
        finally:
            objects.unlink()
            saved.rename(objects)

    def test_new_loose_replace_ref_cannot_poison_warm_cache(self):
        self.assertEqual(b'ORIGINAL\n', self.read_cached())
        self.git('replace', self.base, self.candidate)
        self.assertTrue(cache._mutable_git_history_override_risk(self.root))
        self.assertEqual(b'REPLACEMENT\n', self.read_cached())
        self.git('replace', '-d', self.base)
        self.assertEqual(b'ORIGINAL\n', self.read_cached())

    def test_packed_replace_ref_cannot_poison_warm_cache(self):
        self.assertEqual(b'ORIGINAL\n', self.read_cached())
        self.git('replace', self.base, self.candidate)
        self.git('pack-refs', '--all')
        packed = self.root / '.git' / 'packed-refs'
        self.assertTrue(packed.is_file())
        self.assertIn(b'refs/replace/', packed.read_bytes())
        # Git leaves a now-empty refs/replace directory behind. Remove it
        # to prove detection comes from packed refs, not the loose directory.
        loose = self.root / '.git' / 'refs' / 'replace'
        self.assertEqual([], list(loose.iterdir()))
        loose.rmdir()
        self.assertTrue(cache._mutable_git_history_override_risk(self.root))
        self.assertEqual(b'REPLACEMENT\n', self.read_cached())
        self.git('replace', '-d', self.base)
        self.assertEqual(b'ORIGINAL\n', self.read_cached())

    def test_mutable_grafts_and_shallow_markers_disable_immutable_cache(self):
        self.assertEqual(b'ORIGINAL\n', self.read_cached())
        gitdir = self.root / '.git'
        for marker in (gitdir / 'info' / 'grafts', gitdir / 'shallow'):
            with self.subTest(marker=marker.name):
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.write_text(self.base + '\n', encoding='ascii')
                self.assertTrue(cache._mutable_git_history_override_risk(self.root))
                marker.unlink()
                self.assertFalse(cache._mutable_git_history_override_risk(self.root))

    def test_linked_worktree_checks_common_git_replace_refs(self):
        with tempfile.TemporaryDirectory(prefix='tcg-replace-worktree-') as other:
            self.git('worktree', 'add', '-q', '--detach', other, self.candidate)
            nested = Path(other)
            self.assertTrue((nested / '.git').is_file())
            self.assertFalse(cache._mutable_git_history_override_risk(nested))
            command = ['git', 'show', self.base + ':card.txt']
            self.assertEqual(
                b'ORIGINAL\n',
                cache.git_validation_output(command, cwd=nested, timeout=10),
            )
            self.git('replace', self.base, self.candidate)
            self.assertTrue(cache._mutable_git_history_override_risk(nested))
            self.assertEqual(
                b'REPLACEMENT\n',
                cache.git_validation_output(command, cwd=nested, timeout=10),
            )

    def test_linked_gitdir_and_commondir_redirect_bypass_warm_cache(self):
        for common in (False, True):
            with self.subTest(common=common), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                work = base / 'work'
                self.git('worktree', 'add', '-q', '--detach', str(work), self.candidate)
                admin = Path((work / '.git').read_text().strip()[8:])
                other = base / 'other'
                subprocess.run(['git', 'init', '-q', str(other)], check=True, timeout=10)
                alias = base / 'alias'
                alias.symlink_to(self.root / '.git' if common else admin,
                                 target_is_directory=True)
                pointer = admin / 'commondir' if common else work / '.git'
                original = pointer.read_bytes()
                try:
                    pointer.write_text(('' if common else 'gitdir: ') + str(alias) + '\n')
                    def read():
                        return cache.git_validation_output(self.command, cwd=work, timeout=10)
                    self.assertFalse(cache._mutable_git_history_override_risk(work))
                    self.assertEqual(b'ORIGINAL\n', read())
                    self.assertEqual(b'ORIGINAL\n', read())
                    alias.unlink()
                    alias.symlink_to(other / '.git', target_is_directory=True)
                    self.assertTrue(cache._mutable_git_history_override_risk(work))
                    with self.assertRaises(subprocess.CalledProcessError):
                        read()
                    alias.unlink()
                    alias.symlink_to(alias)
                    self.assertTrue(cache._mutable_git_history_override_risk(work))
                finally:
                    pointer.write_bytes(original)
                    self.git('worktree', 'remove', '--force', str(work))

    def test_linked_admin_directory_replacement_disables_warm_cache(self):
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / 'work'
            self.git('worktree', 'add', '-q', '--detach', str(work), self.candidate)
            admin = Path((work / '.git').read_text().strip()[8:])
            original = admin.with_name(admin.name + '-old')
            self.assertFalse(cache._mutable_git_history_override_risk(work))
            self.assertEqual(b'ORIGINAL\n', cache.git_validation_output(
                self.command, cwd=work, timeout=10,
            ))
            admin.rename(original)
            try:
                shutil.copytree(original, admin)
                self.assertTrue(cache._mutable_git_history_override_risk(work))
            finally:
                if admin.exists():
                    shutil.rmtree(admin)
                original.rename(admin)
                self.git('worktree', 'remove', '--force', str(work))

    def test_admin_layout_memoization_still_checks_live_grafts(self):
        self.assertFalse(cache._mutable_git_history_override_risk(self.root))
        self.assertFalse(cache._mutable_git_history_override_risk(self.root))
        self.assertGreaterEqual(cache._git_admin_layout.cache_info().hits, 1)
        graft = self.root / '.git' / 'info' / 'grafts'
        graft.write_text(self.base + '\n', encoding='ascii')
        self.assertTrue(cache._mutable_git_history_override_risk(self.root))
        graft.unlink()
        self.assertFalse(cache._mutable_git_history_override_risk(self.root))

    def test_packed_ref_digest_cache_detects_late_replace(self):
        self.git('pack-refs', '--all')
        self.assertFalse(cache._mutable_git_history_override_risk(self.root))
        self.assertFalse(cache._mutable_git_history_override_risk(self.root))
        self.assertGreaterEqual(cache._packed_replace_ref_present.cache_info().hits, 1)
        self.assertEqual(b'ORIGINAL\n', self.read_cached())
        self.git('replace', self.base, self.candidate)
        self.git('pack-refs', '--all')
        packed = self.root / '.git' / 'packed-refs'
        self.assertIn(b'refs/replace/', packed.read_bytes())
        loose = self.root / '.git' / 'refs' / 'replace'
        self.assertEqual([], list(loose.iterdir()))
        loose.rmdir()
        self.assertTrue(cache._mutable_git_history_override_risk(self.root))
        self.assertEqual(b'REPLACEMENT\n', self.read_cached())

    def test_permission_denied_override_marker_disables_cache(self):
        # A failed lstat must not be confused with a missing refs/replace.
        original = os.lstat
        blocked = os.fspath(self.root / '.git' / 'refs' / 'replace')
        def denied(path, *args, **kwargs):
            if os.fspath(path) == blocked:
                raise PermissionError('unreadable replace refs')
            return original(path, *args, **kwargs)
        self.assertFalse(cache._mutable_git_history_override_risk(self.root))
        with patch.object(cache.os, 'lstat', side_effect=denied):
            self.assertTrue(cache._mutable_git_history_override_risk(self.root))

    def test_unknown_admin_directory_disables_cache(self):
        with tempfile.TemporaryDirectory(prefix='tcg-not-a-repo-') as other:
            self.assertTrue(cache._mutable_git_history_override_risk(Path(other)))

    def test_v993_and_v995_outer_approvals_revalidate_real_replace_refs(self):
        import hashlib
        import json
        import sync_v376_successor_test_support as sync

        name = 'card.txt'
        original = hashlib.sha256(b'ORIGINAL\n').hexdigest()
        reviewed = hashlib.sha256(b'REPLACEMENT\n').hexdigest()
        hot = dict(path=name, baseline_commit=self.base,
                   candidate_commit=self.candidate, baseline_sha256=original,
                   reviewed_sha256=reviewed)
        post = dict(base_commit=self.base, candidate_commit=self.candidate,
                    reviewed_paths=[name], reviewed_sha256={name: reviewed},
                    reviewed_bytes={name: len(b'REPLACEMENT\n')})
        folder = self.root / '.github' / 'tablet-autonomy'
        folder.mkdir(parents=True)
        (folder / 'hot_sale_successor_v993.json').write_text(json.dumps(hot))
        (folder / 'post_v884_runtime_successor_v995.json').write_text(json.dumps(post))
        readers = (sync._v993_immutable_hot_evidence,
                   sync._v995_immutable_post_evidence)
        for reader in readers:
            reader.cache_clear()
            self.addCleanup(reader.cache_clear)
        with (patch.object(sync, 'ROOT', self.root),
              patch.object(sync, 'V993_HOT_SUCCESSOR', hot),
              patch.object(sync, 'V995_POST_V884_PROOF', post)):
            for _ in range(2):
                self.assertTrue(sync._v993_hot_live_verified())
                self.assertEqual([name], sync.verify_v995_post_v884())
            for reader in readers:
                self.assertGreaterEqual(reader.cache_info().hits, 1)
            self.git('replace', self.candidate, self.base)
            self.assertEqual(self.candidate, self.git('rev-parse', 'HEAD').decode().strip())
            self.assertTrue(cache._mutable_git_history_override_risk(self.root))
            self.assertFalse(sync._v993_hot_live_verified())
            with self.assertRaises(AssertionError):
                sync.verify_v995_post_v884()
            self.git('replace', '-d', self.candidate)
            self.assertTrue(sync._v993_hot_live_verified())
            self.assertEqual([name], sync.verify_v995_post_v884())


class GitCacheEnvironmentKeyTests(unittest.TestCase):
    """The fast key must stay equivalent and observe changing Git settings."""

    def test_only_git_relevant_environment_values_are_read(self):
        class GuardedValues(dict):
            def items(self):
                raise AssertionError('full environment value scan is forbidden')

            def __getitem__(self, key):
                if key == 'UNRELATED_SECRET':
                    raise AssertionError('irrelevant environment value was read')
                return super().__getitem__(key)

        values = GuardedValues({
            'UNRELATED_SECRET': 'must-not-read',
            'PATH': '/bin',
            'LANG': 'C',
            'GIT_OBJECT_DIRECTORY': '/tmp/object-one',
            'LC_ALL': 'ko_KR.UTF-8',
        })
        with patch.object(cache.os, 'environ', values):
            self.assertEqual((
                ('GIT_OBJECT_DIRECTORY', '/tmp/object-one'),
                ('LANG', 'C'),
                ('LC_ALL', 'ko_KR.UTF-8'),
                ('PATH', '/bin'),
            ), cache._environment_key())
            values['UNRELATED_SECRET'] = 'changed'
            self.assertEqual('/tmp/object-one', dict(cache._environment_key())['GIT_OBJECT_DIRECTORY'])
            before = cache._environment_key()
            values['GIT_OBJECT_DIRECTORY'] = '/tmp/object-two'
            self.assertNotEqual(before, cache._environment_key())
            values['LC_ALL'] = 'C'
            self.assertEqual('C', dict(cache._environment_key())['LC_ALL'])

    def test_cache_context_preserves_all_git_variable_prefixes(self):
        with patch.object(cache.os, 'environ', {
            'GIT_CONFIG_COUNT': '2',
            'GIT_CONFIG_KEY_0': 'core.quotePath',
            'GIT_CONFIG_VALUE_0': 'false',
            'GIT_NO_REPLACE_OBJECTS': '1',
            'LC_CTYPE': 'ko_KR.UTF-8',
            'IGNORED_SETTINGS': 'xyz',
        }):
            actual = dict(cache._environment_key())
        self.assertEqual('false', actual['GIT_CONFIG_VALUE_0'])
        self.assertEqual('1', actual['GIT_NO_REPLACE_OBJECTS'])
        self.assertEqual('ko_KR.UTF-8', actual['LC_CTYPE'])
        self.assertNotIn('IGNORED_SETTINGS', actual)


class V881OuterHistoryReplacementTests(unittest.TestCase):
    """A warmed outer V881 success cannot mask a later Git history override."""

    def test_late_override_bypasses_earlier_immutable_approval(self):
        import sync_v376_successor_test_support as sync
        from execution.tests import test_video_ui_successor_v881 as v881

        with tempfile.TemporaryDirectory(prefix='tcg-v881-outer-cache-') as tmp:
            root = Path(tmp)
            proofs = root / '.github' / 'tablet-autonomy'
            proofs.mkdir(parents=True)
            (proofs / 'video_ui_successor_v881.json').write_bytes(b'{}')
            (proofs / 'csp_hash_successor_v882.json').write_bytes(b'{}')
            calls = []

            def verify_candidate():
                calls.append(1)
                if len(calls) > 1:
                    raise AssertionError('replacement changed historical evidence')
                return ['index.html']

            sync._v881_immutable_review_at_head.cache_clear()
            self.addCleanup(sync._v881_immutable_review_at_head.cache_clear)
            with (
                patch.object(sync, 'ROOT', root),
                patch.object(v881, 'validate_candidate', side_effect=verify_candidate),
                patch.object(sync, '_mutable_git_history_override_risk',
                             return_value=False) as risk,
            ):
                first = sync._v881_checked_immutable_review_at_head('a' * 40)
                self.assertEqual(first[0], ('index.html',))
                self.assertEqual(first, sync._v881_checked_immutable_review_at_head('a' * 40))
                self.assertEqual(len(calls), 1, 'stable Git history should use LRU')
                risk.return_value = True
                with self.assertRaisesRegex(AssertionError, 'replacement changed'):
                    sync._v881_checked_immutable_review_at_head('a' * 40)
                self.assertEqual(len(calls), 2, 'mutable Git history must rerun proof')


if __name__ == '__main__':
    unittest.main()
