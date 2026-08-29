#!/usr/bin/env python3
"""Public social/search stock-signal discovery.

Safety rules
- Public search surfaces only. No Instagram/X login, session reuse, private API, or bypass.
- A social post is a *report*, never official realtime inventory by itself.
- Claimed quantities are preserved as claims; they are never promoted to confirmed stock.
- Device-local source learning changes search priority only; it can never change trust status.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from xml.etree import ElementTree as ET

from safe_runtime import atomic_write_json, env_int, safe_read_text, safe_urlopen, validate_public_https_url

ROOT = Path(__file__).resolve().parent
SOURCE_DB = ROOT / "social_stock_sources.json"
SIGNAL_DB = ROOT / "social_stock_signals.json"
PURCHASE_SIGNAL_DB = ROOT / "purchase_signals.json"
LEARNING_DB = ROOT / "social_stock_learning.json"

BING_HOSTS = {"www.bing.com", "bing.com"}
DDG_HOSTS = {"html.duckduckgo.com", "duckduckgo.com", "www.duckduckgo.com"}
PUBLIC_SOCIAL_HOSTS = {"www.instagram.com", "instagram.com", "x.com", "www.x.com", "twitter.com", "www.twitter.com"}
UA = "TCG-Grader-Social-Stock/1.0"
TIMEOUT = env_int("TCG_HTTP_TIMEOUT", 18, 5, 45)
MAX_RESULT_PER_SOURCE = 12
MAX_AGE_HOURS = 168

IN_TERMS = ("재고", "입고", "재입고", "판매중", "구매가능", "in stock", "restock", "available")
OUT_TERMS = ("품절", "매진", "sold out", "out of stock")
STOP_TERMS = ("스톱", "중단", "고장", "오류", "버그", "stop", "stopped", "error")
COMMON_QUERY_TERMS = {
    "포켓몬", "pokemon", "카드", "cards", "card", "tcg", "box", "박스", "팩", "pack",
    "재고", "입고", "판매", "구매", "한국", "kr",
}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _clean(value: object, limit: int = 500) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _norm(value: object) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", "", str(value or "").lower())


def _host(url: str) -> str:
    try:
        return (urllib.parse.urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def _safe_https(url: str) -> bool:
    try:
        validate_public_https_url(url)
        return True
    except (TypeError, ValueError):
        return False


def parse_quantity_claim(text: str) -> tuple[int | None, str | None]:
    """Return a claimed quantity without turning it into confirmed inventory."""
    cleaned = _clean(text).lower()
    patterns = (
        r"(\d{1,4})\s*(?:개|박스|box(?:es)?|팩|pack(?:s)?)\s*(이상|이상\s*재고|\+)",
        r"재고\s*(?:가|는|:)??\s*(\d{1,4})\s*(?:개|박스|box(?:es)?|팩|pack(?:s)?)",
    )
    m = re.search(patterns[0], cleaned, re.I)
    if m:
        return min(9999, int(m.group(1))), "at_least"
    m = re.search(patterns[1], cleaned, re.I)
    if m:
        return min(9999, int(m.group(1))), "reported"
    return None, None


def classify_status(text: str) -> tuple[str | None, str | None]:
    cleaned = _clean(text).lower()
    if any(term in cleaned for term in STOP_TERMS):
        return "operation_stop_report", "자판기·판매 운영중단 제보"
    if any(term in cleaned for term in OUT_TERMS):
        return "out_of_stock_report", "품절·매진 제보"
    if any(term in cleaned for term in IN_TERMS):
        return "in_stock_report", "재고·입고 제보"
    return None, None


def _parse_observed(value: object) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if len(text) == 10:
            return dt.datetime.fromisoformat(text + "T00:00:00+00:00")
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except ValueError:
        return None


def _age_hours(row: dict, now: dt.datetime | None = None) -> float:
    now = now or dt.datetime.now(dt.timezone.utc)
    observed = _parse_observed(row.get("observed_at") or row.get("collected_at"))
    if not observed:
        return 9999.0
    return max(0.0, (now - observed).total_seconds() / 3600.0)


def age_adjusted_score(row: dict, now: dt.datetime | None = None) -> tuple[int, bool]:
    """Decay social reports quickly; official lookup remains a separate system."""
    age = _age_hours(row, now)
    base = max(5, min(90, int(row.get("score") or 50)))
    ttl = max(6, min(72, int(row.get("ttl_hours") or 24)))
    if age <= ttl:
        return base, False
    if age <= ttl * 2:
        return max(25, base - 20), True
    if age <= MAX_AGE_HOURS:
        return max(10, base - 35), True
    return 5, True


def _decode_ddg_href(href: str) -> str | None:
    href = html.unescape(str(href or ""))
    if href.startswith("//"):
        href = "https:" + href
    if href.startswith("/"):
        href = "https://html.duckduckgo.com" + href
    try:
        parsed = urllib.parse.urlsplit(href)
    except ValueError:
        return None
    if (parsed.hostname or "").lower() in DDG_HOSTS:
        target = urllib.parse.parse_qs(parsed.query).get("uddg", [None])[0]
        if target:
            href = urllib.parse.unquote(target)
    return href if href.startswith("https://") else None


def _bing_rows(query: str) -> list[dict]:
    url = "https://www.bing.com/search?format=rss&q=" + urllib.parse.quote_plus(query)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml,text/xml;q=0.9,*/*;q=0.5"})
    with safe_urlopen(req, timeout=TIMEOUT, allowed_hosts=BING_HOSTS) as response:
        raw = response.read(600_000)
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("unsafe XML")
    root = ET.fromstring(raw)
    out = []
    for item in root.findall(".//item")[:20]:
        title = _clean(item.findtext("title"), 220)
        summary = _clean(item.findtext("description"), 360)
        link = str(item.findtext("link") or "").strip()
        if title and _safe_https(link):
            out.append({"title": title, "summary": summary, "url": link, "provider": "bing_rss"})
    return out


def _ddg_rows(query: str) -> list[dict]:
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with safe_urlopen(req, timeout=TIMEOUT, allowed_hosts=DDG_HOSTS) as response:
        raw = response.read(800_000).decode("utf-8", "replace")
    out = []
    for href, raw_title in re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', raw, re.I | re.S)[:20]:
        link = _decode_ddg_href(href)
        title = _clean(raw_title, 220)
        if link and title and _safe_https(link):
            out.append({"title": title, "summary": title, "url": link, "provider": "duckduckgo"})
    return out


def _load_json(path: Path, fallback: dict) -> dict:
    try:
        data = json.loads(safe_read_text(path))
        return data if isinstance(data, dict) else fallback
    except (OSError, ValueError, json.JSONDecodeError):
        return fallback


def _learning() -> dict:
    return _load_json(LEARNING_DB, {"version": 1, "updated_at": None, "sources": {}})


def _source_priority(source: dict, learning: dict) -> tuple[float, str]:
    row = learning.get("sources", {}).get(str(source.get("username")), {})
    runs = max(0, int(row.get("runs") or 0))
    accepted = max(0, int(row.get("accepted") or 0))
    errors = max(0, int(row.get("errors") or 0))
    score = (accepted + 1.0) / (runs + 2.0) - min(0.35, errors * 0.03)
    return (-score, str(source.get("username") or ""))


def _source_queries(source: dict) -> list[str]:
    username = str(source.get("username") or "").strip().lstrip("@")
    terms = [str(x).strip() for x in source.get("terms", []) if str(x).strip()][:8]
    term_expr = " OR ".join(terms) or "재고 OR 입고 OR 품절"
    platform = str(source.get("platform") or "instagram")
    host = "instagram.com" if platform == "instagram" else "x.com"
    return [
        f'"{username}" ({term_expr})',
        f'site:{host} "{username}" ({term_expr})',
    ]


def _row_matches_source(raw: dict, source: dict) -> bool:
    username = str(source.get("username") or "").lower().lstrip("@")
    url = str(raw.get("url") or "")
    text = f"{raw.get('title','')} {raw.get('summary','')} {url}".lower()
    host = _host(url)
    if username and username in text:
        return True
    profile = str(source.get("profile_url") or "").rstrip("/").lower()
    if profile and url.rstrip("/").lower().startswith(profile):
        return True
    return host in PUBLIC_SOCIAL_HOSTS and username and username.replace("_", "") in text.replace("_", "")


def _candidate_from_result(raw: dict, source: dict) -> dict | None:
    if not _row_matches_source(raw, source):
        return None
    text = f"{raw.get('title','')} {raw.get('summary','')}"
    status, status_label = classify_status(text)
    if not status:
        return None
    quantity, relation = parse_quantity_claim(text)
    profile = str(source.get("profile_url") or raw.get("url") or "")
    if not _safe_https(profile):
        return None
    score = 52
    if quantity is not None:
        score += 5
    if _host(str(raw.get("url") or "")) in PUBLIC_SOCIAL_HOSTS:
        score += 5
    row = {
        "id": f"auto-{source.get('username')}-{abs(hash((_norm(text), status))) % 10**10}",
        "game": source.get("game") or "Pokemon",
        "region": source.get("region") or "KR",
        "source_platform": source.get("platform") or "instagram",
        "source_username": source.get("username"),
        "source_url": str(raw.get("url") or profile),
        "profile_url": profile,
        "location": source.get("default_location") or "",
        "product": source.get("default_product") or "포켓몬 카드 상품 (제품명 미확정)",
        "status": status,
        "status_label": status_label,
        "summary": _clean(text, 420),
        "quantity_claim_min": quantity if relation == "at_least" else None,
        "quantity_claim": quantity if relation == "reported" else None,
        "quantity_relation": relation,
        "observed_at": _now(),
        "observed_precision": "public_search_result",
        "manual_user_evidence": False,
        "verification_status": "social_unverified",
        "official_stock": False,
        "realtime_stock": False,
        "confidence": round(min(0.78, score / 100.0), 2),
        "score": min(78, score),
        "ttl_hours": int(source.get("ttl_hours") or 24),
        "provider": raw.get("provider"),
        "signals": ["SNS 재고제보", status_label, "공식 재고 재확인 필요"],
    }
    return row


def _dedupe(rows: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str, str, str, str], dict] = {}
    sources_by_key: dict[tuple[str, str, str, str, str], set[str]] = {}
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        key = (
            str(raw.get("game") or ""), str(raw.get("region") or ""),
            _norm(raw.get("location")), _norm(raw.get("product")), str(raw.get("status") or ""),
        )
        if not key[2] or not key[4]:
            continue
        current = groups.get(key)
        source_name = str(raw.get("source_username") or raw.get("source_url") or "")
        sources_by_key.setdefault(key, set()).add(source_name)
        if current is None:
            groups[key] = dict(raw)
            continue
        # Prefer newer/manual evidence and keep the strongest claimed quantity as a claim.
        cur_manual = bool(current.get("manual_user_evidence")); new_manual = bool(raw.get("manual_user_evidence"))
        cur_time = _parse_observed(current.get("observed_at")) or dt.datetime.min.replace(tzinfo=dt.timezone.utc)
        new_time = _parse_observed(raw.get("observed_at")) or dt.datetime.min.replace(tzinfo=dt.timezone.utc)
        if (new_manual and not cur_manual) or new_time > cur_time:
            winner, other = dict(raw), current
        else:
            winner, other = current, raw
        for field in ("quantity_claim_min", "quantity_claim"):
            values = [x for x in (winner.get(field), other.get(field)) if isinstance(x, int)]
            if values:
                winner[field] = max(values)
        winner["confidence"] = max(float(winner.get("confidence") or 0), float(other.get("confidence") or 0))
        winner["score"] = max(int(winner.get("score") or 0), int(other.get("score") or 0))
        groups[key] = winner

    now = dt.datetime.now(dt.timezone.utc)
    out = []
    for key, row in groups.items():
        age = _age_hours(row, now)
        if age > MAX_AGE_HOURS:
            continue
        score, stale = age_adjusted_score(row, now)
        count = len([x for x in sources_by_key.get(key, set()) if x])
        row = dict(row)
        row["score"] = score
        row["age_hours"] = round(age, 1)
        row["stale"] = stale
        row["active"] = not stale
        row["independent_source_count"] = max(1, count)
        if count >= 2:
            row["cross_checked_social"] = True
            row["confidence"] = round(min(0.86, float(row.get("confidence") or 0.5) + 0.08), 2)
            row["score"] = min(86, row["score"] + 8)
        # Learning never changes trust/official inventory status.
        row["verification_status"] = "social_unverified"
        row["official_stock"] = False
        row["realtime_stock"] = False
        out.append(row)
    out.sort(key=lambda x: (bool(x.get("stale")), -int(x.get("score") or 0), float(x.get("age_hours") or 9999)))
    return out[:120]


def _record_learning(learning: dict, source: dict, *, raw_count: int, accepted: int, errors: int, seconds: float) -> None:
    rows = learning.setdefault("sources", {})
    key = str(source.get("username") or source.get("id") or "unknown")
    row = rows.setdefault(key, {"runs": 0, "raw_results": 0, "accepted": 0, "errors": 0})
    row["runs"] = int(row.get("runs") or 0) + 1
    row["raw_results"] = int(row.get("raw_results") or 0) + max(0, raw_count)
    row["accepted"] = int(row.get("accepted") or 0) + max(0, accepted)
    row["errors"] = int(row.get("errors") or 0) + max(0, errors)
    row["last_seconds"] = round(max(0.0, seconds), 3)
    row["last_run"] = _now()
    row["success_rate"] = round(int(row.get("accepted") or 0) / max(1, int(row.get("runs") or 0)), 3)
    row["trust_learning_disabled"] = True


def _collect_source(source: dict) -> tuple[list[dict], int, list[str], float]:
    started = time.monotonic(); raw_rows = []; errors = []
    for query in _source_queries(source):
        for provider in (_bing_rows, _ddg_rows):
            try:
                raw_rows.extend(provider(query))
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError, ET.ParseError, UnicodeDecodeError) as exc:
                errors.append(f"{provider.__name__}:{type(exc).__name__}")
    seen = set(); candidates = []
    for raw in raw_rows:
        key = (str(raw.get("url")), str(raw.get("title")))
        if key in seen:
            continue
        seen.add(key)
        candidate = _candidate_from_result(raw, source)
        if candidate:
            candidates.append(candidate)
        if len(candidates) >= MAX_RESULT_PER_SOURCE:
            break
    return candidates, len(raw_rows), errors, time.monotonic() - started


def main() -> dict:
    source_data = _load_json(SOURCE_DB, {"sources": []})
    signal_data = _load_json(SIGNAL_DB, {"version": 1, "items": []})
    learning = _learning()
    sources = [x for x in source_data.get("sources", []) if isinstance(x, dict) and "stock" in str(x.get("role") or "")]
    sources.sort(key=lambda x: _source_priority(x, learning))

    existing = [dict(x) for x in signal_data.get("items", []) if isinstance(x, dict)]
    discovered: list[dict] = []
    errors: list[str] = []
    raw_total = 0
    for source in sources:
        rows, raw_count, source_errors, seconds = _collect_source(source)
        discovered.extend(rows); raw_total += raw_count
        errors.extend(f"{source.get('username')}:{x}" for x in source_errors)
        _record_learning(learning, source, raw_count=raw_count, accepted=len(rows), errors=len(source_errors), seconds=seconds)

    merged = _dedupe(existing + discovered)
    payload = {
        "version": 2,
        "updated_at": _now(),
        "items": merged,
        "summary": {
            "sources_watched": len(sources),
            "raw_results": raw_total,
            "new_candidates": len(discovered),
            "active_signals": sum(1 for x in merged if not x.get("stale")),
            "stale_signals": sum(1 for x in merged if x.get("stale")),
            "errors": len(errors),
        },
        "collection_errors": errors[:30],
        "policy": "SNS는 재고 제보 신호만 생성합니다. 공식 실시간 재고·확정 수량으로 자동승격하지 않으며, 학습은 검색 우선순위만 조정합니다.",
    }
    atomic_write_json(SIGNAL_DB, payload, suffix=".social-stock.tmp")

    purchase_payload = {
        "version": 2,
        "updated_at": payload["updated_at"],
        "items": [x for x in merged if not x.get("stale")],
        "social_stock_signal_count": sum(1 for x in merged if not x.get("stale")),
        "notice": "최근 SNS 재고제보입니다. 실제 재고는 공식 재고조회·매장 확인이 필요합니다.",
    }
    atomic_write_json(PURCHASE_SIGNAL_DB, purchase_payload, suffix=".purchase-signal.tmp")
    learning["version"] = 1
    learning["updated_at"] = _now()
    learning["policy"] = "검색 성공률·응답시간만 학습하며 계정 trusted/official 여부는 학습으로 변경하지 않습니다."
    atomic_write_json(LEARNING_DB, learning, suffix=".social-learning.tmp")
    return payload


if __name__ == "__main__":
    result = main()
    print(json.dumps(result.get("summary", {}), ensure_ascii=False))
