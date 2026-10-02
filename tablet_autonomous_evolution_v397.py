#!/usr/bin/env python3
"""V397: bounded self-extending and self-rollback supervisor for Tablet GPT.

V397 sits above V391 and keeps every V391/V390/V388 hard gate mandatory.
It adds a bounded lifecycle around verified Tablet autonomy:

* select an operational mode from market freshness/coverage/source health,
  V391 diagnosis, uncertainty/drift, neural consensus and resource headroom;
* add at most one V397-owned canonical V373 declarative capability for the
  next cycle only;
* measure later operational KPI movement and automatically remove only that
  exact V397-owned capability after material regression or an upstream hold;
* promote recurring source-level ideas only from explicit verified canary
  evidence to a protected-PR candidate. Runtime source generation/rewrite
  remains forbidden.

"Market flow" here is operational evidence (freshness, coverage, source health,
regime/drift/uncertainty). No market direction, price, grade or card fact is
invented.
"""
from __future__ import annotations

import argparse
import json
import math
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tablet_autonomous_evolution_v391 as v391
from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
CONTROLLER_VERSION = "v397"
CORE_CONTROLLER_VERSION = "v391"

STATE_PATH = ROOT / ".tablet_autonomy_v397_state.json"
REPORT_PATH = ROOT / "tablet_autonomy_v397_report.json"
FEATURE_PLAN_PATH = ROOT / "tablet_autonomy_feature_lifecycle_v397.json"
LOCK_PATH = ROOT / ".tablet_autonomy_execution_v397.lock"

STATE_SCHEMA_VERSION = 1
MAX_STATE_BYTES = 1_500_000
MAX_HISTORY = 192
MAX_FEATURE_MEMORY = 96
ROLLBACK_KPI_DROP = 0.08
SOURCE_PROMOTION_KPI_DELTA = 0.02
SOURCE_ROLLBACK_KPI_DELTA = -0.03
MIN_VERIFIED_CANARY_SUCCESSES = 2
CAPABILITY_COOLDOWN_CYCLES = 1

_HOLD_STATUSES = set(getattr(v391, "_HOLD_STATUSES", set())) | {
    "V397_STATE_CORRUPTION_HOLD",
    "V397_CONCURRENT_AUTONOMY_HOLD",
    "V397_UPSTREAM_HOLD",
    "V397_CAPABILITY_CORRUPTION_HOLD",
    "V397_CAPABILITY_WRITE_HOLD",
    "V397_CAPABILITY_ROLLBACK_HOLD",
    "V397_STATE_COMMIT_HOLD",
}

SAFETY = dict(v391.SAFETY)
SAFETY.update({
    "operational_mode_self_selection": True,
    "market_flow_operational_only": True,
    "feature_lifecycle_verified_canary_enabled": True,
    "declarative_self_extension_enabled": True,
    "declarative_self_extension_owned_only": True,
    "declarative_self_extension_allowlisted_only": True,
    "declarative_self_extension_next_cycle_only": True,
    "owned_capability_auto_rollback_enabled": True,
    "owned_capability_material_kpi_regression_only": True,
    "source_feature_verified_canary_required": True,
    "source_feature_protected_pr_candidate_enabled": True,
    "source_feature_runtime_auto_execution": False,
    "source_code_auto_generation": False,
    "source_code_auto_rewrite": False,
    "arbitrary_command_execution": False,
    "git_write": False,
    "direct_main_write": False,
    "verification_bypass": False,
    "trust_or_fact_auto_promotion": False,
    "market_direction_inferred": False,
    "price_or_grade_invention": False,
    "peer_model_weights_imported": False,
    "peer_raw_state_imported": False,
    "v391_gate_cannot_be_bypassed": True,
    "v390_gate_cannot_be_bypassed": True,
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
        "schema_version": STATE_SCHEMA_VERSION,
        "controller_version": CONTROLLER_VERSION,
        "cycle": 0,
        "active_capability": None,
        "capability_cooldown_until_cycle": 0,
        "feature_memory": {},
        "last_kpi_score": None,
        "history": [],
    }


def _valid_active_capability(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, dict):
        return False
    if set(value) != {"id", "primitive", "baseline_kpi", "activated_cycle", "goal_id"}:
        return False
    if not isinstance(value["id"], str) or not value["id"] or len(value["id"]) > 180:
        return False
    if not isinstance(value["primitive"], str) or not value["primitive"] or len(value["primitive"]) > 80:
        return False
    baseline = _finite(value["baseline_kpi"])
    if baseline is None or not 0.0 <= baseline <= 1.0:
        return False
    if not isinstance(value["activated_cycle"], int) or value["activated_cycle"] < 0:
        return False
    return isinstance(value["goal_id"], str) and len(value["goal_id"]) <= 120


def _valid_feature_memory(value: Any) -> bool:
    allowed_stages = {
        "observe", "shadow_spec", "canary_spec",
        "protected_pr_candidate", "rollback_candidate",
    }
    if not isinstance(value, dict) or len(value) > MAX_FEATURE_MEMORY:
        return False
    for proposal_id, row in value.items():
        if not isinstance(proposal_id, str) or not proposal_id or len(proposal_id) > 220:
            return False
        if not isinstance(row, dict):
            return False
        if set(row) != {
            "stage", "observations", "verified_canary_successes",
            "verified_canary_failures", "last_verified_kpi_delta", "last_seen_cycle",
        }:
            return False
        if row["stage"] not in allowed_stages:
            return False
        for key in ("observations", "verified_canary_successes", "verified_canary_failures", "last_seen_cycle"):
            if not isinstance(row[key], int) or row[key] < 0:
                return False
        delta = row["last_verified_kpi_delta"]
        if delta is not None:
            number = _finite(delta)
            if number is None or not -1.0 <= number <= 1.0:
                return False
    return True


def _valid_state(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if set(value) != {
        "schema_version", "controller_version", "cycle", "active_capability",
        "capability_cooldown_until_cycle", "feature_memory", "last_kpi_score", "history",
    }:
        return False
    if value["schema_version"] != STATE_SCHEMA_VERSION or value["controller_version"] != CONTROLLER_VERSION:
        return False
    if not isinstance(value["cycle"], int) or not 0 <= value["cycle"] <= 10_000_000:
        return False
    if not isinstance(value["capability_cooldown_until_cycle"], int) or value["capability_cooldown_until_cycle"] < 0:
        return False
    if not _valid_active_capability(value["active_capability"]):
        return False
    if not _valid_feature_memory(value["feature_memory"]):
        return False
    score = value["last_kpi_score"]
    if score is not None:
        number = _finite(score)
        if number is None or not 0.0 <= number <= 1.0:
            return False
    return isinstance(value["history"], list) and len(value["history"]) <= MAX_HISTORY


def load_state(path: Path = STATE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"state": _default_state(), "status": "fresh", "corruption_hold": False}
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError("UNSAFE_V397_STATE_PATH")
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
            "error_code": "V397_STATE_SCHEMA_INVALID",
        }
    return {"state": value, "status": "loaded", "corruption_hold": False}


def save_state(state: dict[str, Any], path: Path, *, corruption_hold: bool) -> dict[str, Any]:
    if corruption_hold:
        return {"status": "V397_STATE_CORRUPTION_HOLD", "written": False}
    if not _valid_state(state):
        return {"status": "V397_STATE_INVALID", "written": False}
    try:
        atomic_write_json(path, state, suffix=".v397-state.tmp")
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        return {
            "status": "V397_STATE_WRITE_FAILED",
            "written": False,
            "error_code": type(exc).__name__,
        }
    return {"status": "V397_STATE_SAVED", "written": True}


def _kpi_score(result: dict[str, Any]) -> float | None:
    kpis = result.get("v382_kpis")
    kpis = kpis if isinstance(kpis, dict) else {}
    score = _finite(kpis.get("score"))
    return _clamp(score) if score is not None else None


def _dimensions(result: dict[str, Any]) -> dict[str, float]:
    kpis = result.get("v382_kpis")
    kpis = kpis if isinstance(kpis, dict) else {}
    raw = kpis.get("dimensions")
    raw = raw if isinstance(raw, dict) else {}
    values: dict[str, float] = {}
    for name in (
        "market_freshness", "market_coverage", "source_health",
        "neural_consensus", "resource_headroom",
    ):
        number = _finite(raw.get(name))
        values[name] = _clamp(number if number is not None else 0.5)
    return values


def operating_mode(result: dict[str, Any]) -> dict[str, Any]:
    dims = _dimensions(result)
    budget = result.get("v388_resource_budget")
    budget = budget if isinstance(budget, dict) else {}
    diagnosis = result.get("v391_self_diagnosis")
    diagnosis = diagnosis if isinstance(diagnosis, dict) else {}
    gate = result.get("v391_autonomous_gate")
    gate = gate if isinstance(gate, dict) else {}

    uncertainty = _clamp(float(_finite(budget.get("selected_uncertainty")) or 0.0))
    drift = _clamp(float(_finite(budget.get("drift_score")) or 0.0))
    diagnostic_regime = str(diagnosis.get("operational_regime") or "")
    top_fault = diagnosis.get("top_fault")
    top_fault = top_fault if isinstance(top_fault, dict) else {}
    top_fault_id = str(top_fault.get("fault_id") or "")

    if gate.get("allow_execution") is not True:
        mode, budget_value, reason = "HOLD", 0.0, "v391_hard_gate"
    elif diagnostic_regime == "RECOVERY_GOVERNANCE":
        mode, budget_value, reason = "RECOVERY_GOVERNANCE", 0.05, top_fault_id or diagnostic_regime
    elif dims["market_freshness"] < 0.55:
        mode, budget_value, reason = "FRESHNESS_RECOVERY", 0.10, "market_freshness"
    elif dims["source_health"] < 0.65:
        mode, budget_value, reason = "SOURCE_HEAL", 0.12, "source_health"
    elif dims["market_coverage"] < 0.70:
        mode, budget_value, reason = "COVERAGE_BUILD", 0.18, "market_coverage"
    elif max(uncertainty, drift) > 0.55 or diagnostic_regime == "REVALIDATION":
        mode, budget_value, reason = "REVALIDATE", 0.12, "uncertainty_or_drift"
    elif dims["resource_headroom"] < 0.30:
        mode, budget_value, reason = "CONSERVE_RESOURCES", 0.05, "resource_headroom"
    elif dims["neural_consensus"] < 0.70 or diagnostic_regime == "VERIFIED_LEARNING":
        mode, budget_value, reason = "VERIFIED_LEARNING", 0.22, "neural_consensus"
    else:
        mode, budget_value, reason = "STEADY_OPTIMIZATION", 0.16, "balanced_operational_state"

    resource_scale = 0.5 + 0.5 * dims["resource_headroom"]
    learning_budget = round(_clamp(budget_value * resource_scale, 0.0, 0.25), 6)
    return {
        "mode": mode,
        "reason": reason,
        "learning_budget": learning_budget,
        "dimensions": dims,
        "uncertainty": round(uncertainty, 6),
        "drift": round(drift, 6),
        "v391_diagnostic_regime": diagnostic_regime,
        "market_direction_inferred": False,
    }


def _source_stage(row: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    priority = _clamp(float(_finite(row.get("v388_priority_score")) or 0.0))
    recurrence = max(0, int(row.get("v388_recurrence") or 0))
    successes = max(0, int(row.get("verified_canary_successes") or 0))
    failures = max(0, int(row.get("verified_canary_failures") or 0))
    delta = _finite(row.get("verified_kpi_delta"))
    output_ok = row.get("verified_output_passed") is True

    if failures > 0 or (delta is not None and delta <= SOURCE_ROLLBACK_KPI_DELTA):
        stage = "rollback_candidate"
    elif (
        successes >= MIN_VERIFIED_CANARY_SUCCESSES
        and delta is not None
        and delta >= SOURCE_PROMOTION_KPI_DELTA
        and output_ok
    ):
        stage = "protected_pr_candidate"
    elif priority >= 0.72 and recurrence >= 3:
        stage = "canary_spec"
    elif priority >= 0.48:
        stage = "shadow_spec"
    else:
        stage = "observe"
    return stage, {
        "priority": round(priority, 6),
        "recurrence": recurrence,
        "verified_canary_successes": successes,
        "verified_canary_failures": failures,
        "verified_kpi_delta": round(delta, 6) if delta is not None else None,
        "verified_output_passed": output_ok,
    }


def source_feature_lifecycle(result: dict[str, Any], state: dict[str, Any]) -> list[dict[str, Any]]:
    rows = result.get("v391_feature_lifecycle")
    rows = rows if isinstance(rows, list) else []
    cycle = int(state.get("cycle") or 0) + 1
    output = []
    for raw in rows[:MAX_FEATURE_MEMORY]:
        if not isinstance(raw, dict):
            continue
        proposal_id = str(
            raw.get("v388_proposal_id")
            or raw.get("proposal_id")
            or raw.get("feature_id")
            or ""
        )[:220]
        if not proposal_id:
            continue
        stage, evidence = _source_stage(raw)
        output.append({
            "proposal_id": proposal_id,
            "stage": stage,
            "cycle": cycle,
            **evidence,
            "auto_execute": False,
            "auto_generate_source": False,
            "git_write": False,
            "promotion_requires": [
                "verified_canary_evidence",
                "positive_verified_kpi_delta",
                "actual_output_validation",
                "targeted_tests",
                "related_regression",
                "full_runtime_regression",
                "repository_integrity",
                "tablet_gpt_tcg_grader_alignment",
                "protected_pr_ci",
            ],
        })
    return output


def _candidate_from_result(result: dict[str, Any]) -> dict[str, Any] | None:
    remediation = result.get("v391_remediation_candidate")
    remediation = remediation if isinstance(remediation, dict) else {}
    candidate = remediation.get("candidate")
    if isinstance(candidate, dict):
        return candidate
    goal_cap = result.get("v390_goal_capability")
    goal_cap = goal_cap if isinstance(goal_cap, dict) else {}
    candidate = goal_cap.get("candidate")
    return candidate if isinstance(candidate, dict) else None


def _owned_capability(candidate: dict[str, Any] | None, *, now: datetime) -> dict[str, Any] | None:
    if not isinstance(candidate, dict):
        return None
    primitive = str(candidate.get("primitive") or "")
    parameters = candidate.get("parameters")
    parameters = deepcopy(parameters) if isinstance(parameters, dict) else {}
    if primitive not in v391.v390.v373.CAPABILITY_PRIMITIVES:
        return None
    evidence = candidate.get("evidence")
    evidence = deepcopy(evidence) if isinstance(evidence, dict) else {}
    evidence.update({
        "owner_controller": CONTROLLER_VERSION,
        "reason": "v397_bounded_verified_self_extension",
    })
    row = v391.v390.v373._capability(
        primitive,
        "V397_GOAL",
        parameters,
        evidence,
        now=now,
    )
    return row if v391.v390.v373.validate_capability(row, now=now) else None


def _load_capability_ids(path: Path, *, now: datetime) -> tuple[set[str], bool]:
    loaded = v391.v390.v373.load_capabilities(path=path, now=now)
    if loaded.get("corruption_hold") is True:
        return set(), True
    return {
        str(row.get("id") or "")
        for row in list(loaded.get("capabilities") or [])
        if isinstance(row, dict) and str(row.get("id") or "")
    }, False


def _persist_owned_capability(
    candidate: dict[str, Any] | None,
    *,
    path: Path,
    now: datetime,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    owned = _owned_capability(candidate, now=now)
    if owned is None:
        return {"status": "NO_V397_CAPABILITY", "written": False}, None
    loaded = v391.v390.v373.load_capabilities(path=path, now=now)
    if loaded.get("corruption_hold") is True:
        return {"status": "V397_CAPABILITY_CORRUPTION_HOLD", "written": False}, None
    merged = v391.v390.v373.merge_capabilities(
        list(loaded.get("capabilities") or []),
        [owned],
        now=now,
    )
    write = v391.v390.v373.save_capabilities(
        merged,
        path=path,
        corruption_hold=False,
        now=now,
    )
    return write, owned if write.get("written") is True else None


def rollback_decision(state: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    active = state.get("active_capability")
    if not isinstance(active, dict):
        return {"rollback": False, "reason": None, "kpi_drop": 0.0}
    gate = result.get("v391_autonomous_gate")
    gate = gate if isinstance(gate, dict) else {}
    if gate.get("allow_execution") is not True:
        return {"rollback": True, "reason": "V391_UPSTREAM_HARD_HOLD", "kpi_drop": 0.0}

    current = _kpi_score(result)
    baseline = _finite(active.get("baseline_kpi"))
    current_cycle = int(state.get("cycle") or 0) + 1
    activated_cycle = int(active.get("activated_cycle") or 0)
    if current is None or baseline is None or current_cycle <= activated_cycle:
        return {"rollback": False, "reason": None, "kpi_drop": 0.0}
    drop = max(0.0, baseline - current)
    return {
        "rollback": drop >= ROLLBACK_KPI_DROP,
        "reason": "MATERIAL_OPERATIONAL_KPI_REGRESSION" if drop >= ROLLBACK_KPI_DROP else None,
        "kpi_drop": round(drop, 6),
    }


def _rollback_owned_capability(active: dict[str, Any], *, path: Path, now: datetime) -> dict[str, Any]:
    capability_id = str(active.get("id") or "")
    if not capability_id:
        return {"status": "NO_ACTIVE_CAPABILITY_ID", "written": False, "rolled_back": False}
    loaded = v391.v390.v373.load_capabilities(path=path, now=now)
    if loaded.get("corruption_hold") is True:
        return {"status": "V397_CAPABILITY_CORRUPTION_HOLD", "written": False, "rolled_back": False}
    existing = list(loaded.get("capabilities") or [])
    kept = [row for row in existing if str(row.get("id") or "") != capability_id]
    if len(kept) == len(existing):
        return {"status": "V397_CAPABILITY_ALREADY_ABSENT", "written": False, "rolled_back": True}
    write = v391.v390.v373.save_capabilities(
        kept,
        path=path,
        corruption_hold=False,
        now=now,
    )
    return {
        **write,
        "rolled_back": write.get("written") is True,
        "capability_id": capability_id,
    }


def _next_state(
    state: dict[str, Any],
    lifecycle: list[dict[str, Any]],
    *,
    kpi_score: float | None,
    new_capability: dict[str, Any] | None,
    rolled_back: bool,
    rollback_reason: str | None,
    mode: dict[str, Any],
    result: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    nxt = deepcopy(state)
    cycle = min(10_000_000, int(state.get("cycle") or 0) + 1)
    memory = dict(state.get("feature_memory") or {})
    for row in lifecycle:
        proposal_id = row["proposal_id"]
        old = memory.get(proposal_id) if isinstance(memory.get(proposal_id), dict) else {}
        memory[proposal_id] = {
            "stage": row["stage"],
            "observations": min(1_000_000, int(old.get("observations") or 0) + 1),
            "verified_canary_successes": int(row["verified_canary_successes"]),
            "verified_canary_failures": int(row["verified_canary_failures"]),
            "last_verified_kpi_delta": row["verified_kpi_delta"],
            "last_seen_cycle": cycle,
        }
    memory = dict(sorted(
        memory.items(),
        key=lambda pair: (-int(pair[1]["last_seen_cycle"]), pair[0]),
    )[:MAX_FEATURE_MEMORY])

    active = state.get("active_capability")
    cooldown = int(state.get("capability_cooldown_until_cycle") or 0)
    if rolled_back:
        active = None
        cooldown = cycle + CAPABILITY_COOLDOWN_CYCLES
    elif new_capability is not None:
        plan = result.get("v390_goal_plan")
        plan = plan if isinstance(plan, dict) else {}
        primary = plan.get("primary_goal")
        primary = primary if isinstance(primary, dict) else {}
        active = {
            "id": str(new_capability["id"])[:180],
            "primitive": str(new_capability["primitive"])[:80],
            "baseline_kpi": round(kpi_score if kpi_score is not None else 0.5, 6),
            "activated_cycle": cycle,
            "goal_id": str(primary.get("goal_id") or "")[:120],
        }

    history = list(state.get("history") or [])
    history.append({
        "observed_at": now.isoformat(timespec="seconds"),
        "cycle": cycle,
        "mode": mode.get("mode"),
        "kpi_score": round(kpi_score, 6) if kpi_score is not None else None,
        "active_capability": active.get("id") if isinstance(active, dict) else None,
        "rolled_back": bool(rolled_back),
        "rollback_reason": rollback_reason,
        "upstream_status": result.get("v391_status"),
    })
    nxt.update({
        "schema_version": STATE_SCHEMA_VERSION,
        "controller_version": CONTROLLER_VERSION,
        "cycle": cycle,
        "active_capability": active,
        "capability_cooldown_until_cycle": cooldown,
        "feature_memory": memory,
        "last_kpi_score": round(kpi_score, 6) if kpi_score is not None else None,
        "history": history[-MAX_HISTORY:],
    })
    return nxt


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
    cap_raw = upstream_paths.get("capability_path")
    cap_path = Path(cap_raw) if cap_raw is not None else (root / v391.v390.v373.CAPABILITY_PATH.name)

    fd = None
    if mutating:
        fd, _ = v391.v390.v388.v387.v386.v385._acquire_lock(root / LOCK_PATH.name)
        if fd is None:
            return {
                "controller_version": CONTROLLER_VERSION,
                "v397_status": "V397_CONCURRENT_AUTONOMY_HOLD",
                "execution": {
                    "status": "V397_CONCURRENT_AUTONOMY_HOLD",
                    "executed": False,
                    "git_write": False,
                    "source_code_modified": False,
                },
                "safety": SAFETY,
            }

    try:
        preview = v391.run_cycle(
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
        working_state = deepcopy(loaded["state"])

        if isinstance(working_state.get("active_capability"), dict):
            ids, cap_corrupt = _load_capability_ids(cap_path, now=moment)
            if cap_corrupt:
                loaded["corruption_hold"] = True
            elif str(working_state["active_capability"].get("id") or "") not in ids:
                working_state["active_capability"] = None

        mode = operating_mode(preview)
        lifecycle = source_feature_lifecycle(preview, working_state)
        rollback_plan = rollback_decision(working_state, preview)

        upstream_gate = preview.get("v391_autonomous_gate")
        upstream_gate = upstream_gate if isinstance(upstream_gate, dict) else {}
        allow = upstream_gate.get("allow_execution") is True and not loaded.get("corruption_hold")
        status = "V397_VERIFIED_ALLOW" if allow else (
            "V397_STATE_CORRUPTION_HOLD" if loaded.get("corruption_hold") else "V397_UPSTREAM_HOLD"
        )

        rollback_write = {"status": "ROLLBACK_NOT_REQUESTED", "written": False, "rolled_back": False}
        rolled_back = False
        if (
            mutating
            and apply_capabilities
            and rollback_plan.get("rollback") is True
            and isinstance(working_state.get("active_capability"), dict)
            and not loaded.get("corruption_hold")
        ):
            rollback_write = _rollback_owned_capability(
                working_state["active_capability"],
                path=cap_path,
                now=moment,
            )
            rolled_back = rollback_write.get("rolled_back") is True
            if not rolled_back:
                allow = False
                status = (
                    "V397_CAPABILITY_CORRUPTION_HOLD"
                    if rollback_write.get("status") == "V397_CAPABILITY_CORRUPTION_HOLD"
                    else "V397_CAPABILITY_ROLLBACK_HOLD"
                )

        base = preview
        if mutating and allow:
            # V397 owns next-cycle capability persistence. V391/V390 still own
            # all diagnosis, learning, decision and execution gates.
            base = v391.run_cycle(
                domain=domain,
                execute=execute,
                apply_capabilities=False,
                train_meta=train_meta,
                apply_skills=apply_skills,
                root=root,
                now=moment,
                persist_outputs=False,
                **upstream_paths,
            )
            if str(base.get("v391_status") or "") in getattr(v391, "_HOLD_STATUSES", set()):
                allow = False
                status = "V397_UPSTREAM_HOLD"

        capability_write = {"status": "V397_CAPABILITY_NOT_REQUESTED", "written": False}
        new_capability = None
        state_cycle = int(working_state.get("cycle") or 0)
        cooldown_until = int(working_state.get("capability_cooldown_until_cycle") or 0)
        no_active = not isinstance(working_state.get("active_capability"), dict)
        if (
            mutating
            and apply_capabilities
            and allow
            and not rolled_back
            and no_active
            and state_cycle >= cooldown_until
        ):
            candidate = _candidate_from_result(preview)
            capability_write, new_capability = _persist_owned_capability(
                candidate,
                path=cap_path,
                now=moment,
            )
            if capability_write.get("status") == "V397_CAPABILITY_CORRUPTION_HOLD":
                allow = False
                status = "V397_CAPABILITY_CORRUPTION_HOLD"
            elif candidate is not None and capability_write.get("written") is not True:
                allow = False
                status = "V397_CAPABILITY_WRITE_HOLD"

        current_kpi = _kpi_score(base)
        result = deepcopy(base)
        result.update({
            "core_controller_version": str(base.get("controller_version") or CORE_CONTROLLER_VERSION),
            "controller_version": CONTROLLER_VERSION,
            "v397_status": status if mutating else "PLAN_ONLY",
            "v397_operating_mode": mode,
            "v397_feature_lifecycle": lifecycle,
            "v397_rollback": {
                "decision": rollback_plan,
                "write": rollback_write,
                "owned_capability_only": True,
            },
            "v397_self_extension": {
                "write": capability_write,
                "new_capability": new_capability,
                "canonical_allowlist_only": True,
                "next_cycle_only": True,
                "source_code_generated": False,
                "git_write": False,
            },
            "v397_autonomous_gate": {
                "status": status,
                "allow_execution": allow,
                "v391_gate_required": True,
                "hard_blocker_override": False,
            },
            "evolution_contract_v397": {
                "core": "v391_self_diagnosis_counterfactual_verified_regression",
                "neural_core": "v390_goal_directed_verified_meta_critic",
                "loop": "observe_diagnose_select_learn_extend_measure_rollback_or_promote",
                "market_adaptation": "operational_freshness_coverage_source_health_uncertainty_resource_only",
                "runtime_self_extension": "one_v397_owned_canonical_v373_declarative_capability_next_cycle_only",
                "source_level_extension": "verified_canary_to_protected_pr_candidate_only",
                "automatic_source_generation": False,
                "automatic_source_rewrite": False,
                "direct_git_or_main_write": False,
                "v391_v390_and_prior_gate_bypass": False,
                "market_direction_inferred": False,
            },
            "safety": SAFETY,
        })
        if mutating and not allow:
            result["execution"] = {
                "status": status,
                "executed": False,
                "git_write": False,
                "source_code_modified": False,
                "proposals_executed": False,
            }

        state_write = {"status": "V397_STATE_WRITE_NOT_REQUESTED", "written": False}
        if mutating:
            next_state = _next_state(
                working_state,
                lifecycle,
                kpi_score=current_kpi,
                new_capability=new_capability,
                rolled_back=rolled_back,
                rollback_reason=rollback_plan.get("reason"),
                mode=mode,
                result=base,
                now=moment,
            )
            state_write = save_state(
                next_state,
                state_file,
                corruption_hold=bool(loaded.get("corruption_hold")),
            )
            if not state_write.get("written"):
                if new_capability is not None:
                    _rollback_owned_capability(
                        {
                            "id": new_capability["id"],
                            "primitive": new_capability["primitive"],
                            "baseline_kpi": current_kpi if current_kpi is not None else 0.5,
                            "activated_cycle": state_cycle + 1,
                            "goal_id": "",
                        },
                        path=cap_path,
                        now=moment,
                    )
                result["v397_status"] = "V397_STATE_COMMIT_HOLD"
                result["v397_autonomous_gate"] = {
                    **result["v397_autonomous_gate"],
                    "status": "V397_STATE_COMMIT_HOLD",
                    "allow_execution": False,
                }
                result["execution"] = {
                    "status": "V397_STATE_COMMIT_HOLD",
                    "executed": False,
                    "git_write": False,
                    "source_code_modified": False,
                    "proposals_executed": False,
                }
        result["v397_state_write"] = state_write

        if persist_outputs:
            try:
                atomic_write_json(
                    root / FEATURE_PLAN_PATH.name,
                    {
                        "schema_version": 1,
                        "controller_version": CONTROLLER_VERSION,
                        "generated_at": moment.isoformat(timespec="seconds"),
                        "operating_mode": mode,
                        "features": lifecycle,
                        "runtime_source_auto_generation": False,
                        "protected_pr_ci_required": True,
                    },
                    suffix=".v397-feature-plan.tmp",
                )
                atomic_write_json(root / REPORT_PATH.name, result, suffix=".v397-report.tmp")
                result["v397_runtime_output"] = {"status": "SAVED"}
            except (OSError, UnicodeError, ValueError, TypeError) as exc:
                result["v397_runtime_output"] = {
                    "status": "WRITE_FAILED",
                    "error_code": type(exc).__name__,
                }
        return result
    finally:
        if fd is not None:
            v391.v390.v388.v387.v386.v385._release_lock(fd)


def self_test() -> None:
    state = _default_state()
    assert _valid_state(state)
    assert SAFETY["declarative_self_extension_enabled"] is True
    assert SAFETY["owned_capability_auto_rollback_enabled"] is True
    assert SAFETY["source_feature_verified_canary_required"] is True
    assert SAFETY["source_code_auto_generation"] is False
    assert SAFETY["source_code_auto_rewrite"] is False
    assert SAFETY["git_write"] is False
    assert SAFETY["market_direction_inferred"] is False
    assert SAFETY["v391_gate_cannot_be_bypassed"] is True
    print("Tablet bounded self-extending and self-rollback supervisor v397: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", choices=sorted(v391.v390.v388.v387.v386.DOMAINS), default="tablet_gpt")
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
    return 2 if result.get("v397_status") in _HOLD_STATUSES else 0


if __name__ == "__main__":
    raise SystemExit(main())
