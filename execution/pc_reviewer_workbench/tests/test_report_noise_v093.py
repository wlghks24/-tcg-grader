"""Regressions derived from real TCG PC audit report: 70 EOF-only + 6 intentional stubs."""
import unittest,sys,tempfile,json
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
import local_review as lr
class RealReportRegression(unittest.TestCase):
 def test_protocol_and_http_noop_are_informational(self):
  src=b'from typing import Protocol\nfrom http.server import BaseHTTPRequestHandler\nclass Sandbox(Protocol):\n def preflight(self): ...\nclass Handler(BaseHTTPRequestHandler):\n def log_message(self,*args):pass\n'
  findings=lr.inspect(src,'app.py')
  self.assertEqual(2,sum(x['rule']=='INTENTIONAL_STUB' for x in findings))
  self.assertEqual(0,sum(x['state']=='REVIEW_REQUIRED' for x in findings))
 def test_real_unimplemented_keeps_hold(self):
  findings=lr.inspect(b'def todo():\n pass\ndef nope():\n raise NotImplementedError\n','app.py')
  self.assertEqual({'STUB','NOT_IMPLEMENTED'},{x['rule'] for x in findings})
  self.assertTrue(all(x['state']=='REVIEW_REQUIRED' for x in findings))
 def test_mock_helpers_are_not_actual_unimplemented_features(self):
  t=b'class Response:\n def __exit__(self,*args):pass\n'
  self.assertEqual('INTENTIONAL_STUB',lr.inspect(t,'execution/tests/test_fetch.py')[0]['rule'])
  t=b'def verify():\n class SafeRecovery:\n  def __init__(self,*args):pass\n'
  self.assertEqual('INTENTIONAL_STUB',lr.inspect(t,'verify_all_legacy_v99.py')[0]['rule'])
 def test_nested_with_test_double_is_intentional(self):
  t=b'def verify():\n with object():\n  class SafeRecovery:\n   def __init__(self,*args):pass\n'
  self.assertEqual('INTENTIONAL_STUB',lr.inspect(t,'verify_all_legacy_v99.py')[0]['rule'])
 def test_final_newline_info_and_no_cosmetic_patch(self):
  f=lr.inspect(b'x=1','app.py')
  self.assertEqual('INFORMATIONAL_FORMAT_ONLY',f[0]['state'])
  self.assertIsNone(lr.candidate(b'x=1','app.py',f))
 def test_integrity_manifest_blocks_even_comment_typo_candidate(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);src=root/'src';src.mkdir();out=root/'out'
   original=b'# teh\nx=1\n';(src/'feature.py').write_bytes(original)
   (src/'integrity_manifest.json').write_text(json.dumps({'files':{'feature.py':{'sha256':lr.sha(original),'bytes':len(original)}}}))
   report=lr.review(src,out)
   self.assertEqual(0,len(report['proposals']))
   self.assertEqual('INTEGRITY_MANIFEST_PROTECTED',report['blocked_patches'][0]['reason'])
   self.assertEqual(original,(src/'feature.py').read_bytes())
 def test_bad_manifest_fails_closed(self):
  with tempfile.TemporaryDirectory() as td:
   src=Path(td)/'src';src.mkdir();(src/'integrity_manifest.json').write_text('NOT_JSON')
   with self.assertRaisesRegex(lr.ReviewHold,'invalid_integrity_manifest'):
    lr.review(src,Path(td)/'out')
if __name__=='__main__':unittest.main()
