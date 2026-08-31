#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verified-only grade calibration gate for TCG Grader v135.

Safety invariants:
- Client-side ``verified`` / checkbox flags are never trusted by themselves.
- A training row must match an official certification registry entry by
  company + certification id + exact official grade.
- New rows are added only after an official lookup succeeds, or when the same
  exact certification is already in the locally persisted verified registry.
- An independent raw pre-calibration prediction is mandatory. Slab/reference
  images remain reference evidence and are excluded from RAW grade correction.
- Calibration is company-separated, card-group cross-validated and
  downward-only through ``grading_accuracy_v99``.
"""
from __future__ import annotations

import json
import math
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from grading_accuracy_v99 import (
    COMPANIES,
    train_company_calibration,
    valid_actual_grade,
)

ROOT = Path(__file__).resolve().parent
LEARNING_STORE = ROOT / "learning_store.json"
VERIFIED_CERTS = ROOT / "verified_certifications.json"
VISION_CALIBRATION = ROOT / "vision_calibration.json"
MAX_ROWS = 500

_CERT_RE = re.compile(r"^[A-Za-z0-9._/-]{4,120}$")
_GAME = {"pokemon", "onepiece", "naruto", "unknown"}
_MODE = {"raw", "slab"}
_VISION_FIELDS = {
    "analysisConfidence": (0.0, 100.0),
    "frontCenter": (0.0, 50.0),
    "backCenter": (0.0, 50.0),
    "surfaceRisk": (0.0, 100.0),
    "edgeRisk": (0.0, 100.0),
    "cornerRisk": (0.0, 100.0),
    "surfaceConfidence": (0.0, 100.0),
}


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _finite(value: Any, low: float | None = None, high: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number):
        return None
    if low is not None and number < low:
        return None
    if high is not None and number > high:
        return None
    return number


def _company(value: Any) -> str:
    company = str(value or "").strip().upper()
    return company if company in COMPANIES else ""


def _cert(value: Any) -> str:
    text = str(value or "").strip()
    return text if _CERT_RE.fullmatch(text) else ""


def _cert_key(company: str, cert: str) -> str:
    # Official lookup code treats punctuation as presentation only.
    canonical = re.sub(r"[^A-Za-z0-9]", "", cert).upper()
    return f"{company}|{canonical}"


def _load(path: Path, fallback: Any) -> Any:
    try:
        if path.is_symlink() or not path.is_file():
            return fallback
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(fallback, dict) and not isinstance(value, dict):
            return fallback
        return value
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return fallback


def _atomic_json(path: Path, value: Any) -> None:
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError("unsafe symlink path")
    encoded = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.is_file() and not path.is_symlink():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
            backup = path.with_name(path.name + ".bak")
            if not backup.is_symlink():
                backup.write_text(json.dumps(old, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
            pass
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        tmp.write_text(encoded, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _registry_rows() -> list[dict[str, Any]]:
    payload = _load(VERIFIED_CERTS, {"version": 1, "certifications": []})
    rows = payload.get("certifications", []) if isinstance(payload, dict) else []
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def registry_index() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    conflicts: set[str] = set()
    for row in _registry_rows():
        if row.get("verified") is not True and row.get("official_result") is not True:
            continue
        company = _company(row.get("company") or row.get("grader"))
        cert = _cert(row.get("certification_id") or row.get("cert_no"))
        grade = _finite(row.get("grade", row.get("official_grade")), 1, 10)
        if not company or not cert or grade is None or not valid_actual_grade(company, grade):
            continue
        key = _cert_key(company, cert)
        if key in conflicts:
            continue
        previous = out.get(key)
        if previous is not None and abs(float(previous["grade"]) - grade) > 1e-9:
            out.pop(key, None)
            conflicts.add(key)
            continue
        out[key] = {
            "company": company,
            "certification_id": cert,
            "grade": float(grade),
            "verified": True,
            "official_reference_url": str(row.get("official_reference_url") or row.get("official_url") or "")[:1000],
        }
    return out


def _clean_vision(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    out: dict[str, Any] = {}
    for key, (low, high) in _VISION_FIELDS.items():
        raw = value.get(key)
        if raw is None and key in {"edgeRisk", "cornerRisk"}:
            raw = 0
        number = _finite(raw, low, high)
        if number is None:
            return None
        out[key] = round(number, 2)
    out["multiAngle"] = value.get("multiAngle") is True
    engine = str(value.get("engine") or "")
    if re.fullmatch(r"v\d{1,3}-[A-Za-z0-9-]{1,80}", engine):
        out["engine"] = engine
    return out


def _normalize_training_row(row: Mapping[str, Any], registry: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    company = _company(row.get("company") or row.get("grader"))
    cert = _cert(row.get("certification_id") or row.get("cert_no"))
    actual = _finite(row.get("actual", row.get("actual_grade")), 1, 10)
    raw = _finite(row.get("raw_pred", row.get("predicted_raw")), 1, 10)
    if not company or not cert or actual is None or not valid_actual_grade(company, actual):
        return None, "invalid_identity_or_grade"
    if raw is None:
        return None, "missing_independent_raw_prediction"
    reg = registry.get(_cert_key(company, cert))
    if not reg:
        return None, "not_in_verified_registry"
    if abs(float(reg["grade"]) - actual) > 1e-9:
        return None, "registry_grade_conflict"
    mode = str(row.get("mode") or "raw").lower()
    if mode not in _MODE:
        mode = "raw"
    if mode != "raw":
        return None, "slab_reference_not_raw_calibration"
    game = str(row.get("game") or "unknown").lower()
    if game not in _GAME:
        game = "unknown"
    card_key = str(row.get("card_key") or "").strip()[:180]
    card_id = str(row.get("card_id") or card_key or cert).strip()[:120]
    item: dict[str, Any] = {
        "company": company,
        "actual": float(actual),
        "raw_pred": float(raw),
        "pred": float(_finite(row.get("pred"), 1, 10) or raw),
        "certification_id": cert,
        "card_id": card_id,
        "official_result": True,
        "server_verified": True,
        "mode": "raw",
        "game": game,
    }
    if card_key:
        item["card_key"] = card_key
    vision = _clean_vision(row.get("vision"))
    if vision:
        item["vision"] = vision
    return item, "eligible"


def eligible_training_rows(store: Mapping[str, Any] | None = None) -> tuple[list[dict[str, Any]], dict[str, int]]:
    payload = dict(store) if isinstance(store, Mapping) else _load(LEARNING_STORE, {})
    registry = registry_index()
    candidates: list[Mapping[str, Any]] = []
    for key in ("v99_validation", "v30_validation", "v11_validation", "confirmed_samples"):
        rows = payload.get(key, []) if isinstance(payload, dict) else []
        if isinstance(rows, list):
            candidates.extend(row for row in rows if isinstance(row, Mapping))
    dedup: dict[str, dict[str, Any]] = {}
    conflicts: set[str] = set()
    stats: dict[str, int] = {"seen": 0, "eligible": 0, "not_in_verified_registry": 0,
                             "missing_independent_raw_prediction": 0,
                             "registry_grade_conflict": 0,
                             "slab_reference_not_raw_calibration": 0,
                             "invalid_identity_or_grade": 0, "cert_conflicts": 0}
    for row in candidates[-4000:]:
        stats["seen"] += 1
        item, reason = _normalize_training_row(row, registry)
        if item is None:
            stats[reason] = stats.get(reason, 0) + 1
            continue
        key = _cert_key(item["company"], item["certification_id"])
        if key in conflicts:
            continue
        previous = dedup.get(key)
        if previous is not None and abs(float(previous["actual"]) - float(item["actual"])) > 1e-9:
            dedup.pop(key, None)
            conflicts.add(key)
            stats["cert_conflicts"] += 1
            continue
        dedup[key] = item
    rows = list(dedup.values())[-MAX_ROWS:]
    stats["eligible"] = len(rows)
    return rows, stats


def _state(n: int, enabled: bool) -> str:
    if n < 10:
        return "observe"
    if not enabled:
        return "validated_wait"
    if n < 30:
        return "limited"
    if n < 60:
        return "strong"
    return "mature"


def _vision_profiles() -> dict[str, Any]:
    data = _load(VISION_CALIBRATION, {})
    profiles = data.get("profiles", {}) if isinstance(data, dict) else {}
    return profiles if isinstance(profiles, dict) else {}


def model_status() -> dict[str, Any]:
    rows, audit = eligible_training_rows()
    models = train_company_calibration(rows)
    companies: dict[str, Any] = {}
    for company in COMPANIES:
        row = models.get(company, {})
        n = int(row.get("n") or 0)
        enabled = row.get("enabled") is True
        companies[company] = {
            **row,
            "n": n,
            "state": _state(n, enabled),
            "correction": float(row.get("correction") or 0) if enabled else 0.0,
            "mae": row.get("cv_mae_after") if enabled else row.get("cv_mae_before"),
            "game_adjustments": {},
        }
    return {
        "ok": True,
        "version": 135,
        "engine": "v135-verified-only-crossvalidated-downward-calibration",
        "verified_training_rows": len(rows),
        "companies": companies,
        "vision_profiles": _vision_profiles(),
        "audit": audit,
        "policy": {
            "client_verified_flag_trusted": False,
            "official_registry_exact_match_required": True,
            "independent_raw_prediction_required": True,
            "slab_reference_trains_raw_calibration": False,
            "company_separated": True,
            "card_grouped_cross_validation": True,
            "upward_correction_allowed": False,
            "minimum_rows_to_enable": 10,
            "minimum_unique_cards_to_enable": 8,
        },
    }


def _persist_verified_cert(company: str, cert: str, grade: float, verify_result: Mapping[str, Any]) -> None:
    payload = _load(VERIFIED_CERTS, {"version": 1, "certifications": []})
    if not isinstance(payload, dict):
        payload = {"version": 1, "certifications": []}
    rows = payload.get("certifications", [])
    if not isinstance(rows, list):
        rows = []
    key = _cert_key(company, cert)
    kept: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        c = _company(row.get("company") or row.get("grader"))
        existing_cert = _cert(row.get("certification_id") or row.get("cert_no"))
        if c and existing_cert and _cert_key(c, existing_cert) == key:
            existing_grade = _finite(row.get("grade", row.get("official_grade")), 1, 10)
            if existing_grade is not None and abs(existing_grade - grade) > 1e-9:
                raise ValueError("verified registry grade conflict")
            continue
        kept.append(row)
    kept.append({
        "company": company,
        "certification_id": cert,
        "grade": float(grade),
        "verified": True,
        "official_reference_url": str(verify_result.get("official_url") or "")[:1000],
        "verification_method": "official_live_lookup_v135",
        "verified_at": _now(),
    })
    payload["version"] = max(1, int(payload.get("version") or 1))
    payload["certifications"] = kept[-2000:]
    _atomic_json(VERIFIED_CERTS, payload)


def _append_store_row(row: dict[str, Any]) -> None:
    payload = _load(LEARNING_STORE, {})
    if not isinstance(payload, dict):
        payload = {}
    rows = payload.get("v99_validation", [])
    if not isinstance(rows, list):
        rows = []
    key = _cert_key(row["company"], row["certification_id"])
    kept: list[dict[str, Any]] = []
    for old in rows:
        if not isinstance(old, dict):
            continue
        c = _company(old.get("company") or old.get("grader"))
        cert = _cert(old.get("certification_id") or old.get("cert_no"))
        if c and cert and _cert_key(c, cert) == key:
            old_actual = _finite(old.get("actual"), 1, 10)
            if old_actual is not None and abs(old_actual - float(row["actual"])) > 1e-9:
                raise ValueError("learning store certification conflict")
            continue
        kept.append(old)
    kept.append(row)
    payload["version"] = max(3, int(payload.get("version") or 0))
    payload["updated_at"] = _now()
    payload["v99_validation"] = kept[-MAX_ROWS:]
    payload.setdefault("v30_validation", [])
    payload.setdefault("v11_validation", [])
    _atomic_json(LEARNING_STORE, payload)


def submit_verified_sample(
    payload: Mapping[str, Any],
    *,
    verifier: Callable[[str, str, float], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError("sample must be an object")
    company = _company(payload.get("company") or payload.get("grader"))
    cert = _cert(payload.get("certification_id") or payload.get("cert_no"))
    actual = _finite(payload.get("actual_grade", payload.get("actual")), 1, 10)
    raw = _finite(payload.get("raw_pred", payload.get("predicted_raw")), 1, 10)
    if not company or not cert or actual is None or not valid_actual_grade(company, actual):
        raise ValueError("company/certification/official grade is invalid")
    if raw is None:
        raise ValueError("independent raw prediction is required")
    mode = str(payload.get("mode") or "raw").lower()
    if mode not in _MODE:
        mode = "raw"

    registry = registry_index()
    existing = registry.get(_cert_key(company, cert))
    verify_result: Mapping[str, Any]
    if existing and abs(float(existing["grade"]) - actual) <= 1e-9:
        verify_result = {"ok": True, "verified": True, "grade": actual,
                         "official_url": existing.get("official_reference_url", ""),
                         "verification_method": "persisted_verified_registry"}
    else:
        if verifier is None:
            from grading_cert_verifier import verify_cert
            verifier = lambda c, n, g: verify_cert(c, n, expected_grade=g)
        verify_result = verifier(company, cert, float(actual))
        if not isinstance(verify_result, Mapping) or verify_result.get("verified") is not True:
            return {"ok": False, "accepted": False, "reason": "official_verification_required",
                    "verification": dict(verify_result) if isinstance(verify_result, Mapping) else {}}
        verified_grade = _finite(verify_result.get("grade"), 1, 10)
        if verified_grade is None or abs(verified_grade - actual) > 1e-9:
            return {"ok": False, "accepted": False, "reason": "official_grade_conflict",
                    "verification": dict(verify_result)}
        _persist_verified_cert(company, cert, float(actual), verify_result)

    game = str(payload.get("game") or "unknown").lower()
    if game not in _GAME:
        game = "unknown"
    card_key = str(payload.get("card_key") or "").strip()[:180]
    pred = _finite(payload.get("pred"), 1, 10)
    vision = _clean_vision(payload.get("vision"))
    row: dict[str, Any] = {
        "time": _now(),
        "company": company,
        "grader": company,
        "actual": float(actual),
        "pred": float(pred if pred is not None else raw),
        "raw_pred": float(raw),
        "match": abs(float(pred if pred is not None else raw) - float(actual)) < 1e-9,
        "mode": mode,
        "game": game,
        "official_result": True,
        "server_verified": True,
        "certification_id": cert,
        "card_id": str(payload.get("card_id") or card_key or cert)[:120],
        "verification_method": "official_registry_gate_v135",
    }
    if card_key:
        row["card_key"] = card_key
    if vision:
        row["vision"] = vision
    _append_store_row(row)

    # Rebuild the existing safe vision residual calibration from registry-gated rows.
    try:
        from vision_calibration import train_file
        train_file(LEARNING_STORE, VISION_CALIBRATION)
    except (ImportError, OSError, ValueError, TypeError):
        pass

    return {"ok": True, "accepted": True, "sample": row, "verification": dict(verify_result),
            "model": model_status()}


def audit() -> dict[str, Any]:
    status = model_status()
    registry = registry_index()
    return {
        "ok": True,
        "version": 135,
        "verified_registry_entries": len(registry),
        "verified_training_rows": status["verified_training_rows"],
        "audit": status["audit"],
        "companies": status["companies"],
        "policy": status["policy"],
    }


if __name__ == "__main__":
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
