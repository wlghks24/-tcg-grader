#!/usr/bin/env python3
"""Auditable learning-memory layer for MARKET_ANALYSIS.

This module learns only from explicitly verified outcomes. It never mutates hidden
model weights, never promotes unverified evidence, and never bypasses hard gates.
It provides bounded calibration, drift detection, recurring-error memory and
human-readable anomaly explanations using Python's standard library only.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Iterable


@dataclass(frozen=True)
class VerifiedOutcome:
    key: str
    predicted_value: float
    observed_value: float
    predicted_confidence: float
    verified: bool
    source_family: str = "unknown"
    region: str = "unknown"
    category: str = "unknown"
    timestamp: str | None = None
    error_code: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CalibrationReport:
    sample_count: int
    mae: float | None
    mape: float | None
    mean_confidence: float | None
    empirical_accuracy: float | None
    calibration_gap: float | None
    recommended_confidence_cap: float
    status: str
    reason_codes: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "sample_count": self.sample_count,
            "mae": self.mae,
            "mape": self.mape,
            "mean_confidence": self.mean_confidence,
            "empirical_accuracy": self.empirical_accuracy,
            "calibration_gap": self.calibration_gap,
            "recommended_confidence_cap": self.recommended_confidence_cap,
            "status": self.status,
            "reason_codes": list(self.reason_codes),
        }


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def verified_only(outcomes: Iterable[VerifiedOutcome]) -> list[VerifiedOutcome]:
    """Fail closed: calibration memory accepts only explicitly verified rows."""
    clean: list[VerifiedOutcome] = []
    for row in outcomes:
        if not row.verified:
            continue
        if not row.key.strip():
            continue
        if not (_finite(row.predicted_value) and _finite(row.observed_value)):
            continue
        if not _finite(row.predicted_confidence):
            continue
        clean.append(row)
    return clean


def calibration_report(
    outcomes: Iterable[VerifiedOutcome],
    *,
    relative_tolerance: float = 0.10,
    min_samples: int = 5,
) -> CalibrationReport:
    rows = verified_only(outcomes)
    if len(rows) < max(1, int(min_samples)):
        return CalibrationReport(
            sample_count=len(rows),
            mae=None,
            mape=None,
            mean_confidence=None,
            empirical_accuracy=None,
            calibration_gap=None,
            recommended_confidence_cap=0.65,
            status="INSUFFICIENT_VERIFIED_HISTORY",
            reason_codes=("VERIFIED_SAMPLE_FLOOR_NOT_MET",),
        )

    abs_errors: list[float] = []
    ape: list[float] = []
    correct: list[float] = []
    confidences: list[float] = []
    tolerance = max(0.0, float(relative_tolerance))

    for row in rows:
        pred = float(row.predicted_value)
        obs = float(row.observed_value)
        err = abs(pred - obs)
        abs_errors.append(err)
        denom = max(abs(obs), 1e-12)
        rel = err / denom
        ape.append(rel)
        correct.append(1.0 if rel <= tolerance else 0.0)
        confidences.append(_clamp01(float(row.predicted_confidence)))

    mae = statistics.fmean(abs_errors)
    mape = statistics.fmean(ape)
    empirical = statistics.fmean(correct)
    mean_conf = statistics.fmean(confidences)
    gap = mean_conf - empirical

    reasons: list[str] = []
    status = "CALIBRATED"
    cap = min(0.99, empirical + 0.05)
    if gap > 0.15:
        status = "OVERCONFIDENT"
        reasons.append("CONFIDENCE_EXCEEDS_EMPIRICAL_ACCURACY")
        cap = max(0.50, empirical)
    elif gap < -0.20:
        status = "UNDERCONFIDENT"
        reasons.append("CONFIDENCE_BELOW_EMPIRICAL_ACCURACY")
    if mape > max(0.25, tolerance * 2.5):
        status = "DEGRADED"
        reasons.append("ERROR_RATE_ABOVE_BOUND")
        cap = min(cap, 0.60)
    if not reasons:
        reasons.append("VERIFIED_HISTORY_WITHIN_BOUNDS")

    return CalibrationReport(
        sample_count=len(rows),
        mae=round(mae, 6),
        mape=round(mape, 6),
        mean_confidence=round(mean_conf, 6),
        empirical_accuracy=round(empirical, 6),
        calibration_gap=round(gap, 6),
        recommended_confidence_cap=round(_clamp01(cap), 4),
        status=status,
        reason_codes=tuple(reasons),
    )


def apply_confidence_cap(raw_confidence: float, report: CalibrationReport) -> float:
    """A learned cap may lower confidence, never raise the original score."""
    raw = _clamp01(raw_confidence)
    return round(min(raw, report.recommended_confidence_cap), 4)


def detect_distribution_drift(
    baseline: Iterable[float],
    recent: Iterable[float],
    *,
    relative_shift_limit: float = 0.20,
    spread_ratio_limit: float = 2.5,
    min_samples: int = 5,
) -> dict[str, Any]:
    base = [float(x) for x in baseline if _finite(x)]
    new = [float(x) for x in recent if _finite(x)]
    floor = max(2, int(min_samples))
    if len(base) < floor or len(new) < floor:
        return {
            "drift": False,
            "status": "INSUFFICIENT_HISTORY",
            "reason_codes": ["DRIFT_SAMPLE_FLOOR_NOT_MET"],
            "baseline_count": len(base),
            "recent_count": len(new),
        }

    base_med = statistics.median(base)
    new_med = statistics.median(new)
    denom = max(abs(base_med), 1e-12)
    median_shift = abs(new_med - base_med) / denom

    def robust_spread(values: list[float]) -> float:
        med = statistics.median(values)
        return statistics.median(abs(x - med) for x in values)

    base_spread = robust_spread(base)
    new_spread = robust_spread(new)
    spread_ratio = (new_spread + 1e-12) / (base_spread + 1e-12)

    reasons: list[str] = []
    if median_shift > max(0.0, float(relative_shift_limit)):
        reasons.append("MEDIAN_SHIFT_EXCEEDED")
    if spread_ratio > max(1.0, float(spread_ratio_limit)):
        reasons.append("VARIABILITY_SPIKE")

    return {
        "drift": bool(reasons),
        "status": "DRIFT_DETECTED" if reasons else "STABLE",
        "reason_codes": reasons or ["DISTRIBUTION_WITHIN_BOUNDS"],
        "baseline_count": len(base),
        "recent_count": len(new),
        "baseline_median": round(base_med, 6),
        "recent_median": round(new_med, 6),
        "relative_median_shift": round(median_shift, 6),
        "spread_ratio": round(spread_ratio, 6),
    }


def recurring_error_memory(
    error_codes: Iterable[str | None],
    *,
    escalation_threshold: int = 3,
) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for code in error_codes:
        normalized = (code or "").strip().upper()
        if not normalized:
            continue
        counts[normalized] = counts.get(normalized, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    threshold = max(2, int(escalation_threshold))
    recurring = [{"error_code": code, "count": count} for code, count in ordered if count >= threshold]
    return {
        "unique_error_count": len(counts),
        "recurring": recurring,
        "requires_strategy_change": bool(recurring),
        "top_errors": [{"error_code": code, "count": count} for code, count in ordered[:10]],
    }


def explain_anomaly(
    *,
    observed: float,
    expected_center: float,
    expected_spread: float,
    source_health_state: str = "healthy",
    identity_match: bool = True,
    lineage_novel: bool = False,
) -> dict[str, Any]:
    if not (_finite(observed) and _finite(expected_center) and _finite(expected_spread)):
        return {
            "status": "QUARANTINE",
            "severity": "high",
            "reason_codes": ["ANOMALY_INPUT_INVALID"],
            "explanation": "Anomaly inputs are incomplete or non-finite.",
        }
    spread = max(abs(float(expected_spread)), 1e-9)
    z = abs(float(observed) - float(expected_center)) / spread
    reasons: list[str] = []
    severity = "low"
    if z >= 5.0:
        severity = "high"
        reasons.append("EXTREME_VALUE_DEVIATION")
    elif z >= 3.0:
        severity = "medium"
        reasons.append("VALUE_DEVIATION")
    if source_health_state != "healthy":
        severity = "high"
        reasons.append("SOURCE_HEALTH_NOT_OK")
    if not identity_match:
        severity = "high"
        reasons.append("IDENTITY_MISMATCH")
    if lineage_novel:
        reasons.append("NOVEL_LINEAGE_REQUIRES_CORROBORATION")
    if not reasons:
        reasons.append("NO_MATERIAL_ANOMALY")

    if severity == "high":
        action = "quarantine_and_reverify"
    elif severity == "medium":
        action = "hold_for_corroboration"
    elif lineage_novel:
        action = "provisional_until_corroborated"
    else:
        action = "accept_if_other_hard_gates_pass"

    return {
        "status": "ANOMALOUS" if reasons != ["NO_MATERIAL_ANOMALY"] else "NORMAL",
        "severity": severity,
        "z_like_distance": round(z, 4),
        "reason_codes": reasons,
        "recommended_action": action,
        "confidence_override_allowed": False,
    }
