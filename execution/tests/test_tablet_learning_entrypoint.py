"""Entrypoint tests with simulated exits; never produce training labels."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class LearningEntrypointTests(unittest.TestCase):
    def invoke(self, *, autonomy=0, status=0, precheck=0, selftest=0, neural=0, command='learn'):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'main').write_bytes((ROOT / 'main').read_bytes())
            executable = root / 'python'
            executable.write_text('''#!/bin/bash
if [ "$1" = tablet_runtime_manifest.py ]; then exit "$PRECHECK_RC"; fi
if [ "$1" = tablet_autonomous_evolution_v400.py ]; then
  if [ "$2" = --self-test ]; then exit "$SELFTEST_RC"; fi
  printf '%s\\n' autonomy-invoked >> "$CALLS"
  exit "$AUTONOMY_RC"
fi
if [ "$1" = -m ] && [ "$2" = execution.tablet_local_learning ]; then
  printf '%s\\n' neural-invoked >> "$CALLS"
  exit "$NEURAL_RC"
fi
if [ "$1" = - ]; then
  cat >/dev/null
  printf '%s\\n' status-invoked >> "$CALLS"
  printf '%s\\n' '{"query":{"labels":17,"minimum_labels":1000},"job":{"labels":9}}'
  exit "$STATUS_RC"
fi
exit 99
''')
            executable.chmod(0o700)
            calls = root / 'calls'
            env = dict(os.environ, PATH=str(root)+os.pathsep+os.environ['PATH'],
                       AUTONOMY_RC=str(autonomy), NEURAL_RC=str(neural), STATUS_RC=str(status),
                       PRECHECK_RC=str(precheck), SELFTEST_RC=str(selftest), CALLS=str(calls))
            result = subprocess.run(['bash', str(root / 'main'), command], env=env,
                                    capture_output=True, text=True, timeout=5)
            return result, calls.read_text().splitlines() if calls.exists() else []

    def test_hold_preserves_exit_and_reports_real_label_status(self):
        run, calls = self.invoke(autonomy=2)
        self.assertEqual(run.returncode, 2)
        self.assertEqual(calls, ['autonomy-invoked', 'neural-invoked', 'status-invoked'])
        self.assertIn('"labels":17', run.stdout)
        self.assertNotIn('[OK]', run.stdout)

    def test_runtime_error_does_not_become_success(self):
        run, calls = self.invoke(autonomy=1)
        self.assertEqual(run.returncode, 1)
        self.assertEqual(calls.count('autonomy-invoked'), 1)
        self.assertIn('status-invoked', calls)
        self.assertNotIn('[OK]', run.stdout)

    def test_status_error_never_masks_original_error(self):
        run, _ = self.invoke(autonomy=2, status=7)
        self.assertEqual(run.returncode, 2)
        self.assertNotIn('[OK]', run.stdout)

    def test_status_error_is_reported_after_successful_cycle(self):
        run, _ = self.invoke(status=7)
        self.assertEqual(run.returncode, 7)
        self.assertNotIn('[OK]', run.stdout)

    def test_success_does_not_claim_a_model_was_trained(self):
        run, calls = self.invoke()
        self.assertEqual(run.returncode, 0)
        self.assertEqual(calls, ['autonomy-invoked', 'neural-invoked', 'status-invoked'])
        self.assertIn('[OK]', run.stdout)
        self.assertNotIn('"ok": true', run.stdout)

    def test_neural_error_is_not_claimed_success(self):
        run,calls=self.invoke(neural=8)
        self.assertEqual(run.returncode,8)
        self.assertIn('neural-invoked',calls)
        self.assertNotIn('[OK]',run.stdout)

    def test_precheck_and_selftest_fail_closed(self):
        for args in ({'precheck':11}, {'selftest':12}):
            run, calls = self.invoke(**args)
            self.assertNotEqual(run.returncode, 0)
            self.assertEqual(calls, [])

    def test_status_only_does_not_start_autonomy(self):
        run, calls = self.invoke(command='learn-status')
        self.assertEqual(run.returncode, 0)
        self.assertEqual(calls, ['status-invoked'])



class ScheduledLearningStatusTests(unittest.TestCase):
    def invoke(self, *, status_rc=0, no_timeout=False):
        source = (ROOT / 'TABLET_SCHEDULED_UPDATE.sh').read_text()
        function = source[source.index('capture_learning_status() {'):source.index('\nwrite_boot_heartbeat()')]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'main').write_text('#!/bin/bash\n[ "$1" = learn-status ] || exit 99\nprintf \'%s\\n\' \'{"query":{"labels":17},"job":{"labels":9}}\'\nexit "$STATUS_RC"\n')
            state = root / 'learning-status.env'
            state.write_text('old checkpoint')
            script = 'set -euo pipefail\nROOT="$1"; LOG_DIR="$1"; LEARNING_STATUS_FILE="$1/learning-status.env"\nnow() { printf test-time; }\nsha() { printf aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa; }\ntimeout() { [ "$1" = 10s ] || return 99; shift; "$@"; }\n' + function + '\ncapture_learning_status\n'
            if no_timeout:
                script = script.replace('timeout() {', 'command() { if [ "$1" = -v ] && [ "$2" = timeout ]; then return 1; fi; builtin command "$@"; }\ntimeout() {')
            env = dict(os.environ, STATUS_RC=str(status_rc))
            run = subprocess.run(['bash', '-c', script, 'test', str(root)], env=env,
                                 capture_output=True, text=True, timeout=5)
            fields = dict(line.split('=', 1) for line in state.read_text().splitlines())
            report_path = fields.get('LEARNING_STATUS_LOG')
            report = Path(report_path).read_text() if report_path != 'unavailable' else None
            pending = list(root.glob('*.tmp'))
            return run, fields, report, pending

    def test_scheduled_capture_records_independent_readiness(self):
        run, fields, report, pending = self.invoke()
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(fields['LEARNING_STATUS'], 'RECORDED')
        self.assertEqual(fields['LEARNING_LAST_CHECK'], 'test-time')
        self.assertIn('"labels":17', report)
        self.assertEqual(pending, [])

    def test_error_or_timeout_is_not_reported_as_fresh_data(self):
        for code in (1, 124):
            run, fields, report, pending = self.invoke(status_rc=code)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(fields['LEARNING_STATUS'], 'UNAVAILABLE')
            self.assertIsNone(report)
            self.assertEqual(pending, [])

    def test_absent_timeout_is_bounded_unavailable(self):
        run, fields, report, pending = self.invoke(no_timeout=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(fields['LEARNING_STATUS'], 'UNAVAILABLE')
        self.assertIsNone(report)
        self.assertEqual(pending, [])


if __name__ == '__main__':
    unittest.main()
