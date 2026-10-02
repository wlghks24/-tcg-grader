#!/usr/bin/env python3
"""V399 cross-surface self-evolution supervisor for Tablet GPT.

V399 preserves V398 as the mandatory autonomous capability core and extends
self-diagnosis across the tablet UI, PWA cache, static server exposure and
runtime manifest. Repeated UI/runtime gaps are learned as bounded,
non-executable protected-PR candidates. Runtime source code is never generated,
rewritten or committed by this controller.
"""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tablet_autonomous_evolution_v398 as v398
from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
CONTROLLER_VERSION = "v399"
CORE_CONTROLLER_VERSION = "v398"
STATE_PATH = ROOT / ".tablet_autonomy_v399_state.json"
REPORT_PATH = ROOT / "tablet_autonomy_v399_report.json"
UI_CANDIDATE_PATH = ROOT / "tablet_autonomy_ui_feature_candidates_v399.json"
LOCK_PATH = ROOT / ".tablet_autonomy_execution_v399.lock"

MAX_STATE_BYTES = 1_000_000
MAX_HISTORY = 192
MAX_GAPS = 48
PROTECTED_PR_RECURRENCE = 2

_HOLD_STATUSES = set(getattr(v398, "_HOLD_STATUSES", set())) | {
    "V399_STATE_CORRUPTION_HOLD",
    "V399_CONCURRENT_AUTONOMY_HOLD",
    "V399_UPSTREAM_HOLD",
    "V399_STATE_COMMIT_HOLD",
}

SAFETY = dict(v398.SAFETY)
SAFETY.update({
    "cross_surface_self_diagnosis_enabled": True,
    "ui_ux_pwa_runtime_health_governed": True,
    "ui_gap_recurrence_learning_enabled": True,
    "ui_source_feature_candidate_generation_enabled": True,
    "ui_source_feature_candidates_non_executable": True,
    "ui_source_feature_protected_pr_ci_required": True,
    "runtime_source_code_auto_generation": False,
    "runtime_source_code_auto_rewrite": False,
    "runtime_ui_source_auto_rewrite": False,
    "arbitrary_command_execution": False,
    "git_write": False,
    "direct_main_write": False,
    "verification_bypass": False,
    "market_direction_inferred": False,
    "price_or_grade_invention": False,
    "peer_model_weights_imported": False,
    "peer_raw_state_imported": False,
    "v398_gate_cannot_be_bypassed": True,
})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _default_gap() -> dict[str, Any]:
    return {
        "observations": 0,
        "consecutive_failures": 0,
        "last_seen_cycle": 0,
        "last_status": "unknown",
    }


def _default_state() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "controller_version": CONTROLLER_VERSION,
        "cycle": 0,
        "gap_memory": {},
        "history": [],
    }


def _valid_state(value: Any) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "schema_version", "controller_version", "cycle", "gap_memory", "history",
    }:
        return False
    if value["schema_version"] != 1 or value["controller_version"] != CONTROLLER_VERSION:
        return False
    if not isinstance(value["cycle"], int) or isinstance(value["cycle"], bool) or value["cycle"] < 0:
        return False
    memory = value["gap_memory"]
    if not isinstance(memory, dict) or len(memory) > MAX_GAPS:
        return False
    required = set(_default_gap())
    for key, row in memory.items():
        if not isinstance(key, str) or not key or len(key) > 160:
            return False
        if not isinstance(row, dict) or set(row) != required:
            return False
        for number_key in ("observations", "consecutive_failures", "last_seen_cycle"):
            if not isinstance(row[number_key], int) or isinstance(row[number_key], bool) or row[number_key] < 0:
                return False
        if row["last_status"] not in {"pass", "fail", "unknown"}:
            return False
    return isinstance(value["history"], list) and len(value["history"]) <= MAX_HISTORY


def load_state(path: Path = STATE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"state": _default_state(), "status": "fresh", "corruption_hold": False}
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError("UNSAFE_V399_STATE_PATH")
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
            "error_code": "V399_STATE_SCHEMA_INVALID",
        }
    return {"state": value, "status": "loaded", "corruption_hold": False}


def save_state(state: dict[str, Any], path: Path, *, corruption_hold: bool) -> dict[str, Any]:
    if corruption_hold:
        return {"status": "V399_STATE_CORRUPTION_HOLD", "written": False}
    if not _valid_state(state):
        return {"status": "V399_STATE_INVALID", "written": False}
    try:
        atomic_write_json(path, state, suffix=".v399-state.tmp")
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        return {"status": "V399_STATE_WRITE_FAILED", "written": False, "error_code": type(exc).__name__}
    return {"status": "V399_STATE_SAVED", "written": True}


def _text(root: Path, relative: str, *, max_bytes: int = 3_000_000) -> str:
    path = root / relative
    try:
        if not path.is_file() or path.is_symlink():
            return ""
        return safe_read_text(path, max_bytes=max_bytes)
    except (OSError, UnicodeError, ValueError, TypeError):
        return ""


def ui_runtime_health(root: Path = ROOT) -> dict[str, Any]:
    index = _text(root, "index.html")
    css = _text(root, "tablet_autonomy_dashboard_v399.css")
    js = _text(root, "tablet_autonomy_dashboard_v399.js")
    sw = _text(root, "sw.js")
    updater = _text(root, "tcg_updater.py")
    manifest = _text(root, "tablet_runtime_manifest.py")
    main = _text(root, "main")

    checks = [
        ("dashboard_js_file", bool(js), "ui", True),
        ("dashboard_css_file", bool(css), "ui", True),
        ("index_dashboard_css", "tablet_autonomy_dashboard_v399.css" in index, "ui", True),
        ("index_dashboard_js", "tablet_autonomy_dashboard_v399.js" in index, "ui", True),
        ("dashboard_report_binding", "tablet_autonomy_v399_report.json" in js, "ui", True),
        ("dashboard_accessibility", "aria-live" in js and "prefers-reduced-motion" in css, "ui", False),
        ("pwa_dashboard_assets", "tablet_autonomy_dashboard_v399.js" in sw and "tablet_autonomy_dashboard_v399.css" in sw, "pwa", True),
        ("static_report_exposure", "tablet_autonomy_v399_report.json" in updater, "server", True),
        ("runtime_manifest_controller", "tablet_autonomous_evolution_v399.py" in manifest, "runtime", True),
        ("runtime_manifest_dashboard", "tablet_autonomy_dashboard_v399.js" in manifest and "tablet_autonomy_dashboard_v399.css" in manifest, "runtime", True),
        ("main_v399_route", "tablet_autonomous_evolution_v399.py --domain tablet_gpt" in main, "runtime", True),
        ("viewport_contract", 'name="viewport"' in index, "ui", False),
        ("tablet_manager_anchor", 'id="tabletManagerHub"' in index, "ui", False),
    ]
    rows = [
        {
            "check_id": check_id,
            "ok": bool(ok),
            "component": component,
            "critical": bool(critical),
        }
        for check_id, ok, component, critical in checks
    ]
    passed = sum(1 for row in rows if row["ok"])
    failed = [row for row in rows if not row["ok"]]
    critical_failed = [row for row in failed if row["critical"]]
    return {
        "score": round(passed / max(1, len(rows)), 6),
        "passed": passed,
        "total": len(rows),
        "failed": len(failed),
        "critical_failed": len(critical_failed),
        "checks": rows,
        "healthy": not critical_failed,
    }


def composition_policy(base: dict[str, Any], health: dict[str, Any]) -> dict[str, Any]:
    gate = base.get("v398_autonomous_gate") if isinstance(base.get("v398_autonomous_gate"), dict) else {}
    mode = base.get("v398_operating_mode") if isinstance(base.get("v398_operating_mode"), dict) else {}
    mode_name = str(mode.get("mode") or "STEADY_OPTIMIZATION")
    active = base.get("v398_active_evaluation") if isinstance(base.get("v398_active_evaluation"), dict) else {}
    if gate.get("allow_execution") is not True or health.get("critical_failed"):
        surface = "ATTENTION"
        refresh = 30
    elif "RECOVERY" in mode_name or active.get("rollback") is True:
        surface = "RECOVERY_FOCUS"
        refresh = 30
    elif "LEARNING" in mode_name or "OPTIMIZATION" in mode_name:
        surface = "LEARNING_FOCUS"
        refresh = 45
    else:
        surface = "STEADY"
        refresh = 60
    return {
        "surface_mode": surface,
        "refresh_seconds": refresh,
        "primary_sections": ["autonomy", "tablet_runtime", "market_health", "quality"],
        "touch_first": True,
        "compact_tablet_layout": True,
        "reduced_motion_respected": True,
        "source_layout_auto_rewrite": False,
    }


def update_gap_memory(state: dict[str, Any], health: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    cycle = int(state.get("cycle") or 0) + 1
    memory = deepcopy(state.get("gap_memory") or {})
    candidates = []
    for check in health.get("checks", []):
        if not isinstance(check, dict):
            continue
        check_id = str(check.get("check_id") or "")[:160]
        if not check_id:
            continue
        row = deepcopy(memory.get(check_id)) if isinstance(memory.get(check_id), dict) else _default_gap()
        row["observations"] = min(1_000_000, int(row["observations"]) + 1)
        row["last_seen_cycle"] = cycle
        if check.get("ok") is True:
            row["consecutive_failures"] = 0
            row["last_status"] = "pass"
        else:
            row["consecutive_failures"] = min(1_000_000, int(row["consecutive_failures"]) + 1)
            row["last_status"] = "fail"
            recurrence = int(row["consecutive_failures"])
            candidates.append({
                "candidate_id": "UI_GAP:" + check_id,
                "check_id": check_id,
                "component": str(check.get("component") or "ui"),
                "critical": bool(check.get("critical")),
                "recurrence": recurrence,
                "stage": "protected_pr_candidate" if recurrence >= PROTECTED_PR_RECURRENCE else "observe",
                "auto_execute": False,
                "auto_generate_source": False,
                "auto_rewrite_source": False,
                "git_write": False,
                "protected_pr_ci_required": True,
                "validation_required": [
                    "targeted_ui_test",
                    "browser_runtime_check",
                    "pwa_cache_check",
                    "tablet_runtime_manifest_check",
                    "repository_integrity",
                    "tablet_gpt_tcg_grader_alignment",
                    "actual_tablet_output_validation",
                ],
            })
        memory[check_id] = row
    memory = dict(sorted(
        memory.items(),
        key=lambda pair: (-int(pair[1]["consecutive_failures"]), -int(pair[1]["last_seen_cycle"]), pair[0]),
    )[:MAX_GAPS])
    candidates.sort(key=lambda row: (not row["critical"], -row["recurrence"], row["check_id"]))
    return {
        "schema_version": 1,
        "controller_version": CONTROLLER_VERSION,
        "cycle": cycle,
        "gap_memory": memory,
        "history": list(state.get("history") or []),
    }, candidates


def _append_history(
    state: dict[str, Any],
    *,
    base: dict[str, Any],
    health: dict[str, Any],
    policy: dict[str, Any],
    candidates: list[dict[str, Any]],
    now: datetime,
) -> dict[str, Any]:
    result = deepcopy(state)
    tournament = base.get("v398_candidate_tournament") if isinstance(base.get("v398_candidate_tournament"), dict) else {}
    history = list(result.get("history") or [])
    history.append({
        "observed_at": now.isoformat(timespec="seconds"),
        "cycle": result["cycle"],
        "v398_status": base.get("v398_status"),
        "surface_mode": policy["surface_mode"],
        "ui_health_score": health["score"],
        "ui_failed": health["failed"],
        "ui_protected_pr_candidates": sum(row["stage"] == "protected_pr_candidate" for row in candidates),
        "v398_candidate_count": tournament.get("candidate_count"),
        "v398_selected_recipe": tournament.get("selected_recipe_key"),
    })
    result["history"] = history[-MAX_HISTORY:]
    return result


def _ui_summary(base: dict[str, Any], health: dict[str, Any], policy: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    tournament = base.get("v398_candidate_tournament") if isinstance(base.get("v398_candidate_tournament"), dict) else {}
    selected = tournament.get("selected_capability") if isinstance(tournament.get("selected_capability"), dict) else {}
    evaluation = base.get("v398_active_evaluation") if isinstance(base.get("v398_active_evaluation"), dict) else {}
    mode = base.get("v398_operating_mode") if isinstance(base.get("v398_operating_mode"), dict) else {}
    plan = base.get("v390_goal_plan") if isinstance(base.get("v390_goal_plan"), dict) else {}
    primary = plan.get("primary_goal") if isinstance(plan.get("primary_goal"), dict) else {}
    critic = base.get("v390_meta_critic") if isinstance(base.get("v390_meta_critic"), dict) else {}
    memory = base.get("v398_self_extension") if isinstance(base.get("v398_self_extension"), dict) else {}
    return {
        "controller_version": CONTROLLER_VERSION,
        "core_controller": "v398",
        "surface_mode": policy["surface_mode"],
        "refresh_seconds": policy["refresh_seconds"],
        "operating_mode": mode.get("mode"),
        "primary_goal": primary.get("goal_id"),
        "goal_urgency": primary.get("urgency"),
        "critic_samples": critic.get("sample_count"),
        "candidate_count": tournament.get("candidate_count", 0),
        "selected_capability": selected.get("primitive"),
        "selected_score": tournament.get("selected_score"),
        "active_evaluation": evaluation.get("status"),
        "rollback_required": bool(evaluation.get("rollback")),
        "new_capability_written": bool((memory.get("write") or {}).get("written")) if isinstance(memory.get("write"), dict) else False,
        "gate_status": (base.get("v398_autonomous_gate") or {}).get("status") if isinstance(base.get("v398_autonomous_gate"), dict) else None,
        "ui_health_score": health["score"],
        "ui_checks_passed": health["passed"],
        "ui_checks_total": health["total"],
        "ui_critical_failed": health["critical_failed"],
        "ui_source_candidates": len(candidates),
        "ui_protected_pr_candidates": sum(row["stage"] == "protected_pr_candidate" for row in candidates),
        "physical_tablet_runtime_verified": False,
    }


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
    if mutating:
        fd, _ = v398.v397.v391.v390.v388.v387.v386.v385._acquire_lock(root / LOCK_PATH.name)
        if fd is None:
            return {
                "controller_version": CONTROLLER_VERSION,
                "v399_status": "V399_CONCURRENT_AUTONOMY_HOLD",
                "execution": {
                    "status": "V399_CONCURRENT_AUTONOMY_HOLD",
                    "executed": False,
                    "git_write": False,
                    "source_code_modified": False,
                },
                "safety": SAFETY,
            }

    try:
        preview = v398.run_cycle(
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
        health = ui_runtime_health(root)
        policy = composition_policy(preview, health)
        next_state, ui_candidates = update_gap_memory(loaded["state"], health)

        gate = preview.get("v398_autonomous_gate") if isinstance(preview.get("v398_autonomous_gate"), dict) else {}
        allow = gate.get("allow_execution") is True and not loaded.get("corruption_hold")
        status = "PLAN_ONLY" if not mutating else (
            "V399_VERIFIED_ALLOW" if allow
            else "V399_STATE_CORRUPTION_HOLD" if loaded.get("corruption_hold")
            else "V399_UPSTREAM_HOLD"
        )

        base = preview
        if mutating and allow:
            base = v398.run_cycle(
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
            if str(base.get("v398_status") or "") in getattr(v398, "_HOLD_STATUSES", set()):
                allow = False
                status = "V399_UPSTREAM_HOLD"

        next_state = _append_history(
            next_state,
            base=base,
            health=health,
            policy=policy,
            candidates=ui_candidates,
            now=moment,
        )

        result = deepcopy(base)
        result.update({
            "core_controller_version": str(base.get("controller_version") or CORE_CONTROLLER_VERSION),
            "controller_version": CONTROLLER_VERSION,
            "v399_status": status,
            "v399_ui_runtime_health": health,
            "v399_composition_policy": policy,
            "v399_ui_feature_candidates": ui_candidates,
            "v399_autonomous_gate": {
                "status": status,
                "allow_execution": allow,
                "v398_gate_required": True,
                "hard_blocker_override": False,
            },
            "v399_ui": _ui_summary(base, health, policy, ui_candidates),
            "evolution_contract_v399": {
                "core": "v398_verified_multi_candidate_self_evolution",
                "extended_scope": "ui_ux_pwa_static_server_runtime_manifest",
                "gap_learning": "device_local_recurrence_memory_only",
                "runtime_self_extension": "v398_canonical_v373_capability_tournament_unchanged",
                "ui_source_extension": "non_executable_protected_pr_ci_candidate_only",
                "source_code_auto_generation": False,
                "source_code_auto_rewrite": False,
                "ui_source_auto_rewrite": False,
                "git_write": False,
                "v398_and_prior_gate_bypass": False,
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

        state_write = {"status": "V399_STATE_WRITE_NOT_REQUESTED", "written": False}
        if mutating:
            state_write = save_state(next_state, state_file, corruption_hold=bool(loaded.get("corruption_hold")))
            if not state_write.get("written") and allow:
                result["v399_status"] = "V399_STATE_COMMIT_HOLD"
                result["v399_autonomous_gate"] = {
                    **result["v399_autonomous_gate"],
                    "status": "V399_STATE_COMMIT_HOLD",
                    "allow_execution": False,
                }
                result["execution"] = {
                    "status": "V399_STATE_COMMIT_HOLD",
                    "executed": False,
                    "git_write": False,
                    "source_code_modified": False,
                    "proposals_executed": False,
                }
        result["v399_state_write"] = state_write

        if persist_outputs:
            try:
                atomic_write_json(
                    root / UI_CANDIDATE_PATH.name,
                    {
                        "schema_version": 1,
                        "controller_version": CONTROLLER_VERSION,
                        "generated_at": moment.isoformat(timespec="seconds"),
                        "health": health,
                        "composition_policy": policy,
                        "candidates": ui_candidates,
                        "auto_execute": False,
                        "auto_generate_source": False,
                        "auto_rewrite_source": False,
                        "git_write": False,
                        "protected_pr_ci_required": True,
                    },
                    suffix=".v399-ui-candidates.tmp",
                )
                atomic_write_json(root / REPORT_PATH.name, result, suffix=".v399-report.tmp")
                result["v399_runtime_output"] = {"status": "SAVED"}
            except (OSError, UnicodeError, ValueError, TypeError) as exc:
                result["v399_runtime_output"] = {
                    "status": "WRITE_FAILED",
                    "error_code": type(exc).__name__,
                }
        return result
    finally:
        if fd is not None:
            v398.v397.v391.v390.v388.v387.v386.v385._release_lock(fd)


def self_test() -> None:
    assert _valid_state(_default_state())
    assert SAFETY["cross_surface_self_diagnosis_enabled"] is True
    assert SAFETY["ui_gap_recurrence_learning_enabled"] is True
    assert SAFETY["ui_source_feature_candidates_non_executable"] is True
    assert SAFETY["runtime_source_code_auto_generation"] is False
    assert SAFETY["git_write"] is False
    assert SAFETY["market_direction_inferred"] is False
    print("Tablet cross-surface self-evolution supervisor v399: PASS")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--domain", choices=sorted(v398.v397.v391.v390.v388.v387.v386.DOMAINS), default="tablet_gpt")
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
        domain=args.domain,
        execute=args.execute_safe_learning,
        apply_capabilities=args.apply_capabilities,
        train_meta=args.train_meta,
        apply_skills=args.apply_skills,
    )
    if not args.quiet:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 2 if result.get("v399_status") in _HOLD_STATUSES else 0


if __name__ == "__main__":
    raise SystemExit(main())
