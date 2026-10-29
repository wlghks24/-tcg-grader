"""Two independent complete audit runs must match every report byte."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pc_auditor'))
from audit import AuditError, read_checkpoint
from double_review import _inventory, run_double_review


def git(repo, *args):
    return subprocess.run(['git', *args], cwd=repo, check=True,
                          capture_output=True).stdout.decode().strip()


class DoubleIndependentReviewTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='tcg-double-review-')
        self.addCleanup(temp.cleanup)
        self.tmp = Path(temp.name)
        self.repo = self.tmp / 'repo'
        self.repo.mkdir()
        git(self.repo, 'init', '-q')
        git(self.repo, 'config', 'user.email', 'audit@example.invalid')
        git(self.repo, 'config', 'user.name', 'Audit')
        (self.repo / 'V040_file.py').write_text(
            'def grading(row):\n    return bool(row.get("verified", False))\n', encoding='utf-8')
        (self.repo / 'V101_upcoming.py').write_text('def future():\n    return 2\n', encoding='utf-8')
        ledger = self.repo / 'execution' / 'evidence'
        ledger.mkdir(parents=True)
        (ledger / 'version_review_findings_v001_v205.json').write_text(json.dumps({
            'findings': [{'id': 'W001-F015', 'first_observed_version': 40,
                          'state': 'OPEN_SUCCESSOR_REQUIRED', 'severity': 'P0',
                          'summary': 'Review gated verified flag'}]}), encoding='utf-8')
        git(self.repo, 'add', '.')
        git(self.repo, 'commit', '-qm', 'V40 V101 historical hints only')
        self.out = self.tmp / 'separate_reports'
        self.head = git(self.repo, 'rev-parse', 'HEAD')

    def pass_dir(self, name):
        return self.out / name / f'HEAD_{self.head[:12]}_V1-V205'

    def test_two_full_runs_equal_raw_files_and_original_unmodified(self):
        receipt = run_double_review(self.repo, self.out, latest=205)
        self.assertEqual(2, receipt['pass_count'])
        self.assertTrue(receipt['independent_report_bytes_and_sha256_equal'])
        self.assertFalse(receipt['next_window_allowed'])
        self.assertFalse(receipt['release_or_patch_approved'])
        self.assertEqual(receipt, read_checkpoint(self.out/'double_review_receipt.json'))
        self.assertEqual(_inventory(self.pass_dir('first_pass')),
                         _inventory(self.pass_dir('second_pass')))
        self.assertTrue((self.pass_dir('first_pass')/'V0001_V0100.json').exists())
        self.assertFalse((self.pass_dir('second_pass')/'V0101_V0200.json').exists())
        self.assertEqual(self.head, git(self.repo, 'rev-parse', 'HEAD'))
        self.assertEqual('', git(self.repo, 'status', '--porcelain'))

    def test_repeat_entire_program_rereviews_and_preserves_receipt(self):
        a = run_double_review(self.repo, self.out, latest=205)
        b = run_double_review(self.repo, self.out, latest=205)
        self.assertEqual(a, b)
        self.assertEqual(a, read_checkpoint(self.out/'double_review_receipt.json'))

    def test_tampered_second_pass_must_fail_even_with_valid_first(self):
        run_double_review(self.repo, self.out, latest=205)
        p = self.pass_dir('second_pass')/'code_map.json'
        p.write_text('{"forged": true}', encoding='utf-8')
        with self.assertRaises(AuditError):
            run_double_review(self.repo, self.out, latest=205)
        self.assertFalse((self.pass_dir('second_pass')/'V0101_V0200.json').exists())

    def test_direct_independent_inventory_rejects_modified_copy(self):
        run_double_review(self.repo, self.out, latest=205)
        p = self.pass_dir('second_pass')/'현재구간_보완검증_상태.md'
        p.write_text(p.read_text(encoding='utf-8') + 'forged\n', encoding='utf-8')
        self.assertNotEqual(_inventory(self.pass_dir('first_pass')),
                            _inventory(self.pass_dir('second_pass')))
        with self.assertRaises(AuditError):
            run_double_review(self.repo, self.out, latest=205)

    def test_forged_double_receipt_even_rehashed_cannot_pass(self):
        from audit import digest, atomic_json
        run_double_review(self.repo, self.out, latest=205)
        p = self.out/'double_review_receipt.json'
        receipt = read_checkpoint(p)
        receipt['next_window_allowed'] = True
        receipt['receipt_sha256'] = digest({k:v for k,v in receipt.items()
                                           if k!='receipt_sha256'})
        atomic_json(p, receipt)
        with self.assertRaisesRegex(AuditError, 'double_review_existing_receipt_disagrees'):
            run_double_review(self.repo, self.out, latest=205)

    def test_second_pass_status_disagreement_holds(self):
        from double_review import run_strict_cycle as original
        state = {'count': 0}
        def different(*args, **kwargs):
            x = original(*args, **kwargs)
            state['count'] += 1
            return {**x, 'unresolved_findings': 1234} if state['count'] == 2 else x
        with patch('double_review.run_strict_cycle', side_effect=different):
            with self.assertRaisesRegex(AuditError, 'double_review_independent_status_disagrees'):
                run_double_review(self.repo, self.out, latest=205)
        self.assertFalse((self.out/'double_review_receipt.json').exists())

    def test_second_pass_git_head_drift_holds(self):
        from double_review import run_strict_cycle as original
        count = {'value': 0}
        def mutating(*args, **kwargs):
            x = original(*args, **kwargs)
            count['value'] += 1
            if count['value'] == 1:
                (self.repo/'new_file.txt').write_text('new local candidate',encoding='utf-8')
                git(self.repo, 'add', '.')
                git(self.repo, 'commit', '-qm', 'disallowed head changed mid scan')
            return x
        with patch('double_review.run_strict_cycle', side_effect=mutating):
            with self.assertRaisesRegex(AuditError, 'double_review_git_head_changed_between_passes'):
                run_double_review(self.repo, self.out, latest=205)
        self.assertFalse((self.out/'double_review_receipt.json').exists())

    def test_symlink_output_refused(self):
        link = self.tmp/'link'
        try: link.symlink_to(self.out, target_is_directory=True)
        except OSError: self.skipTest('symlink unavailable')
        with self.assertRaisesRegex(AuditError, 'double_review_output_symlink'):
            run_double_review(self.repo, link, latest=205)

    def test_output_inside_or_above_git_refused(self):
        for x in (self.repo/'reports', self.tmp):
            with self.subTest(x=x), self.assertRaisesRegex(AuditError, 'double_review_output_must_not_overlap'):
                run_double_review(self.repo, x, latest=205)


if __name__ == '__main__': unittest.main()
