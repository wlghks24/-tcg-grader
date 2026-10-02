import hashlib
import json
import unittest
from pathlib import Path
import tablet_autonomous_evolution_v381 as autonomy
from sync_v376_successor_test_support import assert_v381_successor

ROOT=Path(__file__).resolve().parent
CONTRACT=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V381.json"
DELTA=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v381_delta.json"
RECEIPT=ROOT/"TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v381.json"
BASE="108adece2681783ddb46f6911da345bdb938c0cd"
CANDIDATE="f6e9557c4d528c0282b7cefebcee2609700ab5cd"
LESSON="TABLET-GPT-DRIFT-AWARE-VERIFIED-OUTCOME-GOVERNANCE-V381"

def load(path): return json.loads(path.read_text(encoding="utf-8"))
def digest(value):
 raw=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))
 return hashlib.sha256(raw.encode("utf-8")).hexdigest()

class TabletGptTcgGraderSyncV381Tests(unittest.TestCase):
 def test_binding_digest_counts_and_physical_boundary(self):
  c,d,r=load(CONTRACT),load(DELTA),load(RECEIPT)
  self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V380.json",c["prior_contract"])
  self.assertEqual(BASE,d["source_main_sha"]); self.assertEqual(BASE,r["source_main_sha"])
  self.assertEqual(d["lesson_digest_sha256"],digest(d["lessons"]))
  self.assertEqual(d["lesson_digest_sha256"],r["delta_lesson_digest_sha256"])
  self.assertEqual([LESSON],r["accepted_lesson_ids"])
  self.assertEqual(73,c["prior_required_lesson_count"]); self.assertEqual(74,c["current_required_lesson_count"])
  self.assertEqual(370,c["current_required_merge_prs"][-1]); self.assertEqual("SYNCED_VERIFIED",r["status"])
  self.assertFalse(r["verification"]["physical_tablet_runtime_verified"]); self.assertFalse(r["verification"]["physical_drive_readback_verified"])
 def test_fail_closed_v381_rules(self):
  c=load(CONTRACT); rules=c["rules"]
  for key in ("multi_objective_verified_feedback_governor_required","operational_concept_drift_detection_required","operational_drift_must_not_infer_market_direction","verified_history_confidence_bound_required","verified_regression_quarantine_required","shadow_challenger_advisory_only","feature_contracts_non_executable","feature_contracts_require_protected_pr_ci","v380_gate_cannot_be_bypassed","decision_specific_100_senior_matrix_required","decision_specific_1000_review_cells_required","information_exchange_conflict_blocks_mutation","single_mutating_cycle_lock_required","autonomous_source_code_generation_forbidden","autonomous_git_write_forbidden","autonomous_verification_bypass_forbidden","autonomous_price_or_grade_invention_forbidden","physical_tablet_and_drive_results_must_not_be_invented"):
   self.assertIs(rules[key],True,key)
  self.assertTrue(autonomy.SAFETY["multi_objective_verified_feedback_governor"])
  self.assertTrue(autonomy.SAFETY["v380_gate_cannot_be_bypassed"])
  self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
  self.assertFalse(autonomy.SAFETY["git_write"])
  self.assertFalse(autonomy.SAFETY["market_direction_inferred"])
 def test_exact_candidate_and_current_runtime_route(self):
  c=load(CONTRACT); candidate=c["candidate_sync"]
  self.assertEqual(BASE,candidate["base_main_sha"]); self.assertEqual(CANDIDATE,candidate["candidate_commit"])
  self.assertEqual(["main","tablet_autonomous_evolution_v381.py","tablet_runtime_manifest.py"],candidate["watched_paths"])
  self.assertTrue(candidate["requires_exact_watched_path_match"]); self.assertTrue(candidate["post_merge_coverage_allowed"])
  assert_v381_successor(self)
  main=(ROOT/"main").read_text(encoding="utf-8"); manifest=(ROOT/"tablet_runtime_manifest.py").read_text(encoding="utf-8")
  self.assertIn("tablet_autonomous_evolution_v381.py --execute-safe-learning --apply-capabilities --train-meta --apply-skills",main)
  for version in ("v381","v380","v379","v378","v377","v376"): self.assertIn(f'"tablet_autonomous_evolution_{version}.py"',manifest)

if __name__=="__main__": unittest.main(verbosity=2)
