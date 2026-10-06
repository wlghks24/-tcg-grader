#!/usr/bin/env python3
import hashlib,json,subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
C=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V432.json"
D=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v432_delta.json"
R=ROOT/"TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v432.json"
def load(p): return json.loads(p.read_text(encoding="utf-8"))
class SyncV432(unittest.TestCase):
 def test_generation_digest_and_runtime_bundle(self):
  c,d,r=load(C),load(D),load(R); raw=json.dumps(d["lessons"],ensure_ascii=False,sort_keys=True,separators=(",",":"))
  self.assertEqual(d["lesson_digest_sha256"],hashlib.sha256(raw.encode()).hexdigest())
  self.assertEqual(d["lesson_digest_sha256"],r["delta_lesson_digest_sha256"])
  self.assertEqual([x["lesson_id"] for x in d["lessons"]],r["accepted_lesson_ids"])
  self.assertEqual([".github/workflows/tablet-gpt-tcg-grader-main-alignment.yml","auto_update_all.py","tablet_runtime_manifest.py"],c["candidate_sync"]["watched_paths"])
  subprocess.run(["git","merge-base","--is-ancestor",c["candidate_sync"]["candidate_commit"],"HEAD"],check=True)
 def test_multisource_safety_and_regression(self):
  for p in ("promoted_tcg_multisource_v432.py","test_promoted_tcg_multisource_v432.py"): self.assertTrue((ROOT/p).is_file())
  d,r=load(D),load(R); self.assertFalse(d["share_policy"]["profit_guarantee"]); self.assertFalse(d["share_policy"]["market_direction_prediction"])
  self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
if __name__=="__main__": unittest.main(verbosity=2)
