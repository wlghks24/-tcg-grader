#!/usr/bin/env python3
"""TCG Grader V391 domain-isolated goal-directed autonomous evolution.

This wrapper reuses the verified Tablet/TCG V390 autonomy core with the
tcg_grader domain while isolating every device-local autonomy state/model/
lock/report path from the Tablet GPT domain. It also adds a grader-specific
specialization layer for verified grade calibration, 1->4->8 vision health,
SELFREFINE health, and market freshness.

Only registry-verified grade samples may rebuild vision_calibration.json.
Source-level feature gaps remain non-executable proposals behind protected
PR/CI, targeted tests, regression, integrity and actual-output validation.
No arbitrary command execution, direct Git/main write, model-weight import,
price/grade invention, or unverified source-code self-modification is allowed.
"""
from __future__ import annotations

import argparse
import json
import math
import threading
import types
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import tablet_autonomous_evolution_v390 as v390
import verified_grade_learning_v135_safe as grade_learning
from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
CONTROLLER_VERSION = "tcg-grader-v391"
CORE_CONTROLLER_VERSION = "v390"
REPORT_PATH = ROOT / "tcg_grader_autonomy_v391_report.json"
PLAN_PATH = ROOT / "tcg_grader_autonomy_v391_plan.json"

MAX_LEDGER_BYTES = 4_000_000
MARKET_STALE_HOURS = 6.0
MIN_HEALTHY_VERIFIED_GRADE_ROWS = 100
_PATH_SWAP_LOCK = threading.RLock()

SAFETY = dict(v390.SAFETY)
SAFETY.update({
    "tcg_grader_domain_isolated": True,
    "tablet_runtime_state_shared": False,
    "verified_grade_calibration_autorebuild": True,
    "verified_grade_registry_gate_required": True,
    "vision_hierarchy_1_4_8_required": True,
    "grader_specialization_planner": True,
    "source_feature_plan_non_executable": True,
    "source_feature_protected_pr_ci_required": True,
    "source_code_auto_generation": False,
    "source_code_auto_rewrite": False,
    "arbitrary_command_execution": False,
    "git_write": False,
    "direct_main_write": False,
    "verification_bypass": False,
    "peer_model_weights_imported": False,
    "peer_raw_state_imported": False,
    "market_direction_inferred": False,
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


def _autonomy_modules() -> list[types.ModuleType]:
    """Return the loaded V371+ autonomy dependency graph without importing peers."""
    found: dict[str, types.ModuleType] = {}
    stack = [v390]
    while stack:
        module = stack.pop()
        if module.__name__ in found:
            continue
        found[module.__name__] = module
        for value in vars(module).values():
            if (
                isinstance(value, types.ModuleType)
                and value.__name__.startswith("tablet_autonomous_evolution_v")
                and value.__name__ not in found
            ):
                stack.append(value)
    return [found[name] for name in sorted(found)]


def _tcg_runtime_name(name: str) -> str:
    if "tablet_autonomy" not in name:
        return name
    return name.replace("tablet_autonomy", "tcg_grader_autonomy", 1)


def runtime_isolation_manifest() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for module in _autonomy_modules():
        for key, value in vars(module).items():
            if not isinstance(value, Path) or "tablet_autonomy" not in value.name:
                continue
            rows.append({
                "module": module.__name__,
                "global": key,
                "source_name": value.name,
                "tcg_name": _tcg_runtime_name(value.name),
            })
    rows.sort(key=lambda row: (row["module"], row["global"], row["source_name"]))
    return rows


@contextmanager
def isolated_tcg_runtime_paths() -> Iterator[list[dict[str, str]]]:
    """Temporarily redirect every tablet-autonomy runtime file to TCG names.

    The source modules are shared code, but runtime state/models/locks/reports are
    never shared. Globals are restored even if the autonomy cycle fails.
    """
    with _PATH_SWAP_LOCK:
        originals: list[tuple[types.ModuleType, str, Path]] = []
        manifest = runtime_isolation_manifest()
        try:
            for module in _autonomy_modules():
                for key, value in list(vars(module).items()):
                    if not isinstance(value, Path) or "tablet_autonomy" not in value.name:
                        continue
                    originals.append((module, key, value))
                    setattr(module, key, value.with_name(_tcg_runtime_name(value.name)))
            yield manifest
        finally:
            for module, key, value in reversed(originals):
                setattr(module, key, value)


def _strict_json(path: Path, max_bytes: int = MAX_LEDGER_BYTES) -> dict[str, Any] | None:
    try:
        if path.is_symlink() or not path.is_file():
            return None
        value = json.loads(safe_read_text(path, max_bytes=max_bytes))
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _age_hours(path: Path, now: datetime) -> float | None:
    try:
        if path.is_symlink() or not path.is_file():
            return None
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except (OSError, OverflowError, ValueError):
        return None
    return max(0.0, (now - modified).total_seconds() / 3600.0)


def grader_snapshot(root: Path = ROOT, *, now: datetime | None = None) -> dict[str, Any]:
    """Collect bounded operational evidence; never infer a grade or market direction."""
    moment = (now or _now()).astimezone(timezone.utc)
    try:
        grade_audit = grade_learning.audit()
    except Exception as exc:
        grade_audit = {
            "ok": False,
            "verified_training_rows": 0,
            "vision_profiles": 0,
            "error_code": type(exc).__name__,
        }

    vision_engine = root / "grading_vision_engine.js"
    hierarchy_test = root / "test_grading_hierarchy_v17.py"
    vision_contract = {
        "engine_present": vision_engine.is_file() and not vision_engine.is_symlink(),
        "hierarchy_test_present": hierarchy_test.is_file() and not hierarchy_test.is_symlink(),
    }
    vision_contract["one_four_eight_contract_present"] = all(vision_contract.values())

    ledger = _strict_json(root / "MAIN_SELFREFINE_ERROR_LEDGER.json") or {}
    errors = ledger.get("errors") if isinstance(ledger.get("errors"), list) else []
    open_errors = sum(
        1 for row in errors
        if isinstance(row, dict) and str(row.get("state") or "open").lower() == "open"
    )

    market_age = _age_hours(root / "market_prices.json", moment)
    verified_rows = int(grade_audit.get("verified_training_rows") or 0)
    vision_profiles = grade_audit.get("vision_profiles")
    if isinstance(vision_profiles, dict):
        vision_profile_count = len(vision_profiles)
    else:
        try:
            vision_profile_count = max(0, int(vision_profiles or 0))
        except (TypeError, ValueError, OverflowError):
            vision_profile_count = 0

    return {
        "observed_at": moment.isoformat(timespec="seconds"),
        "verified_grade_learning": {
            "audit_ok": grade_audit.get("ok") is True,
            "verified_training_rows": max(0, verified_rows),
            "vision_profile_count": vision_profile_count,
            "registry_gate_required": True,
            "error_code": grade_audit.get("error_code"),
        },
        "vision_1_4_8": vision_contract,
        "selfrefine": {
            "open_error_count": open_errors,
            "ledger_present": bool(ledger),
        },
        "market": {
            "market_prices_present": market_age is not None,
            "market_prices_age_hours": round(market_age, 3) if market_age is not None else None,
            "stale_after_hours": MARKET_STALE_HOURS,
            "market_direction_inferred": False,
        },
    }


def grader_specialization_plan(
    snapshot: dict[str, Any],
    core_result: dict[str, Any],
) -> dict[str, Any]:
    grade = snapshot.get("verified_grade_learning")
    grade = grade if isinstance(grade, dict) else {}
    vision = snapshot.get("vision_1_4_8")
    vision = vision if isinstance(vision, dict) else {}
    selfrefine = snapshot.get("selfrefine")
    selfrefine = selfrefine if isinstance(selfrefine, dict) else {}
    market = snapshot.get("market")
    market = market if isinstance(market, dict) else {}

    verified_rows = max(0, int(grade.get("verified_training_rows") or 0))
    profiles = max(0, int(grade.get("vision_profile_count") or 0))
    open_errors = max(0, int(selfrefine.get("open_error_count") or 0))
    market_age = _finite(market.get("market_prices_age_hours"))

    audit_ok = grade.get("audit_ok") is True
    calibration_need = 0.0
    if audit_ok and verified_rows > 0 and profiles == 0:
        calibration_need = 1.0
    elif audit_ok and verified_rows > 0:
        calibration_need = 0.28
    audit_recovery_need = 1.0 if not audit_ok else 0.0

    hierarchy_need = 0.15 if vision.get("one_four_eight_contract_present") is True else 1.0
    selfrefine_need = _clamp(open_errors / 12.0) if open_errors else 0.05
    if market_age is None:
        market_need = 0.90
    else:
        market_need = _clamp(market_age / max(1.0, MARKET_STALE_HOURS * 2.0))
    label_need = _clamp(
        1.0 - min(verified_rows, MIN_HEALTHY_VERIFIED_GRADE_ROWS)
        / float(MIN_HEALTHY_VERIFIED_GRADE_ROWS)
    )

    candidates = [
        {
            "action_id": "RECOVER_VERIFIED_GRADE_AUDIT",
            "urgency": round(audit_recovery_need, 6),
            "auto_execute": False,
            "execution_boundary": "fail_closed_manual_or_verified_selfrefine_recovery",
        },
        {
            "action_id": "REBUILD_VERIFIED_GRADE_CALIBRATION",
            "urgency": round(calibration_need, 6),
            "auto_execute": True,
            "execution_boundary": "registry_verified_rows_only",
        },
        {
            "action_id": "VERIFY_1_4_8_VISION_HIERARCHY",
            "urgency": round(hierarchy_need, 6),
            "auto_execute": False,
            "execution_boundary": "protected_tests_and_regression",
        },
        {
            "action_id": "RECOVER_MAIN_SELFREFINE",
            "urgency": round(selfrefine_need, 6),
            "auto_execute": False,
            "execution_boundary": "existing_verified_selfrefine_gate_only",
        },
        {
            "action_id": "REFRESH_MARKET_EVIDENCE",
            "urgency": round(market_need, 6),
            "auto_execute": False,
            "execution_boundary": "existing_market_collectors_only",
        },
        {
            "action_id": "EXPAND_VERIFIED_GRADE_LABELS",
            "urgency": round(label_need, 6),
            "auto_execute": False,
            "execution_boundary": "official_registry_verified_samples_only",
        },
    ]
    candidates.sort(key=lambda row: (-float(row["urgency"]), row["action_id"]))

    core_plan = core_result.get("v390_goal_plan")
    core_plan = core_plan if isinstance(core_plan, dict) else {}
    core_goal = core_plan.get("primary_goal")
    core_goal = core_goal if isinstance(core_goal, dict) else {}
    gate = core_result.get("v390_autonomous_gate")
    gate = gate if isinstance(gate, dict) else {}

    return {
        "primary_action": candidates[0]["action_id"] if candidates else None,
        "primary_urgency": candidates[0]["urgency"] if candidates else 0.0,
        "candidates": candidates,
        "core_primary_goal": core_goal.get("goal_id"),
        "core_recommended_action": core_plan.get("recommended_action"),
        "core_gate_status": gate.get("status"),
        "core_gate_allow_execution": gate.get("allow_execution") is True,
        "decision_inputs": [
            "verified_grade_registry_audit",
            "verified_grade_training_rows",
            "vision_profile_count",
            "1_4_8_vision_contract",
            "main_selfrefine_open_errors",
            "market_evidence_freshness",
            "v390_verified_meta_critic_goal_plan",
        ],
        "source_code_auto_generation": False,
        "protected_pr_ci_required_for_source_features": True,
    }


def _maybe_rebuild_grade_calibration(
    *,
    execute: bool,
    plan: dict[str, Any],
) -> dict[str, Any]:
    if not execute:
        return {"status": "GRADE_CALIBRATION_PLAN_ONLY", "executed": False}
    if plan.get("core_gate_allow_execution") is not True:
        return {"status": "GRADE_CALIBRATION_UPSTREAM_HOLD", "executed": False}
    if plan.get("primary_action") != "REBUILD_VERIFIED_GRADE_CALIBRATION":
        return {"status": "GRADE_CALIBRATION_NOT_SELECTED", "executed": False}
    if float(_finite(plan.get("primary_urgency")) or 0.0) < 0.80:
        return {"status": "GRADE_CALIBRATION_URGENCY_GATE", "executed": False}
    try:
        result = grade_learning.rebuild_safe_vision_calibration()
    except Exception as exc:
        return {
            "status": "GRADE_CALIBRATION_REBUILD_FAILED",
            "executed": False,
            "error_code": type(exc).__name__,
        }
    return {
        "status": "GRADE_CALIBRATION_REBUILT_VERIFIED_ONLY",
        "executed": True,
        "registry_verified_training_rows": int(result.get("registry_verified_training_rows") or 0),
        "registry_gate_v135": result.get("registry_gate_v135") is True,
    }


def run_cycle(
    *,
    execute: bool = False,
    apply_capabilities: bool = False,
    train_meta: bool = False,
    apply_skills: bool = False,
    root: Path = ROOT,
    now: datetime | None = None,
    persist_outputs: bool = True,
) -> dict[str, Any]:
    moment = (now or _now()).astimezone(timezone.utc)
    with isolated_tcg_runtime_paths() as isolation_manifest:
        core = v390.run_cycle(
            domain="tcg_grader",
            execute=execute,
            apply_capabilities=apply_capabilities,
            train_meta=train_meta,
            apply_skills=apply_skills,
            root=root,
            now=moment,
            persist_outputs=persist_outputs,
        )

    before = grader_snapshot(root, now=moment)
    plan = grader_specialization_plan(before, core)
    calibration = _maybe_rebuild_grade_calibration(execute=execute, plan=plan)
    after = grader_snapshot(root, now=moment) if calibration.get("executed") else before

    result = deepcopy(core)
    result.update({
        "core_controller_version": str(core.get("controller_version") or CORE_CONTROLLER_VERSION),
        "controller_version": CONTROLLER_VERSION,
        "tcg_grader_autonomy_v391": {
            "domain": "tcg_grader",
            "domain_runtime_state_isolated": True,
            "isolated_runtime_paths": len(isolation_manifest),
            "specialization_plan": plan,
            "grade_calibration_action": calibration,
            "snapshot_before": before,
            "snapshot_after": after,
            "evolution_loop": "observe->critic/goal rank->tcg specialize->verified action->revalidate->monitor",
        },
        "safety": SAFETY,
    })

    if persist_outputs:
        try:
            atomic_write_json(
                root / PLAN_PATH.name,
                {
                    "schema_version": 1,
                    "controller_version": CONTROLLER_VERSION,
                    "generated_at": moment.isoformat(timespec="seconds"),
                    "specialization_plan": plan,
                    "isolation_manifest": isolation_manifest,
                    "source_code_auto_generation": False,
                    "protected_pr_ci_required": True,
                },
                suffix=".tcg-v391-plan.tmp",
            )
            atomic_write_json(root / REPORT_PATH.name, result, suffix=".tcg-v391-report.tmp")
            result["tcg_grader_v391_runtime_output"] = {"status": "SAVED"}
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            result["tcg_grader_v391_runtime_output"] = {
                "status": "WRITE_FAILED",
                "error_code": type(exc).__name__,
            }
    return result


def self_test() -> None:
    manifest = runtime_isolation_manifest()
    assert manifest, "no tablet autonomy runtime paths discovered"
    assert all("tablet_autonomy" in row["source_name"] for row in manifest)
    assert all("tcg_grader_autonomy" in row["tcg_name"] for row in manifest)
    assert len({(row["module"], row["global"]) for row in manifest}) == len(manifest)

    originals = {
        (module.__name__, key): value
        for module in _autonomy_modules()
        for key, value in vars(module).items()
        if isinstance(value, Path) and "tablet_autonomy" in value.name
    }
    with isolated_tcg_runtime_paths():
        current = {
            (module.__name__, key): value
            for module in _autonomy_modules()
            for key, value in vars(module).items()
            if isinstance(value, Path) and "tcg_grader_autonomy" in value.name
        }
        assert current
        assert set(current) == set(originals)
    restored = {
        (module.__name__, key): value
        for module in _autonomy_modules()
        for key, value in vars(module).items()
        if (module.__name__, key) in originals
    }
    assert restored == originals
    assert SAFETY["tcg_grader_domain_isolated"] is True
    assert SAFETY["verified_grade_registry_gate_required"] is True
    assert SAFETY["source_code_auto_generation"] is False
    assert SAFETY["git_write"] is False
    assert SAFETY["price_or_grade_invention"] is False
    print("TCG Grader domain-isolated autonomous evolution v391: PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description="TCG Grader verified autonomous evolution V391")
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
        summary = result.get("tcg_grader_autonomy_v391", {})
        print(json.dumps({
            "controller_version": result.get("controller_version"),
            "v390_status": result.get("v390_status"),
            "primary_action": (summary.get("specialization_plan") or {}).get("primary_action"),
            "grade_calibration": summary.get("grade_calibration_action"),
            "domain_runtime_state_isolated": summary.get("domain_runtime_state_isolated"),
        }, ensure_ascii=False, sort_keys=True))
    hold = str(result.get("v390_status") or "") in getattr(v390, "_HOLD_STATUSES", set())
    return 2 if hold else 0


if __name__ == "__main__":
    raise SystemExit(main())
