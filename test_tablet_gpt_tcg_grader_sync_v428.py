#!/usr/bin/env python3
import hashlib,json,unittest
from pathlib import Path
from sync_v376_successor_test_support import assert_v428_successor
ROOT=Path(__file__).resolve().parent
C=ROOT/'TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V428.json';D=ROOT/'TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v428_delta.json';R=ROOT/'TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v428.json'
def load(p): return json.loads(p.read_text(encoding='utf-8'))
class SyncV428(unittest.TestCase):
 def test_generation(self):
  c,d,r=load(C),load(D),load(R); raw=json.dumps(d['lessons'],ensure_ascii=False,sort_keys=True,separators=(',',':'))
  self.assertEqual(d['lesson_digest_sha256'],hashlib.sha256(raw.encode()).hexdigest());self.assertEqual(d['lesson_digest_sha256'],r['delta_lesson_digest_sha256']);self.assertEqual((121,1,122),(c['prior_required_lesson_count'],c['delta_required_lesson_count'],c['current_required_lesson_count']));assert_v428_successor(self)
 def test_safety(self):
  d,r=load(D),load(R);self.assertFalse(d['share_policy']['runtime_logic_changed']);self.assertFalse(r['verification']['physical_tablet_runtime_verified'])
if __name__=='__main__':unittest.main(verbosity=2)
