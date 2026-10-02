#!/usr/bin/env python3
"""TCG Grader V393 verified experiment, canary and rollback controller.

V393 extends V392 with a model-governance loop:
  observe -> detect company drift -> build verified shadow candidate ->
  deterministic holdout comparison -> promote/reject -> canary state ->
  next-cycle re-evaluation -> rollback/hold when verified evidence regresses.

Only official-registry-gated RAW grading samples are used.  Market adaptation
remains operational (freshness/coverage/source health/regime), never directional
price prediction.  Source code is never rewritten by this controller.
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
import tcg_grader_autonomous_evolution_v392 as v392
import verified_grade_learning_v135_safe as grade_learning
import vision_calibration as vision_learning
from safe_runtime import atomic_write_json, exclusive_file_lock, safe_read_text

ROOT = Path(__file__).resolve().parent
CONTROLLER_VERSION = "tcg-grader-v393"
CORE_CONTROLLER_VERSION = "tcg-grader-v392"

EXPERIMENT_STATE = ROOT / "tcg_grader_autonomy_v393_experiments.json"
REPORT_PATH = ROOT / "tcg_grader_autonomy_v393_report.json"
PLAN_PATH = ROOT / "tcg_grader_autonomy_v393_plan.json"

STATE_SCHEMA_VERSION = 1
MAX_STATE_BYTES = 3_000_000
MAX_HISTORY = 128
MIN_EXPERIMENT_ROWS = 15
MIN_HOLDOUT_ROWS = 5
MIN_PROMOTION_GAIN = 0.02
MAX_COMPANY_REGRESSION = 0.10
MAX_WORST_ERROR_REGRESSION = 0.25
ROLLBACK_MARGIN = 0.05
COMPANIES = tuple(grade_accuracy.COMPANIES)

SAFETY = dict(v392.SAFETY)
SAFETY.update({
    "verified_shadow_experiments": True,
    "deterministic_holdout_required": True,
    "company_specific_grading_drift": True,
    "candidate_promotion_requires_verified_gain": True,
    "vision_canary_and_rollback": True,
    "global_calibration_rollback_auto_forced": False,
    "critical_drift_blocks_promotion": True,
    "source_code_auto_generation": False,
    "source_code_auto_rewrite": False,
    "direct_main_write": False,
    "git_write": False,
    "arbitrary_command_execution": False,
    "verification_bypass": False,
    "market_direction_inferred": False,
    "price_or_grade_invention": False,
})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _default_state() -> dict[str, Any]:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "controller_version": CONTROLLER_VERSION,
        "generation": 0,
        "champion": None,
        "canary": None,
        "history": [],
    }


def _valid_metric(value: Any) -> bool:
    number = _finite(value)
    return number is not None and 0.0 <= number <= 10.0


def _valid_snapshot(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, dict):
        return False
    if not isinstance(value.get("snapshot_id"), str) or not value["snapshot_id"]:
        return False
    if not isinstance(value.get("global_models"), dict):
        return False
    if not isinstance(value.get("vision_profiles"), dict):
        return False
    evaluation = value.get("promotion_evaluation")
    if not isinstance(evaluation, dict):
        return False
    mae = evaluation.get("candidate_mae")
    return mae is None or _valid_metric(mae)


def _valid_state(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if set(value) != {"schema_version", "controller_version", "generation", "champion", "canary", "history"}:
        return False
    if value["schema_version"] != STATE_SCHEMA_VERSION or value["controller_version"] != CONTROLLER_VERSION:
        return False
    if not isinstance(value["generation"], int) or not 0 <= value["generation"] <= 10_000_000:
        return False
    if not _valid_snapshot(value["champion"]) or not _valid_snapshot(value["canary"]):
        return False
    return isinstance(value["history"], list) and len(value["history"]) <= MAX_HISTORY


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"state": _default_state(), "status": "fresh", "corruption_hold": False}
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError("unsafe_state_path")
        payload = json.loads(safe_read_text(path, max_bytes=MAX_STATE_BYTES))
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return {
            "state": _default_state(),
            "status": "corrupt",
            "corruption_hold": True,
            "error_code": type(exc).__name__,
        }
    if not _valid_state(payload):
        return {
            "state": _default_state(),
            "status": "corrupt",
            "corruption_hold": True,
            "error_code": "V393_STATE_SCHEMA_INVALID",
        }
    return {"state": payload, "status": "loaded", "corruption_hold": False}


def save_state(path: Path, state: dict[str, Any], *, corruption_hold: bool) -> dict[str, Any]:
    if corruption_hold:
        return {"status": "V393_STATE_CORRUPTION_HOLD", "written": False}
    if not _valid_state(state):
        return {"status": "V393_STATE_INVALID", "written": False}
    try:
        atomic_write_json(path, state, suffix=".v393-state.tmp")
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        return {"status": "V393_STATE_WRITE_FAILED", "written": False, "error_code": type(exc).__name__}
    return {"status": "V393_STATE_SAVED", "written": True}


def _row_key(row: dict[str, Any]) -> str:
    return f"{row.get('company','')}|{row.get('certification_id','')}|{row.get('card_id','')}"


def split_train_holdout(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Stable 80/20 split; fallback guarantees a bounded holdout when possible."""
    holdout = [
        row for row in rows
        if int(hashlib.sha256(_row_key(row).encode("utf-8")).hexdigest()[:8], 16) % 5 == 0
    ]
    hold_ids = {_row_key(row) for row in holdout}
    train = [row for row in rows if _row_key(row) not in hold_ids]
    target = max(1, len(rows) // 5)
    if len(holdout) < min(MIN_HOLDOUT_ROWS, target) and len(rows) >= 5:
        ordered = sorted(rows, key=lambda row: hashlib.sha256(_row_key(row).encode("utf-8")).hexdigest())
        holdout = ordered[::5]
        hold_ids = {_row_key(row) for row in holdout}
        train = [row for row in ordered if _row_key(row) not in hold_ids]
    return train, holdout


def company_drift_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    companies: dict[str, Any] = {}
    critical: list[str] = []
    for company in COMPANIES:
        group = [row for row in rows if row.get("company") == company]
        n = len(group)
        if n < 12:
            companies[company] = {
                "rows": n,
                "status": "insufficient_verified_sequence",
                "severity": 0.0,
            }
            continue
        half = n // 2
        older, recent = group[:half], group[half:]

        def metrics(sample: list[dict[str, Any]]) -> tuple[float, float]:
            residuals = [float(row["raw_pred"]) - float(row["actual"]) for row in sample]
            mae = sum(abs(value) for value in residuals) / max(1, len(residuals))
            bias = sum(residuals) / max(1, len(residuals))
            return mae, bias

        old_mae, old_bias = metrics(older)
        new_mae, new_bias = metrics(recent)
        mae_delta = new_mae - old_mae
        bias_delta = new_bias - old_bias
        severity = _clamp(max(abs(mae_delta) / 0.60, abs(bias_delta) / 0.75))
        status = "critical" if severity >= 0.75 else "watch" if severity >= 0.45 else "stable"
        if status == "critical":
            critical.append(company)
        companies[company] = {
            "rows": n,
            "older_rows": len(older),
            "recent_rows": len(recent),
            "older_raw_mae": round(old_mae, 4),
            "recent_raw_mae": round(new_mae, 4),
            "mae_delta": round(mae_delta, 4),
            "older_overgrade_bias": round(old_bias, 4),
            "recent_overgrade_bias": round(new_bias, 4),
            "bias_delta": round(bias_delta, 4),
            "severity": round(severity, 6),
            "status": status,
        }
    return {
        "companies": companies,
        "critical_companies": critical,
        "critical": bool(critical),
        "interpretation": "verified-grading-evidence drift; not market-direction prediction",
    }


def _snapshot_id(rows: list[dict[str, Any]], *, tag: str) -> str:
    digest = hashlib.sha256()
    digest.update(tag.encode("utf-8"))
    for row in sorted(rows, key=_row_key):
        digest.update(_row_key(row).encode("utf-8"))
        digest.update(f"|{row.get('actual')}|{row.get('raw_pred')}".encode("utf-8"))
    return digest.hexdigest()[:20]


def build_snapshot(rows: list[dict[str, Any]], *, tag: str) -> dict[str, Any]:
    global_models = grade_accuracy.train_company_calibration(rows)
    payload = {"v99_validation": rows, "v30_validation": [], "v11_validation": []}
    vision_rows = vision_learning.sanitize_rows(payload)
    vision = vision_learning.train_calibration(vision_rows, global_models)
    return {
        "snapshot_id": _snapshot_id(rows, tag=tag),
        "tag": tag,
        "training_rows": len(rows),
        "global_models": global_models,
        "vision_profiles": dict(vision.get("profiles") or {}),
        "vision_payload": vision,
        "promotion_evaluation": {"candidate_mae": None},
    }


def production_snapshot(rows: list[dict[str, Any]]) -> dict[str, Any]:
    global_models = grade_accuracy.train_company_calibration(rows)
    calibration = grade_learning.base._load(grade_learning.base.VISION_CALIBRATION, {})
    safe = isinstance(calibration, dict) and calibration.get("registry_gate_v135") is True
    profiles = calibration.get("profiles", {}) if safe else {}
    return {
        "snapshot_id": _snapshot_id(rows, tag="production"),
        "tag": "production",
        "training_rows": len(rows),
        "global_models": global_models,
        "vision_profiles": profiles if isinstance(profiles, dict) else {},
        "vision_payload": calibration if safe else {},
        "promotion_evaluation": {"candidate_mae": None},
    }


def _snapshot_grade(snapshot: dict[str, Any], row: dict[str, Any]) -> float:
    company = str(row.get("company") or "")
    raw = float(row.get("raw_pred") or 1.0)
    global_row = snapshot.get("global_models", {}).get(company, {})
    global_correction = (
        float(global_row.get("correction") or 0.0)
        if isinstance(global_row, dict) and global_row.get("enabled") is True
        else 0.0
    )
    vision_correction = 0.0
    vision = row.get("vision")
    bucket = vision_learning.vision_bucket(vision) if isinstance(vision, dict) else None
    if bucket:
        profile = snapshot.get("vision_profiles", {}).get(f"{company}|{bucket}", {})
        if isinstance(profile, dict) and profile.get("enabled") is True:
            vision_correction = float(profile.get("correction") or 0.0)
    return grade_accuracy.apply_downward_correction(company, raw, global_correction + vision_correction)


def evaluate_snapshot(snapshot: dict[str, Any], holdout: list[dict[str, Any]]) -> dict[str, Any]:
    if not holdout:
        return {
            "rows": 0,
            "candidate_mae": None,
            "baseline_mae": None,
            "candidate_worst": None,
            "baseline_worst": None,
            "gain": None,
            "companies": {},
        }
    candidate_errors: list[float] = []
    baseline_errors: list[float] = []
    company_rows: dict[str, list[tuple[float, float]]] = {company: [] for company in COMPANIES}
    for row in holdout:
        actual = float(row["actual"])
        company = str(row["company"])
        candidate = _snapshot_grade(snapshot, row)
        baseline = grade_accuracy.apply_downward_correction(company, float(row["raw_pred"]), 0.0)
        c_err, b_err = abs(candidate - actual), abs(baseline - actual)
        candidate_errors.append(c_err)
        baseline_errors.append(b_err)
        if company in company_rows:
            company_rows[company].append((c_err, b_err))
    c_mae = sum(candidate_errors) / len(candidate_errors)
    b_mae = sum(baseline_errors) / len(baseline_errors)
    companies: dict[str, Any] = {}
    for company, values in company_rows.items():
        if not values:
            continue
        c = sum(x for x, _ in values) / len(values)
        b = sum(y for _, y in values) / len(values)
        companies[company] = {
            "rows": len(values),
            "candidate_mae": round(c, 4),
            "baseline_mae": round(b, 4),
            "gain": round(b - c, 4),
        }
    return {
        "rows": len(holdout),
        "candidate_mae": round(c_mae, 4),
        "baseline_mae": round(b_mae, 4),
        "candidate_worst": round(max(candidate_errors), 4),
        "baseline_worst": round(max(baseline_errors), 4),
        "gain": round(b_mae - c_mae, 4),
        "companies": companies,
    }


def compare_candidate(
    candidate: dict[str, Any],
    champion: dict[str, Any] | None,
    holdout: list[dict[str, Any]],
) -> dict[str, Any]:
    candidate_eval = evaluate_snapshot(candidate, holdout)
    champion_eval = evaluate_snapshot(champion, holdout) if isinstance(champion, dict) else None
    reasons: list[str] = []
    if candidate_eval["rows"] < MIN_HOLDOUT_ROWS:
        reasons.append("insufficient_holdout")
    gain = _finite(candidate_eval.get("gain"))
    if gain is None or gain < MIN_PROMOTION_GAIN:
        reasons.append("insufficient_verified_gain")
    if (
        _finite(candidate_eval.get("candidate_worst")) is not None
        and _finite(candidate_eval.get("baseline_worst")) is not None
        and float(candidate_eval["candidate_worst"]) > float(candidate_eval["baseline_worst"]) + MAX_WORST_ERROR_REGRESSION
    ):
        reasons.append("worst_error_regression")

    if champion_eval and champion_eval.get("rows"):
        c_mae = _finite(candidate_eval.get("candidate_mae"))
        champ_mae = _finite(champion_eval.get("candidate_mae"))
        if c_mae is None or champ_mae is None or c_mae > champ_mae + 1e-9:
            reasons.append("not_better_than_champion")
        for company, row in candidate_eval.get("companies", {}).items():
            prior = champion_eval.get("companies", {}).get(company)
            if not isinstance(prior, dict) or int(row.get("rows") or 0) < 3:
                continue
            candidate_mae = _finite(row.get("candidate_mae"))
            champion_mae = _finite(prior.get("candidate_mae"))
            if candidate_mae is not None and champion_mae is not None and candidate_mae > champion_mae + MAX_COMPANY_REGRESSION:
                reasons.append(f"company_regression:{company}")

    return {
        "eligible_for_promotion": not reasons,
        "reasons": sorted(set(reasons)),
        "candidate": candidate_eval,
        "champion": champion_eval,
    }


def _capture_deployed_champion(rows: list[dict[str, Any]], evaluation: dict[str, Any], now: datetime) -> dict[str, Any]:
    snap = production_snapshot(rows)
    snap["tag"] = "champion"
    snap["promoted_at"] = now.isoformat(timespec="seconds")
    snap["promotion_evaluation"] = evaluation.get("candidate") or {"candidate_mae": None}
    return snap


def maybe_promote(
    *,
    rows: list[dict[str, Any]],
    candidate: dict[str, Any],
    comparison: dict[str, Any],
    drift: dict[str, Any],
    execute: bool,
    now: datetime,
) -> dict[str, Any]:
    if drift.get("critical") is True:
        return {"status": "V393_CRITICAL_DRIFT_HOLD", "executed": False}
    if comparison.get("eligible_for_promotion") is not True:
        return {"status": "V393_CANDIDATE_REJECTED", "executed": False}
    if not execute:
        return {"status": "V393_PROMOTION_PLAN_ONLY", "executed": False}
    try:
        rebuilt = grade_learning.rebuild_safe_vision_calibration()
    except Exception as exc:
        return {
            "status": "V393_PROMOTION_REBUILD_FAILED",
            "executed": False,
            "error_code": type(exc).__name__,
        }
    if rebuilt.get("registry_gate_v135") is not True:
        return {"status": "V393_PROMOTION_REGISTRY_GATE_FAILED", "executed": False}
    return {
        "status": "V393_PROMOTED_VERIFIED_CALIBRATION",
        "executed": True,
        "registry_verified_training_rows": int(rebuilt.get("registry_verified_training_rows") or 0),
        "champion": _capture_deployed_champion(rows, comparison, now),
    }


def maybe_rollback_vision(
    *,
    rows: list[dict[str, Any]],
    champion: dict[str, Any] | None,
    drift: dict[str, Any],
    execute: bool,
) -> dict[str, Any]:
    if not isinstance(champion, dict):
        return {"status": "V393_NO_CHAMPION", "executed": False}
    if drift.get("critical") is True:
        return {"status": "V393_DRIFT_HOLD_NO_ROLLBACK", "executed": False}
    _, holdout = split_train_holdout(rows)
    if len(holdout) < MIN_HOLDOUT_ROWS:
        return {"status": "V393_ROLLBACK_INSUFFICIENT_HOLDOUT", "executed": False}
    production = production_snapshot(rows)
    prod_eval = evaluate_snapshot(production, holdout)
    champ_eval = evaluate_snapshot(champion, holdout)
    prod_mae = _finite(prod_eval.get("candidate_mae"))
    champ_mae = _finite(champ_eval.get("candidate_mae"))
    if prod_mae is None or champ_mae is None or prod_mae < champ_mae + ROLLBACK_MARGIN:
        return {
            "status": "V393_PRODUCTION_WITHIN_CHAMPION_MARGIN",
            "executed": False,
            "production_mae": prod_mae,
            "champion_mae": champ_mae,
        }
    payload = champion.get("vision_payload")
    if not isinstance(payload, dict) or payload.get("registry_gate_v135") is not True:
        return {"status": "V393_CHAMPION_VISION_NOT_REGISTRY_GATED", "executed": False}
    if not execute:
        return {
            "status": "V393_VISION_ROLLBACK_PLAN_ONLY",
            "executed": False,
            "production_mae": prod_mae,
            "champion_mae": champ_mae,
        }
    try:
        grade_learning.base._atomic_json(grade_learning.base.VISION_CALIBRATION, payload)
    except Exception as exc:
        return {
            "status": "V393_VISION_ROLLBACK_FAILED",
            "executed": False,
            "error_code": type(exc).__name__,
        }
    return {
        "status": "V393_VISION_ROLLED_BACK_TO_CHAMPION",
        "executed": True,
        "production_mae": prod_mae,
        "champion_mae": champ_mae,
        "global_calibration_rollback_forced": False,
    }


def source_feature_contracts(drift: dict[str, Any], rollback: dict[str, Any]) -> list[dict[str, Any]]:
    contracts: list[dict[str, Any]] = []
    if drift.get("critical_companies"):
        contracts.append({
            "feature_id": "TCG_V393_COMPANY_SPECIFIC_DRIFT_ADAPTER",
            "reason": "critical verified grading drift detected for " + ",".join(drift["critical_companies"]),
        })
    if rollback.get("status") in {"V393_VISION_ROLLED_BACK_TO_CHAMPION", "V393_VISION_ROLLBACK_PLAN_ONLY"}:
        contracts.append({
            "feature_id": "TCG_V393_PERSISTED_GLOBAL_CHAMPION_LAYER",
            "reason": "vision rollback exists but global calibration is intentionally not force-rolled-back",
        })
    return [{
        **row,
        "stage": "shadow_spec",
        "auto_execute": False,
        "source_code_generated": False,
        "protected_pr_ci_required": True,
        "promotion_requires": [
            "targeted_tests",
            "grading_company_holdout",
            "vision_1_4_8_regression",
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
    moment = (now or _now()).astimezone(timezone.utc)
    state_path = root / EXPERIMENT_STATE.name
    try:
        with exclusive_file_lock(state_path, timeout_seconds=2.0, stale_seconds=1800.0):
            loaded = load_state(state_path)
            rows, audit = grade_learning.eligible_training_rows()
            drift = company_drift_report(rows)
            audit_ok = isinstance(audit, dict) and int(audit.get("eligible") or 0) == len(rows)

            preview = v392.run_cycle(
                execute=False,
                apply_capabilities=False,
                train_meta=False,
                apply_skills=False,
                root=root,
                now=moment,
                persist_outputs=False,
            )
            corruption_hold = loaded.get("corruption_hold") is True
            critical_hold = corruption_hold or not audit_ok or drift.get("critical") is True

            core = preview
            mutating = bool(execute or apply_capabilities or train_meta or apply_skills)
            if mutating and not critical_hold:
                core = v392.run_cycle(
                    execute=execute,
                    apply_capabilities=apply_capabilities,
                    train_meta=train_meta,
                    apply_skills=apply_skills,
                    root=root,
                    now=moment,
                    persist_outputs=False,
                )

            train, holdout = split_train_holdout(rows)
            candidate = build_snapshot(train, tag="shadow") if len(rows) >= MIN_EXPERIMENT_ROWS else None
            comparison = (
                compare_candidate(candidate, loaded["state"].get("champion"), holdout)
                if isinstance(candidate, dict)
                else {
                    "eligible_for_promotion": False,
                    "reasons": ["insufficient_verified_rows"],
                    "candidate": None,
                    "champion": None,
                }
            )
            rollback = maybe_rollback_vision(
                rows=rows,
                champion=loaded["state"].get("champion"),
                drift=drift,
                execute=execute and not corruption_hold and audit_ok,
            )
            promotion = (
                maybe_promote(
                    rows=rows,
                    candidate=candidate,
                    comparison=comparison,
                    drift=drift,
                    execute=execute and not critical_hold,
                    now=moment,
                )
                if isinstance(candidate, dict)
                else {"status": "V393_NO_CANDIDATE", "executed": False}
            )

            state = deepcopy(loaded["state"])
            state["generation"] = min(10_000_000, int(state.get("generation") or 0) + (1 if mutating else 0))
            if promotion.get("executed") is True and isinstance(promotion.get("champion"), dict):
                state["champion"] = promotion["champion"]
                state["canary"] = None
            elif isinstance(candidate, dict):
                canary = deepcopy(candidate)
                canary["promotion_evaluation"] = comparison.get("candidate") or {"candidate_mae": None}
                canary["observed_at"] = moment.isoformat(timespec="seconds")
                state["canary"] = canary
            if mutating:
                history = list(state.get("history") or [])
                history.append({
                    "observed_at": moment.isoformat(timespec="seconds"),
                    "rows": len(rows),
                    "holdout_rows": len(holdout),
                    "critical_drift": list(drift.get("critical_companies") or []),
                    "promotion_status": promotion.get("status"),
                    "rollback_status": rollback.get("status"),
                })
                state["history"] = history[-MAX_HISTORY:]

            state_write = (
                save_state(state_path, state, corruption_hold=corruption_hold)
                if mutating
                else {"status": "V393_STATE_WRITE_NOT_REQUESTED", "written": False}
            )
            contracts = source_feature_contracts(drift, rollback)

            result = deepcopy(core)
            result.update({
                "core_controller_version": str(core.get("controller_version") or CORE_CONTROLLER_VERSION),
                "controller_version": CONTROLLER_VERSION,
                "tcg_grader_autonomy_v393": {
                    "verified_rows": len(rows),
                    "audit_ok": audit_ok,
                    "train_rows": len(train),
                    "holdout_rows": len(holdout),
                    "company_drift": drift,
                    "critical_hold": critical_hold,
                    "experiment": {
                        "candidate_id": candidate.get("snapshot_id") if isinstance(candidate, dict) else None,
                        "comparison": comparison,
                        "promotion": {k: v for k, v in promotion.items() if k != "champion"},
                        "rollback": rollback,
                        "champion_id": (
                            state.get("champion", {}).get("snapshot_id")
                            if isinstance(state.get("champion"), dict)
                            else None
                        ),
                    },
                    "source_feature_contracts": contracts,
                    "closed_loop": "observe->drift->shadow->holdout->promote/reject->canary->recheck->rollback/hold",
                    "market_adaptation": "inherited V392 freshness/coverage/source-health/regime; no direction prediction",
                },
                "v393_state_write": state_write,
                "safety": SAFETY,
            })

            if persist_outputs:
                try:
                    atomic_write_json(root / PLAN_PATH.name, {
                        "schema_version": 1,
                        "controller_version": CONTROLLER_VERSION,
                        "generated_at": moment.isoformat(timespec="seconds"),
                        "critical_hold": critical_hold,
                        "company_drift": drift,
                        "comparison": comparison,
                        "source_feature_contracts": contracts,
                    }, suffix=".v393-plan.tmp")
                    atomic_write_json(root / REPORT_PATH.name, result, suffix=".v393-report.tmp")
                    result["tcg_grader_v393_runtime_output"] = {"status": "SAVED"}
                except (OSError, UnicodeError, ValueError, TypeError) as exc:
                    result["tcg_grader_v393_runtime_output"] = {
                        "status": "WRITE_FAILED",
                        "error_code": type(exc).__name__,
                    }
            return result
    except TimeoutError:
        return {
            "controller_version": CONTROLLER_VERSION,
            "v393_status": "V393_CONCURRENT_AUTONOMY_HOLD",
            "execution": {"executed": False, "git_write": False, "source_code_modified": False},
            "safety": SAFETY,
        }


def self_test() -> None:
    state = _default_state()
    assert _valid_state(state)
    assert SAFETY["verified_shadow_experiments"] is True
    assert SAFETY["deterministic_holdout_required"] is True
    assert SAFETY["critical_drift_blocks_promotion"] is True
    assert SAFETY["source_code_auto_generation"] is False
    assert SAFETY["direct_main_write"] is False
    assert SAFETY["market_direction_inferred"] is False
    print("TCG Grader verified experiment/canary evolution v393: PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description="TCG Grader V393 verified experiment autonomy")
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
        payload = result.get("tcg_grader_autonomy_v393") or {}
        experiment = payload.get("experiment") or {}
        print(json.dumps({
            "controller_version": result.get("controller_version"),
            "verified_rows": payload.get("verified_rows"),
            "critical_hold": payload.get("critical_hold"),
            "critical_companies": (payload.get("company_drift") or {}).get("critical_companies"),
            "promotion": experiment.get("promotion"),
            "rollback": experiment.get("rollback"),
            "champion_id": experiment.get("champion_id"),
        }, ensure_ascii=False, sort_keys=True))
    return 2 if result.get("v393_status") == "V393_CONCURRENT_AUTONOMY_HOLD" else 0


if __name__ == "__main__":
    raise SystemExit(main())
