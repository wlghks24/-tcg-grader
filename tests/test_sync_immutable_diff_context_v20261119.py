"""Ensure V369-V371 immutable Git cache never crosses execution contexts."""
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

    def test_bad_commit_id_not_silently_cached(self):
        with patch.object(cache.subprocess, 'check_output', side_effect=['one\n', 'two\n']) as runner:
            self.assertEqual(('one',), cache.immutable_diff_paths('not-a-sha', 'b' * 40))
            self.assertEqual(('two',), cache.immutable_diff_paths('not-a-sha', 'b' * 40))
        self.assertEqual(2, runner.call_count)
