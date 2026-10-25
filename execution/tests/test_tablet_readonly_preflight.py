"""Offline fixtures prove bounded, non-mutating diagnostics and honest HOLDs."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from execution import tablet_readonly_preflight as m


class ReadonlyPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        self.state = self.root / 'state'
        self._git('init', '-q')
        self._git('config', 'user.name', 'Offline Test')
        self._git('config', 'user.email', 'offline@localhost')
        (self.repo / 'source.txt').write_text('last good\n')
        self._git('add', 'source.txt')
        self._git('commit', '-qm', 'fixture')
        self.sha = self._git('rev-parse', 'HEAD').strip()
        self.now = 1_800_000_000
        self.config = {'schema': 1, 'enabled': True, 'repo': str(self.repo)}
        self.status = {'status': 'SUPERVISING', 'checked_at_epoch': self.now-1,
                       'running': {'running_build_sha': self.sha},
                       'learning': {'models': {'query': {'label_count': 315,
                           'eligible_training_labels': 6, 'minimum_labels': 1000,
                           'training_readiness': {'ready': False}},
                           'job': {'label_count': 600, 'minimum_labels': 1000}}}}
        self.write('automation/config.json', self.config)
        self.write('automation/status.json', self.status)

    def _git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], text=True,
                                       stderr=subprocess.DEVNULL)

    def write(self, name, value):
        path = self.state / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf-8')
        return path

    def report(self, **kwargs):
        return m.build_report(self.repo, self.state, now=self.now, **kwargs)

    def snapshot(self):
        return {str(path.relative_to(self.root)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in self.root.rglob('*') if path.is_file() and not path.is_symlink()}

    def test_fresh_matching_cache_is_only_preflight_never_authorization(self):
        self.write('image-learning/status.json', {'accepted_photos': 8, 'models': [{}, {}]})
        out = self.report(expected_sha=self.sha)
        self.assertEqual('PREFLIGHT_ONLY', out['status'])
        self.assertEqual('HOLD', out['decision'])
        for key in ('physical_tablet_verified', 'running_process_verified', 'restore_verified',
                    'deployment_allowed', 'model_promotion_allowed', 'training_allowed'):
            self.assertIs(False, out[key])
        self.assertEqual(6, out['observations']['cached_learning_models']['query']['eligible_training_labels'])
        self.assertEqual(8, out['observations']['cached_accepted_photos'])
        self.assertIn('verified_restore', out['missing_acceptance_evidence'])

    def test_missing_repository_does_not_create_it_or_any_output(self):
        absent = self.root / 'missing'
        out = m.build_report(absent, self.root / 'absent-state', now=self.now)
        self.assertEqual('HOLD', out['status'])
        self.assertFalse(absent.exists())
        self.assertFalse((self.root / 'absent-state').exists())

    def test_read_has_no_file_or_index_mutation(self):
        before = self.snapshot()
        self.report()
        self.assertEqual(before, self.snapshot())

    def test_dirty_checkout_is_preserved_and_holds(self):
        (self.repo / 'source.txt').write_text('local edits must survive\n')
        before = self.snapshot()
        out = self.report()
        self.assertIn('TRACKED_CHECKOUT_DIRTY', out['reasons'])
        self.assertEqual(before, self.snapshot())

    def test_untracked_main_is_never_executed(self):
        marker = self.root / 'executed'
        (self.repo / 'main').write_text('touch ' + str(marker))
        self.report()
        self.assertFalse(marker.exists())

    def test_expected_and_cached_build_mismatches_hold(self):
        out = self.report(expected_sha='a'*40)
        self.assertIn('EXPECTED_SHA_DIFFERS_FROM_DISK', out['reasons'])
        self.status['running']['running_build_sha'] = 'b'*40
        self.write('automation/status.json', self.status)
        self.assertIn('CACHED_BUILD_DIFFERS_FROM_DISK_OR_UNKNOWN', self.report()['reasons'])

    def test_wrong_checkout_configuration_and_boolean_schema_hold(self):
        for change in ({'repo': '/some/other/repo'}, {'schema': True}, {'enabled': 'true'}):
            self.write('automation/config.json', {**self.config, **change})
            self.assertIn('AUTOMATION_CONFIGURATION_UNVERIFIED', self.report()['reasons'])

    def test_stale_future_and_invalid_heartbeat_hold(self):
        for value in (self.now-181, self.now+1, True, '1800000000', 10**1000, None):
            with self.subTest(value=str(value)[:20]):
                self.write('automation/status.json', {**self.status, 'checked_at_epoch': value})
                self.assertIn('CACHED_HEARTBEAT_STALE_OR_INVALID', self.report()['reasons'])

    def test_non_supervising_state_holds(self):
        self.write('automation/status.json', {**self.status, 'status': 'HOLD'})
        self.assertIn('CACHED_AUTOMATION_NOT_SUPERVISING', self.report()['reasons'])

    def test_duplicate_nonfinite_bad_utf8_and_nested_json_fail_closed(self):
        path = self.state / 'automation/status.json'
        bad = (b'{"status":"SUPERVISING","status":"HOLD"}', b'{"x":NaN}',
               b'{"x":1e999}', b'\xff', b'[]', b'{', b'{"x":'+b'['*40+b'0'+b']'*40+b'}')
        for raw in bad:
            with self.subTest(raw=raw[:35]):
                path.write_bytes(raw)
                out = self.report()
                self.assertEqual('INVALID_OR_UNSAFE', out['files']['automation_status']['status'])
                self.assertEqual('HOLD', out['status'])

    def test_giant_file_and_fifo_rejected_without_blocking(self):
        path = self.state / 'automation/status.json'
        path.write_bytes(b' ' * (m.MAX_BYTES+1))
        self.assertEqual('INVALID_OR_UNSAFE', self.report()['files']['automation_status']['status'])
        path.unlink()
        os.mkfifo(path)
        started = time.monotonic()
        self.assertEqual('INVALID_OR_UNSAFE', self.report()['files']['automation_status']['status'])
        self.assertLess(time.monotonic()-started, 2)

    def test_symlink_leaf_parent_and_repository_are_rejected(self):
        outside_file = self.root / 'outside.json'
        outside_file.write_text('{"unrelated":"not-for-report"}')
        path = self.state / 'automation/status.json'
        path.unlink()
        path.symlink_to(outside_file)
        out = self.report()
        self.assertEqual('INVALID_OR_UNSAFE', out['files']['automation_status']['status'])
        self.assertNotIn('not-for-report', json.dumps(out))
        linked = self.root / 'linked-state'
        linked.symlink_to(self.state, target_is_directory=True)
        self.assertEqual('INVALID_OR_UNSAFE', m.read_json(linked / 'automation/config.json')[0]['status'])
        repo_link = self.root / 'linked-repo'
        repo_link.symlink_to(self.repo, target_is_directory=True)
        out = m.build_report(repo_link, self.state, now=self.now)
        self.assertIn('GIT_METADATA_UNVERIFIED', out['reasons'])

    def test_raw_unknown_strings_urls_and_paths_never_enter_report(self):
        marker = 'https://example.invalid/omitted-fixture-value'
        self.status['reason'] = marker
        self.status['learning']['models']['query'].update(reason=marker, label_count=True,
                                                        minimum_labels=-1, progress_percent=marker)
        self.write('automation/status.json', self.status)
        self.write('image-learning/status.json', {'accepted_photos': True, 'models': marker})
        out = self.report()
        encoded = json.dumps(out)
        self.assertNotIn(marker, encoded)
        self.assertNotIn(str(self.repo), encoded)
        query = out['observations']['cached_learning_models']['query']
        self.assertNotIn('label_count', query)
        self.assertNotIn('minimum_labels', query)
        self.assertNotIn('cached_accepted_photos', out['observations'])

    def test_missing_and_malformed_image_status_are_different(self):
        self.assertEqual('PREFLIGHT_ONLY', self.report()['status'])
        self.write('image-learning/status.json', [])
        self.assertIn('CACHED_IMAGE_STATUS_INVALID_OR_UNSAFE', self.report()['reasons'])

    def test_training_failure_is_reported_without_leaking_raw_error(self):
        marker = 'https://untrusted.invalid/private-runtime-error'
        self.status['learning']['models']['query'].update(
            training_attempted=True, last_training_status='FAILED',
            last_training_error=marker)
        self.write('automation/status.json', self.status)
        out = self.report()
        self.assertEqual('HOLD', out['status'])
        self.assertIn('CACHED_MODEL_TRAINING_FAILURE_OBSERVED', out['reasons'])
        self.assertTrue(out['observations']['cached_learning_models']['query']['cached_training_failure_signal'])
        self.assertNotIn(marker, json.dumps(out))

    def test_training_fail_flags_and_count_contradiction_hold(self):
        query = self.status['learning']['models']['query']
        query['training_failed'] = True
        query['training_readiness']['ready'] = True
        self.write('automation/status.json', self.status)
        out = self.report()
        self.assertIn('CACHED_MODEL_TRAINING_FAILURE_OBSERVED', out['reasons'])
        self.assertIn('CACHED_MODEL_READINESS_INCONSISTENT', out['reasons'])
        self.assertIs(False, out['observations']['cached_learning_models']['query']['observed_readiness_count_consistent'])
        self.assertFalse(out['deployment_allowed'])

    def test_impossible_eligible_count_and_bad_training_state_type(self):
        self.status['learning']['models']['query'].update(
            eligible_training_labels=316, training_status={'untrusted': 'never echo'})
        self.write('automation/status.json', self.status)
        out = self.report()
        self.assertIn('CACHED_MODEL_READINESS_INCONSISTENT', out['reasons'])
        self.assertNotIn('never echo', json.dumps(out))

    def test_optional_learning_snapshot_age_is_explicitly_bounded(self):
        self.assertIs(False, self.report()['observations']['cached_learning_snapshot_fresh'])
        for stamp in (self.now - 86401, self.now + 1, True, 'invalid'):
            with self.subTest(stamp=stamp):
                self.status['learning']['checked_at_epoch'] = stamp
                self.write('automation/status.json', self.status)
                out = self.report()
                self.assertIn('CACHED_LEARNING_SNAPSHOT_STALE_OR_INVALID', out['reasons'])
                self.assertEqual('HOLD', out['status'])
        self.status['learning']['checked_at_epoch'] = self.now - 20
        self.write('automation/status.json', self.status)
        out = self.report()
        self.assertTrue(out['observations']['cached_learning_snapshot_fresh'])
        self.assertNotIn('CACHED_LEARNING_SNAPSHOT_STALE_OR_INVALID', out['reasons'])

    def test_live_scheduler_learning_failure_and_errors_not_silenced(self):
        marker = 'PRIVATE_NEVER_ECHO_RUNTIME_EXCEPTION'
        self.status['learning'].update(ok=False, errors=[{'model': 'query', 'error': marker}])
        self.write('automation/status.json', self.status)
        out = self.report()
        self.assertEqual('HOLD', out['status'])
        self.assertIn('CACHED_LEARNING_CYCLE_REPORTED_FAILURE', out['reasons'])
        self.assertIn('CACHED_LEARNING_ERRORS_OBSERVED', out['reasons'])
        self.assertEqual(1, out['observations']['cached_learning_error_count'])
        self.assertNotIn(marker, json.dumps(out))

    def test_live_scheduler_stale_learning_timestamps_are_independent_of_heartbeat(self):
        for key, code, limit in (
                ('learning_observed_epoch', 'CACHED_LEARNING_OBSERVATION_STALE_OR_INVALID', 900),
                ('learning_checked_epoch', 'CACHED_LEARNING_TRAIN_CHECK_STALE_OR_INVALID', 21780)):
            for stamp in (self.now - limit - 1, self.now + 1, True, 'bad'):
                with self.subTest(key=key, stamp=stamp):
                    self.status.pop('learning_observed_epoch', None)
                    self.status.pop('learning_checked_epoch', None)
                    self.status[key] = stamp
                    self.write('automation/status.json', self.status)
                    out = self.report()
                    self.assertIn(code, out['reasons'])
                    self.assertEqual('HOLD', out['status'])
            self.status.pop(key, None)
        self.status['learning_observed_epoch'] = self.now - 30
        self.status['learning_checked_epoch'] = self.now - 60
        self.status['learning_status_cached'] = True
        self.write('automation/status.json', self.status)
        out = self.report()
        self.assertEqual('PREFLIGHT_ONLY', out['status'])
        self.assertTrue(out['observations']['cached_learning_observation_fresh'])
        self.assertTrue(out['observations']['cached_learning_train_check_recent'])

    def test_cached_status_without_observation_proof_holds(self):
        self.status['learning_status_cached'] = True
        self.write('automation/status.json', self.status)
        out = self.report()
        self.assertIn('CACHED_LEARNING_CACHE_WITHOUT_OBSERVATION_EVIDENCE', out['reasons'])

    def test_actual_training_result_inactive_is_reviewed_as_failure(self):
        self.status['learning']['models']['query'].update(
            training_attempted=True,
            training_result={'active': False, 'training_skipped': False,
                             'reason': 'do not expose raw detail'})
        self.write('automation/status.json', self.status)
        out = self.report()
        self.assertIn('CACHED_MODEL_TRAINING_FAILURE_OBSERVED', out['reasons'])
        self.assertNotIn('do not expose raw detail', json.dumps(out))

    def test_fsmonitor_and_hooks_are_not_executed(self):
        marker = self.root / 'executed'
        monitor = self.root / 'monitor.sh'
        monitor.write_text('#!/bin/sh\ntouch "' + str(marker) + '"\n')
        monitor.chmod(0o700)
        self._git('config', 'core.fsmonitor', str(monitor))
        self.report()
        self.assertFalse(marker.exists())

    def test_configured_clean_filter_holds_before_execution(self):
        (self.repo / '.gitattributes').write_text('source.txt filter=poison\n')
        self._git('add', '.gitattributes')
        self._git('commit', '-qm', 'filter fixture')
        marker = self.root / 'filter-executed'
        clean = self.root / 'clean.sh'
        clean.write_text('#!/bin/sh\ntouch "' + str(marker) + '"\ncat\n')
        clean.chmod(0o700)
        self._git('config', 'filter.poison.clean', str(clean))
        (self.repo / 'source.txt').write_text('last evil\n')
        out = self.report()
        self.assertIn('GIT_METADATA_UNVERIFIED', out['reasons'])
        self.assertFalse(marker.exists())

    def test_inherited_git_trace_cannot_write_files(self):
        marker = self.root / 'git-trace'
        with patch.dict(os.environ, {'GIT_TRACE': str(marker),
                                     'GIT_TRACE2_EVENT': str(marker),
                                     'GIT_TRACE_PERFORMANCE': str(marker)}):
            self.assertEqual(self.sha, self.report()['git']['disk_sha'])
        self.assertFalse(marker.exists())

    def test_inherited_git_routing_cannot_redirect_checkout(self):
        with patch.dict(os.environ, {'GIT_DIR': '/absent/evil-git', 'GIT_WORK_TREE': '/absent/evil-tree',
                                     'GIT_INDEX_FILE': '/absent/evil-index'}):
            self.assertEqual(self.sha, self.report()['git']['disk_sha'])

    def test_git_output_bound_is_fail_closed(self):
        executable = self.root / 'git'
        executable.write_text('#!/bin/sh\nhead -c 70000 /dev/zero\n')
        executable.chmod(0o700)
        with patch.dict(os.environ, {'PATH': str(self.root)+':'+os.environ['PATH']}):
            with self.assertRaises(m.ReadHold):
                m._git(self.repo, 'status')

    def test_git_timeout_is_fail_closed(self):
        with patch.object(m.time, 'monotonic', side_effect=[0, 6]):
            with self.assertRaisesRegex(m.ReadHold, 'GIT_TIMEOUT'):
                m._git(self.repo, 'rev-parse', 'HEAD')

    def test_cli_stdout_only_and_missing_repo_returns_hold(self):
        before = self.snapshot()
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            rc = m.main(['--repo', str(self.root/'no-repo'), '--state-root', str(self.state)])
        self.assertEqual(2, rc)
        self.assertEqual('HOLD', json.loads(buffer.getvalue())['status'])
        self.assertEqual(before, self.snapshot())


if __name__ == '__main__':
    unittest.main()
