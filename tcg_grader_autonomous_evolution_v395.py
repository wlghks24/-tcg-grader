#!/usr/bin/env python3
"""TCG Grader V395 active-learning and source-reliability autonomy.

V395 extends V394 with three bounded capabilities:
1) verified active-learning target selection: decides which company/game/vision
   segment needs more official RAW labels next;
2) operational source-reliability policy: reads existing provider/search health
   learners and classifies routes for healthy/degraded/cooldown/exploration use
   without changing factual trust;
3) resource-aware execution: protects the grading runtime under low headroom
   and enables progressively heavier verified learning only when resources
   permit.

V394/V393 remain the hard model tournament, promotion, canary and rollback
gates. This module never invents grades/prices, predicts market direction,
rewrites source code, or bypasses verification.
"""
from __future__ import annotations

import argparse
import json
import math
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import provider_health_learning
import search_method_learning
import tcg_grader_autonomous_evolution_v394 as v394
import vision_calibration as vision_learning
from safe_runtime import atomic_write_json

ROOT = Path(__file__).resolve().parent
CONTROLLER_VERSION = "tcg-grader-v395"
CORE_CONTROLLER_VERSION = "tcg-grader-v394"
REPORT_PATH = ROOT / "tcg_grader_autonomy_v395_report.json"
PLAN_PATH = ROOT / "tcg_grader_autonomy_v395_plan.json"

ACTIVE_TARGET_LIMIT = 12
MIN_SEGMENT_READY_ROWS = 12
SOURCE_POLICY_LIMIT = 40

SAFETY = dict(v394.SAFETY)
SAFETY.update({
    "verified_active_learning": True,
    "active_learning_priority_only": True,
    "synthetic_label_training": False,
    "source_reliability_operational_only": True,
    "source_reliability_changes_factual_trust": False,
    "temporary_source_cooldown_only": True,
    "resource_aware_learning_budget": True,
    "low_headroom_runtime_protection": True,
    "market_regime_adaptation_non_directional": True,
    "new_source_primitive_protected_pr_ci_required": True,
    "source_code_auto_generation": False,
    "source_code_auto_rewrite": False,
    "direct_main_write": False,
    "git_write": False,
    "arbitrary_command_execution": False,
    "verification_bypass": False,
    "market_direction_inferred": False,
    "price_or_grade_invention": False,
})


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


def _segment_key(row: dict[str, Any]) -> tuple[str, str, str]:
    company = str(row.get("company") or "UNKNOWN")
    game = str(row.get("game") or "unknown")
    vision = row.get("vision")
    bucket = vision_learning.vision_bucket(vision) if isinstance(vision, dict) else None
    return company, game, bucket or "no-vision-bucket"


def active_learning_targets(
    rows: list[dict[str, Any]],
    drift: dict[str, Any],
    evidence: dict[str, Any],
    *,
    limit: int = ACTIVE_TARGET_LIMIT,
) -> list[dict[str, Any]]:
    """Rank verified-data acquisition targets without fabricating labels."""
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        grouped.setdefault(_segment_key(row), []).append(row)

    targets: list[dict[str, Any]] = []
    companies = evidence.get("companies") if isinstance(evidence, dict) else {}
    companies = companies if isinstance(companies, dict) else {}
    drift_companies = drift.get("companies") if isinstance(drift, dict) else {}
    drift_companies = drift_companies if isinstance(drift_companies, dict) else {}

    for (company, game, bucket), group in grouped.items():
        errors = [
            abs(float(row["raw_pred"]) - float(row["actual"]))
            for row in group
            if _finite(row.get("raw_pred")) is not None and _finite(row.get("actual")) is not None
        ]
        mean_error = sum(errors) / max(1, len(errors))
        unique_cards = len({str(row.get("card_id") or "") for row in group if row.get("card_id")})
        scarcity = _clamp(1.0 - min(1.0, len(group) / float(MIN_SEGMENT_READY_ROWS * 2)))
        error_pressure = _clamp(mean_error / 1.5)
        company_evidence = companies.get(company, {})
        company_evidence = company_evidence if isinstance(company_evidence, dict) else {}
        evidence_score = _clamp(float(_finite(company_evidence.get("evidence_score")) or 0.0))
        drift_row = drift_companies.get(company, {})
        drift_row = drift_row if isinstance(drift_row, dict) else {}
        drift_severity = _clamp(float(_finite(drift_row.get("severity")) or 0.0))
        diversity_gap = _clamp(1.0 - min(1.0, unique_cards / float(MIN_SEGMENT_READY_ROWS)))

        priority = (
            scarcity * 0.34
            + error_pressure * 0.31
            + drift_severity * 0.17
            + (1.0 - evidence_score) * 0.10
            + diversity_gap * 0.08
        )
        targets.append({
            "company": company,
            "game": game,
            "vision_bucket": bucket,
            "verified_rows": len(group),
            "unique_cards": unique_cards,
            "mean_raw_error": round(mean_error, 4),
            "scarcity": round(scarcity, 6),
            "error_pressure": round(error_pressure, 6),
            "drift_severity": round(drift_severity, 6),
            "priority": round(_clamp(priority), 6),
            "requested_evidence": "official-registry-verified independent RAW sample",
            "synthetic_label_allowed": False,
        })

    # Companies with zero rows must also remain visible to the acquisition planner.
    for company, company_evidence in companies.items():
        if not isinstance(company_evidence, dict):
            continue
        if int(company_evidence.get("verified_rows") or 0) > 0:
            continue
        targets.append({
            "company": company,
            "game": "any-supported",
            "vision_bucket": "coverage-gap",
            "verified_rows": 0,
            "unique_cards": 0,
            "mean_raw_error": None,
            "scarcity": 1.0,
            "error_pressure": 0.0,
            "drift_severity": 0.0,
            "priority": 0.92,
            "requested_evidence": "official-registry-verified independent RAW sample",
            "synthetic_label_allowed": False,
        })

    targets.sort(
        key=lambda row: (
            -float(row["priority"]),
            row["company"],
            row["game"],
            row["vision_bucket"],
        )
    )
    return targets[:max(1, min(ACTIVE_TARGET_LIMIT, int(limit)))]


def _provider_policy(row: dict[str, Any]) -> dict[str, Any]:
    configured = max(0, int(row.get("configured_runs") or 0))
    errors = max(0, int(row.get("errors") or 0))
    error_rate = errors / max(1, configured)
    response = _clamp(float(_finite(row.get("response_rate")) or 0.0))
    error_streak = max(0, int(row.get("error_streak") or 0))
    empty_streak = max(0, int(row.get("empty_streak") or 0))
    if configured < 3:
        state, action = "EXPLORATION", "KEEP_BOUNDED_EXPLORATION"
    elif error_streak >= 3 or error_rate >= 0.50:
        state, action = "COOLDOWN", "DEFER_AND_RETRY_LATER"
    elif response < 0.35 or empty_streak >= 4:
        state, action = "DEGRADED", "LOWER_OPERATIONAL_PRIORITY"
    else:
        state, action = "HEALTHY", "NORMAL_OPERATIONAL_PRIORITY"
    return {
        "kind": "provider",
        "name": str(row.get("provider") or "unknown")[:120],
        "state": state,
        "action": action,
        "configured_runs": configured,
        "response_rate": round(response, 4),
        "error_rate": round(error_rate, 4),
        "error_streak": error_streak,
        "empty_streak": empty_streak,
        "factual_trust_changed": False,
        "permanent_blacklist": False,
    }


def _method_policy(row: dict[str, Any]) -> dict[str, Any]:
    attempts = max(0, int(row.get("attempts") or 0))
    response = _clamp(float(_finite(row.get("response_rate")) or 0.0))
    nonempty = _clamp(float(_finite(row.get("nonempty_rate")) or 0.0))
    blocked = _clamp(float(_finite(row.get("blocked_rate")) or 0.0))
    limited = _clamp(float(_finite(row.get("rate_limited_rate")) or 0.0))
    timeout = _clamp(float(_finite(row.get("timeout_rate")) or 0.0))
    failure_streak = max(0, int(row.get("failure_streak") or 0))
    cooling = row.get("cooling_down") is True
    failure_pressure = _clamp(blocked + limited + timeout)

    if attempts < 3:
        state, action = "EXPLORATION", "KEEP_BOUNDED_EXPLORATION"
    elif cooling or failure_streak >= 3 or failure_pressure >= 0.40:
        state, action = "COOLDOWN", "HONOR_EXISTING_COOLDOWN"
    elif response < 0.35 or nonempty < 0.20:
        state, action = "DEGRADED", "LOWER_OPERATIONAL_PRIORITY"
    else:
        state, action = "HEALTHY", "NORMAL_OPERATIONAL_PRIORITY"
    return {
        "kind": "search_method",
        "name": str(row.get("method") or "unknown")[:120],
        "state": state,
        "action": action,
        "attempts": attempts,
        "response_rate": round(response, 4),
        "nonempty_rate": round(nonempty, 4),
        "failure_pressure": round(failure_pressure, 4),
        "failure_streak": failure_streak,
        "cooling_down": cooling,
        "factual_trust_changed": False,
        "permanent_blacklist": False,
    }


def source_reliability_policy(
    provider_report: dict[str, Any] | None,
    search_report: dict[str, Any] | None,
) -> dict[str, Any]:
    providers = provider_report.get("providers", []) if isinstance(provider_report, dict) else []
    methods = search_report.get("methods", []) if isinstance(search_report, dict) else []
    policies: list[dict[str, Any]] = []
    policies.extend(_provider_policy(row) for row in providers if isinstance(row, dict))
    policies.extend(_method_policy(row) for row in methods if isinstance(row, dict))
    policies = policies[:SOURCE_POLICY_LIMIT]

    counts = {"HEALTHY": 0, "DEGRADED": 0, "COOLDOWN": 0, "EXPLORATION": 0}
    for row in policies:
        counts[row["state"]] = counts.get(row["state"], 0) + 1
    total = max(1, len(policies))
    degraded_ratio = (counts["DEGRADED"] + counts["COOLDOWN"]) / total
    return {
        "routes": policies,
        "counts": counts,
        "route_count": len(policies),
        "degraded_or_cooldown_ratio": round(degraded_ratio, 6),
        "operational_only": True,
        "factual_trust_learning": False,
        "permanent_blacklist": False,
        "recovery_slot_preserved": True,
    }


def read_source_reports() -> dict[str, Any]:
    provider_report: dict[str, Any] | None = None
    search_report: dict[str, Any] | None = None
    errors: list[str] = []
    try:
        value = provider_health_learning.report()
        if isinstance(value, dict):
            provider_report = value
    except Exception as exc:
        errors.append(f"provider:{type(exc).__name__}")
    try:
        value = search_method_learning.SearchMethodLearner().report()
        if isinstance(value, dict):
            search_report = value
    except Exception as exc:
        errors.append(f"search:{type(exc).__name__}")
    return {
        "provider_report": provider_report,
        "search_report": search_report,
        "errors": errors,
        "read_only": True,
    }


def resource_schedule(core: dict[str, Any]) -> dict[str, Any]:
    try:
        observation = v394.v393.v392.observation(core)
    except Exception:
        observation = {}
    dims = observation.get("dimensions") if isinstance(observation, dict) else {}
    dims = dims if isinstance(dims, dict) else {}
    headroom = _clamp(float(_finite(dims.get("resource_headroom")) or 0.5))
    uncertainty = _clamp(float(_finite(observation.get("uncertainty")) or 0.5))
    drift = _clamp(float(_finite(observation.get("drift")) or 0.5))

    if headroom < 0.25:
        mode = "PROTECT_RUNTIME"
        allow_mutation = False
        active_target_budget = 2
        optional_learning = 0.0
    elif headroom < 0.50:
        mode = "LIGHT_LEARNING"
        allow_mutation = True
        active_target_budget = 4
        optional_learning = 0.25
    elif headroom >= 0.75 and max(uncertainty, drift) >= 0.35:
        mode = "INTENSIVE_VERIFIED_LEARNING"
        allow_mutation = True
        active_target_budget = 12
        optional_learning = 1.0
    else:
        mode = "BALANCED"
        allow_mutation = True
        active_target_budget = 8
        optional_learning = 0.60

    return {
        "mode": mode,
        "resource_headroom": round(headroom, 6),
        "uncertainty": round(uncertainty, 6),
        "drift": round(drift, 6),
        "allow_mutation": allow_mutation,
        "optional_learning_budget": optional_learning,
        "active_target_budget": active_target_budget,
        "protect_foreground_grading": mode in {"PROTECT_RUNTIME", "LIGHT_LEARNING"},
    }


def effective_flags(
    schedule: dict[str, Any],
    *,
    execute: bool,
    apply_capabilities: bool,
    train_meta: bool,
    apply_skills: bool,
) -> dict[str, bool]:
    mode = str(schedule.get("mode") or "BALANCED")
    if schedule.get("allow_mutation") is not True:
        return {
            "execute": False,
            "apply_capabilities": False,
            "train_meta": False,
            "apply_skills": False,
        }
    if mode == "LIGHT_LEARNING":
        return {
            "execute": bool(execute),
            "apply_capabilities": bool(apply_capabilities),
            "train_meta": False,
            "apply_skills": False,
        }
    if mode == "BALANCED":
        return {
            "execute": bool(execute),
            "apply_capabilities": bool(apply_capabilities),
            "train_meta": bool(train_meta),
            "apply_skills": False,
        }
    return {
        "execute": bool(execute),
        "apply_capabilities": bool(apply_capabilities),
        "train_meta": bool(train_meta),
        "apply_skills": bool(apply_skills),
    }


def market_operating_mode(core: dict[str, Any], source_policy: dict[str, Any]) -> dict[str, Any]:
    market = core.get("market_adaptation_v381")
    market = market if isinstance(market, dict) else {}
    regime = str(market.get("regime") or "UNKNOWN")[:80]
    stress = _clamp(float(_finite(market.get("stress_score")) or 0.0))
    low_regions = [
        str(region) for region in list(market.get("low_coverage_regions") or [])
        if str(region) in {"KR", "JP", "US"}
    ]
    degraded = _clamp(float(_finite(source_policy.get("degraded_or_cooldown_ratio")) or 0.0))

    if degraded >= 0.40:
        mode = "SOURCE_RECOVERY"
        action = "DEFER_DEGRADED_ROUTES_AND_KEEP_RECOVERY_SLOTS"
    elif low_regions:
        mode = "COVERAGE_EXPANSION"
        action = "PRIORITIZE_LOW_COVERAGE_REGIONS"
    elif stress >= 0.70:
        mode = "HIGH_OBSERVATION"
        action = "INCREASE_NON_DIRECTIONAL_MARKET_OBSERVATION"
    else:
        mode = "NORMAL"
        action = "MAINTAIN_VERIFIED_COLLECTION"
    return {
        "mode": mode,
        "action": action,
        "regime": regime,
        "stress_score": round(stress, 6),
        "low_coverage_regions": low_regions,
        "source_degraded_ratio": round(degraded, 6),
        "market_direction_inferred": False,
    }


def feature_contracts(
    targets: list[dict[str, Any]],
    source_policy: dict[str, Any],
    schedule: dict[str, Any],
) -> list[dict[str, Any]]:
    contracts: list[dict[str, Any]] = []
    if any(float(row.get("priority") or 0.0) >= 0.80 for row in targets):
        contracts.append({
            "feature_id": "TCG_V395_ACTIVE_VERIFIED_LABEL_ACQUISITION",
            "reason": "high-priority verified grading evidence gaps require a bounded acquisition workflow",
        })
    if float(source_policy.get("degraded_or_cooldown_ratio") or 0.0) >= 0.40:
        contracts.append({
            "feature_id": "TCG_V395_SOURCE_HEALTH_RUNTIME_BRIDGE",
            "reason": "many collection routes are degraded/cooling and need explicit runtime route-policy observability",
        })
    if schedule.get("mode") == "PROTECT_RUNTIME":
        contracts.append({
            "feature_id": "TCG_V395_BACKGROUND_LEARNING_RESOURCE_BUDGET",
            "reason": "foreground grading headroom is low; heavy optional learning must remain deferred",
        })
    return [{
        **row,
        "stage": "shadow_spec",
        "auto_execute": False,
        "source_code_generated": False,
        "protected_pr_ci_required": True,
        "promotion_requires": [
            "targeted_tests",
            "grading_holdout",
            "source_health_regression",
            "resource_budget_regression",
            "full_regression",
            "repository_integrity",
            "actual_output_validation",
        ],
    } for row in contracts]


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
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    preview = v394.run_cycle(
        execute=False,
        apply_capabilities=False,
        train_meta=False,
        apply_skills=False,
        root=root,
        now=moment,
        persist_outputs=False,
    )

    rows, audit = v394.v393.grade_learning.eligible_training_rows()
    audit_ok = isinstance(audit, dict) and int(audit.get("eligible") or 0) == len(rows)
    drift = v394.v393.company_drift_report(rows)
    evidence = v394.evidence_report(rows)

    source_reports = read_source_reports()
    source_policy = source_reliability_policy(
        source_reports.get("provider_report"),
        source_reports.get("search_report"),
    )
    schedule = resource_schedule(preview)
    targets = active_learning_targets(
        rows,
        drift,
        evidence,
        limit=int(schedule["active_target_budget"]),
    )
    market_mode = market_operating_mode(preview, source_policy)
    contracts = feature_contracts(targets, source_policy, schedule)

    requested_mutation = bool(execute or apply_capabilities or train_meta or apply_skills)
    blocked = (
        not audit_ok
        or drift.get("critical") is True
        or (preview.get("tcg_grader_autonomy_v394") or {}).get("blocked") is True
    )
    flags = effective_flags(
        schedule,
        execute=execute,
        apply_capabilities=apply_capabilities,
        train_meta=train_meta,
        apply_skills=apply_skills,
    )
    core = preview
    if requested_mutation and not blocked and any(flags.values()):
        core = v394.run_cycle(
            execute=flags["execute"],
            apply_capabilities=flags["apply_capabilities"],
            train_meta=flags["train_meta"],
            apply_skills=flags["apply_skills"],
            root=root,
            now=moment,
            persist_outputs=False,
        )

    result = deepcopy(core)
    result.update({
        "core_controller_version": str(core.get("controller_version") or CORE_CONTROLLER_VERSION),
        "controller_version": CONTROLLER_VERSION,
        "tcg_grader_autonomy_v395": {
            "verified_rows": len(rows),
            "audit_ok": audit_ok,
            "blocked": blocked,
            "resource_schedule": schedule,
            "effective_mutation_flags": flags,
            "active_learning_targets": targets,
            "source_reliability": source_policy,
            "source_report_errors": source_reports.get("errors") or [],
            "market_operating_mode": market_mode,
            "source_feature_contracts": contracts,
            "closed_loop": (
                "observe->resource-budget->company-drift/evidence->active-learning-targets->"
                "source-health-policy->market-operating-mode->V394-candidate-tournament->"
                "V393-promotion/canary/rollback->reobserve"
            ),
        },
        "safety": SAFETY,
    })

    if persist_outputs:
        plan = {
            "schema_version": 1,
            "controller_version": CONTROLLER_VERSION,
            "generated_at": moment.isoformat(timespec="seconds"),
            "blocked": blocked,
            "resource_schedule": schedule,
            "effective_mutation_flags": flags,
            "active_learning_targets": targets,
            "source_reliability": source_policy,
            "market_operating_mode": market_mode,
            "source_feature_contracts": contracts,
        }
        try:
            atomic_write_json(root / PLAN_PATH.name, plan, suffix=".v395-plan.tmp")
            atomic_write_json(root / REPORT_PATH.name, result, suffix=".v395-report.tmp")
            result["tcg_grader_v395_runtime_output"] = {"status": "SAVED"}
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            result["tcg_grader_v395_runtime_output"] = {
                "status": "WRITE_FAILED",
                "error_code": type(exc).__name__,
            }
    return result


def self_test() -> None:
    assert SAFETY["verified_active_learning"] is True
    assert SAFETY["synthetic_label_training"] is False
    assert SAFETY["source_reliability_changes_factual_trust"] is False
    assert SAFETY["low_headroom_runtime_protection"] is True
    assert SAFETY["source_code_auto_generation"] is False
    assert SAFETY["market_direction_inferred"] is False
    print("TCG Grader active-learning/source-reliability autonomy v395: PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description="TCG Grader V395 active-learning autonomy")
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
        payload = result.get("tcg_grader_autonomy_v395") or {}
        print(json.dumps({
            "controller_version": result.get("controller_version"),
            "verified_rows": payload.get("verified_rows"),
            "blocked": payload.get("blocked"),
            "resource_mode": (payload.get("resource_schedule") or {}).get("mode"),
            "market_mode": (payload.get("market_operating_mode") or {}).get("mode"),
            "top_targets": (payload.get("active_learning_targets") or [])[:3],
            "source_counts": (payload.get("source_reliability") or {}).get("counts"),
        }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
