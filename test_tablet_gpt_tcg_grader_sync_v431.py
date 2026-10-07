#!/usr/bin/env python3
import hashlib,json,subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
C=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V431.json"
D=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v431_delta.json"
R=ROOT/"TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v431.json"
def load(p): return json.loads(p.read_text(encoding="utf-8"))
class SyncV431(unittest.TestCase):
 def test_generation_digest_and_exact_mainline_bundle(self):
  c,d,r=load(C),load(D),load(R)
  raw=json.dumps(d["lessons"],ensure_ascii=False,sort_keys=True,separators=(",",":"))
  self.assertEqual(d["lesson_digest_sha256"],hashlib.sha256(raw.encode("utf-8")).hexdigest())
  self.assertEqual(d["lesson_digest_sha256"],r["delta_lesson_digest_sha256"])
  self.assertEqual([row["lesson_id"] for row in d["lessons"]],r["accepted_lesson_ids"])
  self.assertEqual("b59eb45ab9b5596f0fad76b9b3e85a5e49e5e466",d["source_main_sha"])
  self.assertEqual(["feature_category_nav.js","tablet_autonomy_dashboard_v400.js","tcg_game_registry.py","ui_app_shell_v272.css"],c["candidate_sync"]["watched_paths"])
  subprocess.run(["git","merge-base","--is-ancestor",c["candidate_sync"]["candidate_commit"],"HEAD"],check=True)
 def test_prior_regressions_and_safety_boundaries(self):
  d,r=load(D),load(R)
  for p in ("test_tablet_recording_ui_v428.py","test_tablet_registry_market_lens_v429.py","test_tablet_category_focus_v430.py","test_tcg_game_registry.py"):
   self.assertTrue((ROOT/p).is_file())
  self.assertFalse(d["share_policy"]["runtime_ui_source_auto_rewrite"])
  self.assertFalse(d["share_policy"]["profit_guarantee"])
  self.assertFalse(d["share_policy"]["market_direction_prediction"])
  self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
  self.assertFalse(r["verification"]["physical_drive_readback_verified"])
if __name__=="__main__": unittest.main(verbosity=2)
