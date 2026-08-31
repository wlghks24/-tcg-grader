#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lightweight breaking-event scan between the heavier six-hour update cycles.

The normal updater intentionally remains conservative because price, image and
full-catalog collection is expensive and can trigger 403/429 responses.  This
module only refreshes social/event discovery so newly announced movies,
collaborations, promos and events can reach social_event_candidates.json much
sooner.
"""
from __future__ import annotations

import json
import threading
import time

import social_event_discovery
from safe_runtime import env_int

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


def run_once(shared_lock=None) -> dict:
    """Refresh only event/social candidates and return a small health summary."""
    if not _RUN_LOCK.acquire(blocking=False):
        return {"ok": True, "skipped": True, "reason": "event quick scan already running"}
    started = time.monotonic()
    try:
        if shared_lock is None:
            result = social_event_discovery.main()
        else:
            with shared_lock:
                result = social_event_discovery.main()
        items = result.get("items", []) if isinstance(result, dict) else []
        movie_count = sum(
            1 for row in items
            if isinstance(row, dict) and row.get("category") == "movie"
        )
        return {
            "ok": bool(result.get("fresh_collection_ok", False)),
            "degraded": bool(result.get("degraded", False)),
            "item_count": len(items),
            "movie_candidate_count": movie_count,
            "official_social_candidate_count": int(result.get("official_social_candidate_count") or 0),
            "cross_checked_count": int(result.get("cross_checked_count") or 0),
            "error_count": len(result.get("collection_errors", []) or []),
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }
    except Exception as exc:  # isolate discovery failures from the local server
        return {
            "ok": False,
            "degraded": True,
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
            "행사·영화 긴급탐색: " + json.dumps(summary, ensure_ascii=False),
            flush=True,
        )
        elapsed = time.monotonic() - started
        time.sleep(max(60.0, INTERVAL_SECONDS - elapsed))


if __name__ == "__main__":
    print(json.dumps(run_once(), ensure_ascii=False))
