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


if __name__ == '__main__':
    unittest.main()
