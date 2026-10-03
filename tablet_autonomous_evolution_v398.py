#!/usr/bin/env python3
"""V398 verified multi-candidate self-evolution supervisor for Tablet GPT.

V398 keeps V397/V391/V390/V388 gates mandatory. It synthesizes several
canonical V373 declarative capability candidates from operational evidence,
scores them with V390 goal alignment plus locally verified KPI outcomes,
applies at most one V398-owned canary for the next cycle, learns its result,
quarantines failing recipes, and rolls back only the exact V398 capability.

Source-level feature needs stay on V397's verified-canary -> protected-PR/CI
path. No source generation/rewrite, arbitrary commands, Git/main writes,
verification bypass, market-direction inference, or invented facts/prices/
grades are allowed.
"""
from __future__ import annotations

import argparse
import json
import math
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tablet_autonomous_evolution_v397 as v397
from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
CONTROLLER_VERSION = "v398"
CORE_CONTROLLER_VERSION = "v397"
STATE_PATH = ROOT / ".tablet_autonomy_v398_state.json"
REPORT_PATH = ROOT / "tablet_autonomy_v398_report.json"
TOURNAMENT_PATH = ROOT / "tablet_autonomy_candidate_tournament_v398.json"
LOCK_PATH = ROOT / ".tablet_autonomy_execution_v398.lock"

MAX_STATE_BYTES = 1_500_000
MAX_HISTORY = 160
MAX_MEMORY = 64
MAX_CANDIDATES = 8
MIN_SCORE = 0.48
ROLLBACK_DROP = 0.06
VERIFIED_GAIN = 0.02
QUARANTINE_CYCLES = 3
COOLDOWN_CYCLES = 1

_HOLD_STATUSES = set(getattr(v397, "_HOLD_STATUSES", set())) | {
    "V398_STATE_CORRUPTION_HOLD",
    "V398_CONCURRENT_AUTONOMY_HOLD",
    "V398_UPSTREAM_HOLD",
    "V398_CAPABILITY_CORRUPTION_HOLD",
    "V398_CAPABILITY_WRITE_HOLD",
    "V398_CAPABILITY_ROLLBACK_HOLD",
    "V398_STATE_COMMIT_HOLD",
}

SAFETY = dict(v397.SAFETY)
SAFETY.update({
    "multi_candidate_self_extension_enabled": True,
    "candidate_tournament_deterministic": True,
    "candidate_tournament_allowlisted_only": True,
    "candidate_tournament_verified_history_learning": True,
    "candidate_failure_quarantine_enabled": True,
    "single_canary_capability_only": True,
    "v398_owned_capability_only": True,
    "v398_owned_capability_auto_rollback": True,
    "v397_extension_conflict_prevention": True,
    "market_flow_operational_only": True,
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
    "v397_gate_cannot_be_bypassed": True,
    "v391_gate_cannot_be_bypassed": True,
    "v390_gate_cannot_be_bypassed": True,
})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) else None


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _memory_row() -> dict[str, Any]:
    return {
        "observations": 0,
        "successes": 0,
        "failures": 0,
        "reward_ewma": 0.0,
        "last_selected_cycle": 0,
        "last_scored_cycle": 0,
        "quarantine_until_cycle": 0,
    }


def _default_state() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "controller_version": CONTROLLER_VERSION,
        "cycle": 0,
        "active": None,
        "cooldown_until_cycle": 0,
        "candidate_memory": {},
        "history": [],
    }


def _valid_state(value: Any) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "schema_version", "controller_version", "cycle", "active",
        "cooldown_until_cycle", "candidate_memory", "history",
    }:
        return False
    if value["schema_version"] != 1 or value["controller_version"] != CONTROLLER_VERSION:
        return False
    if not isinstance(value["cycle"], int) or value["cycle"] < 0:
        return False
    if not isinstance(value["cooldown_until_cycle"], int) or value["cooldown_until_cycle"] < 0:
        return False
    active = value["active"]
    if active is not None:
        if not isinstance(active, dict) or set(active) != {
            "id", "recipe_key", "primitive", "baseline_kpi",
            "activated_cycle", "goal_id", "mode",
        }:
            return False
        if any(not isinstance(active[k], str) or not active[k] for k in ("id", "recipe_key", "primitive", "goal_id", "mode")):
            return False
        baseline = _finite(active["baseline_kpi"])
        if baseline is None or not 0.0 <= baseline <= 1.0:
            return False
        if not isinstance(active["activated_cycle"], int) or active["activated_cycle"] < 0:
            return False
    memory = value["candidate_memory"]
    if not isinstance(memory, dict) or len(memory) > MAX_MEMORY:
        return False
    keys = set(_memory_row())
    for recipe, row in memory.items():
        if not isinstance(recipe, str) or not recipe or len(recipe) > 360:
            return False
        if not isinstance(row, dict) or set(row) != keys:
            return False
        for key in ("observations", "successes", "failures", "last_selected_cycle", "last_scored_cycle", "quarantine_until_cycle"):
            if not isinstance(row[key], int) or isinstance(row[key], bool) or row[key] < 0:
                return False
        reward = _finite(row["reward_ewma"])
        if reward is None or not -1.0 <= reward <= 1.0:
            return False
    return isinstance(value["history"], list) and len(value["history"]) <= MAX_HISTORY


def load_state(path: Path = STATE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"state": _default_state(), "status": "fresh", "corruption_hold": False}
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError("UNSAFE_V398_STATE_PATH")
        value = json.loads(safe_read_text(path, max_bytes=MAX_STATE_BYTES))
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return {"state": _default_state(), "status": "corrupt", "corruption_hold": True, "error_code": type(exc).__name__}
    if not _valid_state(value):
        return {"state": _default_state(), "status": "corrupt", "corruption_hold": True, "error_code": "V398_STATE_SCHEMA_INVALID"}
    return {"state": value, "status": "loaded", "corruption_hold": False}


def save_state(state: dict[str, Any], path: Path, *, corruption_hold: bool) -> dict[str, Any]:
    if corruption_hold:
        return {"status": "V398_STATE_CORRUPTION_HOLD", "written": False}
    if not _valid_state(state):
        return {"status": "V398_STATE_INVALID", "written": False}
    try:
        atomic_write_json(path, state, suffix=".v398-state.tmp")
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        return {"status": "V398_STATE_WRITE_FAILED", "written": False, "error_code": type(exc).__name__}
    return {"status": "V398_STATE_SAVED", "written": True}


def _kpi(result: dict[str, Any]) -> float | None:
    row = result.get("v382_kpis") if isinstance(result.get("v382_kpis"), dict) else {}
    value = _finite(row.get("score"))
    return _clamp(value) if value is not None else None


def _mode(result: dict[str, Any]) -> dict[str, Any]:
    row = result.get("v397_operating_mode")
    return deepcopy(row) if isinstance(row, dict) else v397.operating_mode(result)


def _owner(capability: dict[str, Any]) -> str:
    evidence = capability.get("evidence") if isinstance(capability.get("evidence"), dict) else {}
    return str(evidence.get("owner_controller") or "")


def _recipe(capability: dict[str, Any]) -> str:
    params = capability.get("parameters") if isinstance(capability.get("parameters"), dict) else {}
    return (str(capability.get("primitive") or "") + "|" + json.dumps(
        params, sort_keys=True, ensure_ascii=True, separators=(",", ":")
    ))[:360]


def _capability(primitive: str, suffix: str, params: dict[str, Any], evidence: dict[str, Any], *, now: datetime):
    v373 = v397.v391.v390.v373
    if primitive not in v373.CAPABILITY_PRIMITIVES:
        return None
    evidence = {**deepcopy(evidence), "owner_controller": CONTROLLER_VERSION, "reason": "v398_verified_candidate_tournament"}
    row = v373._capability(primitive, suffix, deepcopy(params), evidence, now=now)
    return row if v373.validate_capability(row, now=now) else None


def _alignment(capability: dict[str, Any], result: dict[str, Any]) -> float:
    plan = result.get("v390_goal_plan") if isinstance(result.get("v390_goal_plan"), dict) else {}
    primary = plan.get("primary_goal") if isinstance(plan.get("primary_goal"), dict) else {}
    goal = str(primary.get("goal_id") or "")
    expected = {
        "RECOVER_MARKET_FRESHNESS": "REQUEST_FRESHNESS_REFRESH",
        "EXPAND_VERIFIED_MARKET_COVERAGE": "PRIORITIZE_REGION",
        "RECOVER_SOURCE_HEALTH": "RETRY_DEGRADED_SOURCES",
        "IMPROVE_NEURAL_CONSENSUS": "PRIORITIZE_SAFE_LEARNING",
        "REVALIDATE_UNCERTAINTY": "INCREASE_OBSERVATION",
        "STABILIZE_POLICY_PORTFOLIO": "INCREASE_OBSERVATION",
    }.get(goal)
    if expected is None:
        return 0.5
    return 1.0 if capability.get("primitive") == expected else 0.25


def synthesize_candidates(result: dict[str, Any], state: dict[str, Any], *, now: datetime) -> list[dict[str, Any]]:
    mode = _mode(result)
    dims = mode.get("dimensions") if isinstance(mode.get("dimensions"), dict) else {}
    plan = result.get("v390_goal_plan") if isinstance(result.get("v390_goal_plan"), dict) else {}
    primary = plan.get("primary_goal") if isinstance(plan.get("primary_goal"), dict) else {}
    urgency = _clamp(float(_finite(primary.get("urgency")) or 0.0))
    found: dict[str, dict[str, Any]] = {}

    def add(cap, source: str, evidence_score: float, action: str | None = None):
        if not isinstance(cap, dict):
            return
        key = _recipe(cap)
        if key and key not in found:
            found[key] = {
                "recipe_key": key,
                "capability": cap,
                "source": source,
                "action_id": action,
                "evidence_score": round(_clamp(evidence_score), 6),
            }

    upstream = v397._candidate_from_result(result)
    if isinstance(upstream, dict):
        add(
            _capability(
                str(upstream.get("primitive") or ""), "V398_UPSTREAM",
                upstream.get("parameters") if isinstance(upstream.get("parameters"), dict) else {},
                {"source": "upstream_verified_candidate", "goal_id": str(primary.get("goal_id") or "")},
                now=now,
            ),
            "upstream_verified_candidate", max(0.50, urgency),
            str(plan.get("recommended_action") or "") or None,
        )

    freshness = _clamp(float(_finite(dims.get("market_freshness")) or 0.5))
    coverage = _clamp(float(_finite(dims.get("market_coverage")) or 0.5))
    source_health = _clamp(float(_finite(dims.get("source_health")) or 0.5))
    neural = _clamp(float(_finite(dims.get("neural_consensus")) or 0.5))
    uncertainty = _clamp(float(_finite(mode.get("uncertainty")) or 0.0))
    drift = _clamp(float(_finite(mode.get("drift")) or 0.0))

    if 1.0 - freshness >= 0.15:
        add(_capability(
            "REQUEST_FRESHNESS_REFRESH", "V398_FRESHNESS", {"max_runs": 1},
            {"source": "market_freshness_deficit", "deficit": round(1.0 - freshness, 6)}, now=now,
        ), "market_freshness_deficit", 1.0 - freshness, "REFRESH_MARKET_DATA")

    if 1.0 - source_health >= 0.15:
        add(_capability(
            "RETRY_DEGRADED_SOURCES", "V398_SOURCES", {"max_retry": 2, "backoff_seconds": 120},
            {"source": "source_health_deficit", "deficit": round(1.0 - source_health, 6)}, now=now,
        ), "source_health_deficit", 1.0 - source_health, "RECHECK_DEGRADED_SOURCES")

    market = result.get("market_adaptation_v381") if isinstance(result.get("market_adaptation_v381"), dict) else {}
    regions = [str(x) for x in list(market.get("low_coverage_regions") or []) if str(x) in {"KR", "JP", "US"}]
    if 1.0 - coverage >= 0.15 and regions:
        add(_capability(
            "PRIORITIZE_REGION", "V398_" + regions[0],
            {"region": regions[0], "boost": min(0.12, 0.05 + 0.07 * (1.0 - coverage))},
            {"source": "market_coverage_deficit", "deficit": round(1.0 - coverage, 6)}, now=now,
        ), "market_coverage_deficit", 1.0 - coverage, "EXPAND_MARKET_COVERAGE")

    stress = max(uncertainty, drift)
    if stress >= 0.25:
        add(_capability(
            "INCREASE_OBSERVATION", "V398_REVALIDATE", {"scope": "market_health", "factor": 1.25},
            {"source": "uncertainty_drift", "stress": round(stress, 6)}, now=now,
        ), "uncertainty_drift", stress, "REVALIDATE_UNCERTAINTY")

    recommended = str(plan.get("recommended_action") or "")
    safe = set(v397.v391.v390.v373.v372.SAFE_LEARNING_ACTIONS)
    if 1.0 - neural >= 0.15 and recommended in safe:
        add(_capability(
            "PRIORITIZE_SAFE_LEARNING", "V398_LEARNING",
            {"action_id": recommended, "boost": min(0.10, 0.04 + 0.06 * (1.0 - neural))},
            {"source": "neural_consensus_deficit", "deficit": round(1.0 - neural, 6)}, now=now,
        ), "neural_consensus_deficit", 1.0 - neural, recommended)

    return sorted(found.values(), key=lambda row: (-row["evidence_score"], row["recipe_key"]))[:MAX_CANDIDATES]


def tournament(candidates: list[dict[str, Any]], result: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    memory = state.get("candidate_memory") if isinstance(state.get("candidate_memory"), dict) else {}
    cycle = int(state.get("cycle") or 0) + 1
    budget = _clamp(float(_finite(_mode(result).get("learning_budget")) or 0.0), 0.0, 0.25)
    ranked = []
    for item in candidates:
        row = deepcopy(item)
        mem = memory.get(row["recipe_key"]) if isinstance(memory.get(row["recipe_key"]), dict) else _memory_row()
        obs = int(mem.get("observations") or 0)
        success = int(mem.get("successes") or 0)
        fail = int(mem.get("failures") or 0)
        learned = _clamp((float(_finite(mem.get("reward_ewma")) or 0.0) + 1.0) / 2.0)
        reliability = (success + 1.0) / (success + fail + 2.0)
        explore = min(0.10, budget * 0.40 / math.sqrt(obs + 1.0))
        quarantined = int(mem.get("quarantine_until_cycle") or 0) >= cycle
        score = 0.42 * row["evidence_score"] + 0.23 * learned + 0.15 * reliability + 0.15 * _alignment(row["capability"], result) + explore
        row.update({
            "observations": obs,
            "successes": success,
            "failures": fail,
            "quarantined": quarantined,
            "tournament_score": 0.0 if quarantined else round(_clamp(score), 6),
        })
        ranked.append(row)
    ranked.sort(key=lambda row: (row["quarantined"], -row["tournament_score"], row["failures"], row["observations"], row["recipe_key"]))
    selected = next((row for row in ranked if not row["quarantined"] and row["tournament_score"] >= MIN_SCORE), None)
    return {
        "candidates": ranked,
        "selected_recipe_key": selected["recipe_key"] if selected else None,
        "selected_capability": deepcopy(selected["capability"]) if selected else None,
        "selected_score": selected["tournament_score"] if selected else None,
        "candidate_count": len(ranked),
        "learning_budget": round(budget, 6),
        "single_canary_only": True,
        "deterministic": True,
        "market_direction_inferred": False,
    }


def _load_caps(path: Path, *, now: datetime):
    return v397.v391.v390.v373.load_capabilities(path=path, now=now)


def evaluate_active(state: dict[str, Any], result: dict[str, Any], ids: set[str]) -> dict[str, Any]:
    active = state.get("active")
    if not isinstance(active, dict):
        return {"status": "NO_ACTIVE_V398_CAPABILITY", "rollback": False, "release": False, "kpi_delta": None}
    if active["id"] not in ids:
        return {"status": "ACTIVE_CAPABILITY_EXPIRED_OR_ABSENT", "rollback": False, "release": True, "kpi_delta": None}
    gate = result.get("v397_autonomous_gate") if isinstance(result.get("v397_autonomous_gate"), dict) else {}
    if gate.get("allow_execution") is not True:
        return {"status": "UPSTREAM_HARD_HOLD", "rollback": True, "release": False, "kpi_delta": None}
    current = _kpi(result)
    baseline = _finite(active.get("baseline_kpi"))
    if current is None or baseline is None or int(state.get("cycle") or 0) + 1 <= int(active.get("activated_cycle") or 0):
        return {"status": "CANARY_OBSERVE", "rollback": False, "release": False, "kpi_delta": None}
    delta = current - baseline
    if delta <= -ROLLBACK_DROP:
        return {"status": "MATERIAL_KPI_REGRESSION", "rollback": True, "release": False, "kpi_delta": round(delta, 6)}
    if delta >= VERIFIED_GAIN:
        return {"status": "VERIFIED_POSITIVE_CANARY", "rollback": False, "release": False, "kpi_delta": round(delta, 6)}
    return {"status": "CANARY_OBSERVE", "rollback": False, "release": False, "kpi_delta": round(delta, 6)}


def _rollback(active: dict[str, Any], *, path: Path, now: datetime) -> dict[str, Any]:
    loaded = _load_caps(path, now=now)
    if loaded.get("corruption_hold") is True:
        return {"status": "V398_CAPABILITY_CORRUPTION_HOLD", "written": False, "rolled_back": False}
    rows = list(loaded.get("capabilities") or [])
    target = next((row for row in rows if str(row.get("id") or "") == active["id"]), None)
    if target is None:
        return {"status": "V398_CAPABILITY_ALREADY_ABSENT", "written": False, "rolled_back": True}
    if _owner(target) != CONTROLLER_VERSION:
        return {"status": "V398_CAPABILITY_OWNERSHIP_HOLD", "written": False, "rolled_back": False}
    kept = [row for row in rows if str(row.get("id") or "") != active["id"]]
    write = v397.v391.v390.v373.save_capabilities(kept, path=path, corruption_hold=False, now=now)
    return {**write, "rolled_back": write.get("written") is True, "capability_id": active["id"]}


def _persist(capability: dict[str, Any], *, path: Path, now: datetime):
    v373 = v397.v391.v390.v373
    if not v373.validate_capability(capability, now=now) or _owner(capability) != CONTROLLER_VERSION:
        return {"status": "V398_INVALID_SELECTED_CAPABILITY", "written": False}, None
    loaded = _load_caps(path, now=now)
    if loaded.get("corruption_hold") is True:
        return {"status": "V398_CAPABILITY_CORRUPTION_HOLD", "written": False}, None
    rows = list(loaded.get("capabilities") or [])
    owner = next((_owner(row) for row in rows if _owner(row) in {"v397", "v398", "v400"}), None)
    if owner:
        return {"status": "V398_EXPERIMENTAL_CAPABILITY_CONFLICT", "written": False, "owner": owner}, None
    write = v373.save_capabilities(v373.merge_capabilities(rows, [capability], now=now), path=path, corruption_hold=False, now=now)
    return write, deepcopy(capability) if write.get("written") is True else None


def _next_state(state: dict[str, Any], *, evaluation: dict[str, Any], new_capability, selected_recipe, rolled_back: bool, current_kpi, mode, result, now):
    cycle = int(state.get("cycle") or 0) + 1
    memory = deepcopy(state.get("candidate_memory") or {})
    old_active = state.get("active") if isinstance(state.get("active"), dict) else None
    if old_active:
        key = old_active["recipe_key"]
        row = deepcopy(memory.get(key)) if isinstance(memory.get(key), dict) else _memory_row()
        delta = _finite(evaluation.get("kpi_delta"))
        if delta is not None and cycle > int(row.get("last_scored_cycle") or 0):
            reward = max(-1.0, min(1.0, delta / 0.10))
            row["reward_ewma"] = round(0.35 * reward + 0.65 * float(row.get("reward_ewma") or 0.0), 6)
            row["observations"] += 1
            row["last_scored_cycle"] = cycle
            if evaluation.get("status") == "VERIFIED_POSITIVE_CANARY":
                row["successes"] += 1
            if evaluation.get("rollback") is True:
                row["failures"] += 1
                row["quarantine_until_cycle"] = cycle + QUARANTINE_CYCLES
            memory[key] = row
    if selected_recipe:
        row = deepcopy(memory.get(selected_recipe)) if isinstance(memory.get(selected_recipe), dict) else _memory_row()
        row["last_selected_cycle"] = cycle
        memory[selected_recipe] = row
    memory = dict(sorted(memory.items(), key=lambda pair: (-pair[1]["last_selected_cycle"], -pair[1]["observations"], pair[0]))[:MAX_MEMORY])

    active = old_active
    cooldown = int(state.get("cooldown_until_cycle") or 0)
    if rolled_back or evaluation.get("release") is True:
        active = None
        cooldown = cycle + COOLDOWN_CYCLES
    elif new_capability is not None and selected_recipe:
        plan = result.get("v390_goal_plan") if isinstance(result.get("v390_goal_plan"), dict) else {}
        primary = plan.get("primary_goal") if isinstance(plan.get("primary_goal"), dict) else {}
        active = {
            "id": str(new_capability["id"]),
            "recipe_key": selected_recipe,
            "primitive": str(new_capability["primitive"]),
            "baseline_kpi": round(current_kpi if current_kpi is not None else 0.5, 6),
            "activated_cycle": cycle,
            "goal_id": str(primary.get("goal_id") or "STEADY_VERIFIED_OPTIMIZATION"),
            "mode": str(mode.get("mode") or "UNKNOWN"),
        }
    history = list(state.get("history") or [])
    history.append({
        "observed_at": now.isoformat(timespec="seconds"),
        "cycle": cycle,
        "mode": mode.get("mode"),
        "kpi_score": round(current_kpi, 6) if current_kpi is not None else None,
        "active_capability": active.get("id") if isinstance(active, dict) else None,
        "active_evaluation": evaluation.get("status"),
        "selected_recipe": selected_recipe,
        "rolled_back": bool(rolled_back),
        "upstream_status": result.get("v397_status"),
    })
    return {
        "schema_version": 1,
        "controller_version": CONTROLLER_VERSION,
        "cycle": cycle,
        "active": active,
        "cooldown_until_cycle": cooldown,
        "candidate_memory": memory,
        "history": history[-MAX_HISTORY:],
    }


def run_cycle(*, domain="tablet_gpt", execute=False, apply_capabilities=False, train_meta=False, apply_skills=False,
              root=ROOT, now=None, state_path=None, persist_outputs=True, **upstream_paths):
    moment = (now or _now()).astimezone(timezone.utc)
    mutating = bool(execute or apply_capabilities or train_meta or apply_skills)
    state_file = state_path or (root / STATE_PATH.name)
    cap_raw = upstream_paths.get("capability_path")
    cap_path = Path(cap_raw) if cap_raw is not None else (root / v397.v391.v390.v373.CAPABILITY_PATH.name)

    fd = None
    if mutating:
        fd, _ = v397.v391.v390.v388.v387.v386.v385._acquire_lock(root / LOCK_PATH.name)
        if fd is None:
            return {"controller_version": CONTROLLER_VERSION, "v398_status": "V398_CONCURRENT_AUTONOMY_HOLD",
                    "execution": {"status": "V398_CONCURRENT_AUTONOMY_HOLD", "executed": False, "git_write": False, "source_code_modified": False},
                    "safety": SAFETY}
    try:
        preview = v397.run_cycle(
            domain=domain, execute=False, apply_capabilities=False, train_meta=False, apply_skills=False,
            root=root, now=moment, persist_outputs=False, **upstream_paths
        )
        loaded = load_state(state_file)
        state = deepcopy(loaded["state"])
        cap_loaded = _load_caps(cap_path, now=moment)
        cap_corrupt = cap_loaded.get("corruption_hold") is True
        cap_rows = list(cap_loaded.get("capabilities") or []) if not cap_corrupt else []
        ids = {str(row.get("id") or "") for row in cap_rows if isinstance(row, dict)}
        v397_present = any(_owner(row) == "v397" for row in cap_rows if isinstance(row, dict))
        evaluation = evaluate_active(state, preview, ids)
        mode = _mode(preview)
        contest = tournament(synthesize_candidates(preview, state, now=moment), preview, state)

        gate = preview.get("v397_autonomous_gate") if isinstance(preview.get("v397_autonomous_gate"), dict) else {}
        allow = gate.get("allow_execution") is True and not loaded.get("corruption_hold") and not cap_corrupt
        status = "V398_VERIFIED_ALLOW" if allow else (
            "V398_STATE_CORRUPTION_HOLD" if loaded.get("corruption_hold")
            else "V398_CAPABILITY_CORRUPTION_HOLD" if cap_corrupt
            else "V398_UPSTREAM_HOLD"
        )

        rollback_write = {"status": "ROLLBACK_NOT_REQUESTED", "written": False, "rolled_back": False}
        rolled_back = False
        if mutating and apply_capabilities and evaluation.get("rollback") is True and isinstance(state.get("active"), dict) and allow:
            rollback_write = _rollback(state["active"], path=cap_path, now=moment)
            rolled_back = rollback_write.get("rolled_back") is True
            if not rolled_back:
                allow = False
                status = "V398_CAPABILITY_ROLLBACK_HOLD"

        base = preview
        if mutating and allow:
            core_apply = bool(apply_capabilities and v397_present and not isinstance(state.get("active"), dict))
            base = v397.run_cycle(
                domain=domain, execute=execute, apply_capabilities=core_apply,
                train_meta=train_meta, apply_skills=apply_skills,
                root=root, now=moment, persist_outputs=False, **upstream_paths
            )
            if str(base.get("v397_status") or "") in getattr(v397, "_HOLD_STATUSES", set()):
                allow = False
                status = "V398_UPSTREAM_HOLD"

        write = {"status": "V398_CAPABILITY_NOT_REQUESTED", "written": False}
        new_cap = None
        selected_recipe = None
        selected = contest.get("selected_capability")
        no_active = not isinstance(state.get("active"), dict) or evaluation.get("release") is True
        if (mutating and apply_capabilities and allow and not rolled_back and no_active and not v397_present
                and int(state.get("cycle") or 0) >= int(state.get("cooldown_until_cycle") or 0)
                and isinstance(selected, dict)):
            write, new_cap = _persist(selected, path=cap_path, now=moment)
            if new_cap is not None:
                selected_recipe = str(contest.get("selected_recipe_key") or "") or None
            elif write.get("status") not in {"V398_EXPERIMENTAL_CAPABILITY_CONFLICT"}:
                allow = False
                status = "V398_CAPABILITY_WRITE_HOLD"

        current_kpi = _kpi(base)
        result = deepcopy(base)
        result.update({
            "core_controller_version": str(base.get("controller_version") or CORE_CONTROLLER_VERSION),
            "controller_version": CONTROLLER_VERSION,
            "v398_status": status if mutating else "PLAN_ONLY",
            "v398_operating_mode": mode,
            "v398_candidate_tournament": contest,
            "v398_active_evaluation": evaluation,
            "v398_rollback": {"write": rollback_write, "owned_capability_only": True},
            "v398_self_extension": {
                "write": write,
                "new_capability": new_cap,
                "selected_recipe_key": selected_recipe,
                "v397_experiment_present": v397_present,
                "canonical_allowlist_only": True,
                "single_canary_only": True,
                "next_cycle_only": True,
                "source_code_generated": False,
                "git_write": False,
            },
            "v398_autonomous_gate": {
                "status": status, "allow_execution": allow,
                "v397_gate_required": True, "hard_blocker_override": False,
            },
            "evolution_contract_v398": {
                "core": "v397_plus_v391_self_diagnosis_plus_v390_verified_meta_critic",
                "loop": "observe_diagnose_synthesize_tournament_canary_measure_learn_quarantine_or_reuse",
                "candidate_sources": "operational_deficits_plus_upstream_verified_candidate",
                "candidate_learning": "local_verified_kpi_reward_memory_only",
                "runtime_self_extension": "one_v398_owned_canonical_v373_capability_next_cycle_only",
                "source_level_extension": "v397_verified_canary_to_protected_pr_candidate_only",
                "market_adaptation": "freshness_coverage_source_health_neural_consensus_drift_uncertainty_resource_only",
                "automatic_source_generation": False,
                "automatic_source_rewrite": False,
                "direct_git_or_main_write": False,
                "v397_v391_v390_and_prior_gate_bypass": False,
                "market_direction_inferred": False,
            },
            "safety": SAFETY,
        })
        if mutating and not allow:
            result["execution"] = {"status": status, "executed": False, "git_write": False, "source_code_modified": False, "proposals_executed": False}

        state_write = {"status": "V398_STATE_WRITE_NOT_REQUESTED", "written": False}
        if mutating:
            nxt = _next_state(
                state, evaluation=evaluation, new_capability=new_cap, selected_recipe=selected_recipe,
                rolled_back=rolled_back, current_kpi=current_kpi, mode=mode, result=base, now=moment
            )
            state_write = save_state(nxt, state_file, corruption_hold=bool(loaded.get("corruption_hold")))
            if not state_write.get("written"):
                if new_cap is not None:
                    _rollback({
                        "id": new_cap["id"], "recipe_key": selected_recipe or _recipe(new_cap),
                        "primitive": new_cap["primitive"], "baseline_kpi": current_kpi or 0.5,
                        "activated_cycle": int(state.get("cycle") or 0) + 1,
                        "goal_id": "STATE_COMMIT_ROLLBACK", "mode": str(mode.get("mode") or "UNKNOWN"),
                    }, path=cap_path, now=moment)
                result["v398_status"] = "V398_STATE_COMMIT_HOLD"
                result["v398_autonomous_gate"] = {**result["v398_autonomous_gate"], "status": "V398_STATE_COMMIT_HOLD", "allow_execution": False}
                result["execution"] = {"status": "V398_STATE_COMMIT_HOLD", "executed": False, "git_write": False, "source_code_modified": False, "proposals_executed": False}
        result["v398_state_write"] = state_write

        if persist_outputs:
            try:
                atomic_write_json(root / TOURNAMENT_PATH.name, {
                    "schema_version": 1,
                    "controller_version": CONTROLLER_VERSION,
                    "generated_at": moment.isoformat(timespec="seconds"),
                    "operating_mode": mode,
                    "tournament": contest,
                    "source_feature_runtime_auto_execution": False,
                    "protected_pr_ci_required": True,
                }, suffix=".v398-tournament.tmp")
                atomic_write_json(root / REPORT_PATH.name, result, suffix=".v398-report.tmp")
                result["v398_runtime_output"] = {"status": "SAVED"}
            except (OSError, UnicodeError, ValueError, TypeError) as exc:
                result["v398_runtime_output"] = {"status": "WRITE_FAILED", "error_code": type(exc).__name__}
        return result
    finally:
        if fd is not None:
            v397.v391.v390.v388.v387.v386.v385._release_lock(fd)


def self_test() -> None:
    assert _valid_state(_default_state())
    assert SAFETY["multi_candidate_self_extension_enabled"] is True
    assert SAFETY["candidate_tournament_verified_history_learning"] is True
    assert SAFETY["single_canary_capability_only"] is True
    assert SAFETY["source_code_auto_generation"] is False
    assert SAFETY["git_write"] is False
    assert SAFETY["market_direction_inferred"] is False
    print("Tablet verified multi-candidate self-evolution supervisor v398: PASS")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--domain", choices=sorted(v397.v391.v390.v388.v387.v386.DOMAINS), default="tablet_gpt")
    p.add_argument("--execute-safe-learning", action="store_true")
    p.add_argument("--apply-capabilities", action="store_true")
    p.add_argument("--train-meta", action="store_true")
    p.add_argument("--apply-skills", action="store_true")
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()
    if args.self_test:
        self_test()
        return 0
    result = run_cycle(
        domain=args.domain, execute=args.execute_safe_learning,
        apply_capabilities=args.apply_capabilities, train_meta=args.train_meta,
        apply_skills=args.apply_skills,
    )
    if not args.quiet:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 2 if result.get("v398_status") in _HOLD_STATUSES else 0


if __name__ == "__main__":
    raise SystemExit(main())
