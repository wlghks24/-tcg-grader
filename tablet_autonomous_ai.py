#!/usr/bin/env python3
"""Bounded autonomous controller for Tablet GPT / Lenovo TCG runtime.

The controller observes verified repository/runtime evidence, selects an allowlisted
capability, and may request only existing protected workflows. Learned/free-form
text is never executable and neural output is priority-only. New capabilities are
structured proposals that still require branch/PR/full-regression verification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from safe_runtime import atomic_write_json, exclusive_file_lock
except ImportError:  # isolated unit-test fallback; repository runtime provides safe_runtime
    from contextlib import contextmanager
    def atomic_write_json(path: Path, payload: Any, suffix: str = ".tmp") -> None:
        target = Path(path)
        tmp = Path(str(target) + suffix)
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, target)
    @contextmanager
    def exclusive_file_lock(_: Path, **__: Any):
        yield

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "TABLET_AUTONOMOUS_AI_STATE.json"
MODEL = ROOT / "TABLET_AUTONOMOUS_AI_MODEL.json"
REPORT = ROOT / "TABLET_AUTONOMOUS_AI_REPORT.json"
PROPOSALS = ROOT / "TABLET_AUTONOMOUS_AI_PROPOSALS.json"
SCHEMA = 1
MODEL_SCHEMA = 1
MAX_HISTORY = 500
MAX_PROPOSALS = 200
MAX_LABELS = 2000
MIN_LABELS = 200
MIN_CLASS = 30
MODEL_MAX_AGE_DAYS = 30
COOLDOWN_HOURS = 6
HIDDEN = 8
EPOCHS = 48
LR = 0.03
L2 = 0.0005
SEED = 20261001

SIGNALS = (
    "market_shift", "market_volatility", "source_degraded", "stale", "conflict",
    "unknown", "ocr_gap", "grading_gap", "tablet_runtime_gap", "sync_gap",
    "performance_gap",
)
CAPABILITIES: dict[str, dict[str, Any]] = {
    "market_regime_adaptation": {
        "action": "COLLECT_AND_REEVALUATE", "domain": "market", "risk": "medium",
        "description": "시장 변동·가격 변화가 커지면 검증 수집을 다시 실행하고 우선순위를 재평가",
        "checks": ["market_provenance", "fx_freshness", "completed_sale_separation", "collection_verification"],
    },
    "source_route_rebalancing": {
        "action": "ADJUST_COLLECTION_PRIORITY", "domain": "market", "risk": "medium",
        "description": "반복 실패·공백이 있는 수집 경로를 검증된 관측값 기준으로 재평가",
        "checks": ["source_health", "bounded_retry", "no_403_429_bypass", "verified_learning_only"],
    },
    "ocr_identity_recalibration": {
        "action": "RECALIBRATE_VERIFIED_ONLY", "domain": "vision", "risk": "high",
        "description": "OCR·카드번호·판본 식별 오차를 검증된 표본으로만 재교정",
        "checks": ["card_number_exact", "edition_language_isolation", "unknown_conflict_hold", "verified_label_only"],
    },
    "grading_calibration": {
        "action": "RECALIBRATE_VERIFIED_ONLY", "domain": "grading", "risk": "high",
        "description": "PSA/BGS/CGC/TAG/BRG 예측 오차를 회사·정확등급별 검증 표본으로만 재교정",
        "checks": ["grader_isolation", "exact_grade", "predictive_only", "verified_label_only"],
    },
    "tablet_runtime_recovery": {
        "action": "RUN_EXISTING_RECOVERY", "domain": "tablet", "risk": "medium",
        "description": "Termux/Lenovo runtime·부팅·PID·health 이상 시 기존 검증 복구 경로 선택",
        "checks": ["pid_ownership", "health_endpoint", "fast_forward_only", "device_state_preserved"],
    },
    "tablet_sync_recovery": {
        "action": "SYNC_CHECK_AND_RECOVER", "domain": "tablet", "risk": "medium",
        "description": "Tablet GPT↔TCG Grader contract/snapshot/receipt 정렬 이상 재검증",
        "checks": ["latest_contract_dynamic", "learning_digest", "receipt_match", "sync_stale_fail_closed"],
    },
    "performance_tuning": {
        "action": "PROFILE_AND_PROPOSE", "domain": "runtime", "risk": "medium",
        "description": "지연·중복 IO·캐시 미스를 프로파일링하고 최소 변경 개선안을 제안",
        "checks": ["targeted_benchmark", "full_regression_if_runtime", "memory_bound", "no_test_weakening"],
    },
    "feature_gap_expansion": {
        "action": "PROPOSE_FEATURE", "domain": "control", "risk": "high",
        "description": "기존 capability가 설명하지 못하는 반복 공백을 새 기능 후보로 구조화",
        "checks": ["evidence_required", "acceptance_tests_required", "branch_pr_only", "full_regression_required"],
    },
}
CAPABILITY_ORDER = tuple(CAPABILITIES)
AUTO_ACTIONS = {
    "COLLECT_AND_REEVALUATE", "ADJUST_COLLECTION_PRIORITY",
    "RUN_EXISTING_RECOVERY", "SYNC_CHECK_AND_RECOVER",
}
FORBIDDEN = {
    "source_code_from_learned_text": False,
    "shell_from_learned_text": False,
    "git_write_from_neural_output": False,
    "direct_main_write": False,
    "branch_protection_bypass": False,
    "verification_bypass": False,
    "unknown_conflict_auto_promotion": False,
    "price_invention": False,
    "grade_truth_from_prediction": False,
    "403_429_bypass": False,
}
FEATURE_COUNT = len(SIGNALS) + len(CAPABILITY_ORDER) + 1


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clip01(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return max(0.0, min(1.0, number)) if math.isfinite(number) else 0.0


def strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON key")
        out[key] = value
    return out


def reject_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def read_json(path: Path, *, max_bytes: int = 20_000_000) -> Any:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > max_bytes:
        raise ValueError("unsafe or missing JSON")
    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=strict_object,
        parse_constant=reject_constant,
    )


def payload_time(payload: Any) -> datetime | None:
    if not isinstance(payload, dict):
        return None
    for key in ("updated_at", "generated_at", "checked_at", "collected_at", "built_at", "timestamp"):
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        try:
            stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            continue
        if stamp.tzinfo is not None and stamp.utcoffset() is not None:
            return stamp.astimezone(timezone.utc)
    return None


def fresh(payload: Any, now: datetime, hours: float) -> bool:
    stamp = payload_time(payload)
    if stamp is None:
        return False
    age = (now - stamp).total_seconds() / 3600.0
    return -0.084 <= age <= hours


def walk(value: Any, *, limit: int = 30000) -> Iterable[tuple[str, Any]]:
    stack: list[tuple[str, Any]] = [("", value)]
    seen = 0
    while stack and seen < limit:
        key, item = stack.pop()
        seen += 1
        yield key, item
        if isinstance(item, dict):
            for child_key, child in list(item.items())[-500:]:
                stack.append((str(child_key)[:120], child))
        elif isinstance(item, list):
            for child in item[-500:]:
                stack.append((key, child))


def scan_payload(payload: Any, signals: dict[str, float]) -> None:
    counts = {key: 0 for key in (
        "degraded", "stale", "conflict", "unknown", "ocr", "grade", "grading",
        "tablet", "termux", "lenovo", "sync", "alignment", "latency", "timeout", "slow",
    )}
    changes: list[float] = []
    vol: list[float] = []
    for key, value in walk(payload):
        low = key.casefold()
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            number = float(value)
            if math.isfinite(number):
                if any(token in low for token in ("change_pct", "price_change_pct", "change_percent")):
                    changes.append(abs(number))
                if "volatility" in low or "spread_pct" in low:
                    vol.append(abs(number))
        text = low + " " + (value.casefold()[:600] if isinstance(value, str) else "")
        for token in counts:
            if token in text:
                counts[token] += 1
    signals["market_shift"] = max(signals["market_shift"], min(1.0, max(changes, default=0.0) / 20.0))
    volatility = max(vol, default=0.0)
    if volatility > 1.0:
        volatility /= 100.0
    signals["market_volatility"] = max(signals["market_volatility"], min(1.0, volatility))
    signals["source_degraded"] = max(signals["source_degraded"], min(1.0, counts["degraded"] / 5.0))
    signals["stale"] = max(signals["stale"], min(1.0, counts["stale"] / 4.0))
    signals["conflict"] = max(signals["conflict"], min(1.0, counts["conflict"] / 3.0))
    signals["unknown"] = max(signals["unknown"], min(1.0, counts["unknown"] / 5.0))
    signals["ocr_gap"] = max(signals["ocr_gap"], min(1.0, counts["ocr"] / 4.0))
    signals["grading_gap"] = max(signals["grading_gap"], min(1.0, (counts["grade"] + counts["grading"]) / 8.0))
    signals["tablet_runtime_gap"] = max(signals["tablet_runtime_gap"], min(1.0, (counts["tablet"] + counts["termux"] + counts["lenovo"]) / 8.0))
    signals["sync_gap"] = max(signals["sync_gap"], min(1.0, (counts["sync"] + counts["alignment"]) / 5.0))
    signals["performance_gap"] = max(signals["performance_gap"], min(1.0, (counts["latency"] + counts["timeout"] + counts["slow"]) / 5.0))


def latest_tablet_delta(root: Path) -> Path | None:
    folder = root / "TCG_CROSSCHECK" / "TABLET_GPT"
    candidates: list[tuple[int, Path]] = []
    for path in folder.glob("learning_snapshot_v*_delta.json") if folder.is_dir() else ():
        try:
            version = int(path.stem.split("_v", 1)[1].split("_", 1)[0])
        except (IndexError, ValueError):
            continue
        candidates.append((version, path))
    return max(candidates, default=(0, None), key=lambda row: row[0])[1]


def collect_context(root: Path = ROOT, *, now: datetime | None = None) -> dict[str, Any]:
    root = Path(root)
    stamp = now or datetime.now(timezone.utc)
    signals = {name: 0.0 for name in SIGNALS}
    evidence: list[dict[str, Any]] = []
    market_fresh = False
    runtime_fresh = False
    specs = (
        ("market_watch.json", "market", 72.0),
        ("market_prices.json", "market", 72.0),
        ("source_collection_stats.json", "market", 24.0),
        ("adaptive_collection_stats.json", "market", 24.0),
        ("collection_runtime_health.json", "runtime", 2.0),
        ("CURRENT_RUNTIME_VERIFICATION_REPORT.json", "runtime", 24.0),
        ("AI_AUTO_TRACKER_REPORT.json", "tracker", 24.0),
        ("MARKET_AI_TRACKER_REPORT.json", "tracker", 24.0),
    )
    for name, domain, max_age in specs:
        path = root / name
        try:
            payload = read_json(path)
            is_fresh = fresh(payload, stamp, max_age)
            scan_payload(payload, signals)
            evidence.append({"path": name, "domain": domain, "fresh": is_fresh})
            if domain == "market" and is_fresh:
                market_fresh = True
            if domain == "runtime" and is_fresh:
                runtime_fresh = True
            if not is_fresh:
                signals["stale"] = max(signals["stale"], 0.35)
        except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError):
            evidence.append({"path": name, "domain": domain, "fresh": False, "state": "unavailable"})
    delta = latest_tablet_delta(root)
    if delta is not None:
        try:
            payload = read_json(delta)
            scan_payload(payload, signals)
            evidence.append({"path": delta.relative_to(root).as_posix(), "domain": "tablet_sync", "fresh": fresh(payload, stamp, 168.0)})
        except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError):
            signals["sync_gap"] = max(signals["sync_gap"], 0.6)
    return {
        "observed_at": stamp.isoformat(timespec="seconds"),
        "signals": {key: round(clip01(value), 4) for key, value in signals.items()},
        "market_fresh": market_fresh,
        "runtime_fresh": runtime_fresh,
        "evidence": evidence[:30],
    }


def default_state() -> dict[str, Any]:
    return {"schema": SCHEMA, "updated_at": None, "labels": [], "history": [], "proposals": [], "last_actions": {}}


def sanitize_state(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
        return None
    state = default_state()
    state["updated_at"] = raw.get("updated_at") if isinstance(raw.get("updated_at"), str) else None
    state["labels"] = [row for row in (raw.get("labels") or [])[-MAX_LABELS:] if isinstance(row, dict)]
    state["history"] = [row for row in (raw.get("history") or [])[-MAX_HISTORY:] if isinstance(row, dict)]
    state["proposals"] = [row for row in (raw.get("proposals") or [])[-MAX_PROPOSALS:] if isinstance(row, dict)]
    state["last_actions"] = {str(k): str(v) for k, v in (raw.get("last_actions") or {}).items() if k in CAPABILITIES and isinstance(v, str)}
    return state


def load_state(path: Path = STATE) -> tuple[dict[str, Any], str, bool]:
    path = Path(path)
    backup = path.with_name(path.name + ".bak")
    for candidate, source in ((path, "primary"), (backup, "backup")):
        try:
            clean = sanitize_state(read_json(candidate))
        except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError):
            clean = None
        if clean is not None:
            return clean, source, source == "backup"
    existed = path.exists() or backup.exists()
    return default_state(), ("corruption_hold" if existed else "fresh"), existed


def save_state(state: dict[str, Any], path: Path = STATE, *, corruption_hold: bool = False) -> None:
    if corruption_hold:
        raise ValueError("state persistence blocked by corruption hold")
    path = Path(path)
    backup = path.with_name(path.name + ".bak")
    previous, source, _ = load_state(path)
    clean = sanitize_state({**state, "schema": SCHEMA}) or default_state()
    clean["updated_at"] = now_iso()
    if source in {"primary", "backup"}:
        atomic_write_json(backup, previous, suffix=".tablet-ai-backup.tmp")
    atomic_write_json(path, clean, suffix=".tablet-ai-state.tmp")


def feature_vector(context: dict[str, Any], capability_id: str) -> list[float]:
    signals = context.get("signals") if isinstance(context.get("signals"), dict) else {}
    values = [clip01(signals.get(name)) for name in SIGNALS]
    values.extend(1.0 if capability_id == item else 0.0 for item in CAPABILITY_ORDER)
    values.append(1.0)
    return values


def sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-50.0, min(50.0, value))))


def init_model(seed: int = SEED) -> dict[str, Any]:
    rng = random.Random(seed)
    scale = 1.0 / math.sqrt(FEATURE_COUNT)
    return {
        "schema": MODEL_SCHEMA, "trained_at": None, "feature_count": FEATURE_COUNT,
        "hidden": HIDDEN,
        "w1": [[rng.uniform(-scale, scale) for _ in range(FEATURE_COUNT)] for _ in range(HIDDEN)],
        "b1": [0.0] * HIDDEN, "w2": [rng.uniform(-0.3, 0.3) for _ in range(HIDDEN)], "b2": 0.0,
    }


def predict(model: dict[str, Any], values: list[float]) -> float:
    hidden = [math.tanh(sum(w * x for w, x in zip(row, values)) + bias) for row, bias in zip(model["w1"], model["b1"])]
    return sigmoid(sum(w * h for w, h in zip(model["w2"], hidden)) + float(model["b2"]))


def train_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    model = init_model()
    data = [(feature_vector(row["context"], row["capability_id"]), 1.0 if row["outcome"] else 0.0) for row in rows]
    rng = random.Random(SEED ^ 0x5F3759DF)
    for epoch in range(EPOCHS):
        rng.shuffle(data)
        rate = LR * (1.0 - 0.35 * epoch / max(1, EPOCHS - 1))
        for x, target in data:
            hidden = [math.tanh(sum(w * v for w, v in zip(row, x)) + b) for row, b in zip(model["w1"], model["b1"])]
            pred = sigmoid(sum(w * h for w, h in zip(model["w2"], hidden)) + model["b2"])
            delta2 = pred - target
            old_w2 = list(model["w2"])
            for j in range(HIDDEN):
                model["w2"][j] -= rate * (delta2 * hidden[j] + L2 * model["w2"][j])
            model["b2"] -= rate * delta2
            for j in range(HIDDEN):
                delta1 = delta2 * old_w2[j] * (1.0 - hidden[j] ** 2)
                for i in range(FEATURE_COUNT):
                    model["w1"][j][i] -= rate * (delta1 * x[i] + L2 * model["w1"][j][i])
                model["b1"][j] -= rate * delta1
    return model


def train_verified_policy(labels: list[dict[str, Any]]) -> dict[str, Any]:
    clean = [row for row in labels if isinstance(row, dict) and row.get("verification_level") == "full_regression" and row.get("capability_id") in CAPABILITIES and type(row.get("outcome")) is bool and isinstance(row.get("context"), dict)]
    positives = sum(row["outcome"] for row in clean)
    negatives = len(clean) - positives
    if len(clean) < MIN_LABELS or min(positives, negatives) < MIN_CLASS:
        return {"active": False, "reason": "insufficient_verified_labels", "labels": len(clean), "positives": positives, "negatives": negatives}
    clean.sort(key=lambda row: (str(row.get("recorded_at") or ""), str(row.get("sample_id") or "")))
    split = max(1, int(len(clean) * 0.8))
    train, holdout = clean[:split], clean[split:]
    model = train_rows(train)
    predictions = [predict(model, feature_vector(row["context"], row["capability_id"])) >= 0.5 for row in holdout]
    accuracy = sum(pred == row["outcome"] for pred, row in zip(predictions, holdout)) / max(1, len(holdout))
    rate = sum(row["outcome"] for row in holdout) / max(1, len(holdout))
    baseline = max(rate, 1.0 - rate)
    if accuracy < max(0.60, baseline + 0.02):
        return {"active": False, "reason": "holdout_gate_failed", "accuracy": round(accuracy, 4), "baseline": round(baseline, 4), "labels": len(clean)}
    model.update({"active": True, "trained_at": now_iso(), "labels": len(clean), "accuracy": round(accuracy, 4), "baseline": round(baseline, 4), "neural_output_is_priority_only": True})
    return model


def load_model(path: Path = MODEL) -> dict[str, Any] | None:
    try:
        model = read_json(path, max_bytes=2_000_000)
        if not isinstance(model, dict) or model.get("schema") != MODEL_SCHEMA or model.get("feature_count") != FEATURE_COUNT or model.get("active") is not True:
            return None
        stamp = datetime.fromisoformat(str(model["trained_at"]).replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - stamp.astimezone(timezone.utc)
        if age < timedelta(minutes=-5) or age > timedelta(days=MODEL_MAX_AGE_DAYS):
            return None
        if len(model.get("w1", [])) != HIDDEN or len(model.get("w2", [])) != HIDDEN:
            return None
        return model
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, json.JSONDecodeError):
        return None


def deterministic_scores(context: dict[str, Any]) -> dict[str, float]:
    s = context["signals"]
    return {
        "market_regime_adaptation": clip01(0.50 * s["market_shift"] + 0.30 * s["market_volatility"] + 0.20 * s["stale"]),
        "source_route_rebalancing": clip01(0.65 * s["source_degraded"] + 0.20 * s["stale"] + 0.15 * s["performance_gap"]),
        "ocr_identity_recalibration": clip01(0.65 * s["ocr_gap"] + 0.20 * s["conflict"] + 0.15 * s["unknown"]),
        "grading_calibration": clip01(0.65 * s["grading_gap"] + 0.20 * s["conflict"] + 0.15 * s["unknown"]),
        "tablet_runtime_recovery": clip01(0.75 * s["tablet_runtime_gap"] + 0.25 * s["performance_gap"]),
        "tablet_sync_recovery": clip01(0.80 * s["sync_gap"] + 0.20 * s["stale"]),
        "performance_tuning": clip01(0.80 * s["performance_gap"] + 0.20 * s["source_degraded"]),
        "feature_gap_expansion": clip01(0.35 * s["unknown"] + 0.25 * s["conflict"] + 0.15 * s["ocr_gap"] + 0.15 * s["grading_gap"] + 0.10 * s["sync_gap"]),
    }


def cooldown_hold(state: dict[str, Any], capability_id: str, now: datetime) -> bool:
    raw = (state.get("last_actions") or {}).get(capability_id)
    if not isinstance(raw, str):
        return False
    try:
        stamp = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return True
    return -300 <= (now - stamp).total_seconds() < COOLDOWN_HOURS * 3600


def hard_holds(capability_id: str, context: dict[str, Any], state: dict[str, Any], now: datetime) -> list[str]:
    s = context["signals"]
    reasons: list[str] = []
    if capability_id in {"market_regime_adaptation", "source_route_rebalancing"} and not context["market_fresh"]:
        reasons.append("MARKET_EVIDENCE_NOT_FRESH")
    if capability_id in {"ocr_identity_recalibration", "grading_calibration"} and (s["conflict"] > 0 or s["unknown"] > 0):
        reasons.append("UNKNOWN_CONFLICT_REQUIRES_VERIFIED_LABELS")
    if capability_id == "tablet_runtime_recovery" and not context["runtime_fresh"]:
        reasons.append("RUNTIME_EVIDENCE_NOT_FRESH")
    if cooldown_hold(state, capability_id, now):
        reasons.append("ACTION_COOLDOWN_ACTIVE")
    return reasons


def plan(context: dict[str, Any], state: dict[str, Any], model: dict[str, Any] | None = None, *, now: datetime | None = None) -> dict[str, Any]:
    stamp = now or datetime.now(timezone.utc)
    base = deterministic_scores(context)
    rows: list[dict[str, Any]] = []
    for capability_id in CAPABILITY_ORDER:
        capability = CAPABILITIES[capability_id]
        neural = predict(model, feature_vector(context, capability_id)) if model is not None else 0.5
        score = base[capability_id] if model is None else 0.80 * base[capability_id] + 0.20 * neural
        holds = hard_holds(capability_id, context, state, stamp)
        threshold = 0.34 if capability_id == "feature_gap_expansion" else 0.28
        selected = score >= threshold
        rows.append({
            "capability_id": capability_id, "domain": capability["domain"], "action": capability["action"],
            "risk": capability["risk"], "score": round(clip01(score), 4), "deterministic_score": round(base[capability_id], 4),
            "neural_priority_active": model is not None, "neural_score": round(neural, 4) if model is not None else None,
            "selected": selected,
            "auto_execution_allowed": bool(selected and not holds and capability["action"] in AUTO_ACTIONS),
            "hold_reasons": holds, "checks": capability["checks"], "description": capability["description"],
        })
    rows.sort(key=lambda row: (-row["score"], row["capability_id"]))
    return {"schema": SCHEMA, "generated_at": now_iso(), "context": context, "decisions": rows, "safety": {**FORBIDDEN, "neural_priority_only": True, "capability_allowlist_only": True, "new_feature_requires_structured_proposal": True, "code_change_requires_branch_pr_full_regression": True}}


def proposal_id(capability_id: str, context: dict[str, Any]) -> str:
    material = capability_id + "|" + json.dumps(context.get("signals", {}), sort_keys=True, separators=(",", ":"))
    return "TAI-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def build_proposals(result: dict[str, Any]) -> list[dict[str, Any]]:
    context = result["context"]
    proposals = []
    for row in result["decisions"]:
        if not row["selected"] or (row["capability_id"] != "feature_gap_expansion" and row["score"] < 0.60):
            continue
        proposals.append({
            "proposal_id": proposal_id(row["capability_id"], context), "capability_id": row["capability_id"],
            "created_at": now_iso(), "reason": row["description"], "evidence": context["evidence"][:20],
            "acceptance_tests": row["checks"], "implementation_policy": "existing_verified_rule_or_branch_pr_only",
            "source_code_generated": False, "learned_text_executable": False,
            "requires_full_regression": True, "requires_post_merge_verification": True,
        })
    return proposals[:20]


def record_verified_outcome(state: dict[str, Any], *, capability_id: str, context: dict[str, Any], outcome: bool, verification_level: str, metric_delta: float = 0.0) -> dict[str, Any]:
    if capability_id not in CAPABILITIES:
        return {"accepted": False, "reason": "unknown_capability"}
    if verification_level != "full_regression" or type(outcome) is not bool:
        return {"accepted": False, "reason": "full_regression_verification_required"}
    signals = {name: clip01((context.get("signals") or {}).get(name)) for name in SIGNALS}
    sample_material = capability_id + "|" + json.dumps(signals, sort_keys=True) + "|" + str(outcome) + "|" + str(len(state.get("labels", [])))
    row = {
        "sample_id": hashlib.sha256(sample_material.encode("utf-8")).hexdigest()[:24],
        "capability_id": capability_id, "context": {"signals": signals}, "outcome": outcome,
        "metric_delta": max(-1.0, min(1.0, float(metric_delta))), "verification_level": "full_regression", "recorded_at": now_iso(),
    }
    labels = [item for item in state.get("labels", []) if isinstance(item, dict)]
    if not any(item.get("sample_id") == row["sample_id"] for item in labels):
        labels.append(row)
    state["labels"] = labels[-MAX_LABELS:]
    return {"accepted": True, "sample_id": row["sample_id"], "label_count": len(state["labels"])}


def mark_action(capability_id: str, state_path: Path = STATE) -> dict[str, Any]:
    if capability_id not in CAPABILITIES or CAPABILITIES[capability_id]["action"] not in AUTO_ACTIONS:
        return {"ok": False, "reason": "action_not_allowlisted"}
    with exclusive_file_lock(state_path, timeout_seconds=3.0, stale_seconds=300):
        state, source, corruption = load_state(state_path)
        if corruption:
            return {"ok": False, "reason": "state_corruption_hold", "source": source}
        state["last_actions"][capability_id] = now_iso()
        state["history"].append({"at": now_iso(), "event": "safe_action_dispatched", "capability_id": capability_id})
        save_state(state, state_path)
    return {"ok": True, "capability_id": capability_id}


def run_cycle(root: Path = ROOT, *, persist: bool = True) -> dict[str, Any]:
    context = collect_context(root)
    state, source, corruption = load_state(STATE)
    model = load_model(MODEL)
    result = plan(context, state, model=model)
    proposals = build_proposals(result)
    result.update({"state_source": source, "state_corruption_hold": corruption, "neural_model_active": model is not None, "proposals": proposals})
    if persist and not corruption:
        state["history"].append({"at": now_iso(), "event": "autonomous_cycle", "selected": [row["capability_id"] for row in result["decisions"] if row["selected"]], "neural_model_active": model is not None})
        known = {row.get("proposal_id"): row for row in state["proposals"] if isinstance(row, dict)}
        for proposal in proposals:
            known[proposal["proposal_id"]] = proposal
        state["proposals"] = list(known.values())[-MAX_PROPOSALS:]
        with exclusive_file_lock(STATE, timeout_seconds=3.0, stale_seconds=300):
            save_state(state, STATE)
        atomic_write_json(REPORT, result, suffix=".tablet-ai-report.tmp")
        atomic_write_json(PROPOSALS, {"schema": SCHEMA, "updated_at": now_iso(), "proposals": proposals}, suffix=".tablet-ai-proposals.tmp")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--train", action="store_true")
    parser.add_argument("--mark-action", choices=CAPABILITY_ORDER)
    args = parser.parse_args(argv)
    if args.mark_action:
        result = mark_action(args.mark_action)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result.get("ok") else 2
    if args.train:
        state, source, corruption = load_state(STATE)
        if corruption:
            print(json.dumps({"active": False, "reason": "state_corruption_hold", "source": source}, ensure_ascii=False))
            return 2
        model = train_verified_policy(state["labels"])
        if model.get("active") is True:
            previous = load_model(MODEL)
            if previous is not None:
                atomic_write_json(MODEL.with_name(MODEL.name + ".bak"), previous, suffix=".tablet-ai-model-backup.tmp")
            atomic_write_json(MODEL, model, suffix=".tablet-ai-model.tmp")
        print(json.dumps(model, ensure_ascii=False, sort_keys=True))
        return 0
    result = run_cycle(args.root, persist=not args.dry_run)
    print(json.dumps({
        "selected": [row["capability_id"] for row in result["decisions"] if row["selected"]],
        "auto_execution_allowed": [row["capability_id"] for row in result["decisions"] if row["auto_execution_allowed"]],
        "neural_model_active": result["neural_model_active"], "state_corruption_hold": result["state_corruption_hold"],
        "proposal_count": len(result["proposals"]),
    }, ensure_ascii=False, sort_keys=True))
    return 2 if result["state_corruption_hold"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
