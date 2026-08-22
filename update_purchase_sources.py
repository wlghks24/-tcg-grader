#!/usr/bin/env python3
"""Safely validate and refresh the curated purchase-source directory."""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import ipaddress
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "purchase_sources.json"
REGIONS = {"KR", "JP", "US"}
GAMES = {"Pokemon", "ONE PIECE", "NARUTO"}
TYPES = {"official", "marketplace", "used", "blog", "map", "tracker"}
TIMEOUT_SECONDS = 7
MAX_ONLINE_CHECKS = 16
CANONICAL_URLS = {
    "https://events.pokemon.com/en-us/locations": "https://events.pokemon.com/EventLocator",
    "https://www.gamestop.com/stores/": "https://www.gamestop.com/stores",
}


def checked_url(value: str, template: bool = False) -> str:
    if not isinstance(value, str) or not value or len(value) > 2048:
        raise ValueError("구매처 주소 형식 오류")
    if template and value.count("{query}") != 1:
        raise ValueError("구매처 검색어 자리표시자 오류")
    probe = value.replace("{query}", "TCG")
    parsed = urllib.parse.urlsplit(probe)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("HTTPS 외부 주소만 허용")
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise ValueError("내부 주소 차단")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("사설 IP 주소 차단")
    return CANONICAL_URLS.get(value, value)


def normalize_source(source: dict) -> dict:
    if not isinstance(source, dict):
        raise ValueError("구매처 항목 형식 오류")
    clean = dict(source)
    if not isinstance(clean.get("name"), str) or not clean["name"].strip():
        raise ValueError("구매처 이름 누락")
    if clean.get("region") not in REGIONS or clean.get("type") not in TYPES:
        raise ValueError("구매처 국가 또는 유형 오류")
    games = clean.get("games")
    if not isinstance(games, list) or not games or not set(games).issubset(GAMES):
        raise ValueError("구매처 카드게임 분류 오류")
    if clean.get("channel", "online") not in {"online", "offline"}:
        raise ValueError("구매처 채널 오류")
    if clean.get("url"):
        clean["url"] = checked_url(clean["url"])
    elif clean.get("url_template"):
        clean["url_template"] = checked_url(clean["url_template"], template=True)
    else:
        raise ValueError("구매처 연결 주소 누락")
    return clean


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        checked_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def probe(source: dict) -> tuple[str, str]:
    value = source.get("url")
    if not value:
        return source["name"], "검색주소 형식 정상"
    opener = urllib.request.build_opener(SafeRedirect)
    headers = {"User-Agent": "Mozilla/5.0 TCG-Grader-Link-Checker/1.0"}
    try:
        request = urllib.request.Request(value, headers=headers, method="HEAD")
        try:
            response = opener.open(request, timeout=TIMEOUT_SECONDS)
        except urllib.error.HTTPError as exc:
            if exc.code not in {403, 405, 429}:
                raise
            return source["name"], f"접속 제한·기존 주소 유지 (HTTP {exc.code})"
        with response:
            checked_url(response.geturl())
            return source["name"], "정상"
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, socket.timeout) as exc:
        return source["name"], f"재확인 필요·기존 주소 유지 ({type(exc).__name__})"


def main() -> dict:
    current = json.loads(DATA.read_text(encoding="utf-8"))
    original = current.get("sources")
    if not isinstance(original, list) or not original:
        raise ValueError("구매처 목록이 비어 있습니다")
    normalized = []
    seen = set()
    errors = []
    for source in original:
        try:
            clean = normalize_source(source)
            key = (clean["name"], clean["region"], clean.get("channel", "online"))
            if key in seen:
                errors.append(f"{clean['name']}: 중복 구매처 유지")
            else:
                seen.add(key)
                normalized.append(clean)
        except ValueError as exc:
            errors.append(f"{source.get('name', '이름 없음')}: {exc}")
            # A malformed record is never exposed as an executable link.
    if len(normalized) < max(1, len(original) // 2):
        raise ValueError("구매처 대량 감소 차단·기존 정상자료 유지")

    targets = [s for s in normalized if s.get("url") and s.get("type") == "official"][:MAX_ONLINE_CHECKS]
    statuses = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for name, state in pool.map(probe, targets):
            statuses[name] = state
            if state.startswith("재확인 필요"):
                errors.append(f"{name}: {state}")

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    for source in normalized:
        source["link_status"] = statuses.get(source["name"], "주소 형식 검증 완료")
        source["last_checked_at"] = now
    current["sources"] = normalized
    current["updated_at"] = now
    current["collection_status"] = "정상" if not errors else "일부 구매처 재확인 필요·기존 목록 유지"
    current["collection_errors"] = errors
    current["checked_source_count"] = len(normalized)
    current["online_checked_count"] = len(targets)
    temp = DATA.with_suffix(".json.tmp")
    temp.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(DATA)
    return current


if __name__ == "__main__":
    main()
