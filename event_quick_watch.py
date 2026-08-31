#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lightweight breaking-event scan between the heavier six-hour update cycles.

The normal updater intentionally remains conservative because price, image and
full-catalog collection is expensive and can trigger 403/429 responses. This
module only refreshes social/event discovery so newly announced movies,
collaborations, promos, reward/giveaway notices and events can reach
social_event_candidates.json much sooner. It also preserves narrowly scoped
manual official evidence when a fresh announcement is reported before search
engines/API feeds have indexed it. v142 prevents unverified candidates from
poisoning persistent host/term learning.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import collection_learning_hardening_v142 as hardening
import social_event_discovery
from safe_runtime import atomic_write_json, env_int, safe_read_text

ROOT = Path(__file__).resolve().parent
MANUAL_EVIDENCE = ROOT / "manual_event_evidence.json"
DEFAULT_INTERVAL_SECONDS = 60 * 60
DEFAULT_START_DELAY_SECONDS = 10 * 60
INTERVAL_SECONDS = env_int(
    "TCG_EVENT_QUICK_INTERVAL_SECONDS",
    DEFAULT_INTERVAL_SECONDS,
    30 * 60,
    6 * 60 * 60,
)
START_DELAY_SECONDS = env_int(
    "TCG_EVENT_QUICK_START_DELAY_SECONDS",
    DEFAULT_START_DELAY_SECONDS,
    60,
    60 * 60,
)
_RUN_LOCK = threading.Lock()

# Keep standalone executions identical to the main updater runtime.
hardening.apply()


def _text(row: dict) -> str:
    return " ".join(str(row.get(key) or "") for key in ("title", "excerpt", "author", "source")).lower()


def _same_manual_fact(existing: dict, seed: dict) -> bool:
    if any(existing.get(key) != seed.get(key) for key in ("game", "region", "category")):
        return False
    if str(existing.get("title") or "").strip() == str(seed.get("title") or "").strip():
        return True
    terms = [str(x).strip().lower() for x in seed.get("dedupe_terms", []) if str(x).strip()]
    if not terms:
        return False
    current = _text(existing)
    return any(term in current for term in terms)


def _category_names() -> set[str]:
    patterns = getattr(social_event_discovery, "CATEGORY_PATTERNS", ())
    if isinstance(patterns, dict):
        return {str(name) for name in patterns}
    names: set[str] = set()
    for row in patterns:
        if isinstance(row, (tuple, list)) and row:
            names.add(str(row[0]))
    return names


def _load_manual_seeds() -> list[dict]:
    if not MANUAL_EVIDENCE.exists() or MANUAL_EVIDENCE.is_symlink():
        return []
    try:
        payload = json.loads(safe_read_text(MANUAL_EVIDENCE, max_bytes=300_000))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return []
    rows = payload.get("items", []) if isinstance(payload, dict) else []
    valid_categories = _category_names()
    valid = []
    for row in rows:
        if not isinstance(row, dict) or row.get("manual_evidence") is not True:
            continue
        if row.get("game") not in social_event_discovery.GAMES or row.get("region") not in social_event_discovery.REGION_LANG:
            continue
        if row.get("category") not in valid_categories:
            continue
        source = str(row.get("source") or "")
        if not source.startswith("https://"):
            continue
        valid.append(dict(row))
    return valid


def _merge_manual_evidence(result: dict) -> tuple[dict, int]:
    """Keep user-confirmed official evidence until normal discovery catches up."""
    seeds = _load_manual_seeds()
    if not seeds or not isinstance(result, dict):
        return result, 0
    payload = dict(result)
    items = [dict(row) for row in payload.get("items", []) if isinstance(row, dict)]
    added = 0
    for seed in seeds:
        if any(_same_manual_fact(row, seed) for row in items):
            continue
        items.insert(0, seed)
        added += 1
    max_items = int(getattr(social_event_discovery, "MAX_ITEMS", 240) or 240)
    items = items[:max_items]
    payload["items"] = items
    payload["item_count"] = len(items)
    payload["manual_evidence_count"] = sum(1 for row in items if row.get("manual_evidence") is True)
    payload["official_social_candidate_count"] = sum(1 for row in items if row.get("official_account_verified") is True)
    payload["reward_watch_count"] = sum(1 for row in items if row.get("reward_watch") is True)
    payload["cross_checked_count"] = sum(1 for row in items if row.get("cross_checked") is True)
    try:
        payload["topic_coverage"] = {
            f"{game}/{region}/{topic}": sum(
                1 for row in items
                if row.get("game") == game
                and row.get("region") == region
                and social_event_discovery._coverage_topic(row) == topic
            )
            for game in social_event_discovery.GAMES
            for region in social_event_discovery.REGION_LANG
            for topic in social_event_discovery.multi_route_event_discovery.COVERAGE_TOPICS
        }
    except (AttributeError, TypeError, ValueError):
        pass
    atomic_write_json(social_event_discovery.OUT, payload, suffix=".quickwatch.tmp")
    return payload, added


def run_once(shared_lock=None) -> dict:
    """Refresh only event/social candidates and return a small health summary."""
    if not _RUN_LOCK.acquire(blocking=False):
        return {"ok": True, "skipped": True, "reason": "event quick scan already running"}
    started = time.monotonic()
    try:
        hardening.apply()
        if shared_lock is None:
            result = social_event_discovery.main()
            result, manual_added = _merge_manual_evidence(result)
        else:
            with shared_lock:
                result = social_event_discovery.main()
                result, manual_added = _merge_manual_evidence(result)
        items = result.get("items", []) if isinstance(result, dict) else []
        movie_count = sum(
            1 for row in items
            if isinstance(row, dict) and row.get("category") == "movie"
        )
        reward_count = sum(
            1 for row in items
            if isinstance(row, dict) and row.get("reward_watch") is True
        )
        return {
            "ok": bool(result.get("fresh_collection_ok", False)),
            "degraded": bool(result.get("degraded", False)),
            "event_collection_patch": hardening.PATCH_ID,
            "item_count": len(items),
            "movie_candidate_count": movie_count,
            "reward_candidate_count": reward_count,
            "manual_evidence_count": int(result.get("manual_evidence_count") or 0),
            "manual_evidence_added_this_run": manual_added,
            "official_social_candidate_count": int(result.get("official_social_candidate_count") or 0),
            "cross_checked_count": int(result.get("cross_checked_count") or 0),
            "error_count": len(result.get("collection_errors", []) or []),
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }
    except Exception as exc:  # isolate discovery failures from the local server
        return {
            "ok": False,
            "degraded": True,
            "event_collection_patch": hardening.PATCH_ID,
            "error": f"{type(exc).__name__}: event quick scan failed",
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }
    finally:
        _RUN_LOCK.release()


def loop(shared_lock=None) -> None:
    """Run after startup collection, then once per hour by default."""
    time.sleep(START_DELAY_SECONDS)
    while True:
        started = time.monotonic()
        summary = run_once(shared_lock)
        print(
            "행사·영화·증정 긴급탐색: " + json.dumps(summary, ensure_ascii=False),
            flush=True,
        )
        elapsed = time.monotonic() - started
        time.sleep(max(60.0, INTERVAL_SECONDS - elapsed))


if __name__ == "__main__":
    print(json.dumps(run_once(), ensure_ascii=False))
