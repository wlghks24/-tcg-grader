#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unified append-only official release-history backfill for Pokémon / ONE PIECE / NARUTO.

The backfill is incremental and fail-closed:
- Pokémon, ONE PIECE and NARUTO expose the same KR / JP / US coverage matrix.
- Only hard-coded official sources and caller-supplied official collectors are used.
- Exact dates are preserved; month/season announcements never invent a day.
- A missing or failed source never deletes previously verified history.
- A global announcement never becomes a KR/JP/US row unless the relevant regional
  official page (or explicit country wording) supports that regional claim.
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
MAX_ROWS_PER_SOURCE = 160
MAX_TOTAL_ROWS = 600
MAX_DETAIL_PAGES_PER_REGION = 18
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
    # Korea does not currently have a dedicated locale in the region selector.
    # Keep Asia-English as a watch source, but parse_pokemon/naruto rules below
    # require explicit Korea wording before this cell can be marked verified.
    "KR": "https://www.naruto-cardgame.com/asia-en/",
    "JP": "https://www.naruto-cardgame.com/jp/",
    "US": "https://www.naruto-cardgame.com/en/",
}


def _load_state():
    try:
        data = json.loads(safe_read_text(STATE, max_bytes=500_000))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError, UnicodeError):
        return {}


def _save_state(data):
    atomic_write_json(STATE, data if isinstance(data, dict) else {}, suffix=".release-history.tmp")


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
    clean = _norm(value)
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return dt.datetime.strptime(clean, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _dedupe(rows, limit=MAX_ROWS_PER_SOURCE):
    out = []
    seen = set()
    safe_limit = max(1, min(MAX_TOTAL_ROWS, int(limit)))
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        key = (
            row.get("game"), row.get("region"), _norm(row.get("name")).casefold(),
            row.get("release_date"), row.get("release_window"), row.get("source"),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= safe_limit:
            break
    return out


def _official_detail_links(raw, base_url, path_pattern, limit=MAX_DETAIL_PAGES_PER_REGION):
    """Extract bounded same-host HTTPS detail links from an official index page."""
    try:
        base = urllib.parse.urlsplit(base_url)
    except ValueError:
        return []
    base_host = (base.hostname or "").lower()
    if not base_host:
        return []
    out, seen = [], set()
    for href in re.findall(r"href\s*=\s*[\"']([^\"']+)[\"']", str(raw or ""), re.I)[:2500]:
        target = urllib.parse.urljoin(base_url, html.unescape(href)).split("#", 1)[0]
        try:
            parsed = urllib.parse.urlsplit(target)
        except ValueError:
            continue
        if parsed.scheme != "https" or (parsed.hostname or "").lower() != base_host:
            continue
        if not re.search(path_pattern, parsed.path, re.I):
            continue
        canonical = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))
        if canonical in seen:
            continue
        seen.add(canonical)
        out.append(canonical)
        if len(out) >= max(1, min(40, int(limit))):
            break
    return out


def pokemon_jp_years(fetch, html_to_text, years_per_run=2):
    """Backfill Japanese Pokémon expansion/high-class product archive from 1996 onward."""
    state = _load_state()
    cur = _today().year
    try:
        next_year = int(state.get("pokemon_jp_next_year") or cur)
    except (TypeError, ValueError, OverflowError):
        next_year = cur
    next_year = max(1996, min(cur, next_year))
    safe_years = max(1, min(5, int(years_per_run)))
    years = [cur]
    year = next_year
    while len(years) < safe_years + 1 and year >= 1996:
        if year not in years:
            years.append(year)
        year -= 1
    out, errors = [], []
    pattern = re.compile(
        r"(?:拡張パック|強化拡張パック|ハイクラスパック|コンセプトパック|再販パック)\s*[「『]?(.{2,80}?)[」』]?\s*"
        r".{0,180}?(?:発売日|販売日)\s*(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日"
        r"(?:.{0,220}?(?:希望小売価格|価格)\s*([0-9,]+)円)?", re.I,
    )
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
            out.append({
                "game": "Pokémon", "region": "JP", "name": _norm(name),
                "release_date": release_date,
                "price": f"¥{price}/팩" if price else "공식 가격 확인",
                "status": "공식 과거출시 확인", "source": url,
                "archive_year": archive_year,
            })
    if next_year >= 1996:
        state["pokemon_jp_next_year"] = max(1995, next_year - safe_years)
    state["pokemon_jp_last_run"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    _save_state(state)
    return _dedupe(out), errors


def _pokemon_kr_row(title, source, *, release_date=None, year=None, month=None, price=None):
    base = {
        "game": "Pokémon", "region": "KR", "name": _norm(title)[:180],
        "price": f"₩{int(str(price).replace(',', '')):,}" if price else "공식 가격 확인",
        "source": source,
    }
    if release_date:
        base.update({"release_date": release_date, "status": "공식 출시 확인"})
        return base
    try:
        y, m = int(year), int(month)
        if not (1996 <= y <= _today().year + 5 and 1 <= m <= 12):
            return None
    except (TypeError, ValueError, OverflowError):
        return None
    base.update({
        "release_date": None, "release_window": f"{y:04d}-{m:02d}",
        "release_precision": "month", "release_label": f"{y}년 {m}월",
        "status": "공식 출시월 확인",
    })
    return base


def parse_pokemon_kr(text, source=POKEMON_REGION_SOURCES["KR"]):
    """Parse only explicit Korean Pokémon product release statements."""
    value = _bounded_text(text)
    rows = []
    product = r"(?:MEGA|스칼렛&바이올렛|소드&실드|썬&문|포켓몬\s*카드\s*게임)?\s*(?:강화\s*)?(?:확장팩|하이클래스팩|스페셜\s*팩|스타터(?:\s*세트|\s*덱)?|구축덱)"
    title = rf"(?P<title>{product}\s*.{{0,45}}?[「『][^」』]{{2,80}}[」』])"
    price_tail = r"(?:.{0,100}?(?:가격|판매가격)\s*(?P<price>[0-9][0-9,]{0,8})\s*원)?"
    patterns = (
        re.compile(title + r".{0,140}?(?:발매일|출시일)\s*(?P<y>20\d{2})[-./](?P<m>\d{1,2})[-./](?P<d>\d{1,2})" + price_tail, re.I),
        re.compile(title + r".{0,120}?(?P<y>20\d{2})년\s*(?P<m>\d{1,2})월\s*(?P<d>\d{1,2})일.{0,55}?(?:출시|발매|판매\s*시작|정식\s*발매)" + price_tail, re.I),
        re.compile(title + r".{0,120}?(?:출시|발매|판매\s*시작|정식\s*발매).{0,55}?(?P<y>20\d{2})년\s*(?P<m>\d{1,2})월\s*(?P<d>\d{1,2})일" + price_tail, re.I),
    )
    for pattern in patterns:
        for match in pattern.finditer(value):
            release_date = _safe_date(match.group("y"), match.group("m"), match.group("d"))
            if not release_date:
                continue
            row = _pokemon_kr_row(
                match.group("title"), source, release_date=release_date,
                price=match.groupdict().get("price"),
            )
            if row:
                rows.append(row)
    month_patterns = (
        re.compile(title + r".{0,120}?(?P<y>20\d{2})년\s*(?P<m>\d{1,2})월(?!\s*\d{1,2}일).{0,55}?(?:출시|발매|판매\s*예정|발매\s*예정)", re.I),
        re.compile(title + r".{0,120}?(?:출시|발매|판매\s*예정|발매\s*예정).{0,55}?(?P<y>20\d{2})년\s*(?P<m>\d{1,2})월(?!\s*\d{1,2}일)", re.I),
    )
    for pattern in month_patterns:
        for match in pattern.finditer(value):
            row = _pokemon_kr_row(match.group("title"), source, year=match.group("y"), month=match.group("m"))
            if row:
                rows.append(row)
    return _dedupe(rows)


def parse_pokemon_us(text, source=POKEMON_REGION_SOURCES["US"]):
    """Parse Pokemon.com product/news text only when Launch/Release wording is explicit."""
    value = _bounded_text(text)
    rows = []
    title_re = r"(?P<title>Pok[eé]mon\s+TCG(?::|\s)[^\n]{2,150}?)"
    exact_patterns = (
        re.compile(title_re + r".{0,180}?(?:Launch|Release\s+Date|releasing|arriving)\s*:?\s*(?P<date>[A-Z][a-z]+\s+\d{1,2},\s*20\d{2})", re.I),
        re.compile(title_re + r".{0,180}?(?P<date>[A-Z][a-z]+\s+\d{1,2},\s*20\d{2}).{0,70}?(?:launch|release|releasing|arriving)", re.I),
    )
    for pattern in exact_patterns:
        for match in pattern.finditer(value):
            release_date = _parse_english_date(match.group("date"))
            if not release_date:
                continue
            title = _norm(match.group("title"))
            title = re.split(r"\s+(?:Launch|Release\s+Date|releasing|arriving)\b", title, maxsplit=1, flags=re.I)[0]
            rows.append({
                "game": "Pokémon", "region": "US", "name": title[:180],
                "release_date": release_date, "price": "official price check",
                "status": "official release verified", "source": source,
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
    rows, errors, detail_links = [], [], []
    seen_links = set()
    for index_url in indexes:
        try:
            raw = fetch(index_url)
        except (OSError, ValueError, TypeError, UnicodeError) as exc:
            errors.append(f"Pokémon {region} index: {type(exc).__name__}")
            continue
        rows.extend(parser(html_to_text(raw), index_url))
        for link in _official_detail_links(raw, index_url, path_pattern, MAX_DETAIL_PAGES_PER_REGION):
            if link not in seen_links:
                detail_links.append(link)
                seen_links.add(link)
            if len(detail_links) >= MAX_DETAIL_PAGES_PER_REGION:
                break
        if len(detail_links) >= MAX_DETAIL_PAGES_PER_REGION:
            break
    for url in detail_links[:MAX_DETAIL_PAGES_PER_REGION]:
        try:
            rows.extend(parser(html_to_text(fetch(url)), url))
        except (OSError, ValueError, TypeError, UnicodeError) as exc:
            errors.append(f"Pokémon {region} detail: {type(exc).__name__}")
    return _dedupe(rows), errors


def pokemon_other_regions(fetch, html_to_text):
    out, errors = [], []
    for region in ("KR", "US"):
        rows, found_errors = _collect_pokemon_region_details(fetch, html_to_text, region)
        out.extend(rows)
        errors.extend(found_errors)
    return _dedupe(out, MAX_ROWS_PER_SOURCE * 2), errors


def onepiece_all_regions(collect_kr, collect_jp, collect_us):
    out, errors = [], []
    for label, fn in (
        ("ONE PIECE KR", collect_kr), ("ONE PIECE JP", collect_jp), ("ONE PIECE US", collect_us),
    ):
        try:
            for row in fn() or []:
                if isinstance(row, dict):
                    out.append(row)
        except (OSError, ValueError, TypeError, UnicodeError) as exc:
            errors.append(f"{label}: {type(exc).__name__}")
    return _dedupe(out, MAX_ROWS_PER_SOURCE * 3), errors


def parse_naruto_region(text, region, source=None):
    """Create a regional row only when the regional official evidence is sufficient."""
    if region not in NARUTO_REGION_SOURCES:
        return []
    source = source or NARUTO_REGION_SOURCES[region]
    value = _bounded_text(text)
    release_confirmed = bool(re.search(
        r"GLOBAL\s+RELEASE\s+CONFIRMED|simultaneous\s+global\s+release|全世界同時(?:リリース|発売)|Scheduled\s+Release|発売",
        value, re.I,
    ))
    if not release_confirmed:
        return []
    # The Asia-English page is a watch source for Korea, not proof by itself.
    # Do not turn a generic global announcement into a Korean release claim.
    if region == "KR" and not re.search(r"South\s+Korea|Korea|대한민국|한국|韓国", value, re.I):
        return []
    season = re.search(r"(?:Arriving\s+in\s+)?(Spring|Summer|Fall|Autumn|Winter)\s+(20\d{2})", value, re.I)
    if season:
        season_ko = {
            "spring": "봄", "summer": "여름", "fall": "가을",
            "autumn": "가을", "winter": "겨울",
        }[season.group(1).lower()]
        year = int(season.group(2))
    else:
        jp = re.search(r"(20\d{2})年\s*(春|夏|秋|冬).{0,100}?(?:発売|リリース)", value)
        if not jp:
            return []
        season_ko = {"春": "봄", "夏": "여름", "秋": "가을", "冬": "겨울"}[jp.group(2)]
        year = int(jp.group(1))
    return [{
        "game": "NARUTO", "region": region, "name": "NARUTO CARD GAME",
        "release_date": None, "release_window": f"{year}년 {season_ko}",
        "release_precision": "season", "release_label": f"{year}년 {season_ko}",
        "price": "가격·제품 구성 미정", "status": "지역 공식 페이지 출시 확인",
        "source": source,
    }]


def naruto_all_regions(fetch, html_to_text, collect_naruto=None):
    out, errors = [], []
    for region, url in NARUTO_REGION_SOURCES.items():
        try:
            out.extend(parse_naruto_region(html_to_text(fetch(url)), region, url))
        except (OSError, ValueError, TypeError, UnicodeError) as exc:
            errors.append(f"NARUTO {region}: {type(exc).__name__}")
    # Retain the previous GLOBAL collector for compatibility/history evidence. It
    # never satisfies one of the required KR/JP/US coverage cells.
    if callable(collect_naruto):
        try:
            for row in collect_naruto() or []:
                if isinstance(row, dict):
                    out.append(row)
        except (OSError, ValueError, TypeError, UnicodeError) as exc:
            errors.append(f"NARUTO GLOBAL: {type(exc).__name__}")
    return _dedupe(out, MAX_ROWS_PER_SOURCE * 4), errors


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
        "cells": {key: {"configured": True, "verified_rows": count} for key, count in counts.items()},
        "matrix_policy": "3게임×KR/JP/US 공식출처만 확인 · 미발표 날짜 임의 생성 금지",
    }


def run(fetch, html_to_text, collect_onepiece_kr, collect_onepiece_jp, collect_onepiece_us, collect_naruto):
    items, errors = [], []

    rows, found_errors = pokemon_jp_years(fetch, html_to_text)
    items += rows; errors += found_errors
    rows, found_errors = pokemon_other_regions(fetch, html_to_text)
    items += rows; errors += found_errors
    rows, found_errors = onepiece_all_regions(collect_onepiece_kr, collect_onepiece_jp, collect_onepiece_us)
    items += rows; errors += found_errors
    rows, found_errors = naruto_all_regions(fetch, html_to_text, collect_naruto)
    items += rows; errors += found_errors

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
