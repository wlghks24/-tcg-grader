#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Safe self-learning calibration for TCG pre-grading.

This module never trains on unverified internet data and never attempts to
reverse-engineer a grader's proprietary process. It learns only a bounded,
company-specific calibration from user-confirmed graded-card results.
"""
from __future__ import annotations

import hashlib
import math
import statistics
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

COMPANIES = ("PSA", "BGS", "CGC", "BRG", "TAG")
MAX_SAMPLES = 2000

GRADE_STEPS = {
    "PSA": tuple(float(x) for x in range(1, 11)),
    "BGS": tuple(x / 2 for x in range(2, 21)),
    "CGC": tuple(x / 2 for x in range(2, 21)),
    "BRG": tuple(x / 2 for x in range(2, 21)),
    "TAG": tuple(x / 2 for x in range(2, 21)),
}


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _finite(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _median(values: Sequence[float]) -> float:
    return float(statistics.median(values)) if values else 0.0


def _weighted_mean(values: Sequence[Tuple[float, float]]) -> float:
    total = sum(weight for _, weight in values)
    return sum(value * weight for value, weight in values) / total if total else 0.0


def _nearest_grade(company: str, value: float) -> float:
    steps = GRADE_STEPS[company]
    return min(steps, key=lambda grade: (abs(grade - value), grade))


def _company(raw: Any) -> Optional[str]:
    company = str(raw or "").strip().upper()
    return company if company in COMPANIES else None


def _game(raw: Any) -> str:
    text = str(raw or "").strip().lower()
    aliases = {
        "pokemon": "pokemon", "pokémon": "pokemon", "포켓몬": "pokemon",
        "onepiece": "onepiece", "one piece": "onepiece", "원피스": "onepiece",
        "naruto": "naruto", "나루토": "naruto",
    }
    return aliases.get(text, text[:40] if text else "unknown")


def _card_key(sample: Mapping[str, Any]) -> str:
    explicit = str(sample.get("card_key") or "").strip()
    if explicit:
        return explicit[:180]
    parts = [
        str(sample.get("game") or "").strip(),
        str(sample.get("set") or sample.get("set_name") or "").strip(),
        str(sample.get("card_name") or sample.get("name") or "").strip(),
        str(sample.get("card_no") or sample.get("number") or "").strip(),
    ]
    joined = "|".join(part for part in parts if part)
    return joined[:180]


def _subgrades(sample: Mapping[str, Any]) -> Dict[str, float]:
    src = sample.get("subgrades")
    if not isinstance(src, Mapping):
        src = {}
    out: Dict[str, float] = {}
    for key in ("centering", "corners", "edges", "surface"):
        value = _finite(src.get(key, sample.get(f"subgrade_{key}")))
        if value is not None and 1 <= value <= 10:
            out[key] = round(value * 2) / 2
    return out


def _features(sample: Mapping[str, Any]) -> Dict[str, float]:
    src = sample.get("features")
    if not isinstance(src, Mapping):
        src = {}
    allowed = (
        "front_centering_worst", "back_centering_worst",
        "surface_risk", "edge_risk", "corner_risk",
        "photo_quality", "confidence",
    )
    out: Dict[str, float] = {}
    for key in allowed:
        value = _finite(src.get(key, sample.get(key)))
        if value is not None:
            out[key] = round(value, 4)
    return out


def sanitize_sample(sample: Mapping[str, Any], *, legacy_verified: bool = False) -> Dict[str, Any]:
    if not isinstance(sample, Mapping):
        raise ValueError("sample must be an object")
    company = _company(sample.get("company") or sample.get("grader"))
    if not company:
        raise ValueError("unsupported grading company")

    actual = _finite(sample.get("actual_grade", sample.get("actual")))
    raw_pred = _finite(sample.get("raw_pred", sample.get("predicted_raw")))
    pred = _finite(sample.get("predicted_grade", sample.get("pred")))
    if raw_pred is None:
        raw_pred = pred
    if actual is None or raw_pred is None or not (1 <= actual <= 10 and 1 <= raw_pred <= 10):
        raise ValueError("actual/raw prediction must be between 1 and 10")

    verified = bool(sample.get("verified", legacy_verified))
    if not verified:
        raise ValueError("only verified graded-card results may train calibration")

    cert_no = str(sample.get("cert_no") or sample.get("cert") or "").strip()[:80]
    time_value = str(sample.get("time") or sample.get("created_at") or _now())[:64]
    provided_id = str(sample.get("id") or "").strip()[:96]
    stable_material = "|".join((time_value, company, str(actual), str(raw_pred), cert_no, _card_key(sample)))
    sample_id = provided_id or hashlib.sha1(stable_material.encode("utf-8")).hexdigest()[:24]

    result: Dict[str, Any] = {
        "id": sample_id,
        "time": time_value,
        "company": company,
        "actual": _nearest_grade(company, actual),
        "pred": _nearest_grade(company, pred if pred is not None else raw_pred),
        "raw_pred": _clip(raw_pred, 1, 10),
        "verified": True,
        "source": str(sample.get("source") or ("legacy_validation" if legacy_verified else "user_confirmed"))[:80],
        "mode": str(sample.get("mode") or "unknown")[:32],
        "game": _game(sample.get("game")),
    }
    card_key = _card_key(sample)
    if card_key:
        result["card_key"] = card_key
    if cert_no:
        result["cert_no"] = cert_no

    for key in ("card_name", "set", "set_name", "card_no", "note", "defect_label"):
        value = str(sample.get(key) or "").strip()
        if value:
            result[key] = value[:300]

    features = _features(sample)
    if features:
        result["features"] = features
    subgrades = _subgrades(sample)
    if company == "BGS" and subgrades:
        result["subgrades"] = subgrades
    return result


def sanitize_legacy_rows(rows: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    clean: List[Dict[str, Any]] = []
    for row in list(rows or [])[-500:]:
        try:
            clean.append(sanitize_sample(row, legacy_verified=True))
        except (ValueError, TypeError):
            continue
    return clean


def _sample_identity(sample: Mapping[str, Any]) -> str:
    cert = str(sample.get("cert_no") or "").strip()
    if cert:
        return f"{sample.get('company')}|cert|{cert}"
    return "|".join((
        str(sample.get("id") or ""),
        str(sample.get("time") or ""),
        str(sample.get("company") or ""),
        str(sample.get("actual") or ""),
        str(sample.get("raw_pred") or sample.get("pred") or ""),
        str(sample.get("card_key") or ""),
    ))


def _dedupe(samples: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    seen: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for raw in samples:
        try:
            sample = sanitize_sample(raw, legacy_verified=True)
        except (ValueError, TypeError):
            continue
        key = _sample_identity(sample)
        if key not in seen:
            order.append(key)
        seen[key] = sample
    return [seen[key] for key in order][-MAX_SAMPLES:]


def _sample_weights(samples: Sequence[Mapping[str, Any]]) -> List[float]:
    counts: Dict[str, int] = {}
    for sample in samples:
        key = str(sample.get("card_key") or "")
        if key:
            counts[key] = counts.get(key, 0) + 1
    weights: List[float] = []
    for sample in samples:
        key = str(sample.get("card_key") or "")
        count = counts.get(key, 1)
        weights.append(1.0 / math.sqrt(count) if key else 1.0)
    return weights


def _robust_residual(samples: Sequence[Mapping[str, Any]]) -> Tuple[float, float, float, float, float]:
    """Return robust(actual-raw_pred), MAE, RMSE, exact rate, within-0.5 rate."""
    if not samples:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    residuals = [float(x["actual"]) - float(x.get("raw_pred", x["pred"])) for x in samples]
    abs_err = [abs(x) for x in residuals]
    weights = _sample_weights(samples)
    med = _median(residuals)
    deviations = [abs(x - med) for x in residuals]
    mad = _median(deviations)
    radius = max(1.0, 3.0 * 1.4826 * mad)
    bounded = [(_clip(residual, med - radius, med + radius), weight)
               for residual, weight in zip(residuals, weights)]
    robust = _weighted_mean(bounded)
    mae = sum(abs_err) / len(abs_err)
    rmse = math.sqrt(sum(x * x for x in residuals) / len(residuals))
    exact = sum(abs(x) < 0.01 for x in residuals) / len(residuals)
    within_half = sum(abs(x) <= 0.5 + 1e-9 for x in residuals) / len(residuals)
    return robust, mae, rmse, exact, within_half


def _tier(n: int) -> Tuple[str, float, float]:
    if n < 5:
        return "observe", 0.0, 0.0
    if n < 10:
        return "conservative", 0.25, 0.25
    if n < 30:
        return "limited", 0.50, 0.50
    if n < 60:
        return "strong", 0.75, 0.75
    return "mature", 1.0, 0.75


def build_calibration(samples: Iterable[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    verified = _dedupe(samples)
    model: Dict[str, Dict[str, Any]] = {}
    for company in COMPANIES:
        rows = [x for x in verified if x["company"] == company]
        n = len(rows)
        robust, mae, rmse, exact, within_half = _robust_residual(rows)
        state, strength, cap = _tier(n)
        correction = _clip(robust * strength, -cap, cap) if cap else 0.0

        games: Dict[str, Dict[str, Any]] = {}
        for game in sorted({str(x.get("game") or "unknown") for x in rows}):
            if game not in ("pokemon", "onepiece", "naruto"):
                continue
            subset = [x for x in rows if str(x.get("game") or "unknown") == game]
            if len(subset) < 8:
                continue
            game_robust, game_mae, _, _, _ = _robust_residual(subset)
            residual_after_global = game_robust - correction
            game_strength = min(0.5, len(subset) / 40.0)
            games[game] = {
                "n": len(subset),
                "correction": round(_clip(residual_after_global * game_strength, -0.25, 0.25), 4),
                "mae": round(game_mae, 4),
            }

        card_counts: Dict[str, int] = {}
        for row in rows:
            key = str(row.get("card_key") or "")
            if key:
                card_counts[key] = card_counts.get(key, 0) + 1
        repeated = sum(1 for count in card_counts.values() if count >= 2)

        model[company] = {
            "n": n,
            "state": state,
            "strength": strength,
            "correction": round(correction, 4),
            "robust_residual": round(robust, 4),
            "mae": round(mae, 4),
            "rmse": round(rmse, 4),
            "exact_rate": round(exact, 4),
            "within_half_rate": round(within_half, 4),
            "same_card_groups": repeated,
            "game_adjustments": games,
        }
    return model


def apply_calibration(company: str, prediction: float, calibration: Mapping[str, Any],
                      *, game: Optional[str] = None) -> Dict[str, Any]:
    company = _company(company)
    pred = _finite(prediction)
    if not company or pred is None or not 1 <= pred <= 10:
        raise ValueError("invalid company/prediction")
    entry = calibration.get(company, {}) if isinstance(calibration, Mapping) else {}
    correction = _finite(entry.get("correction")) or 0.0
    game_name = _game(game) if game is not None else "unknown"
    game_adjustment = 0.0
    game_entries = entry.get("game_adjustments", {}) if isinstance(entry, Mapping) else {}
    if game_name != "unknown" and isinstance(game_entries, Mapping) and game_name in game_entries:
        game_adjustment = _finite(game_entries[game_name].get("correction")) or 0.0
    raw = _clip(pred, 1, 10)
    corrected = _nearest_grade(company, _clip(raw + correction + game_adjustment, 1, 10))
    return {
        "company": company,
        "raw_prediction": raw,
        "grade": corrected,
        "correction": round(correction + game_adjustment, 4),
        "state": str(entry.get("state") or "observe"),
        "sample_count": int(entry.get("n") or 0),
    }


def bgs_empirical_summary(samples: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for raw in samples:
        try:
            sample = sanitize_sample(raw, legacy_verified=True)
        except (ValueError, TypeError):
            continue
        if sample["company"] == "BGS" and len(sample.get("subgrades", {})) == 4:
            rows.append(sample)
    if not rows:
        return {"n": 0, "note": "BGS 서브그레이드 검증자료 없음"}
    gaps = []
    black_label = 0
    one_95_to_10 = 0
    for row in rows:
        values = list(row["subgrades"].values())
        low = min(values)
        gaps.append(float(row["actual"]) - low)
        if all(abs(x - 10) < 0.01 for x in values) and row["actual"] == 10:
            black_label += 1
        if values.count(9.5) == 1 and values.count(10.0) == 3 and row["actual"] == 10:
            one_95_to_10 += 1
    return {
        "n": len(rows),
        "median_final_minus_lowest": round(_median(gaps), 3),
        "max_observed_final_minus_lowest": round(max(gaps), 3),
        "all_10_final_10_cases": black_label,
        "three_10_one_9_5_final_10_cases": one_95_to_10,
        "note": "사용자 확인 사례의 경험 통계이며 Beckett 비공개 채점공식을 의미하지 않음",
    }


def empty_store() -> Dict[str, Any]:
    return {
        "version": 2,
        "updated_at": None,
        "v30_validation": [],
        "v11_validation": [],
        "confirmed_samples": [],
        "calibration": build_calibration([]),
        "bgs_subgrade_summary": bgs_empirical_summary([]),
    }


def rebuild_store(store: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    source = dict(store or {})
    v30 = sanitize_legacy_rows(source.get("v30_validation", []))
    v11 = sanitize_legacy_rows(source.get("v11_validation", []))
    confirmed_raw = source.get("confirmed_samples", [])
    confirmed: List[Dict[str, Any]] = []
    if isinstance(confirmed_raw, list):
        for row in confirmed_raw:
            try:
                confirmed.append(sanitize_sample(row, legacy_verified=False))
            except (ValueError, TypeError):
                continue
    all_samples = _dedupe([*v30, *v11, *confirmed])
    confirmed_ids = {_sample_identity(x) for x in confirmed}
    confirmed = [x for x in all_samples if _sample_identity(x) in confirmed_ids]
    calibration = build_calibration(all_samples)
    return {
        "version": 2,
        "updated_at": source.get("updated_at"),
        "v30_validation": v30[-500:],
        "v11_validation": v11[-500:],
        "confirmed_samples": confirmed[-MAX_SAMPLES:],
        "calibration": calibration,
        "bgs_subgrade_summary": bgs_empirical_summary(all_samples),
    }


def append_confirmed_sample(store: Optional[Mapping[str, Any]], sample: Mapping[str, Any]) -> Dict[str, Any]:
    base = rebuild_store(store)
    clean = sanitize_sample({**dict(sample), "verified": True}, legacy_verified=False)
    current = list(base.get("confirmed_samples", []))
    current.append(clean)
    base["confirmed_samples"] = _dedupe(current)[-MAX_SAMPLES:]
    base["updated_at"] = _now()
    return rebuild_store(base)


def model_status(store: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    rebuilt = rebuild_store(store)
    total = sum(int(x.get("n") or 0) for x in rebuilt["calibration"].values())
    return {
        "ok": True,
        "version": 2,
        "updated_at": rebuilt.get("updated_at"),
        "verified_training_rows": total,
        "companies": rebuilt["calibration"],
        "bgs_subgrade_summary": rebuilt["bgs_subgrade_summary"],
        "policy": {
            "verified_only": True,
            "minimum_to_apply": 5,
            "company_separated": True,
            "same_card_downweighting": True,
            "max_global_correction": 0.75,
        },
    }


def calibrate_prediction(store: Optional[Mapping[str, Any]], company: str, prediction: float,
                         *, game: Optional[str] = None) -> Dict[str, Any]:
    rebuilt = rebuild_store(store)
    return apply_calibration(company, prediction, rebuilt["calibration"], game=game)
