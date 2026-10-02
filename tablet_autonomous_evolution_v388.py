#!/usr/bin/env python3
"""V388: regime-conditioned policy portfolio and resource-budget autonomy.

V388 sits above V387. V387 provides uncertainty-aware mutual neural decisions,
operational regime transition holds, and a declarative feature lifecycle.
V388 adds long-horizon verified policy portfolios per operational regime,
short/long reward memory, conservative lower-confidence bounds, bounded
quarantine/retirement of repeatedly regressing non-recovery policies,
resource-aware learning/exploration/revalidation budgets, and prioritized
non-executable feature backlogs.

V388 never predicts market direction, never generates or rewrites source code,
never executes arbitrary commands, never writes Git/main, never imports peer
weights/raw state, never invents facts/prices/grades, and never bypasses V387
or any earlier hard gate. New source-level capabilities remain proposals that
require protected PR/CI and verified output.
"""
from __future__ import annotations

import argparse
import json
import math
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tablet_autonomous_evolution_v387 as v387
from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
CONTROLLER_VERSION = "v388"
CORE_CONTROLLER_VERSION = "v387"

STATE_PATH = ROOT / ".tablet_autonomy_v388_state.json"
REPORT_PATH = ROOT / "tablet_autonomy_v388_report.json"
FEATURE_BACKLOG_PATH = ROOT / "tablet_autonomy_feature_backlog_v388.json"
LOCK_PATH = ROOT / ".tablet_autonomy_execution_v388.lock"

STATE_SCHEMA_VERSION = 1
MAX_STATE_BYTES = 1_500_000
MAX_REGIMES = 20
MAX_ACTIONS_PER_REGIME = 48
MAX_FEATURES = 96
MAX_HISTORY = 192

MIN_VERIFIED_SAMPLES = max(
    3,
    int(getattr(getattr(v387, "v386", object()), "MIN_VERIFIED_SAMPLES", 3)),
)
MIN_PORTFOLIO_OBSERVATIONS = 2
QUARANTINE_BAD_STREAK = 3
RETIRE_BAD_STREAK = 6
QUARANTINE_CYCLES = 4
PORTFOLIO_DISAGREEMENT_MARGIN = 0.16
RESOURCE_LOW = 0.28
RESOURCE_CRITICAL = 0.14
HIGH_DRIFT = 0.55

RECOVERY_TOKENS = tuple(getattr(v387, "RECOVERY_TOKENS", (
    "REFRESH", "REVALIDATE", "RECOVER", "VERIFY", "AUDIT", "COLLECT",
    "RECHECK", "REBUILD_LAST_GOOD", "RESTORE_LAST_GOOD",
)))

_PORTFOLIO_STATUSES = {"challenger", "champion", "quarantined", "retired", "recovery"}
_HOLD_STATUSES = set(getattr(v387, "_HOLD_STATUSES", set())) | {
    "V388_STATE_CORRUPTION_HOLD",
    "V388_LOCK_UNAVAILABLE",
    "V388_CONCURRENT_AUTONOMY_HOLD",
    "V388_POLICY_QUARANTINE_HOLD",
    "V388_PORTFOLIO_DISAGREEMENT_HOLD",
    "V388_RESOURCE_CRITICAL_HOLD",
    "V388_UPSTREAM_HOLD",
    "V388_STATE_COMMIT_HOLD",
}

SAFETY = dict(v387.SAFETY)
SAFETY.update({
    "regime_conditioned_policy_portfolio": True,
    "verified_reward_memory_only": True,
    "short_long_horizon_reward_tracking": True,
    "conservative_reward_confidence_bound": True,
    "verified_regression_policy_quarantine": True,
    "verified_regression_policy_retirement": True,
    "resource_budget_autonomy": True,
    "bounded_exploration_budget_advisory_only": True,
    "feature_backlog_autoprioritization": True,
    "feature_backlog_non_executable": True,
    "v387_gate_cannot_be_bypassed": True,
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


def _clamp_reward(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _is_recovery(action_id: str | None) -> bool:
    value = str(action_id or "").upper()
    return any(token in value for token in RECOVERY_TOKENS)


def _default_state() -> dict[str, Any]:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "controller_version": CONTROLLER_VERSION,
        "cycle": 0,
        "portfolios": {},
        "feature_priorities": {},
        "history": [],
    }


def _valid_metric_row(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    required = {
        "observations", "verified_samples", "short_reward", "long_reward",
        "confidence", "reward_lcb", "bad_streak", "status",
        "quarantine_until_cycle", "last_seen_cycle",
    }
    if set(row) != required:
        return False
    if not isinstance(row["observations"], int) or not 0 <= row["observations"] <= 1_000_000:
        return False
    if not isinstance(row["verified_samples"], int) or not 0 <= row["verified_samples"] <= 1_000_000:
        return False
    for key in ("short_reward", "long_reward", "reward_lcb"):
        value = _finite(row.get(key))
        if value is None or not -1.0 <= value <= 1.0:
            return False
    confidence = _finite(row.get("confidence"))
    if confidence is None or not 0 <= confidence <= 1:
        return False
    if not isinstance(row["bad_streak"], int) or not 0 <= row["bad_streak"] <= 1_000_000:
        return False
    if row["status"] not in _PORTFOLIO_STATUSES:
        return False
    if not isinstance(row["quarantine_until_cycle"], int) or row["quarantine_until_cycle"] < 0:
        return False
    if not isinstance(row["last_seen_cycle"], int) or row["last_seen_cycle"] < 0:
        return False
    return True


def _valid_state(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if set(value) != {
        "schema_version", "controller_version", "cycle",
        "portfolios", "feature_priorities", "history",
    }:
        return False
    if value.get("schema_version") != STATE_SCHEMA_VERSION:
        return False
    if value.get("controller_version") != CONTROLLER_VERSION:
        return False
    if not isinstance(value.get("cycle"), int) or not 0 <= value["cycle"] <= 10_000_000:
        return False
    portfolios = value.get("portfolios")
    if not isinstance(portfolios, dict) or len(portfolios) > MAX_REGIMES:
        return False
    for regime, actions in portfolios.items():
        if not isinstance(regime, str) or not regime or len(regime) > 80:
            return False
        if not isinstance(actions, dict) or len(actions) > MAX_ACTIONS_PER_REGIME:
            return False
        for action, row in actions.items():
            if not isinstance(action, str) or not action or len(action) > 160:
                return False
            if not _valid_metric_row(row):
                return False
    priorities = value.get("feature_priorities")
    if not isinstance(priorities, dict) or len(priorities) > MAX_FEATURES:
        return False
    for proposal_id, row in priorities.items():
        if not isinstance(proposal_id, str) or not proposal_id or len(proposal_id) > 180:
            return False
        if not isinstance(row, dict):
            return False
        if set(row) != {"observations", "priority_ewma", "last_status", "last_seen_cycle"}:
            return False
        if not isinstance(row["observations"], int) or not 0 <= row["observations"] <= 1_000_000:
            return False
        if _finite(row["priority_ewma"]) is None or not 0 <= float(row["priority_ewma"]) <= 1:
            return False
        if not isinstance(row["last_status"], str) or len(row["last_status"]) > 48:
            return False
        if not isinstance(row["last_seen_cycle"], int) or row["last_seen_cycle"] < 0:
            return False
    history = value.get("history")
    return isinstance(history, list) and len(history) <= MAX_HISTORY


def load_state(path: Path = STATE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"state": _default_state(), "status": "fresh", "corruption_hold": False}
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError("UNSAFE_V388_STATE_PATH")
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
            "error_code": "V388_STATE_SCHEMA_INVALID",
        }
    return {"state": value, "status": "loaded", "corruption_hold": False}


def save_state(state: dict[str, Any], path: Path, corruption_hold: bool) -> dict[str, Any]:
    if corruption_hold:
        return {"status": "V388_STATE_CORRUPTION_HOLD", "written": False}
    if not _valid_state(state):
        return {"status": "V388_STATE_INVALID", "written": False}
    try:
        atomic_write_json(path, state, suffix=".v388-state.tmp")
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        return {
            "status": "V388_STATE_WRITE_FAILED",
            "written": False,
            "error_code": type(exc).__name__,
        }
    return {"status": "V388_STATE_SAVED", "written": True}


def _current_regime(base: dict[str, Any]) -> str:
    policy = base.get("v387_uncertainty_policy")
    if isinstance(policy, dict):
        transition = policy.get("regime_transition")
        if isinstance(transition, dict):
            regime = str(transition.get("local_regime") or "UNKNOWN")[:80]
            return regime or "UNKNOWN"
    mutual = base.get("v386_mutual_neural_policy")
    if isinstance(mutual, dict):
        return str(mutual.get("local_regime") or "UNKNOWN")[:80]
    return "UNKNOWN"


def _verified_reward_rows(base: dict[str, Any]) -> dict[str, dict[str, Any]]:
    policy = base.get("v385_verified_neural_policy")
    rows = policy.get("candidates") if isinstance(policy, dict) and isinstance(policy.get("candidates"), list) else []
    result: dict[str, dict[str, Any]] = {}
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        action = str(raw.get("action_id") or "")[:160]
        samples = max(0, int(raw.get("verified_samples") or 0))
        reward = _finite(raw.get("reward_mean"))
        if not action or samples < MIN_VERIFIED_SAMPLES or reward is None:
            continue
        result[action] = {
            "verified_samples": samples,
            "reward_mean": _clamp_reward(reward),
        }
    return result


def _v387_candidates(base: dict[str, Any]) -> list[dict[str, Any]]:
    policy = base.get("v387_uncertainty_policy")
    rows = policy.get("candidates") if isinstance(policy, dict) and isinstance(policy.get("candidates"), list) else []
    return [row for row in rows[:MAX_ACTIONS_PER_REGIME] if isinstance(row, dict)]


def update_portfolio(state: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    cycle = min(10_000_000, int(state.get("cycle") or 0) + 1)
    regime = _current_regime(base)
    portfolios = deepcopy(state.get("portfolios") or {})
    current = dict(portfolios.get(regime) or {})
    reward_rows = _verified_reward_rows(base)

    for candidate in _v387_candidates(base):
        action = str(candidate.get("action_id") or "")[:160]
        verified = reward_rows.get(action)
        if not action or not verified:
            continue

        reward = float(verified["reward_mean"])
        samples = int(verified["verified_samples"])
        confidence = _finite(candidate.get("confidence"))
        confidence = _clamp(confidence if confidence is not None else 0.0)

        previous = current.get(action) if isinstance(current.get(action), dict) else None
        observations = int(previous.get("observations") or 0) + 1 if previous else 1
        short = reward if previous is None else 0.35 * reward + 0.65 * float(previous["short_reward"])
        long = reward if previous is None else 0.10 * reward + 0.90 * float(previous["long_reward"])
        conf = confidence if previous is None else 0.20 * confidence + 0.80 * float(previous["confidence"])
        effective_samples = max(samples, int(previous.get("verified_samples") or 0) if previous else 0)
        penalty = min(0.65, 0.85 / math.sqrt(max(1, effective_samples)))
        reward_lcb = _clamp_reward(long - penalty)

        regression = (
            reward_lcb < -0.10
            or short + 0.20 < long
            or (previous is not None and short + 0.18 < float(previous["short_reward"]))
        )
        bad_streak = min(
            1_000_000,
            (int(previous.get("bad_streak") or 0) + 1 if regression else 0)
            if previous else (1 if regression else 0),
        )

        recovery = _is_recovery(action)
        status = str(previous.get("status") or "challenger") if previous else "challenger"
        quarantine_until = int(previous.get("quarantine_until_cycle") or 0) if previous else 0

        if recovery:
            status = "recovery"
            bad_streak = 0
            quarantine_until = 0
        elif bad_streak >= RETIRE_BAD_STREAK and observations >= RETIRE_BAD_STREAK:
            status = "retired"
            quarantine_until = cycle + QUARANTINE_CYCLES
        elif bad_streak >= QUARANTINE_BAD_STREAK:
            status = "quarantined"
            quarantine_until = max(quarantine_until, cycle + QUARANTINE_CYCLES)
        elif status == "quarantined" and cycle < quarantine_until:
            status = "quarantined"
        elif status in {"quarantined", "retired"} and reward_lcb >= 0.05 and bad_streak == 0:
            status = "challenger"
            quarantine_until = 0
        elif status not in {"champion", "recovery"}:
            status = "challenger"

        current[action] = {
            "observations": min(1_000_000, observations),
            "verified_samples": min(1_000_000, effective_samples),
            "short_reward": round(_clamp_reward(short), 6),
            "long_reward": round(_clamp_reward(long), 6),
            "confidence": round(_clamp(conf), 6),
            "reward_lcb": round(reward_lcb, 6),
            "bad_streak": bad_streak,
            "status": status,
            "quarantine_until_cycle": min(10_000_000, quarantine_until),
            "last_seen_cycle": cycle,
        }

    current = dict(
        sorted(
            current.items(),
            key=lambda pair: (
                pair[1]["status"] == "retired",
                -int(pair[1]["observations"]),
                pair[0],
            ),
        )[:MAX_ACTIONS_PER_REGIME]
    )
    portfolios[regime] = current
    portfolios = dict(list(portfolios.items())[-MAX_REGIMES:])

    projected = deepcopy(state)
    projected["cycle"] = cycle
    projected["portfolios"] = portfolios
    return projected


def portfolio_policy(base: dict[str, Any], projected_state: dict[str, Any]) -> dict[str, Any]:
    regime = _current_regime(base)
    portfolio = projected_state.get("portfolios", {}).get(regime, {})
    upstream = base.get("v387_uncertainty_policy")
    upstream = upstream if isinstance(upstream, dict) else {}
    rows_by_action = {
        str(row.get("action_id") or ""): row
        for row in _v387_candidates(base)
        if str(row.get("action_id") or "")
    }

    ranked = []
    for action, metrics in portfolio.items():
        row = rows_by_action.get(action, {})
        multi = _finite(row.get("multi_objective_score"))
        multi = _clamp(multi if multi is not None else 0.5)
        reward_term = _clamp((float(metrics["long_reward"]) + 1.0) / 2.0)
        lcb_term = _clamp((float(metrics["reward_lcb"]) + 1.0) / 2.0)
        confidence = float(metrics["confidence"])
        status = str(metrics["status"])
        status_penalty = 0.0
        if status == "quarantined":
            status_penalty = 0.35
        elif status == "retired":
            status_penalty = 0.65
        score = (
            0.34 * multi
            + 0.25 * reward_term
            + 0.22 * lcb_term
            + 0.19 * confidence
            - status_penalty
        )
        ranked.append({
            "action_id": action,
            **deepcopy(metrics),
            "portfolio_score": round(_clamp(score), 6),
            "upstream_multi_objective_score": round(multi, 6),
            "recovery_action": _is_recovery(action),
        })

    ranked.sort(
        key=lambda row: (
            row["status"] in {"quarantined", "retired"},
            -float(row["portfolio_score"]),
            -int(row["verified_samples"]),
            row["action_id"],
        )
    )

    eligible = [
        row for row in ranked
        if row["status"] not in {"quarantined", "retired"}
        and int(row["observations"]) >= MIN_PORTFOLIO_OBSERVATIONS
    ]
    champion = eligible[0] if eligible else None
    if champion:
        portfolio[champion["action_id"]]["status"] = "recovery" if champion["recovery_action"] else "champion"
        for action, metrics in portfolio.items():
            if action != champion["action_id"] and metrics["status"] == "champion":
                metrics["status"] = "challenger"
        for row in ranked:
            if row["action_id"] == champion["action_id"]:
                row["status"] = portfolio[row["action_id"]]["status"]

    upstream_action = str(upstream.get("selected_action") or "") or None
    upstream_row = next((row for row in ranked if row["action_id"] == upstream_action), None)
    return {
        "regime": regime,
        "upstream_selected_action": upstream_action,
        "champion_action": champion.get("action_id") if champion else None,
        "champion_score": champion.get("portfolio_score") if champion else None,
        "upstream_portfolio_status": upstream_row.get("status") if upstream_row else None,
        "upstream_portfolio_score": upstream_row.get("portfolio_score") if upstream_row else None,
        "candidates": ranked,
        "market_direction_inferred": False,
    }


def resource_budget(base: dict[str, Any]) -> dict[str, Any]:
    kpis = base.get("v382_kpis")
    kpis = kpis if isinstance(kpis, dict) else {}
    dims = kpis.get("dimensions")
    dims = dims if isinstance(dims, dict) else {}
    headroom = _finite(dims.get("resource_headroom"))
    headroom = _clamp(headroom if headroom is not None else 0.5)

    drift = base.get("v382_drift")
    drift = drift if isinstance(drift, dict) else {}
    drift_score = _finite(drift.get("score"))
    drift_score = _clamp(drift_score if drift_score is not None else 0.5)

    uncertainty_policy = base.get("v387_uncertainty_policy")
    uncertainty_policy = uncertainty_policy if isinstance(uncertainty_policy, dict) else {}
    uncertainty = _finite(uncertainty_policy.get("selected_uncertainty"))
    uncertainty = _clamp(uncertainty if uncertainty is not None else 0.5)

    if headroom < RESOURCE_CRITICAL:
        state = "CRITICAL"
    elif headroom < RESOURCE_LOW:
        state = "LOW"
    else:
        state = "NORMAL"

    exploration = _clamp(0.04 + 0.16 * headroom + 0.10 * uncertainty, 0.0, 0.25)
    learning = _clamp(0.10 + 0.55 * headroom * (1.0 - drift_score), 0.0, 0.70)
    revalidation = _clamp(0.12 + 0.55 * uncertainty + 0.20 * drift_score, 0.0, 0.80)

    if state == "CRITICAL":
        exploration = 0.0
        learning = 0.0
        revalidation = max(revalidation, 0.55)
    elif state == "LOW":
        exploration = min(exploration, 0.04)
        learning = min(learning, 0.15)
    if drift_score >= HIGH_DRIFT:
        exploration = min(exploration, 0.03)
        learning = min(learning, 0.12)
        revalidation = max(revalidation, 0.55)

    return {
        "resource_state": state,
        "resource_headroom": round(headroom, 6),
        "drift_score": round(drift_score, 6),
        "selected_uncertainty": round(uncertainty, 6),
        "exploration_budget": round(exploration, 6),
        "learning_budget": round(learning, 6),
        "revalidation_budget": round(revalidation, 6),
        "exploration_is_advisory_only": True,
        "market_direction_inferred": False,
    }


def autonomous_gate(base: dict[str, Any], portfolio: dict[str, Any], budget: dict[str, Any]) -> dict[str, Any]:
    upstream = base.get("v387_autonomous_gate")
    upstream = upstream if isinstance(upstream, dict) else {}
    allow = upstream.get("allow_execution") is True
    reasons: list[str] = []
    if not allow:
        reasons.append(str(upstream.get("status") or "V387_UPSTREAM_HOLD"))

    selected = str(portfolio.get("upstream_selected_action") or "") or None
    selected_status = portfolio.get("upstream_portfolio_status")
    selected_score = _finite(portfolio.get("upstream_portfolio_score"))
    champion = portfolio.get("champion_action")
    champion_score = _finite(portfolio.get("champion_score"))
    recovery = _is_recovery(selected)

    if selected_status in {"quarantined", "retired"} and not recovery:
        allow = False
        reasons.append("VERIFIED_POLICY_REGRESSION")

    if (
        selected
        and champion
        and selected != champion
        and not recovery
        and selected_score is not None
        and champion_score is not None
        and champion_score - selected_score >= PORTFOLIO_DISAGREEMENT_MARGIN
    ):
        allow = False
        reasons.append("PORTFOLIO_CHAMPION_DISAGREEMENT")

    if budget.get("resource_state") == "CRITICAL" and not recovery:
        allow = False
        reasons.append("RESOURCE_CRITICAL")

    if "VERIFIED_POLICY_REGRESSION" in reasons:
        status = "V388_POLICY_QUARANTINE_HOLD"
    elif "PORTFOLIO_CHAMPION_DISAGREEMENT" in reasons:
        status = "V388_PORTFOLIO_DISAGREEMENT_HOLD"
    elif "RESOURCE_CRITICAL" in reasons:
        status = "V388_RESOURCE_CRITICAL_HOLD"
    elif not allow:
        status = "V388_UPSTREAM_HOLD"
    else:
        status = "V388_VERIFIED_ALLOW"

    return {
        "status": status,
        "allow_execution": allow,
        "selected_action": selected,
        "selected_portfolio_status": selected_status,
        "champion_action": champion,
        "reasons": reasons,
        "hard_blocker_override": False,
        "market_direction_inferred": False,
    }


def feature_backlog(base: dict[str, Any], state: dict[str, Any], budget: dict[str, Any]) -> list[dict[str, Any]]:
    rows = base.get("v387_feature_lifecycle")
    rows = rows if isinstance(rows, list) else []
    memory = state.get("feature_priorities")
    memory = memory if isinstance(memory, dict) else {}
    transition = (base.get("v387_uncertainty_policy") or {}).get("regime_transition") if isinstance(base.get("v387_uncertainty_policy"), dict) else {}
    stable = isinstance(transition, dict) and transition.get("level") == "STABLE"

    result = []
    for index, raw in enumerate(rows[:MAX_FEATURES]):
        if not isinstance(raw, dict):
            continue
        proposal_id = str(
            raw.get("v387_proposal_id")
            or raw.get("proposal_id")
            or raw.get("contract_id")
            or f"v388-feature-{index}"
        )[:180]
        prior = memory.get(proposal_id) if isinstance(memory.get(proposal_id), dict) else {}
        recurrence = min(1_000_000, int(prior.get("observations") or 0) + 1)
        conf = _finite(raw.get("v387_confidence"))
        conf = _clamp(conf if conf is not None else 0.0)
        status = str(raw.get("v387_status") or "shadow")
        lifecycle_weight = {
            "rolled_back": 0.10,
            "shadow": 0.30,
            "canary": 0.60,
            "active_candidate": 0.80,
        }.get(status, 0.25)
        recurrence_weight = _clamp(recurrence / 6.0)
        priority = _clamp(
            0.36 * conf
            + 0.26 * recurrence_weight
            + 0.22 * lifecycle_weight
            + 0.10 * (1.0 if stable else 0.35)
            + 0.06 * (1.0 - float(budget["revalidation_budget"]))
        )
        if status == "rolled_back":
            priority = min(priority, 0.22)

        if priority >= 0.72:
            band = "HIGH"
        elif priority >= 0.48:
            band = "MEDIUM"
        else:
            band = "LOW"

        result.append({
            **deepcopy(raw),
            "v388_proposal_id": proposal_id,
            "v388_priority_score": round(priority, 6),
            "v388_priority_band": band,
            "v388_recurrence": recurrence,
            "auto_execute": False,
            "auto_generate_source": False,
            "source_code_generated": False,
            "git_write": False,
            "protected_pr_ci_required": True,
            "promotion_requires": [
                "targeted_tests",
                "related_regression",
                "full_current_runtime",
                "repository_integrity",
                "tablet_gpt_alignment",
                "actual_output_validation",
            ],
            "self_extension_mode": "prioritized_non_executable_feature_contract",
        })

    result.sort(
        key=lambda row: (
            {"HIGH": 0, "MEDIUM": 1, "LOW": 2}[row["v388_priority_band"]],
            -float(row["v388_priority_score"]),
            row["v388_proposal_id"],
        )
    )
    return result


def _next_state(
    projected: dict[str, Any],
    portfolio: dict[str, Any],
    gate: dict[str, Any],
    backlog: list[dict[str, Any]],
    *,
    now: datetime,
) -> dict[str, Any]:
    nxt = deepcopy(projected)
    priorities = dict(nxt.get("feature_priorities") or {})
    cycle = int(nxt.get("cycle") or 0)

    for row in backlog:
        proposal_id = str(row.get("v388_proposal_id") or "")
        if not proposal_id:
            continue
        old = priorities.get(proposal_id) if isinstance(priorities.get(proposal_id), dict) else {}
        old_score = _finite(old.get("priority_ewma"))
        current = float(row["v388_priority_score"])
        blended = current if old_score is None else 0.25 * current + 0.75 * old_score
        priorities[proposal_id] = {
            "observations": min(1_000_000, int(old.get("observations") or 0) + 1),
            "priority_ewma": round(_clamp(blended), 6),
            "last_status": str(row.get("v387_status") or "shadow")[:48],
            "last_seen_cycle": cycle,
        }

    nxt["feature_priorities"] = dict(
        sorted(
            priorities.items(),
            key=lambda pair: (-float(pair[1]["priority_ewma"]), pair[0]),
        )[:MAX_FEATURES]
    )

    history = list(nxt.get("history") or [])
    history.append({
        "observed_at": now.isoformat(timespec="seconds"),
        "cycle": cycle,
        "regime": portfolio.get("regime"),
        "upstream_selected_action": portfolio.get("upstream_selected_action"),
        "champion_action": portfolio.get("champion_action"),
        "gate_status": gate.get("status"),
    })
    nxt["history"] = history[-MAX_HISTORY:]
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

    fd = None
    lock_info = {"status": "V388_LOCK_NOT_REQUIRED", "error_code": None}
    if mutating:
        fd, lock_info = v387.v386.v385._acquire_lock(root / LOCK_PATH.name)
        if fd is None:
            return {
                "controller_version": CONTROLLER_VERSION,
                "v388_status": "V388_CONCURRENT_AUTONOMY_HOLD",
                "execution": {
                    "status": "V388_CONCURRENT_AUTONOMY_HOLD",
                    "executed": False,
                    "git_write": False,
                    "source_code_modified": False,
                },
                "safety": SAFETY,
            }

    try:
        preview = v387.run_cycle(
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
        projected = update_portfolio(loaded["state"], preview)
        portfolio = portfolio_policy(preview, projected)
        budget = resource_budget(preview)
        gate = autonomous_gate(preview, portfolio, budget)

        if mutating and loaded.get("corruption_hold"):
            gate = {
                "status": "V388_STATE_CORRUPTION_HOLD",
                "allow_execution": False,
                "selected_action": portfolio.get("upstream_selected_action"),
                "selected_portfolio_status": portfolio.get("upstream_portfolio_status"),
                "champion_action": portfolio.get("champion_action"),
                "reasons": ["STATE_CORRUPTION_HOLD"],
                "hard_blocker_override": False,
                "market_direction_inferred": False,
            }

        base = preview
        if mutating and gate.get("allow_execution") is True:
            allow_optional = budget["resource_state"] == "NORMAL" and float(budget["drift_score"]) < HIGH_DRIFT
            base = v387.run_cycle(
                domain=domain,
                execute=execute,
                apply_capabilities=bool(apply_capabilities and allow_optional),
                train_meta=bool(train_meta and allow_optional and float(budget["learning_budget"]) >= 0.20),
                apply_skills=bool(apply_skills and allow_optional),
                root=root,
                now=moment,
                persist_outputs=False,
                **upstream_paths,
            )
            if str(base.get("v387_status") or "") in getattr(v387, "_HOLD_STATUSES", set()):
                gate = {
                    "status": "V388_UPSTREAM_HOLD",
                    "allow_execution": False,
                    "selected_action": portfolio.get("upstream_selected_action"),
                    "selected_portfolio_status": portfolio.get("upstream_portfolio_status"),
                    "champion_action": portfolio.get("champion_action"),
                    "reasons": [str(base.get("v387_status") or "V387_HOLD")],
                    "hard_blocker_override": False,
                    "market_direction_inferred": False,
                }

        backlog = feature_backlog(base, projected, budget)
        result = deepcopy(base)
        result.update({
            "core_controller_version": str(base.get("controller_version") or CORE_CONTROLLER_VERSION),
            "controller_version": CONTROLLER_VERSION,
            "v388_status": gate.get("status") if mutating else "PLAN_ONLY",
            "v388_policy_portfolio": portfolio,
            "v388_resource_budget": budget,
            "v388_autonomous_gate": gate,
            "v388_feature_backlog": backlog,
            "evolution_contract_v388": {
                "base_controller": "v387",
                "policy_memory": "verified_reward_regime_portfolio_only",
                "horizons": ["short_ewma", "long_ewma", "reward_lcb"],
                "policy_lifecycle": "challenger_champion_quarantine_retire_revalidate",
                "resource_budgeting": "headroom_drift_uncertainty_bounded",
                "exploration": "advisory_only_never_forces_execution",
                "market_adaptation": "operational_regime_kpi_drift_only_no_direction_prediction",
                "self_extension": "prioritized_non_executable_feature_contract",
                "source_level_activation": "protected_pr_ci_required",
                "v387_and_prior_gate_bypass": False,
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

        state_write = {"status": "V388_STATE_WRITE_NOT_REQUESTED", "written": False}
        if mutating:
            nxt = _next_state(projected, portfolio, gate, backlog, now=moment)
            state_write = save_state(nxt, state_file, bool(loaded.get("corruption_hold")))
            if not state_write.get("written") and gate.get("allow_execution") is True:
                result["v388_status"] = "V388_STATE_COMMIT_HOLD"
                result["execution"] = {
                    "status": "V388_STATE_COMMIT_HOLD",
                    "executed": False,
                    "git_write": False,
                    "source_code_modified": False,
                    "proposals_executed": False,
                }
        result["v388_state_write"] = state_write

        if persist_outputs:
            try:
                backlog_payload = {
                    "schema_version": 1,
                    "controller_version": CONTROLLER_VERSION,
                    "generated_at": moment.isoformat(timespec="seconds"),
                    "items": backlog,
                    "auto_execute": False,
                    "source_code_generation": False,
                    "protected_pr_ci_required": True,
                }
                atomic_write_json(root / FEATURE_BACKLOG_PATH.name, backlog_payload, suffix=".v388-backlog.tmp")
                atomic_write_json(root / REPORT_PATH.name, result, suffix=".v388-report.tmp")
                result["v388_runtime_output"] = {"status": "SAVED"}
            except (OSError, UnicodeError, ValueError, TypeError) as exc:
                result["v388_runtime_output"] = {
                    "status": "WRITE_FAILED",
                    "error_code": type(exc).__name__,
                }
        return result
    finally:
        if fd is not None:
            v387.v386.v385._release_lock(fd)


def self_test() -> None:
    state = _default_state()
    assert _valid_state(state)
    assert SAFETY["regime_conditioned_policy_portfolio"] is True
    assert SAFETY["verified_reward_memory_only"] is True
    assert SAFETY["resource_budget_autonomy"] is True
    assert SAFETY["feature_backlog_non_executable"] is True
    assert SAFETY["v387_gate_cannot_be_bypassed"] is True
    assert SAFETY["source_code_auto_generation"] is False
    assert SAFETY["arbitrary_command_execution"] is False
    assert SAFETY["git_write"] is False
    assert SAFETY["market_direction_inferred"] is False
    print("Tablet/TCG regime policy portfolio autonomy v388: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", choices=sorted(v387.v386.DOMAINS), default="tablet_gpt")
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
    return 2 if result.get("v388_status") in _HOLD_STATUSES else 0


if __name__ == "__main__":
    raise SystemExit(main())
