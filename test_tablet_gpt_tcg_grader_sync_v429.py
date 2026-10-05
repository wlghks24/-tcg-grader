#!/usr/bin/env python3
import hashlib,json,subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
C=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V429.json"
D=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v429_delta.json"
R=ROOT/"TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v429.json"
def load(p): return json.loads(p.read_text(encoding="utf-8"))
class SyncV429(unittest.TestCase):
 def test_generation_digest_and_candidate_scope(self):
  c,d,r=load(C),load(D),load(R)
  raw=json.dumps(d["lessons"],ensure_ascii=False,sort_keys=True,separators=(",",":"))
  self.assertEqual(d["lesson_digest_sha256"],hashlib.sha256(raw.encode("utf-8")).hexdigest())
  self.assertEqual(d["lesson_digest_sha256"],r["delta_lesson_digest_sha256"])
  self.assertEqual([row["lesson_id"] for row in d["lessons"]],r["accepted_lesson_ids"])
  self.assertEqual(["tablet_autonomy_dashboard_v400.js"],c["candidate_sync"]["watched_paths"])
  self.assertTrue(c["candidate_sync"]["requires_exact_watched_path_match"])
  subprocess.run(["git","merge-base","--is-ancestor",c["candidate_sync"]["candidate_commit"],"HEAD"],check=True)
 def test_fail_closed_boundaries(self):
  d,r=load(D),load(R)
  self.assertFalse(d["share_policy"]["profit_guarantee"])
  self.assertFalse(d["share_policy"]["profit_guarantee"])
  self.assertFalse(d["share_policy"]["market_direction_prediction"])
  self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
  self.assertFalse(r["verification"]["physical_drive_readback_verified"])
if __name__=="__main__": unittest.main(verbosity=2)
