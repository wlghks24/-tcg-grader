#!/usr/bin/env python3
"""Verified adaptive policy evolution for Tablet GPT / TCG Grader.

V381 layers persistent, verified-outcome policy adaptation on V380 without
weakening any V376-V380 safety, evidence, information-exchange, quality,
serialization, or protected-main boundary.

The controller:
- learns only from V373 verified outcome records;
- keeps a bounded summary-only policy memory (no raw peer lessons or card facts);
- compares a champion and challenger policy before changing the preferred safe
  learning action;
- composes at most three next-cycle declarative capabilities using only the
  canonical V373 allowlist;
- adapts to market freshness / coverage / source-health regimes without
  predicting market direction;
- turns unresolved source-level gaps into non-executable PR/CI proposals only.

Source code is never generated or rewritten by the runtime controller, arbitrary
commands are never executed, and Git/main are never written by the controller.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import stat
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import tablet_autonomous_evolution_v373 as v373
import tablet_autonomous_evolution_v380 as v380
from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
CONTROLLER_VERSION = "v381"
CORE_CONTROLLER_VERSION = "v380"
REPORT_PATH = ROOT / "tablet_autonomy_v381_report.json"
POLICY_STATE_PATH = ROOT / "tablet_autonomy_policy_v381.json"
PROPOSAL_PATH = ROOT / "tablet_autonomy_source_feature_proposals_v381.json"
LOCK_PATH = ROOT / ".tablet_autonomy_execution_v381.lock"

POLICY_SCHEMA_VERSION = 1
MAX_POLICY_BYTES = 1_000_000
MAX_POLICY_HISTORY = 32
MAX_RECIPE_CAPABILITIES = 3
MIN_POLICY_SAMPLES = 8
PROMOTION_MARGIN = 0.05

_HOLD_STATUSES = set(getattr(v380, "_HOLD_STATUSES", set())) | {
    "V381_POLICY_MEMORY_HOLD",
    "V381_LOCK_UNAVAILABLE",
    "V381_CONCURRENT_AUTONOMY_HOLD",
}

SAFETY = dict(v380.SAFETY)
SAFETY.update({
    "verified_outcome_policy_learning_only": True,
    "policy_memory_summary_only": True,
    "policy_memory_corruption_blocks_mutation": True,
    "champion_challenger_sample_gate_required": True,
    "challenger_promotion_margin_bounded": True,
    "existing_meta_neural_model_reused": True,
    "adaptive_policy_neural_advisory_only": True,
    "market_regime_adaptation_operational_only": True,
    "market_direction_inferred": False,
    "information_exchange_digest_memory_summary_only": True,
    "raw_peer_lessons_persisted": False,
    "declarative_capability_recipe_allowlisted_only": True,
    "declarative_capability_recipe_max_per_cycle": MAX_RECIPE_CAPABILITIES,
    "capability_recipe_applies_next_cycle_only_after_bounded_core": True,
    "source_level_gap_proposal_only": True,
    "source_level_new_function_pr_ci_required": True,
    "source_code_auto_generation": False,
    "source_code_auto_rewrite": False,
    "arbitrary_command_execution": False,
    "git_write": False,
    "direct_main_write": False,
    "verification_bypass": False,
    "trust_or_fact_auto_promotion": False,
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
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _default_policy_state() -> dict[str, Any]:
    return {
        "schema_version": POLICY_SCHEMA_VERSION,
        "controller_version": CONTROLLER_VERSION,
        "champion_action": None,
        "promotion_count": 0,
        "history": [],
    }


def _validate_policy_state(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if value.get("schema_version") != POLICY_SCHEMA_VERSION:
        return False
    if value.get("controller_version") != CONTROLLER_VERSION:
        return False
    champion = value.get("champion_action")
    if champion is not None and champion not in v373.META_ACTIONS:
        return False
    promotions = value.get("promotion_count")
    if isinstance(promotions, bool) or not isinstance(promotions, int) or promotions < 0:
        return False
    history = value.get("history")
    if not isinstance(history, list) or len(history) > MAX_POLICY_HISTORY:
        return False
    allowed = {
        "observed_at", "market_regime", "exchange_status", "exchange_digest",
        "champion_action", "decision_status",
    }
    for row in history:
        if not isinstance(row, dict) or set(row) != allowed:
            return False
        if row.get("champion_action") is not None and row.get("champion_action") not in v373.META_ACTIONS:
            return False
        digest = row.get("exchange_digest")
        if digest is not None and (not isinstance(digest, str) or len(digest) > 128):
            return False
        for key in ("observed_at", "market_regime", "exchange_status", "decision_status"):
            if not isinstance(row.get(key), str) or len(row[key]) > 160:
                return False
    return True


def load_policy_state(path: Path = POLICY_STATE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"status": "fresh", "corruption_hold": False, "state": _default_policy_state()}
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError("UNSAFE_POLICY_STATE_PATH")
        value = json.loads(safe_read_text(path, max_bytes=MAX_POLICY_BYTES))
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return {
            "status": "corrupt",
            "corruption_hold": True,
            "state": _default_policy_state(),
            "error_code": type(exc).__name__,
        }
    if not _validate_policy_state(value):
        return {
            "status": "corrupt",
            "corruption_hold": True,
            "state": _default_policy_state(),
            "error_code": "POLICY_STATE_SCHEMA_INVALID",
        }
    return {"status": "loaded", "corruption_hold": False, "state": value}


def verified_outcome_stats(path: Path) -> dict[str, dict[str, Any]]:
    rows = v373.load_verified_outcomes(path=path)
    buckets: dict[str, list[float]] = {action: [] for action in v373.META_ACTIONS}
    for row in rows:
        action = str(row.get("action_id") or "")
        reward = _finite(row.get("reward"))
        if action in buckets and reward is not None:
            buckets[action].append(_clamp(reward, -1.0, 1.0))
    result: dict[str, dict[str, Any]] = {}
    for action in v373.META_ACTIONS:
        values = buckets[action]
        result[action] = {
            "verified_samples": len(values),
            "reward_mean": round(sum(values) / len(values), 6) if values else None,
            "reward_min": round(min(values), 6) if values else None,
            "reward_max": round(max(values), 6) if values else None,
        }
    return result


def market_operational_state(base: dict[str, Any]) -> dict[str, Any]:
    plan = base.get("plan") if isinstance(base.get("plan"), dict) else {}
    regime = v373.market_regime(plan)
    dimensions = v380.dimension_values(base)
    stress = 1.0 - (
        float(dimensions.get("market_freshness", 0.0))
        + float(dimensions.get("market_coverage", 0.0))
        + float(dimensions.get("source_health", 0.0))
    ) / 3.0
    mapping = {
        "FRESHNESS_HOLD": "RECOVER_FRESHNESS",
        "COVERAGE_AND_SOURCE_STRESS": "RECOVER_COVERAGE_AND_SOURCES",
        "UNDERCOVERED": "EXPAND_VERIFIED_COVERAGE",
        "SOURCE_DEGRADED": "RECOVER_SOURCE_HEALTH",
        "HEALTHY": "STEADY_VERIFIED_EVOLUTION",
    }
    return {
        "regime": str(regime.get("regime") or "UNKNOWN"),
        "mode": mapping.get(str(regime.get("regime") or ""), "OBSERVE_UNCERTAIN_REGIME"),
        "low_coverage_regions": list(regime.get("low_coverage_regions") or [])[:3],
        "degraded_source_ratio": regime.get("degraded_source_ratio"),
        "stress_score": round(_clamp(stress), 6),
        "market_direction_inferred": False,
    }


def information_exchange_memory(base: dict[str, Any]) -> dict[str, Any]:
    exchange = (
        base.get("information_exchange_manager")
        if isinstance(base.get("information_exchange_manager"), dict)
        else {}
    )
    counts = exchange.get("counts") if isinstance(exchange.get("counts"), dict) else {}
    status = str(exchange.get("status") or "EXCHANGE_UNKNOWN")
    priority = {
        "EXCHANGE_INTEGRITY_HOLD": 100,
        "EXCHANGE_CONFLICT_HOLD": 100,
        "EXCHANGE_REPRODUCTION_REQUIRED": 80,
        "EXCHANGE_PARTIAL": 65,
        "EXCHANGE_UNAVAILABLE": 55,
        "EXCHANGE_CORROBORATED": 35,
        "EXCHANGE_EMPTY_OR_NOT_APPLICABLE": 30,
    }.get(status, 60)
    digest = str(exchange.get("input_digest") or "")
    return {
        "status": status,
        "management_action": str(exchange.get("selected_management_action") or "LOCAL_VERIFIED_ONLY")[:160],
        "priority": priority,
        "input_digest": digest[:128] or None,
        "counts": {
            key: int(counts.get(key) or 0)
            for key in ("corroborated", "single-system-only", "conflicting-fix", "not-applicable")
        },
        "signal_score": _finite(exchange.get("signal_score")),
        "raw_peer_lessons_persisted": False,
        "summary_only": True,
    }


def _regime_affinity(action: str, regime: str) -> float:
    if regime == "FRESHNESS_HOLD":
        return 1.0 if action == "REFRESH_MARKET_DATA" else 0.35
    if regime == "UNDERCOVERED":
        return 1.0 if action == "EXPAND_MARKET_COVERAGE" else 0.40
    if regime == "SOURCE_DEGRADED":
        return 1.0 if action == "RECHECK_DEGRADED_SOURCES" else 0.40
    if regime == "COVERAGE_AND_SOURCE_STRESS":
        return 0.95 if action in {"EXPAND_MARKET_COVERAGE", "RECHECK_DEGRADED_SOURCES"} else 0.35
    if regime == "HEALTHY":
        return 0.70 if action in {"TRAIN_QUERY_STRATEGY", "TRAIN_JOB_STRATEGY", "TRAIN_REPAIR_PRIORITY"} else 0.50
    return 0.45


def policy_candidates(
    base: dict[str, Any],
    stats: dict[str, dict[str, Any]],
    market: dict[str, Any],
) -> list[dict[str, Any]]:
    plan = base.get("plan") if isinstance(base.get("plan"), dict) else {}
    meta_scores = plan.get("meta_scores") if isinstance(plan.get("meta_scores"), dict) else {}
    rows = []
    for action in v373.META_ACTIONS:
        neural_raw = _finite(meta_scores.get(action))
        if neural_raw is None:
            neural_raw = 0.0
        neural = _clamp((neural_raw + 1.0) / 2.0)
        stat_row = stats.get(action) if isinstance(stats.get(action), dict) else {}
        count = int(stat_row.get("verified_samples") or 0)
        reward_mean = _finite(stat_row.get("reward_mean"))
        reward = _clamp(((reward_mean if reward_mean is not None else 0.0) + 1.0) / 2.0)
        affinity = _regime_affinity(action, str(market.get("regime") or "UNKNOWN"))
        score = 0.50 * neural + 0.35 * reward + 0.15 * affinity
        rows.append({
            "action_id": action,
            "score": round(_clamp(score), 6),
            "neural_score": round(neural, 6),
            "verified_reward_score": round(reward, 6),
            "regime_affinity": round(affinity, 6),
            "verified_samples": count,
            "reward_mean": round(reward_mean, 6) if reward_mean is not None else None,
            "promotion_eligible": count >= MIN_POLICY_SAMPLES,
        })
    rows.sort(key=lambda row: (-row["score"], -row["verified_samples"], row["action_id"]))
    return rows


def select_champion(
    state: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    by_action = {row["action_id"]: row for row in candidates}
    previous = state.get("champion_action")
    champion = by_action.get(previous) if previous in by_action else None

    eligible = [row for row in candidates if row["promotion_eligible"]]
    if champion is None:
        if eligible:
            champion = eligible[0]
            status = "BOOTSTRAP_VERIFIED_CHAMPION"
        else:
            champion = candidates[0] if candidates else None
            status = "BOOTSTRAP_ADVISORY_ONLY"
        return {
            "status": status,
            "previous_champion": previous,
            "champion_action": champion["action_id"] if champion else None,
            "challenger_action": candidates[1]["action_id"] if len(candidates) > 1 else None,
            "promoted": bool(champion and champion["promotion_eligible"]),
            "promotion_margin": PROMOTION_MARGIN,
            "minimum_verified_samples": MIN_POLICY_SAMPLES,
            "champion": champion,
        }

    challengers = [row for row in candidates if row["action_id"] != champion["action_id"]]
    challenger = challengers[0] if challengers else None
    promoted = False
    status = "KEEP_CHAMPION"
    if challenger and challenger["promotion_eligible"]:
        champion_reward = _finite(champion.get("reward_mean"))
        challenger_reward = _finite(challenger.get("reward_mean"))
        reward_safe = (
            challenger_reward is not None
            and (champion_reward is None or challenger_reward >= champion_reward - 0.10)
        )
        if challenger["score"] >= champion["score"] + PROMOTION_MARGIN and reward_safe:
            champion = challenger
            promoted = True
            status = "PROMOTED_VERIFIED_CHALLENGER"

    return {
        "status": status,
        "previous_champion": previous,
        "champion_action": champion["action_id"],
        "challenger_action": challenger["action_id"] if challenger else None,
        "promoted": promoted,
        "promotion_margin": PROMOTION_MARGIN,
        "minimum_verified_samples": MIN_POLICY_SAMPLES,
        "champion": champion,
        "challenger": challenger,
    }


def _capability(
    primitive: str,
    suffix: str,
    parameters: dict[str, Any],
    evidence: dict[str, Any],
    *,
    now: datetime,
) -> dict[str, Any]:
    normalized = "".join(ch for ch in suffix.upper() if ch.isalnum() or ch in "_-")[:64]
    return {
        "id": f"{primitive}:{normalized or 'V381'}",
        "primitive": primitive,
        "parameters": parameters,
        "evidence": evidence,
        "created_at": now.isoformat(timespec="seconds"),
        "expires_at": (now + timedelta(hours=24)).isoformat(timespec="seconds"),
        "auto_generated": True,
        "auto_active": True,
        "source_code_change": False,
        "arbitrary_command": False,
        "scope": "operational_policy",
    }


def capability_recipe(
    base: dict[str, Any],
    market: dict[str, Any],
    exchange: dict[str, Any],
    selection: dict[str, Any],
    *,
    now: datetime,
) -> dict[str, Any]:
    ranked: list[tuple[int, dict[str, Any]]] = []
    regime = str(market.get("regime") or "UNKNOWN")
    low_regions = list(market.get("low_coverage_regions") or [])
    degraded = _finite(market.get("degraded_source_ratio"))

    if regime == "FRESHNESS_HOLD":
        ranked.append((100, _capability(
            "REQUEST_FRESHNESS_REFRESH", "MARKET",
            {"max_runs": 1},
            {"reason": "v381_market_freshness_hold", "regime": regime},
            now=now,
        )))
    for region in low_regions[:2]:
        ranked.append((90, _capability(
            "PRIORITIZE_REGION", str(region),
            {"region": str(region), "boost": 0.12},
            {"reason": "v381_verified_coverage_gap", "regime": regime},
            now=now,
        )))
    if degraded is not None and degraded > 0.35:
        ranked.append((85, _capability(
            "RETRY_DEGRADED_SOURCES", "MARKET",
            {"max_retry": 2, "backoff_seconds": 120},
            {"reason": "v381_degraded_source_ratio", "ratio": degraded},
            now=now,
        )))

    if exchange.get("status") in {
        "EXCHANGE_REPRODUCTION_REQUIRED", "EXCHANGE_PARTIAL",
        "EXCHANGE_UNAVAILABLE", "EXCHANGE_CONFLICT_HOLD", "EXCHANGE_INTEGRITY_HOLD",
    }:
        ranked.append((80, _capability(
            "INCREASE_OBSERVATION", "SYNC_HEALTH",
            {"scope": "sync_health", "factor": 1.25},
            {"reason": "v381_information_exchange_attention", "status": exchange.get("status")},
            now=now,
        )))

    champion = selection.get("champion")
    if isinstance(champion, dict) and champion.get("promotion_eligible") is True:
        ranked.append((70, _capability(
            "PRIORITIZE_SAFE_LEARNING", str(champion.get("action_id") or "POLICY"),
            {"action_id": champion["action_id"], "boost": 0.10},
            {
                "reason": "v381_verified_champion_policy",
                "verified_samples": champion.get("verified_samples"),
                "score": champion.get("score"),
            },
            now=now,
        )))

    valid = []
    seen = set()
    for priority, row in sorted(ranked, key=lambda item: (-item[0], item[1]["id"])):
        if row["id"] in seen:
            continue
        if not v373.validate_capability(row, now=now):
            continue
        seen.add(row["id"])
        valid.append({"priority": priority, "capability": row})
        if len(valid) >= MAX_RECIPE_CAPABILITIES:
            break

    return {
        "status": "ALLOWLISTED_RECIPE_READY" if valid else "NO_ADDITIONAL_RECIPE",
        "max_capabilities": MAX_RECIPE_CAPABILITIES,
        "capabilities": [row["capability"] for row in valid],
        "canonical_registry": "tablet_autonomous_evolution_v373.CAPABILITY_PRIMITIVES",
        "canonical_validator": "tablet_autonomous_evolution_v373.validate_capability",
        "source_code_change": False,
        "arbitrary_command": False,
        "market_direction_inferred": False,
    }


def source_gap_proposals(
    state: dict[str, Any],
    market: dict[str, Any],
    exchange: dict[str, Any],
    recipe: dict[str, Any],
) -> list[dict[str, Any]]:
    history = state.get("history") if isinstance(state.get("history"), list) else []
    recent_regime = str(market.get("regime") or "UNKNOWN")
    repeated_regime = sum(
        1 for row in history[-6:]
        if isinstance(row, dict) and row.get("market_regime") == recent_regime
    )
    recent_exchange = str(exchange.get("status") or "EXCHANGE_UNKNOWN")
    repeated_exchange = sum(
        1 for row in history[-6:]
        if isinstance(row, dict) and row.get("exchange_status") == recent_exchange
    )
    proposals = []

    if recent_regime not in {"HEALTHY", "UNKNOWN"} and repeated_regime >= 3 and not recipe.get("capabilities"):
        proposals.append({
            "id": f"V381_MARKET_GAP:{recent_regime}",
            "kind": "source_feature",
            "reason": "persistent_market_operational_gap_without_allowlisted_recipe",
            "evidence": {"regime": recent_regime, "recent_occurrences": repeated_regime},
            "auto_apply": False,
            "pr_required": True,
            "required_validation": ["targeted_tests", "full_regression", "output_validation"],
        })

    if recent_exchange in {"EXCHANGE_CONFLICT_HOLD", "EXCHANGE_INTEGRITY_HOLD"} and repeated_exchange >= 3:
        proposals.append({
            "id": f"V381_EXCHANGE_GAP:{recent_exchange}",
            "kind": "source_feature",
            "reason": "repeated_information_exchange_hold_requires_new_diagnostic_or_reproduction_tooling",
            "evidence": {"status": recent_exchange, "recent_occurrences": repeated_exchange},
            "auto_apply": False,
            "pr_required": True,
            "required_validation": ["local_reproduction", "targeted_tests", "full_regression"],
        })
    return proposals[:8]


def _save_policy_state(state: dict[str, Any], *, path: Path) -> dict[str, Any]:
    if not _validate_policy_state(state):
        return {"status": "INVALID_POLICY_STATE", "written": False}
    try:
        atomic_write_json(path, state, suffix=".v381-policy.tmp")
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        return {"status": "POLICY_STATE_WRITE_FAILED", "written": False, "error_code": type(exc).__name__}
    return {"status": "POLICY_STATE_SAVED", "written": True}


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
            return None, {"status": "V381_LOCK_UNAVAILABLE", "error_code": "NOT_REGULAR_FILE"}
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        try:
            os.close(fd)
        except (OSError, UnboundLocalError):
            pass
        return None, {"status": "V381_CONCURRENT_AUTONOMY_HOLD", "error_code": "LOCK_BUSY"}
    except OSError as exc:
        try:
            os.close(fd)
        except (OSError, UnboundLocalError):
            pass
        return None, {"status": "V381_LOCK_UNAVAILABLE", "error_code": type(exc).__name__}
    return fd, {"status": "V381_LOCK_ACQUIRED", "error_code": None}


def _release_lock(fd: int) -> None:
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _history_row(
    *,
    now: datetime,
    market: dict[str, Any],
    exchange: dict[str, Any],
    selection: dict[str, Any],
    decision_status: str,
) -> dict[str, Any]:
    return {
        "observed_at": now.isoformat(timespec="seconds"),
        "market_regime": str(market.get("regime") or "UNKNOWN")[:160],
        "exchange_status": str(exchange.get("status") or "EXCHANGE_UNKNOWN")[:160],
        "exchange_digest": exchange.get("input_digest"),
        "champion_action": selection.get("champion_action"),
        "decision_status": str(decision_status or "UNKNOWN")[:160],
    }


def _next_policy_state(
    current: dict[str, Any],
    *,
    now: datetime,
    market: dict[str, Any],
    exchange: dict[str, Any],
    selection: dict[str, Any],
    decision_status: str,
) -> dict[str, Any]:
    history = list(current.get("history") or [])
    history.append(_history_row(
        now=now, market=market, exchange=exchange,
        selection=selection, decision_status=decision_status,
    ))
    return {
        "schema_version": POLICY_SCHEMA_VERSION,
        "controller_version": CONTROLLER_VERSION,
        "champion_action": selection.get("champion_action"),
        "promotion_count": int(current.get("promotion_count") or 0) + (1 if selection.get("promoted") else 0),
        "history": history[-MAX_POLICY_HISTORY:],
    }


def _decorate(
    base: dict[str, Any],
    *,
    lock: dict[str, Any],
    policy_load: dict[str, Any],
    stats: dict[str, dict[str, Any]],
    market: dict[str, Any],
    exchange: dict[str, Any],
    candidates: list[dict[str, Any]],
    selection: dict[str, Any],
    recipe: dict[str, Any],
    proposals: list[dict[str, Any]],
) -> dict[str, Any]:
    result = deepcopy(base)
    result["core_controller_version"] = str(base.get("controller_version") or CORE_CONTROLLER_VERSION)
    result["controller_version"] = CONTROLLER_VERSION
    result["v381_single_run_lock"] = lock
    result["policy_evolution_v381"] = {
        "state_status": policy_load.get("status"),
        "corruption_hold": policy_load.get("corruption_hold") is True,
        "verified_outcome_stats": stats,
        "candidate_actions": candidates,
        "selection": selection,
        "neural_model_source": "tablet_autonomous_evolution_v373 verified-outcome meta-neural",
        "raw_peer_lessons_used_for_training": False,
    }
    result["information_exchange_memory_v381"] = exchange
    result["market_adaptation_v381"] = market
    result["capability_recipe_v381"] = recipe
    result["source_feature_proposals_v381"] = proposals
    result["evolution_contract_v381"] = {
        "verified_outcomes_only": True,
        "champion_challenger_sample_gate": MIN_POLICY_SAMPLES,
        "promotion_margin": PROMOTION_MARGIN,
        "max_next_cycle_capabilities": MAX_RECIPE_CAPABILITIES,
        "runtime_self_extension": "allowlisted_declarative_capability_recipe_only",
        "source_level_new_functions": "non_executable_proposal_requires_protected_pr_ci",
        "market_adaptation": "freshness_coverage_source_health_only",
        "market_direction_prediction": False,
        "information_exchange_persistence": "digest_status_counts_only",
        "external_human_review_claimed": False,
    }
    result["safety"] = SAFETY
    return result


def run_cycle(
    *,
    execute: bool = False,
    apply_capabilities: bool = False,
    train_meta: bool = False,
    apply_skills: bool = False,
    root: Path = ROOT,
    now: datetime | None = None,
    proc_root: Path = Path("/proc"),
    state_path=None,
    capability_path=None,
    meta_model_path=None,
    meta_outcomes_path=None,
    skill_state_path=None,
    skill_outcomes_path=None,
    journal_path=None,
    core_lock_path=None,
    v380_lock_path=None,
    lock_path=None,
    quality_policy_path=None,
    policy_state_path=None,
    persist_outputs: bool = True,
) -> dict[str, Any]:
    moment = (now or _now()).astimezone(timezone.utc)
    mutating = bool(execute or apply_capabilities or train_meta or apply_skills)
    outer_lock = {"status": "V381_LOCK_NOT_REQUIRED", "error_code": None}
    fd = None
    if mutating:
        fd, outer_lock = _acquire_lock(lock_path or (root / LOCK_PATH.name))
        if fd is None:
            return {
                "controller_version": CONTROLLER_VERSION,
                "core_controller_version": CORE_CONTROLLER_VERSION,
                "v381_status": str(outer_lock["status"]),
                "execution": {
                    "status": str(outer_lock["status"]),
                    "executed": False,
                    "git_write": False,
                    "source_code_modified": False,
                    "proposals_executed": False,
                },
                "v381_single_run_lock": outer_lock,
                "safety": SAFETY,
            }

    outcome_path = meta_outcomes_path or (root / v373.OUTCOMES_PATH.name)
    policy_path = policy_state_path or (root / POLICY_STATE_PATH.name)
    kwargs = dict(
        root=root, now=moment, proc_root=proc_root,
        state_path=state_path, capability_path=capability_path,
        meta_model_path=meta_model_path, meta_outcomes_path=meta_outcomes_path,
        skill_state_path=skill_state_path, skill_outcomes_path=skill_outcomes_path,
        journal_path=journal_path, core_lock_path=core_lock_path,
        lock_path=v380_lock_path, quality_policy_path=quality_policy_path,
        persist_outputs=False,
    )
    try:
        preview = v380.run_cycle(
            execute=False, apply_capabilities=False, train_meta=False, apply_skills=False, **kwargs
        )
        policy_load = load_policy_state(policy_path)
        stats = verified_outcome_stats(outcome_path)
        market = market_operational_state(preview)
        exchange = information_exchange_memory(preview)
        candidates = policy_candidates(preview, stats, market)
        selection = select_champion(policy_load["state"], candidates)
        recipe = capability_recipe(preview, market, exchange, selection, now=moment)
        proposals = source_gap_proposals(policy_load["state"], market, exchange, recipe)

        if mutating and policy_load.get("corruption_hold") is True:
            result = _decorate(
                preview, lock=outer_lock, policy_load=policy_load, stats=stats,
                market=market, exchange=exchange, candidates=candidates,
                selection=selection, recipe=recipe, proposals=proposals,
            )
            result["v381_status"] = "V381_POLICY_MEMORY_HOLD"
            result["execution"] = {
                "status": "V381_POLICY_MEMORY_HOLD",
                "executed": False,
                "git_write": False,
                "source_code_modified": False,
                "proposals_executed": False,
            }
            return result

        core = preview
        if mutating:
            core = v380.run_cycle(
                execute=execute, apply_capabilities=apply_capabilities,
                train_meta=train_meta, apply_skills=apply_skills, **kwargs
            )

        result = _decorate(
            core, lock=outer_lock, policy_load=policy_load, stats=stats,
            market=market, exchange=exchange, candidates=candidates,
            selection=selection, recipe=recipe, proposals=proposals,
        )
        result["v381_status"] = str(core.get("v380_status") or "UNKNOWN") if mutating else "PLAN_ONLY"

        decision = core.get("autonomous_decision") if isinstance(core.get("autonomous_decision"), dict) else {}
        core_allowed = decision.get("allow_execution") is True and result["v381_status"] not in _HOLD_STATUSES

        capability_write = {"status": "V381_RECIPE_NOT_APPLIED", "written": False}
        if mutating and apply_capabilities and core_allowed and recipe["capabilities"]:
            cap_path = capability_path or (root / v373.CAPABILITY_PATH.name)
            loaded = v373.load_capabilities(path=cap_path, now=moment)
            if loaded.get("corruption_hold") is True:
                capability_write = {"status": "CAPABILITY_CORRUPTION_HOLD", "written": False}
            else:
                merged = v373.merge_capabilities(
                    list(loaded.get("capabilities") or []),
                    list(recipe["capabilities"]),
                    now=moment,
                )
                capability_write = v373.save_capabilities(
                    merged, path=cap_path, corruption_hold=False, now=moment
                )
        result["capability_recipe_v381"]["write"] = capability_write

        policy_write = {"status": "V381_POLICY_WRITE_NOT_REQUESTED", "written": False}
        if mutating and core_allowed:
            next_state = _next_policy_state(
                policy_load["state"], now=moment, market=market, exchange=exchange,
                selection=selection, decision_status=result["v381_status"],
            )
            policy_write = _save_policy_state(next_state, path=policy_path)
        result["policy_evolution_v381"]["write"] = policy_write

        if mutating and proposals:
            try:
                atomic_write_json(
                    root / PROPOSAL_PATH.name,
                    {
                        "schema_version": 1,
                        "controller_version": CONTROLLER_VERSION,
                        "generated_at": moment.isoformat(timespec="seconds"),
                        "auto_apply": False,
                        "pr_required": True,
                        "proposals": proposals,
                    },
                    suffix=".v381-proposals.tmp",
                )
                result["source_feature_proposals_v381_write"] = {"status": "SAVED", "written": True}
            except (OSError, UnicodeError, ValueError, TypeError) as exc:
                result["source_feature_proposals_v381_write"] = {
                    "status": "WRITE_FAILED", "written": False, "error_code": type(exc).__name__
                }

        if persist_outputs:
            try:
                atomic_write_json(root / REPORT_PATH.name, result, suffix=".v381-report.tmp")
                result["v381_runtime_output"] = {"status": "SAVED"}
            except (OSError, UnicodeError, ValueError, TypeError) as exc:
                result["v381_runtime_output"] = {
                    "status": "WRITE_FAILED", "error_code": type(exc).__name__
                }
        return result
    finally:
        if fd is not None:
            _release_lock(fd)


def self_test() -> None:
    assert SAFETY["verified_outcome_policy_learning_only"] is True
    assert SAFETY["policy_memory_summary_only"] is True
    assert SAFETY["champion_challenger_sample_gate_required"] is True
    assert SAFETY["declarative_capability_recipe_allowlisted_only"] is True
    assert SAFETY["source_level_gap_proposal_only"] is True
    assert SAFETY["source_code_auto_generation"] is False
    assert SAFETY["source_code_auto_rewrite"] is False
    assert SAFETY["git_write"] is False
    assert SAFETY["verification_bypass"] is False
    assert SAFETY["market_direction_inferred"] is False
    print("Tablet verified adaptive policy evolution v381: PASS")


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
    return 2 if result.get("v381_status") in _HOLD_STATUSES else 0


if __name__ == "__main__":
    raise SystemExit(main())
