#!/usr/bin/env python3
"""Transactional verified-feedback autonomy for Tablet GPT / TCG Grader.

V376 keeps V375's bounded neural/capability evolution and adds a durable evidence
commit barrier around autonomous execution:
- prior verified outcomes and meta feedback must settle before a new action;
- autonomous execution requires durable skill-state and capability persistence;
- a local execution journal prevents ambiguous retries after crashes/write failures;
- a sanitized exchange capsule exposes verified operational context without model
  weights, secrets, raw grading calibration, or automatic fact/price/grade promotion.

The runtime still cannot generate/rewrite source code, execute arbitrary commands,
write Git/main, bypass CI, infer market direction, or invent card facts/prices/grades.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tablet_autonomous_evolution_v375 as v375
from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
CONTROLLER_VERSION = "v376"
SCHEMA_VERSION = 6
REPORT_PATH = ROOT / "tablet_autonomy_v376_report.json"
EXCHANGE_CAPSULE_PATH = ROOT / "tablet_autonomy_exchange_capsule_v376.json"
EXECUTION_JOURNAL_PATH = ROOT / "tablet_autonomy_execution_journal_v376.json"
MAX_JOURNAL_BYTES = 512_000

SAFETY = dict(v375.SAFETY)
SAFETY.update({
    "prior_evidence_commit_required_before_new_execution": True,
    "meta_feedback_requires_skill_evidence_commit": True,
    "execution_requires_skill_state_persistence": True,
    "execution_requires_capability_persistence": True,
    "ambiguous_execution_retry_forbidden": True,
    "execution_journal_fail_closed": True,
    "sanitized_exchange_capsule_enabled": True,
    "exchange_capsule_exports_model_weights": False,
    "exchange_capsule_exports_secrets": False,
    "exchange_capsule_exports_raw_grading_calibration": False,
    "source_code_auto_generation": False,
    "source_code_auto_rewrite": False,
    "arbitrary_command_execution": False,
    "git_write": False,
    "direct_main_write": False,
    "verification_bypass": False,
    "trust_or_fact_auto_promotion": False,
    "price_or_grade_invention": False,
    "market_direction_inferred": False,
})

_HARD_FAILURE_TOKENS = ("FAILED", "CORRUPTION_HOLD", "INVALID")
_JOURNAL_STATES = {"PREPARED", "EXECUTED_UNCOMMITTED", "COMMITTED", "ABORTED_NO_EXECUTION"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _strict_json(path: Path, *, max_bytes: int = MAX_JOURNAL_BYTES) -> dict[str, Any] | None:
    try:
        if not path.is_file() or path.is_symlink():
            return None
        value = json.loads(safe_read_text(path, max_bytes=max_bytes))
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def load_execution_journal(*, path: Path = EXECUTION_JOURNAL_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"status": "fresh", "recovery_hold": False, "record": None}
    row = _strict_json(path)
    if row is None:
        return {"status": "corrupt", "recovery_hold": True, "record": None}
    status = str(row.get("status") or "")
    cycle_id = str(row.get("cycle_id") or "")
    if (
        row.get("schema_version") != SCHEMA_VERSION
        or row.get("controller_version") != CONTROLLER_VERSION
        or status not in _JOURNAL_STATES
        or len(cycle_id) != 64
        or any(ch not in "0123456789abcdef" for ch in cycle_id.lower())
    ):
        return {"status": "corrupt", "recovery_hold": True, "record": None}
    return {
        "status": "loaded",
        "recovery_hold": status in {"PREPARED", "EXECUTED_UNCOMMITTED"},
        "record": row,
    }


def _write_journal(payload: dict[str, Any], *, path: Path) -> dict[str, Any]:
    if (
        payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("controller_version") != CONTROLLER_VERSION
        or str(payload.get("status") or "") not in _JOURNAL_STATES
    ):
        return {"status": "INVALID_EXECUTION_JOURNAL", "written": False}
    try:
        atomic_write_json(path, payload, suffix=".v376-execution-journal.tmp")
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        return {"status": "EXECUTION_JOURNAL_WRITE_FAILED", "written": False, "error_code": type(exc).__name__}
    return {"status": "EXECUTION_JOURNAL_SAVED", "written": True}


def _hard_failure(status: Any) -> bool:
    text = str(status or "")
    return any(token in text for token in _HARD_FAILURE_TOKENS)


def evidence_commit_barrier(result: dict[str, Any], *, apply_skills: bool, train_meta: bool) -> dict[str, Any]:
    reasons: list[str] = []
    skill = result.get("skill_state") if isinstance(result.get("skill_state"), dict) else {}
    if skill.get("corruption_hold") is True:
        reasons.append("SKILL_STATE_CORRUPTION_HOLD")
    if str(skill.get("skill_outcome_store_status") or "") == "corrupt":
        reasons.append("SKILL_OUTCOME_CORRUPTION_HOLD")
    if apply_skills:
        state_write = skill.get("write") if isinstance(skill.get("write"), dict) else {}
        if state_write.get("written") is not True:
            reasons.append(str(state_write.get("status") or "SKILL_STATE_NOT_DURABLE"))
        outcome_write = result.get("verified_outcome_write") if isinstance(result.get("verified_outcome_write"), dict) else {}
        if _hard_failure(outcome_write.get("status")):
            reasons.append(str(outcome_write.get("status")))
        meta = result.get("meta_feedback") if isinstance(result.get("meta_feedback"), dict) else {}
        meta_write = meta.get("write") if isinstance(meta.get("write"), dict) else {}
        if _hard_failure(meta_write.get("status")):
            reasons.append(str(meta_write.get("status")))
        training = meta.get("training") if isinstance(meta.get("training"), dict) else {}
        if train_meta and _hard_failure(training.get("status")):
            reasons.append(str(training.get("status")))
    return {
        "ok": not reasons,
        "status": "EVIDENCE_COMMIT_OK" if not reasons else "EVIDENCE_COMMIT_HOLD",
        "reasons": sorted(set(reasons)),
    }


def neural_reliability(result: dict[str, Any], *, model_path: Path, now: datetime) -> dict[str, Any]:
    model = v375.v374.v373.load_meta_model(path=model_path, now=now)
    meta_samples = int(model.get("sample_count") or 0) if isinstance(model, dict) else 0
    history = result.get("skill_history") if isinstance(result.get("skill_history"), dict) else {}
    skill_samples = sum(int(row.get("samples") or 0) for row in history.values() if isinstance(row, dict))
    covered = sum(1 for row in history.values() if isinstance(row, dict) and int(row.get("samples") or 0) > 0)
    confidence = min(
        1.0,
        0.50 * min(1.0, skill_samples / 32.0)
        + 0.30 * min(1.0, meta_samples / 32.0)
        + 0.20 * min(1.0, covered / 5.0),
    )
    return {
        "advisory_only": True,
        "meta_verified_samples": meta_samples,
        "skill_verified_samples": skill_samples,
        "covered_recipes": covered,
        "confidence": round(confidence, 6),
        "unverified_prediction_not_promoted": True,
    }


def market_context(result: dict[str, Any]) -> dict[str, Any]:
    plan = result.get("plan") if isinstance(result.get("plan"), dict) else {}
    gaps = result.get("gaps") if isinstance(result.get("gaps"), list) else []
    return {
        "regime": v375.v374.v373.market_regime(plan),
        "gap_kinds": sorted({str(row.get("kind") or "") for row in gaps if isinstance(row, dict) and row.get("kind")}),
        "market_direction_inferred": False,
    }


def build_exchange_capsule(
    result: dict[str, Any], *, cycle_id: str, journal_status: str,
    barrier: dict[str, Any], reliability: dict[str, Any], now: datetime,
) -> dict[str, Any]:
    selected = result.get("selected_skill") if isinstance(result.get("selected_skill"), dict) else None
    meta = result.get("meta_feedback") if isinstance(result.get("meta_feedback"), dict) else {}
    proposal_rows = result.get("source_feature_proposals") if isinstance(result.get("source_feature_proposals"), list) else []
    payload = {
        "schema_version": SCHEMA_VERSION,
        "controller_version": CONTROLLER_VERSION,
        "generated_at": now.isoformat(timespec="seconds"),
        "cycle_id": cycle_id,
        "journal_status": journal_status,
        "evidence_barrier": deepcopy(barrier),
        "neural_reliability": deepcopy(reliability),
        "market_context": market_context(result),
        "selected_skill": None if selected is None else {
            "skill_id": str(selected.get("skill_id") or "")[:128],
            "recipe": str(selected.get("recipe") or "")[:64],
            "score": selected.get("v375_score", selected.get("score")),
            "risk": selected.get("risk"),
            "cost": selected.get("cost"),
        },
        "skill_state": deepcopy(result.get("skill_state") if isinstance(result.get("skill_state"), dict) else {}),
        "meta_feedback": {
            "generated": int(meta.get("generated") or 0),
            "write_status": str((meta.get("write") or {}).get("status") or "") if isinstance(meta.get("write"), dict) else "",
            "training_status": str((meta.get("training") or {}).get("status") or "") if isinstance(meta.get("training"), dict) else "",
        },
        "source_proposal_count": len(proposal_rows),
        "exchange_policy": {
            "verified_operational_summary_only": True,
            "model_weights_exported": False,
            "secrets_exported": False,
            "raw_grading_calibration_exported": False,
            "fact_price_grade_auto_promoted": False,
            "source_change_auto_applied": False,
        },
    }
    payload["capsule_sha256"] = _canonical_digest(payload)
    return payload


def _persist_outputs(result: dict[str, Any], capsule: dict[str, Any], *, root: Path) -> dict[str, Any]:
    try:
        atomic_write_json(root / REPORT_PATH.name, result, suffix=".v376-report.tmp")
        atomic_write_json(root / EXCHANGE_CAPSULE_PATH.name, capsule, suffix=".v376-exchange.tmp")
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        return {"status": "WRITE_FAILED", "error_code": type(exc).__name__}
    return {"status": "SAVED", "report": True, "exchange_capsule": True}


def _hold_result(
    base: dict[str, Any], *, status: str, reason: str, cycle_id: str,
    journal_status: str, barrier: dict[str, Any], reliability: dict[str, Any],
    now: datetime, root: Path, persist_outputs: bool,
) -> dict[str, Any]:
    result = deepcopy(base)
    result.update({
        "controller_version": CONTROLLER_VERSION,
        "v376_status": status,
        "execution": {
            "status": status,
            "executed": False,
            "reason": reason,
            "git_write": False,
            "source_code_modified": False,
            "proposals_executed": False,
        },
        "evidence_barrier": barrier,
        "neural_reliability": reliability,
        "execution_journal": {"status": journal_status},
        "safety": SAFETY,
    })
    capsule = build_exchange_capsule(
        result, cycle_id=cycle_id, journal_status=journal_status,
        barrier=barrier, reliability=reliability, now=now,
    )
    result["exchange_capsule"] = capsule
    if persist_outputs:
        result["runtime_output"] = _persist_outputs(result, capsule, root=root)
    return result


def run_cycle(
    *, execute: bool = False, apply_capabilities: bool = False, train_meta: bool = False,
    apply_skills: bool = False, root: Path = ROOT, now: datetime | None = None,
    proc_root: Path = Path("/proc"), state_path: Path | None = None,
    capability_path: Path | None = None, meta_model_path: Path | None = None,
    meta_outcomes_path: Path | None = None, skill_state_path: Path | None = None,
    skill_outcomes_path: Path | None = None, journal_path: Path | None = None,
    persist_outputs: bool = True,
) -> dict[str, Any]:
    moment = (now or _now()).astimezone(timezone.utc)
    cap_path = capability_path or (root / v375.v374.v373.CAPABILITY_PATH.name)
    meta_path = meta_model_path or (root / v375.v374.v373.META_MODEL_PATH.name)
    skill_state_file = skill_state_path or (root / v375.v374.SKILL_STATE_PATH.name)
    journal_file = journal_path or (root / EXECUTION_JOURNAL_PATH.name)
    plan_only = dict(
        execute=False, apply_capabilities=False, train_meta=False, apply_skills=False,
        root=root, now=moment, proc_root=proc_root, state_path=state_path,
        capability_path=cap_path, meta_model_path=meta_path,
        meta_outcomes_path=meta_outcomes_path, skill_state_path=skill_state_file,
        skill_outcomes_path=skill_outcomes_path, persist_outputs=False,
    )

    journal = load_execution_journal(path=journal_file)
    if journal["recovery_hold"]:
        base = v375.run_cycle(**plan_only)
        barrier = {"ok": False, "status": "EXECUTION_RECOVERY_HOLD", "reasons": ["AMBIGUOUS_PRIOR_EXECUTION"]}
        reliability = neural_reliability(base, model_path=meta_path, now=moment)
        cycle_id = str((journal.get("record") or {}).get("cycle_id") or "0" * 64)
        return _hold_result(
            base, status="EXECUTION_RECOVERY_HOLD",
            reason="prior execution journal is not committed; do not repeat autonomously",
            cycle_id=cycle_id,
            journal_status=str((journal.get("record") or {}).get("status") or journal["status"]),
            barrier=barrier, reliability=reliability, now=moment, root=root,
            persist_outputs=persist_outputs,
        )

    if execute and (not apply_skills or not apply_capabilities):
        base = v375.run_cycle(**plan_only)
        barrier = {
            "ok": False,
            "status": "EXECUTION_PERSISTENCE_PRECONDITION_HOLD",
            "reasons": ["EXECUTION_REQUIRES_APPLY_SKILLS_AND_CAPABILITIES"],
        }
        reliability = neural_reliability(base, model_path=meta_path, now=moment)
        return _hold_result(
            base, status="EXECUTION_PERSISTENCE_PRECONDITION_HOLD",
            reason="autonomous execution requires durable skill and capability state",
            cycle_id="0" * 64, journal_status="NOT_STARTED", barrier=barrier,
            reliability=reliability, now=moment, root=root, persist_outputs=persist_outputs,
        )

    settled = v375.run_cycle(
        execute=False, apply_capabilities=False, train_meta=train_meta,
        apply_skills=apply_skills, root=root, now=moment, proc_root=proc_root,
        state_path=state_path, capability_path=cap_path, meta_model_path=meta_path,
        meta_outcomes_path=meta_outcomes_path, skill_state_path=skill_state_file,
        skill_outcomes_path=skill_outcomes_path, persist_outputs=False,
    )
    barrier = evidence_commit_barrier(settled, apply_skills=apply_skills, train_meta=train_meta)

    capability_write = {"status": "CAPABILITY_APPLY_NOT_REQUESTED", "written": False}
    desired_caps = settled.get("plan", {}).get("v374_active_capabilities", []) if isinstance(settled.get("plan"), dict) else []
    if apply_capabilities and barrier["ok"]:
        capability_store = v375.v374.v373.load_capabilities(path=cap_path, now=moment)
        if capability_store.get("corruption_hold") is True:
            barrier = {
                "ok": False,
                "status": "EVIDENCE_COMMIT_HOLD",
                "reasons": sorted(set(barrier["reasons"] + ["CAPABILITY_CORRUPTION_HOLD"])),
            }
            capability_write = {"status": "CAPABILITY_CORRUPTION_HOLD", "written": False}
        else:
            capability_write = v375.v374.v373.save_capabilities(
                desired_caps if isinstance(desired_caps, list) else [],
                path=cap_path, corruption_hold=False, now=moment,
            )
            if capability_write.get("written") is not True:
                barrier = {
                    "ok": False,
                    "status": "EVIDENCE_COMMIT_HOLD",
                    "reasons": sorted(set(barrier["reasons"] + [str(capability_write.get("status") or "CAPABILITY_NOT_DURABLE")])),
                }
    settled["capability_write"] = capability_write
    reliability = neural_reliability(settled, model_path=meta_path, now=moment)
    selected = settled.get("selected_skill") if isinstance(settled.get("selected_skill"), dict) else None
    cycle_id = _canonical_digest({
        "time": moment.isoformat(timespec="seconds"),
        "selected": selected,
        "market": market_context(settled),
        "plan_digest": _canonical_digest(settled.get("plan", {})),
    })

    if not barrier["ok"]:
        return _hold_result(
            settled, status="EVIDENCE_COMMIT_HOLD",
            reason="prior verified evidence or durable controller state did not commit",
            cycle_id=cycle_id, journal_status="NOT_STARTED", barrier=barrier,
            reliability=reliability, now=moment, root=root, persist_outputs=persist_outputs,
        )
    if not execute or selected is None:
        status = "PLAN_ONLY" if not execute else "NO_ELIGIBLE_AUTONOMOUS_ACTION"
        return _hold_result(
            settled, status=status,
            reason="planning only" if not execute else "no eligible verified candidate",
            cycle_id=cycle_id, journal_status="NOT_STARTED", barrier=barrier,
            reliability=reliability, now=moment, root=root, persist_outputs=persist_outputs,
        )

    prepared = {
        "schema_version": SCHEMA_VERSION,
        "controller_version": CONTROLLER_VERSION,
        "cycle_id": cycle_id,
        "status": "PREPARED",
        "prepared_at": moment.isoformat(timespec="seconds"),
        "selected_skill_id": str(selected.get("skill_id") or "")[:128],
        "selected_recipe": str(selected.get("recipe") or "")[:64],
        "plan_sha256": _canonical_digest(settled.get("plan", {})),
        "market_context": market_context(settled),
        "git_write": False,
        "source_code_modified": False,
    }
    journal_write = _write_journal(prepared, path=journal_file)
    if journal_write.get("written") is not True:
        hold = {
            "ok": False,
            "status": "EXECUTION_JOURNAL_HOLD",
            "reasons": [str(journal_write.get("status") or "EXECUTION_JOURNAL_WRITE_FAILED")],
        }
        return _hold_result(
            settled, status="EXECUTION_JOURNAL_HOLD",
            reason="execution intent could not be durably journaled",
            cycle_id=cycle_id, journal_status="WRITE_FAILED", barrier=hold,
            reliability=reliability, now=moment, root=root, persist_outputs=persist_outputs,
        )

    operational = v375.v374.execute_operational_skill(selected, settled["plan"])
    safe_learning = v375.v374.v373.v372.execute_safe_learning(
        settled["plan"],
        state_path=state_path or (root / v375.v374.v373.v372.STATE_PATH.name),
        now=moment,
    )
    executed_record = deepcopy(prepared)
    executed_record.update({
        "status": "EXECUTED_UNCOMMITTED",
        "executed_at": moment.isoformat(timespec="seconds"),
        "operational_status": str(operational.get("status") or ""),
        "safe_learning_status": str(safe_learning.get("status") or ""),
    })
    after_exec_write = _write_journal(executed_record, path=journal_file)
    if after_exec_write.get("written") is not True:
        hold = {
            "ok": False,
            "status": "EXECUTED_JOURNAL_COMMIT_HOLD",
            "reasons": [str(after_exec_write.get("status") or "EXECUTION_JOURNAL_WRITE_FAILED")],
        }
        result = _hold_result(
            settled, status="EXECUTED_JOURNAL_COMMIT_HOLD",
            reason="action may have executed but durable post-action journal commit failed; automatic retry is forbidden",
            cycle_id=cycle_id, journal_status="PREPARED", barrier=hold,
            reliability=reliability, now=moment, root=root, persist_outputs=False,
        )
        result["execution"] = {
            "status": "EXECUTED_JOURNAL_COMMIT_HOLD",
            "executed": True,
            "operational": operational,
            "safe_learning": safe_learning,
            "git_write": False,
            "source_code_modified": False,
            "proposals_executed": False,
        }
        capsule = build_exchange_capsule(
            result, cycle_id=cycle_id, journal_status="PREPARED",
            barrier=hold, reliability=reliability, now=moment,
        )
        result["exchange_capsule"] = capsule
        if persist_outputs:
            result["runtime_output"] = _persist_outputs(result, capsule, root=root)
        return result

    loaded = v375.v374.load_skill_state(path=skill_state_file, now=moment)
    if loaded.get("corruption_hold") is True:
        hold = {"ok": False, "status": "EXECUTED_STATE_COMMIT_HOLD", "reasons": ["SKILL_STATE_CORRUPTION_HOLD"]}
        result = _hold_result(
            settled, status="EXECUTED_STATE_COMMIT_HOLD",
            reason="action executed but skill state is corrupt; automatic retry is forbidden",
            cycle_id=cycle_id, journal_status="EXECUTED_UNCOMMITTED", barrier=hold,
            reliability=reliability, now=moment, root=root, persist_outputs=False,
        )
        result["execution"]["executed"] = True
        if persist_outputs:
            result["runtime_output"] = _persist_outputs(result, result["exchange_capsule"], root=root)
        return result

    next_state, unexpected = v375.reconcile_skill_state(
        loaded["state"], plan=settled["plan"], selected_skill=selected,
        history=settled.get("skill_history", {}), now=moment,
    )
    if unexpected:
        hold = {"ok": False, "status": "EXECUTED_STATE_COMMIT_HOLD", "reasons": ["UNEXPECTED_VERIFIED_OUTCOME_DURING_COMMIT"]}
        result = _hold_result(
            settled, status="EXECUTED_STATE_COMMIT_HOLD",
            reason="unexpected state transition during commit; automatic retry is forbidden",
            cycle_id=cycle_id, journal_status="EXECUTED_UNCOMMITTED", barrier=hold,
            reliability=reliability, now=moment, root=root, persist_outputs=False,
        )
        result["execution"]["executed"] = True
        if persist_outputs:
            result["runtime_output"] = _persist_outputs(result, result["exchange_capsule"], root=root)
        return result

    state_write = v375.v374.save_skill_state(next_state, path=skill_state_file, corruption_hold=False, now=moment)
    if state_write.get("written") is not True:
        hold = {"ok": False, "status": "EXECUTED_STATE_COMMIT_HOLD", "reasons": [str(state_write.get("status") or "SKILL_STATE_WRITE_FAILED")]}
        result = _hold_result(
            settled, status="EXECUTED_STATE_COMMIT_HOLD",
            reason="action executed but pending trial state did not commit; automatic retry is forbidden",
            cycle_id=cycle_id, journal_status="EXECUTED_UNCOMMITTED", barrier=hold,
            reliability=reliability, now=moment, root=root, persist_outputs=False,
        )
        result["execution"]["executed"] = True
        if persist_outputs:
            result["runtime_output"] = _persist_outputs(result, result["exchange_capsule"], root=root)
        return result

    committed = deepcopy(executed_record)
    committed.update({
        "status": "COMMITTED",
        "committed_at": moment.isoformat(timespec="seconds"),
        "skill_state_status": str(state_write.get("status") or ""),
    })
    final_journal_write = _write_journal(committed, path=journal_file)
    journal_status = "COMMITTED" if final_journal_write.get("written") is True else "EXECUTED_UNCOMMITTED"
    final_status = "V376_EXECUTED" if journal_status == "COMMITTED" else "EXECUTED_STATE_COMMIT_HOLD"
    final_barrier = barrier
    if journal_status != "COMMITTED":
        final_barrier = {
            "ok": False,
            "status": "EXECUTED_STATE_COMMIT_HOLD",
            "reasons": [str(final_journal_write.get("status") or "EXECUTION_JOURNAL_WRITE_FAILED")],
        }

    result = deepcopy(settled)
    result.update({
        "controller_version": CONTROLLER_VERSION,
        "v376_status": final_status,
        "execution": {
            "status": final_status,
            "executed": True,
            "operational": operational,
            "safe_learning": safe_learning,
            "git_write": False,
            "source_code_modified": False,
            "proposals_executed": False,
        },
        "evidence_barrier": final_barrier,
        "neural_reliability": reliability,
        "execution_journal": {"status": journal_status, "cycle_id": cycle_id},
        "safety": SAFETY,
    })
    result["skill_state"] = dict(result.get("skill_state") or {})
    result["skill_state"].update({
        "write": state_write,
        "active_count": len(next_state.get("active_skills", [])),
        "pending_trial_count": len(next_state.get("pending_trials", [])),
        "suspended_recipes": list(next_state.get("suspended_recipes", [])),
    })
    capsule = build_exchange_capsule(
        result, cycle_id=cycle_id, journal_status=journal_status,
        barrier=final_barrier, reliability=reliability, now=moment,
    )
    result["exchange_capsule"] = capsule
    if persist_outputs:
        result["runtime_output"] = _persist_outputs(result, capsule, root=root)
    return result


def self_test() -> None:
    assert SAFETY["prior_evidence_commit_required_before_new_execution"] is True
    assert SAFETY["ambiguous_execution_retry_forbidden"] is True
    assert SAFETY["execution_journal_fail_closed"] is True
    assert SAFETY["sanitized_exchange_capsule_enabled"] is True
    assert SAFETY["source_code_auto_generation"] is False
    assert SAFETY["arbitrary_command_execution"] is False
    assert SAFETY["git_write"] is False
    assert SAFETY["verification_bypass"] is False
    assert SAFETY["price_or_grade_invention"] is False
    assert SAFETY["market_direction_inferred"] is False
    print("Tablet transactional autonomous evolution v376: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-safe-learning", action="store_true")
    parser.add_argument("--apply-capabilities", action="store_true")
    parser.add_argument("--train-meta", action="store_true")
    parser.add_argument("--apply-skills", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    result = run_cycle(
        execute=args.execute_safe_learning,
        apply_capabilities=args.apply_capabilities,
        train_meta=args.train_meta,
        apply_skills=args.apply_skills,
    )
    if not args.quiet:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    holds = {
        "EXECUTION_RECOVERY_HOLD",
        "EXECUTION_PERSISTENCE_PRECONDITION_HOLD",
        "EVIDENCE_COMMIT_HOLD",
        "EXECUTION_JOURNAL_HOLD",
        "EXECUTED_JOURNAL_COMMIT_HOLD",
        "EXECUTED_STATE_COMMIT_HOLD",
    }
    return 2 if result.get("v376_status") in holds else 0


if __name__ == "__main__":
    raise SystemExit(main())
