#!/usr/bin/env python3
"""V396: supervised self-evolution layer for Tablet GPT.

V396 keeps V390 as the mandatory goal/critic core and adds a bounded lifecycle
for self-added declarative capabilities, operational market modes, regression
rollback, and non-executable source-feature PR specifications.

Runtime self-extension is limited to the canonical V373 declarative capability
DSL already validated by V390. New source-level functionality is never written
or executed by this controller; it is emitted as a protected PR/CI candidate.
"""
from __future__ import annotations

import argparse
import json
import math
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tablet_autonomous_evolution_v390 as v390
from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
CONTROLLER_VERSION = "v396"
CORE_CONTROLLER_VERSION = "v390"

STATE_PATH = ROOT / ".tablet_autonomy_v396_state.json"
REPORT_PATH = ROOT / "tablet_autonomy_v396_report.json"
FEATURE_PLAN_PATH = ROOT / "tablet_autonomy_feature_candidates_v396.json"
LOCK_PATH = ROOT / ".tablet_autonomy_execution_v396.lock"

SCHEMA_VERSION = 1
MAX_STATE_BYTES = 1_500_000
MAX_FEATURES = 64
MAX_HISTORY = 256
SHADOW_OBSERVATIONS = 2
CANARY_OBSERVATIONS = 4
CANARY_MAX_REGRESSION = 0.03
ACTIVE_MIN_IMPROVEMENT = 0.01
ROLLBACK_REGRESSION = 0.08
DORMANT_AFTER_CYCLES = 3

_HOLD_STATUSES = set(getattr(v390, "_HOLD_STATUSES", set())) | {
    "V396_STATE_CORRUPTION_HOLD",
    "V396_CONCURRENT_AUTONOMY_HOLD",
    "V396_ROLLBACK_WRITE_HOLD",
    "V396_STATE_COMMIT_HOLD",
    "V396_UPSTREAM_HOLD",
}

SAFETY = dict(v390.SAFETY)
SAFETY.update({
    "supervised_self_evolution": True,
    "operational_market_mode_adaptation": True,
    "market_direction_inferred": False,
    "feature_lifecycle_shadow_canary_active": True,
    "verified_kpi_regression_rollback": True,
    "declarative_self_extension_allowlisted_only": True,
    "source_feature_pr_spec_generation": True,
    "source_feature_pr_spec_non_executable": True,
    "source_code_auto_generation": False,
    "source_code_auto_rewrite": False,
    "arbitrary_command_execution": False,
    "git_write": False,
    "direct_main_write": False,
    "verification_bypass": False,
    "peer_model_weights_imported": False,
    "peer_raw_state_imported": False,
    "price_or_grade_invention": False,
})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _default_state() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "controller_version": CONTROLLER_VERSION,
        "cycle": 0,
        "features": {},
        "history": [],
    }


def _valid_feature(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    required = {
        "capability_id", "stage", "observations", "baseline_score", "last_score",
        "best_score", "regressions", "last_seen_cycle", "last_transition",
    }
    if set(row) != required:
        return False
    if not isinstance(row["capability_id"], str) or not 1 <= len(row["capability_id"]) <= 180:
        return False
    if row["stage"] not in {"shadow", "canary", "active", "rollback", "dormant"}:
        return False
    for key in ("observations", "regressions", "last_seen_cycle"):
        if isinstance(row[key], bool) or not isinstance(row[key], int) or row[key] < 0:
            return False
    for key in ("baseline_score", "last_score", "best_score"):
        value = _finite(row[key])
        if value is None or not 0.0 <= value <= 1.0:
            return False
    return isinstance(row["last_transition"], str) and len(row["last_transition"]) <= 160


def _valid_state(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if set(value) != {"schema_version", "controller_version", "cycle", "features", "history"}:
        return False
    if value["schema_version"] != SCHEMA_VERSION or value["controller_version"] != CONTROLLER_VERSION:
        return False
    if isinstance(value["cycle"], bool) or not isinstance(value["cycle"], int) or value["cycle"] < 0:
        return False
    features = value["features"]
    if not isinstance(features, dict) or len(features) > MAX_FEATURES:
        return False
    if any(not isinstance(key, str) or not _valid_feature(row) for key, row in features.items()):
        return False
    return isinstance(value["history"], list) and len(value["history"]) <= MAX_HISTORY


def load_state(path: Path = STATE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"state": _default_state(), "status": "fresh", "corruption_hold": False}
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError("UNSAFE_V396_STATE_PATH")
        value = json.loads(safe_read_text(path, max_bytes=MAX_STATE_BYTES))
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return {
            "state": _default_state(),
            "status": "corrupt",
            "corruption_hold": True,
            "error_code": type(exc).__name__,
        }
    if not _valid_state(value):
        return {
            "state": _default_state(),
            "status": "corrupt",
            "corruption_hold": True,
            "error_code": "V396_STATE_SCHEMA_INVALID",
        }
    return {"state": value, "status": "loaded", "corruption_hold": False}


def save_state(state: dict[str, Any], path: Path, corruption_hold: bool) -> dict[str, Any]:
    if corruption_hold:
        return {"status": "V396_STATE_CORRUPTION_HOLD", "written": False}
    if not _valid_state(state):
        return {"status": "V396_STATE_INVALID", "written": False}
    try:
        atomic_write_json(path, state, suffix=".v396-state.tmp")
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        return {"status": "V396_STATE_WRITE_FAILED", "written": False, "error_code": type(exc).__name__}
    return {"status": "V396_STATE_SAVED", "written": True}


def operational_score(base: dict[str, Any]) -> float:
    kpis = base.get("v382_kpis") if isinstance(base.get("v382_kpis"), dict) else {}
    dims = kpis.get("dimensions") if isinstance(kpis.get("dimensions"), dict) else {}
    names = ("market_freshness", "market_coverage", "source_health", "neural_consensus", "resource_headroom")
    values = []
    for name in names:
        number = _finite(dims.get(name))
        values.append(_clamp(number if number is not None else 0.5))
    budget = base.get("v388_resource_budget") if isinstance(base.get("v388_resource_budget"), dict) else {}
    uncertainty = _finite(budget.get("selected_uncertainty"))
    drift = _finite(budget.get("drift_score"))
    instability = max(
        _clamp(uncertainty if uncertainty is not None else 0.5),
        _clamp(drift if drift is not None else 0.5),
    )
    return round(_clamp(0.70 * (sum(values) / len(values)) + 0.30 * (1.0 - instability)), 6)


def operating_mode(base: dict[str, Any]) -> dict[str, Any]:
    goals = base.get("v390_goals") if isinstance(base.get("v390_goals"), list) else []
    primary = goals[0] if goals and isinstance(goals[0], dict) else {}
    goal_id = str(primary.get("goal_id") or "STEADY_VERIFIED_OPTIMIZATION")
    urgency = _clamp(float(_finite(primary.get("urgency")) or 0.0))
    budget = base.get("v388_resource_budget") if isinstance(base.get("v388_resource_budget"), dict) else {}
    headroom = _clamp(float(_finite(budget.get("resource_headroom")) or 0.5))
    drift = _clamp(float(_finite(budget.get("drift_score")) or 0.0))
    uncertainty = _clamp(float(_finite(budget.get("selected_uncertainty")) or 0.0))

    if goal_id == "RECOVER_MARKET_FRESHNESS":
        mode = "FRESHNESS_RECOVERY"
    elif goal_id == "RECOVER_SOURCE_HEALTH":
        mode = "SOURCE_RECOVERY"
    elif goal_id == "EXPAND_VERIFIED_MARKET_COVERAGE":
        mode = "COVERAGE_EXPANSION"
    elif max(drift, uncertainty) >= 0.65:
        mode = "CONSERVATIVE_REVALIDATION"
    elif headroom <= 0.30:
        mode = "RESOURCE_PRESERVATION"
    elif goal_id in {"IMPROVE_NEURAL_CONSENSUS", "STABILIZE_POLICY_PORTFOLIO"}:
        mode = "VERIFIED_LEARNING_OPTIMIZATION"
    elif goal_id == "RESOLVE_PERSISTENT_FEATURE_GAPS":
        mode = "FEATURE_DISCOVERY"
    else:
        mode = "STEADY_VERIFIED_OPTIMIZATION"
    return {
        "mode": mode,
        "primary_goal": goal_id,
        "goal_urgency": round(urgency, 6),
        "resource_headroom": round(headroom, 6),
        "drift": round(drift, 6),
        "uncertainty": round(uncertainty, 6),
        "market_direction_inferred": False,
    }


def capability_candidate(base: dict[str, Any]) -> dict[str, Any] | None:
    section = base.get("v390_goal_capability")
    section = section if isinstance(section, dict) else {}
    row = section.get("candidate")
    if not isinstance(row, dict):
        return None
    if not v390.v373.validate_capability(row, now=_now()):
        return None
    return deepcopy(row)


def advance_feature_lifecycle(
    state: dict[str, Any],
    candidate: dict[str, Any] | None,
    score: float,
) -> dict[str, Any]:
    cycle = int(state.get("cycle") or 0) + 1
    features = deepcopy(state.get("features") or {})
    transition = "NO_CANDIDATE"

    if candidate is not None:
        capability_id = str(candidate.get("id") or "")[:180]
        row = features.get(capability_id)
        if not isinstance(row, dict):
            row = {
                "capability_id": capability_id,
                "stage": "shadow",
                "observations": 1,
                "baseline_score": score,
                "last_score": score,
                "best_score": score,
                "regressions": 0,
                "last_seen_cycle": cycle,
                "last_transition": "candidate_to_shadow",
            }
            transition = "candidate_to_shadow"
        else:
            row = deepcopy(row)
            row["observations"] = min(1_000_000, int(row["observations"]) + 1)
            row["last_score"] = score
            row["best_score"] = max(float(row["best_score"]), score)
            row["last_seen_cycle"] = cycle
            regression = float(row["best_score"]) - score
            improvement = score - float(row["baseline_score"])
            old_stage = str(row["stage"])
            if old_stage in {"canary", "active"} and regression >= ROLLBACK_REGRESSION:
                row["stage"] = "rollback"
                row["regressions"] = min(1_000_000, int(row["regressions"]) + 1)
                row["last_transition"] = f"{old_stage}_to_rollback"
            elif old_stage == "shadow" and int(row["observations"]) >= SHADOW_OBSERVATIONS:
                if score >= float(row["baseline_score"]) - CANARY_MAX_REGRESSION:
                    row["stage"] = "canary"
                    row["last_transition"] = "shadow_to_canary"
            elif old_stage == "canary" and int(row["observations"]) >= CANARY_OBSERVATIONS:
                if improvement >= ACTIVE_MIN_IMPROVEMENT:
                    row["stage"] = "active"
                    row["last_transition"] = "canary_to_active"
            elif old_stage == "rollback" and regression < CANARY_MAX_REGRESSION:
                row["stage"] = "shadow"
                row["baseline_score"] = score
                row["best_score"] = score
                row["observations"] = 1
                row["last_transition"] = "rollback_to_shadow_revalidation"
            transition = str(row["last_transition"])
        features[capability_id] = row

    for capability_id, row in list(features.items()):
        if candidate is not None and capability_id == str(candidate.get("id") or ""):
            continue
        if cycle - int(row["last_seen_cycle"]) >= DORMANT_AFTER_CYCLES and row["stage"] not in {"rollback", "dormant"}:
            updated = deepcopy(row)
            updated["stage"] = "dormant"
            updated["last_transition"] = "inactive_to_dormant"
            features[capability_id] = updated

    ordered = sorted(
        features.items(),
        key=lambda pair: (-int(pair[1]["last_seen_cycle"]), pair[0]),
    )[:MAX_FEATURES]
    return {
        "cycle": cycle,
        "features": dict(ordered),
        "candidate_id": str(candidate.get("id") or "") if candidate else None,
        "candidate_stage": (
            dict(ordered).get(str(candidate.get("id") or ""), {}).get("stage")
            if candidate else None
        ),
        "transition": transition,
    }


def rollback_capability(capability_id: str | None, path: Path, now: datetime) -> dict[str, Any]:
    if not capability_id:
        return {"status": "NO_ROLLBACK_TARGET", "written": False}
    loaded = v390.v373.load_capabilities(path=path, now=now)
    if loaded.get("corruption_hold") is True:
        return {"status": "V396_CAPABILITY_CORRUPTION_HOLD", "written": False}
    existing = list(loaded.get("capabilities") or [])
    kept = [row for row in existing if str(row.get("id") or "") != capability_id]
    if len(kept) == len(existing):
        return {"status": "ROLLBACK_TARGET_NOT_ACTIVE", "written": False}
    result = v390.v373.save_capabilities(kept, path=path, corruption_hold=False, now=now)
    return {
        "status": "V396_CAPABILITY_ROLLED_BACK" if result.get("written") else "V396_ROLLBACK_WRITE_FAILED",
        "written": bool(result.get("written")),
        "remaining": len(kept),
    }


def source_feature_candidates(base: dict[str, Any], mode: dict[str, Any]) -> list[dict[str, Any]]:
    rows = base.get("v390_source_feature_plan")
    rows = rows if isinstance(rows, list) else []
    result = []
    for row in rows[:24]:
        if not isinstance(row, dict):
            continue
        stage = str(row.get("v390_stage") or "observe")
        if stage not in {"shadow_spec", "protected_pr_candidate"}:
            continue
        proposal_id = str(row.get("v388_proposal_id") or row.get("proposal_id") or "")[:180]
        result.append({
            "proposal_id": proposal_id,
            "stage": stage,
            "operating_mode": mode["mode"],
            "priority": round(_clamp(float(_finite(row.get("v388_priority_score")) or 0.0)), 6),
            "auto_execute": False,
            "auto_generate_source": False,
            "git_write": False,
            "protected_pr_ci_required": True,
            "required_validation": [
                "shadow_spec",
                "targeted_tests",
                "related_regression",
                "canary_validation",
                "full_current_runtime",
                "repository_integrity",
                "tablet_gpt_tcg_grader_alignment",
                "actual_output_validation",
            ],
        })
    return result


def _next_state(
    current: dict[str, Any],
    lifecycle: dict[str, Any],
    mode: dict[str, Any],
    score: float,
    gate_status: str,
    now: datetime,
) -> dict[str, Any]:
    history = list(current.get("history") or [])
    history.append({
        "observed_at": now.isoformat(timespec="seconds"),
        "cycle": lifecycle["cycle"],
        "operating_mode": mode["mode"],
        "primary_goal": mode["primary_goal"],
        "health_score": score,
        "candidate_id": lifecycle["candidate_id"],
        "candidate_stage": lifecycle["candidate_stage"],
        "transition": lifecycle["transition"],
        "gate_status": gate_status,
    })
    return {
        "schema_version": SCHEMA_VERSION,
        "controller_version": CONTROLLER_VERSION,
        "cycle": lifecycle["cycle"],
        "features": lifecycle["features"],
        "history": history[-MAX_HISTORY:],
    }


def run_cycle(
    *,
    domain: str = "tablet_gpt",
    execute: bool = False,
    apply_capabilities: bool = False,
    train_meta: bool = False,
    apply_skills: bool = False,
    root: Path = ROOT,
    now: datetime | None = None,
    state_path: Path | None = None,
    persist_outputs: bool = True,
    **upstream_paths: Any,
) -> dict[str, Any]:
    moment = (now or _now()).astimezone(timezone.utc)
    mutating = bool(execute or apply_capabilities or train_meta or apply_skills)
    state_file = state_path or (root / STATE_PATH.name)
    cap_path_raw = upstream_paths.get("capability_path")
    cap_path = Path(cap_path_raw) if cap_path_raw is not None else (root / v390.v373.CAPABILITY_PATH.name)

    fd = None
    if mutating:
        fd, lock_info = v390.v388.v387.v386.v385._acquire_lock(root / LOCK_PATH.name)
        if fd is None:
            return {
                "controller_version": CONTROLLER_VERSION,
                "v396_status": "V396_CONCURRENT_AUTONOMY_HOLD",
                "execution": {
                    "status": "V396_CONCURRENT_AUTONOMY_HOLD",
                    "executed": False,
                    "git_write": False,
                    "source_code_modified": False,
                },
                "safety": SAFETY,
            }

    try:
        preview = v390.run_cycle(
            domain=domain,
            execute=False,
            apply_capabilities=False,
            train_meta=False,
            apply_skills=False,
            root=root,
            now=moment,
            persist_outputs=False,
            **upstream_paths,
        )
        loaded = load_state(state_file)
        score = operational_score(preview)
        mode = operating_mode(preview)
        candidate = capability_candidate(preview)
        lifecycle = advance_feature_lifecycle(loaded["state"], candidate, score)
        candidate_stage = lifecycle.get("candidate_stage")

        upstream_gate = preview.get("v390_autonomous_gate")
        upstream_gate = upstream_gate if isinstance(upstream_gate, dict) else {}
        allow_execution = upstream_gate.get("allow_execution") is True
        status = "PLAN_ONLY" if not mutating else "V396_VERIFIED_ALLOW"
        reasons: list[str] = []

        if loaded.get("corruption_hold") is True:
            allow_execution = False
            status = "V396_STATE_CORRUPTION_HOLD"
            reasons.append("STATE_CORRUPTION_HOLD")
        elif mutating and not allow_execution:
            status = "V396_UPSTREAM_HOLD"
            reasons.append(str(upstream_gate.get("status") or "V390_UPSTREAM_HOLD"))

        rollback = {"status": "ROLLBACK_NOT_REQUIRED", "written": False}
        if mutating and candidate_stage == "rollback" and not loaded.get("corruption_hold"):
            rollback = rollback_capability(lifecycle.get("candidate_id"), cap_path, moment)
            if rollback.get("status") == "V396_ROLLBACK_WRITE_FAILED":
                allow_execution = False
                status = "V396_ROLLBACK_WRITE_HOLD"
                reasons.append("ROLLBACK_WRITE_FAILED")

        base = preview
        can_apply_candidate = candidate_stage in {"canary", "active"}
        if mutating and allow_execution:
            base = v390.run_cycle(
                domain=domain,
                execute=execute,
                apply_capabilities=bool(apply_capabilities and can_apply_candidate),
                train_meta=train_meta,
                apply_skills=apply_skills,
                root=root,
                now=moment,
                persist_outputs=False,
                **upstream_paths,
            )
            if str(base.get("v390_status") or "") in getattr(v390, "_HOLD_STATUSES", set()):
                status = "V396_UPSTREAM_HOLD"
                allow_execution = False
                reasons.append(str(base.get("v390_status") or "V390_HOLD"))

        feature_specs = source_feature_candidates(base, mode)
        result = deepcopy(base)
        result.update({
            "core_controller_version": str(base.get("controller_version") or CORE_CONTROLLER_VERSION),
            "controller_version": CONTROLLER_VERSION,
            "v396_status": status,
            "v396_operating_mode": mode,
            "v396_health_score": score,
            "v396_feature_lifecycle": {
                "candidate_id": lifecycle.get("candidate_id"),
                "candidate_stage": candidate_stage,
                "transition": lifecycle.get("transition"),
                "apply_capability_this_cycle": bool(mutating and apply_capabilities and can_apply_candidate and allow_execution),
                "rollback": rollback,
                "features": lifecycle.get("features"),
            },
            "v396_autonomous_gate": {
                "status": status,
                "allow_execution": allow_execution,
                "reasons": reasons,
                "v390_gate_required": True,
                "hard_blocker_override": False,
            },
            "v396_source_feature_candidates": feature_specs,
            "v396_ui": {
                "operating_mode": mode["mode"],
                "primary_goal": mode["primary_goal"],
                "goal_urgency": mode["goal_urgency"],
                "health_score": score,
                "critic_samples": int(
                    (preview.get("v390_meta_critic") or {}).get("sample_count") or 0
                ) if isinstance(preview.get("v390_meta_critic"), dict) else 0,
                "recommended_action": (
                    (preview.get("v390_goal_plan") or {}).get("recommended_action")
                    if isinstance(preview.get("v390_goal_plan"), dict) else None
                ),
                "upstream_action": (
                    (preview.get("v390_goal_plan") or {}).get("upstream_selected_action")
                    if isinstance(preview.get("v390_goal_plan"), dict) else None
                ),
                "feature_stage": candidate_stage,
                "feature_transition": lifecycle.get("transition"),
                "source_feature_candidates": len(feature_specs),
                "gate_status": status,
                "physical_tablet_runtime_verified": False,
            },
            "evolution_contract_v396": {
                "base_controller": "v390",
                "loop": "observe_diagnose_choose_goal_learn_shadow_canary_activate_monitor_rollback",
                "runtime_self_extension": "canonical_v373_declarative_capabilities_only",
                "source_feature_extension": "non_executable_protected_pr_ci_spec_only",
                "market_adaptation": "operational_health_regime_only_no_direction_prediction",
                "verified_regression_rollback": True,
                "v390_and_prior_gate_bypass": False,
                "source_code_auto_generation": False,
                "source_code_auto_rewrite": False,
                "arbitrary_command_execution": False,
                "git_write": False,
                "verification_bypass": False,
            },
            "safety": SAFETY,
        })

        if mutating and not allow_execution:
            result["execution"] = {
                "status": status,
                "executed": False,
                "git_write": False,
                "source_code_modified": False,
                "proposals_executed": False,
            }

        state_write = {"status": "V396_STATE_WRITE_NOT_REQUESTED", "written": False}
        if mutating:
            next_state = _next_state(
                loaded["state"], lifecycle, mode, score, status, moment
            )
            state_write = save_state(next_state, state_file, bool(loaded.get("corruption_hold")))
            if not state_write.get("written") and allow_execution:
                result["v396_status"] = "V396_STATE_COMMIT_HOLD"
                result["execution"] = {
                    "status": "V396_STATE_COMMIT_HOLD",
                    "executed": False,
                    "git_write": False,
                    "source_code_modified": False,
                    "proposals_executed": False,
                }
        result["v396_state_write"] = state_write

        if persist_outputs:
            try:
                atomic_write_json(
                    root / FEATURE_PLAN_PATH.name,
                    {
                        "schema_version": 1,
                        "controller_version": CONTROLLER_VERSION,
                        "generated_at": moment.isoformat(timespec="seconds"),
                        "operating_mode": mode,
                        "candidates": feature_specs,
                        "auto_execute": False,
                        "auto_generate_source": False,
                        "git_write": False,
                    },
                    suffix=".v396-feature-plan.tmp",
                )
                atomic_write_json(root / REPORT_PATH.name, result, suffix=".v396-report.tmp")
                result["v396_runtime_output"] = {"status": "SAVED"}
            except (OSError, UnicodeError, ValueError, TypeError) as exc:
                result["v396_runtime_output"] = {
                    "status": "WRITE_FAILED",
                    "error_code": type(exc).__name__,
                }
        return result
    finally:
        if fd is not None:
            v390.v388.v387.v386.v385._release_lock(fd)


def self_test() -> None:
    state = _default_state()
    assert _valid_state(state)
    assert SAFETY["supervised_self_evolution"] is True
    assert SAFETY["verified_kpi_regression_rollback"] is True
    assert SAFETY["declarative_self_extension_allowlisted_only"] is True
    assert SAFETY["source_feature_pr_spec_non_executable"] is True
    assert SAFETY["source_code_auto_generation"] is False
    assert SAFETY["git_write"] is False
    assert SAFETY["market_direction_inferred"] is False
    print("Tablet supervised self-evolution governor v396: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", choices=sorted(v390.v388.v387.v386.DOMAINS), default="tablet_gpt")
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
        domain=args.domain,
        execute=args.execute_safe_learning,
        apply_capabilities=args.apply_capabilities,
        train_meta=args.train_meta,
        apply_skills=args.apply_skills,
    )
    if not args.quiet:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 2 if result.get("v396_status") in _HOLD_STATUSES else 0


if __name__ == "__main__":
    raise SystemExit(main())
