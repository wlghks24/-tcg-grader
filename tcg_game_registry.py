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
REVIEW_SNAPSHOT_PATH = ROOT / "tcg_registry_review.json"
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
DEFAULT_AUTO_WATCH_RETIRE_DAYS = 180


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
        "auto_watch_retire_after_days",
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
    retire_days = policy.get("auto_watch_retire_after_days")
    review_days = policy.get("review_window_days")
    if (
        not isinstance(retire_days, int) or isinstance(retire_days, bool)
        or not 90 <= retire_days <= 3650
        or not isinstance(review_days, int) or isinstance(review_days, bool)
        or retire_days < review_days
    ):
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


def _source_host(value: Any) -> str:
    if not _safe_https(value):
        return ""
    try:
        host = (urlparse(str(value)).hostname or "").casefold()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def _safe_candidate_name(value: Any) -> str | None:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not 2 <= len(text) <= 120:
        return None
    if not any(char.isalpha() for char in text):
        return None
    if any(ord(char) < 32 for char in text):
        return None
    if text.casefold() in {"unknown", "none", "n/a", "test", "sample"}:
        return None
    return text


def _collect_local_observations(
    root: Path, registry: dict[str, Any], now: dt.datetime
) -> dict[str, dict[str, Any]]:
    days = int(registry["policy"].get("review_window_days") or DEFAULT_REVIEW_WINDOW_DAYS)
    observations: dict[str, dict[str, Any]] = {}
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
            canonical = canonical_game(raw_game, root=root) or _safe_candidate_name(raw_game)
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

            item = observations.setdefault(canonical, {
                "signals": set(),
                "official_sources": set(),
                "market_sources": set(),
                "regions": set(),
            })
            item["signals"].add(kind)
            region = str(row.get("region") or "").strip().upper()
            if region in REGIONS:
                item["regions"].add(region)

            # Automatic WATCH seeding is stricter than signal collection:
            # both source classes must be fresh public HTTPS and independent.
            if _safe_https(source) and _fresh_verified(row, now, days):
                if kind.startswith("official_"):
                    item["official_sources"].add(str(source))
                elif kind in {"market_watch", "market_price"}:
                    item["market_sources"].add(str(source))
    return observations


def _collect_local_signals(root: Path, registry: dict[str, Any], now: dt.datetime) -> dict[str, set[str]]:
    observations = _collect_local_observations(root, registry, now)
    return {canonical: set(value["signals"]) for canonical, value in observations.items()}


def _provisional_watch_row(
    canonical: str, observation: dict[str, Any], moment: dt.datetime
) -> tuple[dict[str, Any] | None, str]:
    safe_name = _safe_candidate_name(canonical)
    if safe_name is None:
        return None, "invalid_candidate_identity"
    candidate_id = _game_id(safe_name)
    if not candidate_id:
        return None, "stable_ascii_id_required"

    official_sources = sorted({
        str(url) for url in observation.get("official_sources", set()) if _safe_https(url)
    })
    market_sources = sorted({
        str(url) for url in observation.get("market_sources", set()) if _safe_https(url)
    })
    if not official_sources:
        return None, "fresh_official_source_required"
    if not market_sources:
        return None, "fresh_independent_market_source_required"

    pair: tuple[str, str] | None = None
    for official in official_sources:
        official_host = _source_host(official)
        for market in market_sources:
            market_host = _source_host(market)
            if official_host and market_host and official_host != market_host:
                pair = (official, market)
                break
        if pair is not None:
            break
    if pair is None:
        return None, "independent_source_hosts_required"

    regions = sorted({
        str(region).upper() for region in observation.get("regions", set())
        if str(region).upper() in REGIONS
    })
    if not regions:
        regions = ["GLOBAL"]

    signals = sorted(set(observation.get("signals", set())))
    row = {
        "id": candidate_id,
        "canonical": safe_name,
        "label_ko": safe_name,
        "state": "watch",
        "aliases": [safe_name],
        "purchase_value": safe_name,
        "promo_value": safe_name,
        "capabilities": {
            "market": True,
            "release": True,
            "promo": True,
            "purchase": True,
            "grading": False,
        },
        "regions": regions,
        "activation_score": 0.0,
        "evidence": {
            "official_live": True,
            "marketplace_catalog_count": None,
            "organized_play": False,
            "collector_rarity_signal": False,
            "last_verified_at": moment.isoformat(timespec="seconds"),
            "auto_watch_seeded": True,
            "auto_watch_seeded_at": moment.isoformat(timespec="seconds"),
            "discovery_signals": signals,
        },
        "official_source": pair[0],
        "market_source": pair[1],
    }
    return row, "verified_official_and_independent_market_sources"

def _registry_signal_set(row: dict[str, Any], now: dt.datetime, days: int) -> set[str]:
    evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
    signals: set[str] = set()
    verified = _parse_time(evidence.get("last_verified_at"))
    fresh = verified is not None and 0.0 <= (now - verified).total_seconds() <= days * 86400
    if fresh and evidence.get("official_live") is True:
        signals.add("official_registry")
    catalog = evidence.get("marketplace_catalog_count")
    market_verified = _parse_time(evidence.get("marketplace_catalog_checked_at"))
    market_fresh = (
        market_verified is not None
        and 0.0 <= (now - market_verified).total_seconds() <= days * 86400
    )
    if (
        isinstance(catalog, int) and not isinstance(catalog, bool) and catalog > 0
        and market_fresh
    ):
        signals.add("marketplace_depth")
    if evidence.get("organized_play") is True:
        signals.add("organized_play")
    if evidence.get("collector_rarity_signal") is True or evidence.get("serialized_card_signal") is True:
        signals.add("collector_rarity")
    return signals


def _auto_watch_retirable(
    row: dict[str, Any],
    observation: dict[str, Any],
    now: dt.datetime,
    *,
    review_days: int,
    retire_days: int,
) -> bool:
    """Retire only stale WATCH rows that the runtime itself auto-created."""
    if row.get("state") != "watch":
        return False
    evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
    if evidence.get("auto_watch_seeded") is not True:
        return False

    stamps = [
        _parse_time(evidence.get("last_verified_at")),
        _parse_time(evidence.get("marketplace_catalog_checked_at")),
        _parse_time(evidence.get("auto_watch_seeded_at")),
    ]
    usable = [stamp for stamp in stamps if stamp is not None and stamp <= now]
    latest = max(usable) if usable else None
    if latest is None or (now - latest).total_seconds() <= retire_days * 86400:
        return False

    if observation.get("official_sources") or observation.get("market_sources"):
        return False
    fresh_registry_signals = _registry_signal_set(row, now, review_days)
    return not any(
        signal in fresh_registry_signals
        for signal in ("official_registry", "marketplace_depth")
    )


def _evidence_activation_score(
    row: dict[str, Any], signals: set[str], *, min_catalog: int
) -> float:
    """Score verified market viability without predicting price direction or profit.

    This is a bounded evidence score used only for category activation. It rewards
    fresh official evidence, independent market evidence, organized play,
    collectibility signals, catalog depth, signal diversity and geographic
    coverage. It never consumes price trend, expected return or user behavior.
    """
    evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
    official = any(name in signals for name in ("official_registry", "official_release", "official_promo"))
    market = any(name in signals for name in ("marketplace_depth", "market_price", "market_watch"))
    organized = "organized_play" in signals
    collectible = "collector_rarity" in signals
    raw_catalog = evidence.get("marketplace_catalog_count")
    catalog = (
        int(raw_catalog)
        if isinstance(raw_catalog, int) and not isinstance(raw_catalog, bool) and raw_catalog > 0
        else 0
    )
    catalog_scale = 0.0
    if catalog >= max(1, min_catalog) and "marketplace_depth" in signals:
        catalog_scale = min(1.0, math.log10(catalog + 1.0) / math.log10(100_000 + 1.0))
    signal_diversity = min(1.0, len(signals) / 4.0)
    region_coverage = min(1.0, len({
        str(region).upper() for region in row.get("regions", [])
        if str(region).upper() in {"KR", "JP", "US"}
    }) / 3.0)
    score = (
        0.22 * float(official)
        + 0.22 * float(market)
        + 0.14 * float(organized)
        + 0.08 * float(collectible)
        + 0.18 * catalog_scale
        + 0.10 * signal_diversity
        + 0.06 * region_coverage
    )
    return round(max(0.0, min(1.0, score)), 6)


def _promotion_hold_reasons(
    *, is_core: bool, activation: float, min_score: float, signal_count: int,
    min_signals: int, catalog_ok: bool, official_ok: bool, market_ok: bool,
) -> list[str]:
    if is_core:
        return []
    reasons: list[str] = []
    if activation < min_score:
        reasons.append("activation_score_below_threshold")
    if signal_count < min_signals:
        reasons.append("independent_signal_types_below_threshold")
    if not catalog_ok:
        reasons.append("marketplace_catalog_depth_below_threshold")
    if not official_ok:
        reasons.append("fresh_official_evidence_required")
    if not market_ok:
        reasons.append("fresh_independent_market_evidence_required")
    return reasons


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
    retire_days = int(policy.get("auto_watch_retire_after_days") or DEFAULT_AUTO_WATCH_RETIRE_DAYS)
    observations = _collect_local_observations(root, registry, moment)
    local = {canonical: set(value["signals"]) for canonical, value in observations.items()}
    rows = deepcopy(registry["games"])
    by_canonical = {row["canonical"]: row for row in rows}
    reviewed: list[dict[str, Any]] = []

    for canonical, row in by_canonical.items():
        signals = set(local.get(canonical, set())) | _registry_signal_set(row, moment, days)
        evidence = row["evidence"]
        catalog = evidence.get("marketplace_catalog_count")
        catalog_ok = row["state"] == "core" or (
            isinstance(catalog, int) and not isinstance(catalog, bool)
            and catalog >= min_catalog and "marketplace_depth" in signals
        )
        official_ok = row["state"] == "core" or any(
            name in signals for name in ("official_registry", "official_release", "official_promo")
        )
        market_ok = row["state"] == "core" or any(
            name in signals for name in ("marketplace_depth", "market_price", "market_watch")
        )
        seed_activation = float(_finite(row.get("activation_score")) or 0.0)
        evidence_activation = _evidence_activation_score(row, signals, min_catalog=min_catalog)
        activation = max(seed_activation, evidence_activation)
        is_core = row["state"] == "core"
        hold_reasons = _promotion_hold_reasons(
            is_core=is_core,
            activation=activation,
            min_score=min_score,
            signal_count=len(signals),
            min_signals=min_signals,
            catalog_ok=catalog_ok,
            official_ok=official_ok,
            market_ok=market_ok,
        )
        eligible = is_core or not hold_reasons
        next_state = "core" if is_core else ("promoted" if eligible else "watch")
        row["state"] = next_state
        if next_state != "core":
            row["capabilities"]["grading"] = False
        reviewed.append({
            "canonical": canonical,
            "state": next_state,
            "activation_score": round(activation, 6),
            "seed_activation_score": round(seed_activation, 6),
            "evidence_activation_score": round(evidence_activation, 6),
            "activation_score_source": (
                "evidence" if evidence_activation > seed_activation else "seed"
            ),
            "signals": sorted(signals),
            "signal_count": len(signals),
            "catalog_ok": catalog_ok,
            "official_ok": official_ok,
            "market_ok": market_ok,
            "eligible": eligible,
            "hold_reasons": hold_reasons,
        })

    retired_auto_watch_games: list[str] = []
    active_rows: list[dict[str, Any]] = []
    for row in rows:
        observation = observations.get(row["canonical"], {})
        if _auto_watch_retirable(
            row, observation, moment, review_days=days, retire_days=retire_days
        ):
            retired_auto_watch_games.append(row["canonical"])
            continue
        active_rows.append(row)
    rows = active_rows

    known_casefold = {row["canonical"].casefold() for row in rows}
    used_ids = {row["id"] for row in rows}
    unknown_candidates = []
    auto_watch_created_games: list[str] = []
    for canonical, signals in sorted(local.items()):
        if canonical.casefold() in known_casefold:
            continue
        observation = observations.get(canonical, {})
        provisional, reason = _provisional_watch_row(canonical, observation, moment)
        auto_watch_eligible = provisional is not None
        auto_watch_created = False
        if provisional is not None:
            if provisional["id"] in used_ids:
                provisional = None
                reason = "registry_id_collision"
                auto_watch_eligible = False
            elif len(rows) >= MAX_GAMES:
                provisional = None
                reason = "registry_capacity_hold"
                auto_watch_eligible = False
            elif persist:
                rows.append(provisional)
                used_ids.add(provisional["id"])
                known_casefold.add(provisional["canonical"].casefold())
                auto_watch_created = True
                auto_watch_created_games.append(provisional["canonical"])
        unknown_candidates.append({
            "canonical": canonical,
            "state": "watch",
            "signals": sorted(signals),
            "signal_count": len(signals),
            "auto_promoted": False,
            "auto_watch_eligible": auto_watch_eligible,
            "auto_watch_created": auto_watch_created,
            "reason": reason,
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
        "auto_watch_created_games": auto_watch_created_games,
        "retired_auto_watch_games": retired_auto_watch_games,
        "changed": changed,
        "persisted": bool(persist and changed),
        "review_window_days": days,
        "auto_watch_retire_after_days": retire_days,
        "min_auto_promotion_score": min_score,
        "min_marketplace_catalog_count": min_catalog,
        "min_independent_signal_types": min_signals,
        "profit_guaranteed": False,
        "market_direction_inferred": False,
        "source_code_modified": False,
        "git_write": False,
        "grading_auto_enabled_for_new_games": False,
        "activation_score_uses_verified_evidence": True,
        "activation_score_uses_price_direction": False,
        "activation_score_uses_profit_prediction": False,
        "activation_score_uses_user_behavior": False,
    }


def build_review_snapshot(
    review: dict[str, Any], *, now: dt.datetime | None = None
) -> dict[str, Any]:
    """Build a bounded, non-predictive explanation snapshot for the tablet UI."""
    if not isinstance(review, dict) or review.get("status") != "REVIEWED":
        raise ValueError("TCG_REGISTRY_REVIEW_SNAPSHOT_INVALID")
    moment = (now or _now()).astimezone(dt.timezone.utc)
    rows = review.get("reviewed")
    if not isinstance(rows, list) or len(rows) > MAX_GAMES:
        raise ValueError("TCG_REGISTRY_REVIEW_ROWS_INVALID")
    reviewed: list[dict[str, Any]] = []
    allowed_reasons = {
        "activation_score_below_threshold",
        "independent_signal_types_below_threshold",
        "marketplace_catalog_depth_below_threshold",
        "fresh_official_evidence_required",
        "fresh_independent_market_evidence_required",
    }
    for row in rows:
        if not isinstance(row, dict):
            continue
        canonical = str(row.get("canonical") or "").strip()
        state = str(row.get("state") or "").strip()
        activation = _finite(row.get("activation_score"))
        seed = _finite(row.get("seed_activation_score"))
        evidence = _finite(row.get("evidence_activation_score"))
        reasons = [
            reason for reason in row.get("hold_reasons", [])
            if isinstance(reason, str) and reason in allowed_reasons
        ][:5]
        if (
            not canonical or len(canonical) > 120
            or state not in {"core", "promoted", "watch"}
            or activation is None or not 0.0 <= activation <= 1.0
            or seed is None or not 0.0 <= seed <= 1.0
            or evidence is None or not 0.0 <= evidence <= 1.0
        ):
            raise ValueError("TCG_REGISTRY_REVIEW_ROW_INVALID")
        reviewed.append({
            "canonical": canonical,
            "state": state,
            "activation_score": round(activation, 6),
            "seed_activation_score": round(seed, 6),
            "evidence_activation_score": round(evidence, 6),
            "activation_score_source": (
                "evidence" if row.get("activation_score_source") == "evidence" else "seed"
            ),
            "signal_count": max(0, min(int(row.get("signal_count") or 0), 32)),
            "catalog_ok": bool(row.get("catalog_ok")),
            "official_ok": bool(row.get("official_ok")),
            "market_ok": bool(row.get("market_ok")),
            "eligible": bool(row.get("eligible")),
            "hold_reasons": reasons,
        })
    return {
        "schema_version": 1,
        "generated_at": moment.isoformat(timespec="seconds"),
        "status": "REVIEWED",
        "reviewed": reviewed,
        "policy": {
            "min_auto_promotion_score": float(review["min_auto_promotion_score"]),
            "min_marketplace_catalog_count": int(review["min_marketplace_catalog_count"]),
            "min_independent_signal_types": int(review["min_independent_signal_types"]),
            "review_window_days": int(review["review_window_days"]),
        },
        "profit_guaranteed": False,
        "market_direction_inferred": False,
        "grading_auto_enabled_for_new_games": False,
    }


def write_review_snapshot(
    review: dict[str, Any], *, root: Path = ROOT, now: dt.datetime | None = None
) -> dict[str, Any]:
    snapshot = build_review_snapshot(review, now=now)
    atomic_write_json(
        root / REVIEW_SNAPSHOT_PATH.name,
        snapshot,
        suffix=".tcg-registry-review.tmp",
    )
    return snapshot


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
