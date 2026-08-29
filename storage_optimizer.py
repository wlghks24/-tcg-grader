#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reduce local storage without deleting user data or learning history.

Safe policy:
- compact valid JSON/JSON backups by removing indentation only;
- remove Python caches and temporary atomic-write files;
- never delete release history, market data, grading learning, photos, or backups;
- run `git gc --auto` only (no history rewriting/prune-now).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(__file__).resolve().parent
REPORT = BASE / "storage_optimization_report.json"

JSON_NAMES = {
    "releases.json","market_prices.json","market_watch.json","promo_events.json",
    "supplementary_candidates.json","social_event_candidates.json","purchase_sources.json",
    "purchase_signals.json","exchange_rates.json","tcg_live_data.json","auto_update_report.json",
    "auto_update_issues.json","auto_repair_memory.json","learning_store.json","vision_self_learning_report.json",
    "ebay_grader_candidates.json","verified_certifications.json","card_identity_learning.json",
    "source_collection_stats.json","collection_learning_memory.json","collection_learning_report.json",
    "collection_feedback.json","collection_provider_health.json","multi_market_source_learning.json",
    "graded_photo_candidates.json","graded_photo_source_learning.json","box_hit_market_candidates.json",
    "box_hit_market_learning.json","precollect_status.json"
}

TEMP_GLOBS = ("*.tmp", "*.tmp.json", "*.db.tmp", "*.json.tmp", "*.adaptive-social.tmp")
CACHE_DIRS = ("__pycache__", ".pytest_cache", ".mypy_cache")


def size_of(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def compact_json(path: Path) -> tuple[int, int]:
    if not path.exists() or path.is_symlink() or not path.is_file():
        return (0, 0)
    before = size_of(path)
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        if len(encoded.encode("utf-8")) >= before:
            return (before, before)
        tmp = path.with_name(path.name + ".opt.tmp")
        tmp.write_text(encoded, encoding="utf-8")
        tmp.replace(path)
        return (before, size_of(path))
    except (OSError, UnicodeError, ValueError, TypeError):
        return (before, before)


def remove_caches() -> tuple[int, int]:
    removed_files = 0
    freed = 0
    for name in CACHE_DIRS:
        for p in BASE.rglob(name):
            if not p.is_dir() or p.is_symlink():
                continue
            total = sum(size_of(x) for x in p.rglob("*") if x.is_file())
            try:
                shutil.rmtree(p)
                removed_files += 1
                freed += total
            except OSError:
                pass
    for pattern in TEMP_GLOBS:
        for p in BASE.glob(pattern):
            if not p.is_file() or p.is_symlink():
                continue
            s = size_of(p)
            try:
                p.unlink()
                removed_files += 1
                freed += s
            except OSError:
                pass
    return removed_files, freed


def compact_known_json() -> dict:
    before = after = files = 0
    candidates = []
    for name in JSON_NAMES:
        candidates.append(BASE / name)
        candidates.append(BASE / (name + ".bak"))
    for path in candidates:
        if not path.exists():
            continue
        b, a = compact_json(path)
        if b:
            files += 1
            before += b
            after += a
    return {"files": files, "before_bytes": before, "after_bytes": after, "saved_bytes": max(0, before-after)}


def git_gc_auto() -> str:
    if not (BASE / ".git").exists():
        return "not_git_checkout"
    try:
        cp = subprocess.run(
            ["git", "gc", "--auto"], cwd=BASE, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=45, check=False
        )
        return "ok" if cp.returncode == 0 else f"exit_{cp.returncode}"
    except (OSError, subprocess.SubprocessError):
        return "skipped"


def run() -> dict:
    json_result = compact_known_json()
    removed, cache_saved = remove_caches()
    git_result = git_gc_auto()
    result = {
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "policy": "학습/출시/시세/백업 데이터 삭제 없음 · JSON 공백압축 + 캐시/임시파일 정리 + git gc --auto",
        "json": json_result,
        "cache_temp_removed": removed,
        "cache_temp_saved_bytes": cache_saved,
        "estimated_saved_bytes": json_result["saved_bytes"] + cache_saved,
        "git_gc": git_result,
    }
    try:
        REPORT.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    except OSError:
        pass
    return result


if __name__ == "__main__":
    result = run()
    mb = result["estimated_saved_bytes"] / (1024*1024)
    print(f"저장공간 최적화 완료 · 약 {mb:.2f} MB 절감 · 학습/출시/시세 데이터 보존")
