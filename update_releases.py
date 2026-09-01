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
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.7",
    "Accept-Language": "ko-KR,ko;q=0.9,ja-JP;q=0.8,en;q=0.6",
}
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
POKEMON_JP_PRODUCT_URLS = (
    "https://www.pokemon-card.com/products/",
    "https://www.pokemon-card.com/products/index.html?productType=expansion",
)
ONEPIECE_JP_PRODUCT_URLS = (
    "https://www.onepiece-cardgame.com/products/?subcategory=boosters",
    "https://www.onepiece-cardgame.com/products/",
)


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


def _parse_onepiece_jp(text: str, url: str) -> list[dict]:
    pattern = re.compile(
        r"(?:ブースター\s+)?(?:ブースターパック|エクストラブースター|プレミアムブースター)\s*"
        r"(.{2,90}?)\s*[〖【](OP-\d+|EB-\d+|PRB-\d+)[〗】]\s*"
        r"発売日\s*(20\d{2})\s*[./年]\s*(\d{1,2})"
        r"(?:\s*[./月]\s*(\d{1,2})\s*日?)?(?:\([^)]*\))?\s*"
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


def _parse_onepiece_jp_fallback(text: str, url: str) -> list[dict]:
    pattern = re.compile(
        r"(?:ブースター\s+)?(?:ブースターパック|エクストラブースター|プレミアムブースター)\s+"
        r"(.{2,100}?)\s*[〖【](OP-\d+|EB-\d+|PRB-\d+)[〗】]"
        r".{0,120}?発売日\s*(20\d{2})\s*[./年]\s*(\d{1,2})"
        r"(?:\s*[./月]\s*(\d{1,2}))?.{0,160}?メーカー希望小売価格\s*([0-9,]+)\s*円",
        re.I | re.S,
    )
    found=[]
    for title,code,y,m,d,price in pattern.findall(text):
        row={"game":"ONE PIECE","region":"JP","name":f"{re.sub(r'\s+',' ',title).strip()} [{code}]",
             "price":f"¥{price}/팩","status":"공식 확인","source":url}
        if d:
            row["release_date"]=dt.date(int(y),int(m),int(d)).isoformat()
        else:
            row.update({"release_date":None,"release_window":f"{int(y):04d}-{int(m):02d}",
                        "release_precision":"month","release_label":f"{int(y):04d}년 {int(m)}월"})
        found.append(row)
    return found



def _parse_onepiece_jp_segmented(text: str, url: str) -> list[dict]:
    """Parse current/future JP product cards without depending on one DOM text order.

    Official pages have changed spacing, punctuation and label order several times.
    Anchor on the stable product code, then read only a bounded neighborhood for
    発売日 and the manufacturer price. This is a conservative third parser: a row
    is emitted only when code + date/month + JPY price are all present together.
    """
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    found = []
    seen = set()
    code_re = re.compile(r"\b(OP-\d+|EB-\d+|PRB-\d+)\b", re.I)
    date_re = re.compile(
        r"発売日.{0,90}?(20\d{2})\s*(?:[./年-])\s*(\d{1,2})"
        r"(?:\s*(?:[./月-])\s*(\d{1,2})\s*日?)?",
        re.I,
    )
    price_re = re.compile(r"(?:メーカー希望小売価格|希望小売価格|価格).{0,100}?([0-9][0-9,]{1,7})\s*円", re.I)
    product_words = re.compile(r"(?:ブースターパック|エクストラブースター|プレミアムブースター|ブースター)", re.I)
    for match in code_re.finditer(normalized):
        code = match.group(1).upper()
        left = max(0, match.start() - 180)
        right = min(len(normalized), match.end() + 520)
        segment = normalized[left:right]
        dm = date_re.search(segment)
        pm = price_re.search(segment)
        if not dm or not pm:
            continue
        y, m, d = dm.groups()
        try:
            year, month = int(y), int(m)
            day = int(d) if d else None
            price = int(pm.group(1).replace(",", ""))
            if not (1 <= month <= 12 and 1 <= price <= 1_000_000):
                continue
            if day is not None:
                dt.date(year, month, day)
        except (TypeError, ValueError):
            continue
        before = normalized[max(left, match.start() - 150):match.start()]
        words = list(product_words.finditer(before))
        title_start = words[-1].start() if words else max(0, len(before) - 100)
        title = re.sub(r"\s+", " ", before[title_start:]).strip(" -|:：/・")
        title = product_words.sub("", title, count=1).strip(" -|:：/・")
        if len(title) < 2:
            title = f"ONE PIECE {code}"
        key = (code, year, month, day, price)
        if key in seen:
            continue
        seen.add(key)
        row = {"game": "ONE PIECE", "region": "JP", "name": f"{title} [{code}]",
               "price": f"¥{price:,}/팩", "status": "공식 확인", "source": url,
               "parser": "segmented-code-date-price-v111"}
        if day is None:
            row.update({"release_date": None, "release_window": f"{year:04d}-{month:02d}",
                        "release_precision": "month", "release_label": f"{year:04d}년 {month}월"})
        else:
            row["release_date"] = dt.date(year, month, day).isoformat()
        found.append(row)
    return found

def collect_onepiece_jp() -> list[dict]:
    last_error: Exception | None = None
    fetched_official_page = False
    for url in ONEPIECE_JP_PRODUCT_URLS:
        try:
            text = html_to_text(fetch(url)); found = (_parse_onepiece_jp(text, url) or _parse_onepiece_jp_fallback(text, url) or _parse_onepiece_jp_segmented(text, url))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, UnicodeError) as exc:
            last_error = exc
            continue
        fetched_official_page = True
        if found:
            return found
    if fetched_official_page:
        return []
    if last_error is not None:
        raise last_error
    return []


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


def _parse_pokemon_jp(text: str, url: str) -> list[dict]:
    pattern = re.compile(
        r"(?:強化拡張パック|拡張パック|ハイクラスパック|コンセプトパック)\s*"
        r"[「『]?\s*(.{2,70}?)\s*[」』]?\s*"
        r"(?:強化拡張パック|拡張パック|ハイクラスパック)?\s*(?:販売日|発売日)\s*"
        r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"
        r".{0,180}?希望小売価格\s*([0-9,]+)\s*円",
        re.I,
    )
    found = []
    for name, y, m, d, price in pattern.findall(text):
        date = dt.date(int(y), int(m), int(d)).isoformat()
        found.append({"game":"Pokémon","region":"JP","name":name.strip(),"release_date":date,"price":f"¥{price}/팩","status":"공식 확인","source":url})
    return found


def _parse_pokemon_jp_fallback(text: str, url: str) -> list[dict]:
    pattern = re.compile(
        r"(?:強化拡張パック|拡張パック|ハイクラスパック|コンセプトパック)\s*[「『]\s*([^」』]{2,70})[」』]"
        r".{0,140}?(?:販売日|発売日)\s*(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"
        r".{0,180}?希望小売価格\s*([0-9,]+)\s*円",
        re.I | re.S,
    )
    found=[]
    for name,y,m,d,price in pattern.findall(text):
        found.append({"game":"Pokémon","region":"JP","name":re.sub(r'\s+',' ',name).strip(),
                      "release_date":dt.date(int(y),int(m),int(d)).isoformat(),"price":f"¥{price}/팩",
                      "status":"공식 확인","source":url})
    return found



def _parse_pokemon_jp_segmented(text: str, url: str) -> list[dict]:
    """Conservative JP Pokémon parser resilient to whitespace/label-order drift."""
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    product_re = re.compile(r"(?:強化拡張パック|拡張パック|ハイクラスパック|コンセプトパック)", re.I)
    date_re = re.compile(
        r"(?:販売日|発売日).{0,90}?(20\d{2})\s*(?:年|[./-])\s*(\d{1,2})\s*(?:月|[./-])\s*(\d{1,2})\s*日?",
        re.I,
    )
    price_re = re.compile(r"(?:希望小売価格|メーカー希望小売価格|価格).{0,100}?([0-9][0-9,]{1,7})\s*円", re.I)
    found = []
    seen = set()
    for product in product_re.finditer(normalized):
        left = max(0, product.start() - 20)
        right = min(len(normalized), product.end() + 620)
        segment = normalized[left:right]
        dm = date_re.search(segment)
        pm = price_re.search(segment)
        if not dm or not pm:
            continue
        try:
            y, m, d = (int(value) for value in dm.groups())
            date = dt.date(y, m, d).isoformat()
            price = int(pm.group(1).replace(",", ""))
            if not (1 <= price <= 1_000_000):
                continue
        except (TypeError, ValueError):
            continue
        after = normalized[product.end():min(len(normalized), product.end() + 170)]
        quoted = re.search(r"[「『]\s*([^」』]{2,90})\s*[」』]", after)
        if quoted:
            name = re.sub(r"\s+", " ", quoted.group(1)).strip()
        else:
            stop = re.search(r"(?:販売日|発売日|希望小売価格|メーカー希望小売価格)", after)
            name = (after[:stop.start()] if stop else after[:100]).strip(" -|:：/・")
            name = re.sub(r"\s+", " ", name)
        if len(name) < 2:
            continue
        key = (name.casefold(), date, price)
        if key in seen:
            continue
        seen.add(key)
        found.append({"game": "Pokémon", "region": "JP", "name": name,
                      "release_date": date, "price": f"¥{price:,}/팩", "status": "공식 확인",
                      "source": url, "parser": "segmented-label-date-price-v111"})
    return found

def collect_pokemon_jp() -> list[dict]:
    last_error: Exception | None = None
    fetched_official_page = False
    for url in POKEMON_JP_PRODUCT_URLS:
        try:
            text = html_to_text(fetch(url)); found = (_parse_pokemon_jp(text, url) or _parse_pokemon_jp_fallback(text, url) or _parse_pokemon_jp_segmented(text, url))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, UnicodeError) as exc:
            last_error = exc
            continue
        fetched_official_page = True
        if found:
            return found
    if fetched_official_page:
        return []
    if last_error is not None:
        raise last_error
    return []


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
    parser_drift_warnings: list[str] = []
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
                    coverage_map={
                        'Pokémon JP':('Pokémon','JP'),'ONE PIECE KR':('ONE PIECE','KR'),
                        'ONE PIECE JP':('ONE PIECE','JP'),'ONE PIECE US':('ONE PIECE','US'),
                        'NARUTO Global':('NARUTO','GLOBAL'),
                    }
                    expected=coverage_map.get(label)
                    has_history=bool(expected and any(
                        isinstance(x,dict) and x.get('game')==expected[0] and x.get('region')==expected[1] and valid(x)
                        for x in current.get('items',[])
                    ))
                    if has_history:
                        parser_drift_warnings.append(f"{label}: 공식 페이지 0건 · 기존 검증 이력 유지 · 다음 실행에서 재파싱")
                        continue
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
    if errors:
        current["collection_status"] = "일부 출처 확인 실패 · 기존 전체 출시이력 보존"
    elif parser_drift_warnings:
        current["collection_status"] = "정상 · 기존 검증자료 유지 · 파서 드리프트 자가복구 대기"
    else:
        current["collection_status"] = "정상"
    current["collection_errors"] = errors
    current["parser_drift_warnings"] = parser_drift_warnings
    current["history_policy"] = "공식 확인된 과거 출시제품은 기간 제한 없이 누적 보존하며 네트워크 실패 시 삭제하지 않음"
    current["history_count"] = len(current["items"])
    atomic_write_json(DATA,current,suffix=".json.tmp")


if __name__ == "__main__":
    main()
