"""V971: exercise the real scheduler status branch with isolated Git/updater stubs.

No Android device, remote GitHub fetch, photo access or checkout is performed.
"""
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class TabletUpdateStatusV971Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script = (ROOT / 'TABLET_SCHEDULED_UPDATE.sh').read_text(encoding='utf-8')
        start = script.index('run_update() {')
        end = script.index('\nstop_verified_loop_process() {', start)
        cls.update_function = script[start:end]

    def run_case(self, branch='main', dirty=False, staged=False, updater_exit=0):
        with tempfile.TemporaryDirectory(prefix='tcg-v971-scheduler-') as td:
            root = Path(td)
            logs = root / 'logs'
            logs.mkdir()
            (root / 'ANDROID_UPDATE_AND_START.sh').write_text(
                '#!/usr/bin/env bash\nexit ' + str(updater_exit) + '\n',
                encoding='utf-8')
            harness = '\n'.join([
                'set +e',
                'ROOT=' + shlex.quote(str(root)),
                'LOG_DIR=' + shlex.quote(str(logs)),
                'OFFICIAL_HTTPS=https://example.invalid/never-fetched',
                'TEST_BRANCH=' + shlex.quote(branch),
                'TEST_DIRTY=' + ('1' if dirty else '0'),
                'TEST_STAGED=' + ('1' if staged else '0'),
                'acquire_lock() { :; }',
                'now() { printf "fixture-time\\n"; }',
                "sha() { if [ \"$1\" = HEAD ]; then printf '%040d\\n' 1; else printf '%040d\\n' 2; fi; }",
                "write_status() { printf 'STATE:%s\\n' \"$1\"; }",
                """git() {
  case "$1" in
    fetch) return 0 ;;
    symbolic-ref)
      if [ "$TEST_BRANCH" = DETACHED ]; then return 1; fi
      printf '%s\n' "$TEST_BRANCH"
      return 0 ;;
    diff) if [ "$TEST_STAGED" = 1 ]; then return 1; fi; return 0 ;;
    status)
      if [ "$TEST_DIRTY" = 1 ]; then printf ' M learning_store.json\n'; fi
      return 0 ;;
    *) printf 'unexpected git call: %s\n' "$*" >&2; return 77 ;;
  esac
}""",
                self.update_function,
                'run_update',
                '',
            ])
            result = subprocess.run(
                ['bash', '-c', harness], cwd=root,
                capture_output=True, text=True, timeout=15, check=False)
            return result.returncode, result.stdout + result.stderr

    def assert_state(self, branch, dirty, staged, expected, rc=0, updater_exit=0):
        code, output = self.run_case(branch, dirty, staged, updater_exit)
        self.assertEqual(code, rc, output)
        self.assertIn('STATE:' + expected, output)
        return output

    def test_detached_with_runtime_learning_edits_is_not_dirty_code_hold(self):
        out = self.assert_state('DETACHED', True, False, 'DETACHED_HEAD_HOLD')
        self.assertNotIn('STATE:LOCAL_CHANGES_HOLD', out)
        self.assertIn('detached HEAD', out)

    def test_detached_even_when_clean_is_branch_hold(self):
        self.assert_state('DETACHED', False, False, 'DETACHED_HEAD_HOLD')

    def test_non_main_branch_keeps_candidate_untouched(self):
        self.assert_state('tablet-v927-preserved-20261108', True, False,
                          'NON_MAIN_BRANCH_HOLD')

    def test_main_staged_changes_take_precedence_over_runtime_edits(self):
        self.assert_state('main', True, True, 'STAGED_CHANGES_HOLD')

    def test_main_dirty_unstaged_keeps_existing_hold_behavior(self):
        self.assert_state('main', True, False, 'LOCAL_CHANGES_HOLD')

    def test_main_clean_unexplained_skip_is_not_success(self):
        self.assert_state('main', False, False, 'POSTCHECK_MISMATCH', rc=4)

    def test_updater_failure_remains_failure_not_branch_hold(self):
        self.assert_state('DETACHED', True, False, 'UPDATE_FAILED',
                          rc=9, updater_exit=9)

    def test_no_forced_ref_edit_checkout_or_device_reset(self):
        for forbidden in ('git reset --hard', 'git branch -f', 'git switch',
                          'git checkout', 'git update-ref', 'rm -rf'):
            self.assertNotIn(forbidden, self.update_function)


if __name__ == '__main__':
    unittest.main()
