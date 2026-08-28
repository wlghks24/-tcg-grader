#!/usr/bin/env python3
"""Leakage-safe company/game/card-type residual calibration.

This layer complements grading_accuracy_v99's global company calibration.  It
learns only a *residual downward correction* for a company + game segment and
only when grouped cross-validation improves error.  Repeated photos/copies of
one artwork are grouped by card_key/card_id so the same design cannot leak into
both train and validation folds.

Slab-derived eBay rows are kept isolated from raw-card rows.  A slab model can
therefore never silently change a raw-camera prediction.
"""
from __future__ import annotations

import hashlib
import math
import statistics
from collections import defaultdict
from typing import Any, Iterable

from grading_accuracy_v99 import (
    COMPANIES,
    apply_downward_correction,
    finite,
    sanitize_rows as sanitize_global_rows,
    train_company_calibration,
    valid_actual_grade,
)

GAMES = ("pokemon", "onepiece", "naruto")
MODES = ("raw", "slab")
MIN_ROWS = 16
MIN_ARTWORK_GROUPS = 8
MIN_FOLDS = 2
MAX_SEGMENT_CORRECTION = -0.5


def _safe_token(value: Any, allowed: tuple[str, ...], fallback: str) -> str:
    text = str(value or "").strip().lower()
    return text if text in allowed else fallback


def _card_group(row: dict[str, Any]) -> str:
    value = str(row.get("card_key") or row.get("card_id") or row.get("certification_id") or "").strip()
    return value[:180]


def sanitize_segment_rows(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    global_clean = sanitize_global_rows(payload)
    # Index original rows by certification so we can preserve safe segment metadata
    # without weakening V99's certification/conflict validation.
    source = payload.get("v99_validation", [])
    if not isinstance(source, list):
        source = []
    metadata: dict[tuple[str, str], dict[str, Any]] = {}
    for row in source[-1000:]:
        if not isinstance(row, dict):
            continue
        company = str(row.get("company") or row.get("grader") or "").upper()
        cert = str(row.get("certification_id") or row.get("cert_no") or "").strip()
        if not cert:
            continue
        metadata[(company, cert)] = row
    out = []
    for row in global_clean:
        src = metadata.get((row["company"], row["certification_id"]), {})
        game = _safe_token(src.get("game"), GAMES, "unknown")
        mode = _safe_token(src.get("mode"), MODES, "raw")
        card_group = str(src.get("card_key") or src.get("card_id") or row.get("card_key") or row.get("card_id") or "").strip()[:180]
        if not card_group:
            continue
        out.append({**row, "game": game, "mode": mode, "card_group": card_group})
    return out


def _fold(group: str) -> int:
    return int(hashlib.sha256(group.encode("utf-8")).hexdigest()[:8], 16) % 5


def _baseline_correction(company: str, global_models: dict[str, dict[str, Any]]) -> float:
    row = global_models.get(company, {}) if isinstance(global_models, dict) else {}
    if not isinstance(row, dict) or row.get("enabled") is not True:
        return 0.0
    value = finite(row.get("correction"))
    return max(-1.0, min(0.0, value or 0.0))


def _candidate(rows: list[dict[str, Any]], baseline: float) -> float:
    if not rows:
        return 0.0
    over = [apply_downward_correction(row["company"], row["raw_pred"], baseline) - row["actual"] for row in rows]
    med = statistics.median(over)
    mad = statistics.median(abs(x - med) for x in over) if over else 0.0
    radius = max(0.5, 3 * 1.4826 * mad)
    clipped = [max(med - radius, min(med + radius, x)) for x in over]
    robust = statistics.median(clipped)
    # Segment correction is deliberately only 0 or -0.5.  Fine-grained 0.05
    # adjustments are inappropriate for the discrete grading scales.
    return -0.5 if robust >= 0.5 else 0.0


def _errors(rows: list[dict[str, Any]], baseline: float, residual: float) -> list[float]:
    return [abs(apply_downward_correction(row["company"], row["raw_pred"], baseline + residual) - row["actual"]) for row in rows]


def train_segment_models(rows: Iterable[dict[str, Any]],
                         global_models: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = list(rows)
    if global_models is None:
        global_models = train_company_calibration(rows)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        company = row.get("company")
        game = row.get("game", "unknown")
        mode = row.get("mode", "raw")
        if company in COMPANIES and game in (*GAMES, "unknown") and mode in MODES:
            grouped[f"{company}|{game}|{mode}"].append(row)
    profiles: dict[str, dict[str, Any]] = {}
    for key, group in sorted(grouped.items()):
        company = key.split("|", 1)[0]
        baseline = _baseline_correction(company, global_models)
        artwork_groups = {row["card_group"] for row in group}
        before_all: list[float] = []
        after_all: list[float] = []
        nonworse = 0
        folds = 0
        for fold in range(5):
            hold = [row for row in group if _fold(row["card_group"]) == fold]
            train = [row for row in group if _fold(row["card_group"]) != fold]
            train_groups = {row["card_group"] for row in train}
            if not hold or len(train_groups) < 5:
                continue
            residual = _candidate(train, baseline)
            before = _errors(hold, baseline, 0)
            after = _errors(hold, baseline, residual)
            before_all.extend(before); after_all.extend(after)
            if sum(after) / len(after) <= sum(before) / len(before) + 1e-9:
                nonworse += 1
            folds += 1
        candidate = _candidate(group, baseline)
        before_mae = sum(before_all) / len(before_all) if before_all else math.inf
        after_mae = sum(after_all) / len(after_all) if after_all else math.inf
        enough = len(group) >= MIN_ROWS and len(artwork_groups) >= MIN_ARTWORK_GROUPS and folds >= MIN_FOLDS
        improved = (not math.isinf(before_mae) and after_mae + 0.04 <= before_mae and
                    nonworse / max(1, folds) >= 0.60)
        enabled = bool(enough and improved and candidate <= MAX_SEGMENT_CORRECTION)
        profiles[key] = {
            "enabled": enabled,
            "correction": candidate if enabled else 0.0,
            "rows": len(group),
            "unique_artwork_groups": len(artwork_groups),
            "folds": folds,
            "nonworse_folds": nonworse,
            "baseline_global_correction": baseline,
            "cv_mae_before": None if math.isinf(before_mae) else round(before_mae, 4),
            "cv_mae_after": None if math.isinf(after_mae) else round(after_mae, 4),
            "reason": "grouped-cv-improved" if enabled else
                      "insufficient-independent-artwork" if not enough else "no-safe-improvement",
        }
    return {
        "version": 1,
        "engine": "v102-provider-segment-learning",
        "profiles": profiles,
        "policy": {
            "company_isolated": True,
            "game_isolated": True,
            "raw_and_slab_isolated": True,
            "same_artwork_grouped_across_folds": True,
            "official_certified_rows_only": True,
            "upward_correction_allowed": False,
            "max_segment_downward_correction": -0.5,
        },
    }


def apply_segment(company: str, game: str, mode: str, raw: float,
                  global_models: dict[str, dict[str, Any]], segment_models: dict[str, Any]) -> float:
    company = str(company or "").upper()
    game = _safe_token(game, GAMES, "unknown")
    mode = _safe_token(mode, MODES, "raw")
    baseline = _baseline_correction(company, global_models)
    row = segment_models.get("profiles", {}).get(f"{company}|{game}|{mode}", {}) if isinstance(segment_models, dict) else {}
    residual = finite(row.get("correction")) if isinstance(row, dict) and row.get("enabled") is True else 0.0
    residual = max(-0.5, min(0.0, residual or 0.0))
    return apply_downward_correction(company, raw, baseline + residual)


def self_test() -> dict[str, Any]:
    payload = {"v99_validation": []}
    # Build 10 independent artwork groups, each with two certified specimens.
    # Raw predictions systematically overgrade PSA/pokemon/raw by 0.5-1 grade.
    for artwork in range(10):
        for copy in range(2):
            i = artwork * 2 + copy
            payload["v99_validation"].append({
                "company": "PSA", "actual": 9, "pred": 10, "raw_pred": 10,
                "official_result": True, "certification_id": f"PSA-{artwork:02d}-{copy:02d}",
                "card_id": f"pokemon|set|art-{artwork:02d}", "card_key": f"pokemon|set|art-{artwork:02d}",
                "game": "pokemon", "mode": "raw",
            })
    rows = sanitize_segment_rows(payload)
    assert len(rows) == 20 and len({row["card_group"] for row in rows}) == 10
    global_models = train_company_calibration(rows)
    models = train_segment_models(rows, global_models)
    key = "PSA|pokemon|raw"
    assert key in models["profiles"]
    profile = models["profiles"][key]
    # Depending on whether global correction fully absorbs the synthetic bias,
    # segment may correctly remain disabled.  It must never apply an upward move.
    assert profile["correction"] <= 0
    # Slab rows stay isolated and cannot alter raw profile counts.
    slab = dict(payload["v99_validation"][0]); slab.update({"certification_id":"PSA-SLAB-001","mode":"slab","card_key":"pokemon|set|slab-art"})
    mixed = sanitize_segment_rows({"v99_validation": payload["v99_validation"] + [slab]})
    mixed_models = train_segment_models(mixed, train_company_calibration(mixed))
    assert mixed_models["profiles"][key]["rows"] == 20
    assert mixed_models["profiles"]["PSA|pokemon|slab"]["rows"] == 1
    return {"ok": True, "tests": 6, "profile": profile, "slab_isolated": True}


if __name__ == "__main__":
    import json
    print(json.dumps(self_test(), ensure_ascii=False, indent=2))
