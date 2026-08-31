#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lightweight priority watch for official movie/collab/event/reward announcements.

Unlike the hourly full discovery pass, this watcher only performs account-targeted
public searches against already trusted official SNS accounts. It is intentionally
small so it can run every 30 minutes without duplicating the heavy price/catalog
update or the full 10-topic search matrix. v140 also includes out-of-scope card,
promo, limited-edition and collaboration giveaway/reward announcements.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import threading
import time

import event_collection_hardening_v140 as hardening
import social_event_discovery
from safe_runtime import atomic_write_json, env_int, safe_read_text

DEFAULT_INTERVAL_SECONDS = 30 * 60
DEFAULT_START_DELAY_SECONDS = 3 * 60
INTERVAL_SECONDS = env_int(
    "TCG_EVENT_PRIORITY_INTERVAL_SECONDS",
    DEFAULT_INTERVAL_SECONDS,
    15 * 60,
    2 * 60 * 60,
)
START_DELAY_SECONDS = env_int(
    "TCG_EVENT_PRIORITY_START_DELAY_SECONDS",
    DEFAULT_START_DELAY_SECONDS,
    60,
    30 * 60,
)
_RUN_LOCK = threading.Lock()


def _load_previous() -> dict:
    path = social_event_discovery.OUT
    if not path.exists() or path.is_symlink():
        return {}
    try:
        data = json.loads(safe_read_text(path, max_bytes=3_000_000))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        return {}


def _priority_gaps(items: list[dict], registry: dict) -> list[str]:
    gaps: list[str] = []
    for game in social_event_discovery.GAMES:
        for region in social_event_discovery.REGION_LANG:
            trusted = hardening._trusted_accounts(registry, game, region)
            if not trusted:
                continue
            for topic in hardening.FOCUS_TOPICS:
                count = 0
                for row in items:
                    if not isinstance(row, dict) or row.get("game") != game or row.get("region") != region:
                        continue
                    if social_event_discovery._coverage_topic(row) != topic:
                        continue
                    if row.get("official_account_verified") is True or row.get("official_domain_match") is True or row.get("cross_checked") is True:
                        count += 1
                if count == 0:
                    gaps.append(f"{game}/{region}/{topic}")
    return gaps[:80]


def _collect(registry: dict, jobs: list[tuple[str, str]]) -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    errors: list[str] = []
    is_android = 'com.termux' in os.environ.get('PREFIX', '') or 'ANDROID_ROOT' in os.environ
    workers = 2 if is_android else 3
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {
            pool.submit(hardening.focused_official_social_search, game, region, registry): (game, region)
            for game, region in jobs
        }
        for future in concurrent.futures.as_completed(future_map):
            try:
                part, error = future.result()
            except Exception as exc:
                part, error = [], f"priority watch: {type(exc).__name__}"
            rows.extend(part)
            if error:
                errors.append(error)
    return rows, errors


def _run_locked(started: float) -> dict:
    hardening.apply()
    registry = social_event_discovery.load_registry()
    jobs = [
        (game, region)
        for game in social_event_discovery.GAMES
        for region in social_event_discovery.REGION_LANG
        if hardening._trusted_accounts(registry, game, region)
    ]
    new_rows, errors = _collect(registry, jobs)
    previous = _load_previous()
    existing = [dict(x) for x in previous.get("items", []) if isinstance(x, dict)]
    annotated = social_event_discovery._annotate_social_rows(new_rows, registry)
    merged = social_event_discovery.merge_candidates(existing + annotated)
    payload = dict(previous)
    payload.update({
        "items": merged,
        "item_count": len(merged),
        "priority_watch": {
            "patch": hardening.PATCH_ID,
            "interval_seconds": INTERVAL_SECONDS,
            "trusted_account_groups": len(jobs),
            "result_count": len(annotated),
            "official_result_count": sum(1 for x in annotated if x.get("official_account_verified") is True),
            "reward_result_count": sum(1 for x in annotated if x.get("reward_watch") is True),
            "targeted_candidate_count": sum(1 for x in annotated if x.get("official_query_target") is True),
            "error_count": len(errors),
            "errors": errors[:20],
            "elapsed_seconds": round(time.monotonic() - started, 2),
        },
        "priority_gap_cells": _priority_gaps(merged, registry),
        "official_social_candidate_count": sum(1 for x in merged if x.get("official_account_verified") is True),
        "reward_watch_count": sum(1 for x in merged if x.get("reward_watch") is True),
        "cross_checked_count": sum(1 for x in merged if x.get("cross_checked") is True),
    })

    # Keep the manually verified official announcement visible until indexed
    # discovery catches up; this never promotes unverified community evidence.
    try:
        import event_quick_watch
        payload, manual_added = event_quick_watch._merge_manual_evidence(payload)
    except (ImportError, AttributeError, OSError, ValueError, TypeError):
        manual_added = 0
    atomic_write_json(social_event_discovery.OUT, payload, suffix=".priority.tmp")
    return {
        "ok": True,
        "patch": hardening.PATCH_ID,
        "trusted_account_groups": len(jobs),
        "result_count": len(annotated),
        "official_result_count": sum(1 for x in annotated if x.get("official_account_verified") is True),
        "reward_result_count": sum(1 for x in annotated if x.get("reward_watch") is True),
        "manual_evidence_added": manual_added,
        "priority_gap_count": len(payload.get("priority_gap_cells", []) or []),
        "error_count": len(errors),
        "elapsed_seconds": round(time.monotonic() - started, 2),
    }


def run_once(shared_lock=None) -> dict:
    if not _RUN_LOCK.acquire(blocking=False):
        return {"ok": True, "skipped": True, "reason": "priority watch already running"}
    started = time.monotonic()
    try:
        if shared_lock is None:
            return _run_locked(started)
        with shared_lock:
            return _run_locked(started)
    except Exception as exc:
        return {
            "ok": False,
            "patch": hardening.PATCH_ID,
            "error": f"{type(exc).__name__}: priority event watch failed",
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }
    finally:
        _RUN_LOCK.release()


def loop(shared_lock=None) -> None:
    time.sleep(START_DELAY_SECONDS)
    while True:
        started = time.monotonic()
        summary = run_once(shared_lock)
        print("공식 SNS 우선탐색: " + json.dumps(summary, ensure_ascii=False), flush=True)
        elapsed = time.monotonic() - started
        time.sleep(max(60.0, INTERVAL_SECONDS - elapsed))


if __name__ == "__main__":
    print(json.dumps(run_once(), ensure_ascii=False))
