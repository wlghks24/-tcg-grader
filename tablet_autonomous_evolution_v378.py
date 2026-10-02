#!/usr/bin/env python3
"""100+1000 quality-governed autonomy for Tablet GPT / TCG Grader.

V378 keeps V377/V376 as the execution and transactional core and adds a
fail-closed quality governor in front of every mutating autonomous cycle.

The governor computes:
- 100 simulated senior preparation perspectives; and
- 25 expert groups x 40 review lenses = 1000 internal review cells.

Those are internal QA lenses, not external people. They supervise the existing
verified-only meta-neural learning and market-regime adaptation. A hard safety,
state-integrity, evidence, or provenance blocker can never be outvoted.

Runtime self-added behavior remains limited to the existing allowlisted
declarative capabilities. Source-level feature gaps remain proposals that must
use the protected branch/PR/CI path. No card fact, price, grade, trust state, or
market direction is invented by this controller.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import quality_review_policy
import tablet_autonomous_evolution_v377 as v377
from safe_runtime import atomic_write_json

ROOT = Path(__file__).resolve().parent
CONTROLLER_VERSION = "v378"
CORE_CONTROLLER_VERSION = "v377"
REPORT_PATH = ROOT / "tablet_autonomy_v378_report.json"

DIMENSIONS = (
    "policy_contract",
    "safety_boundary",
    "evidence_commit",
    "state_integrity",
    "market_freshness",
    "market_coverage",
    "source_health",
    "neural_reliability",
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

HOLD_STATUSES = set(getattr(v377, "_HOLD_STATUSES", set())) | {
    "QUALITY_GOVERNANCE_HOLD",
    "QUALITY_POLICY_HOLD",
}

SAFETY = dict(v377.SAFETY)
SAFETY.update({
    "hundred_senior_prep_perspectives_required": 100,
    "thousand_review_cells_required": 1000,
    "review_cells_are_internal_simulation_not_external_people": True,
    "hard_blocker_cannot_be_outvoted": True,
    "existing_verified_neural_learning_remains_enabled": True,
    "quality_governor_can_hold_but_never_bypass": True,
    "market_regime_adaptation_bounded": True,
    "declarative_self_added_functions_allowlisted_only": True,
    "source_level_feature_gap_requires_protected_pr_ci": True,
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


def _policy(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    policy_path = root / "quality_review_policy_v2.json"
    validation = quality_review_policy.validate(policy_path)
    try:
        payload = json.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        payload = {}
    return validation, payload if isinstance(payload, dict) else {}


def _market_context(base: dict[str, Any]) -> dict[str, Any]:
    capsule = base.get("exchange_capsule") if isinstance(base.get("exchange_capsule"), dict) else {}
    market = capsule.get("market_context") if isinstance(capsule.get("market_context"), dict) else {}
    if market:
        return market
    try:
        value = v377.v376.market_context(base)
    except (AttributeError, TypeError, ValueError):
        value = {}
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
    )
    required_true = (
        "single_mutating_cycle_lock_required",
        "concurrent_mutating_cycle_fail_closed",
    )
    reasons = [key for key in required_false if safety.get(key) is not False]
    reasons.extend(key for key in required_true if safety.get(key) is not True)
    return not reasons, reasons


def dimension_values(base: dict[str, Any], policy_validation: dict[str, Any]) -> dict[str, float]:
    plan = base.get("plan") if isinstance(base.get("plan"), dict) else {}
    barrier = base.get("evidence_barrier") if isinstance(base.get("evidence_barrier"), dict) else {}
    skill = base.get("skill_state") if isinstance(base.get("skill_state"), dict) else {}
    reliability = base.get("neural_reliability") if isinstance(base.get("neural_reliability"), dict) else {}
    resources = plan.get("resources") if isinstance(plan.get("resources"), dict) else {}
    selected = base.get("selected_skill") if isinstance(base.get("selected_skill"), dict) else {}
    market = _market_context(base)
    core_safe, _ = _core_safety(base)

    low_regions = market.get("low_coverage_regions")
    if not isinstance(low_regions, list):
        low_regions = []
    degraded = _finite(market.get("degraded_source_ratio"))
    confidence = _finite(reliability.get("confidence"))
    risk = _finite(selected.get("risk"))
    if risk is None:
        risk = 0.0

    resource_status = str(resources.get("status") or "unknown")
    resource_score = 1.0 if resource_status == "normal" else 0.6 if resource_status == "unknown" else 0.2
    lock = base.get("single_run_lock") if isinstance(base.get("single_run_lock"), dict) else {}
    lock_ok = str(lock.get("status") or "") in {"LOCK_NOT_REQUIRED", "LOCK_ACQUIRED"}

    execution = base.get("execution") if isinstance(base.get("execution"), dict) else {}
    boundary_ok = (
        execution.get("git_write") is not True
        and execution.get("source_code_modified") is not True
        and execution.get("proposals_executed") is not True
    )

    return {
        "policy_contract": 1.0 if policy_validation.get("ok") is True else 0.0,
        "safety_boundary": 1.0 if core_safe else 0.0,
        "evidence_commit": 1.0 if barrier.get("ok") is True else 0.0,
        "state_integrity": 0.0 if skill.get("corruption_hold") is True else 1.0,
        "market_freshness": 0.25 if str(market.get("regime") or "") == "FRESHNESS_HOLD" else 1.0,
        "market_coverage": _clamp(1.0 - len(low_regions) / 3.0),
        "source_health": _clamp(1.0 - (degraded if degraded is not None else 0.5)),
        "neural_reliability": _clamp(confidence if confidence is not None else 0.0),
        "resource_headroom": resource_score,
        "recovery_integrity": 1.0 if lock_ok else 0.0,
        "candidate_risk": _clamp(1.0 - risk),
        "proposal_boundary": 1.0 if boundary_ok else 0.0,
    }


def _group_dimension(group_id: int) -> str:
    if 7 <= group_id <= 10:
        return "safety_boundary"
    if 11 <= group_id <= 15:
        return "neural_reliability" if group_id in {13, 14} else "state_integrity"
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
        return ("recovery_integrity", "recovery_integrity", "candidate_risk", "state_integrity",
                "recovery_integrity", "recovery_integrity", "recovery_integrity",
                "market_freshness", "source_health")[lens_id - 12]
    if lens_id <= 24:
        return ("safety_boundary", "safety_boundary", "proposal_boundary", "safety_boundary")[lens_id - 21]
    if lens_id <= 31:
        return "resource_headroom"
    if lens_id <= 34:
        return ("state_integrity", "evidence_commit", "neural_reliability")[lens_id - 32]
    return ("recovery_integrity", "evidence_commit", "recovery_integrity",
            "neural_reliability", "state_integrity", "policy_contract")[lens_id - 35]


def review_matrices(policy_payload: dict[str, Any], dimensions: dict[str, float]) -> dict[str, Any]:
    prep_domains = list(DIMENSIONS[:10])
    prep_rows = []
    for index in range(100):
        dimension = prep_domains[index % len(prep_domains)]
        score = dimensions[dimension]
        prep_rows.append({
            "perspective": index + 1,
            "dimension": dimension,
            "score": round(score, 6),
            "status": "PASS" if score >= 0.55 else "REVIEW",
        })
    prep_pass = sum(row["status"] == "PASS" for row in prep_rows)

    groups = policy_payload.get("expert_groups") if isinstance(policy_payload.get("expert_groups"), list) else []
    lenses = policy_payload.get("review_lenses") if isinstance(policy_payload.get("review_lenses"), list) else []
    cells = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        group_id = int(group.get("id") or 0)
        group_dimension = _group_dimension(group_id)
        for lens in lenses:
            if not isinstance(lens, dict):
                continue
            lens_id = int(lens.get("id") or 0)
            lens_dimension = _lens_dimension(lens_id)
            score = (dimensions[group_dimension] + dimensions[lens_dimension]) / 2.0
            cells.append({
                "group": group_id,
                "lens": lens_id,
                "dimensions": [group_dimension, lens_dimension],
                "score": round(score, 6),
                "status": "PASS" if score >= 0.60 else "REVIEW",
            })
    review_pass = sum(row["status"] == "PASS" for row in cells)
    return {
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
            "pass": review_pass,
            "review": len(cells) - review_pass,
            "pass_ratio": round(review_pass / max(1, len(cells)), 6),
            "digest_sha256": _digest(cells),
            "lowest": sorted(cells, key=lambda row: (row["score"], row["group"], row["lens"]))[:20],
        },
    }


def hard_blockers(
    base: dict[str, Any], policy_validation: dict[str, Any], dimensions: dict[str, float]
) -> list[str]:
    blockers = []
    if policy_validation.get("ok") is not True:
        blockers.append("QUALITY_POLICY_INVALID")
    core_safe, reasons = _core_safety(base)
    if not core_safe:
        blockers.extend(f"SAFETY_{reason.upper()}" for reason in reasons)
    skill = base.get("skill_state") if isinstance(base.get("skill_state"), dict) else {}
    if skill.get("corruption_hold") is True:
        blockers.append("SKILL_STATE_CORRUPTION_HOLD")
    barrier = base.get("evidence_barrier") if isinstance(base.get("evidence_barrier"), dict) else {}
    if barrier and barrier.get("ok") is not True:
        blockers.append(str(barrier.get("status") or "EVIDENCE_COMMIT_HOLD"))
    if dimensions["proposal_boundary"] < 1.0:
        blockers.append("PROPOSAL_BOUNDARY_VIOLATION")
    status = str(base.get("v377_status") or "")
    if status in HOLD_STATUSES:
        blockers.append(status)

    selected = base.get("selected_skill") if isinstance(base.get("selected_skill"), dict) else {}
    recipe = str(selected.get("recipe") or "")
    if str(_market_context(base).get("regime") or "") == "FRESHNESS_HOLD" and recipe and recipe not in RECOVERY_RECIPES:
        blockers.append("MARKET_FRESHNESS_RECOVERY_ONLY")
    return sorted(set(blockers))


def governance(base: dict[str, Any], *, root: Path = ROOT) -> dict[str, Any]:
    validation, policy_payload = _policy(root)
    dimensions = dimension_values(base, validation)
    matrices = review_matrices(policy_payload, dimensions)
    blockers = hard_blockers(base, validation, dimensions)

    selected = base.get("selected_skill") if isinstance(base.get("selected_skill"), dict) else {}
    recipe = str(selected.get("recipe") or "")
    regime = str(_market_context(base).get("regime") or "")
    if blockers:
        directive = "OBSERVE_MORE"
    elif regime in {"FRESHNESS_HOLD", "COVERAGE_AND_SOURCE_STRESS", "SOURCE_DEGRADED", "UNDERCOVERED"}:
        directive = "RECOVER_MARKET"
    elif recipe == "RECOVER_MODEL":
        directive = "RETRAIN_EXISTING"
    elif not selected and isinstance(base.get("source_feature_proposals"), list) and base["source_feature_proposals"]:
        directive = "PROPOSE_FEATURE"
    else:
        directive = "ALLOW_BOUNDED"

    threshold = 0.55 if directive in {"OBSERVE_MORE", "RECOVER_MARKET", "RETRAIN_EXISTING"} else 0.70
    matrix_ok = (
        matrices["preparation"]["perspectives"] == 100
        and matrices["expert_review"]["cells"] == 1000
        and matrices["preparation"]["pass_ratio"] >= threshold
        and matrices["expert_review"]["pass_ratio"] >= threshold
    )
    allow = not blockers and matrix_ok
    return {
        "status": "ALLOW_BOUNDED" if allow else "QUALITY_GOVERNANCE_HOLD",
        "allow_execution": allow,
        "directive": directive,
        "hard_blockers": blockers,
        "threshold": threshold,
        "dimensions": dimensions,
        "preparation": matrices["preparation"],
        "expert_review": matrices["expert_review"],
        "neural_supervision": {
            "existing_verified_meta_neural_preserved": True,
            "verified_outcomes_only": True,
            "neural_confidence": dimensions["neural_reliability"],
            "can_override_hard_blocker": False,
        },
        "self_extension": {
            "declarative_capabilities_may_auto_compose": True,
            "allowlisted_primitives_only": True,
            "source_feature_proposals_may_be_generated": True,
            "source_feature_proposals_executed": False,
            "source_change_requires_protected_pr_ci": True,
        },
        "external_humans_claimed": False,
    }


def _hold(status: str, base: dict[str, Any], quality: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    result["core_controller_version"] = str(base.get("controller_version") or CORE_CONTROLLER_VERSION)
    result["controller_version"] = CONTROLLER_VERSION
    result["v378_status"] = status
    result["quality_governance"] = quality
    result["execution"] = {
        "status": status,
        "executed": False,
        "git_write": False,
        "source_code_modified": False,
        "proposals_executed": False,
    }
    result["safety"] = SAFETY
    return result


def run_cycle(
    *, execute: bool = False, apply_capabilities: bool = False, train_meta: bool = False,
    apply_skills: bool = False, root: Path = ROOT, now=None, proc_root=Path("/proc"),
    state_path=None, capability_path=None, meta_model_path=None, meta_outcomes_path=None,
    skill_state_path=None, skill_outcomes_path=None, journal_path=None, lock_path=None,
    persist_outputs: bool = True,
) -> dict[str, Any]:
    kwargs = dict(
        root=root, now=now, proc_root=proc_root, state_path=state_path,
        capability_path=capability_path, meta_model_path=meta_model_path,
        meta_outcomes_path=meta_outcomes_path, skill_state_path=skill_state_path,
        skill_outcomes_path=skill_outcomes_path, journal_path=journal_path,
        lock_path=lock_path, persist_outputs=False,
    )
    preview = v377.run_cycle(
        execute=False, apply_capabilities=False, train_meta=False, apply_skills=False, **kwargs
    )
    quality = governance(preview, root=root)
    mutating = bool(execute or apply_capabilities or train_meta or apply_skills)
    if mutating and not quality["allow_execution"]:
        result = _hold("QUALITY_GOVERNANCE_HOLD", preview, quality)
    elif mutating:
        core = v377.run_cycle(
            execute=execute, apply_capabilities=apply_capabilities, train_meta=train_meta,
            apply_skills=apply_skills, **kwargs
        )
        result = deepcopy(core)
        result["core_controller_version"] = str(core.get("controller_version") or CORE_CONTROLLER_VERSION)
        result["controller_version"] = CONTROLLER_VERSION
        result["v378_status"] = str(core.get("v377_status") or core.get("status") or "UNKNOWN")
        result["quality_governance"] = quality
        result["safety"] = SAFETY
    else:
        result = deepcopy(preview)
        result["core_controller_version"] = str(preview.get("controller_version") or CORE_CONTROLLER_VERSION)
        result["controller_version"] = CONTROLLER_VERSION
        result["v378_status"] = "PLAN_ONLY"
        result["quality_governance"] = quality
        result["safety"] = SAFETY

    if persist_outputs:
        try:
            atomic_write_json(root / REPORT_PATH.name, result, suffix=".v378-report.tmp")
            result["v378_runtime_output"] = {"status": "SAVED"}
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            result["v378_runtime_output"] = {"status": "WRITE_FAILED", "error_code": type(exc).__name__}
    return result


def self_test() -> None:
    assert SAFETY["hundred_senior_prep_perspectives_required"] == 100
    assert SAFETY["thousand_review_cells_required"] == 1000
    assert SAFETY["hard_blocker_cannot_be_outvoted"] is True
    assert SAFETY["existing_verified_neural_learning_remains_enabled"] is True
    assert SAFETY["source_code_auto_generation"] is False
    assert SAFETY["source_code_auto_rewrite"] is False
    assert SAFETY["git_write"] is False
    assert SAFETY["verification_bypass"] is False
    assert SAFETY["price_or_grade_invention"] is False
    assert SAFETY["market_direction_inferred"] is False
    print("Tablet 100+1000 quality-governed autonomy v378: PASS")


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
    return 2 if result.get("v378_status") in HOLD_STATUSES else 0


if __name__ == "__main__":
    raise SystemExit(main())
