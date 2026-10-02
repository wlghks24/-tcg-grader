import json, tempfile, unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock
import tablet_autonomous_evolution_v381 as v381
NOW=datetime(2026,10,2,2,0,tzinfo=timezone.utc)
def healthy():
 return {"controller_version":"v380","v380_status":"PLAN_ONLY","safety":{"source_code_auto_generation":False,"source_code_auto_rewrite":False,"git_write":False,"verification_bypass":False,"price_or_grade_invention":False,"market_direction_inferred":False,"peer_fix_auto_apply":False,"peer_content_direct_model_training":False,"quality_policy_fail_closed_before_mutation":True,"quality_blocker_cannot_be_outvoted":True,"single_mutating_cycle_lock_required":True,"concurrent_mutating_cycle_fail_closed":True,"information_exchange_conflict_blocks_mutation":True,"information_exchange_invalid_blocks_mutation":True,"information_exchange_input_stability_required":True},"quality_governance":{"ok":True},"evidence_barrier":{"ok":True},"skill_state":{"corruption_hold":False},"plan":{"resources":{"status":"normal"},"market_profile":{"low_coverage_regions":[],"degraded_source_ratio":.05},"signals":{"runtime_models":{"status":"healthy","models":{"query_strategy":{"status":"active"}}}}},"selected_skill":{"skill_id":"RECOVER_SOURCE_HEALTH:SOURCE_HEALTH","recipe":"RECOVER_SOURCE_HEALTH","risk":.05},"candidates":[{"skill_id":"RECOVER_SOURCE_HEALTH:SOURCE_HEALTH","recipe":"RECOVER_SOURCE_HEALTH","score":80.,"risk":.05},{"skill_id":"OBSERVE_ONLY:SYNC","recipe":"OBSERVE_ONLY","score":62.,"risk":0.}],"skill_history":{"RECOVER_SOURCE_HEALTH":{"samples":5,"mean_reward":.7,"regression_rate":0.,"negative_streak":0,"hard_hold":False}},"source_feature_proposals":[{"proposal_id":"V374_SOURCE_GAP:parser","gap_kind":"source_parser"}],"adaptive_mode":{"mode":"RECOVER_SOURCE_HEALTH","market_regime":"HEALTHY"},"v378_single_run_lock":{"status":"V378_LOCK_NOT_REQUIRED"},"single_run_lock":{"status":"LOCK_NOT_REQUIRED"},"execution":{"status":"PLAN_ONLY","executed":False,"git_write":False,"source_code_modified":False,"proposals_executed":False},"information_exchange_manager":{"status":"EXCHANGE_CORROBORATED","mutation_allowed":True,"input_digest":"a"*64},"information_exchange_neural_council":{"confidence":.9,"agreement":.9,"readiness":"HIGH"},"autonomous_decision":{"status":"ALLOW_BOUNDED","allow_execution":True,"hard_blockers":[]}}
class V381Tests(unittest.TestCase):
 def test_safety(self):
  for k in ("multi_objective_verified_feedback_governor","concept_drift_detection_enabled","verified_history_confidence_bound_required","shadow_challenger_advisory_only","feature_contracts_non_executable","v380_gate_cannot_be_bypassed"): self.assertTrue(v381.SAFETY[k])
  for k in ("source_code_auto_generation","source_code_auto_rewrite","git_write","verification_bypass","market_direction_inferred"): self.assertFalse(v381.SAFETY[k])
 def test_kpi_and_drift(self):
  b=healthy(); k=v381.kpis(b); self.assertGreaterEqual(k["score"],0); self.assertLessEqual(k["score"],1); self.assertEqual(64,len(k["digest_sha256"])); s=v381._default(); old=deepcopy(k); old["dimensions"]["source_health"]=1.; s["last_kpis"]=old; b["plan"]["market_profile"]["degraded_source_ratio"]=.9; k2=v381.kpis(b); d=v381.drift(s,k2,b); self.assertEqual("HIGH",d["level"]); self.assertFalse(d["market_direction_inferred"])
 def test_verified_bad_history_holds(self):
  b=healthy(); b["skill_history"]["RECOVER_SOURCE_HEALTH"]={"samples":5,"mean_reward":-.5,"regression_rate":.6,"negative_streak":3,"hard_hold":True}; rel=v381.reliability(b); self.assertTrue(rel["quarantine_recommended"]); g=v381.gate(b,v381._default(),{"level":"LOW","score":0},rel,v381.kpis(b),NOW); self.assertFalse(g["allow_execution"]); self.assertEqual("V381_VERIFIED_STRATEGY_REGRESSION_HOLD",g["status"])
 def test_high_drift_only_recovery(self):
  b=healthy(); b["selected_skill"]["recipe"]="NORMAL_OPTIMIZATION"; b["skill_history"]={}; g=v381.gate(b,v381._default(),{"level":"HIGH","score":.8},v381.reliability(b),v381.kpis(b),NOW); self.assertEqual("V381_DRIFT_RECOVERY_ONLY",g["status"]); b["selected_skill"]["recipe"]="RECOVER_SOURCE_HEALTH"; g=v381.gate(b,v381._default(),{"level":"HIGH","score":.8},v381.reliability(b),v381.kpis(b),NOW); self.assertTrue(g["allow_execution"])
 def test_challenger_and_contracts_are_nonexecuting(self):
  c=v381.challenger(healthy()); self.assertTrue(c["available"]); self.assertFalse(c["auto_execute"]); fs=v381.contracts(healthy()); self.assertEqual(1,len(fs)); self.assertFalse(fs[0]["auto_execute"]); self.assertFalse(fs[0]["auto_generate_source"]); self.assertTrue(fs[0]["protected_pr_ci_required"]); self.assertEqual(["targeted_tests","related_regression","full_current_runtime","repository_integrity","tablet_gpt_alignment","actual_output_validation"],fs[0]["acceptance_sequence"])
 def test_v380_hold_never_bypassed(self):
  b=healthy(); b["autonomous_decision"]={"allow_execution":False,"hard_blockers":["TEST"]}; g=v381.gate(b,v381._default(),{"level":"LOW","score":0},v381.reliability(b),v381.kpis(b),NOW); self.assertEqual("V381_UPSTREAM_HOLD",g["status"]); self.assertFalse(g["allow_execution"])
 def test_blocked_cycle_only_previews(self):
  b=healthy(); b["autonomous_decision"]={"allow_execution":False,"hard_blockers":["TEST"]}
  with tempfile.TemporaryDirectory() as td, mock.patch.object(v381.v380,"run_cycle",return_value=b) as core:
   root=Path(td); r=v381.run_cycle(execute=True,apply_capabilities=True,train_meta=True,apply_skills=True,root=root,now=NOW,v381_state_path=root/".s",v381_lock_path=root/".l",persist_outputs=False)
  self.assertEqual(1,core.call_count); self.assertEqual("V381_UPSTREAM_HOLD",r["v381_status"]); self.assertFalse(r["execution"]["executed"])
 def test_allowed_cycle_executes_and_persists(self):
  p=healthy(); e=deepcopy(p); e["v380_status"]="V376_EXECUTED"; e["execution"]={"status":"V376_EXECUTED","executed":True,"git_write":False,"source_code_modified":False,"proposals_executed":False}
  with tempfile.TemporaryDirectory() as td, mock.patch.object(v381.v380,"run_cycle",side_effect=[p,e]) as core:
   root=Path(td); state=root/".s"; r=v381.run_cycle(execute=True,apply_capabilities=True,train_meta=True,apply_skills=True,root=root,now=NOW,v381_state_path=state,v381_lock_path=root/".l",persist_outputs=False); saved=json.loads(state.read_text())
  self.assertEqual(2,core.call_count); self.assertEqual("ALLOW_BOUNDED",r["v381_status"]); self.assertTrue(r["execution"]["executed"]); self.assertTrue(r["v381_state"]["write"]["written"]); self.assertEqual("v381",saved["controller_version"])
if __name__=="__main__": unittest.main(verbosity=2)
