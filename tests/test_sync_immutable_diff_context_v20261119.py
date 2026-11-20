"""Ensure V369-V371 immutable Git cache never crosses execution contexts."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import TestCase
from unittest.mock import patch

from execution.diagnostics import immutable_diff_cache as cache


class ImmutableDiffContextTests(TestCase):
    def setUp(self):
        cache.immutable_diff_paths.cache_clear()

    def tearDown(self):
        cache.immutable_diff_paths.cache_clear()

    def test_exact_sha_same_context_reuses_git_result(self):
        source, candidate = 'a' * 40, 'b' * 40
        with patch.object(cache.subprocess, 'check_output', return_value='main\n') as runner:
            self.assertEqual(('main',), cache.immutable_diff_paths(source, candidate))
            self.assertEqual(('main',), cache.immutable_diff_paths(source, candidate))
        runner.assert_called_once()

    def test_switching_executor_must_not_reuse_cached_result(self):
        source, candidate = 'a' * 40, 'b' * 40
        with patch.object(cache.subprocess, 'check_output', return_value='main\n') as first:
            self.assertEqual(('main',), cache.immutable_diff_paths(source, candidate))
        with patch.object(cache.subprocess, 'check_output', return_value='index.html\n') as second:
            self.assertEqual(('index.html',), cache.immutable_diff_paths(source, candidate))
        first.assert_called_once()
        second.assert_called_once()

    def test_git_object_directory_change_invalidates_cache(self):
        source, candidate = 'a' * 40, 'b' * 40
        with patch.object(cache.subprocess, 'check_output', side_effect=['main\n', 'index.html\n']) as runner:
            with patch.dict(cache.os.environ, {'GIT_OBJECT_DIRECTORY': '/tmp/cache-test-a'}):
                self.assertEqual(('main',), cache.immutable_diff_paths(source, candidate))
            with patch.dict(cache.os.environ, {'GIT_OBJECT_DIRECTORY': '/tmp/cache-test-b'}):
                self.assertEqual(('index.html',), cache.immutable_diff_paths(source, candidate))
        self.assertEqual(2, runner.call_count)

    def test_head_and_symbolic_ref_always_uncached(self):
        source = 'a' * 40
        for head in ('HEAD', 'refs/heads/main'):
            with self.subTest(head=head):
                with patch.object(cache.subprocess, 'check_output', side_effect=['main\n', 'index.html\n']) as runner:
                    self.assertEqual(('main',), cache.immutable_diff_paths(source, head))
                    self.assertEqual(('index.html',), cache.immutable_diff_paths(source, head))
                self.assertEqual(2, runner.call_count)


    def test_git_config_change_invalidates_cached_pair(self):
        source, candidate = 'a' * 40, 'b' * 40
        snapshots = [
            subprocess.CompletedProcess([], 0, stdout=b'file:.git/config\x00diff.renames\x00true\x00'),
            subprocess.CompletedProcess([], 0, stdout=b'file:.git/config\x00diff.renames\x00false\x00'),
        ]
        with patch.object(cache.subprocess, 'run', side_effect=snapshots):
            with patch.object(cache.subprocess, 'check_output',
                              side_effect=['new.txt\n', 'new.txt\nold.txt\n']) as runner:
                self.assertEqual(('new.txt',), cache.immutable_diff_paths(source, candidate))
                self.assertEqual(('new.txt', 'old.txt'), cache.immutable_diff_paths(source, candidate))
        self.assertEqual(2, runner.call_count)

    def test_unreadable_git_config_uses_uncached_diff(self):
        source, candidate = 'a' * 40, 'b' * 40
        with patch.object(cache.subprocess, 'run', side_effect=OSError('config unreadable')):
            with patch.object(cache.subprocess, 'check_output',
                              side_effect=['first.txt\n', 'second.txt\n']) as runner:
                self.assertEqual(('first.txt',), cache.immutable_diff_paths(source, candidate))
                self.assertEqual(('second.txt',), cache.immutable_diff_paths(source, candidate))
        self.assertEqual(2, runner.call_count)

    @unittest.skipUnless(shutil.which('git'), 'Git executable unavailable')
    def test_real_git_local_rename_config_invalidates_cached_pair(self):
        # End-to-end reproduction: a rename changes --name-only output when
        # diff.renames flips while both immutable SHA operands stay identical.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', '-q', str(root)], check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)

            def git(*args):
                return subprocess.run(['git', '-C', str(root), *args],
                                      check=True, capture_output=True,
                                      text=True, timeout=10).stdout.strip()

            git('config', 'user.name', 'TCG Regression')
            git('config', 'user.email', 'tcg@example.invalid')
            git('config', 'commit.gpgsign', 'false')
            (root / 'old.txt').write_text('sample content\n' * 40, encoding='utf-8')
            git('add', 'old.txt')
            git('commit', '-m', 'before rename')
            before = git('rev-parse', 'HEAD')
            git('mv', 'old.txt', 'new.txt')
            git('commit', '-m', 'after rename')
            after = git('rev-parse', 'HEAD')

            original = Path.cwd()
            os.chdir(root)
            try:
                git('config', '--local', 'diff.renames', 'true')
                renamed = cache.immutable_diff_paths(before, after)
                git('config', '--local', 'diff.renames', 'false')
                expanded = cache.immutable_diff_paths(before, after)
            finally:
                os.chdir(original)
            self.assertEqual(('new.txt',), renamed)
            self.assertEqual(('new.txt', 'old.txt'), expanded)


    @unittest.skipUnless(shutil.which('git'), 'Git executable unavailable')
    def test_real_replace_ref_bypasses_warmed_legacy_diff_cache(self):
        self._assert_replacement_ref_refresh(packed=False)

    @unittest.skipUnless(shutil.which('git'), 'Git executable unavailable')
    def test_real_packed_replace_ref_bypasses_warmed_legacy_diff_cache(self):
        self._assert_replacement_ref_refresh(packed=True)

    def _assert_replacement_ref_refresh(self, *, packed):
        # Identical 40-hex SHA operands can produce different diff output
        # after Git replace refs are added. Never accept prior cached success.
        with tempfile.TemporaryDirectory(prefix='tcg-legacy-replace-') as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', '-q', str(root)], check=True, timeout=10)

            def git(*args):
                return subprocess.check_output(
                    ['git', '-C', str(root), *args], text=True, timeout=10,
                ).strip()

            git('config', 'user.name', 'TCG Legacy Guard')
            git('config', 'user.email', 'tcg@example.invalid')
            git('config', 'commit.gpgsign', 'false')
            target = root / 'card.txt'
            target.write_text('original\\n', encoding='utf-8')
            git('add', '.')
            git('commit', '-qm', 'baseline')
            before = git('rev-parse', 'HEAD')
            target.write_text('candidate\\n', encoding='utf-8')
            git('add', '.')
            git('commit', '-qm', 'candidate')
            after = git('rev-parse', 'HEAD')

            previous = Path.cwd()
            try:
                os.chdir(root)
                self.assertEqual(('card.txt',), cache.immutable_diff_paths(before, after))
                self.assertEqual(('card.txt',), cache.immutable_diff_paths(before, after))
                self.assertGreaterEqual(cache._cached_diff.cache_info().hits, 1)
                git('replace', before, after)
                if packed:
                    git('pack-refs', '--all')
                    packed_file = root / '.git' / 'packed-refs'
                    self.assertIn('refs/replace/', packed_file.read_text())
                    loose = root / '.git' / 'refs' / 'replace'
                    self.assertEqual([], list(loose.iterdir()))
                    loose.rmdir()
                self.assertEqual((), cache.immutable_diff_paths(before, after))
                git('replace', '-d', before)
                self.assertEqual(('card.txt',), cache.immutable_diff_paths(before, after))
            finally:
                os.chdir(previous)

    def test_bad_commit_id_not_silently_cached(self):
        with patch.object(cache.subprocess, 'check_output', side_effect=['one\n', 'two\n']) as runner:
            self.assertEqual(('one',), cache.immutable_diff_paths('not-a-sha', 'b' * 40))
            self.assertEqual(('two',), cache.immutable_diff_paths('not-a-sha', 'b' * 40))
        self.assertEqual(2, runner.call_count)
