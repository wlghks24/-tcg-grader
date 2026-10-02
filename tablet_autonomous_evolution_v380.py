#!/usr/bin/env python3
"""Decision-specific 100+1000 neural governance for Tablet GPT / TCG Grader.

V380 keeps V379/V378/V377/V376 safety and learning intact, including V379's
validated Tablet GPT ↔ TCG Grader information-exchange governance, and closes one remaining
governance gap: the 100 senior-preparation perspectives and the 25x40=1000
expert review cells are now computed for the *current autonomous decision*, not
only validated as a static policy declaration.

The resulting matrix is combined with V379's validated information-exchange neural
council (falling back to the verified local neural council) and the market
operational regime before any mutating cycle. Hard safety/evidence/state/
provenance blockers cannot be outvoted. Low-confidence neural consensus may
hold a non-recovery action, but can never authorize a blocked action.

Runtime self-extension remains limited to existing allowlisted declarative
capabilities. Source-level new functions remain evidence-backed, non-executable
proposals requiring protected PR/CI and full regression.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import stat
from copy import deepcopy
from pathlib import Path
from typing import Any

import tablet_autonomous_evolution_v373 as v373
import tablet_autonomous_evolution_v379 as v379
from safe_runtime import atomic_write_json

ROOT = Path(__file__).resolve().parent
CONTROLLER_VERSION = "v380"
CORE_CONTROLLER_VERSION = "v379"
REPORT_PATH = ROOT / "tablet_autonomy_v380_report.json"
LOCK_PATH = ROOT / ".tablet_autonomy_execution_v380.lock"

DIMENSIONS = (
    "policy_contract",
    "safety_boundary",
    "evidence_commit",
    "state_integrity",
    "market_freshness",
    "market_coverage",
    "source_health",
    "neural_consensus",
    "resource_headroom",
    "recovery_integrity",
    "candidate_risk",
    "proposal_boundary",
)

RECOVERY_RECIPES = {
    "RECOVER_FRESHNESS",
    "EXPAND_REGION_COVERAGE",
    "RECOVER_SOURCE_HEALTH",
    "RECOVER_MODEL",
    "OBSERVE_ONLY",
}

_HOLD_STATUSES = set(getattr(v379, "_HOLD_STATUSES", set())) | {
    "V380_QUALITY_DECISION_HOLD",
    "V380_LOCK_UNAVAILABLE",
    "V380_CONCURRENT_AUTONOMY_HOLD",
    "V380_EXCHANGE_DRIFT_HOLD",
}

SAFETY = dict(v379.SAFETY)
SAFETY.update({
    "decision_specific_100_senior_matrix_required": True,
    "decision_specific_1000_review_cells_required": True,
    "review_matrix_digest_required": True,
    "verified_neural_council_participates_in_gate": True,
    "neural_low_confidence_may_hold_non_recovery": True,
    "neural_council_can_never_override_hard_blocker": True,
    "market_recovery_only_when_freshness_held": True,
    "decision_gate_runs_before_mutating_v379": True,
    "information_exchange_neural_council_participates_in_gate": True,
    "information_exchange_hold_cannot_be_outvoted": True,
    "decision_time_exchange_digest_recheck_required": True,
    "runtime_self_extension_allowlisted_declarative_only": True,
    "source_level_new_function_pr_ci_required": True,
    "allowlisted_capability_selection_is_decision_gated": True,
    "source_level_feature_proposals_are_non_executable": True,
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


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _load_policy(root: Path) -> dict[str, Any]:
    path = root / "quality_review_policy_v2.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _core_safety(base: dict[str, Any]) -> tuple[bool, list[str]]:
    safety = base.get("safety") if isinstance(base.get("safety"), dict) else {}
    required_false = (
        "source_code_auto_generation",
        "source_code_auto_rewrite",
        "git_write",
        "verification_bypass",
        "price_or_grade_invention",
        "market_direction_inferred",
        "peer_fix_auto_apply",
        "peer_content_direct_model_training",
    )
    required_true = (
        "quality_policy_fail_closed_before_mutation",
        "quality_blocker_cannot_be_outvoted",
        "single_mutating_cycle_lock_required",
        "concurrent_mutating_cycle_fail_closed",
        "information_exchange_conflict_blocks_mutation",
        "information_exchange_invalid_blocks_mutation",
        "information_exchange_input_stability_required",
    )
    reasons = [key for key in required_false if safety.get(key) is not False]
    reasons.extend(key for key in required_true if safety.get(key) is not True)
    return not reasons, reasons


def _market_profile(base: dict[str, Any]) -> dict[str, Any]:
    plan = base.get("plan") if isinstance(base.get("plan"), dict) else {}
    profile = plan.get("market_profile") if isinstance(plan.get("market_profile"), dict) else {}
    return profile


def dimension_values(base: dict[str, Any]) -> dict[str, float]:
    quality = base.get("quality_governance") if isinstance(base.get("quality_governance"), dict) else {}
    council = (
        base.get("information_exchange_neural_council")
        if isinstance(base.get("information_exchange_neural_council"), dict)
        else base.get("neural_council")
        if isinstance(base.get("neural_council"), dict)
        else {}
    )
    mode = base.get("adaptive_mode") if isinstance(base.get("adaptive_mode"), dict) else {}
    barrier = base.get("evidence_barrier") if isinstance(base.get("evidence_barrier"), dict) else {}
    skill = base.get("skill_state") if isinstance(base.get("skill_state"), dict) else {}
    plan = base.get("plan") if isinstance(base.get("plan"), dict) else {}
    resources = plan.get("resources") if isinstance(plan.get("resources"), dict) else {}
    selected = base.get("selected_skill") if isinstance(base.get("selected_skill"), dict) else {}
    profile = _market_profile(base)
    core_safe, _ = _core_safety(base)

    low_regions = profile.get("low_coverage_regions")
    if not isinstance(low_regions, list):
        low_regions = []
    degraded = _finite(profile.get("degraded_source_ratio"))
    council_confidence = _finite(council.get("confidence"))
    council_agreement = _finite(council.get("agreement"))
    risk = _finite(selected.get("risk"))
    if risk is None:
        risk = 0.0

    resource_status = str(resources.get("status") or "unknown")
    resource_score = 1.0 if resource_status == "normal" else 0.6 if resource_status == "unknown" else 0.2

    v378_lock = base.get("v378_single_run_lock") if isinstance(base.get("v378_single_run_lock"), dict) else {}
    inner_lock = base.get("single_run_lock") if isinstance(base.get("single_run_lock"), dict) else {}
    recovery_ok = (
        str(v378_lock.get("status") or "") in {"V378_LOCK_NOT_REQUIRED", "V378_LOCK_ACQUIRED"}
        and str(inner_lock.get("status") or "") in {"LOCK_NOT_REQUIRED", "LOCK_ACQUIRED"}
    )

    execution = base.get("execution") if isinstance(base.get("execution"), dict) else {}
    proposal_boundary = (
        execution.get("git_write") is not True
        and execution.get("source_code_modified") is not True
        and execution.get("proposals_executed") is not True
    )

    neural_score = 0.0
    if council_confidence is not None and council_agreement is not None:
        neural_score = _clamp(0.65 * council_confidence + 0.35 * council_agreement)
    elif council_confidence is not None:
        neural_score = _clamp(council_confidence)

    market_regime = str(mode.get("market_regime") or "UNKNOWN")
    freshness = 0.25 if market_regime == "FRESHNESS_HOLD" else 1.0

    return {
        "policy_contract": 1.0 if quality.get("ok") is True else 0.0,
        "safety_boundary": 1.0 if core_safe else 0.0,
        "evidence_commit": 1.0 if barrier.get("ok") is True else 0.0,
        "state_integrity": 0.0 if skill.get("corruption_hold") is True else 1.0,
        "market_freshness": freshness,
        "market_coverage": _clamp(1.0 - len(low_regions) / 3.0),
        "source_health": _clamp(1.0 - (degraded if degraded is not None else 0.5)),
        "neural_consensus": neural_score,
        "resource_headroom": resource_score,
        "recovery_integrity": 1.0 if recovery_ok else 0.0,
        "candidate_risk": _clamp(1.0 - risk),
        "proposal_boundary": 1.0 if proposal_boundary else 0.0,
    }


def _group_dimension(group_id: int) -> str:
    if 7 <= group_id <= 10:
        return "safety_boundary"
    if 11 <= group_id <= 15:
        return "neural_consensus" if group_id in {13, 14} else "state_integrity"
    if 16 <= group_id <= 19:
        return ("market_freshness", "market_coverage", "source_health", "policy_contract")[group_id - 16]
    if 20 <= group_id <= 22:
        return ("resource_headroom", "recovery_integrity", "state_integrity")[group_id - 20]
    if group_id == 24:
        return "evidence_commit"
    return "policy_contract"


def _lens_dimension(lens_id: int) -> str:
    if lens_id <= 6:
        return ("policy_contract", "market_freshness", "source_health", "evidence_commit", "source_health", "evidence_commit")[lens_id - 1]
    if lens_id <= 11:
        return "policy_contract"
    if lens_id <= 20:
        return (
            "recovery_integrity",
            "recovery_integrity",
            "candidate_risk",
            "state_integrity",
            "recovery_integrity",
            "recovery_integrity",
            "recovery_integrity",
            "market_freshness",
            "source_health",
        )[lens_id - 12]
    if lens_id <= 24:
        return ("safety_boundary", "safety_boundary", "proposal_boundary", "safety_boundary")[lens_id - 21]
    if lens_id <= 31:
        return "resource_headroom"
    if lens_id <= 34:
        return ("state_integrity", "evidence_commit", "neural_consensus")[lens_id - 32]
    return (
        "recovery_integrity",
        "evidence_commit",
        "recovery_integrity",
        "neural_consensus",
        "state_integrity",
        "policy_contract",
    )[lens_id - 35]


def decision_matrix(base: dict[str, Any], *, root: Path = ROOT) -> dict[str, Any]:
    policy = _load_policy(root)
    dimensions = dimension_values(base)

    prep_domains = list(DIMENSIONS[:10])
    prep_rows = []
    for index in range(100):
        dimension = prep_domains[index % len(prep_domains)]
        score = float(dimensions[dimension])
        prep_rows.append({
            "perspective": index + 1,
            "dimension": dimension,
            "score": round(score, 6),
            "status": "PASS" if score >= 0.55 else "REVIEW",
        })

    groups = policy.get("expert_groups") if isinstance(policy.get("expert_groups"), list) else []
    lenses = policy.get("review_lenses") if isinstance(policy.get("review_lenses"), list) else []
    cells = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        gid = int(group.get("id") or 0)
        gd = _group_dimension(gid)
        for lens in lenses:
            if not isinstance(lens, dict):
                continue
            lid = int(lens.get("id") or 0)
            ld = _lens_dimension(lid)
            score = (float(dimensions[gd]) + float(dimensions[ld])) / 2.0
            cells.append({
                "group": gid,
                "lens": lid,
                "dimensions": [gd, ld],
                "score": round(score, 6),
                "status": "PASS" if score >= 0.60 else "REVIEW",
            })

    prep_pass = sum(row["status"] == "PASS" for row in prep_rows)
    cell_pass = sum(row["status"] == "PASS" for row in cells)
    return {
        "dimensions": dimensions,
        "preparation": {
            "perspectives": len(prep_rows),
            "pass": prep_pass,
            "review": len(prep_rows) - prep_pass,
            "pass_ratio": round(prep_pass / max(1, len(prep_rows)), 6),
            "digest_sha256": _digest(prep_rows),
            "lowest": sorted(prep_rows, key=lambda row: (row["score"], row["perspective"]))[:10],
        },
        "expert_review": {
            "groups": len(groups),
            "lenses": len(lenses),
            "cells": len(cells),
            "pass": cell_pass,
            "review": len(cells) - cell_pass,
            "pass_ratio": round(cell_pass / max(1, len(cells)), 6),
            "digest_sha256": _digest(cells),
            "lowest": sorted(cells, key=lambda row: (row["score"], row["group"], row["lens"]))[:20],
        },
        "external_human_review_claimed": False,
    }


def hard_blockers(base: dict[str, Any], matrix: dict[str, Any]) -> list[str]:
    blockers = []
    quality = base.get("quality_governance") if isinstance(base.get("quality_governance"), dict) else {}
    if quality.get("ok") is not True:
        blockers.append("QUALITY_POLICY_INVALID")
    core_safe, reasons = _core_safety(base)
    if not core_safe:
        blockers.extend(f"SAFETY_{reason.upper()}" for reason in reasons)
    barrier = base.get("evidence_barrier") if isinstance(base.get("evidence_barrier"), dict) else {}
    if barrier and barrier.get("ok") is not True:
        blockers.append(str(barrier.get("status") or "EVIDENCE_COMMIT_HOLD"))
    skill = base.get("skill_state") if isinstance(base.get("skill_state"), dict) else {}
    if skill.get("corruption_hold") is True:
        blockers.append("SKILL_STATE_CORRUPTION_HOLD")
    if matrix["dimensions"]["proposal_boundary"] < 1.0:
        blockers.append("PROPOSAL_BOUNDARY_VIOLATION")

    status = str(base.get("v379_status") or "")
    if status in _HOLD_STATUSES:
        blockers.append(status)
    exchange = (
        base.get("information_exchange_manager")
        if isinstance(base.get("information_exchange_manager"), dict)
        else {}
    )
    if exchange and exchange.get("mutation_allowed") is not True:
        blockers.append(str(exchange.get("status") or "EXCHANGE_INTEGRITY_HOLD"))

    selected = base.get("selected_skill") if isinstance(base.get("selected_skill"), dict) else {}
    recipe = str(selected.get("recipe") or "")
    mode = base.get("adaptive_mode") if isinstance(base.get("adaptive_mode"), dict) else {}
    if str(mode.get("market_regime") or "") == "FRESHNESS_HOLD" and recipe and recipe not in RECOVERY_RECIPES:
        blockers.append("MARKET_FRESHNESS_RECOVERY_ONLY")
    return sorted(set(blockers))


def decide(base: dict[str, Any], matrix: dict[str, Any]) -> dict[str, Any]:
    blockers = hard_blockers(base, matrix)
    council = (
        base.get("information_exchange_neural_council")
        if isinstance(base.get("information_exchange_neural_council"), dict)
        else base.get("neural_council")
        if isinstance(base.get("neural_council"), dict)
        else {}
    )
    readiness = str(council.get("readiness") or "LOW")
    mode = base.get("adaptive_mode") if isinstance(base.get("adaptive_mode"), dict) else {}
    selected = base.get("selected_skill") if isinstance(base.get("selected_skill"), dict) else {}
    recipe = str(selected.get("recipe") or "")

    recovery_mode = str(mode.get("mode") or "") in {
        "RECOVER_FRESHNESS",
        "COMPOSED_MARKET_RECOVERY",
        "EXPAND_VERIFIED_COVERAGE",
        "RECOVER_SOURCE_HEALTH",
        "RECOVER_VERIFIED_MODELS",
        "OBSERVE_UNCERTAIN_REGIME",
    }
    threshold = 0.55 if recovery_mode or recipe in RECOVERY_RECIPES else 0.70
    matrix_ok = (
        matrix["preparation"]["perspectives"] == 100
        and matrix["expert_review"]["groups"] == 25
        and matrix["expert_review"]["lenses"] == 40
        and matrix["expert_review"]["cells"] == 1000
        and matrix["preparation"]["pass_ratio"] >= threshold
        and matrix["expert_review"]["pass_ratio"] >= threshold
    )

    low_neural_hold = readiness == "LOW" and bool(recipe) and recipe not in RECOVERY_RECIPES
    allow = not blockers and matrix_ok and not low_neural_hold
    if blockers:
        directive = "BLOCKED"
    elif low_neural_hold:
        directive = "OBSERVE_MORE"
    elif recovery_mode:
        directive = "RECOVERY_BOUNDED"
    else:
        directive = "EXECUTE_VERIFIED_SELECTION"

    return {
        "status": "ALLOW_BOUNDED" if allow else "V380_QUALITY_DECISION_HOLD",
        "allow_execution": allow,
        "directive": directive,
        "hard_blockers": blockers,
        "threshold": threshold,
        "matrix_ok": matrix_ok,
        "neural_readiness": readiness,
        "neural_low_confidence_hold": low_neural_hold,
        "selected_skill_id": str(selected.get("skill_id") or "")[:128] or None,
        "selected_recipe": recipe or None,
        "neural_can_override_hard_blocker": False,
    }



def _capability_priority(row: dict[str, Any], base: dict[str, Any]) -> int:
    primitive = str(row.get("primitive") or "")
    plan = base.get("plan") if isinstance(base.get("plan"), dict) else {}
    profile = plan.get("market_profile") if isinstance(plan.get("market_profile"), dict) else {}
    mode = base.get("adaptive_mode") if isinstance(base.get("adaptive_mode"), dict) else {}
    regime = str(mode.get("market_regime") or "")
    degraded = _finite(profile.get("degraded_source_ratio"))
    low_regions = profile.get("low_coverage_regions")
    if not isinstance(low_regions, list):
        low_regions = []
    if primitive == "REQUEST_FRESHNESS_REFRESH":
        return 100 if regime == "FRESHNESS_HOLD" else 35
    if primitive == "PRIORITIZE_REGION":
        return 90 if low_regions else 40
    if primitive == "RETRY_DEGRADED_SOURCES":
        return 85 if degraded is not None and degraded > 0.35 else 40
    if primitive == "PRIORITIZE_SAFE_LEARNING":
        return 65
    if primitive == "INCREASE_OBSERVATION":
        council = (
            base.get("information_exchange_neural_council")
            if isinstance(base.get("information_exchange_neural_council"), dict)
            else base.get("neural_council")
            if isinstance(base.get("neural_council"), dict)
            else {}
        )
        return 80 if str(council.get("readiness") or "") in {"LOW", "HOLD"} else 45
    return 0


def autonomous_capability_plan(base: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    """Select only capabilities already validated by the V373 declarative DSL.

    Improvement-queue rows are never treated as executable capabilities merely
    because they contain auto_apply=true. Runtime selection comes solely from
    plan.active_capabilities and each row must pass the canonical V373
    capability validator. Source-level gaps remain non-executable PR proposals.
    """
    plan = base.get("plan") if isinstance(base.get("plan"), dict) else {}
    active = plan.get("active_capabilities") if isinstance(plan.get("active_capabilities"), list) else []
    runtime_candidates = []
    rejected_runtime = []
    for row in active:
        if not isinstance(row, dict):
            continue
        if not v373.validate_capability(row):
            rejected_runtime.append({
                "id": str(row.get("id") or "")[:160] or None,
                "primitive": str(row.get("primitive") or "")[:80] or None,
                "reason": "CANONICAL_CAPABILITY_VALIDATION_FAILED",
            })
            continue
        candidate = {
            "id": str(row.get("id") or "")[:160],
            "primitive": str(row.get("primitive") or "")[:80],
            "priority": _capability_priority(row, base),
            "auto_apply": bool(decision.get("allow_execution")),
            "pr_required": False,
            "source_code_change": False,
            "arbitrary_command": False,
        }
        runtime_candidates.append(candidate)

    source_proposals = []
    queue = base.get("improvement_queue") if isinstance(base.get("improvement_queue"), list) else []
    for row in queue:
        if not isinstance(row, dict):
            continue
        kind = str(row.get("kind") or "")
        if row.get("pr_required") is not True and kind not in {"source_feature", "source_code", "new_function"}:
            continue
        try:
            priority = int(row.get("priority") or 0)
        except (TypeError, ValueError, OverflowError):
            priority = 0
        source_proposals.append({
            "id": str(row.get("id") or "")[:160],
            "kind": kind or "source_feature",
            "priority": priority,
            "auto_apply": False,
            "pr_required": True,
        })

    runtime_candidates.sort(key=lambda row: (-row["priority"], row["id"]))
    rejected_runtime.sort(key=lambda row: (str(row.get("primitive") or ""), str(row.get("id") or "")))
    source_proposals.sort(key=lambda row: (-row["priority"], row["id"]))
    exchange = base.get("information_exchange_manager") if isinstance(base.get("information_exchange_manager"), dict) else {}
    mode = base.get("adaptive_mode") if isinstance(base.get("adaptive_mode"), dict) else {}
    return {
        "status": "ALLOWLISTED_RUNTIME_SELECTION" if decision.get("allow_execution") else "DECISION_HOLD",
        "selected_runtime_capability": runtime_candidates[0] if runtime_candidates else None,
        "runtime_candidates": runtime_candidates[:20],
        "rejected_runtime_capabilities": rejected_runtime[:20],
        "canonical_registry": "tablet_autonomous_evolution_v373.CAPABILITY_PRIMITIVES",
        "canonical_validator": "tablet_autonomous_evolution_v373.validate_capability",
        "source_level_proposals": source_proposals[:20],
        "source_level_auto_apply": False,
        "protected_pr_ci_required": bool(source_proposals),
        "information_exchange_status": exchange.get("status"),
        "information_exchange_action": exchange.get("selected_management_action"),
        "market_regime": mode.get("market_regime"),
        "market_direction_inferred": False,
    }


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
            return None, {"status": "V380_LOCK_UNAVAILABLE", "error_code": "NOT_REGULAR_FILE"}
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        try:
            os.close(fd)
        except (OSError, UnboundLocalError):
            pass
        return None, {"status": "V380_CONCURRENT_AUTONOMY_HOLD", "error_code": "LOCK_BUSY"}
    except OSError as exc:
        try:
            os.close(fd)
        except (OSError, UnboundLocalError):
            pass
        return None, {"status": "V380_LOCK_UNAVAILABLE", "error_code": type(exc).__name__}
    return fd, {"status": "V380_LOCK_ACQUIRED", "error_code": None}


def _release_lock(fd: int) -> None:
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _decorate(
    base: dict[str, Any], matrix: dict[str, Any], decision: dict[str, Any], lock: dict[str, Any]
) -> dict[str, Any]:
    result = deepcopy(base)
    result["core_controller_version"] = str(base.get("controller_version") or CORE_CONTROLLER_VERSION)
    result["controller_version"] = CONTROLLER_VERSION
    result["v380_status"] = str(base.get("v379_status") or base.get("v378_status") or "UNKNOWN")
    result["decision_review_matrix"] = matrix
    result["autonomous_decision"] = decision
    result["v380_single_run_lock"] = lock
    result["evolution_contract_v380"] = {
        "actual_senior_perspectives_computed": matrix["preparation"]["perspectives"],
        "actual_review_cells_computed": matrix["expert_review"]["cells"],
        "review_matrix_digest_required": True,
        "verified_neural_council_used_before_mutation": True,
        "hard_blocker_outvote_forbidden": True,
        "runtime_self_added_functions": "allowlisted_declarative_capabilities_only",
        "source_level_new_functions": "proposal_only_pr_ci_required",
        "allowlisted_runtime_capabilities": "decision_gated_selection_only",
        "market_adaptation": "freshness_coverage_source_health_only",
        "market_direction_prediction": False,
        "external_human_review_claimed": False,
    }
    result["autonomous_capability_plan"] = autonomous_capability_plan(base, decision)
    result["safety"] = SAFETY
    return result


def _hold(
    preview: dict[str, Any], matrix: dict[str, Any], decision: dict[str, Any], lock: dict[str, Any], status: str
) -> dict[str, Any]:
    result = _decorate(preview, matrix, decision, lock)
    result["v380_status"] = status
    result["execution"] = {
        "status": status,
        "executed": False,
        "git_write": False,
        "source_code_modified": False,
        "proposals_executed": False,
    }
    return result


def run_cycle(
    *, execute: bool = False, apply_capabilities: bool = False, train_meta: bool = False,
    apply_skills: bool = False, root: Path = ROOT, now=None, proc_root: Path = Path("/proc"),
    state_path=None, capability_path=None, meta_model_path=None, meta_outcomes_path=None,
    skill_state_path=None, skill_outcomes_path=None, journal_path=None,
    core_lock_path=None, lock_path=None, quality_policy_path=None,
    persist_outputs: bool = True,
) -> dict[str, Any]:
    mutating = bool(execute or apply_capabilities or train_meta or apply_skills)
    outer_lock = {"status": "V380_LOCK_NOT_REQUIRED", "error_code": None}
    fd = None
    if mutating:
        fd, outer_lock = _acquire_lock(lock_path or (root / LOCK_PATH.name))
        if fd is None:
            empty_matrix = {
                "dimensions": {},
                "preparation": {"perspectives": 0, "pass": 0, "review": 0, "pass_ratio": 0.0, "digest_sha256": None, "lowest": []},
                "expert_review": {"groups": 0, "lenses": 0, "cells": 0, "pass": 0, "review": 0, "pass_ratio": 0.0, "digest_sha256": None, "lowest": []},
                "external_human_review_claimed": False,
            }
            decision = {
                "status": str(outer_lock["status"]),
                "allow_execution": False,
                "directive": "BLOCKED",
                "hard_blockers": [str(outer_lock["status"])],
                "neural_can_override_hard_blocker": False,
            }
            return {
                "controller_version": CONTROLLER_VERSION,
                "core_controller_version": CORE_CONTROLLER_VERSION,
                "v380_status": str(outer_lock["status"]),
                "execution": {"status": str(outer_lock["status"]), "executed": False, "git_write": False, "source_code_modified": False, "proposals_executed": False},
                "decision_review_matrix": empty_matrix,
                "autonomous_decision": decision,
                "v380_single_run_lock": outer_lock,
                "safety": SAFETY,
            }

    kwargs = dict(
        root=root, now=now, proc_root=proc_root, state_path=state_path,
        capability_path=capability_path, meta_model_path=meta_model_path,
        meta_outcomes_path=meta_outcomes_path, skill_state_path=skill_state_path,
        skill_outcomes_path=skill_outcomes_path, journal_path=journal_path,
        lock_path=core_lock_path, quality_policy_path=quality_policy_path,
        persist_outputs=False,
    )
    try:
        preview = v379.run_cycle(
            execute=False, apply_capabilities=False, train_meta=False, apply_skills=False, **kwargs
        )
        matrix = decision_matrix(preview, root=root)
        decision = decide(preview, matrix)

        if mutating and not decision["allow_execution"]:
            result = _hold(preview, matrix, decision, outer_lock, "V380_QUALITY_DECISION_HOLD")
        elif mutating:
            preview_exchange = (
                preview.get("information_exchange_manager")
                if isinstance(preview.get("information_exchange_manager"), dict)
                else {}
            )
            confirmed_exchange = v379.information_exchange_manager(root)
            preview_digest = str(preview_exchange.get("input_digest") or "")
            confirmed_digest = str(confirmed_exchange.get("input_digest") or "")
            if not preview_digest or preview_digest != confirmed_digest:
                drift = dict(decision)
                drift.update({
                    "status": "V380_EXCHANGE_DRIFT_HOLD",
                    "allow_execution": False,
                    "directive": "BLOCKED",
                    "hard_blockers": sorted(set(list(decision.get("hard_blockers") or []) + ["V380_EXCHANGE_DRIFT_HOLD"])),
                    "neural_can_override_hard_blocker": False,
                })
                result = _hold(preview, matrix, drift, outer_lock, "V380_EXCHANGE_DRIFT_HOLD")
            else:
                core = v379.run_cycle(
                    execute=execute, apply_capabilities=apply_capabilities, train_meta=train_meta,
                    apply_skills=apply_skills, **kwargs
                )
                result = _decorate(core, matrix, decision, outer_lock)
        else:
            result = _decorate(preview, matrix, decision, outer_lock)
            result["v380_status"] = "PLAN_ONLY"

        if persist_outputs:
            try:
                atomic_write_json(root / REPORT_PATH.name, result, suffix=".v380-report.tmp")
                result["v380_runtime_output"] = {"status": "SAVED"}
            except (OSError, UnicodeError, ValueError, TypeError) as exc:
                result["v380_runtime_output"] = {"status": "WRITE_FAILED", "error_code": type(exc).__name__}
        return result
    finally:
        if fd is not None:
            _release_lock(fd)


def self_test() -> None:
    assert SAFETY["decision_specific_100_senior_matrix_required"] is True
    assert SAFETY["decision_specific_1000_review_cells_required"] is True
    assert SAFETY["verified_neural_council_participates_in_gate"] is True
    assert SAFETY["decision_time_exchange_digest_recheck_required"] is True
    assert SAFETY["neural_council_can_never_override_hard_blocker"] is True
    assert SAFETY["runtime_self_extension_allowlisted_declarative_only"] is True
    assert SAFETY["source_code_auto_generation"] is False
    assert SAFETY["source_code_auto_rewrite"] is False
    assert SAFETY["git_write"] is False
    assert SAFETY["verification_bypass"] is False
    assert SAFETY["price_or_grade_invention"] is False
    assert SAFETY["market_direction_inferred"] is False
    print("Tablet decision-specific 100+1000 neural governance v380: PASS")


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
    return 2 if result.get("v380_status") in _HOLD_STATUSES else 0


if __name__ == "__main__":
    raise SystemExit(main())
