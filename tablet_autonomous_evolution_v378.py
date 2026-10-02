#!/usr/bin/env python3
"""100+1000 governed autonomous evolution for Tablet GPT / TCG Grader.

V378 preserves V377's single-run mutation lock and V376's transactional evidence
barrier, while connecting the existing 100-senior preparation + 1000-cell expert
review policy directly to autonomous mutation governance.

It does not create arbitrary source code, write Git/main, invent facts/prices/
grades/market direction, relax verification, or auto-promote trust. Runtime
self-evolution remains limited to already-verified neural learners and the
allowlisted declarative capability DSL inherited from V373-V377. Source-level
feature gaps are emitted only as PR-required, non-executable proposals.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any

import quality_review_policy
import tablet_autonomous_evolution_v377 as v377
from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
CONTROLLER_VERSION = "v378"
CORE_CONTROLLER_VERSION = "v377"
REPORT_PATH = ROOT / "tablet_autonomy_v378_report.json"
LOCK_PATH = ROOT / ".tablet_autonomy_execution_v378.lock"
QUALITY_POLICY_PATH = ROOT / "quality_review_policy_v2.json"
MAX_POLICY_BYTES = 1_000_000

SAFETY = dict(v377.SAFETY)
SAFETY.update({
    "quality_100_senior_prep_required": True,
    "quality_1000_review_cells_required": True,
    "quality_policy_fail_closed_before_mutation": True,
    "quality_blocker_cannot_be_outvoted": True,
    "verified_neural_council_enabled": True,
    "verified_neural_council_advisory_only": True,
    "market_regime_adaptation_operational_only": True,
    "market_direction_inferred": False,
    "declarative_runtime_self_extension_allowed": True,
    "declarative_runtime_self_extension_allowlisted_only": True,
    "source_level_feature_gap_pr_required": True,
    "source_level_feature_auto_implementation": False,
    "source_code_auto_generation": False,
    "source_code_auto_rewrite": False,
    "arbitrary_command_generation": False,
    "arbitrary_command_execution": False,
    "git_write": False,
    "direct_main_write": False,
    "verification_bypass": False,
    "trust_or_fact_auto_promotion": False,
    "price_or_grade_invention": False,
})

_HOLD_STATUSES = set(getattr(v377, "_HOLD_STATUSES", set())) | {
    "QUALITY_GOVERNANCE_HOLD",
    "V378_LOCK_UNAVAILABLE",
    "V378_CONCURRENT_AUTONOMY_HOLD",
}


def _mutating_requested(*, execute: bool, apply_capabilities: bool, train_meta: bool, apply_skills: bool) -> bool:
    return bool(execute or apply_capabilities or train_meta or apply_skills)


def _policy_digest(path: Path) -> str | None:
    try:
        if not path.is_file() or path.is_symlink():
            return None
        raw = safe_read_text(path, max_bytes=MAX_POLICY_BYTES).encode("utf-8")
    except (OSError, UnicodeError, ValueError, TypeError):
        return None
    return hashlib.sha256(raw).hexdigest()


def quality_governance(path: Path = QUALITY_POLICY_PATH) -> dict[str, Any]:
    try:
        checked = quality_review_policy.validate(path)
    except Exception as exc:
        checked = {"ok": False, "errors": [f"validator_error:{type(exc).__name__}"]}
    ok = checked.get("ok") is True
    prep = int(checked.get("preparation_senior_perspectives") or 0)
    cells = int(checked.get("review_cells") or 0)
    ready = ok and prep == 100 and cells == 1000
    return {
        "ok": ready,
        "status": "QUALITY_100_1000_READY" if ready else "QUALITY_GOVERNANCE_HOLD",
        "preparation_senior_perspectives": prep,
        "expert_groups": int(checked.get("expert_groups") or 0),
        "review_lenses": int(checked.get("review_lenses") or 0),
        "review_cells": cells,
        "preparation_before_expert_review": checked.get("preparation_before_expert_review") is True,
        "policy_sha256": _policy_digest(path),
        "errors": list(checked.get("errors") or []),
        "external_human_review_claimed": False,
        "blocker_can_be_outvoted": False,
    }


def _score_model(row: Any) -> float | None:
    if not isinstance(row, dict):
        return None
    status = str(row.get("status") or "").lower()
    if status == "active":
        return 1.0
    if status in {"healthy", "ready"}:
        return 0.9
    if status == "inactive":
        labels = row.get("label_count")
        return 0.65 if isinstance(labels, int) and labels >= 1000 else 0.35
    if status == "degraded":
        return 0.25
    if status == "broken":
        return 0.0
    return None


def _bounded_score(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not (number == number and abs(number) != float("inf")):
        return None
    return max(0.0, min(1.0, number))


def neural_council(result: dict[str, Any]) -> dict[str, Any]:
    plan = result.get("plan") if isinstance(result.get("plan"), dict) else {}
    signals = plan.get("signals") if isinstance(plan.get("signals"), dict) else {}
    runtime = signals.get("runtime_models") if isinstance(signals.get("runtime_models"), dict) else {}
    models = runtime.get("models") if isinstance(runtime.get("models"), dict) else {}
    repair = signals.get("repair_neural") if isinstance(signals.get("repair_neural"), dict) else {}
    reliability = result.get("neural_reliability") if isinstance(result.get("neural_reliability"), dict) else {}
    selected = result.get("selected_skill") if isinstance(result.get("selected_skill"), dict) else {}

    members: list[dict[str, Any]] = []
    for name in ("query_strategy", "job_strategy"):
        score = _score_model(models.get(name))
        if score is not None:
            members.append({"id": name, "score": round(score, 6), "verified_runtime_signal": True})

    repair_score = None
    if repair:
        if repair.get("active") is True and repair.get("requires_attention") is not True:
            repair_score = 1.0
        elif repair.get("requires_attention") is True:
            repair_score = 0.25
        elif repair.get("active") is False:
            repair_score = 0.35
    if repair_score is not None:
        members.append({"id": "repair_priority", "score": round(repair_score, 6), "verified_runtime_signal": True})

    meta_score = _bounded_score(reliability.get("confidence"))
    if meta_score is not None:
        members.append({"id": "meta_neural_reliability", "score": round(meta_score, 6), "verified_runtime_signal": True})

    skill_score = None
    if selected:
        raw_skill_score = selected.get("v375_score", selected.get("score", 0.0))
        try:
            skill_score = _bounded_score(float(raw_skill_score or 0.0) / 100.0)
        except (TypeError, ValueError, OverflowError):
            skill_score = None
    if skill_score is not None:
        members.append({"id": "selected_skill_confidence", "score": round(skill_score, 6), "verified_runtime_signal": True})

    scores = [float(row["score"]) for row in members]
    confidence = sum(scores) / len(scores) if scores else 0.0
    spread = max(scores) - min(scores) if len(scores) >= 2 else 0.0
    agreement = max(0.0, min(1.0, 1.0 - spread))
    readiness = "HIGH" if confidence >= 0.70 and agreement >= 0.45 else ("MEDIUM" if confidence >= 0.40 else "LOW")
    return {
        "advisory_only": True,
        "member_count": len(members),
        "members": members,
        "confidence": round(confidence, 6),
        "agreement": round(agreement, 6),
        "readiness": readiness,
        "verified_outcome_learning_only": True,
        "unverified_prediction_not_promoted": True,
    }


def adaptive_mode(result: dict[str, Any]) -> dict[str, Any]:
    try:
        context = v377.v376.market_context(result)
    except Exception:
        context = {"regime": {"regime": "UNKNOWN"}, "gap_kinds": []}
    regime_row = context.get("regime")
    regime = str(regime_row.get("regime") if isinstance(regime_row, dict) else regime_row or "UNKNOWN")
    gaps = {str(x) for x in (context.get("gap_kinds") or [])}
    plan = result.get("plan") if isinstance(result.get("plan"), dict) else {}
    signals = plan.get("signals") if isinstance(plan.get("signals"), dict) else {}
    runtime = signals.get("runtime_models") if isinstance(signals.get("runtime_models"), dict) else {}
    repair = signals.get("repair_neural") if isinstance(signals.get("repair_neural"), dict) else {}
    model_stress = runtime.get("status") == "broken" or repair.get("requires_attention") is True

    if regime == "FRESHNESS_HOLD" or "market_freshness" in gaps:
        mode = "RECOVER_FRESHNESS"
    elif regime == "COVERAGE_AND_SOURCE_STRESS":
        mode = "COMPOSED_MARKET_RECOVERY"
    elif regime == "UNDERCOVERED" or "region_coverage" in gaps:
        mode = "EXPAND_VERIFIED_COVERAGE"
    elif regime == "SOURCE_DEGRADED" or "source_health" in gaps:
        mode = "RECOVER_SOURCE_HEALTH"
    elif model_stress:
        mode = "RECOVER_VERIFIED_MODELS"
    elif regime == "HEALTHY":
        mode = "STEADY_VERIFIED_EVOLUTION"
    else:
        mode = "OBSERVE_UNCERTAIN_REGIME"
    return {
        "mode": mode,
        "market_regime": regime,
        "gap_kinds": sorted(gaps),
        "market_direction_inferred": False,
        "operational_signal_only": True,
        "allowlisted_runtime_capabilities_only": True,
    }


def improvement_queue(
    result: dict[str, Any], quality: dict[str, Any], council: dict[str, Any], mode: dict[str, Any]
) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    if quality.get("ok") is not True:
        queue.append({
            "id": "RESTORE_100_1000_QUALITY_CONTRACT",
            "priority": 100,
            "kind": "governance",
            "auto_apply": False,
            "pr_required": True,
            "reason": "quality policy is invalid or incomplete",
        })
    if council.get("readiness") == "LOW":
        queue.append({
            "id": "ACCUMULATE_VERIFIED_NEURAL_OUTCOMES",
            "priority": 75,
            "kind": "learning",
            "auto_apply": False,
            "pr_required": False,
            "reason": "neural council confidence is low; preserve existing models and collect verified outcomes",
        })
    if mode.get("mode") != "STEADY_VERIFIED_EVOLUTION":
        queue.append({
            "id": str(mode.get("mode") or "OBSERVE_UNCERTAIN_REGIME"),
            "priority": 70,
            "kind": "runtime_policy",
            "auto_apply": False,
            "pr_required": False,
            "reason": "handled only through existing allowlisted declarative capabilities and verified learners",
        })
    source_proposals = result.get("source_feature_proposals")
    if isinstance(source_proposals, list) and source_proposals:
        queue.append({
            "id": "SOURCE_LEVEL_FEATURE_GAPS",
            "priority": 65,
            "kind": "source_feature_proposal",
            "auto_apply": False,
            "pr_required": True,
            "proposal_count": len(source_proposals),
            "reason": "source-level changes require protected branch/PR/CI and full regression",
        })
    core_status = str(result.get("v377_status") or result.get("v376_status") or "")
    if core_status in _HOLD_STATUSES:
        queue.append({
            "id": "CORE_FAIL_CLOSED_RECOVERY",
            "priority": 95,
            "kind": "recovery",
            "auto_apply": False,
            "pr_required": False,
            "reason": core_status,
        })
    queue.sort(key=lambda row: (-int(row.get("priority") or 0), str(row.get("id") or "")))
    return queue


def _acquire_lock(path: Path) -> tuple[int | None, dict[str, Any]]:
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            os.close(fd)
            return None, {"status": "V378_LOCK_UNAVAILABLE", "error_code": "NOT_REGULAR_FILE"}
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        try:
            os.close(fd)
        except (OSError, UnboundLocalError):
            pass
        return None, {"status": "V378_CONCURRENT_AUTONOMY_HOLD", "error_code": "LOCK_BUSY"}
    except OSError as exc:
        try:
            os.close(fd)
        except (OSError, UnboundLocalError):
            pass
        return None, {"status": "V378_LOCK_UNAVAILABLE", "error_code": type(exc).__name__}
    return fd, {"status": "V378_LOCK_ACQUIRED", "error_code": None}


def _release_lock(fd: int) -> None:
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _quality_hold(quality: dict[str, Any]) -> dict[str, Any]:
    return {
        "controller_version": CONTROLLER_VERSION,
        "core_controller_version": CORE_CONTROLLER_VERSION,
        "v378_status": "QUALITY_GOVERNANCE_HOLD",
        "execution": {
            "status": "QUALITY_GOVERNANCE_HOLD",
            "executed": False,
            "git_write": False,
            "source_code_modified": False,
            "proposals_executed": False,
        },
        "quality_governance": quality,
        "neural_council": {
            "advisory_only": True,
            "member_count": 0,
            "members": [],
            "confidence": 0.0,
            "agreement": 0.0,
            "readiness": "HOLD",
        },
        "adaptive_mode": {
            "mode": "QUALITY_HOLD",
            "market_regime": "UNKNOWN",
            "market_direction_inferred": False,
            "operational_signal_only": True,
        },
        "improvement_queue": [{
            "id": "RESTORE_100_1000_QUALITY_CONTRACT",
            "priority": 100,
            "kind": "governance",
            "auto_apply": False,
            "pr_required": True,
        }],
        "v378_single_run_lock": {"status": "NOT_ATTEMPTED", "error_code": None},
        "safety": SAFETY,
    }


def _decorate(result: dict[str, Any], quality: dict[str, Any], outer_lock: dict[str, Any]) -> dict[str, Any]:
    row = dict(result)
    row["core_controller_version"] = str(row.get("controller_version") or CORE_CONTROLLER_VERSION)
    row["controller_version"] = CONTROLLER_VERSION
    row["v378_status"] = str(row.get("v377_status") or row.get("v376_status") or row.get("status") or "UNKNOWN")
    council = neural_council(row)
    mode = adaptive_mode(row)
    row["quality_governance"] = quality
    row["neural_council"] = council
    row["adaptive_mode"] = mode
    row["improvement_queue"] = improvement_queue(row, quality, council, mode)
    row["v378_single_run_lock"] = outer_lock
    row["evolution_contract"] = {
        "runtime_self_added_functions": "allowlisted_declarative_capabilities_only",
        "source_level_new_functions": "proposal_only_pr_ci_required",
        "existing_function_tuning": "verified_outcomes_only",
        "market_adaptation": "freshness_coverage_source_health_only",
        "market_direction_prediction": False,
        "quality_release_gate": quality.get("ok") is True,
        "simulated_review_perspectives": 100,
        "simulated_review_cells": 1000,
        "external_human_review_claimed": False,
    }
    row["safety"] = SAFETY
    return row


def run_cycle(
    *, execute: bool = False, apply_capabilities: bool = False, train_meta: bool = False,
    apply_skills: bool = False, root: Path = ROOT, now=None, proc_root: Path = Path("/proc"),
    state_path: Path | None = None, capability_path: Path | None = None,
    meta_model_path: Path | None = None, meta_outcomes_path: Path | None = None,
    skill_state_path: Path | None = None, skill_outcomes_path: Path | None = None,
    journal_path: Path | None = None, lock_path: Path | None = None,
    quality_policy_path: Path | None = None, persist_outputs: bool = True,
) -> dict[str, Any]:
    policy_path = quality_policy_path or (root / QUALITY_POLICY_PATH.name)
    quality = quality_governance(policy_path)
    mutating = _mutating_requested(
        execute=execute, apply_capabilities=apply_capabilities,
        train_meta=train_meta, apply_skills=apply_skills,
    )
    if mutating and quality.get("ok") is not True:
        return _quality_hold(quality)

    kwargs = dict(
        execute=execute, apply_capabilities=apply_capabilities, train_meta=train_meta,
        apply_skills=apply_skills, root=root, now=now, proc_root=proc_root,
        state_path=state_path, capability_path=capability_path, meta_model_path=meta_model_path,
        meta_outcomes_path=meta_outcomes_path, skill_state_path=skill_state_path,
        skill_outcomes_path=skill_outcomes_path, journal_path=journal_path,
        persist_outputs=persist_outputs,
    )

    if not mutating:
        result = _decorate(
            v377.run_cycle(**kwargs),
            quality,
            {"status": "V378_LOCK_NOT_REQUIRED", "error_code": None},
        )
        if persist_outputs:
            try:
                atomic_write_json(root / REPORT_PATH.name, result, suffix=".v378-report.tmp")
                result["v378_runtime_output"] = {"status": "SAVED"}
            except (OSError, UnicodeError, ValueError, TypeError) as exc:
                result["v378_runtime_output"] = {"status": "WRITE_FAILED", "error_code": type(exc).__name__}
        return result

    outer_lock_path = lock_path or (root / LOCK_PATH.name)
    fd, outer_lock = _acquire_lock(outer_lock_path)
    if fd is None:
        hold = _quality_hold(quality)
        hold["v378_status"] = str(outer_lock["status"])
        hold["execution"]["status"] = str(outer_lock["status"])
        hold["v378_single_run_lock"] = outer_lock
        return hold
    try:
        result = _decorate(v377.run_cycle(**kwargs), quality, outer_lock)
        if persist_outputs:
            try:
                atomic_write_json(root / REPORT_PATH.name, result, suffix=".v378-report.tmp")
                result["v378_runtime_output"] = {"status": "SAVED"}
            except (OSError, UnicodeError, ValueError, TypeError) as exc:
                result["v378_runtime_output"] = {"status": "WRITE_FAILED", "error_code": type(exc).__name__}
        return result
    finally:
        _release_lock(fd)


def self_test() -> None:
    assert SAFETY["quality_100_senior_prep_required"] is True
    assert SAFETY["quality_1000_review_cells_required"] is True
    assert SAFETY["quality_blocker_cannot_be_outvoted"] is True
    assert SAFETY["verified_neural_council_advisory_only"] is True
    assert SAFETY["declarative_runtime_self_extension_allowlisted_only"] is True
    assert SAFETY["source_level_feature_auto_implementation"] is False
    assert SAFETY["source_code_auto_generation"] is False
    assert SAFETY["git_write"] is False
    assert SAFETY["verification_bypass"] is False
    assert SAFETY["price_or_grade_invention"] is False
    assert SAFETY["market_direction_inferred"] is False
    print("Tablet 100+1000 governed autonomous evolution v378: PASS")


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
    return 2 if result.get("v378_status") in _HOLD_STATUSES else 0


if __name__ == "__main__":
    raise SystemExit(main())
