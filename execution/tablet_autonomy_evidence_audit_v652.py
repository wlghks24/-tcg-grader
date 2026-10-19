#!/usr/bin/env python3
"""V652: independent, read-only evidence maturity audit for Tablet V387.

This is a diagnostic, NOT a verification authority or a verified-outcome writer.
Never updates confidence, never executes training, never synthesizes evidence.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tablet_autonomous_evolution_v373 as v373
import tablet_autonomous_evolution_v386 as v386
import tablet_autonomous_evolution_v387 as v387

MAX_LOG_BYTES = 8_000_000
MAX_OUTCOME_BYTES = v373.MAX_OUTCOME_BYTES
ACTION_KEYS = tuple(v373.META_ACTIONS)
WEIGHTS = {
    "schema": 15,
    "verified_samples": 25,
    "provenance": 15,
    "peer": 10,
    "confidence": 15,
    "regime": 5,
    "gate": 10,
    "storage": 5,
}


def _log_report(path: Path) -> dict[str, Any] | None:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_LOG_BYTES:
            return None
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError, ValueError):
        return None
    for line in reversed(lines[-20:]):
        if not line.startswith("{"):
            continue
        try:
            item = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(item, dict) and isinstance(item.get("v387_uncertainty_policy"), dict):
            return item
    return None


def _meta_rows(path: Path) -> tuple[str, list[dict[str, Any]], int]:
    if path.is_symlink():
        return "UNSAFE_SYMLINK", [], 0
    if not path.exists():
        return "MISSING", [], 0
    try:
        if not path.is_file() or path.stat().st_size > MAX_OUTCOME_BYTES:
            return "UNSAFE_OR_OVERSIZE", [], 0
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError, ValueError):
        return "READ_ERROR", [], 0
    raw_lines = text.splitlines()[-v373.MAX_META_OUTCOMES:]
    rows = v373.load_verified_outcomes(path=path)
    if len(rows) != len(raw_lines):
        return "REJECTED_ROWS", rows, len(raw_lines)
    refs = [str(x.get("evidence_ref") or "") for x in rows]
    if len(refs) != len(set(refs)):
        return "DUPLICATE_EVIDENCE", rows, len(raw_lines)
    return "SCHEMA_VALID_ONLY" if rows else "EMPTY", rows, len(raw_lines)


def _estimate_needed_samples(report: dict[str, Any], selected: str | None) -> dict[str, Any]:
    """Counterfactual *only*: project sample support at fixed other inputs."""
    mutual = report.get("v386_mutual_neural_policy")
    mutual = mutual if isinstance(mutual, dict) else {}
    policy = report.get("v387_uncertainty_policy") or {}
    transition = policy.get("regime_transition") or {}
    drift = transition.get("drift_score")
    if isinstance(drift, bool) or not isinstance(drift, (int, float)) or not math.isfinite(drift):
        return {"mode": "NO_FORECAST", "reason": "DRIFT_UNKNOWN"}
    peer = policy.get("peer_available") is True
    threshold = v387.MIN_MUTUAL_CONFIDENCE if peer else v387.MIN_LOCAL_CONFIDENCE
    for row in mutual.get("candidates") or []:
        if not isinstance(row, dict) or row.get("action_id") != selected:
            continue
        try:
            count = max(0, int(row.get("local_verified_samples") or 0))
        except (ValueError, TypeError, OverflowError):
            return {"mode": "NO_FORECAST", "reason": "INVALID_SAMPLE_COUNT"}
        for future in range(count, 201):
            candidate = dict(row, local_verified_samples=future)
            calc = v387._candidate_confidence(
                candidate, peer_available=peer, drift_score=max(0.0, min(1.0, drift))
            )
            if calc["confidence"] >= threshold and calc["uncertainty"] <= v387.MAX_EXECUTION_UNCERTAINTY:
                return {
                    "mode": "COUNTERFACTUAL_NOT_VERIFIED",
                    "local_samples_now": count,
                    "projected_local_samples_at_fixed_conditions": future,
                    "additional_genuine_samples_indicated": max(0, future - count),
                    "not_a_guarantee": True,
                    "no_records_created": True,
                }
        return {"mode": "COUNTERFACTUAL_NOT_VERIFIED", "projected_local_samples_at_fixed_conditions": None,
                "reason": "THRESHOLD_UNREACHABLE_WITH_COUNT_ONLY", "not_a_guarantee": True}
    return {"mode": "NO_FORECAST", "reason": "SELECTED_ACTION_NOT_IN_POLICY"}


def audit(root: Path, log: Path, *, now: datetime | None = None) -> dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    meta_path = root / v373.OUTCOMES_PATH.name
    peer_path = root / "crosscheck_exchange" / "tcg-grader-autonomy-summary.json"
    storage, rows, total = _meta_rows(meta_path)
    counts = Counter(str(row["action_id"]) for row in rows)
    peer = v386.load_peer_summary(peer_path, "tcg_grader", now=now)
    report = _log_report(log)
    facets: dict[str, str] = {}
    facets["storage"] = "PASS" if storage in {"SCHEMA_VALID_ONLY", "EMPTY", "MISSING"} else "HOLD"
    facets["schema"] = "PASS" if storage == "SCHEMA_VALID_ONLY" else "HOLD"
    facets["provenance"] = "UNVERIFIED_INDEPENDENT_RECEIPT" if rows else "NO_VERIFIED_EVIDENCE"
    facets["peer"] = "PASS" if peer.get("usable") is True else "OPTIONAL_MISSING_OR_INVALID"
    facets["verified_samples"] = "HOLD"
    facets["confidence"] = "HOLD"
    facets["regime"] = "UNAVAILABLE"
    facets["gate"] = "UNAVAILABLE"
    selected = None
    confidence = None
    threshold = None
    uncertainty = None
    mismatch = False
    forecast: dict[str, Any] = {"mode": "NO_FORECAST"}
    if report is not None:
        p = report["v387_uncertainty_policy"]
        selected = p.get("selected_action")
        confidence = p.get("selected_confidence")
        threshold = p.get("confidence_threshold")
        uncertainty = p.get("selected_uncertainty")
        regime = (p.get("regime_transition") or {}).get("level")
        facets["regime"] = "PASS" if regime == "STABLE" else ("WATCH" if regime == "WATCH" else "HOLD")
        gate = report.get("v387_autonomous_gate") or {}
        execution = report.get("execution") or {}
        nonexecution = (
            isinstance(gate, dict) and gate.get("allow_execution") is False
            and isinstance(execution, dict) and execution.get("executed") is False
            and execution.get("git_write") is False
            and execution.get("source_code_modified") is False
        )
        facets["gate"] = "PASS_FAIL_CLOSED" if nonexecution else "REVIEW"
        mutual = report.get("v386_mutual_neural_policy") or {}
        cands = mutual.get("candidates") if isinstance(mutual, dict) else None
        if isinstance(cands, list):
            for row in cands:
                if isinstance(row, dict) and row.get("action_id") in ACTION_KEYS:
                    try:
                        expected = int(row.get("local_verified_samples") or 0)
                    except (ValueError, TypeError, OverflowError):
                        mismatch = True
                        continue
                    if expected != counts[row["action_id"]]:
                        mismatch = True
        if (selected in ACTION_KEYS and isinstance(confidence, (float, int))
                and isinstance(threshold, (float, int)) and not isinstance(confidence, bool)
                and not isinstance(threshold, bool) and math.isfinite(confidence)
                and math.isfinite(threshold)):
            facets["confidence"] = "PASS" if confidence >= threshold else "HOLD"
        facets["verified_samples"] = "HOLD" if mismatch else (
            "SCHEMA_ONLY" if rows else "MISSING"
        )
        forecast = _estimate_needed_samples(report, selected)
    # The readiness score is NOT V387 execution confidence and never authorizes action.
    score = 0
    for lens, weight in WEIGHTS.items():
        if facets[lens].startswith("PASS"):
            score += weight
        elif lens == "regime" and facets[lens] == "WATCH":
            score += weight // 2
    blockers = []
    if storage != "SCHEMA_VALID_ONLY":
        blockers.append("META_OUTCOMES_" + storage)
    if mismatch:
        blockers.append("V381_V386_SAMPLE_COUNT_MISMATCH")
    if peer.get("usable") is not True:
        blockers.append("OPTIONAL_PEER_" + str(peer.get("status")))
    if facets["confidence"] != "PASS":
        blockers.append("V387_CONFIDENCE_NOT_PROVEN")
    if facets["provenance"] != "PASS":
        blockers.append("INDEPENDENT_EVIDENCE_RECEIPT_NOT_ATTESTED")
    return {
        "schema_version": 1,
        "controller": "read_only_v652",
        "overall_status": "HOLD" if blockers else "REVIEW",
        "readiness_score_out_of_100": score,
        "readiness_score_not_v387_confidence": True,
        "no_auto_promotion": True,
        "no_training_or_model_writes": True,
        "evidence_file_status": storage,
        "accepted_schema_rows": len(rows),
        "bounded_lines_checked": total,
        "per_action_schema_rows": {a: counts[a] for a in ACTION_KEYS},
        "independent_provenance_verified": False,
        "peer_summary_status": peer.get("status"),
        "selected_action": selected,
        "recorded_confidence": confidence,
        "recorded_threshold": threshold,
        "recorded_uncertainty": uncertainty,
        "facets": facets,
        "blockers": blockers,
        "counterfactual": forecast,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    args = parser.parse_args()
    output = audit(args.root, args.log)
    print("V652_READ_ONLY_AUDIT=" + json.dumps(output, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
