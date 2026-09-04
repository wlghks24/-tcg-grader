#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bounded official release-history backfill for Pokémon / ONE PIECE / NARUTO.

Safety contracts:
- all three games expose the same KR / JP / US matrix;
- only hard-coded official indexes and caller-supplied official collectors are used;
- same-host detail traversal is bounded;
- exact day/month/season precision is preserved without inventing dates;
- network/parser failures never delete previously verified history;
- global wording alone never becomes a Korea-specific release claim.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import re
import urllib.parse
from pathlib import Path

from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "release_history_progress.json"
MAX_TEXT = 2_000_000
MAX_DETAIL_PAGES_PER_REGION = 18
MAX_ROWS_PER_SOURCE = 160
MAX_TOTAL_ROWS = 600
EXPECTED_CELLS = tuple(
    (game, region)
    for game in ("Pokémon", "ONE PIECE", "NARUTO")
    for region in ("KR", "JP", "US")
)
POKEMON_KR_INDEXES = (
    "https://pokemoncard.co.kr/card/category/info1",
    "https://pokemoncard.co.kr/card",
)
POKEMON_US_INDEXES = (
    "https://www.pokemon.com/us/pokemon-tcg/product-gallery/",
    "https://www.pokemon.com/us/pokemon-news/",
)
POKEMON_REGION_SOURCES = {
    "KR": POKEMON_KR_INDEXES[0],
    "US": POKEMON_US_INDEXES[0],
}
NARUTO_REGION_SOURCES = {
    "KR": "https://www.naruto-cardgame.com/asia-en/",
    "JP": "https://www.naruto-cardgame.com/jp/",
    "US": "https://www.naruto-cardgame.com/en/",
}


def _norm(value):
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def _bounded_text(value):
    return _norm(value)[:MAX_TEXT]


def _today():
    return dt.date.today()


def _safe_date(year, month, day):
    try:
        return dt.date(int(year), int(month), int(day)).isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def _parse_english_date(value):
    value = _norm(value)
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return dt.datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _load_state():
    try:
        data = json.loads(safe_read_text(STATE, max_bytes=500_000))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError, UnicodeError):
        return {}


def _save_state(data):
    atomic_write_json(
        STATE,
        data if isinstance(data, dict) else {},
        suffix=".release-history.tmp",
    )


def _dedupe(rows, limit=MAX_ROWS_PER_SOURCE):
    out, seen = [], set()
    try:
        safe_limit = max(1, min(MAX_TOTAL_ROWS, int(limit)))
    except (TypeError, ValueError, OverflowError):
        safe_limit = MAX_ROWS_PER_SOURCE
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        key = (
            row.get("game"),
            row.get("region"),
            _norm(row.get("name")).casefold(),
            row.get("release_date"),
            row.get("release_window"),
            row.get("source"),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= safe_limit:
            break
    return out


def _official_detail_links(raw, base_url, path_pattern, limit=MAX_DETAIL_PAGES_PER_REGION):
    """Return only bounded HTTPS links on the exact official index host."""
    try:
        base = urllib.parse.urlsplit(base_url)
    except ValueError:
        return []
    base_host = (base.hostname or "").lower()
    if base.scheme != "https" or not base_host:
        return []
    try:
        safe_limit = max(1, min(40, int(limit)))
    except (TypeError, ValueError, OverflowError):
        safe_limit = MAX_DETAIL_PAGES_PER_REGION
    out, seen = [], set()
    hrefs = re.findall(r"href\s*=\s*[\"']([^\"']+)[\"']", str(raw or ""), re.I)[:2500]
    for href in hrefs:
        target = urllib.parse.urljoin(base_url, html.unescape(href)).split("#", 1)[0]
        try:
            parsed = urllib.parse.urlsplit(target)
        except ValueError:
            continue
        if parsed.scheme != "https" or (parsed.hostname or "").lower() != base_host:
            continue
        if not re.search(path_pattern, parsed.path, re.I):
            continue
        target = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))
        if target in seen:
            continue
        seen.add(target)
        out.append(target)
        if len(out) >= safe_limit:
            break
    return out


def pokemon_jp_years(fetch, html_to_text, years_per_run=2):
    """Incrementally backfill Japanese Pokémon expansion/high-class products."""
    state = _load_state()
    current_year = _today().year
    try:
        next_year = int(state.get("pokemon_jp_next_year") or current_year)
    except (TypeError, ValueError, OverflowError):
        next_year = current_year
    next_year = max(1996, min(current_year, next_year))
    try:
        safe_years = max(1, min(5, int(years_per_run)))
    except (TypeError, ValueError, OverflowError):
        safe_years = 2
    years, cursor = [current_year], next_year
    while len(years) < safe_years + 1 and cursor >= 1996:
        if cursor not in years:
            years.append(cursor)
        cursor -= 1

    pattern = re.compile(
        r"(?:拡張パック|強化拡張パック|ハイクラスパック|コンセプトパック|再販パック)\s*"
        r"[「『]?(.{2,80}?)[」』]?\s*.{0,180}?(?:発売日|販売日)\s*"
        r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日"
        r"(?:.{0,220}?(?:希望小売価格|価格)\s*([0-9,]+)円)?",
        re.I,
    )
    rows, errors = [], []
    for archive_year in years:
        url = (
            "https://www.pokemon-card.com/products/?productType=expansion&"
            f"dateLowerY={archive_year}&dateLowerM=1&dateLowerD=1&"
            f"dateUpperY={archive_year}&dateUpperM=12&dateUpperD=31"
        )
        try:
            text = _bounded_text(html_to_text(fetch(url)))
        except (OSError, ValueError, TypeError, UnicodeError) as exc:
            errors.append(f"Pokémon JP {archive_year}: {type(exc).__name__}")
            continue
        for name, yy, mm, dd, price in pattern.findall(text):
            if int(yy) != archive_year:
                continue
            release_date = _safe_date(yy, mm, dd)
            if not release_date:
                continue
            rows.append({
                "game": "Pokémon",
                "region": "JP",
                "name": _norm(name),
                "release_date": release_date,
                "price": f"¥{price}/팩" if price else "공식 가격 확인",
                "status": "공식 과거출시 확인",
                "source": url,
                "archive_year": archive_year,
            })

    state["pokemon_jp_next_year"] = max(1995, next_year - safe_years)
    state["pokemon_jp_last_run"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    _save_state(state)
    return _dedupe(rows), errors


def _pokemon_kr_row(title, source, *, release_date=None, year=None, month=None, price=None):
    if price:
        try:
            price_label = f"₩{int(str(price).replace(',', '')):,}"
        except (TypeError, ValueError, OverflowError):
            price_label = "공식 가격 확인"
    else:
        price_label = "공식 가격 확인"
    row = {
        "game": "Pokémon",
        "region": "KR",
        "name": _norm(title)[:180],
        "price": price_label,
        "source": source,
    }
    if release_date:
        row.update({"release_date": release_date, "status": "공식 출시 확인"})
        return row
    try:
        year, month = int(year), int(month)
    except (TypeError, ValueError, OverflowError):
        return None
    if not (1996 <= year <= _today().year + 5 and 1 <= month <= 12):
        return None
    row.update({
        "release_date": None,
        "release_window": f"{year:04d}-{month:02d}",
        "release_precision": "month",
        "release_label": f"{year}년 {month}월",
        "status": "공식 출시월 확인",
    })
    return row


def parse_pokemon_kr(text, source=POKEMON_REGION_SOURCES["KR"]):
    """Parse Korean products only when an explicit release date/month is present."""
    value = _bounded_text(text)
    product = (
        r"(?:MEGA|스칼렛&바이올렛|소드&실드|썬&문|포켓몬\s*카드\s*게임)?\s*"
        r"(?:강화\s*)?(?:확장팩|하이클래스팩|스페셜\s*팩|스타터(?:\s*세트|\s*덱)?|구축덱)"
    )
    title = rf"(?P<title>{product}\s*.{{0,45}}?[「『][^」』]{{2,80}}[」』])"
    price_tail = r"(?:.{0,100}?(?:가격|판매가격)\s*(?P<price>[0-9][0-9,]{0,8})\s*원)?"
    day_patterns = (
        re.compile(
            title + r".{0,140}?(?:발매일|출시일)\s*(?P<y>20\d{2})[-./](?P<m>\d{1,2})[-./](?P<d>\d{1,2})" + price_tail,
            re.I,
        ),
        re.compile(
            title + r".{0,120}?(?P<y>20\d{2})년\s*(?P<m>\d{1,2})월\s*(?P<d>\d{1,2})일"
            r".{0,55}?(?:출시|발매|판매\s*시작|정식\s*발매)" + price_tail,
            re.I,
        ),
        re.compile(
            title + r".{0,120}?(?:출시|발매|판매\s*시작|정식\s*발매).{0,55}?"
            r"(?P<y>20\d{2})년\s*(?P<m>\d{1,2})월\s*(?P<d>\d{1,2})일" + price_tail,
            re.I,
        ),
    )
    rows = []
    for pattern in day_patterns:
        for match in pattern.finditer(value):
            release_date = _safe_date(match.group("y"), match.group("m"), match.group("d"))
            if release_date:
                row = _pokemon_kr_row(
                    match.group("title"),
                    source,
                    release_date=release_date,
                    price=match.groupdict().get("price"),
                )
                if row:
                    rows.append(row)

    month_patterns = (
        re.compile(
            title + r".{0,120}?(?P<y>20\d{2})년\s*(?P<m>\d{1,2})월(?!\s*\d{1,2}일)"
            r".{0,55}?(?:출시|발매|판매\s*예정|발매\s*예정)",
            re.I,
        ),
        re.compile(
            title + r".{0,120}?(?:출시|발매|판매\s*예정|발매\s*예정).{0,55}?"
            r"(?P<y>20\d{2})년\s*(?P<m>\d{1,2})월(?!\s*\d{1,2}일)",
            re.I,
        ),
    )
    for pattern in month_patterns:
        for match in pattern.finditer(value):
            row = _pokemon_kr_row(
                match.group("title"), source,
                year=match.group("y"), month=match.group("m"),
            )
            if row:
                rows.append(row)
    return _dedupe(rows)


def parse_pokemon_us(text, source=POKEMON_REGION_SOURCES["US"]):
    """Parse Pokemon.com only when title + explicit launch/release + day are present."""
    value = _bounded_text(text)
    # Lookahead anchors the title to the release marker. This avoids the older
    # non-greedy pattern truncating e.g. "Pokémon TCG: 30th Celebration" to "...: 3".
    title = (
        r"(?P<title>Pok[eé]mon\s+TCG(?::|\s).{2,150}?)"
        r"(?=\s+(?:Launch|Release\s+Date|releasing|arriving)\b)"
    )
    pattern = re.compile(
        title
        + r"\s+(?:Launch|Release\s+Date|releasing|arriving)\s*:?\s*.{0,90}?"
        + r"(?P<date>[A-Z][a-z]+\s+\d{1,2},\s*20\d{2})",
        re.I,
    )
    rows = []
    for match in pattern.finditer(value):
        release_date = _parse_english_date(match.group("date"))
        if not release_date:
            continue
        rows.append({
            "game": "Pokémon",
            "region": "US",
            "name": _norm(match.group("title"))[:180],
            "release_date": release_date,
            "price": "official price check",
            "status": "official release verified",
            "source": source,
        })
    return _dedupe(rows)


def _collect_pokemon_region_details(fetch, html_to_text, region):
    if region == "KR":
        indexes = POKEMON_KR_INDEXES
        path_pattern = r"^/card/\d{1,8}/?$"
        parser = parse_pokemon_kr
    elif region == "US":
        indexes = POKEMON_US_INDEXES
        path_pattern = r"^/us/(?:pokemon-tcg/product-gallery|(?:pokemon-)?news)/[a-z0-9][a-z0-9-]+/?$"
        parser = parse_pokemon_us
    else:
        return [], [f"Pokémon {region}: unsupported region"]

    rows, errors, links, seen = [], [], [], set()
    for index_url in indexes:
        try:
            raw = fetch(index_url)
            rows.extend(parser(html_to_text(raw), index_url))
        except (OSError, ValueError, TypeError, UnicodeError) as exc:
            errors.append(f"Pokémon {region} index: {type(exc).__name__}")
            continue
        for link in _official_detail_links(raw, index_url, path_pattern):
            if link not in seen:
                seen.add(link)
                links.append(link)
            if len(links) >= MAX_DETAIL_PAGES_PER_REGION:
                break
        if len(links) >= MAX_DETAIL_PAGES_PER_REGION:
            break

    for url in links[:MAX_DETAIL_PAGES_PER_REGION]:
        try:
            rows.extend(parser(html_to_text(fetch(url)), url))
        except (OSError, ValueError, TypeError, UnicodeError) as exc:
            errors.append(f"Pokémon {region} detail: {type(exc).__name__}")
    return _dedupe(rows), errors


def pokemon_other_regions(fetch, html_to_text):
    rows, errors = [], []
    for region in ("KR", "US"):
        found, found_errors = _collect_pokemon_region_details(fetch, html_to_text, region)
        rows.extend(found)
        errors.extend(found_errors)
    return _dedupe(rows, MAX_ROWS_PER_SOURCE * 2), errors


def onepiece_all_regions(collect_kr, collect_jp, collect_us):
    rows, errors = [], []
    for label, collector in (
        ("ONE PIECE KR", collect_kr),
        ("ONE PIECE JP", collect_jp),
        ("ONE PIECE US", collect_us),
    ):
        try:
            rows.extend(row for row in (collector() or []) if isinstance(row, dict))
        except (OSError, ValueError, TypeError, UnicodeError) as exc:
            errors.append(f"{label}: {type(exc).__name__}")
    return _dedupe(rows, MAX_ROWS_PER_SOURCE * 3), errors


def parse_naruto_region(text, region, source=None):
    """Promote only release claims supported by the relevant regional evidence."""
    if region not in NARUTO_REGION_SOURCES:
        return []
    source = source or NARUTO_REGION_SOURCES[region]
    value = _bounded_text(text)
    if not re.search(
        r"GLOBAL\s+RELEASE\s+CONFIRMED|simultaneous\s+global\s+release|"
        r"全世界同時(?:リリース|発売)|Scheduled\s+Release|発売",
        value,
        re.I,
    ):
        return []
    # Asia-English is a watch source, not Korea proof by itself.
    if region == "KR" and not re.search(r"South\s+Korea|Korea|대한민국|한국|韓国", value, re.I):
        return []

    match = re.search(
        r"(?:Arriving\s+in\s+)?(Spring|Summer|Fall|Autumn|Winter)\s+(20\d{2})",
        value,
        re.I,
    )
    if match:
        season = {
            "spring": "봄",
            "summer": "여름",
            "fall": "가을",
            "autumn": "가을",
            "winter": "겨울",
        }[match.group(1).lower()]
        year = int(match.group(2))
    else:
        jp = re.search(r"(20\d{2})年\s*(春|夏|秋|冬).{0,100}?(?:発売|リリース)", value)
        if not jp:
            return []
        year = int(jp.group(1))
        season = {"春": "봄", "夏": "여름", "秋": "가을", "冬": "겨울"}[jp.group(2)]

    return [{
        "game": "NARUTO",
        "region": region,
        "name": "NARUTO CARD GAME",
        "release_date": None,
        "release_window": f"{year}년 {season}",
        "release_precision": "season",
        "release_label": f"{year}년 {season}",
        "price": "가격·제품 구성 미정",
        "status": "지역 공식 페이지 출시 확인",
        "source": source,
    }]


def naruto_all_regions(fetch, html_to_text, collect_naruto=None):
    rows, errors = [], []
    for region, url in NARUTO_REGION_SOURCES.items():
        try:
            rows.extend(parse_naruto_region(html_to_text(fetch(url)), region, url))
        except (OSError, ValueError, TypeError, UnicodeError) as exc:
            errors.append(f"NARUTO {region}: {type(exc).__name__}")
    # Keep old GLOBAL evidence for backwards compatibility, but GLOBAL never
    # satisfies a KR/JP/US matrix cell.
    if callable(collect_naruto):
        try:
            rows.extend(row for row in (collect_naruto() or []) if isinstance(row, dict))
        except (OSError, ValueError, TypeError, UnicodeError) as exc:
            errors.append(f"NARUTO GLOBAL: {type(exc).__name__}")
    return _dedupe(rows, MAX_ROWS_PER_SOURCE * 4), errors


def coverage_progress(items):
    counts = {f"{game}/{region}": 0 for game, region in EXPECTED_CELLS}
    for row in items or []:
        if not isinstance(row, dict):
            continue
        key = f"{row.get('game')}/{row.get('region')}"
        if key in counts:
            counts[key] += 1
    return {
        "expected_cells": len(EXPECTED_CELLS),
        "configured_cells": len(EXPECTED_CELLS),
        "verified_cells": sum(1 for count in counts.values() if count > 0),
        "missing_verified_cells": [key for key, count in counts.items() if count == 0],
        "cells": {
            key: {"configured": True, "verified_rows": count}
            for key, count in counts.items()
        },
        "matrix_policy": "3게임×KR/JP/US 공식출처만 확인 · 미발표 날짜 임의 생성 금지",
    }


def run(fetch, html_to_text, collect_onepiece_kr, collect_onepiece_jp, collect_onepiece_us, collect_naruto):
    items, errors = [], []

    rows, found_errors = pokemon_jp_years(fetch, html_to_text)
    items.extend(rows); errors.extend(found_errors)
    rows, found_errors = pokemon_other_regions(fetch, html_to_text)
    items.extend(rows); errors.extend(found_errors)
    rows, found_errors = onepiece_all_regions(collect_onepiece_kr, collect_onepiece_jp, collect_onepiece_us)
    items.extend(rows); errors.extend(found_errors)
    rows, found_errors = naruto_all_regions(fetch, html_to_text, collect_naruto)
    items.extend(rows); errors.extend(found_errors)

    items = _dedupe(items, MAX_TOTAL_ROWS)
    state = _load_state()
    matrix = coverage_progress(items)
    state["coverage_matrix"] = matrix
    state["last_matrix_run"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    _save_state(state)
    return {
        "items": items,
        "errors": errors[:60],
        "progress": state,
        "coverage": matrix,
        "policy": (
            "Pokémon/ONE PIECE/NARUTO 3게임×KR/JP/US 동일 append-only 누적정책 · "
            "공식출처만 반영 · 일/월/계절 정확도 보존 · 실패 시 기존 이력 보존"
        ),
    }
