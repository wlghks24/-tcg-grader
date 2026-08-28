#!/usr/bin/env python3
"""명시적으로 실행할 때만 GitHub 동기화를 수행한다."""
from __future__ import annotations
import json
from pathlib import Path
from github_sync_engine import GitHubSyncEngine
from safe_runtime import reject_nonstandard_json, safe_read_text, unique_json_object

ROOT = Path(__file__).resolve().parent
SYNC_FILES = ("releases.json", "market_watch.json", "market_prices.json", "promo_events.json", "purchase_sources.json", "exchange_rates.json")


def snapshot():
    data = {}
    for filename in SYNC_FILES:
        path = ROOT / filename
        try:
            data[filename] = json.loads(
                safe_read_text(path),
                parse_constant=reject_nonstandard_json,
                object_pairs_hook=unique_json_object,
            )
        except (OSError, ValueError, TypeError):
            data[filename] = None
    return data


def main():
    engine = GitHubSyncEngine(file_path="tcg_sync_data.json")
    if not engine.configured:
        print("GitHub 환경변수가 없어 업로드하지 않았습니다. GITHUB_TOKEN/GITHUB_OWNER/GITHUB_REPO를 설정하세요.")
        return False
    _, sha = engine.pull_from_github()
    ok = engine.push_to_github(snapshot(), sha=sha, message="Update TCG synchronized data")
    print("GitHub 동기화 완료" if ok else "GitHub 동기화 실패 · 로컬 캐시 보존")
    return ok

if __name__ == "__main__":
    main()
