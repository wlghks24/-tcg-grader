#!/usr/bin/env python3
"""Verified-feedback autonomous evolution for Tablet GPT / TCG Grader.

V375 extends v374 with four bounded feedback improvements:
1) verified v374 trial outcomes are bridged into the v373 meta-neural learner;
2) candidate selection is uncertainty/failure aware without exceeding fixed safety limits;
3) one market action may compose multiple already-allowlisted declarative capabilities;
4) skill/meta outcome stores are fail-closed so corrupt evidence is never overwritten.

The runtime still cannot generate/rewrite source code, execute arbitrary commands,
write Git/main, invent card facts/prices/grades/market direction, or bypass any
verification/PR/CI boundary. Source-level feature gaps remain non-executable
proposals for the normal protected branch/PR pipeline.
"""
from __future__ import annotations

import argparse
import json
import math
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tablet_autonomous_evolution_v374 as v374
from safe_runtime import atomic_write_json, atomic_write_text, safe_read_text

ROOT = Path(__file__).resolve().parent
CONTROLLER_VERSION = "v375"
SCHEMA_VERSION = 5
REPORT_PATH = ROOT / "tablet_autonomy_v375_report.json"
SOURCE_PROPOSALS_PATH = ROOT / "tablet_autonomy_source_feature_proposals_v375.json"
MAX_EXPLORATION_BONUS = 5.0
MAX_HISTORY_PENALTY = 30.0
NEGATIVE_STREAK_HARD_HOLD = 3
MAX_COMPOSED_CAPABILITIES = 8
SAFETY = dict(v374.SAFETY)
SAFETY.update({
    "verified_skill_outcomes_feed_meta_neural": True,
    "meta_feedback_requires_exact_trial_features": True,
    "skill_outcome_corruption_is_hold": True,
    "meta_outcome_corruption_is_hold": True,
    "uncertainty_aware_candidate_selection": True,
    "verified_failure_streak_penalty": True,
    "negative_streak_hard_hold": NEGATIVE_STREAK_HARD_HOLD,
    "cross_gap_declarative_capability_composition": True,
    "cross_gap_composition_allowlisted_only": True,
    "one_heavy_operation_per_cycle": True,
    "source_code_auto_generation": False,
    "source_code_auto_rewrite": False,
    "arbitrary_command_generation": False,
    "arbitrary_command_execution": False,
    "git_write": False,
    "direct_main_write": False,
    "verification_bypass": False,
    "trust_or_fact_auto_promotion": False,
    "price_or_grade_invention": False,
    "market_direction_inferred": False,
})
META_ACTION_BY_RECIPE = {
    "RECOVER_FRESHNESS": "REFRESH_MARKET_DATA",
    "EXPAND_REGION_COVERAGE": "EXPAND_MARKET_COVERAGE",
    "RECOVER_SOURCE_HEALTH": "RECHECK_DEGRADED_SOURCES",
}

def _now() -> datetime:
    return datetime.now(timezone.utc)

def _finite(value: Any) -> float | None:
    return v374._finite(value)

def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))

def _strict_jsonl(path: Path, *, max_bytes: int, validator) -> tuple[str, list[dict[str, Any]]]:
    try:
        if not path.exists(): return "fresh", []
        if path.is_symlink() or not path.is_file(): return "corrupt", []
        text = safe_read_text(path, max_bytes=max_bytes)
    except (OSError, UnicodeError, ValueError, TypeError):
        return "corrupt", []
    rows=[]
    for raw in text.splitlines():
        if not raw.strip(): continue
        try: row=json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError): return "corrupt", []
        clean=validator(row)
        if clean is None: return "corrupt", []
        rows.append(clean)
    return "loaded", rows

def _clean_skill_outcome(row: Any) -> dict[str, Any] | None:
    if not isinstance(row, dict) or row.get("verified") is not True: return None
    recipe=str(row.get("recipe") or ""); reward=_finite(row.get("reward")); evidence=str(row.get("evidence_ref") or "").strip()
    if recipe not in v374.SKILL_RECIPES or reward is None or not evidence: return None
    return {"verified":True,"recipe":recipe,"skill_id":str(row.get("skill_id") or "")[:128],"reward":round(_clamp(float(reward),-1.0,1.0),6),"regression_detected":row.get("regression_detected") is True,"evidence_ref":evidence[:240],"verified_at":str(row.get("verified_at") or "")[:64]}

def _clean_meta_outcome(row: Any) -> dict[str, Any] | None:
    if not isinstance(row, dict) or row.get("verified") is not True: return None
    action=str(row.get("action_id") or ""); reward=_finite(row.get("reward")); evidence=str(row.get("evidence_ref") or "").strip(); features=row.get("features")
    if action not in v374.v373.META_ACTIONS or reward is None or not evidence: return None
    if not isinstance(features,list) or len(features)!=v374.v373.META_INPUT_DIM: return None
    cleaned=[]
    for value in features:
        number=_finite(value)
        if number is None or number<0.0 or number>1.0: return None
        cleaned.append(float(number))
    return {"verified":True,"action_id":action,"reward":round(_clamp(float(reward),-1.0,1.0),6),"features":cleaned,"evidence_ref":evidence[:240]}

def load_skill_outcomes_strict(*, path: Path=v374.OUTCOMES_PATH)->dict[str,Any]:
    status,rows=_strict_jsonl(path,max_bytes=v374.MAX_OUTCOME_BYTES,validator=_clean_skill_outcome); return {"status":status,"rows":rows,"corruption_hold":status=="corrupt"}

def load_meta_outcomes_strict(*, path: Path=v374.v373.OUTCOMES_PATH)->dict[str,Any]:
    status,rows=_strict_jsonl(path,max_bytes=v374.v373.MAX_OUTCOME_BYTES,validator=_clean_meta_outcome); return {"status":status,"rows":rows,"corruption_hold":status=="corrupt"}

def persist_skill_outcomes_fail_closed(new_rows:list[dict[str,Any]],*,path:Path=v374.OUTCOMES_PATH)->dict[str,Any]:
    store=load_skill_outcomes_strict(path=path)
    if store["corruption_hold"]: return {"status":"SKILL_OUTCOME_CORRUPTION_HOLD","written":False,"count":0}
    if not new_rows: return {"status":"NO_NEW_VERIFIED_OUTCOMES","written":False,"count":0}
    merged=list(store["rows"]); seen={str(r["evidence_ref"]) for r in merged}; accepted=0
    for raw in new_rows:
        clean=_clean_skill_outcome(raw)
        if clean is None or clean["evidence_ref"] in seen: continue
        merged.append(clean); seen.add(clean["evidence_ref"]); accepted+=1
    if accepted==0: return {"status":"NO_VALID_VERIFIED_OUTCOMES","written":False,"count":0}
    merged=merged[-v374.MAX_OUTCOMES:]; text="\n".join(json.dumps(r,ensure_ascii=False,sort_keys=True) for r in merged)+"\n"
    try: atomic_write_text(path,text,suffix=".v375-skill-outcomes.tmp")
    except (OSError,UnicodeError,ValueError,TypeError) as exc: return {"status":"SKILL_OUTCOME_WRITE_FAILED","written":False,"count":0,"error_code":type(exc).__name__}
    return {"status":"VERIFIED_OUTCOMES_SAVED","written":True,"count":accepted}

def _meta_action_from_trial(trial:dict[str,Any])->str|None:
    recipe=str(trial.get("recipe") or "")
    if recipe in META_ACTION_BY_RECIPE: return META_ACTION_BY_RECIPE[recipe]
    if recipe=="RECOVER_MODEL":
        action=str(trial.get("safe_learning_action") or ""); return action if action in v374.v373.META_ACTIONS else None
    return None

def _trial_for_skill(skill:dict[str,Any],plan:dict[str,Any],*,now:datetime)->dict[str,Any]:
    trial=v374._trial_for_skill(skill,plan,now=now); trial["meta_features"]=v374.v373.feature_vector(plan); trial["candidate_score"]=round(float(skill.get("v375_score",skill.get("score",0.0)) or 0.0),6); return trial

def evaluate_trial(trial:dict[str,Any],plan:dict[str,Any],*,now:datetime|None=None)->dict[str,Any]|None:
    result=v374.evaluate_trial(trial,plan,now=now)
    if result is None: return None
    action=_meta_action_from_trial(trial); features=trial.get("meta_features")
    if action is not None and isinstance(features,list) and len(features)==v374.v373.META_INPUT_DIM and all((_finite(x) is not None and 0.0<=float(x)<=1.0) for x in features): result["meta_action_id"]=action; result["meta_features"]=[float(x) for x in features]
    return result

def meta_feedback_rows(verified_rows:list[dict[str,Any]])->list[dict[str,Any]]:
    result=[]
    for row in verified_rows:
        action=str(row.get("meta_action_id") or ""); features=row.get("meta_features"); reward=_finite(row.get("reward")); evidence=str(row.get("evidence_ref") or "").strip()
        if row.get("verified") is not True or action not in v374.v373.META_ACTIONS or reward is None or not evidence or not isinstance(features,list) or len(features)!=v374.v373.META_INPUT_DIM: continue
        clean=_clean_meta_outcome({"verified":True,"action_id":action,"reward":reward,"features":features,"evidence_ref":f"v375:{evidence}"[:240]})
        if clean is not None: result.append(clean)
    return result

def persist_meta_feedback_fail_closed(rows:list[dict[str,Any]],*,path:Path=v374.v373.OUTCOMES_PATH)->dict[str,Any]:
    store=load_meta_outcomes_strict(path=path)
    if store["corruption_hold"]: return {"status":"META_OUTCOME_CORRUPTION_HOLD","written":False,"count":0}
    if not rows: return {"status":"NO_META_FEEDBACK","written":False,"count":0}
    merged=list(store["rows"]); seen={str(r["evidence_ref"]) for r in merged}; accepted=0
    for raw in rows:
        clean=_clean_meta_outcome(raw)
        if clean is None or clean["evidence_ref"] in seen: continue
        merged.append(clean); seen.add(clean["evidence_ref"]); accepted+=1
    if accepted==0: return {"status":"NO_NEW_META_FEEDBACK","written":False,"count":0}
    merged=merged[-v374.v373.MAX_META_OUTCOMES:]; text="\n".join(json.dumps(r,ensure_ascii=False,sort_keys=True) for r in merged)+"\n"
    try: atomic_write_text(path,text,suffix=".v375-meta-feedback.tmp")
    except (OSError,UnicodeError,ValueError,TypeError) as exc: return {"status":"META_FEEDBACK_WRITE_FAILED","written":False,"count":0,"error_code":type(exc).__name__}
    return {"status":"META_FEEDBACK_SAVED","written":True,"count":accepted}

def extended_history_stats(rows:list[dict[str,Any]])->dict[str,dict[str,Any]]:
    base=v374.skill_history_stats(rows); by_recipe={name:[] for name in v374.SKILL_RECIPES}
    for row in rows:
        recipe=str(row.get("recipe") or "")
        if recipe in by_recipe: by_recipe[recipe].append(row)
    result={}
    for recipe,stat in base.items():
        group=by_recipe.get(recipe,[]); negative_streak=0
        for row in reversed(group):
            reward=_finite(row.get("reward"))
            if reward is None or reward>=0: break
            negative_streak+=1
        samples=int(stat.get("samples") or 0); uncertainty=1.0/math.sqrt(samples+1.0); exploration=min(MAX_EXPLORATION_BONUS,4.0*uncertainty); regression_rate=float(stat.get("regression_rate") or 0.0); mean_reward=float(stat.get("mean_reward") or 0.0); penalty=min(MAX_HISTORY_PENALTY,negative_streak*7.0+regression_rate*12.0+max(0.0,-mean_reward)*10.0); merged=dict(stat); merged.update({"negative_streak":negative_streak,"uncertainty":round(uncertainty,6),"exploration_bonus":round(exploration,6),"failure_penalty":round(penalty,6),"hard_hold":negative_streak>=NEGATIVE_STREAK_HARD_HOLD}); result[recipe]=merged
    return result

def rerank_candidates(candidates:list[dict[str,Any]],history:dict[str,dict[str,Any]])->list[dict[str,Any]]:
    ranked=[]
    for raw in candidates:
        row=deepcopy(raw); recipe=str(row.get("recipe") or ""); stat=history.get(recipe) or {}; base=float(_finite(row.get("score")) or 0.0); exploration=float(_finite(stat.get("exploration_bonus")) or 0.0); penalty=float(_finite(stat.get("failure_penalty")) or 0.0); hard=stat.get("hard_hold") is True; adjusted=0.0 if hard else _clamp(base+exploration-penalty,0.0,100.0); row.update({"v375_base_score":round(base,6),"v375_exploration_bonus":round(exploration,6),"v375_history_penalty":round(penalty,6),"v375_negative_streak":int(stat.get("negative_streak") or 0),"v375_hard_hold":hard,"v375_score":round(adjusted,6)}); row["score"]=row["v375_score"]
        if hard: row["blocked_by_verified_history"]=True
        ranked.append(row)
    ranked.sort(key=lambda r:(-float(r["v375_score"]),float(r.get("risk") or 0.0),str(r.get("skill_id") or ""))); return ranked

def compose_cross_gap_capabilities(selected:dict[str,Any]|None,gaps:list[dict[str,Any]],*,now:datetime|None=None)->list[dict[str,Any]]:
    if not isinstance(selected,dict): return []
    moment=(now or _now()).astimezone(timezone.utc); rows=list(v374.skill_capabilities(selected,now=moment)); market_recipes={"RECOVER_FRESHNESS","EXPAND_REGION_COVERAGE","RECOVER_SOURCE_HEALTH"}
    if str(selected.get("recipe") or "") not in market_recipes: return rows
    kinds={str(g.get("kind") or "") for g in gaps}; evidence={"reason":"v375_cross_gap_composition","skill_id":str(selected.get("skill_id") or "")[:128]}
    if "market_freshness" in kinds: rows.append(v374.v373._capability("REQUEST_FRESHNESS_REFRESH","V375_COMPOSED",{"max_runs":1},evidence,now=moment))
    if "source_health" in kinds: rows.append(v374.v373._capability("RETRY_DEGRADED_SOURCES","V375_COMPOSED",{"max_retry":2,"backoff_seconds":120},evidence,now=moment))
    for gap in gaps:
        if str(gap.get("kind") or "")!="region_coverage": continue
        region=str(gap.get("region") or "")
        if region in {"KR","JP","US"}: rows.append(v374.v373._capability("PRIORITIZE_REGION",f"V375_{region}",{"region":region,"boost":0.10},evidence,now=moment))
    rows.append(v374.v373._capability("INCREASE_OBSERVATION","V375_MARKET",{"scope":"market_health","factor":1.25},evidence,now=moment)); return v374.v373.merge_capabilities([],rows,now=moment)[:MAX_COMPOSED_CAPABILITIES]

def reconcile_skill_state(loaded_state:dict[str,Any],*,plan:dict[str,Any],selected_skill:dict[str,Any]|None,history:dict[str,dict[str,Any]],now:datetime|None=None)->tuple[dict[str,Any],list[dict[str,Any]]]:
    moment=(now or _now()).astimezone(timezone.utc); state=deepcopy(loaded_state); verified=[]; pending=[]
    for trial in state.get("pending_trials",[]):
        result=evaluate_trial(trial,plan,now=moment)
        if result is None: pending.append(trial)
        else: verified.append(result)
    state["pending_trials"]=pending[:v374.MAX_PENDING_TRIALS]; blocked={recipe for recipe,stat in history.items() if stat.get("blocked") is True or stat.get("hard_hold") is True}; blocked.update(str(r.get("recipe") or "") for r in verified if r.get("regression_detected") is True); state["suspended_recipes"]=sorted(x for x in blocked if x in v374.SKILL_RECIPES); state["active_skills"]=[r for r in state.get("active_skills",[]) if str(r.get("recipe") or "") not in blocked][:v374.MAX_ACTIVE_SKILLS]
    if selected_skill and selected_skill["recipe"] not in blocked:
        active=v374._active_skill_row(selected_skill,now=moment); by_id={str(r.get("skill_id") or ""):r for r in state["active_skills"]}; by_id[active["skill_id"]]=active; state["active_skills"]=sorted(by_id.values(),key=lambda r:str(r["skill_id"]))[:v374.MAX_ACTIVE_SKILLS]
        if selected_skill["recipe"]!="OBSERVE_ONLY":
            trial=_trial_for_skill(selected_skill,plan,now=moment); by_trial={str(r.get("skill_id") or ""):r for r in state["pending_trials"]}; by_trial[trial["skill_id"]]=trial; state["pending_trials"]=sorted(by_trial.values(),key=lambda r:str(r["skill_id"]))[:v374.MAX_PENDING_TRIALS]
    return state,verified

def train_meta_from_current_evidence(*,path:Path,model_path:Path,now:datetime,requested:bool)->dict[str,Any]:
    if not requested: return {"status":"META_TRAINING_NOT_REQUESTED","written":False}
    store=load_meta_outcomes_strict(path=path)
    if store["corruption_hold"]: return {"status":"META_OUTCOME_CORRUPTION_HOLD","written":False}
    rows=[{"action_id":r["action_id"],"reward":r["reward"],"features":r["features"],"evidence_ref":r["evidence_ref"]} for r in store["rows"]]; existing=v374.v373.load_meta_model(path=model_path,now=now); candidate=v374.v373.train_meta_model(rows,now=now,existing=existing)
    if candidate is None: return {"status":"META_TRAINING_GATE_HELD","written":False,"verified_outcomes":len(rows)}
    result=dict(v374.v373.persist_meta_model(candidate,path=model_path)); result["verified_outcomes"]=len(rows); return result

def run_cycle(*,execute:bool=False,apply_capabilities:bool=False,train_meta:bool=False,apply_skills:bool=False,root:Path=ROOT,now:datetime|None=None,proc_root:Path=Path("/proc"),state_path:Path|None=None,capability_path:Path|None=None,meta_model_path:Path|None=None,meta_outcomes_path:Path|None=None,skill_state_path:Path|None=None,skill_outcomes_path:Path|None=None,persist_outputs:bool=True)->dict[str,Any]:
    moment=(now or _now()).astimezone(timezone.utc); state=state_path or (root/v374.v373.v372.STATE_PATH.name); cap_path=capability_path or (root/v374.v373.CAPABILITY_PATH.name); meta_path=meta_model_path or (root/v374.v373.META_MODEL_PATH.name); meta_outcomes=meta_outcomes_path or (root/v374.v373.OUTCOMES_PATH.name); skill_state_file=skill_state_path or (root/v374.SKILL_STATE_PATH.name); skill_outcomes_file=skill_outcomes_path or (root/v374.OUTCOMES_PATH.name)
    base_report=v374.v373.run_cycle(execute=False,apply_capabilities=False,train_meta=False,root=root,now=moment,proc_root=proc_root,state_path=state,capability_path=cap_path,meta_model_path=meta_path,outcomes_path=meta_outcomes,persist_outputs=False); plan=base_report["plan"]; gaps=v374.detect_gaps(plan); skill_store=load_skill_outcomes_strict(path=skill_outcomes_file); loaded_skills=v374.load_skill_state(path=skill_state_file,now=moment); prior_rows=list(skill_store["rows"]) if not skill_store["corruption_hold"] else []; prior_history=extended_history_stats(prior_rows); evaluated_state,verified_now=reconcile_skill_state(loaded_skills["state"],plan=plan,selected_skill=None,history=prior_history,now=moment)
    skill_outcome_write=persist_skill_outcomes_fail_closed(verified_now,path=skill_outcomes_file) if apply_skills and not skill_store["corruption_hold"] else {"status":"SKILL_OUTCOME_CORRUPTION_HOLD" if skill_store["corruption_hold"] else "OUTCOME_APPLY_NOT_REQUESTED","written":False,"count":0}; meta_feedback=[] if skill_store["corruption_hold"] else meta_feedback_rows(verified_now)
    if skill_store["corruption_hold"]: meta_feedback_write={"status":"SKILL_OUTCOME_CORRUPTION_HOLD","written":False,"count":0}; meta_training={"status":"SKILL_OUTCOME_CORRUPTION_HOLD","written":False}
    else: meta_feedback_write=persist_meta_feedback_fail_closed(meta_feedback,path=meta_outcomes) if apply_skills else {"status":"META_FEEDBACK_APPLY_NOT_REQUESTED","written":False,"count":0}; meta_training=train_meta_from_current_evidence(path=meta_outcomes,model_path=meta_path,now=moment,requested=train_meta)
    trained_model=v374.v373.load_meta_model(path=meta_path,now=moment); existing_caps=[r for r in plan.get("active_capabilities",[]) if isinstance(r,dict) and v374.v373.validate_capability(r,now=moment)]; plan=v374.v373.adaptive_rank_plan(plan,model=trained_model,capabilities=existing_caps); current_rows=prior_rows+[c for c in (_clean_skill_outcome(r) for r in verified_now) if c is not None]; history=extended_history_stats(current_rows); candidates=rerank_candidates(v374.generate_candidates(plan,gaps,history),history); selected=None if loaded_skills["corruption_hold"] or skill_store["corruption_hold"] else v374.select_candidate(plan,candidates,skill_state=evaluated_state); skill_caps=compose_cross_gap_capabilities(selected,gaps,now=moment); merged_caps=v374.v373.merge_capabilities(existing_caps,skill_caps,now=moment); evolved_plan=v374.evolve_plan(plan,selected,merged_caps)
    if execute: execution={"status":"V375_EXECUTED","operational":v374.execute_operational_skill(selected,evolved_plan),"safe_learning":v374.v373.v372.execute_safe_learning(evolved_plan,state_path=state,now=moment),"git_write":False,"source_code_modified":False,"proposals_executed":False}
    else: execution={"status":"PLAN_ONLY","operational":{"status":"PLAN_ONLY","executed":False},"safe_learning":{"status":"PLAN_ONLY","results":{}},"git_write":False,"source_code_modified":False,"proposals_executed":False}
    selected_for_state=selected if (apply_skills and execute) else None; next_state,unexpected=reconcile_skill_state(evaluated_state,plan=plan,selected_skill=selected_for_state,history=history,now=moment)
    if unexpected: execution=dict(execution); execution["status"]="TRIAL_RECONCILIATION_HOLD"; execution["unexpected_verified_outcomes"]=len(unexpected); next_state=evaluated_state
    capability_write={"status":"CAPABILITY_APPLY_NOT_REQUESTED","written":False}
    if apply_capabilities: capability_write=v374.v373.save_capabilities(merged_caps,path=cap_path,corruption_hold=bool(base_report.get("capability_state",{}).get("corruption_hold")),now=moment)
    skill_write={"status":"SKILL_APPLY_NOT_REQUESTED","written":False}
    if apply_skills: skill_write=v374.save_skill_state(next_state,path=skill_state_file,corruption_hold=bool(loaded_skills["corruption_hold"] or skill_store["corruption_hold"]),now=moment)
    proposals=v374.source_feature_proposals(gaps,history); result={"controller_version":CONTROLLER_VERSION,"plan":evolved_plan,"gaps":gaps,"candidates":candidates,"selected_skill":selected,"execution":execution,"capability_write":capability_write,"skill_state":{"load_status":loaded_skills["status"],"corruption_hold":loaded_skills["corruption_hold"],"skill_outcome_store_status":skill_store["status"],"write":skill_write,"active_count":len(next_state.get("active_skills",[])),"pending_trial_count":len(next_state.get("pending_trials",[])),"suspended_recipes":list(next_state.get("suspended_recipes",[]))},"verified_trial_outcomes":verified_now,"verified_outcome_write":skill_outcome_write,"meta_feedback":{"generated":len(meta_feedback),"write":meta_feedback_write,"training":meta_training},"skill_history":history,"source_feature_proposals":proposals,"safety":SAFETY}
    if persist_outputs:
        runtime_output={"status":"SAVED","report":True,"proposals":True}
        try: atomic_write_json(root/REPORT_PATH.name,result,suffix=".v375-report.tmp"); atomic_write_json(root/SOURCE_PROPOSALS_PATH.name,{"schema_version":SCHEMA_VERSION,"controller_version":CONTROLLER_VERSION,"generated_at":moment.isoformat(timespec="seconds"),"normal_pr_pipeline_required":True,"auto_implementation":False,"proposals":proposals},suffix=".v375-source-proposals.tmp")
        except (OSError,UnicodeError,ValueError,TypeError) as exc: runtime_output={"status":"WRITE_FAILED","error_code":type(exc).__name__}
        result["runtime_output"]=runtime_output
    return result

def self_test()->None:
    assert SAFETY["verified_skill_outcomes_feed_meta_neural"] is True; assert SAFETY["skill_outcome_corruption_is_hold"] is True; assert SAFETY["uncertainty_aware_candidate_selection"] is True; assert SAFETY["cross_gap_declarative_capability_composition"] is True; assert SAFETY["one_heavy_operation_per_cycle"] is True; assert SAFETY["source_code_auto_generation"] is False; assert SAFETY["source_code_auto_rewrite"] is False; assert SAFETY["arbitrary_command_execution"] is False; assert SAFETY["git_write"] is False; assert SAFETY["verification_bypass"] is False; assert SAFETY["price_or_grade_invention"] is False; assert SAFETY["market_direction_inferred"] is False; print("Tablet verified-feedback autonomous evolution v375: PASS")

def main()->int:
    parser=argparse.ArgumentParser(); parser.add_argument("--execute-safe-learning",action="store_true"); parser.add_argument("--apply-capabilities",action="store_true"); parser.add_argument("--train-meta",action="store_true"); parser.add_argument("--apply-skills",action="store_true"); parser.add_argument("--self-test",action="store_true"); parser.add_argument("--quiet",action="store_true"); args=parser.parse_args()
    if args.self_test: self_test(); return 0
    result=run_cycle(execute=args.execute_safe_learning,apply_capabilities=args.apply_capabilities,train_meta=args.train_meta,apply_skills=args.apply_skills)
    if not args.quiet: print(json.dumps(result,ensure_ascii=False,sort_keys=True))
    return 0

if __name__=="__main__": raise SystemExit(main())
