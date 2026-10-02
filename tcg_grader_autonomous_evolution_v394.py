#!/usr/bin/env python3
"""TCG Grader V394 multi-candidate autonomous policy layer.

Extends V393 with company-specialist policy, evidence sufficiency scoring,
multiple bounded candidate strategies, deterministic verified holdout
tournament selection, and fail-closed recovery recommendations.

This controller never invents grades/prices, never predicts market direction,
never rewrites source code, and never bypasses V393 verification gates.
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

import grading_accuracy_v99 as grade_accuracy
import tcg_grader_autonomous_evolution_v393 as v393
import vision_calibration as vision_learning
from safe_runtime import atomic_write_json

ROOT = Path(__file__).resolve().parent
CONTROLLER_VERSION = "tcg-grader-v394"
CORE_CONTROLLER_VERSION = "tcg-grader-v393"
REPORT_PATH = ROOT / "tcg_grader_autonomy_v394_report.json"
PLAN_PATH = ROOT / "tcg_grader_autonomy_v394_plan.json"
COMPANIES = tuple(grade_accuracy.COMPANIES)

MIN_SPECIALIST_ROWS = 12
MIN_TOURNAMENT_ROWS = 20
MIN_HOLDOUT_ROWS = 5
MAX_CANDIDATES = 4

SAFETY = dict(v393.SAFETY)
SAFETY.update({
    "company_specialist_policy": True,
    "multi_candidate_verified_tournament": True,
    "evidence_sufficiency_gate": True,
    "bounded_candidate_strategies_only": True,
    "verified_holdout_winner_selection": True,
    "automatic_recovery_recommendations": True,
    "candidate_source_mutation": False,
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


def evidence_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    per_company: dict[str, Any] = {}
    ready = 0
    for company in COMPANIES:
        group = [row for row in rows if row.get("company") == company]
        certs = {str(row.get("certification_id") or "") for row in group if row.get("certification_id")}
        cards = {str(row.get("card_id") or "") for row in group if row.get("card_id")}
        vision_rows = sum(1 for row in group if isinstance(row.get("vision"), dict))
        score = _clamp(
            min(1.0, len(group) / 30.0) * 0.55
            + min(1.0, len(certs) / 20.0) * 0.20
            + min(1.0, len(cards) / 20.0) * 0.10
            + (vision_rows / max(1, len(group))) * 0.15
        )
        status = "ready" if len(group) >= MIN_SPECIALIST_ROWS and score >= 0.55 else "collect_more"
        if status == "ready":
            ready += 1
        per_company[company] = {
            "verified_rows": len(group),
            "unique_certifications": len(certs),
            "unique_cards": len(cards),
            "vision_rows": vision_rows,
            "evidence_score": round(score, 6),
            "status": status,
        }
    return {
        "companies": per_company,
        "ready_companies": ready,
        "total_companies": len(COMPANIES),
        "global_verified_rows": len(rows),
    }


def company_policy(
    rows: list[dict[str, Any]],
    drift: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    policies: dict[str, Any] = {}
    for company in COMPANIES:
        ev = evidence["companies"][company]
        dr = (drift.get("companies") or {}).get(company, {})
        severity = float(dr.get("severity") or 0.0)
        if dr.get("status") == "critical":
            action = "FREEZE_AND_REVERIFY"
            priority = 1.0
        elif ev["status"] != "ready":
            action = "EXPAND_VERIFIED_LABELS"
            priority = 0.90
        elif dr.get("status") == "watch":
            action = "SHADOW_RECALIBRATION"
            priority = max(0.72, severity)
        else:
            action = "HOLD_OR_CANARY"
            priority = 0.35 + 0.25 * severity
        policies[company] = {
            "action": action,
            "priority": round(_clamp(priority), 6),
            "evidence_score": ev["evidence_score"],
            "drift_status": dr.get("status", "insufficient_verified_sequence"),
            "auto_source_change": False,
        }
    ranked = sorted(
        policies.items(),
        key=lambda item: (-float(item[1]["priority"]), item[0]),
    )
    return {"companies": policies, "ranked": [name for name, _ in ranked]}


def _candidate_id(strategy: str, rows: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256(strategy.encode("utf-8"))
    for row in sorted(rows, key=v393._row_key):
        digest.update(v393._row_key(row).encode("utf-8"))
        digest.update(f"|{row.get('actual')}|{row.get('raw_pred')}".encode("utf-8"))
    return digest.hexdigest()[:20]


def _base_models(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return grade_accuracy.train_company_calibration(rows)


def build_candidate(strategy: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Build only bounded, interpretable candidates from verified rows."""
    models = deepcopy(_base_models(rows))
    payload = {"v99_validation": rows, "v30_validation": [], "v11_validation": []}
    vision_rows = vision_learning.sanitize_rows(payload)
    vision = vision_learning.train_calibration(vision_rows, models)
    profiles = dict(vision.get("profiles") or {})

    if strategy == "global_only":
        profiles = {}
    elif strategy == "conservative":
        for row in models.values():
            if isinstance(row, dict) and row.get("enabled") is True:
                row["correction"] = round(float(row.get("correction") or 0.0) * 0.75, 4)
        for row in profiles.values():
            if isinstance(row, dict) and row.get("enabled") is True:
                row["correction"] = round(float(row.get("correction") or 0.0) * 0.75, 4)
    elif strategy == "vision_specialist":
        pass
    elif strategy == "company_guarded":
        counts = {company: sum(1 for row in rows if row.get("company") == company) for company in COMPANIES}
        for company, row in models.items():
            if isinstance(row, dict) and counts.get(company, 0) < MIN_SPECIALIST_ROWS:
                row["enabled"] = False
                row["correction"] = 0.0
        profiles = {
            key: value
            for key, value in profiles.items()
            if counts.get(key.split("|", 1)[0], 0) >= MIN_SPECIALIST_ROWS
        }
    else:
        raise ValueError("unsupported_candidate_strategy")

    return {
        "snapshot_id": _candidate_id(strategy, rows),
        "tag": f"v394:{strategy}",
        "strategy": strategy,
        "training_rows": len(rows),
        "global_models": models,
        "vision_profiles": profiles,
        "vision_payload": vision,
        "promotion_evaluation": {"candidate_mae": None},
    }


def candidate_strategies(rows: list[dict[str, Any]], evidence: dict[str, Any]) -> list[str]:
    strategies = ["global_only", "conservative", "company_guarded"]
    if sum(1 for row in rows if isinstance(row.get("vision"), dict)) >= MIN_TOURNAMENT_ROWS:
        strategies.append("vision_specialist")
    return strategies[:MAX_CANDIDATES]


def tournament(
    train: list[dict[str, Any]],
    holdout: list[dict[str, Any]],
    evidence: dict[str, Any],
    champion: dict[str, Any] | None,
) -> dict[str, Any]:
    if len(train) + len(holdout) < MIN_TOURNAMENT_ROWS or len(holdout) < MIN_HOLDOUT_ROWS:
        return {
            "status": "INSUFFICIENT_VERIFIED_EVIDENCE",
            "winner": None,
            "candidates": [],
        }
    results: list[dict[str, Any]] = []
    for strategy in candidate_strategies(train, evidence):
        candidate = build_candidate(strategy, train)
        comparison = v393.compare_candidate(candidate, champion, holdout)
        evaluation = comparison.get("candidate") or {}
        mae = _finite(evaluation.get("candidate_mae"))
        worst = _finite(evaluation.get("candidate_worst"))
        gain = _finite(evaluation.get("gain"))
        eligible = comparison.get("eligible_for_promotion") is True
        results.append({
            "strategy": strategy,
            "candidate": candidate,
            "comparison": comparison,
            "eligible": eligible,
            "mae": mae,
            "worst": worst,
            "gain": gain,
        })
    eligible = [row for row in results if row["eligible"] and row["mae"] is not None]
    eligible.sort(key=lambda row: (float(row["mae"]), float(row["worst"] or 99.0), row["strategy"]))
    winner = eligible[0] if eligible else None
    return {
        "status": "WINNER_SELECTED" if winner else "NO_SAFE_WINNER",
        "winner": winner,
        "candidates": results,
    }


def recovery_plan(
    *,
    audit_ok: bool,
    drift: dict[str, Any],
    evidence: dict[str, Any],
    tournament_result: dict[str, Any],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if not audit_ok:
        actions.append({"action": "RECOVER_VERIFIED_GRADE_AUDIT", "priority": 1.0})
    for company in drift.get("critical_companies") or []:
        actions.append({"action": "FREEZE_COMPANY_AND_REVERIFY", "company": company, "priority": 0.98})
    for company, row in evidence.get("companies", {}).items():
        if row.get("status") != "ready":
            actions.append({"action": "EXPAND_VERIFIED_LABELS", "company": company, "priority": 0.82})
    if tournament_result.get("status") == "NO_SAFE_WINNER":
        actions.append({"action": "KEEP_CHAMPION_AND_COLLECT_EVIDENCE", "priority": 0.78})
    actions.sort(key=lambda row: (-float(row["priority"]), row.get("company", ""), row["action"]))
    return actions[:12]


def _public_tournament(result: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for item in result.get("candidates") or []:
        rows.append({
            "strategy": item["strategy"],
            "candidate_id": item["candidate"]["snapshot_id"],
            "eligible": item["eligible"],
            "mae": item["mae"],
            "worst": item["worst"],
            "gain": item["gain"],
            "reasons": item["comparison"].get("reasons") or [],
        })
    winner = result.get("winner")
    return {
        "status": result.get("status"),
        "winner_strategy": winner["strategy"] if winner else None,
        "winner_candidate_id": winner["candidate"]["snapshot_id"] if winner else None,
        "candidates": rows,
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
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    preview = v393.run_cycle(
        execute=False,
        apply_capabilities=False,
        train_meta=False,
        apply_skills=False,
        root=root,
        now=moment,
        persist_outputs=False,
    )
    payload393 = preview.get("tcg_grader_autonomy_v393") or {}
    rows, audit = v393.grade_learning.eligible_training_rows()
    audit_ok = isinstance(audit, dict) and int(audit.get("eligible") or 0) == len(rows)
    drift = v393.company_drift_report(rows)
    evidence = evidence_report(rows)
    policy = company_policy(rows, drift, evidence)

    champion = None
    state_loaded = v393.load_state(root / v393.EXPERIMENT_STATE.name)
    if not state_loaded.get("corruption_hold"):
        champion = state_loaded["state"].get("champion")

    train, holdout = v393.split_train_holdout(rows)
    competition = tournament(train, holdout, evidence, champion)
    recovery = recovery_plan(
        audit_ok=audit_ok,
        drift=drift,
        evidence=evidence,
        tournament_result=competition,
    )

    blocked = (
        not audit_ok
        or drift.get("critical") is True
        or state_loaded.get("corruption_hold") is True
    )
    core = preview
    mutating = bool(execute or apply_capabilities or train_meta or apply_skills)
    if mutating and not blocked:
        core = v393.run_cycle(
            execute=execute,
            apply_capabilities=apply_capabilities,
            train_meta=train_meta,
            apply_skills=apply_skills,
            root=root,
            now=moment,
            persist_outputs=False,
        )

    winner = competition.get("winner")
    promotion = {"status": "V394_NO_SAFE_WINNER", "executed": False}
    if winner and not blocked:
        promotion = v393.maybe_promote(
            rows=rows,
            candidate=winner["candidate"],
            comparison=winner["comparison"],
            drift=drift,
            execute=execute,
            now=moment,
        )

    result = deepcopy(core)
    result.update({
        "core_controller_version": str(core.get("controller_version") or CORE_CONTROLLER_VERSION),
        "controller_version": CONTROLLER_VERSION,
        "tcg_grader_autonomy_v394": {
            "verified_rows": len(rows),
            "audit_ok": audit_ok,
            "blocked": blocked,
            "evidence": evidence,
            "company_policy": policy,
            "company_drift": drift,
            "tournament": _public_tournament(competition),
            "promotion": {k: v for k, v in promotion.items() if k != "champion"},
            "recovery_plan": recovery,
            "closed_loop": (
                "observe->audit->company-drift->evidence-score->specialist-policy->"
                "multi-candidate-shadow->verified-holdout-tournament->winner->"
                "V393-promotion/canary/rollback->reobserve"
            ),
            "market_adaptation": (
                "inherits V393/V392 freshness, coverage, source-health and regime signals; "
                "never infers market direction or invents prices"
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
            "evidence": evidence,
            "company_policy": policy,
            "tournament": _public_tournament(competition),
            "recovery_plan": recovery,
        }
        try:
            atomic_write_json(root / PLAN_PATH.name, plan, suffix=".v394-plan.tmp")
            atomic_write_json(root / REPORT_PATH.name, result, suffix=".v394-report.tmp")
            result["tcg_grader_v394_runtime_output"] = {"status": "SAVED"}
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            result["tcg_grader_v394_runtime_output"] = {
                "status": "WRITE_FAILED",
                "error_code": type(exc).__name__,
            }
    return result


def self_test() -> None:
    assert SAFETY["multi_candidate_verified_tournament"] is True
    assert SAFETY["bounded_candidate_strategies_only"] is True
    assert SAFETY["source_code_auto_generation"] is False
    assert SAFETY["direct_main_write"] is False
    assert SAFETY["market_direction_inferred"] is False
    assert MAX_CANDIDATES <= 4
    print("TCG Grader multi-candidate autonomous policy v394: PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description="TCG Grader V394 multi-candidate autonomy")
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
        payload = result.get("tcg_grader_autonomy_v394") or {}
        print(json.dumps({
            "controller_version": result.get("controller_version"),
            "verified_rows": payload.get("verified_rows"),
            "blocked": payload.get("blocked"),
            "winner": (payload.get("tournament") or {}).get("winner_strategy"),
            "promotion": payload.get("promotion"),
            "top_recovery": (payload.get("recovery_plan") or [])[:3],
        }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
