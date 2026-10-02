#!/usr/bin/env python3
"""V386: bidirectional verified neural co-evolution for Tablet GPT and TCG Grader.

V386 sits above V385. Each side exports only a bounded verified-outcome summary.
No model weights, raw grading data, calibration state, logs, secrets, retry queues,
or source internals are exchanged. A small mutual-consensus MLP is trained only
when both sides independently provide verified outcomes for the same action.

The peer layer can hold execution on strong disagreement, strengthen canary
confidence on repeated corroboration, and reprioritize non-executable feature
plans. It cannot bypass V385/V382/V381, generate source code, write Git/main,
execute arbitrary commands, invent facts/prices/grades, or infer market direction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tablet_autonomous_evolution_v385 as v385
from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
CONTROLLER_VERSION = "v386"
CORE_CONTROLLER_VERSION = "v385"

STATE_PATH = ROOT / ".tablet_autonomy_v386_state.json"
REPORT_PATH = ROOT / "tablet_autonomy_v386_report.json"
LOCK_PATH = ROOT / ".tablet_autonomy_execution_v386.lock"

SUMMARY_SCHEMA_VERSION = 1
STATE_SCHEMA_VERSION = 1
MAX_STATE_BYTES = 1_000_000
MAX_SUMMARY_BYTES = 300_000
MAX_PEER_AGE_HOURS = 48
MAX_CANDIDATES = 32
MAX_HISTORY = 128
INPUT_DIM = 8
HIDDEN_DIM = 6
TRAIN_STEPS = 20
BASE_LR = 0.03
MIN_VERIFIED_SAMPLES = max(3, int(getattr(v385, "MIN_VERIFIED_SAMPLES", 3)))
STRONG_DIVERGENCE = 0.42

DOMAINS = {"tablet_gpt", "tcg_grader"}
SUMMARY_FIELDS = {
    "schema_version", "domain", "generated_at", "controller_version", "kind",
    "regime", "kpi_score", "drift_score", "candidates", "safety",
}
CANDIDATE_FIELDS = {"action_id", "score", "verified_samples", "reward_mean"}
SAFETY_FIELDS = {
    "verified_outcomes_only", "raw_model_weights_shared", "raw_state_shared",
    "grading_raw_shared", "grading_calibration_shared", "git_write",
    "source_code_auto_generation", "market_direction_inferred",
}

_HOLD_STATUSES = set(getattr(v385, "_HOLD_STATUSES", set())) | {
    "V386_STATE_CORRUPTION_HOLD",
    "V386_LOCK_UNAVAILABLE",
    "V386_CONCURRENT_AUTONOMY_HOLD",
    "V386_PEER_DIVERGENCE_HOLD",
    "V386_STATE_COMMIT_HOLD",
}

SAFETY = dict(v385.SAFETY)
SAFETY.update({
    "bidirectional_verified_learning_summary": True,
    "peer_summary_strict_allowlist": True,
    "peer_model_weights_imported": False,
    "peer_raw_state_imported": False,
    "peer_grading_raw_imported": False,
    "peer_grading_calibration_imported": False,
    "mutual_consensus_neural_policy": True,
    "mutual_training_requires_matching_verified_outcomes": True,
    "peer_divergence_can_hold_execution": True,
    "peer_divergence_can_never_force_execution": True,
    "mutual_canary_corroboration_required": True,
    "source_feature_auto_generation": False,
    "source_feature_protected_pr_ci_required": True,
    "market_direction_inferred": False,
    "git_write": False,
    "direct_main_write": False,
    "source_code_auto_generation": False,
    "source_code_auto_rewrite": False,
    "arbitrary_command_execution": False,
    "verification_bypass": False,
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


def _stable_unit(text: str) -> float:
    raw = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(raw[:8], "big") / float((1 << 64) - 1)


def _sigmoid(value: float) -> float:
    value = max(-30.0, min(30.0, value))
    return 1.0 / (1.0 + math.exp(-value))


def _initial_network() -> dict[str, Any]:
    w1 = [
        [round((_stable_unit(f"v386:w1:{h}:{i}") - 0.5) * 0.10, 8) for i in range(INPUT_DIM)]
        for h in range(HIDDEN_DIM)
    ]
    return {
        "w1": w1,
        "b1": [0.0] * HIDDEN_DIM,
        "w2": [round((_stable_unit(f"v386:w2:{h}") - 0.5) * 0.10, 8) for h in range(HIDDEN_DIM)],
        "b2": 0.0,
        "updates": 0,
    }


def _valid_network(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if not isinstance(value.get("w1"), list) or len(value["w1"]) != HIDDEN_DIM:
        return False
    if not isinstance(value.get("b1"), list) or len(value["b1"]) != HIDDEN_DIM:
        return False
    if not isinstance(value.get("w2"), list) or len(value["w2"]) != HIDDEN_DIM:
        return False
    for row in value["w1"]:
        if not isinstance(row, list) or len(row) != INPUT_DIM:
            return False
        if any(_finite(x) is None or abs(float(x)) > 8 for x in row):
            return False
    if any(_finite(x) is None or abs(float(x)) > 8 for x in value["b1"] + value["w2"]):
        return False
    return (
        _finite(value.get("b2")) is not None
        and abs(float(value["b2"])) <= 8
        and isinstance(value.get("updates"), int)
        and 0 <= value["updates"] <= 1_000_000
    )


def _default_state() -> dict[str, Any]:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "controller_version": CONTROLLER_VERSION,
        "network": _initial_network(),
        "peer_corroboration": {},
        "history": [],
    }


def _validate_state(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if value.get("schema_version") != STATE_SCHEMA_VERSION or value.get("controller_version") != CONTROLLER_VERSION:
        return False
    if not _valid_network(value.get("network")):
        return False
    if not isinstance(value.get("peer_corroboration"), dict) or len(value["peer_corroboration"]) > 128:
        return False
    if not isinstance(value.get("history"), list) or len(value["history"]) > MAX_HISTORY:
        return False
    return True


def load_state(path: Path = STATE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"state": _default_state(), "status": "fresh", "corruption_hold": False}
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError("UNSAFE_V386_STATE_PATH")
        value = json.loads(safe_read_text(path, max_bytes=MAX_STATE_BYTES))
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return {"state": _default_state(), "status": "corrupt", "corruption_hold": True, "error_code": type(exc).__name__}
    if not _validate_state(value):
        return {"state": _default_state(), "status": "corrupt", "corruption_hold": True, "error_code": "V386_STATE_SCHEMA_INVALID"}
    return {"state": value, "status": "loaded", "corruption_hold": False}


def save_state(state: dict[str, Any], path: Path, corruption_hold: bool) -> dict[str, Any]:
    if corruption_hold:
        return {"status": "V386_STATE_CORRUPTION_HOLD", "written": False}
    if not _validate_state(state):
        return {"status": "V386_STATE_INVALID", "written": False}
    try:
        atomic_write_json(path, state, suffix=".v386-state.tmp")
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        return {"status": "V386_STATE_WRITE_FAILED", "written": False, "error_code": type(exc).__name__}
    return {"status": "V386_STATE_SAVED", "written": True}


def _policy_candidates(base: dict[str, Any]) -> list[dict[str, Any]]:
    policy = base.get("v385_verified_neural_policy")
    rows = policy.get("candidates") if isinstance(policy, dict) and isinstance(policy.get("candidates"), list) else []
    result = []
    for row in rows[:MAX_CANDIDATES]:
        if not isinstance(row, dict):
            continue
        action = str(row.get("action_id") or "")[:160]
        score = _finite(row.get("score"))
        samples = max(0, int(row.get("verified_samples") or 0))
        reward = _finite(row.get("reward_mean"))
        if not action or score is None:
            continue
        result.append({
            "action_id": action,
            "score": round(_clamp(score), 6),
            "verified_samples": samples,
            "reward_mean": round(max(-1.0, min(1.0, reward)), 6) if reward is not None else None,
        })
    return result


def build_summary(base: dict[str, Any], domain: str, *, now: datetime) -> dict[str, Any]:
    if domain not in DOMAINS:
        raise ValueError("V386_UNSUPPORTED_DOMAIN")
    kpi = base.get("v382_kpis") if isinstance(base.get("v382_kpis"), dict) else {}
    drift = base.get("v382_drift") if isinstance(base.get("v382_drift"), dict) else {}
    kpi_score = _finite(kpi.get("score"))
    drift_score = _finite(drift.get("score"))
    regime = str((base.get("v385_verified_neural_policy") or {}).get("regime") or "UNKNOWN")[:80]
    candidates = [
        row for row in _policy_candidates(base)
        if int(row["verified_samples"]) >= MIN_VERIFIED_SAMPLES and row["reward_mean"] is not None
    ]
    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "domain": domain,
        "generated_at": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "controller_version": CONTROLLER_VERSION,
        "kind": "verified_autonomy_outcome_summary",
        "regime": regime,
        "kpi_score": round(_clamp(kpi_score), 6) if kpi_score is not None else None,
        "drift_score": round(_clamp(drift_score), 6) if drift_score is not None else None,
        "candidates": candidates[:MAX_CANDIDATES],
        "safety": {
            "verified_outcomes_only": True,
            "raw_model_weights_shared": False,
            "raw_state_shared": False,
            "grading_raw_shared": False,
            "grading_calibration_shared": False,
            "git_write": False,
            "source_code_auto_generation": False,
            "market_direction_inferred": False,
        },
    }


def validate_summary(value: Any, expected_domain: str, *, now: datetime) -> dict[str, Any]:
    if expected_domain not in DOMAINS:
        raise ValueError("V386_UNSUPPORTED_DOMAIN")
    if not isinstance(value, dict) or set(value) != SUMMARY_FIELDS:
        raise ValueError("V386_PEER_SUMMARY_FIELDS_INVALID")
    if value.get("schema_version") != SUMMARY_SCHEMA_VERSION or value.get("domain") != expected_domain:
        raise ValueError("V386_PEER_SUMMARY_IDENTITY_INVALID")
    if value.get("kind") != "verified_autonomy_outcome_summary":
        raise ValueError("V386_PEER_SUMMARY_KIND_INVALID")
    try:
        generated = datetime.fromisoformat(str(value.get("generated_at")).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError("V386_PEER_SUMMARY_TIME_INVALID") from exc
    if generated.tzinfo is None:
        raise ValueError("V386_PEER_SUMMARY_TIME_NAIVE")
    age_hours = (now.astimezone(timezone.utc) - generated.astimezone(timezone.utc)).total_seconds() / 3600.0
    if age_hours < -0.25 or age_hours > MAX_PEER_AGE_HOURS:
        raise ValueError("V386_PEER_SUMMARY_STALE")
    if not isinstance(value.get("candidates"), list) or len(value["candidates"]) > MAX_CANDIDATES:
        raise ValueError("V386_PEER_CANDIDATES_INVALID")
    for row in value["candidates"]:
        if not isinstance(row, dict) or set(row) != CANDIDATE_FIELDS:
            raise ValueError("V386_PEER_CANDIDATE_FIELDS_INVALID")
        if not isinstance(row.get("action_id"), str) or not row["action_id"] or len(row["action_id"]) > 160:
            raise ValueError("V386_PEER_ACTION_INVALID")
        score, reward = _finite(row.get("score")), _finite(row.get("reward_mean"))
        samples = row.get("verified_samples")
        if score is None or not 0 <= score <= 1 or reward is None or not -1 <= reward <= 1:
            raise ValueError("V386_PEER_METRIC_INVALID")
        if not isinstance(samples, int) or samples < MIN_VERIFIED_SAMPLES or samples > 1_000_000:
            raise ValueError("V386_PEER_SAMPLES_INVALID")
    safety = value.get("safety")
    if not isinstance(safety, dict) or set(safety) != SAFETY_FIELDS:
        raise ValueError("V386_PEER_SAFETY_FIELDS_INVALID")
    if safety.get("verified_outcomes_only") is not True:
        raise ValueError("V386_PEER_NOT_VERIFIED_ONLY")
    for key in SAFETY_FIELDS - {"verified_outcomes_only"}:
        if safety.get(key) is not False:
            raise ValueError("V386_PEER_SAFETY_BOUNDARY_INVALID")
    return value


def load_peer_summary(path: Path, expected_domain: str, *, now: datetime) -> dict[str, Any]:
    if not path.exists():
        return {"usable": False, "status": "PEER_SUMMARY_MISSING", "summary": None}
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError("V386_UNSAFE_PEER_PATH")
        value = json.loads(safe_read_text(path, max_bytes=MAX_SUMMARY_BYTES))
        valid = validate_summary(value, expected_domain, now=now)
        return {"usable": True, "status": "PEER_SUMMARY_VERIFIED", "summary": valid}
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return {"usable": False, "status": "PEER_SUMMARY_REJECTED", "summary": None, "error_code": str(exc)[:120]}


def _forward(network: dict[str, Any], vector: list[float]) -> tuple[list[float], float]:
    hidden = []
    for h in range(HIDDEN_DIM):
        total = float(network["b1"][h]) + sum(float(w) * float(x) for w, x in zip(network["w1"][h], vector))
        hidden.append(math.tanh(max(-20.0, min(20.0, total))))
    output = float(network["b2"]) + sum(float(w) * x for w, x in zip(network["w2"], hidden))
    return hidden, _sigmoid(output)


def _pair_vector(local: dict[str, Any], peer: dict[str, Any], base: dict[str, Any], regime_match: bool) -> list[float]:
    kpi = _finite((base.get("v382_kpis") or {}).get("score")) if isinstance(base.get("v382_kpis"), dict) else None
    drift = _finite((base.get("v382_drift") or {}).get("score")) if isinstance(base.get("v382_drift"), dict) else None
    local_reward = float(local["reward_mean"])
    peer_reward = float(peer["reward_mean"])
    agreement = 1.0 - min(1.0, abs(local_reward - peer_reward) / 2.0)
    return [
        float(local["score"]),
        float(peer["score"]),
        _clamp(int(local["verified_samples"]) / float(MIN_VERIFIED_SAMPLES * 6)),
        _clamp(int(peer["verified_samples"]) / float(MIN_VERIFIED_SAMPLES * 6)),
        _clamp(kpi if kpi is not None else 0.5),
        _clamp(1.0 - (drift if drift is not None else 0.5)),
        1.0 if regime_match else 0.0,
        agreement,
    ]


def train_mutual_network(network: dict[str, Any], base: dict[str, Any], peer_summary: dict[str, Any] | None) -> dict[str, Any]:
    model = deepcopy(network)
    if not peer_summary:
        return {"network": model, "trained": False, "examples": 0, "loss": None}
    peer_by_action = {row["action_id"]: row for row in peer_summary["candidates"]}
    local_rows = [
        row for row in _policy_candidates(base)
        if row["verified_samples"] >= MIN_VERIFIED_SAMPLES and row["reward_mean"] is not None
    ]
    examples = []
    local_regime = str((base.get("v385_verified_neural_policy") or {}).get("regime") or "UNKNOWN")
    regime_match = local_regime == str(peer_summary.get("regime") or "UNKNOWN")
    for local in local_rows:
        peer = peer_by_action.get(local["action_id"])
        if not peer:
            continue
        target = _clamp(((float(local["reward_mean"]) + float(peer["reward_mean"])) / 2.0 + 1.0) / 2.0)
        examples.append((_pair_vector(local, peer, base, regime_match), target))
    if not examples:
        return {"network": model, "trained": False, "examples": 0, "loss": None}

    losses = []
    steps = min(TRAIN_STEPS, max(4, len(examples) * 5))
    for step in range(steps):
        vector, target = examples[step % len(examples)]
        hidden, pred = _forward(model, vector)
        err = pred - target
        losses.append(err * err)
        grad = 2.0 * err * pred * (1.0 - pred)
        old_w2 = [float(x) for x in model["w2"]]
        for h in range(HIDDEN_DIM):
            model["w2"][h] = round(max(-4.0, min(4.0, float(model["w2"][h]) - BASE_LR * grad * hidden[h])), 8)
        model["b2"] = round(max(-4.0, min(4.0, float(model["b2"]) - BASE_LR * grad)), 8)
        for h in range(HIDDEN_DIM):
            hidden_grad = grad * old_w2[h] * (1.0 - hidden[h] * hidden[h])
            for i in range(INPUT_DIM):
                model["w1"][h][i] = round(max(-4.0, min(4.0, float(model["w1"][h][i]) - BASE_LR * hidden_grad * vector[i])), 8)
            model["b1"][h] = round(max(-4.0, min(4.0, float(model["b1"][h]) - BASE_LR * hidden_grad)), 8)
    model["updates"] = int(model.get("updates") or 0) + steps
    return {
        "network": model,
        "trained": True,
        "examples": len(examples),
        "steps": steps,
        "loss": round(sum(losses) / len(losses), 8),
    }


def mutual_policy(network: dict[str, Any], base: dict[str, Any], peer_summary: dict[str, Any] | None) -> dict[str, Any]:
    local_rows = _policy_candidates(base)
    peer_by_action = {row["action_id"]: row for row in peer_summary["candidates"]} if peer_summary else {}
    local_regime = str((base.get("v385_verified_neural_policy") or {}).get("regime") or "UNKNOWN")
    peer_regime = str(peer_summary.get("regime") or "UNKNOWN") if peer_summary else None
    rows = []
    max_reward_gap = 0.0
    for local in local_rows:
        peer = peer_by_action.get(local["action_id"])
        if peer and local["reward_mean"] is not None:
            vector = _pair_vector(local, peer, base, local_regime == peer_regime)
            _, neural = _forward(network, vector)
            peer_score = float(peer["score"])
            score = 0.50 * float(local["score"]) + 0.30 * peer_score + 0.20 * neural
            reward_gap = abs(float(local["reward_mean"]) - float(peer["reward_mean"]))
            max_reward_gap = max(max_reward_gap, reward_gap)
            peer_samples = int(peer["verified_samples"])
        else:
            neural = None
            peer_score = None
            peer_samples = 0
            score = float(local["score"]) * 0.92
            reward_gap = None
        rows.append({
            "action_id": local["action_id"],
            "score": round(_clamp(score), 6),
            "local_score": local["score"],
            "peer_score": round(peer_score, 6) if peer_score is not None else None,
            "mutual_neural_score": round(neural, 6) if neural is not None else None,
            "local_verified_samples": int(local["verified_samples"]),
            "peer_verified_samples": peer_samples,
            "reward_gap": round(reward_gap, 6) if reward_gap is not None else None,
        })
    rows.sort(key=lambda row: (-row["score"], -row["local_verified_samples"], row["action_id"]))
    local_top = local_rows[0]["action_id"] if local_rows else None
    mutual_top = rows[0]["action_id"] if rows else None
    strong = bool(
        peer_summary
        and (
            max_reward_gap >= STRONG_DIVERGENCE
            or (
                local_top and mutual_top and local_top != mutual_top
                and rows[0]["peer_verified_samples"] >= MIN_VERIFIED_SAMPLES * 2
                and rows[0]["score"] >= 0.62
            )
        )
    )
    return {
        "peer_available": bool(peer_summary),
        "local_regime": local_regime,
        "peer_regime": peer_regime,
        "candidates": rows,
        "selected_action": mutual_top,
        "strong_divergence": strong,
        "max_reward_gap": round(max_reward_gap, 6),
        "market_direction_inferred": False,
    }


def mutual_gate(base: dict[str, Any], policy: dict[str, Any], peer_status: dict[str, Any]) -> dict[str, Any]:
    upstream = base.get("v385_autonomous_gate") if isinstance(base.get("v385_autonomous_gate"), dict) else {}
    allow = upstream.get("allow_execution") is True
    reasons = []
    if not allow:
        reasons.append(str(upstream.get("status") or "V385_UPSTREAM_HOLD"))
    if peer_status.get("usable") and policy.get("strong_divergence") is True:
        reasons.append("VERIFIED_PEER_DIVERGENCE")
        allow = False
    if "VERIFIED_PEER_DIVERGENCE" in reasons:
        status = "V386_PEER_DIVERGENCE_HOLD"
    elif not peer_status.get("usable"):
        status = "V386_LOCAL_ONLY_ALLOW" if allow else "V386_LOCAL_ONLY_HOLD"
    else:
        status = "V386_MUTUAL_ALLOW" if allow else "V386_UPSTREAM_HOLD"
    return {
        "status": status,
        "allow_execution": allow,
        "reasons": reasons,
        "peer_status": peer_status.get("status"),
        "hard_blocker_override": False,
        "market_direction_inferred": False,
    }


def function_plan(base: dict[str, Any], policy: dict[str, Any]) -> list[dict[str, Any]]:
    plans = base.get("v385_source_feature_plan") if isinstance(base.get("v385_source_feature_plan"), list) else []
    peer_actions = {
        row["action_id"] for row in policy.get("candidates", [])
        if int(row.get("peer_verified_samples") or 0) >= MIN_VERIFIED_SAMPLES
    }
    result = []
    for row in plans[:32]:
        if not isinstance(row, dict):
            continue
        item = deepcopy(row)
        item["mutual_verified_peer_evidence"] = bool(peer_actions)
        item["auto_execute"] = False
        item["auto_generate_source"] = False
        item["git_write"] = False
        item["protected_pr_ci_required"] = True
        item["required_promotion_gates"] = [
            "targeted_tests", "related_regression", "full_current_runtime",
            "repository_integrity", "tablet_gpt_alignment", "actual_output_validation",
        ]
        result.append(item)
    return result


def _next_state(state: dict[str, Any], training: dict[str, Any], policy: dict[str, Any], gate: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    nxt = deepcopy(state)
    nxt["network"] = deepcopy(training["network"])
    corr = dict(nxt.get("peer_corroboration") or {})
    for row in policy.get("candidates", []):
        action = str(row.get("action_id") or "")
        if action and int(row.get("peer_verified_samples") or 0) >= MIN_VERIFIED_SAMPLES and (row.get("reward_gap") is not None and float(row["reward_gap"]) < 0.25):
            corr[action] = min(9999, int(corr.get(action) or 0) + 1)
    nxt["peer_corroboration"] = dict(sorted(corr.items(), key=lambda p: (-p[1], p[0]))[:128])
    history = list(nxt.get("history") or [])
    history.append({
        "observed_at": now.isoformat(timespec="seconds"),
        "gate_status": gate.get("status"),
        "peer_available": bool(policy.get("peer_available")),
        "selected_action": policy.get("selected_action"),
        "strong_divergence": bool(policy.get("strong_divergence")),
        "network_updates": int(training["network"].get("updates") or 0),
    })
    nxt["history"] = history[-MAX_HISTORY:]
    return nxt


def _paths_for_domain(root: Path, domain: str) -> tuple[Path, Path, str]:
    if domain == "tablet_gpt":
        return (
            root / "crosscheck_exchange" / "tablet-gpt-autonomy-summary.json",
            root / "crosscheck_exchange" / "tcg-grader-autonomy-summary.json",
            "tcg_grader",
        )
    if domain == "tcg_grader":
        return (
            root / "crosscheck_exchange" / "tcg-grader-autonomy-summary.json",
            root / "crosscheck_exchange" / "tablet-gpt-autonomy-summary.json",
            "tablet_gpt",
        )
    raise ValueError("V386_UNSUPPORTED_DOMAIN")


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
    peer_summary_path: Path | None = None,
    local_summary_path: Path | None = None,
    persist_outputs: bool = True,
    **upstream_paths: Any,
) -> dict[str, Any]:
    moment = (now or _now()).astimezone(timezone.utc)
    mutating = bool(execute or apply_capabilities or train_meta or apply_skills)
    state_file = state_path or (root / STATE_PATH.name)
    default_local, default_peer, peer_domain = _paths_for_domain(root, domain)
    local_path = local_summary_path or default_local
    peer_path = peer_summary_path or default_peer

    fd = None
    lock_info = {"status": "V386_LOCK_NOT_REQUIRED", "error_code": None}
    if mutating:
        fd, lock_info = v385._acquire_lock(root / LOCK_PATH.name)
        if fd is None:
            return {
                "controller_version": CONTROLLER_VERSION,
                "v386_status": lock_info["status"],
                "execution": {"status": lock_info["status"], "executed": False, "git_write": False, "source_code_modified": False},
                "safety": SAFETY,
            }

    try:
        preview_kwargs = dict(upstream_paths)
        preview_kwargs.update({"root": root, "now": moment, "persist_outputs": False})
        preview = v385.run_cycle(
            execute=False, apply_capabilities=False, train_meta=False, apply_skills=False,
            **preview_kwargs,
        )
        loaded = load_state(state_file)
        peer_status = load_peer_summary(peer_path, peer_domain, now=moment)
        peer = peer_status.get("summary") if peer_status.get("usable") else None
        training = train_mutual_network(loaded["state"]["network"], preview, peer)
        policy = mutual_policy(training["network"], preview, peer)
        gate = mutual_gate(preview, policy, peer_status)

        if mutating and loaded.get("corruption_hold"):
            gate = {
                "status": "V386_STATE_CORRUPTION_HOLD",
                "allow_execution": False,
                "reasons": ["STATE_CORRUPTION_HOLD"],
                "peer_status": peer_status.get("status"),
                "hard_blocker_override": False,
                "market_direction_inferred": False,
            }

        base = preview
        if mutating and gate.get("allow_execution") is True:
            base = v385.run_cycle(
                execute=execute,
                apply_capabilities=apply_capabilities,
                train_meta=train_meta,
                apply_skills=apply_skills,
                **preview_kwargs,
            )
            if str(base.get("v385_status") or "") in getattr(v385, "_HOLD_STATUSES", set()):
                gate = {
                    "status": "V386_UPSTREAM_HOLD",
                    "allow_execution": False,
                    "reasons": [str(base.get("v385_status") or "V385_HOLD")],
                    "peer_status": peer_status.get("status"),
                    "hard_blocker_override": False,
                    "market_direction_inferred": False,
                }

        local_summary = build_summary(base, domain, now=moment)
        plans = function_plan(base, policy)
        result = deepcopy(base)
        result.update({
            "core_controller_version": str(base.get("controller_version") or CORE_CONTROLLER_VERSION),
            "controller_version": CONTROLLER_VERSION,
            "v386_status": gate.get("status") if mutating else "PLAN_ONLY",
            "v386_peer_exchange": {
                "domain": domain,
                "peer_domain": peer_domain,
                "peer_status": peer_status,
                "raw_model_weights_shared": False,
                "raw_state_shared": False,
            },
            "v386_mutual_neural_policy": {
                **policy,
                "trained_this_cycle": bool(training.get("trained")),
                "training_examples": int(training.get("examples") or 0),
                "training_loss": training.get("loss"),
                "training_requires_matching_verified_outcomes": True,
                "network": f"{INPUT_DIM}x{HIDDEN_DIM}x1_mutual_consensus_mlp",
            },
            "v386_autonomous_gate": gate,
            "v386_function_plan": plans,
            "evolution_contract_v386": {
                "base_controller": "v385",
                "mutual_exchange": "strict_verified_outcome_summary_only",
                "peer_model_weights_imported": False,
                "peer_raw_state_imported": False,
                "mutual_neural_training": "matching_verified_actions_only",
                "market_adaptation": "operational_regime_kpi_drift_only_no_direction_prediction",
                "self_extension": "existing_allowlisted_recipe_plus_non_executable_protected_pr_plan",
                "peer_disagreement": "hold_and_reverify_never_force_execution",
                "v385_v382_v381_bypass": False,
                "git_write": False,
                "source_code_auto_generation": False,
                "arbitrary_command_execution": False,
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

        state_write = {"status": "V386_STATE_WRITE_NOT_REQUESTED", "written": False}
        if mutating:
            nxt = _next_state(loaded["state"], training, policy, gate, now=moment)
            state_write = save_state(nxt, state_file, bool(loaded.get("corruption_hold")))
            if not state_write.get("written") and gate.get("allow_execution") is True:
                result["v386_status"] = "V386_STATE_COMMIT_HOLD"
                result["execution"] = {
                    "status": "V386_STATE_COMMIT_HOLD",
                    "executed": False,
                    "git_write": False,
                    "source_code_modified": False,
                    "proposals_executed": False,
                }
        result["v386_state_write"] = state_write

        if persist_outputs:
            try:
                local_path.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_json(local_path, local_summary, suffix=".v386-summary.tmp")
                atomic_write_json(root / REPORT_PATH.name, result, suffix=".v386-report.tmp")
                result["v386_runtime_output"] = {"status": "SAVED", "summary_path": str(local_path)}
            except (OSError, UnicodeError, ValueError, TypeError) as exc:
                result["v386_runtime_output"] = {"status": "WRITE_FAILED", "error_code": type(exc).__name__}
        return result
    finally:
        if fd is not None:
            v385._release_lock(fd)


def self_test() -> None:
    assert _valid_network(_initial_network())
    assert SAFETY["bidirectional_verified_learning_summary"] is True
    assert SAFETY["peer_model_weights_imported"] is False
    assert SAFETY["source_code_auto_generation"] is False
    assert SAFETY["git_write"] is False
    assert SAFETY["market_direction_inferred"] is False
    print("Tablet/TCG mutual neural co-evolution v386: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", choices=sorted(DOMAINS), default="tablet_gpt")
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
    return 2 if result.get("v386_status") in _HOLD_STATUSES else 0


if __name__ == "__main__":
    raise SystemExit(main())
