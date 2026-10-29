"""Working-tree review and install-copy regressions. No project code execution."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'pc_auditor'))
sys.path.insert(0,str(BASE))
import local_review
import install_local


class LocalReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.source=self.root/'source';self.source.mkdir()
        self.out=self.root/'reports'

    def test_real_working_copy_scan_candidates_and_original_unchanged(self):
        raw=b'# teh\ndef pending():\n    pass'
        (self.source/'x.py').write_bytes(raw)
        result=local_review.review(self.source,self.out)
        rules={x['rule'] for x in result['findings']}
        self.assertTrue({'STUB','COMMENT_TYPO','FINAL_NEWLINE'} <= rules)
        self.assertEqual(raw,(self.source/'x.py').read_bytes())
        self.assertEqual(raw.replace(b'teh',b'the')+b'\n',(self.out/'candidates/x.py').read_bytes())
        self.assertFalse(any(x['rule']=='FINAL_NEWLINE' for x in result['proposals'][0]['remaining_findings']))
        self.assertIn('No newline at end of file',next((self.out/'patches').iterdir()).read_text())
        self.assertEqual('NOT_RUN',result['project_tests']['status'])
        self.assertTrue((self.out/'review.html').is_file())

    def test_syntax_error_and_json_duplicate_are_reported(self):
        (self.source/'bad.py').write_text('def x(:\n')
        (self.source/'data.json').write_text('{"x":1,"x":2}')
        result=local_review.review(self.source,self.out)
        self.assertTrue({'PY_SYNTAX','JSON_DUPLICATE_KEY'} <= {x['rule'] for x in result['findings']})
        self.assertFalse(any(x['path']=='bad.py' for x in result['proposals']))

    def test_source_is_not_imported_or_executed(self):
        marker=self.root/'executed'
        (self.source/'x.py').write_text('from pathlib import Path\nPath('+repr(str(marker))+').touch()\n')
        local_review.review(self.source,self.out)
        self.assertFalse(marker.exists())

    def test_no_git_requirement_and_unsupported_languages_not_certified(self):
        (self.source/'x.ts').write_text('invalid typescript\n')
        result=local_review.review(self.source,self.out)
        self.assertIn('HOLD',result['status'])
        self.assertFalse((self.source/'.git').exists())
        self.assertTrue(any(x['reason']=='built_in_syntax_checker_unavailable' for x in result['coverage_gaps']))

    def test_overlap_and_existing_output_refused(self):
        with self.assertRaises(ValueError): local_review.review(self.source,self.source/'report')
        self.out.mkdir()
        with self.assertRaises(ValueError): local_review.review(self.source,self.out)

    def test_source_mutation_during_scan_prevents_report_publish(self):
        p=self.source/'x.py';p.write_text('x=1\n')
        with self.assertRaisesRegex(ValueError,'원본 변경'):
            local_review.review(self.source,self.out,callback=lambda _:p.write_text('x=2\n'))
        self.assertFalse(self.out.exists())

    def test_symlink_excluded_and_stop_honored(self):
        (self.root/'secret.py').write_text('secret=1\n')
        (self.source/'link.py').symlink_to(self.root/'secret.py')
        result=local_review.review(self.source,self.out)
        self.assertEqual(0,result['files']);self.assertTrue(result['coverage_gaps'])
        event=threading.Event();event.set()
        with self.assertRaises(ValueError):local_review.review(self.source,self.root/'stopped',stop=event)

    def test_ruff_absence_is_missing_not_pass(self):
        with mock.patch.object(local_review.shutil,'which',return_value=None):
            self.assertEqual('MISSING',local_review._ruff(self.root,True)['status'])
        with mock.patch.object(local_review.subprocess,'run') as run:
            self.assertEqual('NOT_REQUESTED',local_review._ruff(self.root,False)['status'])
            run.assert_not_called()

    def test_html_escapes_untrusted_names(self):
        (self.source/'<img>.py').write_text('pass')
        local_review.review(self.source,self.out)
        report=(self.out/'review.html').read_text()
        self.assertIn('&lt;img&gt;',report);self.assertNotIn('<img>',report)

    def test_installer_verifies_bytes_and_preserves_package(self):
        raw=b'x=1\n';(self.source/'x.py').write_bytes(raw)
        m={'files':{'x.py':{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}}}
        (self.source/'SHA256SUMS.json').write_text(json.dumps(m))
        install_local.install(self.source,self.out)
        self.assertEqual(raw,(self.out/'x.py').read_bytes())
        with self.assertRaises(ValueError):install_local.install(self.source,self.out)
        (self.source/'x.py').write_text('tampered')
        with self.assertRaisesRegex(ValueError,'checksum'):install_local.install(self.source,self.root/'badinstall')
        self.assertFalse((self.root/'badinstall').exists())

    def test_installer_rejects_traversal(self):
        (self.source/'SHA256SUMS.json').write_text(json.dumps({'files':{'../x':{}}}))
        with self.assertRaisesRegex(ValueError,'unsafe'):install_local.install(self.source,self.out)


class AdditionalSyntaxTests(unittest.TestCase):
    def test_invalid_top_level_return_is_compile_error(self):
        result=local_review.inspect(b'return 1\n', 'x.py')
        self.assertEqual('PY_SYNTAX', result[0]['rule'])

    def test_string_typo_is_not_modified(self):
        result=local_review.inspect(b'x="teh"\n', 'x.py')
        self.assertFalse(any(x['rule']=='COMMENT_TYPO' for x in result))


class TestRunnerTests(unittest.TestCase):
    def test_disabled_test_runner_cannot_execute_source(self):
        with mock.patch.object(local_review.subprocess,'run') as run:
            self.assertEqual('NOT_RUN',local_review.run_tests(Path('.'),False)['status'])
            run.assert_not_called()

    def test_zero_tests_never_becomes_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'tests').mkdir()
            result=local_review.run_tests(root,True)
            self.assertEqual('FAIL_OR_UNVERIFIED',result['status'])
            self.assertEqual(0,result['tests'])

    def test_opt_in_runs_real_unittest_in_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'tests').mkdir()
            (root/'tests/test_math.py').write_text('import unittest\nclass TestMath(unittest.TestCase):\n def test_sum(self): self.assertEqual(2,1+1)\n')
            result=local_review.run_tests(root,True)
            self.assertEqual('PASS',result['status'])
            self.assertEqual(1,result['tests'])
            self.assertFalse(result['sandboxed'])
