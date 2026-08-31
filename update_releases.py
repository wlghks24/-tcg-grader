#!/usr/bin/env python3
"""Conservatively refresh official TCG release data for GitHub Pages.

Historical release rows are append-only: once an official release was verified it is
never discarded merely because it became old.  New runs only add/update verified
official rows and preserve the last known-good archive on network failures.
"""
from __future__ import annotations

import datetime as dt
import concurrent.futures
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from safe_runtime import atomic_write_json, diagnostic_exception, env_int, html_to_text, safe_read_text, safe_urlopen

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "releases.json"
HEADERS = {"User-Agent": "TCG-Grader-Release-Checker/1.0 (+GitHub Pages; official pages only)"}
ALLOWED = {
    "pokemoncard.co.kr", "www.pokemoncard.co.kr",
    "www.pokemon-card.com", "www.30th.pokemon-card.com", "www.pokemon.com",
    "onepiece-cardgame.kr", "www.onepiece-cardgame.kr",
    "www.onepiece-cardgame.com", "en.onepiece-cardgame.com",
    "www.naruto-cardgame.com",
}

# Plausibility guard only.  Do NOT use a rolling recent-date window here: that used
# to delete old official products from the archive on every refresh.
MIN_RELEASE_DATE = dt.date(1996, 1, 1)
MAX_FUTURE_YEARS = 5


def fetch(url: str) -> str:
    host = urllib.parse.urlparse(url).hostname
    if host not in ALLOWED:
        raise ValueError(f"unapproved host: {host}")
    req = urllib.request.Request(url, headers=HEADERS)
    with safe_urlopen(req, timeout=env_int('TCG_HTTP_TIMEOUT',20,5,60), allowed_hosts=ALLOWED) as response:
        return response.read(3_000_000).decode("utf-8", "replace")


def iso_en(value: str) -> str:
    return dt.datetime.strptime(value, "%B %d, %Y").date().isoformat()


def _english_release_fields(value: str) -> dict:
    """Parse an official English day or month without inventing a day."""
    normalized = re.sub(r"\s+", " ", str(value or "")).strip()
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return {"release_date": dt.datetime.strptime(normalized, fmt).date().isoformat()}
        except ValueError:
            pass
    for fmt in ("%B %Y", "%b %Y"):
        try:
            month = dt.datetime.strptime(normalized, fmt).date()
            return {
                "release_date": None,
                "release_window": month.strftime("%Y-%m"),
                "release_precision": "month",
                "release_label": normalized,
            }
        except ValueError:
            pass
    raise ValueError(f"공식 출시일 형식을 읽지 못했습니다: {normalized[:40]}")


def collect_onepiece(url: str, region: str) -> list[dict]:
    text = html_to_text(fetch(url))
    pattern = re.compile(
        r"((?:(?:EXTRA|PREMIUM)\s+)?BOOSTER(?:\s+PACK)?\s+.{2,130}?"
        r"\[(?:OP|EB|PRB)[A-Z0-9-]+\])\s*"
        r"Release\s*Date\s*([A-Za-z]+\s+(?:\d{1,2},\s*)?20\d{2})\s*"
        r"MSRP\s*USD\s*\$([0-9]+(?:\.[0-9]+)?)",
        re.I,
    )
    found = []
    for name, date, price in pattern.findall(text):
        row={"game":"ONE PIECE","region":region,"name":re.sub(r"\s+"," ",name).strip(),
             "price":f"${price}/팩","status":"공식 확인","source":url}
        row.update(_english_release_fields(date))
        found.append(row)
    return found


def collect_onepiece_jp() -> list[dict]:
    url = "https://www.onepiece-cardgame.com/products/?subcategory=boosters"
    text = html_to_text(fetch(url))
    pattern = re.compile(
        r"(?:ブースターパック|エクストラブースター|プレミアムブースター)\s*"
        r"(.{2,90}?)\s*〖(OP-\d+|EB-\d+|PRB-\d+)〗\s*"
        r"発売日\s*(20\d{2})\s*[.年]\s*(\d{1,2})"
        r"(?:\s*[.月]\s*(\d{1,2})\s*日?)?(?:\([^)]*\))?\s*"
        r"メーカー希望小売価格\s*([0-9,]+)円",
        re.I,
    )
    found = []
    for title, code, y, m, d, price in pattern.findall(text):
        row={
            "game":"ONE PIECE", "region":"JP",
            "name":f"{title.strip()} [{code}]",
            "price":f"¥{price}/팩", "status":"공식 확인", "source":url,
        }
        if d:
            row["release_date"]=dt.date(int(y),int(m),int(d)).isoformat()
        else:
            row.update({"release_date":None,"release_window":f"{int(y):04d}-{int(m):02d}",
                        "release_precision":"month","release_label":f"{int(y):04d}년 {int(m)}월"})
        found.append(row)
    return found


def collect_onepiece_kr() -> list[dict]:
    url = "https://onepiece-cardgame.kr/products.do"
    text = html_to_text(fetch(url))
    pattern = re.compile(r"\[(OPK-\d+|EBK-\d+)\]\s*(.{2,75}?)\s*(20\d{2}-\d{2}-\d{2}).{0,100}?\[1BOX\]\s*([0-9,]+)\s*원", re.I)
    found = []
    for code, title, date, price in pattern.findall(text):
        found.append({
            "game":"ONE PIECE", "region":"KR", "name":f"[{code}] {title.strip()}",
            "release_date":date, "price":f"₩{price}/BOX", "status":"공식 확인", "source":url,
        })
    return found


def collect_pokemon_jp() -> list[dict]:
    url = "https://www.pokemon-card.com/products/index.html?productType=expansion"
    text = html_to_text(fetch(url))
    pattern = re.compile(
        r"(?:拡張パック|ハイクラスパック)\s*[「『]?\s*(.{2,55}?)\s*[」』]?\s*"
        r"(?:拡張パック\s*)?販売日\s*(20\d{2})\s*年\s*(\d{1,2})\s*月\s*"
        r"(\d{1,2})\s*日.{0,160}?希望小売価格\s*([0-9,]+)\s*円"
    )
    found = []
    for name, y, m, d, price in pattern.findall(text):
        date = dt.date(int(y), int(m), int(d)).isoformat()
        found.append({"game":"Pokémon","region":"JP","name":name.strip(),"release_date":date,"price":f"¥{price}/팩","status":"공식 확인","source":url})
    return found


def collect_naruto() -> list[dict]:
    url = "https://www.naruto-cardgame.com/asia-en/"
    text = html_to_text(fetch(url))
    if not re.search(r"(?:Summer\s+2027|Arriving\s+in\s+Summer\s+2027)", text, re.I):
        return []
    return [{"game":"NARUTO","region":"GLOBAL","name":"NARUTO CARD GAME","release_date":None,"release_window":"2027년 여름","price":"가격·제품 구성 미정","status":"전 세계 동시 출시 예정","source":url}]


def valid(item: dict) -> bool:
    if not all(item.get(k) for k in ("game", "region", "name", "source")):
        return False
    host_ok = urllib.parse.urlparse(item["source"]).hostname in ALLOWED
    if not host_ok:
        return False
    if item.get("release_window") and not item.get("release_date"):
        window = str(item["release_window"]).strip()
        month_match = re.fullmatch(r"(20\d{2})-(0[1-9]|1[0-2])", window)
        seasonal_match = re.fullmatch(r"(20\d{2})년\s*(봄|여름|가을|겨울)", window)
        match = month_match or seasonal_match
        if not match:
            return False
        year = int(match.group(1))
        return MIN_RELEASE_DATE.year <= year <= dt.date.today().year + MAX_FUTURE_YEARS
    try:
        date = dt.date.fromisoformat(str(item["release_date"]))
    except (TypeError, ValueError):
        return False
    max_date = dt.date.today().replace(year=dt.date.today().year + MAX_FUTURE_YEARS)
    return MIN_RELEASE_DATE <= date <= max_date


def item_key(item: dict) -> tuple:
    name = str(item.get("name", ""))
    m = re.search(r"\b(?:OPK|EBK|OP|EB|PRB|SV|MEGA)[- ]?\d+[A-Z]?\b", name, re.I)
    identity = re.sub(r"[^A-Z0-9]", "", m.group(0).upper()) if m else re.sub(r"\s+", " ", name).strip().casefold()
    # Date is intentionally not part of identity.  Re-release/date corrections update
    # the same product rather than creating endless duplicates.
    return (item["game"], item["region"], identity)


def _prefer_new(old: dict, new: dict) -> dict:
    """Merge a freshly verified official row without discarding useful history fields."""
    merged = dict(old or {})
    for k, v in (new or {}).items():
        if v not in (None, "", [], {}):
            merged[k] = v
    merged.setdefault("first_seen_at", (old or {}).get("first_seen_at") or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
    merged["last_verified_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    return merged


def main() -> None:
    current = json.loads(safe_read_text(DATA))
    candidates: list[dict] = []
    errors: list[str] = []
    collectors = [
        ("Pokémon JP", collect_pokemon_jp),
        ("ONE PIECE KR", collect_onepiece_kr),
        ("ONE PIECE JP", collect_onepiece_jp),
        ("ONE PIECE US", lambda: collect_onepiece("https://en.onepiece-cardgame.com/products/", "US")),
        ("NARUTO Global", collect_naruto),
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(collectors)) as pool:
        futures = {pool.submit(collector): label for label, collector in collectors}
        for future in concurrent.futures.as_completed(futures):
            label = futures[future]
            try:
                batch = future.result()
                if not batch:
                    raise ValueError("공식 페이지에서 검증 가능한 상품을 1건도 읽지 못함")
                candidates.extend(batch)
            except (urllib.error.URLError, TimeoutError, OSError, ValueError, UnicodeError) as exc:
                errors.append(f"{label}: {diagnostic_exception(exc)}")

    # Unified historical backfill: Pokémon / ONE PIECE / NARUTO all use the same
    # append-only official-history policy.  The backfill is incremental to keep
    # tablet/network load bounded and never deletes previous verified rows.
    try:
        from release_history_backfill import run as run_release_history_backfill
        history = run_release_history_backfill(
            fetch, html_to_text, collect_onepiece_kr, collect_onepiece_jp,
            lambda: collect_onepiece("https://en.onepiece-cardgame.com/products/", "US"),
            collect_naruto,
        )
        candidates.extend(history.get("items", []))
        errors.extend(history.get("errors", []))
        current["history_backfill_progress"] = history.get("progress", {})
        current["unified_history_policy"] = history.get("policy", "")
    except (OSError, ValueError, TypeError, ImportError) as exc:
        errors.append(f"통합 과거출시 백필: {diagnostic_exception(exc)}")

    # Preserve ALL previously valid official history, regardless of age.
    merged: dict[tuple, dict] = {}
    for x in current.get("items", []):
        if valid(x):
            merged[item_key(x)] = dict(x)
    for item in candidates:
        if valid(item):
            key = item_key(item)
            merged[key] = _prefer_new(merged.get(key, {}), item)

    current["items"] = sorted(merged.values(), key=lambda x: (x.get("release_date") or "9999-12-31", x.get("region", ""), x.get("name", "")))
    current["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    current["collection_status"] = "정상" if not errors else "일부 출처 확인 실패 · 기존 전체 출시이력 보존"
    current["collection_errors"] = errors
    current["history_policy"] = "공식 확인된 과거 출시제품은 기간 제한 없이 누적 보존하며 네트워크 실패 시 삭제하지 않음"
    current["history_count"] = len(current["items"])
    atomic_write_json(DATA,current,suffix=".json.tmp")


if __name__ == "__main__":
    main()
