#!/usr/bin/env python3
"""Resource-aware bounded autonomous evolution for Tablet GPT / TCG Grader.

v372 coordinates the existing verified neural learners. It may train at most one
allowlisted advisory model per cycle, defers heavy work under device pressure,
enforces cooldowns, validates post-training artifacts, and rolls back invalid
models. Market signals are freshness/coverage/source-health signals only: the
controller never invents price direction, facts, code, shell commands, or Git
changes. New capability needs remain evidence-backed proposals for the normal
branch/PR/CI path.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import tablet_autonomous_evolution_v371 as v371
from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
CONTROLLER_VERSION = "v372"
SCHEMA_VERSION = 2

MAX_TRAINING_ACTIONS_PER_CYCLE = 1
SUCCESS_COOLDOWN_SECONDS = 6 * 60 * 60
FAILURE_COOLDOWN_SECONDS = 60 * 60
MAX_LOAD_PER_CPU = 0.85
MIN_AVAILABLE_MEMORY_BYTES = 512 * 1024 * 1024
MIN_AVAILABLE_MEMORY_RATIO = 0.12
MAX_STATE_BYTES = 1_000_000
MAX_MARKET_ENTRIES = 20_000
MIN_REGION_ROWS = 2
REGIONS = ("KR", "JP", "US")

STATE_PATH = ROOT / "tablet_autonomy_state.json"
STATE_BACKUP_PATH = ROOT / "tablet_autonomy_state.json.bak"
REPORT_PATH = ROOT / "tablet_autonomy_report.json"
PROPOSALS_PATH = ROOT / "tablet_autonomy_proposals.json"

SAFE_LEARNING_ACTIONS = v371.SAFE_LEARNING_ACTIONS
PROPOSAL_ACTIONS = tuple(sorted(set(v371.PROPOSAL_ACTIONS) | {
    "EXPAND_MARKET_COVERAGE",
    "RECHECK_DEGRADED_SOURCES",
    "REVIEW_MODEL_FEATURE_CONTRACT",
}))
SAFETY = dict(v371.SAFETY)
SAFETY.update({
    "resource_aware_training": True,
    "max_training_actions_per_cycle": MAX_TRAINING_ACTIONS_PER_CYCLE,
    "training_cooldown_enforced": True,
    "unknown_resource_pressure_is_hold": True,
    "invalid_post_training_model_auto_rollback": True,
    "corrupt_autonomy_state_is_hold": True,
    "market_regime_is_operational_signal_only": True,
    "market_direction_inferred": False,
    "capability_proposals_are_non_executable": True,
    "capability_proposals_require_normal_pr_pipeline": True,
    "autonomous_issue_or_pr_write": False,
})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: Any) -> datetime | None:
    return v371._parse_time(value)


def _load_json(path: Path, *, max_bytes: int = MAX_STATE_BYTES) -> dict[str, Any] | None:
    try:
        if not path.is_file() or path.is_symlink():
            return None
        value = json.loads(safe_read_text(path, max_bytes=max_bytes))
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _default_state() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "controller_version": CONTROLLER_VERSION,
        "updated_at": None,
        "last_training": {},
        "consecutive_failures": {},
    }


def _sanitize_state(raw: object) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or raw.get("schema_version") != SCHEMA_VERSION:
        return None
    if not isinstance(raw.get("last_training"), dict) or not isinstance(raw.get("consecutive_failures"), dict):
        return None
    training: dict[str, dict[str, Any]] = {}
    failures: dict[str, int] = {}
    for action_id in SAFE_LEARNING_ACTIONS:
        row = raw["last_training"].get(action_id)
        if isinstance(row, dict):
            stamp = _parse_time(row.get("at"))
            status = str(row.get("status") or "")
            if stamp is not None and status in {"success", "failure"}:
                training[action_id] = {"at": stamp.isoformat(timespec="seconds"), "status": status}
        value = raw["consecutive_failures"].get(action_id, 0)
        if not isinstance(value, bool):
            try:
                failures[action_id] = max(0, min(1000, int(value)))
            except (TypeError, ValueError, OverflowError):
                pass
    return {
        "schema_version": SCHEMA_VERSION,
        "controller_version": CONTROLLER_VERSION,
        "updated_at": str(raw.get("updated_at") or "")[:64] or None,
        "last_training": training,
        "consecutive_failures": failures,
    }


def load_state(*, state_path: Path = STATE_PATH, backup_path: Path | None = None) -> dict[str, Any]:
    backup = backup_path or state_path.with_name(state_path.name + ".bak")
    existed = any(p.exists() and not p.is_symlink() for p in (state_path, backup))
    for candidate, source in ((state_path, "primary"), (backup, "backup")):
        clean = _sanitize_state(_load_json(candidate))
        if clean is not None:
            return {
                "state": clean,
                "source": source,
                "recovered_from_backup": source == "backup",
                "corruption_hold": False,
            }
    return {
        "state": _default_state(),
        "source": "corrupt" if existed else "fresh",
        "recovered_from_backup": False,
        "corruption_hold": existed,
    }


def save_state(
    state: dict[str, Any], *, state_path: Path = STATE_PATH,
    backup_path: Path | None = None, corruption_hold: bool = False,
) -> dict[str, Any]:
    if corruption_hold:
        return {"status": "STATE_CORRUPTION_HOLD", "written": False}
    clean = _sanitize_state(state)
    if clean is None:
        return {"status": "INVALID_STATE", "written": False}
    backup = backup_path or state_path.with_name(state_path.name + ".bak")
    previous = _sanitize_state(_load_json(state_path))
    try:
        if previous is not None:
            atomic_write_json(backup, previous, suffix=".autonomy-state-bak.tmp")
        atomic_write_json(state_path, clean, suffix=".autonomy-state.tmp")
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        return {"status": "STATE_WRITE_FAILED", "written": False, "error_code": type(exc).__name__}
    return {"status": "STATE_SAVED", "written": True}


def _read_proc(path: Path) -> str | None:
    try:
        if not path.is_file() or path.is_symlink():
            return None
        return safe_read_text(path, max_bytes=128_000)
    except (OSError, UnicodeError, ValueError, TypeError):
        return None


def resource_pressure(*, proc_root: Path = Path("/proc")) -> dict[str, Any]:
    cpu_count = max(1, int(os.cpu_count() or 1))
    load1 = None
    text = _read_proc(proc_root / "loadavg")
    if text:
        try:
            number = float(text.split()[0])
            load1 = number if math.isfinite(number) and number >= 0 else None
        except (IndexError, TypeError, ValueError, OverflowError):
            pass

    available = total = None
    text = _read_proc(proc_root / "meminfo")
    if text:
        for line in text.splitlines():
            if ":" not in line:
                continue
            key, raw = line.split(":", 1)
            try:
                value = max(0, int(raw.strip().split()[0]) * 1024)
            except (IndexError, TypeError, ValueError, OverflowError):
                continue
            if key == "MemAvailable":
                available = value
            elif key == "MemTotal":
                total = value

    reasons: list[str] = []
    per_cpu = load1 / cpu_count if load1 is not None else None
    ratio = (available / total) if available is not None and total else None
    if per_cpu is not None and per_cpu > MAX_LOAD_PER_CPU:
        reasons.append("cpu_load_high")
    if available is not None:
        if available < MIN_AVAILABLE_MEMORY_BYTES:
            reasons.append("memory_available_low")
        elif ratio is not None and ratio < MIN_AVAILABLE_MEMORY_RATIO:
            reasons.append("memory_ratio_low")

    observed = load1 is not None and available is not None and total is not None
    if not observed:
        reasons.append("resource_metrics_unavailable")
        status = "unknown"
    else:
        status = "busy" if reasons else "normal"
    return {
        "status": status,
        "reasons": reasons,
        "cpu_count": cpu_count,
        "load1": load1,
        "load_per_cpu": round(per_cpu, 6) if per_cpu is not None else None,
        "mem_available_bytes": available,
        "mem_total_bytes": total,
        "mem_available_ratio": round(ratio, 6) if ratio is not None else None,
        "training_budget": MAX_TRAINING_ACTIONS_PER_CYCLE if status == "normal" else 0,
    }


def _source_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if "T" in text:
            stamp = _parse_time(text)
            return stamp.date() if stamp else None
        return date.fromisoformat(text[:10])
    except (TypeError, ValueError, OverflowError):
        return None


def _healthy_status(value: Any) -> bool:
    text = str(value or "").strip().casefold()
    if not text:
        return False
    if any(token in text for token in ("지연", "대기", "오류", "실패", "timeout", "blocked", "429", "403", "재확인")):
        return False
    return any(token in text for token in ("정상", "ok", "healthy", "success", "verified"))


def market_profile(*, root: Path = ROOT, now: datetime | None = None) -> dict[str, Any]:
    moment = (now or _now()).astimezone(timezone.utc)
    freshness = v371.market_freshness(root=root, now=moment)
    payload = _load_json(root / "market_prices.json", max_bytes=4_000_000)
    entries = payload.get("entries") if isinstance(payload, dict) else None
    if not isinstance(entries, dict) or len(entries) > MAX_MARKET_ENTRIES:
        return {
            "status": "hold", "regime": "HOLD_INVALID_MARKET_FILE",
            "freshness": freshness, "entry_count": 0,
            "region_counts": {r: 0 for r in REGIONS}, "product_counts": {},
            "low_coverage_regions": list(REGIONS), "degraded_source_count": 0,
            "degraded_source_ratio": None, "market_direction_inferred": False,
        }

    regions = {r: 0 for r in REGIONS}
    products: dict[str, int] = {}
    degraded = dated = old_dates = 0
    valid_entries = 0
    for key, raw in entries.items():
        if not isinstance(raw, dict):
            continue
        valid_entries += 1
        parts = str(key).split("|")
        region = parts[0].upper() if parts else ""
        kind = parts[-1].upper() if len(parts) >= 3 else "UNKNOWN"
        if region in regions:
            regions[region] += 1
        products[kind] = products.get(kind, 0) + 1

        statuses: list[Any] = []
        if raw.get("link_status") is not None:
            statuses.append(raw.get("link_status"))
        if isinstance(raw.get("link_statuses"), dict):
            statuses.extend(raw["link_statuses"].values())
        if not statuses or not all(_healthy_status(item) for item in statuses):
            degraded += 1

        src = _source_date(raw.get("source_date"))
        if src is not None:
            dated += 1
            if max(0, (moment.date() - src).days) > 30:
                old_dates += 1

    low_regions = [r for r, count in regions.items() if count < MIN_REGION_ROWS]
    ratio = degraded / valid_entries if valid_entries else None
    if freshness.get("status") != "fresh":
        status, regime = "hold", "HOLD_FRESHNESS"
    elif low_regions:
        status, regime = "attention", "UNDERCOVERED"
    elif ratio is not None and ratio > 0.35:
        status, regime = "attention", "DEGRADED_SOURCES"
    else:
        status, regime = "healthy", "HEALTHY"
    return {
        "status": status, "regime": regime, "freshness": freshness,
        "entry_count": valid_entries, "region_counts": regions,
        "product_counts": dict(sorted(products.items())),
        "low_coverage_regions": low_regions,
        "degraded_source_count": degraded,
        "degraded_source_ratio": round(ratio, 6) if ratio is not None else None,
        "source_date_count": dated, "source_date_older_than_30d_count": old_dates,
        "market_direction_inferred": False,
    }


def _repair_rule_fingerprints() -> dict[str, str]:
    try:
        import verified_code_repair_rules as rules
        values = {str(rid): str(rules.rule_fingerprint(rid)) for rid in tuple(rules.ALL_RULE_IDS)}
    except Exception:
        return {}
    return dict(sorted((k, v) for k, v in values.items() if k and len(v) >= 8))


def _load_repair_neural_status() -> dict[str, Any]:
    try:
        import verified_neural_self_refine as neural
        fingerprints = _repair_rule_fingerprints()
        if not fingerprints:
            raise RuntimeError("REPAIR_RULE_FINGERPRINTS_UNAVAILABLE")
        result = neural.status(current_rule_fingerprints=fingerprints)
    except Exception as exc:
        return {
            "active": False, "label_count": 0, "requires_attention": True,
            "reason": f"repair_neural_error:{type(exc).__name__}",
        }
    result = dict(result) if isinstance(result, dict) else {}
    labels = int(result.get("label_count") or 0)
    minimum = int(result.get("minimum_labels") or 1000)
    reason = str(result.get("reason") or "")
    result["requires_attention"] = (
        (result.get("active") is not True and labels >= minimum)
        or reason not in {"active", "model_inactive", "waiting_for_independent_labels"}
    )
    return result


def gather_signals(*, root: Path = ROOT, now: datetime | None = None) -> dict[str, Any]:
    return {
        "runtime_models": v371._load_runtime_model_status(),
        "repair_neural": _load_repair_neural_status(),
        "market": v371.market_freshness(root=root, now=now),
    }


def _proposal_rows(profile: dict[str, Any], runtime: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    if profile.get("low_coverage_regions"):
        rows.append({
            "id": "EXPAND_MARKET_COVERAGE", "kind": "proposal", "priority": 55,
            "reason": "market_region_coverage_below_minimum",
            "evidence": {
                "low_coverage_regions": list(profile.get("low_coverage_regions") or []),
                "region_counts": dict(profile.get("region_counts") or {}),
            },
            "normal_pr_pipeline_required": True, "auto_implementation": False, "network_execution": False,
        })
    ratio = profile.get("degraded_source_ratio")
    if isinstance(ratio, (int, float)) and not isinstance(ratio, bool) and math.isfinite(float(ratio)) and float(ratio) > 0.35:
        rows.append({
            "id": "RECHECK_DEGRADED_SOURCES", "kind": "proposal", "priority": 65,
            "reason": "market_source_health_degraded",
            "evidence": {
                "degraded_source_count": int(profile.get("degraded_source_count") or 0),
                "degraded_source_ratio": float(ratio),
            },
            "normal_pr_pipeline_required": True, "auto_implementation": False, "network_execution": False,
        })
    if runtime.get("status") == "broken":
        rows.append({
            "id": "REVIEW_MODEL_FEATURE_CONTRACT", "kind": "proposal", "priority": 85,
            "reason": "runtime_model_contract_broken",
            "evidence": {"broken_models": list(runtime.get("broken_models") or [])},
            "normal_pr_pipeline_required": True, "auto_implementation": False, "network_execution": False,
        })
    return rows


def _cooldown_remaining(state: dict[str, Any], action_id: str, *, now: datetime) -> int:
    row = (state.get("last_training") or {}).get(action_id)
    if not isinstance(row, dict):
        return 0
    stamp = _parse_time(row.get("at"))
    if stamp is None:
        return 0
    cooldown = SUCCESS_COOLDOWN_SECONDS if row.get("status") == "success" else FAILURE_COOLDOWN_SECONDS
    return max(0, int(cooldown - (now - stamp).total_seconds()))


def plan_cycle(
    signals: dict[str, Any] | None = None, *, root: Path = ROOT,
    now: datetime | None = None, proc_root: Path = Path("/proc"),
    state_path: Path = STATE_PATH, state_backup_path: Path | None = None,
) -> dict[str, Any]:
    moment = (now or _now()).astimezone(timezone.utc)
    signals = signals if isinstance(signals, dict) else gather_signals(root=root, now=moment)
    base = v371.plan_cycle(signals, root=root, now=moment)
    resources = resource_pressure(proc_root=proc_root)
    profile = market_profile(root=root, now=moment)
    loaded = load_state(state_path=state_path, backup_path=state_backup_path)
    state = loaded["state"]

    actions = [dict(row) for row in base.get("actions", []) if isinstance(row, dict)]
    ids = {str(row.get("id") or "") for row in actions}
    for row in _proposal_rows(profile, signals.get("runtime_models") or {}):
        if row["id"] not in ids:
            actions.append(row)
            ids.add(row["id"])
    actions.sort(key=lambda row: (-int(row.get("priority", 0)), str(row.get("id") or "")))

    candidates = [
        str(row.get("id")) for row in actions
        if row.get("kind") == "safe_learning" and str(row.get("id")) in SAFE_LEARNING_ACTIONS
    ]
    selected: list[str] = []
    deferred: list[dict[str, Any]] = []
    for action_id in candidates:
        if loaded["corruption_hold"]:
            deferred.append({"id": action_id, "reason": "autonomy_state_corruption_hold"})
            continue
        if resources["training_budget"] <= 0:
            deferred.append({"id": action_id, "reason": "device_resource_pressure"})
            continue
        remaining = _cooldown_remaining(state, action_id, now=moment)
        if remaining:
            deferred.append({"id": action_id, "reason": "training_cooldown", "cooldown_remaining_seconds": remaining})
        elif len(selected) < int(resources["training_budget"]):
            selected.append(action_id)
        else:
            deferred.append({"id": action_id, "reason": "per_cycle_training_budget"})

    proposals = [str(row.get("id")) for row in actions if row.get("kind") == "proposal"]
    return {
        "schema_version": SCHEMA_VERSION, "controller_version": CONTROLLER_VERSION,
        "status": "ACTION_REQUIRED" if actions else "STABLE",
        "signals": signals, "resources": resources, "market_profile": profile,
        "state_source": loaded["source"], "state_recovered_from_backup": loaded["recovered_from_backup"],
        "state_corruption_hold": loaded["corruption_hold"], "actions": actions,
        "safe_learning_candidates": candidates, "selected_safe_learning_actions": selected,
        "deferred_safe_learning_actions": deferred, "proposal_actions": proposals,
        "training_budget": int(resources["training_budget"]), "safety": SAFETY,
    }


def _trainer_spec(action_id: str) -> tuple[Any, dict[str, Any]]:
    if action_id == "TRAIN_QUERY_STRATEGY":
        import verified_collection_neural as module
        return module, {}
    if action_id == "TRAIN_JOB_STRATEGY":
        import verified_collection_job_neural as module
        return module, {}
    if action_id == "TRAIN_REPAIR_PRIORITY":
        import verified_neural_self_refine as module
        fingerprints = _repair_rule_fingerprints()
        if not fingerprints:
            raise RuntimeError("REPAIR_RULE_FINGERPRINTS_UNAVAILABLE")
        return module, {"current_rule_fingerprints": fingerprints}
    raise ValueError("UNALLOWLISTED_AUTONOMOUS_ACTION")


def _valid_model(module: Any) -> dict[str, Any] | None:
    path = Path(getattr(module, "MODEL_PATH", ""))
    validator = getattr(module, "_validate_model_payload", None)
    if not path.is_file() or path.is_symlink() or not callable(validator):
        return None
    raw = _load_json(path, max_bytes=8_000_000)
    try:
        return raw if raw is not None and validator(raw) is True else None
    except Exception:
        return None


def _restore_model(module: Any, previous: dict[str, Any] | None, *, remove_if_new: bool) -> dict[str, Any]:
    path = Path(getattr(module, "MODEL_PATH", ""))
    try:
        if previous is not None:
            atomic_write_json(path, previous, suffix=".autonomy-model-rollback.tmp")
            return {"status": "PREVIOUS_MODEL_RESTORED", "restored": True}
        if remove_if_new and path.is_file() and not path.is_symlink():
            path.unlink()
            return {"status": "INVALID_NEW_MODEL_REMOVED", "restored": True}
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        return {"status": "ROLLBACK_FAILED", "restored": False, "error_code": type(exc).__name__}
    return {"status": "ROLLBACK_NOT_APPLICABLE", "restored": False}


def guarded_train(
    action_id: str, *, module_override: Any | None = None,
    kwargs_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if action_id not in SAFE_LEARNING_ACTIONS:
        raise ValueError("UNALLOWLISTED_AUTONOMOUS_ACTION")
    module, kwargs = (
        _trainer_spec(action_id) if module_override is None
        else (module_override, dict(kwargs_override or {}))
    )
    model_path = Path(getattr(module, "MODEL_PATH", ""))
    before_exists = model_path.is_file() and not model_path.is_symlink()
    previous = _valid_model(module)
    try:
        result = module.train_if_ready(**kwargs)
    except Exception as exc:
        return {
            "status": "TRAINING_FAILED_KEEP_EXISTING", "error_code": type(exc).__name__,
            "existing_model_preserved": previous is not None,
            "rollback": {"status": "TRAINER_EXCEPTION_NO_CONTROLLER_WRITE", "restored": False},
        }

    current = _valid_model(module)
    after_exists = model_path.is_file() and not model_path.is_symlink()
    if current is None and (previous is not None or (not before_exists and after_exists)):
        rollback = _restore_model(module, previous, remove_if_new=not before_exists)
        return {
            "status": "ROLLED_BACK_INVALID_POST_TRAINING_MODEL",
            "trainer_result": result if isinstance(result, dict) else {},
            "existing_model_preserved": bool(rollback.get("restored")),
            "rollback": rollback,
        }
    active = isinstance(result, dict) and result.get("active") is True
    if active and current is None:
        return {
            "status": "POST_TRAINING_MODEL_INVALID_HOLD",
            "trainer_result": result, "existing_model_preserved": previous is not None,
            "rollback": {"status": "ROLLBACK_NOT_APPLICABLE", "restored": False},
        }
    return {
        "status": "TRAINING_VERIFIED" if active and current is not None else "TRAINING_GATE_HELD",
        "trainer_result": result if isinstance(result, dict) else {"status": "invalid_trainer_result"},
        "existing_model_preserved": True,
        "rollback": {"status": "NOT_REQUIRED", "restored": False},
    }


def execute_safe_learning(
    plan: dict[str, Any], *, state_path: Path = STATE_PATH,
    state_backup_path: Path | None = None, now: datetime | None = None,
) -> dict[str, Any]:
    requested = plan.get("selected_safe_learning_actions") if isinstance(plan, dict) else []
    if not isinstance(requested, list):
        raise ValueError("INVALID_PLAN")
    if sorted({str(x) for x in requested} - set(SAFE_LEARNING_ACTIONS)):
        raise ValueError("UNALLOWLISTED_AUTONOMOUS_ACTION")
    if len(requested) > MAX_TRAINING_ACTIONS_PER_CYCLE:
        raise ValueError("TRAINING_BUDGET_EXCEEDED")

    moment = (now or _now()).astimezone(timezone.utc)
    loaded = load_state(state_path=state_path, backup_path=state_backup_path)
    if loaded["corruption_hold"] and requested:
        return {
            "status": "STATE_CORRUPTION_HOLD", "results": {},
            "state": {"status": "STATE_CORRUPTION_HOLD", "written": False},
            "proposals_executed": False, "git_write": False, "source_code_modified": False,
        }
    state = loaded["state"]
    results = {}
    for action_id in requested:
        outcome = guarded_train(action_id)
        results[action_id] = outcome
        success = outcome.get("status") in {"TRAINING_VERIFIED", "TRAINING_GATE_HELD"}
        state["last_training"][action_id] = {
            "at": moment.isoformat(timespec="seconds"),
            "status": "success" if success else "failure",
        }
        count = int(state["consecutive_failures"].get(action_id, 0) or 0)
        state["consecutive_failures"][action_id] = 0 if success else min(1000, count + 1)
    state["updated_at"] = moment.isoformat(timespec="seconds")
    state_write = save_state(
        state, state_path=state_path, backup_path=state_backup_path,
        corruption_hold=loaded["corruption_hold"],
    )
    return {
        "status": "SAFE_LEARNING_EXECUTED" if results else "NO_SAFE_LEARNING_ACTION",
        "results": results, "state": state_write, "proposals_executed": False,
        "git_write": False, "source_code_modified": False,
    }


def _write_runtime_outputs(result: dict[str, Any], *, root: Path = ROOT) -> dict[str, Any]:
    proposals = {
        "schema_version": SCHEMA_VERSION, "controller_version": CONTROLLER_VERSION,
        "generated_at": _now().isoformat(timespec="seconds"),
        "normal_pr_pipeline_required": True, "auto_implementation": False,
        "proposals": [
            row for row in result.get("plan", {}).get("actions", [])
            if isinstance(row, dict) and row.get("kind") == "proposal"
        ],
    }
    try:
        atomic_write_json(root / REPORT_PATH.name, result, suffix=".autonomy-report.tmp")
        atomic_write_json(root / PROPOSALS_PATH.name, proposals, suffix=".autonomy-proposals.tmp")
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        return {"status": "RUNTIME_OUTPUT_WRITE_FAILED", "error_code": type(exc).__name__}
    return {"status": "RUNTIME_OUTPUTS_SAVED", "proposal_count": len(proposals["proposals"])}


def run_cycle(
    *, execute: bool = False, root: Path = ROOT, now: datetime | None = None,
    proc_root: Path = Path("/proc"), state_path: Path = STATE_PATH,
    state_backup_path: Path | None = None, persist_outputs: bool = True,
) -> dict[str, Any]:
    plan = plan_cycle(
        root=root, now=now, proc_root=proc_root,
        state_path=state_path, state_backup_path=state_backup_path,
    )
    execution = (
        execute_safe_learning(plan, state_path=state_path, state_backup_path=state_backup_path, now=now)
        if execute else {
            "status": "PLAN_ONLY", "results": {}, "proposals_executed": False,
            "git_write": False, "source_code_modified": False,
        }
    )
    result = {"plan": plan, "execution": execution}
    if persist_outputs:
        result["runtime_outputs"] = _write_runtime_outputs(result, root=root)
    return result


def self_test() -> None:
    assert SAFETY["bounded_autonomy"] is True
    assert SAFETY["source_code_auto_generation"] is False
    assert SAFETY["git_write"] is False
    assert SAFETY["market_direction_inferred"] is False
    assert MAX_TRAINING_ACTIONS_PER_CYCLE == 1
    print("Tablet resource-aware autonomous evolution v372: PASS")


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
