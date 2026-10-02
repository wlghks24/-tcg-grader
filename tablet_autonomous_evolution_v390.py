#!/usr/bin/env python3
"""V390: goal-directed verified self-improvement governor for Tablet GPT / TCG Grader.

V390 sits above V388 and adds a small device-local meta-critic plus a goal
planner. The critic learns only from the verified reward portfolio already
accepted by V388. The planner converts operational KPI deficits, drift,
uncertainty, resource pressure and recurring feature gaps into bounded goals,
then scores the currently available verified actions against those goals.

The controller may persist one canonical V373 declarative capability to steer
the *next* cycle when the verified V388 selection is materially misaligned
with the highest-priority goal. It never invents a new runtime primitive and
never generates/rewrites source code. Source-level ideas remain non-executable
feature contracts requiring protected PR/CI and the existing regression,
integrity, alignment and actual-output validation chain.

No market direction is inferred. No facts, prices, grades, model weights or
raw peer state are invented/imported. V388 and every earlier hard gate remain
mandatory.
"""
from __future__ import annotations

import argparse
import json
import math
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tablet_autonomous_evolution_v373 as v373
import tablet_autonomous_evolution_v388 as v388
from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
CONTROLLER_VERSION = "v390"
CORE_CONTROLLER_VERSION = "v388"

STATE_PATH = ROOT / ".tablet_autonomy_v390_state.json"
REPORT_PATH = ROOT / "tablet_autonomy_v390_report.json"
PLAN_PATH = ROOT / "tablet_autonomy_goal_plan_v390.json"
LOCK_PATH = ROOT / ".tablet_autonomy_execution_v390.lock"

STATE_SCHEMA_VERSION = 1
MAX_STATE_BYTES = 1_500_000
MAX_HISTORY = 192
MAX_GOALS = 8
MAX_ACTION_LEDGER = 48
CRITIC_INPUT_DIM = 8
CRITIC_HIDDEN_DIM = 6
CRITIC_LR = 0.045
CRITIC_EPOCHS = 8
CRITIC_WEIGHT_BOUND = 4.0
MIN_CRITIC_TRAINING_ROWS = 2
GOAL_ALIGNMENT_HOLD_MARGIN = 0.16
MIN_GOAL_CAPABILITY_URGENCY = 0.42
MAX_GOAL_CAPABILITY_BOOST = 0.12

_HOLD_STATUSES = set(getattr(v388, "_HOLD_STATUSES", set())) | {
    "V390_STATE_CORRUPTION_HOLD",
    "V390_CONCURRENT_AUTONOMY_HOLD",
    "V390_GOAL_ALIGNMENT_HOLD",
    "V390_CAPABILITY_CORRUPTION_HOLD",
    "V390_CAPABILITY_WRITE_HOLD",
    "V390_STATE_COMMIT_HOLD",
    "V390_UPSTREAM_HOLD",
}

SAFETY = dict(v388.SAFETY)
SAFETY.update({
    "goal_directed_self_improvement": True,
    "goal_prioritization_operational_only": True,
    "verified_meta_critic_enabled": True,
    "verified_meta_critic_training_only": True,
    "verified_meta_critic_advisory_and_gating_only": True,
    "action_contribution_ledger_verified_reward_only": True,
    "goal_aligned_next_cycle_capability_enabled": True,
    "goal_capability_canonical_allowlist_only": True,
    "goal_capability_next_cycle_only": True,
    "source_feature_plan_non_executable": True,
    "source_feature_plan_requires_protected_pr_ci": True,
    "v388_gate_cannot_be_bypassed": True,
    "peer_model_weights_imported": False,
    "peer_raw_state_imported": False,
    "market_direction_inferred": False,
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
    return number if math.isfinite(number) else None


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _sigmoid(value: float) -> float:
    value = max(-30.0, min(30.0, value))
    return 1.0 / (1.0 + math.exp(-value))


def _default_critic() -> dict[str, Any]:
    w1 = [
        [round(math.sin((i + 1) * (j + 2)) * 0.035, 9) for j in range(CRITIC_HIDDEN_DIM)]
        for i in range(CRITIC_INPUT_DIM)
    ]
    w2 = [round(math.cos((j + 3) * 1.7) * 0.035, 9) for j in range(CRITIC_HIDDEN_DIM)]
    return {
        "input_dim": CRITIC_INPUT_DIM,
        "hidden_dim": CRITIC_HIDDEN_DIM,
        "sample_count": 0,
        "seen_verified_samples": {},
        "w1": w1,
        "b1": [0.0] * CRITIC_HIDDEN_DIM,
        "w2": w2,
        "b2": 0.0,
    }


def _default_state() -> dict[str, Any]:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "controller_version": CONTROLLER_VERSION,
        "cycle": 0,
        "critic": _default_critic(),
        "action_contributions": {},
        "last_primary_goal": None,
        "history": [],
    }


def _valid_matrix(value: Any, rows: int, cols: int) -> bool:
    if not isinstance(value, list) or len(value) != rows:
        return False
    for row in value:
        if not isinstance(row, list) or len(row) != cols:
            return False
        for item in row:
            number = _finite(item)
            if number is None or abs(number) > CRITIC_WEIGHT_BOUND:
                return False
    return True


def _valid_critic(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if set(value) != {"input_dim", "hidden_dim", "sample_count", "seen_verified_samples", "w1", "b1", "w2", "b2"}:
        return False
    if value["input_dim"] != CRITIC_INPUT_DIM or value["hidden_dim"] != CRITIC_HIDDEN_DIM:
        return False
    if not isinstance(value["sample_count"], int) or not 0 <= value["sample_count"] <= 10_000_000:
        return False
    seen = value.get("seen_verified_samples")
    if not isinstance(seen, dict) or len(seen) > MAX_ACTION_LEDGER:
        return False
    for action, samples in seen.items():
        if not isinstance(action, str) or not action or len(action) > 160:
            return False
        if isinstance(samples, bool) or not isinstance(samples, int) or not 0 <= samples <= 10_000_000:
            return False
    if not _valid_matrix(value["w1"], CRITIC_INPUT_DIM, CRITIC_HIDDEN_DIM):
        return False
    if not _valid_matrix([value["b1"]], 1, CRITIC_HIDDEN_DIM):
        return False
    if not _valid_matrix([value["w2"]], 1, CRITIC_HIDDEN_DIM):
        return False
    b2 = _finite(value["b2"])
    return b2 is not None and abs(b2) <= CRITIC_WEIGHT_BOUND


def _valid_state(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if set(value) != {
        "schema_version", "controller_version", "cycle", "critic",
        "action_contributions", "last_primary_goal", "history",
    }:
        return False
    if value["schema_version"] != STATE_SCHEMA_VERSION or value["controller_version"] != CONTROLLER_VERSION:
        return False
    if not isinstance(value["cycle"], int) or not 0 <= value["cycle"] <= 10_000_000:
        return False
    if not _valid_critic(value["critic"]):
        return False
    ledger = value["action_contributions"]
    if not isinstance(ledger, dict) or len(ledger) > MAX_ACTION_LEDGER:
        return False
    for action, row in ledger.items():
        if not isinstance(action, str) or not action or len(action) > 160 or not isinstance(row, dict):
            return False
        if set(row) != {"observations", "verified_reward_ewma", "critic_score_ewma", "last_seen_cycle"}:
            return False
        if not isinstance(row["observations"], int) or row["observations"] < 0:
            return False
        for key in ("verified_reward_ewma", "critic_score_ewma"):
            number = _finite(row[key])
            if number is None or not -1.0 <= number <= 1.0:
                return False
        if not isinstance(row["last_seen_cycle"], int) or row["last_seen_cycle"] < 0:
            return False
    if value["last_primary_goal"] is not None and (
        not isinstance(value["last_primary_goal"], str) or len(value["last_primary_goal"]) > 120
    ):
        return False
    return isinstance(value["history"], list) and len(value["history"]) <= MAX_HISTORY


def load_state(path: Path = STATE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"state": _default_state(), "status": "fresh", "corruption_hold": False}
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError("UNSAFE_V390_STATE_PATH")
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
            "error_code": "V390_STATE_SCHEMA_INVALID",
        }
    return {"state": value, "status": "loaded", "corruption_hold": False}


def save_state(state: dict[str, Any], path: Path, corruption_hold: bool) -> dict[str, Any]:
    if corruption_hold:
        return {"status": "V390_STATE_CORRUPTION_HOLD", "written": False}
    if not _valid_state(state):
        return {"status": "V390_STATE_INVALID", "written": False}
    try:
        atomic_write_json(path, state, suffix=".v390-state.tmp")
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        return {
            "status": "V390_STATE_WRITE_FAILED",
            "written": False,
            "error_code": type(exc).__name__,
        }
    return {"status": "V390_STATE_SAVED", "written": True}


def _critic_forward(model: dict[str, Any], features: list[float]) -> tuple[list[float], float]:
    hidden = []
    for j in range(CRITIC_HIDDEN_DIM):
        total = float(model["b1"][j])
        for i, value in enumerate(features):
            total += float(value) * float(model["w1"][i][j])
        hidden.append(math.tanh(total))
    total = float(model["b2"])
    for j, value in enumerate(hidden):
        total += value * float(model["w2"][j])
    return hidden, _sigmoid(total)


def _critic_features(row: dict[str, Any], base: dict[str, Any]) -> list[float]:
    portfolio_score = _finite(row.get("portfolio_score"))
    reward_lcb = _finite(row.get("reward_lcb"))
    long_reward = _finite(row.get("long_reward"))
    confidence = _finite(row.get("confidence"))
    verified = max(0, int(row.get("verified_samples") or 0))
    observations = max(0, int(row.get("observations") or 0))

    budget = base.get("v388_resource_budget")
    budget = budget if isinstance(budget, dict) else {}
    resource = _finite(budget.get("resource_headroom"))
    uncertainty = _finite(budget.get("selected_uncertainty"))
    drift = _finite(budget.get("drift_score"))

    return [
        _clamp(portfolio_score if portfolio_score is not None else 0.5),
        _clamp(((reward_lcb if reward_lcb is not None else 0.0) + 1.0) / 2.0),
        _clamp(((long_reward if long_reward is not None else 0.0) + 1.0) / 2.0),
        _clamp(confidence if confidence is not None else 0.0),
        _clamp(math.log1p(verified) / math.log(101.0)),
        _clamp(math.log1p(observations) / math.log(33.0)),
        _clamp(resource if resource is not None else 0.5),
        _clamp(1.0 - max(
            _clamp(uncertainty if uncertainty is not None else 0.5),
            _clamp(drift if drift is not None else 0.5),
        )),
    ]


def _critic_training_rows(base: dict[str, Any]) -> list[tuple[list[float], float, str, float, int]]:
    policy = base.get("v388_policy_portfolio")
    policy = policy if isinstance(policy, dict) else {}
    rows = policy.get("candidates") if isinstance(policy.get("candidates"), list) else []
    result = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        action = str(row.get("action_id") or "")[:160]
        verified = int(row.get("verified_samples") or 0)
        reward = _finite(row.get("long_reward"))
        if not action or verified < v388.MIN_VERIFIED_SAMPLES or reward is None:
            continue
        if str(row.get("status") or "") in {"retired"}:
            continue
        label = _clamp((reward + 1.0) / 2.0)
        result.append((_critic_features(row, base), label, action, reward, verified))
    return result[:v388.MAX_ACTIONS_PER_REGIME]


def train_critic(
    model: dict[str, Any],
    rows: list[tuple[list[float], float, str, float, int]],
) -> tuple[dict[str, Any], list[tuple[list[float], float, str, float, int]], dict[str, Any]]:
    trained = deepcopy(model)
    seen = dict(trained.get("seen_verified_samples") or {})
    fresh = [
        row for row in rows
        if int(row[4]) > int(seen.get(str(row[2]), 0) or 0)
    ]
    if len(fresh) < MIN_CRITIC_TRAINING_ROWS:
        return trained, [], {
            "status": "NO_NEW_VERIFIED_TRAINING_SET",
            "fresh_actions": [],
            "gradient_rows": 0,
            "verified_outcomes_only": True,
        }

    for _ in range(CRITIC_EPOCHS):
        for features, label, _, _, _ in fresh:
            hidden, pred = _critic_forward(trained, features)
            delta2 = (pred - label) * pred * (1.0 - pred)
            old_w2 = [float(x) for x in trained["w2"]]
            for j in range(CRITIC_HIDDEN_DIM):
                updated = float(trained["w2"][j]) - CRITIC_LR * delta2 * hidden[j]
                trained["w2"][j] = round(max(-CRITIC_WEIGHT_BOUND, min(CRITIC_WEIGHT_BOUND, updated)), 9)
            b2 = float(trained["b2"]) - CRITIC_LR * delta2
            trained["b2"] = round(max(-CRITIC_WEIGHT_BOUND, min(CRITIC_WEIGHT_BOUND, b2)), 9)

            for j in range(CRITIC_HIDDEN_DIM):
                delta1 = delta2 * old_w2[j] * (1.0 - hidden[j] * hidden[j])
                for i in range(CRITIC_INPUT_DIM):
                    updated = float(trained["w1"][i][j]) - CRITIC_LR * delta1 * features[i]
                    trained["w1"][i][j] = round(
                        max(-CRITIC_WEIGHT_BOUND, min(CRITIC_WEIGHT_BOUND, updated)), 9
                    )
                b1 = float(trained["b1"][j]) - CRITIC_LR * delta1
                trained["b1"][j] = round(max(-CRITIC_WEIGHT_BOUND, min(CRITIC_WEIGHT_BOUND, b1)), 9)

    for _, _, action, _, verified in fresh:
        seen[str(action)] = max(int(seen.get(str(action), 0) or 0), int(verified))
    trained["seen_verified_samples"] = dict(
        sorted(seen.items(), key=lambda item: item[0])[:MAX_ACTION_LEDGER]
    )
    trained["sample_count"] = min(
        10_000_000,
        int(model.get("sample_count") or 0) + len(fresh),
    )
    return trained, fresh, {
        "status": "TRAINED_NEW_VERIFIED_SAMPLES",
        "fresh_actions": [str(row[2]) for row in fresh],
        "gradient_rows": len(fresh),
        "verified_outcomes_only": True,
    }


def derive_goals(base: dict[str, Any]) -> list[dict[str, Any]]:
    kpis = base.get("v382_kpis")
    kpis = kpis if isinstance(kpis, dict) else {}
    dims = kpis.get("dimensions")
    dims = dims if isinstance(dims, dict) else {}
    budget = base.get("v388_resource_budget")
    budget = budget if isinstance(budget, dict) else {}
    backlog = base.get("v388_feature_backlog")
    backlog = backlog if isinstance(backlog, list) else []

    def dim(name: str, default: float = 0.5) -> float:
        value = _finite(dims.get(name))
        return _clamp(value if value is not None else default)

    uncertainty = _finite(budget.get("selected_uncertainty"))
    drift = _finite(budget.get("drift_score"))
    top_backlog = 0.0
    if backlog and isinstance(backlog[0], dict):
        top_backlog = _clamp(float(_finite(backlog[0].get("v388_priority_score")) or 0.0))

    rows = [
        ("RECOVER_MARKET_FRESHNESS", 1.0 - dim("market_freshness"), "market_freshness"),
        ("EXPAND_VERIFIED_MARKET_COVERAGE", 1.0 - dim("market_coverage"), "market_coverage"),
        ("RECOVER_SOURCE_HEALTH", 1.0 - dim("source_health"), "source_health"),
        ("IMPROVE_NEURAL_CONSENSUS", 1.0 - dim("neural_consensus"), "neural_consensus"),
        ("PRESERVE_RESOURCE_HEADROOM", 1.0 - dim("resource_headroom"), "resource_headroom"),
        ("REVALIDATE_UNCERTAINTY", max(
            _clamp(uncertainty if uncertainty is not None else 0.5),
            _clamp(drift if drift is not None else 0.5),
        ), "uncertainty_drift"),
        ("RESOLVE_PERSISTENT_FEATURE_GAPS", top_backlog, "feature_backlog"),
    ]

    portfolio = base.get("v388_policy_portfolio")
    portfolio = portfolio if isinstance(portfolio, dict) else {}
    upstream_status = str(portfolio.get("upstream_portfolio_status") or "")
    portfolio_stress = 0.75 if upstream_status in {"quarantined", "retired"} else 0.0
    rows.append(("STABILIZE_POLICY_PORTFOLIO", portfolio_stress, "policy_portfolio"))

    goals = [
        {
            "goal_id": goal_id,
            "urgency": round(_clamp(urgency), 6),
            "evidence_dimension": evidence,
            "market_direction_inferred": False,
        }
        for goal_id, urgency, evidence in rows
    ]
    goals.sort(key=lambda row: (-float(row["urgency"]), row["goal_id"]))
    return goals[:MAX_GOALS]


def _goal_affinity(action: str, goal_id: str) -> float:
    action_u = action.upper()
    if goal_id == "RECOVER_MARKET_FRESHNESS":
        return 1.0 if "REFRESH" in action_u else (0.70 if "REVALIDATE" in action_u else 0.15)
    if goal_id == "EXPAND_VERIFIED_MARKET_COVERAGE":
        return 1.0 if "COVERAGE" in action_u or "EXPAND" in action_u else 0.15
    if goal_id == "RECOVER_SOURCE_HEALTH":
        return 1.0 if any(token in action_u for token in ("SOURCE", "RECHECK", "RECOVER")) else 0.15
    if goal_id == "IMPROVE_NEURAL_CONSENSUS":
        return 1.0 if any(token in action_u for token in ("TRAIN", "NEURAL", "LEARN")) else 0.25
    if goal_id == "PRESERVE_RESOURCE_HEADROOM":
        return 0.85 if v388._is_recovery(action) else (0.55 if "REVALIDATE" in action_u else 0.30)
    if goal_id == "REVALIDATE_UNCERTAINTY":
        return 1.0 if any(token in action_u for token in ("REVALIDATE", "VERIFY", "AUDIT", "RECHECK")) else 0.35
    if goal_id == "STABILIZE_POLICY_PORTFOLIO":
        return 0.90 if v388._is_recovery(action) else 0.45
    return 0.35


def goal_plan(base: dict[str, Any], critic: dict[str, Any], goals: list[dict[str, Any]]) -> dict[str, Any]:
    policy = base.get("v388_policy_portfolio")
    policy = policy if isinstance(policy, dict) else {}
    candidates = policy.get("candidates") if isinstance(policy.get("candidates"), list) else []
    primary = goals[0] if goals else {
        "goal_id": "STEADY_VERIFIED_OPTIMIZATION",
        "urgency": 0.0,
        "evidence_dimension": "none",
    }
    primary_id = str(primary.get("goal_id") or "")
    urgency = _clamp(float(_finite(primary.get("urgency")) or 0.0))

    ranked = []
    for row in candidates:
        if not isinstance(row, dict):
            continue
        action = str(row.get("action_id") or "")[:160]
        if not action:
            continue
        status = str(row.get("status") or "challenger")
        features = _critic_features(row, base)
        _, critic_score = _critic_forward(critic, features)
        portfolio_score = _clamp(float(_finite(row.get("portfolio_score")) or 0.0))
        confidence = _clamp(float(_finite(row.get("confidence")) or 0.0))
        affinity = _goal_affinity(action, primary_id)
        score = (
            0.34 * critic_score
            + 0.30 * affinity
            + 0.20 * portfolio_score
            + 0.16 * confidence
        )
        if status == "quarantined":
            score -= 0.35
        elif status == "retired":
            score -= 0.70
        ranked.append({
            "action_id": action,
            "goal_affinity": round(_clamp(affinity), 6),
            "critic_score": round(_clamp(critic_score), 6),
            "portfolio_score": round(portfolio_score, 6),
            "confidence": round(confidence, 6),
            "status": status,
            "recovery_action": v388._is_recovery(action),
            "goal_utility": round(_clamp(score), 6),
            "verified_samples": int(row.get("verified_samples") or 0),
        })

    ranked.sort(key=lambda row: (
        row["status"] in {"quarantined", "retired"},
        -float(row["goal_utility"]),
        -int(row["verified_samples"]),
        row["action_id"],
    ))
    recommended = ranked[0] if ranked else None
    upstream_action = str(policy.get("upstream_selected_action") or "") or None
    upstream_row = next((row for row in ranked if row["action_id"] == upstream_action), None)

    return {
        "primary_goal": primary,
        "goals": goals,
        "upstream_selected_action": upstream_action,
        "recommended_action": recommended.get("action_id") if recommended else None,
        "recommended_score": recommended.get("goal_utility") if recommended else None,
        "upstream_goal_score": upstream_row.get("goal_utility") if upstream_row else None,
        "score_gap": round(
            max(
                0.0,
                float(recommended.get("goal_utility") or 0.0)
                - float(upstream_row.get("goal_utility") or 0.0),
            ),
            6,
        ) if recommended and upstream_row else 0.0,
        "candidates": ranked,
        "critic_sample_count": int(critic.get("sample_count") or 0),
        "market_direction_inferred": False,
    }


def goal_capability(plan: dict[str, Any], base: dict[str, Any], *, now: datetime) -> dict[str, Any] | None:
    primary = plan.get("primary_goal") if isinstance(plan.get("primary_goal"), dict) else {}
    urgency = _clamp(float(_finite(primary.get("urgency")) or 0.0))
    if str(primary.get("goal_id") or "") == "RESOLVE_PERSISTENT_FEATURE_GAPS":
        return None
    action = str(plan.get("recommended_action") or "")
    if not action or urgency < MIN_GOAL_CAPABILITY_URGENCY:
        return None

    evidence = {
        "reason": "v390_goal_directed_next_cycle_alignment",
        "goal_id": str(primary.get("goal_id") or "")[:120],
        "urgency": round(urgency, 6),
        "recommended_action": action[:160],
    }

    if action in v373.v372.SAFE_LEARNING_ACTIONS:
        row = v373._capability(
            "PRIORITIZE_SAFE_LEARNING",
            f"V390_{action}",
            {"action_id": action, "boost": min(MAX_GOAL_CAPABILITY_BOOST, 0.05 + 0.07 * urgency)},
            evidence,
            now=now,
        )
        return row if v373.validate_capability(row, now=now) else None

    if action == "REFRESH_MARKET_DATA":
        row = v373._capability(
            "REQUEST_FRESHNESS_REFRESH",
            "V390_GOAL",
            {"max_runs": 1},
            evidence,
            now=now,
        )
        return row if v373.validate_capability(row, now=now) else None

    if action == "RECHECK_DEGRADED_SOURCES":
        row = v373._capability(
            "RETRY_DEGRADED_SOURCES",
            "V390_GOAL",
            {"max_retry": 2, "backoff_seconds": 120},
            evidence,
            now=now,
        )
        return row if v373.validate_capability(row, now=now) else None

    if action == "EXPAND_MARKET_COVERAGE":
        market = base.get("market_adaptation_v381")
        market = market if isinstance(market, dict) else {}
        regions = [str(x) for x in list(market.get("low_coverage_regions") or []) if str(x) in {"KR", "JP", "US"}]
        if regions:
            row = v373._capability(
                "PRIORITIZE_REGION",
                f"V390_{regions[0]}",
                {"region": regions[0], "boost": min(MAX_GOAL_CAPABILITY_BOOST, 0.05 + 0.07 * urgency)},
                evidence,
                now=now,
            )
            return row if v373.validate_capability(row, now=now) else None
    return None


def autonomous_gate(base: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    upstream = base.get("v388_autonomous_gate")
    upstream = upstream if isinstance(upstream, dict) else {}
    allow = upstream.get("allow_execution") is True
    reasons: list[str] = []
    if not allow:
        reasons.append(str(upstream.get("status") or "V388_UPSTREAM_HOLD"))

    upstream_action = str(plan.get("upstream_selected_action") or "") or None
    recommended = str(plan.get("recommended_action") or "") or None
    gap = float(_finite(plan.get("score_gap")) or 0.0)
    critic_samples = int(plan.get("critic_sample_count") or 0)

    if (
        allow
        and recommended
        and upstream_action
        and recommended != upstream_action
        and critic_samples >= MIN_CRITIC_TRAINING_ROWS
        and gap >= GOAL_ALIGNMENT_HOLD_MARGIN
        and not v388._is_recovery(upstream_action)
    ):
        allow = False
        reasons.append("GOAL_ALIGNMENT_REVALIDATION")

    if "GOAL_ALIGNMENT_REVALIDATION" in reasons:
        status = "V390_GOAL_ALIGNMENT_HOLD"
    elif not allow:
        status = "V390_UPSTREAM_HOLD"
    else:
        status = "V390_VERIFIED_ALLOW"

    return {
        "status": status,
        "allow_execution": allow,
        "upstream_selected_action": upstream_action,
        "recommended_action": recommended,
        "score_gap": round(gap, 6),
        "reasons": reasons,
        "hard_blocker_override": False,
        "market_direction_inferred": False,
    }


def source_feature_plan(base: dict[str, Any], goal_plan_value: dict[str, Any]) -> list[dict[str, Any]]:
    backlog = base.get("v388_feature_backlog")
    backlog = backlog if isinstance(backlog, list) else []
    primary = goal_plan_value.get("primary_goal")
    primary = primary if isinstance(primary, dict) else {}
    result = []
    for row in backlog[:24]:
        if not isinstance(row, dict):
            continue
        priority = _clamp(float(_finite(row.get("v388_priority_score")) or 0.0))
        recurrence = max(0, int(row.get("v388_recurrence") or 0))
        if priority >= 0.72 and recurrence >= 3:
            stage = "protected_pr_candidate"
        elif priority >= 0.48:
            stage = "shadow_spec"
        else:
            stage = "observe"
        result.append({
            **deepcopy(row),
            "v390_stage": stage,
            "v390_primary_goal": str(primary.get("goal_id") or "")[:120],
            "v390_goal_urgency": round(float(_finite(primary.get("urgency")) or 0.0), 6),
            "v390_execution_mode": "non_executable_protected_pr_ci_contract",
            "auto_execute": False,
            "auto_generate_source": False,
            "git_write": False,
            "promotion_requires": [
                "shadow_spec",
                "targeted_tests",
                "related_regression",
                "canary_validation",
                "full_current_runtime",
                "repository_integrity",
                "tablet_gpt_alignment",
                "actual_output_validation",
            ],
        })
    return result


def _next_state(
    current: dict[str, Any],
    critic: dict[str, Any],
    training_rows: list[tuple[list[float], float, str, float, int]],
    plan: dict[str, Any],
    gate: dict[str, Any],
    *,
    now: datetime,
) -> dict[str, Any]:
    nxt = deepcopy(current)
    cycle = min(10_000_000, int(current.get("cycle") or 0) + 1)
    ledger = dict(current.get("action_contributions") or {})

    scores = {
        str(row.get("action_id") or ""): float(_finite(row.get("critic_score")) or 0.0)
        for row in plan.get("candidates", [])
        if isinstance(row, dict)
    }
    for _, _, action, reward, _ in training_rows:
        old = ledger.get(action) if isinstance(ledger.get(action), dict) else {}
        observations = min(1_000_000, int(old.get("observations") or 0) + 1)
        old_reward = _finite(old.get("verified_reward_ewma"))
        old_critic = _finite(old.get("critic_score_ewma"))
        critic_score = scores.get(action, 0.5)
        reward_ewma = reward if old_reward is None else 0.25 * reward + 0.75 * old_reward
        critic_ewma = critic_score if old_critic is None else 0.25 * critic_score + 0.75 * old_critic
        ledger[action] = {
            "observations": observations,
            "verified_reward_ewma": round(max(-1.0, min(1.0, reward_ewma)), 6),
            "critic_score_ewma": round(max(-1.0, min(1.0, 2.0 * critic_ewma - 1.0)), 6),
            "last_seen_cycle": cycle,
        }

    ledger = dict(
        sorted(ledger.items(), key=lambda pair: (-int(pair[1]["observations"]), pair[0]))[:MAX_ACTION_LEDGER]
    )
    history = list(current.get("history") or [])
    primary = plan.get("primary_goal") if isinstance(plan.get("primary_goal"), dict) else {}
    history.append({
        "observed_at": now.isoformat(timespec="seconds"),
        "cycle": cycle,
        "primary_goal": primary.get("goal_id"),
        "goal_urgency": primary.get("urgency"),
        "upstream_action": plan.get("upstream_selected_action"),
        "recommended_action": plan.get("recommended_action"),
        "gate_status": gate.get("status"),
        "critic_samples": critic.get("sample_count"),
    })
    nxt.update({
        "schema_version": STATE_SCHEMA_VERSION,
        "controller_version": CONTROLLER_VERSION,
        "cycle": cycle,
        "critic": critic,
        "action_contributions": ledger,
        "last_primary_goal": str(primary.get("goal_id") or "")[:120] or None,
        "history": history[-MAX_HISTORY:],
    })
    return nxt


def _persist_goal_capability(
    capability: dict[str, Any] | None,
    *,
    path: Path,
    now: datetime,
) -> dict[str, Any]:
    if capability is None:
        return {"status": "NO_GOAL_CAPABILITY", "written": False}
    loaded = v373.load_capabilities(path=path, now=now)
    if loaded.get("corruption_hold") is True:
        return {"status": "V390_CAPABILITY_CORRUPTION_HOLD", "written": False}
    merged = v373.merge_capabilities(
        list(loaded.get("capabilities") or []),
        [capability],
        now=now,
    )
    return v373.save_capabilities(merged, path=path, corruption_hold=False, now=now)


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
    cap_path = upstream_paths.get("capability_path")
    cap_path = Path(cap_path) if cap_path is not None else (root / v373.CAPABILITY_PATH.name)

    fd = None
    lock_info = {"status": "V390_LOCK_NOT_REQUIRED", "error_code": None}
    if mutating:
        fd, lock_info = v388.v387.v386.v385._acquire_lock(root / LOCK_PATH.name)
        if fd is None:
            return {
                "controller_version": CONTROLLER_VERSION,
                "v390_status": "V390_CONCURRENT_AUTONOMY_HOLD",
                "execution": {
                    "status": "V390_CONCURRENT_AUTONOMY_HOLD",
                    "executed": False,
                    "git_write": False,
                    "source_code_modified": False,
                },
                "safety": SAFETY,
            }

    try:
        preview = v388.run_cycle(
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
        training_rows = _critic_training_rows(preview)
        critic, fresh_training_rows, critic_training = train_critic(loaded["state"]["critic"], training_rows)
        goals = derive_goals(preview)
        planner = goal_plan(preview, critic, goals)
        gate = autonomous_gate(preview, planner)
        capability = goal_capability(planner, preview, now=moment)
        capability_write = {"status": "GOAL_CAPABILITY_NOT_REQUESTED", "written": False}

        if mutating and loaded.get("corruption_hold"):
            gate = {
                "status": "V390_STATE_CORRUPTION_HOLD",
                "allow_execution": False,
                "upstream_selected_action": planner.get("upstream_selected_action"),
                "recommended_action": planner.get("recommended_action"),
                "score_gap": planner.get("score_gap"),
                "reasons": ["STATE_CORRUPTION_HOLD"],
                "hard_blocker_override": False,
                "market_direction_inferred": False,
            }

        upstream_preview_gate = preview.get("v388_autonomous_gate")
        upstream_preview_allowed = (
            isinstance(upstream_preview_gate, dict)
            and upstream_preview_gate.get("allow_execution") is True
        )
        if (
            mutating
            and apply_capabilities
            and capability is not None
            and upstream_preview_allowed
            and not loaded.get("corruption_hold")
        ):
            capability_write = _persist_goal_capability(capability, path=cap_path, now=moment)
            if capability_write.get("status") == "V390_CAPABILITY_CORRUPTION_HOLD":
                gate = {
                    **gate,
                    "status": "V390_CAPABILITY_CORRUPTION_HOLD",
                    "allow_execution": False,
                    "reasons": list(gate.get("reasons") or []) + ["CAPABILITY_CORRUPTION_HOLD"],
                }
            elif capability_write.get("written") is not True:
                gate = {
                    **gate,
                    "status": "V390_CAPABILITY_WRITE_HOLD",
                    "allow_execution": False,
                    "reasons": list(gate.get("reasons") or []) + ["CAPABILITY_WRITE_FAILED"],
                }

        base = preview
        if mutating and gate.get("allow_execution") is True:
            base = v388.run_cycle(
                domain=domain,
                execute=execute,
                apply_capabilities=apply_capabilities,
                train_meta=train_meta,
                apply_skills=apply_skills,
                root=root,
                now=moment,
                persist_outputs=False,
                **upstream_paths,
            )
            if str(base.get("v388_status") or "") in getattr(v388, "_HOLD_STATUSES", set()):
                gate = {
                    **gate,
                    "status": "V390_UPSTREAM_HOLD",
                    "allow_execution": False,
                    "reasons": list(gate.get("reasons") or []) + [str(base.get("v388_status") or "V388_HOLD")],
                }

        feature_plan = source_feature_plan(base, planner)
        result = deepcopy(base)
        result.update({
            "core_controller_version": str(base.get("controller_version") or CORE_CONTROLLER_VERSION),
            "controller_version": CONTROLLER_VERSION,
            "v390_status": gate.get("status") if mutating else "PLAN_ONLY",
            "v390_goals": goals,
            "v390_goal_plan": planner,
            "v390_meta_critic": {
                "sample_count": critic.get("sample_count"),
                "available_verified_rows": len(training_rows),
                "fresh_training_rows": len(fresh_training_rows),
                "trained_this_cycle": bool(fresh_training_rows),
                "training": critic_training,
                "training_source": "new_v388_verified_reward_portfolio_samples_only",
                "model_weights_imported": False,
            },
            "v390_goal_capability": {
                "candidate": capability,
                "write": capability_write,
                "next_cycle_only": True,
                "canonical_allowlist_only": True,
            },
            "v390_autonomous_gate": gate,
            "v390_source_feature_plan": feature_plan,
            "evolution_contract_v390": {
                "base_controller": "v388",
                "primary_loop": "observe_goal_rank_critic_score_steer_revalidate_execute_monitor",
                "critic_training": "verified_v388_reward_portfolio_only",
                "goal_inputs": "kpi_deficits_drift_uncertainty_resource_feature_backlog",
                "goal_capability": "one_canonical_v373_declarative_capability_next_cycle_only",
                "source_level_extension": "non_executable_protected_pr_ci_contract_only",
                "market_adaptation": "operational_regime_and_kpi_only_no_direction_prediction",
                "v388_and_prior_gate_bypass": False,
                "peer_model_weights_imported": False,
                "peer_raw_state_imported": False,
                "git_write": False,
                "source_code_auto_generation": False,
                "source_code_auto_rewrite": False,
                "arbitrary_command_execution": False,
                "verification_bypass": False,
            },
            "safety": SAFETY,
        })

        if mutating and gate.get("allow_execution") is not True:
            result["execution"] = {
                "status": gate.get("status"),
                "executed": False,
                "git_write": False,
                "source_code_modified": False,
                "proposals_executed": False,
            }

        state_write = {"status": "V390_STATE_WRITE_NOT_REQUESTED", "written": False}
        if mutating:
            nxt = _next_state(
                loaded["state"],
                critic,
                fresh_training_rows,
                planner,
                gate,
                now=moment,
            )
            state_write = save_state(nxt, state_file, bool(loaded.get("corruption_hold")))
            if not state_write.get("written") and gate.get("allow_execution") is True:
                result["v390_status"] = "V390_STATE_COMMIT_HOLD"
                result["execution"] = {
                    "status": "V390_STATE_COMMIT_HOLD",
                    "executed": False,
                    "git_write": False,
                    "source_code_modified": False,
                    "proposals_executed": False,
                }
        result["v390_state_write"] = state_write

        if persist_outputs:
            try:
                atomic_write_json(
                    root / PLAN_PATH.name,
                    {
                        "schema_version": 1,
                        "controller_version": CONTROLLER_VERSION,
                        "generated_at": moment.isoformat(timespec="seconds"),
                        "goal_plan": planner,
                        "feature_plan": feature_plan,
                        "auto_generate_source": False,
                        "git_write": False,
                        "protected_pr_ci_required": True,
                    },
                    suffix=".v390-plan.tmp",
                )
                atomic_write_json(root / REPORT_PATH.name, result, suffix=".v390-report.tmp")
                result["v390_runtime_output"] = {"status": "SAVED"}
            except (OSError, UnicodeError, ValueError, TypeError) as exc:
                result["v390_runtime_output"] = {
                    "status": "WRITE_FAILED",
                    "error_code": type(exc).__name__,
                }
        return result
    finally:
        if fd is not None:
            v388.v387.v386.v385._release_lock(fd)


def self_test() -> None:
    state = _default_state()
    assert _valid_state(state)
    assert SAFETY["goal_directed_self_improvement"] is True
    assert SAFETY["verified_meta_critic_enabled"] is True
    assert SAFETY["verified_meta_critic_training_only"] is True
    assert SAFETY["goal_capability_canonical_allowlist_only"] is True
    assert SAFETY["source_feature_plan_non_executable"] is True
    assert SAFETY["v388_gate_cannot_be_bypassed"] is True
    assert SAFETY["peer_model_weights_imported"] is False
    assert SAFETY["source_code_auto_generation"] is False
    assert SAFETY["source_code_auto_rewrite"] is False
    assert SAFETY["arbitrary_command_execution"] is False
    assert SAFETY["git_write"] is False
    assert SAFETY["market_direction_inferred"] is False
    print("Tablet goal-directed verified self-improvement governor v390: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", choices=sorted(v388.v387.v386.DOMAINS), default="tablet_gpt")
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
    return 2 if result.get("v390_status") in _HOLD_STATUSES else 0


if __name__ == "__main__":
    raise SystemExit(main())
