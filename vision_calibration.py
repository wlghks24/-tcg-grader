#!/usr/bin/env python3
"""공식 확정등급 피드백을 이용한 보수적 비전 보정 학습기.

사진 자체를 모델 재학습했다고 주장하지 않는다. 측정 엔진이 저장한 센터링·표면
특징과 실제 공식 등급의 오차를 카드 단위 교차검증하고, 보류 데이터에서 오차가
줄어든 경우에만 최대 1등급의 하향 보정을 활성화한다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from safe_runtime import atomic_write_json, reject_nonstandard_json, unique_json_object
from grading_accuracy_v99 import (
    apply_downward_correction, sanitize_rows as sanitize_global_rows,
    train_company_calibration, valid_actual_grade,
)


ROOT = Path(__file__).resolve().parent
ENGINE_VERSION = "v160-grading-hierarchy-1-4-8-learning"
INPUT_PATH = ROOT / "learning_store.json"
OUTPUT_PATH = ROOT / "vision_calibration.json"
COMPANIES = {"PSA", "BGS", "CGC", "TAG", "BRG"}
MIN_ROWS = 12
MIN_UNIQUE_CARDS = 8
MIN_HOLDOUT = 3


def _strict_load(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=reject_nonstandard_json,
        object_pairs_hook=unique_json_object,
    )


def _number(value: Any, low: float, high: float) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and low <= number <= high else None


def vision_bucket(vision: dict[str, Any]) -> str | None:
    """Bucket verified RAW rows with whole-card + 4-way + 8-way defect evidence.

    Missing v160 fields default to zero so existing verified rows keep their
    historical bucket instead of being discarded during migration.
    """
    front = _number(vision.get("frontCenter"), 0, 50)
    back = _number(vision.get("backCenter"), 0, 50)
    surface = _number(vision.get("surfaceRisk"), 0, 100)
    quadrant_surface = _number(vision.get("quadrantSurfaceWorstRisk", 0), 0, 100) or 0
    quadrant_worst = _number(vision.get("quadrantWorstRisk", 0), 0, 100) or 0
    quadrant_imbalance = _number(vision.get("quadrantImbalance", 0), 0, 100) or 0
    zone_surface = _number(vision.get("eightZoneSurfaceWorstRisk", 0), 0, 100) or 0
    zone_worst = _number(vision.get("eightZoneWorstRisk", 0), 0, 100) or 0
    zone_imbalance = _number(vision.get("eightZoneImbalance", 0), 0, 100) or 0
    hierarchy_defect = _number(vision.get("hierarchyDefectRisk", 0), 0, 100) or 0
    if None in (front, back, surface):
        return None
    center = min(front, back)
    center_band = "centered" if center >= 47 else "minor-offcenter" if center >= 44 else "offcenter"
    surface = max(surface, quadrant_surface, zone_surface)
    surface_band = "surface-low" if surface < 15 else "surface-medium" if surface < 35 else "surface-high"
    local_worst = max(quadrant_worst, zone_worst, hierarchy_defect)
    local_imbalance = max(quadrant_imbalance, zone_imbalance)
    quadrant_band = (
        "q-balanced"
        if local_worst < 15 and local_imbalance < 20
        else "q-watch"
        if local_worst < 40
        else "q-local-defect"
    )
    return f"{center_band}|{surface_band}|{quadrant_band}|{'multi' if vision.get('multiAngle') is True else 'single'}"


def sanitize_rows(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    modern = payload.get("v99_validation")
    legacy = payload.get("v30_validation")
    rows = modern if isinstance(modern, list) and modern else legacy if isinstance(legacy, list) else []
    dedup: dict[str, dict[str, Any]] = {}
    conflicts: set[str] = set()
    for row in rows[-500:]:
        if not isinstance(row, dict) or row.get("official_result") is not True:
            continue
        company = str(row.get("company", "")).upper()
        actual = _number(row.get("actual"), 1, 10)
        pred = _number(row.get("raw_pred", row.get("pred")), 1, 10)
        certification = str(row.get("certification_id", "")).strip()
        vision = row.get("vision")
        bucket = vision_bucket(vision) if isinstance(vision, dict) else None
        if company not in COMPANIES or actual is None or not valid_actual_grade(company, actual) or pred is None or not bucket:
            continue
        if not re_certification(certification):
            continue
        key = f"{company}|{certification}"
        if key in conflicts:
            continue
        previous = dedup.get(key)
        if previous is not None and abs(float(previous["actual"]) - actual) > 1e-9:
            dedup.pop(key, None); conflicts.add(key); continue
        card_key = str(row.get("card_key") or "").strip()[:180]
        card_id = str(row.get("card_id") or card_key or certification).strip()[:120]
        dedup[key] = {
            "company": company, "actual": actual, "pred": pred, "bucket": bucket,
            "certification_id": certification[:120], "card_id": card_id,
        }
    return list(dedup.values())

def re_certification(value: str) -> bool:
    return 4 <= len(value) <= 120 and all(char.isalnum() or char in "-_./" for char in value)


def _fold(card_id: str) -> int:
    return int(hashlib.sha256(card_id.encode("utf-8")).hexdigest()[:8], 16) % 5


def _global_correction(company: str, models: dict[str, dict[str, Any]] | None) -> float:
    row = models.get(company, {}) if isinstance(models, dict) else {}
    value = row.get("correction", 0) if isinstance(row, dict) and row.get("enabled") is True else 0
    try:
        return max(-1.0, min(0.0, float(value)))
    except (TypeError, ValueError, OverflowError):
        return 0.0

def _mae(rows: list[dict[str, Any]], correction: float, global_correction: float = 0) -> tuple[float, float]:
    errors = [abs(apply_downward_correction(row["company"], row["pred"], global_correction + correction) - row["actual"]) for row in rows]
    return (sum(errors) / len(errors), max(errors)) if errors else (math.inf, math.inf)

def _candidate(train: list[dict[str, Any]], global_correction: float = 0) -> float:
    overgrades = [apply_downward_correction(row["company"], row["pred"], global_correction) - row["actual"] for row in train]
    median = statistics.median(overgrades) if overgrades else 0
    downward = -max(0, min(1, median))
    return round(downward * 2) / 2


def train_calibration(rows: list[dict[str, Any]], global_models: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(f"{row['company']}|{row['bucket']}", []).append(row)
    profiles: dict[str, dict[str, Any]] = {}
    for key, group in sorted(grouped.items()):
        company = key.split("|", 1)[0]
        global_correction = _global_correction(company, global_models)
        unique_cards = len({row["card_id"] for row in group})
        holdout = [row for row in group if _fold(row["card_id"]) == 0]
        train = [row for row in group if _fold(row["card_id"]) != 0]
        if len(holdout) < MIN_HOLDOUT:
            ordered = sorted(group, key=lambda row: hashlib.sha256(row["card_id"].encode()).hexdigest())
            holdout = ordered[::4]
            holdout_ids = {id(row) for row in holdout}
            train = [row for row in ordered if id(row) not in holdout_ids]
        correction = _candidate(train, global_correction)
        before, before_worst = _mae(holdout, 0, global_correction)
        after, after_worst = _mae(holdout, correction, global_correction)
        enough = len(group) >= MIN_ROWS and unique_cards >= MIN_UNIQUE_CARDS and len(holdout) >= MIN_HOLDOUT
        improved = after + 0.05 <= before and after_worst <= before_worst + 0.25
        profiles[key] = {
            "enabled": bool(enough and improved and correction < 0),
            "correction": correction if enough and improved else 0,
            "baseline_global_correction": global_correction,
            "rows": len(group), "unique_cards": unique_cards, "train_rows": len(train),
            "holdout_rows": len(holdout), "baseline_mae": None if math.isinf(before) else round(before, 4),
            "corrected_mae": None if math.isinf(after) else round(after, 4),
            "baseline_worst_error": None if math.isinf(before_worst) else round(before_worst, 4),
            "corrected_worst_error": None if math.isinf(after_worst) else round(after_worst, 4),
            "reason": "holdout-improved" if enough and improved and correction < 0 else
                      "insufficient-official-labels" if not enough else "no-safe-improvement",
        }
    return {
        "version": 4, "engine": ENGINE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "training_rows": len(rows), "profiles": profiles,
        "policy": {
            "official_result_required": True,
            "certification_id_required": True,
            "card_grouped_holdout": True,
            "upward_correction_allowed": False,
            "maximum_downward_correction": -1,
            "vision_learns_residual_after_global": True,
            "four_quadrant_features_isolated": True,
            "eight_zone_features_isolated": True,
            "grading_hierarchy_1_4_8": True,
            "legacy_verified_rows_backward_compatible": True,
            "raw_image_model_retrained": False,
            "official_grade_guaranteed": False,
        },
    }

def train_file(source: Path = INPUT_PATH, target: Path = OUTPUT_PATH) -> dict[str, Any]:
    try:
        payload = _strict_load(source)
    except (OSError, ValueError, TypeError, UnicodeError):
        payload = {}
    global_models = train_company_calibration(sanitize_global_rows(payload))
    result = train_calibration(sanitize_rows(payload), global_models)
    atomic_write_json(target, result, suffix=".vision-calibration.tmp")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TCG 공식등급 교차검증 보정 학습")
    parser.add_argument("--input", type=Path, default=INPUT_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args(argv)
    result = train_file(args.input.resolve(), args.output.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
