import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import full_repo_engine as g


def build_repo(root):
    root.mkdir()
    def git(*args):
        return subprocess.run(['git',*args],cwd=root,check=True,capture_output=True).stdout.strip()
    git('init','-q')
    git('config','user.email','test@invalid.example')
    git('config','user.name','Independent Reviewer')
    (root/'V031_start.py').write_text('def scan(value):\n    return value\n',encoding='utf-8')
    git('add','.');git('commit','-qm','V31 initial source')
    (root/'safety.py').write_text('def verify(row):\n    return bool(row.get("verified"))\n',encoding='utf-8')
    (root/'V100_product.js').write_text('function save(value) { return value; }\n',encoding='utf-8')
    (root/'tcg_updater.py').write_text('confirmed_samples = []\n',encoding='utf-8')
    git('add','.');git('commit','-qm','V100 add validation')
    return git

class GlobalReviewTests(unittest.TestCase):
    def test_entire_repository_two_passes_and_hold(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);repo=base/'repo';git=build_repo(repo)
            start=git('rev-parse','HEAD')
            response=g.run_global(repo,base/'reports')
            row=response['receipt'];gate=response['gate']
            self.assertEqual(2,row['passes'])
            self.assertTrue(row['sha256_and_bytes_equal'])
            self.assertEqual(7,row['matched_files'])
            self.assertEqual(2,gate['history_commits_read'])
            self.assertEqual(4,gate['tracked_files'])
            self.assertEqual(4,gate['source_files_analyzed'])
            self.assertEqual('HOLD',gate['approval'])
            self.assertFalse(row['historic_release_tests_completed'])
            self.assertIn('31',json.loads((base/'reports/pass_1/history.json').read_text())['history_hints'])
            self.assertIn('100',json.loads((base/'reports/pass_2/version_hints.json').read_text())['path_filename_hints'])
            findings=json.loads((base/'reports/pass_1/risk_review.json').read_text())['findings']
            self.assertTrue(any(x['rule']=='VERIFIED_TRUTHINESS' for x in findings))
            self.assertEqual(start,git('rev-parse','HEAD'))
            self.assertEqual(b'',git('status','--porcelain'))
            self.assertEqual((base/'reports/pass_1/gate.json').read_bytes(),
                             (base/'reports/pass_2/gate.json').read_bytes())
    def test_reject_reports_inside_git_and_existing_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);repo=base/'repo';build_repo(repo)
            with self.assertRaisesRegex(g.ReviewHold,'report_must_be_outside_git_checkout'):
                g.run_global(repo,repo/'reports')
            report=base/'reports';report.mkdir()
            (report/'personal_notes.txt').write_text('keep')
            with self.assertRaisesRegex(g.ReviewHold,'output_not_empty'):
                g.run_global(repo,report)
            self.assertEqual('keep',(report/'personal_notes.txt').read_text())
    def test_reject_dirty_worktree(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);repo=base/'repo';build_repo(repo)
            (repo/'safety.py').write_text('changed\n')
            with self.assertRaisesRegex(g.ReviewHold,'worktree_not_clean'):
                g.run_global(repo,base/'report')
            self.assertFalse((base/'report').exists())
    def test_suspicious_source_not_executed(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);repo=base/'repo';git=build_repo(repo)
            (repo/'dont_execute.py').write_text('raise RuntimeError("DO NOT EXECUTE")\n')
            git('add','.');git('commit','-qm','V101 harmless text scan')
            result=g.run_global(repo,base/'out')
            self.assertEqual('HOLD',result['gate']['approval'])
    def test_path_escapes_never_execute_external_shell(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);repo=base/'repo';git=build_repo(repo)
            (repo/'strange;touch_PWNED.py').write_text('pass\n')
            git('add','.');git('commit','-qm','V200 path with shell characters')
            result=g.run_global(repo,base/'out')
            self.assertEqual(5,result['gate']['tracked_files'])
            self.assertFalse((base/'PWNED').exists())
    def test_reject_duplicate_output_after_first_scan(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);repo=base/'repo';build_repo(repo)
            g.run_global(repo,base/'out')
            with self.assertRaisesRegex(g.ReviewHold,'output_not_empty'):
                g.run_global(repo,base/'out')
    def test_static_finding_not_automatically_approved(self):
        record,issues=g._analyze_source('test.py',b'x=bool(row.get("verified"))\n')
        self.assertEqual('PYTHON_AST_OK',record['syntax'])
        self.assertEqual('REVIEW_NOT_CONFIRMED_DEFECT',issues[0]['state'])
    def test_reject_report_symlink_to_repository(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);repo=base/'repo';build_repo(repo)
            link=base/'out'
            try: link.symlink_to(repo,target_is_directory=True)
            except (OSError,NotImplementedError):self.skipTest('No symlink permission')
            with self.assertRaisesRegex(g.ReviewHold,'report_must_be_outside_git_checkout'):
                g.run_global(repo,link)

if __name__=='__main__':unittest.main()
