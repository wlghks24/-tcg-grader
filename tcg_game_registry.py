#!/usr/bin/env python3
"""Declarative, fail-closed TCG category discovery for Tablet GPT.

This module never predicts profit or price direction and never writes source code.
It reviews verified local collection outputs and may only update tcg_game_registry.json.
New games remain watch candidates unless independent official + market evidence
and the configured marketplace-depth gate are both satisfied.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
REGISTRY_PATH = ROOT / "tcg_game_registry.json"
MAX_REGISTRY_BYTES = 1_000_000
MAX_GAMES = 64
CORE_IDS = ("pokemon", "onepiece", "naruto")
CAPABILITIES = ("market", "release", "promo", "purchase", "grading")
REGIONS = {"KR", "JP", "US", "GLOBAL"}
DISCOVERY_FILES = ("releases.json", "promo_events.json", "market_watch.json", "market_prices.json")
DEFAULT_REVIEW_WINDOW_DAYS = 45
DEFAULT_MIN_SCORE = 0.72
DEFAULT_MIN_CATALOG = 500
DEFAULT_MIN_SIGNAL_TYPES = 2


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _parse_time(value: Any) -> dt.datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        stamp = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=dt.timezone.utc)
    return stamp.astimezone(dt.timezone.utc)


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _safe_https(value: Any) -> bool:
    try:
        parts = urlparse(str(value or ""))
    except ValueError:
        return False
    return parts.scheme == "https" and bool(parts.hostname)


def _game_id(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(value or "").casefold()).strip("-")
    return text[:64]


def _read_json(path: Path, *, max_bytes: int = MAX_REGISTRY_BYTES) -> dict[str, Any] | None:
    try:
        if not path.is_file() or path.is_symlink():
            return None
        raw = safe_read_text(path, max_bytes=max_bytes)
        data = json.loads(raw)
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _valid_capabilities(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == set(CAPABILITIES)
        and all(isinstance(value[key], bool) for key in CAPABILITIES)
    )


def valid_game(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    required = {
        "id", "canonical", "label_ko", "state", "aliases", "purchase_value", "promo_value",
        "capabilities", "regions", "activation_score", "evidence", "official_source", "market_source",
    }
    if set(row) != required:
        return False
    if not isinstance(row["id"], str) or not row["id"] or len(row["id"]) > 64:
        return False
    if not isinstance(row["canonical"], str) or not row["canonical"] or len(row["canonical"]) > 120:
        return False
    if row["state"] not in {"core", "promoted", "watch"}:
        return False
    if not isinstance(row["aliases"], list) or not row["aliases"] or len(row["aliases"]) > 32:
        return False
    if any(not isinstance(alias, str) or not alias.strip() or len(alias) > 120 for alias in row["aliases"]):
        return False
    if not _valid_capabilities(row["capabilities"]):
        return False
    if not isinstance(row["regions"], list) or not row["regions"] or any(region not in REGIONS for region in row["regions"]):
        return False
    score = _finite(row["activation_score"])
    if score is None or not 0.0 <= score <= 1.0:
        return False
    if not isinstance(row["evidence"], dict):
        return False
    if not _safe_https(row["official_source"]) or not _safe_https(row["market_source"]):
        return False
    if row["state"] == "core" and row["id"] not in CORE_IDS:
        return False
    if row["state"] != "core" and row["capabilities"].get("grading") is True:
        return False
    return True


def validate_registry(data: Any) -> bool:
    if not isinstance(data, dict) or set(data) != {"schema_version", "updated_at", "policy", "games"}:
        return False
    if data["schema_version"] != 1 or not isinstance(data["policy"], dict):
        return False
    games = data["games"]
    if not isinstance(games, list) or not 3 <= len(games) <= MAX_GAMES:
        return False
    if not all(valid_game(row) for row in games):
        return False
    ids = [row["id"] for row in games]
    canonicals = [row["canonical"].casefold() for row in games]
    if len(ids) != len(set(ids)) or len(canonicals) != len(set(canonicals)):
        return False
    if not set(CORE_IDS).issubset(ids):
        return False
    policy = data["policy"]
    required_policy = {
        "profit_guarantee", "investment_return_prediction", "market_direction_prediction",
        "category_auto_promotion_requires_verified_evidence", "source_code_auto_generation",
        "user_behavior_tracking", "grading_requires_separate_calibration", "review_window_days",
        "min_auto_promotion_score", "min_marketplace_catalog_count", "min_independent_signal_types",
    }
    if not required_policy.issubset(policy):
        return False
    if any(policy.get(key) is not False for key in (
        "profit_guarantee", "investment_return_prediction", "market_direction_prediction",
        "source_code_auto_generation", "user_behavior_tracking",
    )):
        return False
    if policy.get("category_auto_promotion_requires_verified_evidence") is not True:
        return False
    if policy.get("grading_requires_separate_calibration") is not True:
        return False
    return True


def load_registry(root: Path = ROOT) -> dict[str, Any]:
    data = _read_json(root / REGISTRY_PATH.name)
    if data is None or not validate_registry(data):
        raise ValueError("TCG_GAME_REGISTRY_INVALID")
    return data


def enabled_games(capability: str, *, root: Path = ROOT, include_watch: bool = False) -> list[dict[str, Any]]:
    if capability not in CAPABILITIES:
        return []
    data = load_registry(root)
    allowed_states = {"core", "promoted"} | ({"watch"} if include_watch else set())
    return [
        deepcopy(row) for row in data["games"]
        if row["state"] in allowed_states and row["capabilities"].get(capability) is True
    ]


def enabled_canonicals(capability: str, *, root: Path = ROOT) -> tuple[str, ...]:
    return tuple(row["canonical"] for row in enabled_games(capability, root=root))


def canonical_game(value: Any, *, root: Path = ROOT) -> str | None:
    text = re.sub(r"\s+", " ", str(value or "").strip()).casefold()
    if not text:
        return None
    try:
        games = load_registry(root)["games"]
    except ValueError:
        return None
    for row in games:
        candidates = [row["canonical"], row["label_ko"], *row["aliases"]]
        for candidate in candidates:
            key = re.sub(r"\s+", " ", str(candidate).strip()).casefold()
            if text == key or (len(key) >= 5 and key in text):
                return row["canonical"]
    return None


def _fresh_verified(row: dict[str, Any], now: dt.datetime, days: int) -> bool:
    stamp = _parse_time(row.get("last_verified_at") or row.get("link_checked_at") or row.get("updated_at"))
    return stamp is not None and 0.0 <= (now - stamp).total_seconds() <= days * 86400


def _collect_local_signals(root: Path, registry: dict[str, Any], now: dt.datetime) -> dict[str, set[str]]:
    days = int(registry["policy"].get("review_window_days") or DEFAULT_REVIEW_WINDOW_DAYS)
    signals: dict[str, set[str]] = {}
    for filename in DISCOVERY_FILES:
        data = _read_json(root / filename, max_bytes=20_000_000) or {}
        if filename == "market_prices.json":
            rows = [row for row in (data.get("entries") or {}).values() if isinstance(row, dict)]
            kind = "market_price"
        else:
            rows = [
                row for key in ("items", "archive_items")
                for row in (data.get(key) if isinstance(data.get(key), list) else [])
                if isinstance(row, dict)
            ]
            kind = {
                "releases.json": "official_release",
                "promo_events.json": "official_promo",
                "market_watch.json": "market_watch",
            }[filename]
        for row in rows[:10000]:
            raw_game = row.get("game")
            if not raw_game:
                continue
            canonical = canonical_game(raw_game, root=root) or str(raw_game).strip()[:120]
            if not canonical:
                continue
            source = row.get("source") or row.get("url")
            if kind.startswith("official_"):
                if not _safe_https(source) or not _fresh_verified(row, now, days):
                    continue
            elif kind in {"market_watch", "market_price"}:
                if kind == "market_watch" and not str(row.get("sale_status") or "").strip():
                    continue
                if source and not _safe_https(source):
                    continue
            signals.setdefault(canonical, set()).add(kind)
    return signals


def _registry_signal_set(row: dict[str, Any], now: dt.datetime, days: int) -> set[str]:
    evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
    signals: set[str] = set()
    verified = _parse_time(evidence.get("last_verified_at"))
    fresh = verified is not None and 0.0 <= (now - verified).total_seconds() <= days * 86400
    if fresh and evidence.get("official_live") is True:
        signals.add("official_registry")
    catalog = evidence.get("marketplace_catalog_count")
    if isinstance(catalog, int) and not isinstance(catalog, bool) and catalog > 0:
        signals.add("marketplace_depth")
    if evidence.get("organized_play") is True:
        signals.add("organized_play")
    if evidence.get("collector_rarity_signal") is True or evidence.get("serialized_card_signal") is True:
        signals.add("collector_rarity")
    return signals


def review_registry(
    root: Path = ROOT, *, now: dt.datetime | None = None, persist: bool = False
) -> dict[str, Any]:
    moment = (now or _now()).astimezone(dt.timezone.utc)
    registry = load_registry(root)
    policy = registry["policy"]
    min_score = float(policy.get("min_auto_promotion_score") or DEFAULT_MIN_SCORE)
    min_catalog = int(policy.get("min_marketplace_catalog_count") or DEFAULT_MIN_CATALOG)
    min_signals = int(policy.get("min_independent_signal_types") or DEFAULT_MIN_SIGNAL_TYPES)
    days = int(policy.get("review_window_days") or DEFAULT_REVIEW_WINDOW_DAYS)
    local = _collect_local_signals(root, registry, moment)
    rows = deepcopy(registry["games"])
    by_canonical = {row["canonical"]: row for row in rows}
    reviewed: list[dict[str, Any]] = []

    for canonical, row in by_canonical.items():
        signals = set(local.get(canonical, set())) | _registry_signal_set(row, moment, days)
        evidence = row["evidence"]
        catalog = evidence.get("marketplace_catalog_count")
        catalog_ok = row["state"] == "core" or (
            isinstance(catalog, int) and not isinstance(catalog, bool) and catalog >= min_catalog
        )
        official_ok = row["state"] == "core" or any(
            name in signals for name in ("official_registry", "official_release", "official_promo")
        )
        market_ok = row["state"] == "core" or any(
            name in signals for name in ("marketplace_depth", "market_price", "market_watch")
        )
        activation = float(_finite(row.get("activation_score")) or 0.0)
        eligible = (
            row["state"] == "core"
            or activation >= min_score
            and len(signals) >= min_signals
            and catalog_ok and official_ok and market_ok
        )
        next_state = "core" if row["state"] == "core" else ("promoted" if eligible else "watch")
        row["state"] = next_state
        if next_state != "core":
            row["capabilities"]["grading"] = False
        reviewed.append({
            "canonical": canonical,
            "state": next_state,
            "activation_score": round(activation, 6),
            "signals": sorted(signals),
            "signal_count": len(signals),
            "catalog_ok": catalog_ok,
            "official_ok": official_ok,
            "market_ok": market_ok,
            "eligible": eligible,
        })

    known_casefold = {key.casefold() for key in by_canonical}
    unknown_candidates = []
    for canonical, signals in sorted(local.items()):
        if canonical.casefold() in known_casefold:
            continue
        unknown_candidates.append({
            "canonical": canonical,
            "state": "watch",
            "signals": sorted(signals),
            "signal_count": len(signals),
            "auto_promoted": False,
            "reason": "marketplace_depth_and_explicit_official_identity_required",
        })

    promoted = [row["canonical"] for row in rows if row["state"] in {"core", "promoted"}]
    changed = rows != registry["games"]
    if persist and changed:
        output = deepcopy(registry)
        output["games"] = rows
        output["updated_at"] = moment.isoformat(timespec="seconds")
        if not validate_registry(output):
            raise ValueError("TCG_GAME_REGISTRY_REVIEW_INVALID")
        atomic_write_json(root / REGISTRY_PATH.name, output, suffix=".tcg-game-registry.tmp")

    return {
        "status": "REVIEWED",
        "promoted_games": promoted,
        "reviewed": reviewed,
        "unknown_candidates": unknown_candidates[:32],
        "changed": changed,
        "persisted": bool(persist and changed),
        "review_window_days": days,
        "min_auto_promotion_score": min_score,
        "min_marketplace_catalog_count": min_catalog,
        "min_independent_signal_types": min_signals,
        "profit_guaranteed": False,
        "market_direction_inferred": False,
        "source_code_modified": False,
        "git_write": False,
        "grading_auto_enabled_for_new_games": False,
    }


def public_snapshot(root: Path = ROOT, *, now: dt.datetime | None = None) -> dict[str, Any]:
    registry = load_registry(root)
    review = review_registry(root, now=now, persist=False)
    enabled = [row for row in registry["games"] if row["state"] in {"core", "promoted"}]
    return {
        "schema_version": registry["schema_version"],
        "updated_at": registry["updated_at"],
        "enabled_games": [{
            "id": row["id"],
            "canonical": row["canonical"],
            "label_ko": row["label_ko"],
            "state": row["state"],
            "regions": list(row["regions"]),
            "capabilities": dict(row["capabilities"]),
            "activation_score": row["activation_score"],
        } for row in enabled],
        "review": review,
        "policy": deepcopy(registry["policy"]),
    }
