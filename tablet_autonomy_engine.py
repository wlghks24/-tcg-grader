#!/usr/bin/env python3
"""Bounded autonomous Tablet GPT controller for TCG Grader.

This controller may observe verified runtime/market/learning state, choose among
code-defined maintenance actions, train verified local priority models, and emit
non-executable capability proposals. It cannot create market facts, grant trust,
skip mandatory collectors, rewrite source code, push Git, or bypass verification.

Executable feature changes always remain PR + regression + protected-main work.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from safe_runtime import atomic_write_json, safe_read_text
import verified_autonomy_neural
import verified_collection_job_neural
import verified_collection_neural
import verified_neural_self_refine

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "TABLET_AUTONOMY_STATE.json"
PROPOSALS_PATH = ROOT / "TABLET_AUTONOMY_PROPOSALS.json"
REPORT_PATH = ROOT / "TABLET_AUTONOMY_REPORT.json"

SCHEMA = 1
MAX_SELECTED_ACTIONS = 3
MAX_MARKET_PRIORITY_BOOST = 0.15
MAX_EXPLORATION_PRIORITY_BOOST = 0.10
MARKET_JOB_KEYS = frozenset({
    "market_watch.json", "market_prices.json", "exchange_rates.json",
    "purchase_sources.json", "grading_company_updates.json",
})
EXPLORATION_JOB_KEYS = frozenset({"__integration__", "__link_audit__", "promo_events.json"})
ACTIONS = verified_autonomy_neural.ACTIONS

SAFETY = {
    "deterministic_guards_authoritative": True,
    "mandatory_collectors_preserved": True,
    "verified_learning_only": True,
    "unverified_learning_forbidden": True,
    "market_facts_generated": False,
    "official_trust_auto_promotion": False,
    "candidate_database_auto_promotion": False,
    "source_code_auto_rewrite": False,
    "git_write": False,
    "verification_bypass": False,
    "new_executable_capability_requires_pr": True,
    "capability_proposals_are_non_executable": True,
    "max_market_priority_boost": MAX_MARKET_PRIORITY_BOOST,
    "max_exploration_priority_boost": MAX_EXPLORATION_PRIORITY_BOOST,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clip01(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return max(0.0, min(1.0, number))


def _read_json(path: Path, fallback: Any) -> Any:
    try:
        value = json.loads(safe_read_text(path, max_bytes=8_000_000))
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return fallback
    return value


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError):
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def _age_score(value: Any, *, fresh_hours: float = 2.0, stale_hours: float = 72.0,
               now: datetime | None = None) -> float:
    stamp = _parse_time(value)
    if stamp is None:
        return 1.0
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    seconds = (moment - stamp).total_seconds()
    if seconds < -300:
        return 1.0
    hours = max(0.0, seconds / 3600.0)
    if hours <= fresh_hours:
        return 0.0
    if hours >= stale_hours:
        return 1.0
    return _clip01((hours - fresh_hours) / max(0.001, stale_hours - fresh_hours))


def _updated_at(data: Any) -> Any:
    if not isinstance(data, dict):
        return None
    for key in ("updated_at", "generated_at", "finished_at", "checked_at", "collected_at"):
        if data.get(key):
            return data.get(key)
    return None


_CHANGE_KEYS = (
    "change_pct", "change_percent", "change_percentage", "pct_change", "percent_change",
    "price_change_pct", "rise_pct", "fall_pct", "weekly_change_pct", "daily_change_pct",
)


def _walk_market_changes(value: Any, *, depth: int = 0, out: list[float] | None = None) -> list[float]:
    out = [] if out is None else out
    if depth > 5 or len(out) >= 250:
        return out
    if isinstance(value, dict):
        for key, child in list(value.items())[:300]:
            low = str(key).casefold()
            if any(marker in low for marker in _CHANGE_KEYS):
                try:
                    number = abs(float(child))
                except (TypeError, ValueError, OverflowError):
                    number = 0.0
                if math.isfinite(number):
                    out.append(number if number <= 1.0 else number / 100.0)
            elif isinstance(child, (dict, list)):
                _walk_market_changes(child, depth=depth + 1, out=out)
    elif isinstance(value, list):
        for child in value[:300]:
            if isinstance(child, (dict, list)):
                _walk_market_changes(child, depth=depth + 1, out=out)
    return out


def _contains_provenance(value: Any, *, depth: int = 0) -> bool:
    if depth > 4:
        return False
    if isinstance(value, dict):
        for key, child in list(value.items())[:300]:
            low = str(key).casefold()
            if low in {"source", "sources", "provenance", "source_url", "source_route"} and child:
                return True
            if isinstance(child, (dict, list)) and _contains_provenance(child, depth=depth + 1):
                return True
    elif isinstance(value, list):
        return any(_contains_provenance(child, depth=depth + 1) for child in value[:300])
    return False


def _market_uncertainty(payloads: list[Any]) -> float:
    uncertainty = 0.0
    for data in payloads:
        if not isinstance(data, dict):
            uncertainty += 0.35
            continue
        if not _contains_provenance(data):
            uncertainty += 0.15
        if _updated_at(data) is None:
            uncertainty += 0.15
    return _clip01(uncertainty)


def _model_gap(status: dict[str, Any]) -> float:
    minimum = status.get("minimum_labels")
    remaining = status.get("labels_remaining")
    try:
        minimum_f = max(1.0, float(minimum))
        return _clip01(float(remaining) / minimum_f)
    except (TypeError, ValueError, OverflowError):
        return 1.0


def _provider_error_rate(adaptive: Any, issues: Any) -> float:
    failures = runs = 0.0
    if isinstance(adaptive, dict):
        jobs = adaptive.get("jobs") if isinstance(adaptive.get("jobs"), dict) else {}
        for row in list(jobs.values())[:64]:
            if not isinstance(row, dict):
                continue
            try:
                runs += max(0.0, float(row.get("runs", 0) or 0))
                failures += max(0.0, float(row.get("failures", 0) or 0))
            except (TypeError, ValueError, OverflowError):
                continue
    ratio = failures / max(1.0, runs)
    if isinstance(issues, dict):
        try:
            ratio = max(ratio, min(1.0, float(issues.get("issue_count", 0) or 0) / 20.0))
        except (TypeError, ValueError, OverflowError):
            pass
    return _clip01(ratio)


def _coverage_gap(source_stats: Any) -> float:
    if not isinstance(source_stats, dict):
        return 0.5
    candidates = []
    for key in ("coverage_gap", "missing_ratio", "uncovered_ratio", "gap_ratio"):
        if key in source_stats:
            candidates.append(_clip01(source_stats.get(key)))
    if candidates:
        return max(candidates)
    return 0.25


def _load_latest_sync_contract(root: Path) -> dict[str, Any]:
    crosscheck = root / "TCG_CROSSCHECK"
    candidates: list[tuple[int, Path]] = []
    try:
        for path in crosscheck.glob("TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V*.json"):
            suffix = path.stem.rsplit("_V", 1)[-1]
            if suffix.isdigit():
                candidates.append((int(suffix), path))
    except OSError:
        candidates = []
    for _version, path in sorted(candidates, reverse=True):
        value = _read_json(path, {})
        if isinstance(value, dict) and value:
            return value
    fallback = _read_json(crosscheck / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT.json", {})
    return fallback if isinstance(fallback, dict) else {}


def _sync_risk(contract: Any) -> float:
    if not isinstance(contract, dict):
        return 1.0
    status = str(contract.get("status") or contract.get("sync_status") or "").casefold()
    if any(token in status for token in ("stale", "conflict", "hold", "failed", "blocked")):
        return 1.0
    if contract.get("learning_digest") or contract.get("delta_snapshot") or contract.get("receiver_receipt"):
        return 0.0
    return 0.35


def collect_signals(root: Path = ROOT, *, now: datetime | None = None) -> dict[str, float]:
    market_watch = _read_json(root / "market_watch.json", {})
    market_prices = _read_json(root / "market_prices.json", {})
    exchange_rates = _read_json(root / "exchange_rates.json", {})
    adaptive = _read_json(root / "adaptive_collection_stats.json", {})
    source_stats = _read_json(root / "source_collection_stats.json", {})
    issues = _read_json(root / "auto_update_issues.json", {})
    sync_contract = _load_latest_sync_contract(root)

    query_status = verified_collection_neural.status()
    job_status = verified_collection_job_neural.status()

    market_payloads = [market_watch, market_prices, exchange_rates]
    staleness = max(_age_score(_updated_at(data), now=now) for data in market_payloads)
    changes = []
    for payload in (market_watch, market_prices):
        changes.extend(_walk_market_changes(payload))
    market_shift = _clip01(max(changes, default=0.0) / 0.25)
    provider_error = _provider_error_rate(adaptive, issues)
    query_gap = _model_gap(query_status)
    job_gap = _model_gap(job_status)
    try:
        issue_count = max(0.0, float(issues.get("issue_count", 0) or 0)) if isinstance(issues, dict) else 0.0
    except (TypeError, ValueError, OverflowError):
        issue_count = 0.0
    repair_pressure = _clip01(issue_count / 12.0)
    coverage = _coverage_gap(source_stats)
    sync_risk = _sync_risk(sync_contract)
    uncertainty = _market_uncertainty(market_payloads)
    learning_backlog = _clip01((query_gap + job_gap) / 2.0)

    return {
        "data_staleness": round(staleness, 6),
        "market_shift": round(market_shift, 6),
        "coverage_gap": round(coverage, 6),
        "provider_error_rate": round(provider_error, 6),
        "query_model_gap": round(query_gap, 6),
        "job_model_gap": round(job_gap, 6),
        "repair_pressure": round(repair_pressure, 6),
        "tablet_sync_risk": round(sync_risk, 6),
        "learning_backlog": round(learning_backlog, 6),
        "market_uncertainty": round(uncertainty, 6),
    }


def _heuristic_scores(signals: dict[str, float]) -> dict[str, float]:
    s = {key: _clip01(signals.get(key)) for key in verified_autonomy_neural.NUMERIC_FEATURES}
    query_ready = 1.0 - s["query_model_gap"]
    job_ready = 1.0 - s["job_model_gap"]
    return {
        "refresh_market_data": _clip01(0.55 * s["data_staleness"] + 0.30 * s["market_uncertainty"] + 0.15 * s["market_shift"]),
        "increase_source_exploration": _clip01(0.35 * s["coverage_gap"] + 0.25 * s["provider_error_rate"] + 0.25 * s["market_shift"] + 0.15 * s["market_uncertainty"]),
        "retrain_query_neural": _clip01(0.70 * query_ready + 0.20 * s["learning_backlog"] + 0.10 * s["coverage_gap"]),
        "retrain_job_neural": _clip01(0.70 * job_ready + 0.20 * s["learning_backlog"] + 0.10 * s["provider_error_rate"]),
        "run_selfrefine_audit": _clip01(0.70 * s["repair_pressure"] + 0.20 * s["tablet_sync_risk"] + 0.10 * s["provider_error_rate"]),
        "rebalance_market_priority": _clip01(0.65 * s["market_shift"] + 0.20 * s["data_staleness"] + 0.15 * s["market_uncertainty"]),
        "propose_capability": _clip01(0.30 * s["coverage_gap"] + 0.20 * s["provider_error_rate"] + 0.20 * s["tablet_sync_risk"] + 0.20 * s["repair_pressure"] + 0.10 * s["market_uncertainty"]),
    }


def decide(signals: dict[str, float], *, model_path: Path = verified_autonomy_neural.MODEL_PATH) -> dict[str, Any]:
    fixed = _heuristic_scores(signals)
    rows = []
    for action in ACTIONS:
        neural = verified_autonomy_neural.score_action(action, signals, model_path=model_path)
        if neural.get("active") is True:
            combined = 0.75 * fixed[action] + 0.25 * _clip01(neural.get("score"))
            neural_used = True
        else:
            combined = fixed[action]
            neural_used = False
        rows.append({
            "action": action,
            "score": round(_clip01(combined), 6),
            "heuristic_score": round(fixed[action], 6),
            "neural_used": neural_used,
            "neural_score": neural.get("score"),
            "neural_reason": neural.get("reason"),
        })
    rows.sort(key=lambda row: (-row["score"], row["action"]))
    selected = [row for row in rows if row["score"] >= 0.45][:MAX_SELECTED_ACTIONS]
    return {
        "selected_actions": selected,
        "all_actions": rows,
        "max_selected_actions": MAX_SELECTED_ACTIONS,
        "bounded": True,
        "safety": SAFETY,
    }


def _capability_proposals(signals: dict[str, float]) -> list[dict[str, Any]]:
    proposals = []
    if signals.get("coverage_gap", 0.0) >= 0.45 or signals.get("market_uncertainty", 0.0) >= 0.45:
        proposals.append({
            "id": "market-source-diversification",
            "reason": "coverage_or_market_provenance_gap",
            "implementation_mode": "pr_required",
            "executable": False,
            "required_gates": ["official/provenance review", "targeted tests", "full regression", "protected-main PR"],
        })
    if signals.get("tablet_sync_risk", 0.0) >= 0.45:
        proposals.append({
            "id": "tablet-sync-recovery-hardening",
            "reason": "tablet_sync_risk",
            "implementation_mode": "pr_required",
            "executable": False,
            "required_gates": ["fresh contract", "receipt verification", "tablet alignment regression", "protected-main PR"],
        })
    if signals.get("repair_pressure", 0.0) >= 0.45:
        proposals.append({
            "id": "new-verified-repair-rule",
            "reason": "unresolved_repair_pressure",
            "implementation_mode": "pr_required",
            "executable": False,
            "required_gates": ["root-cause evidence", "allowlist review", "targeted tests", "full regression", "protected-main PR"],
        })
    return proposals[:3]


def execute_local_learning(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Run only existing verified local learning; never perform network/Git/source writes."""
    chosen = {row.get("action") for row in plan.get("selected_actions", []) if isinstance(row, dict)}
    results = []
    if "retrain_query_neural" in chosen:
        result = verified_collection_neural.train_if_ready()
        results.append({"action": "retrain_query_neural", "active": bool(result.get("active")), "reason": result.get("reason")})
    if "retrain_job_neural" in chosen:
        result = verified_collection_job_neural.train_if_ready()
        results.append({"action": "retrain_job_neural", "active": bool(result.get("active")), "reason": result.get("reason")})
    autonomy = verified_autonomy_neural.train_if_ready()
    results.append({"action": "retrain_autonomy_neural", "active": bool(autonomy.get("active")), "reason": autonomy.get("reason")})
    if "run_selfrefine_audit" in chosen:
        try:
            repair = verified_neural_self_refine.status()
            results.append({"action": "run_selfrefine_audit", "active": bool(repair.get("active")), "reason": repair.get("reason")})
        except (OSError, ValueError, TypeError, OverflowError, json.JSONDecodeError):
            results.append({"action": "run_selfrefine_audit", "active": False, "reason": "repair_status_unavailable"})
    return results


def _priority_state(signals: dict[str, float], plan: dict[str, Any]) -> dict[str, float]:
    selected = {row.get("action"): _clip01(row.get("score")) for row in plan.get("selected_actions", []) if isinstance(row, dict)}
    market_score = selected.get("rebalance_market_priority", 0.0)
    exploration_score = selected.get("increase_source_exploration", 0.0)
    return {
        "market_priority_boost": round(min(MAX_MARKET_PRIORITY_BOOST, MAX_MARKET_PRIORITY_BOOST * market_score), 6),
        "exploration_priority_boost": round(min(MAX_EXPLORATION_PRIORITY_BOOST, MAX_EXPLORATION_PRIORITY_BOOST * exploration_score), 6),
        "market_shift_signal": round(_clip01(signals.get("market_shift")), 6),
    }


def refresh_state(root: Path = ROOT, *, execute_learning: bool = True, now: datetime | None = None) -> dict[str, Any]:
    signals = collect_signals(root, now=now)
    plan = decide(signals)
    proposals = _capability_proposals(signals)
    learning = execute_local_learning(plan) if execute_learning else []
    priority = _priority_state(signals, plan)
    state = {
        "schema_version": SCHEMA,
        "updated_at": _now(),
        "mode": "bounded_autonomous",
        "signals": signals,
        "selected_actions": plan["selected_actions"],
        "priority": priority,
        "safety": SAFETY,
    }
    report = {
        "schema_version": SCHEMA,
        "updated_at": state["updated_at"],
        "ok": True,
        "state": state,
        "learning": learning,
        "proposals": proposals,
        "deterministic_guard_authority": True,
        "source_changes_require_pr": True,
    }
    atomic_write_json(STATE_PATH if root == ROOT else root / STATE_PATH.name, state, suffix=".tablet-autonomy-state.tmp")
    atomic_write_json(PROPOSALS_PATH if root == ROOT else root / PROPOSALS_PATH.name,
                      {"schema_version": SCHEMA, "updated_at": state["updated_at"], "proposals": proposals,
                       "non_executable": True, "implementation_mode": "pr_required"},
                      suffix=".tablet-autonomy-proposals.tmp")
    atomic_write_json(REPORT_PATH if root == ROOT else root / REPORT_PATH.name, report, suffix=".tablet-autonomy-report.tmp")
    return report


def job_priority_multiplier(filename: str, state: dict[str, Any] | None) -> float:
    if not isinstance(state, dict):
        return 1.0
    priority = state.get("priority") if isinstance(state.get("priority"), dict) else {}
    if filename in MARKET_JOB_KEYS:
        return round(1.0 + min(MAX_MARKET_PRIORITY_BOOST, _clip01(priority.get("market_priority_boost"))), 6)
    if filename in EXPLORATION_JOB_KEYS:
        return round(1.0 + min(MAX_EXPLORATION_PRIORITY_BOOST, _clip01(priority.get("exploration_priority_boost"))), 6)
    return 1.0


def public_status(root: Path = ROOT) -> dict[str, Any]:
    state = _read_json(root / STATE_PATH.name, {})
    proposals = _read_json(root / PROPOSALS_PATH.name, {})
    return {
        "ok": isinstance(state, dict) and state.get("schema_version") == SCHEMA,
        "mode": state.get("mode") if isinstance(state, dict) else None,
        "updated_at": state.get("updated_at") if isinstance(state, dict) else None,
        "signals": state.get("signals", {}) if isinstance(state, dict) else {},
        "selected_actions": state.get("selected_actions", []) if isinstance(state, dict) else [],
        "priority": state.get("priority", {}) if isinstance(state, dict) else {},
        "proposal_count": len(proposals.get("proposals", [])) if isinstance(proposals, dict) and isinstance(proposals.get("proposals"), list) else 0,
        "neural": verified_autonomy_neural.status(),
        "safety": SAFETY,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--no-learning", action="store_true")
    args = parser.parse_args()
    result = public_status() if args.status else refresh_state(execute_learning=not args.no_learning)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
