#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Legacy one-click updater retained for compatibility, without shell execution."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from safe_runtime import atomic_write_json, safe_read_text

BASE = Path(__file__).resolve().parent


def _run_script(filename: str) -> None:
    # Filenames are fixed by the caller; never pass user-controlled text to a shell.
    target = BASE / filename
    if target.parent != BASE or not target.is_file() or target.is_symlink():
        raise RuntimeError(f"안전하게 실행할 수 없는 업데이트 스크립트: {filename}")
    subprocess.run(
        [sys.executable, str(target)],
        cwd=str(BASE),
        check=True,
        timeout=1800,
    )


def _mark_success() -> None:
    path = BASE / "learning_store.json"
    try:
        raw = safe_read_text(path, max_bytes=5_000_000)
        store = json.loads(raw) if raw.strip() else {}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        store = {}
    if not isinstance(store, dict):
        store = {}
    store["last_full_update"] = "SUCCESS"
    atomic_write_json(path, store)


def run_one_click_update() -> None:
    print("1/4. 안전 백업 및 안전 업데이트 진행 중...")
    _run_script("update_exchange_rates.py")

    print("2/4. 네이버/구글/TCG 최신 자료 수집 중...")
    _run_script("update_market_prices.py")
    _run_script("update_promo_events.py")

    print("3/4. 변경 내용 비교 및 교차 검증 중...")
    _run_script("verify_all.py")

    print("4/4. 검증 완료된 최신 내용 자동 반영 중...")
    _mark_success()
    print("✅ 원클릭 모든 업데이트 및 반영이 완료되었습니다.")


if __name__ == "__main__":
    run_one_click_update()
