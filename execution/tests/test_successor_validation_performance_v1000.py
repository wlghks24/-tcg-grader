"""Immutable successor caches must preserve every live validation boundary."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import sync_v376_successor_test_support as sync
from execution import git_validation_cache as git_cache


class SuccessorValidationPerformanceV1000Tests(unittest.TestCase):
    def setUp(self):
        sync._v993_immutable_hot_evidence.cache_clear()
        sync._v995_immutable_post_evidence.cache_clear()
        git_cache._cached_status_read.cache_clear()
        git_cache._cached_object_read.cache_clear()

    def cases(self):
        return (
            (sync._v993_hot_live_verified, sync._v993_immutable_hot_evidence,
             sync.V993_HOT_SUCCESSOR, sync.ROOT / '.github/tablet-autonomy/hot_sale_successor_v993.json',
             ['box_knowledge_stats.js'], False),
            (sync.verify_v995_post_v884, sync._v995_immutable_post_evidence,
             sync.V995_POST_V884_PROOF, sync.ROOT / '.github/tablet-autonomy/post_v884_runtime_successor_v995.json',
             ['index.html', 'update_promo_events.py'], True),
        )

    def assert_blocked(self, validator, raises):
        if raises:
            with self.assertRaises(AssertionError):
                validator()
        else:
            self.assertFalse(validator())

    def test_warm_calls_reuse_only_git_objects_and_read_live_proof_and_files(self):
        for validator, cache, proof, receipt, paths, raises in self.cases():
            with self.subTest(validator=validator.__name__):
                self.assertTrue(validator())
                prior_hits = cache.cache_info().hits
                original_run = subprocess.run
                original_read = Path.read_bytes
                live_reads = []
                git_calls = []
                def run(args, *a, **kw):
                    git_calls.append(tuple(args))
                    return original_run(args, *a, **kw)
                def read(path):
                    live_reads.append(path)
                    return original_read(path)
                with patch.object(subprocess, 'run', run), patch.object(Path, 'read_bytes', read), \
                     patch.object(sync, '_read', wraps=sync._read) as proof_reads, \
                     patch.object(sync, '_resolved_successor_head_sha', wraps=sync._resolved_successor_head_sha) as head_reads:
                    self.assertTrue(validator())
                    prior_hits = cache.cache_info().hits
                    git_calls.clear()
                    live_reads.clear()
                    proof_reads.reset_mock()
                    head_reads.reset_mock()
                    for _ in range(2):
                        self.assertTrue(validator())
                    self.assertEqual(2, head_reads.call_count)
                    self.assertEqual(2, sum(call.args[0] == receipt for call in proof_reads.call_args_list))
                self.assertGreaterEqual(cache.cache_info().hits - prior_hits, 2)
                for name in paths:
                    self.assertGreaterEqual(live_reads.count(sync.ROOT / name), 2)
                if 'path' in proof:
                    history_refs = [proof['baseline_commit'] + ':' + proof['path'],
                                    proof['candidate_commit'] + ':' + proof['path']]
                else:
                    history_refs = [proof['candidate_commit'] + ':' + name for name in paths]
                self.assertFalse(any(call[:2] == ('git', 'show') and call[2] in history_refs
                                     for call in git_calls), git_calls)

    def test_changed_live_bytes_never_reuse_immutable_acceptance(self):
        original = Path.read_bytes
        for validator, cache, proof, receipt, paths, raises in self.cases():
            self.assertTrue(validator())
            for name in paths:
                target = sync.ROOT / name
                def changed(path, target=target):
                    data = original(path)
                    return data + b'unreviewed-after-warmup' if path == target else data
                with self.subTest(name=name), patch.object(Path, 'read_bytes', changed):
                    self.assert_blocked(validator, raises)

    def test_forged_proof_is_checked_before_cache_lookup(self):
        original = sync._read
        for validator, cache, proof, receipt, paths, raises in self.cases():
            self.assertTrue(validator())
            def forged(path, receipt=receipt):
                data = original(path)
                return {**data, 'deployment_allowed': True} if path == receipt else data
            with self.subTest(validator=validator.__name__), patch.object(sync, '_read', forged):
                self.assert_blocked(validator, raises)

    def test_linked_live_source_or_proof_is_rejected_after_warmup(self):
        original = Path.is_symlink
        for validator, cache, proof, receipt, paths, raises in self.cases():
            self.assertTrue(validator())
            for target in [receipt, *[sync.ROOT / name for name in paths]]:
                with self.subTest(target=str(target)), patch.object(Path, 'is_symlink',
                        lambda path, target=target: path == target or original(path)):
                    self.assert_blocked(validator, raises)

    def test_resolved_head_change_does_not_reuse_previous_ancestry(self):
        for validator, cache, proof, receipt, paths, raises in self.cases():
            self.assertTrue(validator())
            prior_misses = cache.cache_info().misses
            base = proof.get('baseline_commit', proof.get('base_commit'))
            with self.subTest(validator=validator.__name__), \
                 patch.object(sync, '_resolved_successor_head_sha', return_value=base):
                self.assert_blocked(validator, raises)
            self.assertGreater(cache.cache_info().misses, prior_misses)

    def test_every_immutable_pin_is_part_of_cache_key(self):
        for validator, cache, proof, receipt, paths, raises in self.cases():
            self.assertTrue(validator())
            altered = copy.deepcopy(proof)
            if 'path' in proof:
                altered['reviewed_sha256'] = '0' * 64
            else:
                altered['reviewed_sha256'][paths[0]] = '0' * 64
            key = json.dumps(altered, sort_keys=True, separators=(',', ':'))
            head = sync._resolved_successor_head_sha()
            with self.subTest(validator=validator.__name__), self.assertRaises(AssertionError):
                cache(head, key, (subprocess.run, subprocess.check_output))

    def test_unresolved_head_fails_closed_without_reading_missing_stdout(self):
        failed = type('FailedGit', (), {'returncode': 1})()
        with patch.object(subprocess, 'run', return_value=failed):
            self.assertFalse(sync._v993_hot_live_verified())
            with self.assertRaises(AssertionError):
                sync.verify_v995_post_v884()


    def test_git_run_copies_results_and_preserves_options(self):
        args = ['git', 'merge-base', '--is-ancestor', 'a' * 40, 'b' * 40]
        calls = []
        def executor(command, **kwargs):
            calls.append((command, kwargs))
            return subprocess.CompletedProcess(command, 0, b'', b'')
        options = dict(cwd=sync.ROOT, capture_output=True, check=False, timeout=20)
        with patch.object(subprocess, 'run', executor):
            first = git_cache.git_validation_run(args, **options)
            first.stdout = b'untrusted mutation'
            first.args[3] = 'changed'
            second = git_cache.git_validation_run(args, **options)
        self.assertEqual(1, len(calls))
        self.assertEqual(b'', second.stdout)
        self.assertEqual(args, second.args)
        self.assertEqual({**options, 'cwd': str(sync.ROOT)}, calls[0][1])
        self.assertEqual(args, calls[0][0])

    def test_changed_executor_cannot_reuse_accepted_ancestry(self):
        args = ['git', 'merge-base', '--is-ancestor', 'a' * 40, 'b' * 40]
        def accepted(command, **kwargs):
            return subprocess.CompletedProcess(command, 0, b'', b'')
        def rejected(command, **kwargs):
            return subprocess.CompletedProcess(command, 1, b'', b'')
        with patch.object(subprocess, 'run', accepted):
            self.assertEqual(0, git_cache.git_validation_run(args, capture_output=True).returncode)
        with patch.object(subprocess, 'run', rejected):
            self.assertEqual(1, git_cache.git_validation_run(args, capture_output=True).returncode)

    def test_check_output_cache_observes_the_actual_run_executor(self):
        args = ['git', 'show', 'a' * 40 + ':path.txt']
        calls = []
        def output(command, **kwargs):
            calls.append(command)
            return b'blob'
        def runner_one(*a, **kw):
            raise AssertionError('output mock does not need a process')
        def runner_two(*a, **kw):
            raise AssertionError('output mock does not need a process')
        with patch.object(subprocess, 'check_output', output):
            with patch.object(subprocess, 'run', runner_one):
                self.assertEqual(b'blob', git_cache.git_validation_output(args))
                self.assertEqual(b'blob', git_cache.git_validation_output(args))
            with patch.object(subprocess, 'run', runner_two):
                self.assertEqual(b'blob', git_cache.git_validation_output(args))
        self.assertEqual(2, len(calls))

    def test_HEAD_resolves_on_every_request_and_separates_cache_entries(self):
        scratch = sync.ROOT / '.tmp'
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='git-cache-head-', dir=scratch) as temp:
            def git(*args):
                return subprocess.check_output(['git', '-C', temp, *args], stderr=subprocess.PIPE).decode().strip()
            git('init', '--quiet')
            identity = ('-c', 'user.name=Local Cache Test', '-c', 'user.email=cache-test@example.invalid')
            git(*identity, 'commit', '--quiet', '--allow-empty', '-m', 'first')
            first = git('rev-parse', 'HEAD')
            git(*identity, 'commit', '--quiet', '--allow-empty', '-m', 'second')
            second = git('rev-parse', 'HEAD')
            command = ['git', 'merge-base', '--is-ancestor', second, 'HEAD']
            before = git_cache._cached_status_read.cache_info()
            a = git_cache.git_validation_run(command, cwd=temp, capture_output=True)
            b = git_cache.git_validation_run(command, cwd=temp, capture_output=True)
            git('update-ref', 'HEAD', first)
            c = git_cache.git_validation_run(command, cwd=temp, capture_output=True)
            after = git_cache._cached_status_read.cache_info()
            self.assertEqual([0, 0, 1], [r.returncode for r in (a, b, c)])
            self.assertEqual(2, after.misses - before.misses)
            self.assertEqual(1, after.hits - before.hits)
            self.assertTrue(all(r.args == command for r in (a, b, c)))

    def test_injected_HEAD_executor_receives_the_original_operand(self):
        command = ['git', 'merge-base', '--is-ancestor', 'a' * 40, 'HEAD']
        calls = []
        def reject_head(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 1)
        with patch.object(subprocess, 'run', reject_head):
            for _ in range(2):
                self.assertEqual(1, git_cache.git_validation_run(command, capture_output=True).returncode)
        self.assertEqual([command, command], calls)

    def test_exact_blob_and_no_rename_diff_reads_reuse_only_same_cwd(self):
        show = ['git', 'show', 'a' * 40 + ':nested/path with space.txt']
        diff = ['git', 'diff', '--no-renames', '--name-only', 'a' * 40 + '..' + 'b' * 40,
                '--', 'nested/path with space.txt']
        calls = []
        def output(command, **kwargs):
            calls.append((command, kwargs))
            return 'exact output'
        with patch.object(subprocess, 'check_output', output):
            for command in (show, diff):
                for _ in range(2):
                    self.assertEqual('exact output', git_cache.git_validation_output(
                        command, cwd=sync.ROOT, text=True, timeout=7))
            git_cache.git_validation_output(show, cwd=sync.ROOT.parent, text=True, timeout=7)
        self.assertEqual(3, len(calls))
        self.assertEqual(show, calls[0][0])
        self.assertEqual(diff, calls[1][0])
        self.assertEqual(dict(cwd=str(sync.ROOT), text=True, timeout=7), calls[0][1])
        self.assertEqual(str(sync.ROOT.parent), calls[-1][1]['cwd'])

    def test_mutable_refs_worktree_reads_and_unknown_options_pass_through(self):
        calls = []
        def output(command, **kwargs):
            calls.append((command, kwargs))
            return b'original executor'
        commands = [(['git', 'hash-object', '--', 'worktree.txt'], {}),
                    (['git', 'show', 'main:index.html'], {}),
                    (['git', 'diff', '--name-only', 'a' * 40, 'b' * 40], {}),
                    (['git', 'show', 'a' * 40 + ':index.html'], {'env': {'CACHE_TEST': 'local'}})]
        with patch.object(subprocess, 'check_output', output):
            for command, options in commands:
                for _ in range(2):
                    self.assertEqual(b'original executor', git_cache.git_validation_output(command, **options))
        self.assertEqual(8, len(calls))
        self.assertEqual(commands[-1], calls[-1])

    def test_process_errors_are_not_cached_as_immutable_success(self):
        args = ['git', 'show', 'a' * 40 + ':missing']
        attempts = []
        def output(command, **kwargs):
            attempts.append(command)
            raise subprocess.CalledProcessError(128, command)
        with patch.object(subprocess, 'check_output', output):
            for _ in range(2):
                with self.assertRaises(subprocess.CalledProcessError):
                    git_cache.git_validation_output(args)
        self.assertEqual(2, len(attempts))


    def test_large_and_mutable_outputs_are_never_retained(self):
        show = ['git', 'show', 'a' * 40 + ':blob']
        status = ['git', 'merge-base', '--is-ancestor', 'a' * 40, 'b' * 40]
        for payload in (b'x' * (git_cache.MAX_OBJECT_OUTPUT_BYTES + 1), ['mutable']):
            calls = []
            def output(command, **kwargs):
                calls.append(command)
                return payload
            with patch.object(subprocess, 'check_output', output):
                for _ in range(2):
                    self.assertEqual(payload, git_cache.git_validation_output(show))
            self.assertEqual(2, len(calls))
        for payload in (b'x' * (git_cache.MAX_STATUS_OUTPUT_BYTES + 1), ['mutable']):
            calls = []
            def run(command, **kwargs):
                calls.append(command)
                return subprocess.CompletedProcess(command, 0, payload, b'')
            with patch.object(subprocess, 'run', run):
                for _ in range(2):
                    self.assertEqual(payload, git_cache.git_validation_run(status, capture_output=True).stdout)
            self.assertEqual(2, len(calls))

    def test_git_environment_changes_do_not_reuse_previous_object_reads(self):
        command = ['git', 'show', 'a' * 40 + ':blob']
        calls = []
        def output(args, **kwargs):
            calls.append(args)
            return b'immutable blob'
        with patch.object(subprocess, 'check_output', output):
            git_cache.git_validation_output(command)
            git_cache.git_validation_output(command)
            with patch.dict(os.environ, {'GIT_NO_REPLACE_OBJECTS': 'cache-test-different-policy'}):
                git_cache.git_validation_output(command)
        self.assertEqual(2, len(calls))


if __name__ == '__main__':
    unittest.main()
