#!/usr/bin/env python3
"""Bounded autonomous evolution controller for the Tablet GPT / TCG Grader runtime.

The controller coordinates existing verified neural learners and health signals.
It may retrain already-defined advisory models when their own gates allow it,
but it never generates source code, invents facts/prices, changes verification
rules, writes Git, or bypasses protected-main / CI. Unknown capability needs are
returned as machine-readable proposals for the normal branch/PR pipeline.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent

SCHEMA_VERSION = 1
CONTROLLER_VERSION = "v371"
MAX_MARKET_AGE_SECONDS = 72 * 60 * 60
FUTURE_TOLERANCE_SECONDS = 5 * 60

SAFE_LEARNING_ACTIONS = (
    "TRAIN_QUERY_STRATEGY",
    "TRAIN_JOB_STRATEGY",
    "TRAIN_REPAIR_PRIORITY",
)
PROPOSAL_ACTIONS = (
    "REFRESH_MARKET_DATA",
    "REPAIR_AI_RUNTIME",
    "REVIEW_SYNC_HEALTH",
    "PROPOSE_VERIFIED_FEATURE",
)

SAFETY = {
    "bounded_autonomy": True,
    "verified_learning_only": True,
    "neural_models_advisory_only": True,
    "source_code_auto_generation": False,
    "source_code_auto_rewrite": False,
    "arbitrary_command_generation": False,
    "git_write": False,
    "direct_main_write": False,
    "branch_protection_bypass": False,
    "verification_bypass": False,
    "official_trust_auto_promotion": False,
    "candidate_database_auto_promotion": False,
    "unknown_fact_auto_promotion": False,
    "unknown_feature_auto_implementation": False,
    "feature_proposals_require_normal_pr_pipeline": True,
    "failed_learning_keeps_existing_model": True,
    "market_data_stale_or_invalid_is_hold": True,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


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


def _load_json(path: Path, *, max_bytes: int = 4_000_000) -> dict[str, Any] | None:
    try:
        if not path.is_file() or path.is_symlink() or path.stat().st_size > max_bytes:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def market_freshness(*, root: Path = ROOT, now: datetime | None = None) -> dict[str, Any]:
    """Read-only market freshness signal. It never repairs or fabricates data."""
    moment = (now or _now()).astimezone(timezone.utc)
    files = ("exchange_rates.json", "market_prices.json")
    rows: dict[str, Any] = {}
    stale: list[str] = []
    invalid: list[str] = []
    for name in files:
        payload = _load_json(root / name)
        if payload is None:
            rows[name] = {"status": "unknown", "age_seconds": None}
            invalid.append(name)
            continue
        timestamp = None
        for key in ("source_timestamp", "updated_at", "generated_at", "collected_at", "timestamp"):
            timestamp = _parse_time(payload.get(key))
            if timestamp is not None:
                break
        if timestamp is None:
            rows[name] = {"status": "invalid_timestamp", "age_seconds": None}
            invalid.append(name)
            continue
        if timestamp > moment + timedelta(seconds=FUTURE_TOLERANCE_SECONDS):
            rows[name] = {"status": "future_timestamp", "age_seconds": None}
            invalid.append(name)
            continue
        age = max(0, int((moment - timestamp).total_seconds()))
        status = "fresh" if age <= MAX_MARKET_AGE_SECONDS else "stale"
        rows[name] = {"status": status, "age_seconds": age}
        if status == "stale":
            stale.append(name)
    return {
        "status": "hold" if invalid or stale else "fresh",
        "files": rows,
        "stale": stale,
        "invalid": invalid,
        "max_age_seconds": MAX_MARKET_AGE_SECONDS,
    }


def _load_runtime_model_status() -> dict[str, Any]:
    try:
        import ai_runtime_model_guard
        value = ai_runtime_model_guard.public_status(use_cache=False)
    except Exception as exc:
        return {
            "status": "broken",
            "healthy": False,
            "requires_attention": True,
            "models": {},
            "reason": f"runtime_guard_error:{type(exc).__name__}",
        }
    return value if isinstance(value, dict) else {
        "status": "broken", "healthy": False, "requires_attention": True,
        "models": {}, "reason": "runtime_guard_invalid",
    }


def _load_repair_neural_status() -> dict[str, Any]:
    try:
        import verified_neural_self_refine
        value = verified_neural_self_refine.status()
    except Exception as exc:
        return {
            "active": False,
            "label_count": 0,
            "requires_attention": True,
            "reason": f"repair_neural_error:{type(exc).__name__}",
        }
    return value if isinstance(value, dict) else {
        "active": False, "label_count": 0, "requires_attention": True,
        "reason": "repair_neural_invalid",
    }


def gather_signals(*, root: Path = ROOT, now: datetime | None = None) -> dict[str, Any]:
    return {
        "runtime_models": _load_runtime_model_status(),
        "repair_neural": _load_repair_neural_status(),
        "market": market_freshness(root=root, now=now),
    }


def _priority(reason: str) -> int:
    table = {
        "broken": 100,
        "stale": 90,
        "inactive_ready": 80,
        "attention": 70,
        "freshness": 60,
        "proposal": 40,
    }
    return table.get(reason, 10)


def plan_cycle(signals: dict[str, Any] | None = None, *, root: Path = ROOT,
               now: datetime | None = None) -> dict[str, Any]:
    signals = signals if isinstance(signals, dict) else gather_signals(root=root, now=now)
    actions: list[dict[str, Any]] = []
    runtime = signals.get("runtime_models") if isinstance(signals.get("runtime_models"), dict) else {}
    models = runtime.get("models") if isinstance(runtime.get("models"), dict) else {}

    for model_name, action_id in (
        ("query_strategy", "TRAIN_QUERY_STRATEGY"),
        ("job_strategy", "TRAIN_JOB_STRATEGY"),
    ):
        row = models.get(model_name) if isinstance(models.get(model_name), dict) else {}
        status = str(row.get("status") or "unknown")
        if status in {"broken", "degraded"}:
            actions.append({
                "id": action_id,
                "kind": "safe_learning",
                "priority": _priority("broken" if status == "broken" else "stale"),
                "reason": str(row.get("reason") or status)[:160],
                "may_modify_source": False,
                "requires_existing_training_gate": True,
            })
        elif status == "inactive":
            labels = row.get("label_count")
            if isinstance(labels, int) and labels >= 1000:
                actions.append({
                    "id": action_id,
                    "kind": "safe_learning",
                    "priority": _priority("inactive_ready"),
                    "reason": "verified_labels_ready_but_model_inactive",
                    "may_modify_source": False,
                    "requires_existing_training_gate": True,
                })

    repair = signals.get("repair_neural") if isinstance(signals.get("repair_neural"), dict) else {}
    repair_labels = repair.get("label_count")
    if (
        repair.get("requires_attention") is True
        or (repair.get("active") is not True and isinstance(repair_labels, int) and repair_labels >= 1000)
    ):
        actions.append({
            "id": "TRAIN_REPAIR_PRIORITY",
            "kind": "safe_learning",
            "priority": _priority("attention"),
            "reason": str(repair.get("reason") or "verified_repair_model_needs_review")[:160],
            "may_modify_source": False,
            "requires_existing_training_gate": True,
        })

    market = signals.get("market") if isinstance(signals.get("market"), dict) else {}
    if market.get("status") == "hold":
        actions.append({
            "id": "REFRESH_MARKET_DATA",
            "kind": "proposal",
            "priority": _priority("freshness"),
            "reason": "market_freshness_hold",
            "evidence": {
                "stale": list(market.get("stale") or []),
                "invalid": list(market.get("invalid") or []),
            },
            "may_modify_source": False,
            "network_execution": False,
        })

    if runtime.get("status") == "broken":
        actions.append({
            "id": "REPAIR_AI_RUNTIME",
            "kind": "proposal",
            "priority": _priority("broken"),
            "reason": str(runtime.get("reason") or "runtime_model_guard_broken")[:160],
            "may_modify_source": False,
            "normal_pr_pipeline_required": True,
        })

    dedup: dict[str, dict[str, Any]] = {}
    for row in actions:
        current = dedup.get(row["id"])
        if current is None or int(row.get("priority", 0)) > int(current.get("priority", 0)):
            dedup[row["id"]] = row
    ordered = sorted(dedup.values(), key=lambda row: (-int(row.get("priority", 0)), row["id"]))

    return {
        "schema_version": SCHEMA_VERSION,
        "controller_version": CONTROLLER_VERSION,
        "status": "ACTION_REQUIRED" if ordered else "STABLE",
        "signals": signals,
        "actions": ordered,
        "safe_learning_actions": [row["id"] for row in ordered if row.get("kind") == "safe_learning"],
        "proposal_actions": [row["id"] for row in ordered if row.get("kind") == "proposal"],
        "safety": SAFETY,
    }


def execute_safe_learning(plan: dict[str, Any]) -> dict[str, Any]:
    """Execute only existing verified model trainers. Never executes proposals."""
    requested = plan.get("safe_learning_actions") if isinstance(plan, dict) else []
    if not isinstance(requested, list):
        raise ValueError("INVALID_PLAN")
    unknown = sorted({str(item) for item in requested} - set(SAFE_LEARNING_ACTIONS))
    if unknown:
        raise ValueError("UNALLOWLISTED_AUTONOMOUS_ACTION")
    results: dict[str, Any] = {}
    for action_id in requested:
        try:
            if action_id == "TRAIN_QUERY_STRATEGY":
                import verified_collection_neural
                results[action_id] = verified_collection_neural.train_if_ready()
            elif action_id == "TRAIN_JOB_STRATEGY":
                import verified_collection_job_neural
                results[action_id] = verified_collection_job_neural.train_if_ready()
            elif action_id == "TRAIN_REPAIR_PRIORITY":
                import verified_neural_self_refine
                results[action_id] = verified_neural_self_refine.train_if_ready()
        except Exception as exc:
            results[action_id] = {
                "status": "FAILED_KEEP_EXISTING",
                "error_code": type(exc).__name__,
                "existing_model_preserved": True,
            }
    return {
        "status": "SAFE_LEARNING_EXECUTED" if results else "NO_SAFE_LEARNING_ACTION",
        "results": results,
        "proposals_executed": False,
        "git_write": False,
        "source_code_modified": False,
    }


def run_cycle(*, execute: bool = False, root: Path = ROOT,
              now: datetime | None = None) -> dict[str, Any]:
    plan = plan_cycle(root=root, now=now)
    execution = execute_safe_learning(plan) if execute else {
        "status": "PLAN_ONLY",
        "results": {},
        "proposals_executed": False,
        "git_write": False,
        "source_code_modified": False,
    }
    return {"plan": plan, "execution": execution}


def self_test() -> None:
    assert SAFETY["source_code_auto_generation"] is False
    assert SAFETY["git_write"] is False
    sample = {
        "runtime_models": {
            "status": "degraded",
            "models": {
                "query_strategy": {"status": "degraded", "reason": "active_model_stale"},
                "job_strategy": {"status": "active", "reason": None},
            },
        },
        "repair_neural": {"active": True, "label_count": 1200, "requires_attention": False},
        "market": {"status": "fresh", "stale": [], "invalid": []},
    }
    plan = plan_cycle(sample)
    assert plan["safe_learning_actions"] == ["TRAIN_QUERY_STRATEGY"]
    assert plan["proposal_actions"] == []
    print("Tablet bounded autonomous evolution v371: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-safe-learning", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    result = run_cycle(execute=args.execute_safe_learning)
    if not args.quiet:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
