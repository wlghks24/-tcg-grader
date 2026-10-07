#!/usr/bin/env python3
import hashlib,json,subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
C=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V434.json";D=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v434_delta.json";R=ROOT/"TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v434.json"
def load(p):return json.loads(p.read_text(encoding="utf-8"))
class SyncV434(unittest.TestCase):
 def test_digest_candidate_and_runtime(self):
  c,d,r=load(C),load(D),load(R);raw=json.dumps(d["lessons"],ensure_ascii=False,sort_keys=True,separators=(",",":"))
  self.assertEqual(d["lesson_digest_sha256"],hashlib.sha256(raw.encode()).hexdigest());self.assertEqual(d["lesson_digest_sha256"],r["delta_lesson_digest_sha256"])
  self.assertEqual(["tablet_runtime_manifest.py"],c["candidate_sync"]["watched_paths"]);subprocess.run(["git","merge-base","--is-ancestor",c["candidate_sync"]["candidate_commit"],"HEAD"],check=True)
 def test_market_context_is_fail_closed(self):
  self.assertTrue((ROOT/"market_price_context_v433.py").is_file());self.assertTrue((ROOT/"test_market_price_context_v433.py").is_file());r=load(R);self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
if __name__=="__main__":unittest.main(verbosity=2)
