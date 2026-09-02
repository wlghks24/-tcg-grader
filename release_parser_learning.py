#!/usr/bin/env python3
"""Bounded learning for verified release-parser strategies.

This module never stores or executes source code, regexes, URLs, JavaScript, shell
commands, or arbitrary strategy names learned from disk.  It only remembers which
already-coded, caller-allowlisted strategy produced verified rows most reliably.
That lets collectors recover from source/DOM transport drift without unsafe source
rewriting or promotion of unverified data.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from typing import Iterable

from safe_runtime import atomic_write_json, exclusive_file_lock, safe_read_text

MEMORY_VERSION = 1
MAX_SOURCES = 32
MAX_STRATEGIES_PER_SOURCE = 12
MAX_LABEL_LEN = 80
MAX_STRATEGY_LEN = 64


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _clean_token(value: object, *, limit: int) -> str:
    text = str(value or "").strip()[:limit]
    if not re.fullmatch(r"[A-Za-z0-9_.: -]+", text):
        return ""
    return text


def _empty_memory() -> dict:
    return {"version": MEMORY_VERSION, "updated_at": None, "sources": {}}


def load_memory(path: Path) -> dict:
    """Load only the small declarative counters understood by this version."""
    try:
        raw = json.loads(safe_read_text(path, max_bytes=512_000))
    except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError):
        return _empty_memory()
    if not isinstance(raw, dict) or raw.get("version") != MEMORY_VERSION:
        return _empty_memory()
    sources = raw.get("sources")
    if not isinstance(sources, dict):
        return _empty_memory()
    clean = _empty_memory()
    clean["updated_at"] = raw.get("updated_at") if isinstance(raw.get("updated_at"), str) else None
    for label, source in list(sources.items())[:MAX_SOURCES]:
        clean_label = _clean_token(label, limit=MAX_LABEL_LEN)
        if not clean_label or not isinstance(source, dict):
            continue
        entry = {
            "last_successful_strategy": _clean_token(source.get("last_successful_strategy"), limit=MAX_STRATEGY_LEN),
            "last_outcome": _clean_token(source.get("last_outcome"), limit=32),
            "last_row_count": max(0, min(100_000, int(source.get("last_row_count", 0) or 0))),
            "consecutive_failures": max(0, min(10_000, int(source.get("consecutive_failures", 0) or 0))),
            "last_success_at": source.get("last_success_at") if isinstance(source.get("last_success_at"), str) else None,
            "last_attempt_at": source.get("last_attempt_at") if isinstance(source.get("last_attempt_at"), str) else None,
            "last_fingerprint": _clean_token(source.get("last_fingerprint"), limit=24),
            "strategies": {},
        }
        strategies = source.get("strategies")
        if isinstance(strategies, dict):
            for strategy, stats in list(strategies.items())[:MAX_STRATEGIES_PER_SOURCE]:
                clean_strategy = _clean_token(strategy, limit=MAX_STRATEGY_LEN)
                if not clean_strategy or not isinstance(stats, dict):
                    continue
                entry["strategies"][clean_strategy] = {
                    "successes": max(0, min(1_000_000, int(stats.get("successes", 0) or 0))),
                    "failures": max(0, min(1_000_000, int(stats.get("failures", 0) or 0))),
                    "last_row_count": max(0, min(100_000, int(stats.get("last_row_count", 0) or 0))),
                    "last_success_at": stats.get("last_success_at") if isinstance(stats.get("last_success_at"), str) else None,
                    "last_attempt_at": stats.get("last_attempt_at") if isinstance(stats.get("last_attempt_at"), str) else None,
                    "last_outcome": _clean_token(stats.get("last_outcome"), limit=32),
                }
        clean["sources"][clean_label] = entry
    return clean


def fingerprint_text(text: str) -> str:
    """Return a non-executable, bounded structural fingerprint for diagnostics."""
    normalized = re.sub(r"\s+", " ", str(text or ""))[:200_000]
    return hashlib.sha256(normalized.encode("utf-8", "replace")).hexdigest()[:16]


def strategy_order(
    path: Path,
    source_label: str,
    allowed_strategies: Iterable[str],
    default_order: Iterable[str],
) -> list[str]:
    """Prefer the last proven allowlisted strategy; ignore every unknown disk value."""
    allowed = []
    for value in allowed_strategies:
        token = _clean_token(value, limit=MAX_STRATEGY_LEN)
        if token and token not in allowed:
            allowed.append(token)
    defaults = []
    for value in default_order:
        token = _clean_token(value, limit=MAX_STRATEGY_LEN)
        if token in allowed and token not in defaults:
            defaults.append(token)
    for token in allowed:
        if token not in defaults:
            defaults.append(token)
    if not defaults:
        return []
    label = _clean_token(source_label, limit=MAX_LABEL_LEN)
    memory = load_memory(path)
    source = memory.get("sources", {}).get(label, {}) if label else {}
    preferred = _clean_token(source.get("last_successful_strategy"), limit=MAX_STRATEGY_LEN) if isinstance(source, dict) else ""
    if preferred in allowed:
        return [preferred] + [item for item in defaults if item != preferred]
    return defaults


def record_attempt(
    path: Path,
    source_label: str,
    strategy: str,
    *,
    allowed_strategies: Iterable[str],
    success: bool,
    row_count: int,
    outcome: str,
    fingerprint: str = "",
) -> bool:
    """Persist counters only for a caller-allowlisted strategy.

    Failure to write learning state never breaks collection; verified data remains the
    priority on read-only or constrained devices.
    """
    label = _clean_token(source_label, limit=MAX_LABEL_LEN)
    strategy_id = _clean_token(strategy, limit=MAX_STRATEGY_LEN)
    allowed = {_clean_token(x, limit=MAX_STRATEGY_LEN) for x in allowed_strategies}
    allowed.discard("")
    if not label or strategy_id not in allowed:
        return False
    outcome_id = _clean_token(outcome, limit=32) or ("success" if success else "failure")
    count = max(0, min(100_000, int(row_count or 0)))
    fp = _clean_token(fingerprint, limit=24)
    try:
        with exclusive_file_lock(path, timeout_seconds=3.0):
            memory = load_memory(path)
            sources = memory.setdefault("sources", {})
            source = sources.setdefault(label, {
                "last_successful_strategy": "",
                "last_outcome": "",
                "last_row_count": 0,
                "consecutive_failures": 0,
                "last_success_at": None,
                "last_attempt_at": None,
                "last_fingerprint": "",
                "strategies": {},
            })
            strategies = source.setdefault("strategies", {})
            stats = strategies.setdefault(strategy_id, {
                "successes": 0, "failures": 0, "last_row_count": 0,
                "last_success_at": None, "last_attempt_at": None, "last_outcome": "",
            })
            now = _utc_now()
            stats["last_attempt_at"] = now
            stats["last_outcome"] = outcome_id
            stats["last_row_count"] = count
            source["last_attempt_at"] = now
            source["last_outcome"] = outcome_id
            source["last_row_count"] = count
            if fp:
                source["last_fingerprint"] = fp
            if success and count > 0:
                stats["successes"] = min(1_000_000, int(stats.get("successes", 0) or 0) + 1)
                stats["last_success_at"] = now
                source["last_successful_strategy"] = strategy_id
                source["last_success_at"] = now
                source["consecutive_failures"] = 0
            else:
                stats["failures"] = min(1_000_000, int(stats.get("failures", 0) or 0) + 1)
                source["consecutive_failures"] = min(10_000, int(source.get("consecutive_failures", 0) or 0) + 1)
            memory["updated_at"] = now
            atomic_write_json(path, memory, suffix=".json.tmp")
        return True
    except (OSError, ValueError, TypeError, OverflowError):
        return False


def public_summary(path: Path, allowed_by_source: dict[str, Iterable[str]]) -> dict:
    """Expose only safe counters/strategy IDs already hard-coded by the caller."""
    memory = load_memory(path)
    out = {"version": MEMORY_VERSION, "updated_at": memory.get("updated_at"), "sources": {}}
    for label, allowed_values in allowed_by_source.items():
        clean_label = _clean_token(label, limit=MAX_LABEL_LEN)
        allowed = {_clean_token(x, limit=MAX_STRATEGY_LEN) for x in allowed_values}
        allowed.discard("")
        source = memory.get("sources", {}).get(clean_label)
        if not isinstance(source, dict):
            continue
        preferred = source.get("last_successful_strategy")
        if preferred not in allowed:
            preferred = ""
        strategies = {}
        for strategy, stats in source.get("strategies", {}).items():
            if strategy not in allowed or not isinstance(stats, dict):
                continue
            strategies[strategy] = {
                "successes": int(stats.get("successes", 0) or 0),
                "failures": int(stats.get("failures", 0) or 0),
                "last_row_count": int(stats.get("last_row_count", 0) or 0),
                "last_success_at": stats.get("last_success_at"),
                "last_outcome": stats.get("last_outcome"),
            }
        out["sources"][clean_label] = {
            "preferred_strategy": preferred,
            "last_outcome": source.get("last_outcome"),
            "last_row_count": int(source.get("last_row_count", 0) or 0),
            "consecutive_failures": int(source.get("consecutive_failures", 0) or 0),
            "last_success_at": source.get("last_success_at"),
            "last_fingerprint": source.get("last_fingerprint"),
            "strategies": strategies,
        }
    return out
