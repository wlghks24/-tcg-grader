#!/usr/bin/env python3
"""V382: drift-aware verified-outcome governor above V381.

Adds KPI/drift feedback, verified-history quarantine, advisory challenger and
non-executable feature contracts. V381 remains the mandatory mutation gate.
No code/Git auto-write, trust promotion, price/grade invention or market-direction inference.
"""
from __future__ import annotations
import argparse, fcntl, hashlib, json, math, os, stat
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tablet_autonomous_evolution_v380 as v380
import tablet_autonomous_evolution_v381 as v381
from safe_runtime import atomic_write_json, safe_read_text
ROOT=Path(__file__).resolve().parent
CONTROLLER_VERSION="v382"; CORE_CONTROLLER_VERSION="v381"
STATE_PATH=ROOT/".tablet_autonomy_v382_state.json"; REPORT_PATH=ROOT/"tablet_autonomy_v382_report.json"; LOCK_PATH=ROOT/".tablet_autonomy_execution_v382.lock"
DRIFT_HIGH=.50; KPI_DROP_HOLD=.15; QUARANTINE_SECONDS=21600; RECOVERY={"REFRESH_MARKET_DATA","EXPAND_MARKET_COVERAGE","RECHECK_DEGRADED_SOURCES"}
_HOLD_STATUSES=set(getattr(v381,"_HOLD_STATUSES",set()))|{"V382_STATE_CORRUPTION_HOLD","V382_LOCK_UNAVAILABLE","V382_CONCURRENT_AUTONOMY_HOLD","V382_STATE_COMMIT_HOLD","V382_UPSTREAM_HOLD","V382_DRIFT_RECOVERY_ONLY","V382_VERIFIED_STRATEGY_REGRESSION_HOLD","V382_KPI_REGRESSION_HOLD"}
SAFETY=dict(v381.SAFETY); SAFETY.update({"multi_objective_verified_feedback_governor":True,"concept_drift_detection_enabled":True,"concept_drift_market_direction_free":True,"verified_history_confidence_bound_required":True,"verified_regression_quarantine_enabled":True,"shadow_challenger_advisory_only":True,"persistent_gap_feature_contracts_enabled":True,"feature_contracts_non_executable":True,"feature_contracts_require_protected_pr_ci":True,"v381_gate_cannot_be_bypassed":True,"source_code_auto_generation":False,"source_code_auto_rewrite":False,"arbitrary_command_execution":False,"git_write":False,"direct_main_write":False,"verification_bypass":False,"trust_or_fact_auto_promotion":False,"price_or_grade_invention":False,"market_direction_inferred":False})
def _now(): return datetime.now(timezone.utc)
def _f(v):
 try: n=float(v)
 except (TypeError,ValueError,OverflowError): return None
 return None if isinstance(v,bool) or not math.isfinite(n) else n
def _c(v,a=0.,b=1.): return max(a,min(b,v))
def _h(v): return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _t(v):
 try: d=datetime.fromisoformat(str(v or "").replace("Z","+00:00"))
 except (TypeError,ValueError,OverflowError): return None
 return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
def _default(): return {"schema_version":1,"controller_version":CONTROLLER_VERSION,"last_kpis":None,"last_regime":None,"last_model_signature":None,"last_exchange_digest":None,"quarantines":{},"history":[]}
def load_state(path):
 try:
  if not path.exists(): return {"state":_default(),"status":"fresh","corruption_hold":False}
  if path.is_symlink() or not path.is_file(): raise ValueError
  v=json.loads(safe_read_text(path,max_bytes=512000))
  if not isinstance(v,dict) or v.get("schema_version")!=1 or v.get("controller_version")!=CONTROLLER_VERSION or not isinstance(v.get("quarantines"),dict) or not isinstance(v.get("history"),list): raise ValueError
  return {"state":v,"status":"loaded","corruption_hold":False}
 except (OSError,UnicodeError,ValueError,TypeError,json.JSONDecodeError): return {"state":_default(),"status":"corrupt","corruption_hold":True}
def save_state(v,path,hold=False):
 if hold: return {"status":"STATE_CORRUPTION_HOLD","written":False}
 try: atomic_write_json(path,v,suffix=".v382-state.tmp")
 except (OSError,UnicodeError,ValueError,TypeError) as e: return {"status":"STATE_WRITE_FAILED","written":False,"error_code":type(e).__name__}
 return {"status":"STATE_SAVED","written":True}
def _regime(base):
 m=base.get("market_adaptation_v381") if isinstance(base.get("market_adaptation_v381"),dict) else {}; return str(m.get("regime") or m.get("market_regime") or "UNKNOWN")
def _model_sig(base):
 p=base.get("plan") if isinstance(base.get("plan"),dict) else {}; s=p.get("signals") if isinstance(p.get("signals"),dict) else {}; r=s.get("runtime_models") if isinstance(s.get("runtime_models"),dict) else {}; m=r.get("models") if isinstance(r.get("models"),dict) else {}; return _h({"runtime":r.get("status"),"models":{k:{"status":v.get("status"),"reason":v.get("reason")} for k,v in sorted(m.items()) if isinstance(v,dict)}})
def kpis(base):
 d=v380.dimension_values(base); w={"policy_contract":16,"safety_boundary":18,"evidence_commit":14,"state_integrity":10,"market_freshness":8,"market_coverage":7,"source_health":8,"neural_consensus":5,"resource_headroom":4,"recovery_integrity":4,"candidate_risk":3,"proposal_boundary":3}; score=sum(float(d.get(k,0))*n for k,n in w.items())/sum(w.values()); return {"score":round(_c(score),6),"dimensions":d,"digest_sha256":_h(d)}
def drift(state,k,base):
 old=(state.get("last_kpis") or {}).get("dimensions") if isinstance(state.get("last_kpis"),dict) else {}; comps={x:round(abs(float(k["dimensions"].get(x,0))-float(_f(old.get(x)) or 0)),6) for x in ("market_freshness","market_coverage","source_health","neural_consensus","resource_headroom")} if old else {x:0. for x in ("market_freshness","market_coverage","source_health","neural_consensus","resource_headroom")}; ex=base.get("information_exchange_memory_v381") if isinstance(base.get("information_exchange_memory_v381"),dict) else (base.get("information_exchange_manager") if isinstance(base.get("information_exchange_manager"),dict) else {}); ed=str(ex.get("input_digest") or ""); score=max(comps.values(),default=0.); score=max(score,.35 if state.get("last_regime") and state.get("last_regime")!=_regime(base) else 0,.25 if state.get("last_model_signature") and state.get("last_model_signature")!=_model_sig(base) else 0,.20 if state.get("last_exchange_digest") and ed and state.get("last_exchange_digest")!=ed else 0); return {"level":"HIGH" if score>=DRIFT_HIGH else "LOW","score":round(score,6),"components":comps,"market_direction_inferred":False}
def reliability(base):
 pol=base.get("policy_evolution_v381") if isinstance(base.get("policy_evolution_v381"),dict) else {}; sel=pol.get("selection") if isinstance(pol.get("selection"),dict) else {}; recipe=str(sel.get("champion_action") or ""); stats=pol.get("verified_outcome_stats") if isinstance(pol.get("verified_outcome_stats"),dict) else {}; row=stats.get(recipe) if recipe else None
 if isinstance(row,dict):
  n=max(0,int(row.get("verified_samples") or 0)); mean=_c(float(_f(row.get("reward_mean")) or 0),-1,1); rmin=_f(row.get("reward_min")); rmax=_f(row.get("reward_max")); lcb=max(-1.,mean-min(1.,1/math.sqrt(max(1,n)))); bad=bool(n>=8 and (lcb<-.2 or mean<-.15 or (rmin is not None and rmin<=-.95 and mean<0))); return {"recipe":recipe or None,"samples":n,"mean_reward":round(mean,6),"reward_min":None if rmin is None else round(rmin,6),"reward_max":None if rmax is None else round(rmax,6),"lower_confidence_bound":round(lcb,6),"regression_rate":None,"negative_streak":None,"quarantine_recommended":bad,"evidence_digest":_h([recipe,n,mean,rmin,rmax,lcb])}
 s=base.get("selected_skill") if isinstance(base.get("selected_skill"),dict) else {}; recipe=str(s.get("recipe") or ""); hist=base.get("skill_history") if isinstance(base.get("skill_history"),dict) else {}; z=hist.get(recipe) if recipe else None
 if not isinstance(z,dict): return {"recipe":recipe or None,"samples":0,"quarantine_recommended":False}
 n=max(0,int(z.get("samples") or 0)); mean=_c(float(_f(z.get("mean_reward")) or 0),-1,1); rr=_c(float(_f(z.get("regression_rate")) or 0)); streak=max(0,int(z.get("negative_streak") or 0)); lcb=max(-1.,mean-min(1.,1/math.sqrt(max(1,n)))); bad=bool(z.get("hard_hold") is True or streak>=3 or rr>=.5 or (n>=3 and lcb<-.2)); return {"recipe":recipe or None,"samples":n,"mean_reward":round(mean,6),"lower_confidence_bound":round(lcb,6),"regression_rate":round(rr,6),"negative_streak":streak,"quarantine_recommended":bad,"evidence_digest":_h([recipe,n,mean,lcb,rr,streak])}
def challenger(base):
 pol=base.get("policy_evolution_v381") if isinstance(base.get("policy_evolution_v381"),dict) else {}; sel=pol.get("selection") if isinstance(pol.get("selection"),dict) else {}; champion=str(sel.get("champion_action") or ""); rows=pol.get("candidate_actions") if isinstance(pol.get("candidate_actions"),list) else []
 if rows:
  valid=[r for r in rows if isinstance(r,dict) and str(r.get("action_id") or "")!=champion]; valid.sort(key=lambda r:(-float(_f(r.get("score")) or 0),-int(r.get("verified_samples") or 0),str(r.get("action_id") or ""))); top=valid[0] if valid else None; return {"available":top is not None,"auto_execute":False,"candidate":({"action_id":str(top.get("action_id") or "")[:128],"score":round(float(_f(top.get("score")) or 0),6),"verified_samples":max(0,int(top.get("verified_samples") or 0)),"reward_mean":_f(top.get("reward_mean"))} if top else None),"source":"v381_verified_policy_candidates"}
 s=base.get("selected_skill") if isinstance(base.get("selected_skill"),dict) else {}; sid=str(s.get("skill_id") or ""); legacy=[r for r in base.get("candidates",[]) if isinstance(r,dict) and str(r.get("skill_id") or "")!=sid and r.get("blocked_by_verified_history") is not True]; legacy.sort(key=lambda r:(-float(_f(r.get("score")) or 0),float(_f(r.get("risk")) or 1))); return {"available":bool(legacy),"auto_execute":False,"candidate":({"skill_id":str(legacy[0].get("skill_id") or "")[:128],"recipe":str(legacy[0].get("recipe") or "")[:96],"score":round(float(_f(legacy[0].get("score")) or 0),6)} if legacy else None),"source":"legacy_verified_candidates"}
def contracts(base):
 out=[]
 for r in (base.get("source_feature_proposals_v381") if isinstance(base.get("source_feature_proposals_v381"),list) else base.get("source_feature_proposals",[])):
  if not isinstance(r,dict): continue
  pid=str(r.get("proposal_id") or r.get("id") or "")[:160]
  if pid: out.append({"contract_id":f"V382:{pid}"[:190],"proposal_id":pid,"gap_kind":str(r.get("gap_kind") or r.get("kind") or "unknown")[:80],"auto_execute":False,"auto_generate_source":False,"git_write":False,"protected_pr_ci_required":True,"acceptance_sequence":["targeted_tests","related_regression","full_current_runtime","repository_integrity","tablet_gpt_alignment","actual_output_validation"],"rollback_triggers":["regression_detected","integrity_failure","alignment_failure","provenance_loss","security_boundary_regression"]})
 return out[:32]
def gate(base,state,d,rel,k,now):
 up=base.get("autonomous_decision") if isinstance(base.get("autonomous_decision"),dict) else {}; pol=base.get("policy_evolution_v381") if isinstance(base.get("policy_evolution_v381"),dict) else {}; sel=pol.get("selection") if isinstance(pol.get("selection"),dict) else {}; s=base.get("selected_skill") if isinstance(base.get("selected_skill"),dict) else {}; recipe=str(sel.get("champion_action") or s.get("recipe") or ""); reasons=[]; q=(state.get("quarantines") or {}).get(recipe); until=_t(q.get("until")) if isinstance(q,dict) else None
 if str(base.get("v381_status") or "") in getattr(v381,"_HOLD_STATUSES",set()) or up.get("allow_execution") is not True: reasons.append("V381_GATE_HOLD")
 if until and until>now: reasons.append("VERIFIED_RECIPE_QUARANTINE")
 if rel.get("quarantine_recommended") is True: reasons.append("VERIFIED_STRATEGY_REGRESSION")
 old=_f((state.get("last_kpis") or {}).get("score")) if isinstance(state.get("last_kpis"),dict) else None
 if old is not None and recipe not in RECOVERY and old-float(k["score"])>KPI_DROP_HOLD: reasons.append("KPI_REGRESSION")
 if d["level"]=="HIGH" and recipe and recipe not in RECOVERY: reasons.append("HIGH_DRIFT_RECOVERY_ONLY")
 status="ALLOW_BOUNDED" if not reasons else "V382_UPSTREAM_HOLD" if "V381_GATE_HOLD" in reasons else "V382_VERIFIED_STRATEGY_REGRESSION_HOLD" if any(x in reasons for x in ("VERIFIED_RECIPE_QUARANTINE","VERIFIED_STRATEGY_REGRESSION")) else "V382_KPI_REGRESSION_HOLD" if "KPI_REGRESSION" in reasons else "V382_DRIFT_RECOVERY_ONLY"
 return {"status":status,"allow_execution":not reasons,"directive":"EXECUTE_VERIFIED_SELECTION" if not reasons else "HOLD_AND_OBSERVE","reasons":reasons,"selected_recipe":recipe or None,"hard_blocker_override":False}
def _next(state,base,k,d,g,rel,now):
 s=deepcopy(state); q=dict(s.get("quarantines") or {}); recipe=str(rel.get("recipe") or "")
 for x,row in list(q.items()):
  if not isinstance(row,dict) or not _t(row.get("until")) or _t(row.get("until"))<=now: q.pop(x,None)
 if recipe and rel.get("quarantine_recommended") is True: q[recipe]={"until":(now+timedelta(seconds=QUARANTINE_SECONDS)).isoformat(timespec="seconds"),"reason":"verified_strategy_regression","evidence_digest":str(rel.get("evidence_digest") or "")}
 ex=base.get("information_exchange_memory_v381") if isinstance(base.get("information_exchange_memory_v381"),dict) else (base.get("information_exchange_manager") if isinstance(base.get("information_exchange_manager"),dict) else {}); h=list(s.get("history") or []); h.append({"at":now.isoformat(timespec="seconds"),"status":g.get("status"),"kpi":k["score"],"drift":d["score"]}); s.update({"last_kpis":k,"last_regime":_regime(base),"last_model_signature":_model_sig(base),"last_exchange_digest":str(ex.get("input_digest") or ""),"quarantines":q,"history":h[-96:]}); return s
def _lock(path):
 fd=None
 try:
  flags=os.O_RDWR|os.O_CREAT|(os.O_CLOEXEC if hasattr(os,"O_CLOEXEC") else 0)|(os.O_NOFOLLOW if hasattr(os,"O_NOFOLLOW") else 0); fd=os.open(path,flags,0o600); info=os.fstat(fd)
  if not stat.S_ISREG(info.st_mode): os.close(fd); return None,"V382_LOCK_UNAVAILABLE"
  os.fchmod(fd,0o600); fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB); return fd,"V382_LOCK_ACQUIRED"
 except BlockingIOError:
  if fd is not None:
   try: os.close(fd)
   except OSError: pass
  return None,"V382_CONCURRENT_AUTONOMY_HOLD"
 except OSError:
  if fd is not None:
   try: os.close(fd)
   except OSError: pass
  return None,"V382_LOCK_UNAVAILABLE"
def run_cycle(*,execute=False,apply_capabilities=False,train_meta=False,apply_skills=False,root=ROOT,now=None,proc_root=Path("/proc"),state_path=None,capability_path=None,meta_model_path=None,meta_outcomes_path=None,skill_state_path=None,skill_outcomes_path=None,journal_path=None,core_lock_path=None,v380_lock_path=None,v381_lock_path=None,quality_policy_path=None,policy_state_path=None,v382_state_path=None,v382_lock_path=None,persist_outputs=True):
 moment=(now or _now()).astimezone(timezone.utc); sp=v382_state_path or root/STATE_PATH.name; si=load_state(sp); mut=bool(execute or apply_capabilities or train_meta or apply_skills); fd=None; ls="V382_LOCK_NOT_REQUIRED"
 if mut:
  fd,ls=_lock(v382_lock_path or root/LOCK_PATH.name)
  if fd is None: return {"controller_version":CONTROLLER_VERSION,"v382_status":ls,"execution":{"status":ls,"executed":False,"git_write":False,"source_code_modified":False,"proposals_executed":False},"safety":SAFETY}
 kw=dict(root=root,now=moment,proc_root=proc_root,state_path=state_path,capability_path=capability_path,meta_model_path=meta_model_path,meta_outcomes_path=meta_outcomes_path,skill_state_path=skill_state_path,skill_outcomes_path=skill_outcomes_path,journal_path=journal_path,core_lock_path=core_lock_path,v380_lock_path=v380_lock_path,lock_path=v381_lock_path,quality_policy_path=quality_policy_path,policy_state_path=policy_state_path,persist_outputs=False)
 try:
  pre=v381.run_cycle(execute=False,apply_capabilities=False,train_meta=False,apply_skills=False,**kw); k=kpis(pre); d=drift(si["state"],k,pre); rel=reliability(pre); g={"status":"V382_STATE_CORRUPTION_HOLD","allow_execution":False,"reasons":["STATE_CORRUPTION_HOLD"]} if si["corruption_hold"] and mut else gate(pre,si["state"],d,rel,k,moment); base=pre
  if mut and g.get("allow_execution") is True:
   base=v381.run_cycle(execute=execute,apply_capabilities=apply_capabilities,train_meta=train_meta,apply_skills=apply_skills,**kw); cs=str(base.get("v381_status") or "")
   if cs in getattr(v381,"_HOLD_STATUSES",set()): g={"status":"V382_UPSTREAM_HOLD","allow_execution":False,"reasons":[cs],"hard_blocker_override":False}
  fk=kpis(base); result=deepcopy(base); result.update({"core_controller_version":str(base.get("controller_version") or CORE_CONTROLLER_VERSION),"controller_version":CONTROLLER_VERSION,"v382_status":g.get("status"),"v382_kpis":fk,"v382_drift":d,"v382_verified_reliability":reliability(base),"v382_shadow_challenger":challenger(base),"v382_feature_contracts":contracts(base),"v382_autonomous_gate":g,"v382_single_run_lock":{"status":ls},"safety":SAFETY})
  if mut and g.get("allow_execution") is not True: result["execution"]={"status":g.get("status"),"executed":False,"git_write":False,"source_code_modified":False,"proposals_executed":False}
  sw={"status":"NOT_REQUESTED","written":False}
  if mut:
   sw=save_state(_next(si["state"],base,fk,d,g,reliability(base),moment),sp,si["corruption_hold"])
   if sw.get("written") is not True and g.get("allow_execution") is True: result["v382_status"]="V382_STATE_COMMIT_HOLD"
  result["v382_state"]={"load_status":si["status"],"corruption_hold":si["corruption_hold"],"write":sw}
  if persist_outputs:
   try: atomic_write_json(root/REPORT_PATH.name,result,suffix=".v382-report.tmp"); result["v382_runtime_output"]={"status":"SAVED"}
   except (OSError,UnicodeError,ValueError,TypeError) as e: result["v382_runtime_output"]={"status":"WRITE_FAILED","error_code":type(e).__name__}
  return result
 finally:
  if fd is not None:
   try: fcntl.flock(fd,fcntl.LOCK_UN)
   finally: os.close(fd)
def self_test():
 assert SAFETY["multi_objective_verified_feedback_governor"] and SAFETY["concept_drift_detection_enabled"] and SAFETY["verified_history_confidence_bound_required"] and SAFETY["shadow_challenger_advisory_only"] and SAFETY["feature_contracts_non_executable"] and SAFETY["v381_gate_cannot_be_bypassed"]; assert SAFETY["source_code_auto_generation"] is False and SAFETY["git_write"] is False and SAFETY["market_direction_inferred"] is False; print("Tablet drift-aware verified-outcome autonomous evolution v382: PASS")
def main():
 p=argparse.ArgumentParser(); p.add_argument("--execute-safe-learning",action="store_true"); p.add_argument("--apply-capabilities",action="store_true"); p.add_argument("--train-meta",action="store_true"); p.add_argument("--apply-skills",action="store_true"); p.add_argument("--self-test",action="store_true"); p.add_argument("--quiet",action="store_true"); a=p.parse_args()
 if a.self_test: self_test(); return 0
 r=run_cycle(execute=a.execute_safe_learning,apply_capabilities=a.apply_capabilities,train_meta=a.train_meta,apply_skills=a.apply_skills)
 if not a.quiet: print(json.dumps(r,ensure_ascii=False,sort_keys=True))
 return 2 if r.get("v382_status") in _HOLD_STATUSES else 0
if __name__=="__main__": raise SystemExit(main())
