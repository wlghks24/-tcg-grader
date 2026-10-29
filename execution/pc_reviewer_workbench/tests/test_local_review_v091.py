from __future__ import annotations
import json,sys,tempfile,unittest
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import local_review as lr

class LocalReviewTests(unittest.TestCase):
 def setUp(self):
  temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.dir=Path(temp.name);self.src=self.dir/'source';self.src.mkdir();self.dst=self.dir/'report'
 def test_scans_proposes_and_never_edits_original(self):
  raw=b'# teh\ndef pending():\n    pass';(self.src/'feature.py').write_bytes(raw)
  report=lr.review(self.src,self.dst)
  self.assertEqual(raw,(self.src/'feature.py').read_bytes())
  self.assertEqual(b'# the\ndef pending():\n    pass\n',(self.dst/'candidates/feature.py').read_bytes())
  self.assertEqual('HOLD_STATIC_REVIEW_NOT_FUNCTIONAL_CERTIFICATION',report['status'])
  self.assertEqual('NOT_RUN',report['optional_tests']['state'])
  self.assertEqual(False,report['proposals'][0]['approved'])
  self.assertTrue((self.dst/'review.html').is_file())
  self.assertIn('\\ No newline at end of file',(next((self.dst/'patches').glob('*.patch'))).read_text())
 def test_syntax_json_dup_and_safe_html_escape(self):
  (self.src/'bad.py').write_text('def broken(:\n');(self.src/'x.json').write_text('{"x":1,"x":2}')
  (self.src/'<script>.py').write_text('pass')
  r=lr.review(self.src,self.dst)
  self.assertTrue({'PY_SYNTAX','JSON_DUPLICATE_KEY'} <= {x['rule'] for x in r['findings']})
  self.assertIn('&lt;script&gt;', (self.dst/'review.html').read_text())
  self.assertNotIn('<script>', (self.dst/'review.html').read_text())
 def test_stub_and_notimplemented_are_hints(self):
  r=lr.inspect(b'def stub():\n pass\ndef todo():\n raise NotImplementedError\n','a.py')
  self.assertTrue({'STUB','NOT_IMPLEMENTED'} <= {x['rule'] for x in r})
  self.assertTrue(all(x['state']=='REVIEW_REQUIRED' for x in r))
 def test_untrusted_code_not_executed(self):
  marker=self.dir/'executed'
  (self.src/'evil.py').write_text(f'from pathlib import Path\nPath({str(marker)!r}).write_text("unsafe")\n')
  lr.review(self.src,self.dst)
  self.assertFalse(marker.exists())
 def test_ruff_missing_and_tests_off(self):
  with mock.patch.object(lr.shutil,'which',return_value=None):
   self.assertEqual('MISSING',lr.ruff_check(self.src,True)['state'])
  with mock.patch.object(lr.subprocess,'run') as p:
   self.assertEqual('NOT_RUN',lr.run_tests(self.src,False)['state']);p.assert_not_called()
 def test_source_changed_mid_review_prevents_output(self):
  p=self.src/'a.py';p.write_text('x=1\n')
  with self.assertRaisesRegex(lr.ReviewHold,'original_content_changed'):
   lr.review(self.src,self.dst,callback=lambda msg:p.write_text('x=2\n'))
  self.assertFalse(self.dst.exists())
 def test_overlap_and_existing_report_hard_fail(self):
  with self.assertRaises(lr.ReviewHold):lr.review(self.src,self.src/'reports')
  self.dst.mkdir()
  with self.assertRaises(lr.ReviewHold):lr.review(self.src,self.dst)
 def test_symlinks_excluded(self):
  target=self.dir/'outside.py';target.write_text('secret=1\n')
  (self.src/'link.py').symlink_to(target)
  r=lr.review(self.src,self.dst);self.assertEqual(0,r['scanned_files']);self.assertTrue(r['skipped'])
 def test_unsupported_languages_not_certified(self):
  (self.src/'syntax.js').write_text('this is invalid javascript\n')
  r=lr.review(self.src,self.dst)
  self.assertEqual(1,r['scanned_files'])
  self.assertIn('Only Python/JSON built-in syntax checks',r['limitations'])
 def test_patch_is_only_a_candidate(self):
  (self.src/'a.py').write_text('# funtion\nx=1\n')
  r=lr.review(self.src,self.dst)
  self.assertEqual(1,len(r['proposals']))
  self.assertIn('NOT_RUN',r['proposals'][0]['behavioral_regression'])
  self.assertEqual((self.src/'a.py').read_text(),'# funtion\nx=1\n')
if __name__=='__main__':unittest.main()
