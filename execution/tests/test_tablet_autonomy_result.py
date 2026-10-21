"""Behavioral regression tests; fixtures are never operational training evidence."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("autonomy_result", ROOT / "execution/tablet_autonomy_result.py")
classifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(classifier)
HOLD = "V400_UPSTREAM_HOLD"


def result():
    return {"controller_version": "v400", "v400_status": HOLD,
            "execution": {"status": HOLD, "executed": False, "git_write": False,
                          "source_code_modified": False},
            "v400_autonomous_gate": {"status": HOLD, "allow_execution": False}}


class ResultTests(unittest.TestCase):
    def test_valid_hold(self):
        self.assertTrue(classifier.is_policy_hold(2, result(), {HOLD}))

    def test_exit_code_alone_never_proves_hold(self):
        for rc in (0, 1, 3, 130):
            self.assertFalse(classifier.is_policy_hold(rc, result(), {HOLD}))
        self.assertFalse(classifier.is_policy_hold(2, {}, {HOLD}))

    def test_inconsistent_or_missing_fields_remain_failed(self):
        paths = [("controller_version",), ("v400_status",), ("execution",),
                 ("v400_autonomous_gate",), ("execution", "status"),
                 ("execution", "executed"), ("execution", "git_write"),
                 ("execution", "source_code_modified"),
                 ("v400_autonomous_gate", "status"),
                 ("v400_autonomous_gate", "allow_execution")]
        for path in paths:
            for value in (None, True, 0, 1, "PLAN_ONLY", [], {}):
                row = result()
                target = row
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                with self.subTest(path=path, value=value):
                    self.assertFalse(classifier.is_policy_hold(2, row, {HOLD}))
        self.assertFalse(classifier.is_policy_hold(2, result(), set()))

    def test_concurrent_hold_is_explicit_exception(self):
        row = result()
        row["v400_status"] = row["execution"]["status"] = "V400_CONCURRENT_AUTONOMY_HOLD"
        del row["v400_autonomous_gate"]
        self.assertTrue(classifier.is_policy_hold(2, row, {row["v400_status"]}))
        row["execution"]["executed"] = True
        self.assertFalse(classifier.is_policy_hold(2, row, {row["v400_status"]}))

    def test_executed_proposal_is_not_non_execution_hold(self):
        row = result()
        row["execution"]["proposals_executed"] = True
        self.assertFalse(classifier.is_policy_hold(2, row, {HOLD}))

    def test_only_final_line_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.log"
            path.write_text('precheck\n' + json.dumps(result()) + '\n\n')
            self.assertEqual(classifier.read_final_result(path), result())
            for suffix in ('Traceback: error\n', '[]\n', '{"x":1,"x":2}\n', '{"x":NaN}\n'):
                path.write_text(json.dumps(result()) + '\n' + suffix)
                with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                    classifier.read_final_result(path)

    def test_log_limits_symlink_and_invalid_encoding(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.log"
            path.write_bytes(b'x' * (classifier.MAX_FINAL_LINE_BYTES + 2))
            with self.assertRaises(ValueError):
                classifier.read_final_result(path)
            path.write_bytes(b'\xff')
            with self.assertRaises(UnicodeError):
                classifier.read_final_result(path)
            link = Path(tmp) / "link"
            link.symlink_to(path)
            with self.assertRaises(ValueError):
                classifier.read_final_result(link)

    def test_large_prefix_does_not_require_full_log_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.log"
            path.write_bytes(b'x' * (classifier.MAX_FINAL_LINE_BYTES + 100) + b'\n' + json.dumps(result()).encode())
            self.assertEqual(classifier.read_final_result(path), result())

    def test_cli_uses_canonical_controller_statuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.log"
            path.write_text(json.dumps(result()) + '\n')
            cmd = ['python', str(ROOT / 'execution/tablet_autonomy_result.py'), '--log', str(path), '--exit-code', '2']
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
            row = result()
            row['v400_status'] = row['execution']['status'] = row['v400_autonomous_gate']['status'] = 'UNREGISTERED_HOLD'
            path.write_text(json.dumps(row) + '\n')
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 1)

    def test_scheduler_preserves_exit_code_and_separates_hold_from_crash(self):
        source = (ROOT / 'TABLET_SCHEDULED_UPDATE.sh').read_text()
        function = source[source.index('run_autonomy_cycle() {'):source.index('\nwrite_boot_heartbeat()')]
        with tempfile.TemporaryDirectory() as tmp:
            for rc, final, expected in ((2, 'hold', 'HOLD'), (2, 'crash', 'FAILED'), (1, 'hold', 'FAILED'), (0, 'hold', 'OK')):
                script = '''set -euo pipefail
ROOT="$1"; LOG_DIR="$2"; rc_fixture="$3"; final_fixture="$4"
now() { printf test; }
write_autonomy_status() { printf '%s' "$1" > "$LOG_DIR/status"; }
python() {
  case "$1" in
    *tablet_autonomy_result.py) command python "$@" ;;
    *tablet_runtime_manifest.py) return 0 ;;
    *)
      if [ "${2:-}" = "--self-test" ]; then return 0; fi
      if [ "$final_fixture" = hold ]; then cat "$LOG_DIR/result.json"; else printf 'argument error\\n'; fi
      return "$rc_fixture" ;;
  esac
}
''' + function + '\nrun_autonomy_cycle\n'
                Path(tmp, 'result.json').write_text(json.dumps(result()) + '\n')
                run = subprocess.run(['bash', '-c', script, 'test', str(ROOT), tmp, str(rc), final], capture_output=True)
                with self.subTest(rc=rc, final=final):
                    self.assertEqual(run.returncode, rc, run.stderr.decode())
                    self.assertEqual(Path(tmp, 'status').read_text(), expected)


if __name__ == '__main__':
    unittest.main()
