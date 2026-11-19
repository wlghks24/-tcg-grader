"""Deterministic log-only regressions for Main Alignment CI bottleneck diagnosis."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from execution.diagnostics.analyze_alignment_job_log import analyze_log, main


def line(time, content):
    return f'2026-11-19T12:{time}Z {content}'


class AlignmentJobLogAnalysisTests(unittest.TestCase):
    def sample(self):
        return '\n'.join([
            line('00:00.0000000', '##[group]Run set -euo pipefail'),
            line('00:10.0000000', 'test_previous (tests.V369.test_previous) ... ok'),
            line('08:24.7000000', 'test_exact_candidate_scope (tests.V369.test_exact_candidate_scope) ... ok'),
            line('10:00.0000000', '##[error]The operation was canceled.'),
        ])

    def test_cancelled_job_is_not_misreported_as_success(self):
        result = analyze_log(self.sample())
        self.assertEqual('cancelled', result['status'])
        self.assertEqual(600.0, result['step_to_cancellation_seconds'])
        self.assertEqual(2, result['completed_test_results'])
        self.assertEqual(0, result['failed_test_results'])

    def test_long_gap_is_explicitly_not_called_method_duration(self):
        result = analyze_log(self.sample())
        self.assertEqual(494.7, result['largest_completion_gaps'][0]['completion_gap_seconds'])
        self.assertIn('not direct method runtime', result['interpretation'])

    def test_failed_test_is_not_accepted(self):
        data = '\n'.join([line('00:01.0', 'test_one (tests.Case.test_one) ... ok'),
                          line('00:02.0', 'test_two (tests.Case.test_two) ... FAIL')])
        result = analyze_log(data)
        self.assertEqual('test_failure', result['status'])
        self.assertEqual(1, result['failed_test_results'])

    def test_no_cancel_marker_does_not_claim_complete_pass(self):
        result = analyze_log(line('01:00.0', 'test_one (tests.Case.test_one) ... ok'))
        self.assertEqual('incomplete_or_unknown', result['status'])

    def test_bom_and_untrusted_lines_do_not_pollute_output(self):
        log = '\ufeff' + line('00:00.0', '##[group]Run set -euo pipefail') + '\n' + 'secret=DO_NOT_ECHO'
        result = analyze_log(log)
        self.assertEqual(0, result['completed_test_results'])
        self.assertNotIn('DO_NOT_ECHO', json.dumps(result))

    def test_negative_time_gap_not_included(self):
        log = '\n'.join([line('09:00.0', 'test_a (tests.Case.test_a) ... ok'),
                         line('08:00.0', 'test_b (tests.Case.test_b) ... ok')])
        self.assertEqual([], analyze_log(log)['largest_completion_gaps'])

    def test_top_limit_rejected(self):
        for value in (0, 51):
            with self.assertRaises(ValueError):
                analyze_log(self.sample(), top=value)

    def test_cli_reads_local_file_without_editing(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'job.log'
            contents = self.sample()
            path.write_text(contents, encoding='utf-8')
            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(0, main([str(path), '--top', '1']))
            parsed = json.loads(out.getvalue())
            self.assertEqual('cancelled', parsed['status'])
            self.assertEqual(1, len(parsed['largest_completion_gaps']))
            self.assertEqual(contents, path.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
