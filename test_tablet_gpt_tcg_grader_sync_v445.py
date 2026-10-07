#!/usr/bin/env python3
import hashlib,json,subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
C=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V445.json";D=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v445_delta.json";R=ROOT/"TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v445.json"
def load(p):return json.loads(p.read_text(encoding="utf-8"))
class SyncV445(unittest.TestCase):
 def test_digest_candidate_and_exact_scope(self):
  c,d,r=load(C),load(D),load(R);raw=json.dumps(d["lessons"],ensure_ascii=False,sort_keys=True,separators=(",",":"))
  self.assertEqual(d["lesson_digest_sha256"],hashlib.sha256(raw.encode()).hexdigest());self.assertEqual(d["lesson_digest_sha256"],r["delta_lesson_digest_sha256"])
  self.assertEqual([".github/workflows/gpt-tcg-drive-package.yml",".github/workflows/tcg-static-data-refresh.yml"],c["candidate_sync"]["watched_paths"]);subprocess.run(["git","merge-base","--is-ancestor",c["candidate_sync"]["candidate_commit"],"HEAD"],check=True)
 def test_quota_preflight_is_bound_without_weakening_delivery(self):
  drive=(ROOT/".github/workflows/gpt-tcg-drive-package.yml").read_text(encoding="utf-8");static=(ROOT/".github/workflows/tcg-static-data-refresh.yml").read_text(encoding="utf-8")
  for text in (drive,static):self.assertIn("github_free_usage_guard_v444.py --live --require-nonessential",text)
  self.assertIn("retention-days: 3",drive);self.assertIn("include-hidden-files: true",drive);self.assertIn("if-no-files-found: error",drive)
  self.assertFalse(load(R)["verification"]["physical_tablet_runtime_verified"]);self.assertFalse(load(R)["verification"]["physical_drive_readback_verified"])
if __name__=="__main__":unittest.main(verbosity=2)
