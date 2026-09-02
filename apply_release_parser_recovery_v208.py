#!/usr/bin/env python3
from pathlib import Path
import re

p = Path("update_releases.py")
s = p.read_text(encoding="utf-8")

old_import = "from safe_runtime import atomic_write_json, diagnostic_exception, env_int, html_to_text, safe_read_text, safe_urlopen\n"
learning_import = "from release_parser_learning import fingerprint_text, public_summary as parser_public_summary, record_attempt as record_parser_attempt, strategy_order as parser_strategy_order\n"
if learning_import not in s:
    if old_import not in s:
        raise SystemExit("safe_runtime import marker missing")
    s = s.replace(old_import, old_import + learning_import, 1)

constants = '''POKEMON_JP_PRODUCT_URLS = (\n    "https://www.pokemon-card.com/products/",\n    "https://www.pokemon-card.com/products/index.html?productType=expansion",\n)\n'''
extended = constants + '''POKEMON_JP_SOURCE_PAGE = "https://www.pokemon-card.com/products/index.html?productType=expansion"\nPOKEMON_JP_RESULT_API = "https://www.pokemon-card.com/products/resultAPI.php"\nPARSER_MEMORY = ROOT / "release_parser_learning.json"\nPOKEMON_JP_STRATEGIES = ("html_chain_v1", "official_result_api_v1")\nPARSER_RUN_EVENTS: list[dict] = []\n'''
if "POKEMON_JP_RESULT_API" not in s:
    if constants not in s:
        raise SystemExit("Pokemon constants marker missing")
    s = s.replace(constants, extended, 1)

fetch_marker = "def iso_en(value: str) -> str:\n"
fetch_json = '''def fetch_json(url: str) -> tuple[dict, str]:
    """Fetch bounded JSON only from the same official allowlist used by HTML collectors."""
    host = urllib.parse.urlparse(url).hostname
    if host not in ALLOWED:
        raise ValueError(f"unapproved host: {host}")
    headers = dict(HEADERS)
    headers["Accept"] = "application/json,text/plain,*/*"
    headers["Referer"] = POKEMON_JP_SOURCE_PAGE
    req = urllib.request.Request(url, headers=headers)
    with safe_urlopen(req, timeout=env_int("TCG_HTTP_TIMEOUT", 20, 5, 60), allowed_hosts=ALLOWED) as response:
        content_type = str(response.headers.get("Content-Type", "")).lower()
        raw = response.read(2_000_000).decode("utf-8", "replace")
    if "json" not in content_type and not raw.lstrip().startswith(("{", "[")):
        raise ValueError("official product API returned non-JSON content")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("official product API root is not an object")
    return data, raw


'''
if "def fetch_json(" not in s:
    if fetch_marker not in s:
        raise SystemExit("iso_en marker missing")
    s = s.replace(fetch_marker, fetch_json + fetch_marker, 1)

pattern = re.compile(r"def collect_pokemon_jp\(\) -> list\[dict\]:\n.*?\n\ndef collect_naruto", re.S)
replacement = '''def _clean_pokemon_jp_api_title(value: str) -> str:
    title = re.sub(r"\\s+", " ", str(value or "")).strip()
    title = re.sub(
        r"^(?:強化拡張パック|拡張パックデラックス|拡張パック|ハイクラスパック|コンセプトパック)\\s*",
        "", title, flags=re.I,
    ).strip()
    return title.strip().strip('「」『』"')


def _parse_pokemon_jp_api_payload(data: dict, *, transport_url: str) -> list[dict]:
    """Validate the official dynamic result API before any row is promoted."""
    if not isinstance(data, dict) or data.get("result") != 1:
        raise ValueError("official product API reported failure")
    products = data.get("products")
    if not isinstance(products, list) or len(products) > 60:
        raise ValueError("official product API products shape invalid")
    try:
        hit_count = int(data.get("hitCnt", len(products)) or 0)
        max_page = int(data.get("maxPage", 1) or 1)
        this_page = int(data.get("thisPage", 1) or 1)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("official product API pagination invalid") from exc
    if not (0 <= hit_count <= 10_000 and 0 <= max_page <= 100 and 0 <= this_page <= max(100, max_page)):
        raise ValueError("official product API pagination out of bounds")
    found: list[dict] = []
    seen: set[tuple[str, str, int]] = set()
    date_re = re.compile(r"(20\\d{2})\\s*年\\s*(\\d{1,2})\\s*月\\s*(\\d{1,2})\\s*日")
    price_re = re.compile(r"([0-9][0-9,]{0,8})\\s*円")
    for product in products:
        if not isinstance(product, dict):
            continue
        if str(product.get("productType", "")).strip() != "拡張パック":
            continue
        name = _clean_pokemon_jp_api_title(product.get("productTitle", ""))
        dm = date_re.search(str(product.get("releaseDate", "")))
        pm = price_re.search(str(product.get("priceTxt", "")))
        if not (2 <= len(name) <= 140 and dm and pm):
            continue
        try:
            date = dt.date(int(dm.group(1)), int(dm.group(2)), int(dm.group(3)))
            price = int(pm.group(1).replace(",", ""))
        except (TypeError, ValueError, OverflowError):
            continue
        max_date = dt.date.today().replace(year=dt.date.today().year + MAX_FUTURE_YEARS)
        if not (MIN_RELEASE_DATE <= date <= max_date and 1 <= price <= 1_000_000):
            continue
        key = (name.casefold(), date.isoformat(), price)
        if key in seen:
            continue
        seen.add(key)
        found.append({
            "game": "Pokémon", "region": "JP", "name": name,
            "release_date": date.isoformat(), "price": f"¥{price:,}/팩",
            "status": "공식 확인", "source": POKEMON_JP_SOURCE_PAGE,
            "parser": "official-result-api-v1", "transport_source": transport_url,
        })
    return found


def _collect_pokemon_jp_api() -> tuple[list[dict], str]:
    query = urllib.parse.urlencode({"productType": "expansion", "page": 1})
    url = f"{POKEMON_JP_RESULT_API}?{query}"
    data, raw = fetch_json(url)
    return _parse_pokemon_jp_api_payload(data, transport_url=url), fingerprint_text(raw)


def _collect_pokemon_jp_html() -> tuple[list[dict], str]:
    last_error: Exception | None = None
    fetched_official_page = False
    last_fingerprint = ""
    for url in POKEMON_JP_PRODUCT_URLS:
        try:
            raw = fetch(url)
            last_fingerprint = fingerprint_text(raw)
            text = html_to_text(raw)
            found = (
                _parse_pokemon_jp(text, url)
                or _parse_pokemon_jp_fallback(text, url)
                or _parse_pokemon_jp_segmented(text, url)
            )
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, UnicodeError) as exc:
            last_error = exc
            continue
        fetched_official_page = True
        if found:
            return found, last_fingerprint
    if fetched_official_page:
        return [], last_fingerprint
    if last_error is not None:
        raise last_error
    return [], last_fingerprint


def collect_pokemon_jp() -> list[dict]:
    """Recover parser drift using only verified, hard-coded source strategies."""
    strategies = {
        "html_chain_v1": _collect_pokemon_jp_html,
        "official_result_api_v1": _collect_pokemon_jp_api,
    }
    order = parser_strategy_order(PARSER_MEMORY, "Pokémon JP", strategies.keys(), POKEMON_JP_STRATEGIES)
    attempted_failure = False
    for strategy_id in order:
        collector = strategies.get(strategy_id)
        if collector is None:
            continue
        try:
            rows, fingerprint = collector()
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, UnicodeError, json.JSONDecodeError):
            attempted_failure = True
            record_parser_attempt(
                PARSER_MEMORY, "Pokémon JP", strategy_id, allowed_strategies=strategies.keys(),
                success=False, row_count=0, outcome="transport_or_parse_error",
            )
            PARSER_RUN_EVENTS.append({"source": "Pokémon JP", "strategy": strategy_id, "outcome": "failed", "rows": 0})
            continue
        if rows:
            recovered = attempted_failure
            record_parser_attempt(
                PARSER_MEMORY, "Pokémon JP", strategy_id, allowed_strategies=strategies.keys(),
                success=True, row_count=len(rows), outcome="recovered" if recovered else "success",
                fingerprint=fingerprint,
            )
            PARSER_RUN_EVENTS.append({
                "source": "Pokémon JP", "strategy": strategy_id,
                "outcome": "recovered" if recovered else "success", "rows": len(rows),
            })
            return rows
        attempted_failure = True
        record_parser_attempt(
            PARSER_MEMORY, "Pokémon JP", strategy_id, allowed_strategies=strategies.keys(),
            success=False, row_count=0, outcome="zero_verified_rows", fingerprint=fingerprint,
        )
        PARSER_RUN_EVENTS.append({
            "source": "Pokémon JP", "strategy": strategy_id,
            "outcome": "zero_verified_rows", "rows": 0,
        })
    return []


def collect_naruto'''
if not pattern.search(s):
    raise SystemExit("collect_pokemon_jp block not found")
s = pattern.sub(lambda _m: replacement, s, count=1)

s = s.replace(
    'parser_drift_warnings.append(f"{label}: 공식 페이지 0건 · 기존 검증 이력 유지 · 다음 실행에서 재파싱")',
    'parser_drift_warnings.append(f"{label}: 모든 검증 파서·전송전략 0건 · 기존 검증 이력 유지 · 자동복구 미해결")',
)
s = s.replace(
    'current["collection_status"] = "정상 · 기존 검증자료 유지 · 파서 드리프트 자가복구 대기"',
    'current["collection_status"] = "일부 파서 자동복구 미해결 · 기존 검증자료 보존"',
)

write_marker = '''    current["history_count"] = len(current["items"])
    atomic_write_json(DATA,current,suffix=".json.tmp")
'''
write_new = '''    current["history_count"] = len(current["items"])
    current["parser_recovery_events"] = PARSER_RUN_EVENTS[-20:]
    current["parser_learning"] = parser_public_summary(
        PARSER_MEMORY, {"Pokémon JP": POKEMON_JP_STRATEGIES}
    )
    atomic_write_json(DATA,current,suffix=".json.tmp")
'''
if 'current["parser_recovery_events"]' not in s:
    if write_marker not in s:
        raise SystemExit("write marker missing")
    s = s.replace(write_marker, write_new, 1)

p.write_text(s, encoding="utf-8")
print("patched update_releases.py")
