#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Official grading-company price/service/event watcher.

Only official allowlisted HTTPS pages can create verified records. Community posts,
screenshots and search results are leads only and never write this snapshot directly.
If a source cannot be fetched or parsed, the previous last-good structured values are
retained and the source is marked degraded instead of replacing facts with emptiness.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit
import json
import re
import urllib.request

from safe_runtime import atomic_write_json, diagnostic_exception, safe_read_text, safe_urlopen

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "grading_company_updates.json"
UA = "Mozilla/5.0 TCG-Grader-GradingCompanyWatch/1.0"
MAX_PAGE_BYTES = 2_000_000
MAX_HISTORY = 240
MAX_ANNOUNCEMENTS = 120
PARSER_VERSION = 2

ALLOWED_HOSTS = {
    "psacard.com", "www.psacard.com",
    "beckett.com", "www.beckett.com",
    "cgccards.com", "www.cgccards.com",
    "taggrading.com", "www.taggrading.com",
    "break.co.kr", "www.break.co.kr",
}

WATCH_SOURCES = {
    "PSA": (
        {"id": "psa-us-pricing", "kind": "pricing", "market": "US", "currency": "USD",
         "url": "https://www.psacard.com/services/tradingcardgrading"},
        {"id": "psa-jp-pricing", "kind": "pricing", "market": "JP", "currency": "JPY",
         "url": "https://www.psacard.com/ja-JP/services/tradingcardgrading/grading"},
        {"id": "psa-jp-news", "kind": "news", "market": "JP", "currency": "JPY",
         "url": "https://www.psacard.com/ja-JP/articles"},
    ),
    "BGS": (
        {"id": "bgs-pricing", "kind": "pricing", "market": "US", "currency": "USD",
         "url": "https://www.beckett.com/grading"},
        {"id": "bgs-news", "kind": "news", "market": "GLOBAL", "currency": "USD",
         "url": "https://www.beckett.com/news/"},
    ),
    "CGC": (
        {"id": "cgc-pricing", "kind": "pricing", "market": "US", "currency": "USD",
         "url": "https://www.cgccards.com/submit/services-fees/cgc-grading/?view=cards"},
        {"id": "cgc-events", "kind": "events", "market": "GLOBAL", "currency": "USD",
         "url": "https://www.cgccards.com/submit/events/"},
        {"id": "cgc-news", "kind": "news", "market": "GLOBAL", "currency": "USD",
         "url": "https://www.cgccards.com/news/"},
    ),
    "TAG": (
        {"id": "tag-pricing", "kind": "pricing", "market": "US", "currency": "USD",
         "url": "https://taggrading.com/pages/pricing"},
        {"id": "tag-home", "kind": "news", "market": "GLOBAL", "currency": "USD",
         "url": "https://taggrading.com/"},
    ),
    "BRG": (
        {"id": "brg-pricing-news", "kind": "pricing_news", "market": "KR", "currency": "KRW",
         "url": "https://break.co.kr/"},
    ),
}

SERVICE_ALIASES = {
    ("PSA", "US"): {
        "Value Bulk": ("Value Bulk",), "Value": ("Value",), "Value Plus": ("Value Plus",),
        "Value Max": ("Value Max",), "Standard": ("Standard",), "Regular": ("Regular",),
        "Priority": ("Priority",), "Express": ("Express",), "Super Express": ("Super Express",),
        "Walk-Through": ("Walk-Through", "Walk Through"), "Premium 1": ("Premium 1",),
        "Premium 2": ("Premium 2",), "Premium 3": ("Premium 3",), "Premium 5": ("Premium 5",),
        "Premium 10": ("Premium 10",),
    },
    ("PSA", "JP"): {
        "Value Bulk": ("バリュー・バルク", "バリューバルク"), "Value": ("バリュー",),
        "Value Plus": ("バリュー・プラス", "バリュープラス"),
        "Value Max": ("バリュー・マックス", "バリューマックス"),
        "Standard": ("スタンダード", "Standard"), "Regular": ("レギュラー", "Regular"),
        "Priority": ("プライオリティ", "Priority"), "Express": ("エクスプレス", "Express"),
        "Super Express": ("スーパー・エクスプレス", "スーパーエクスプレス", "Super Express"),
        "Walk-Through": ("ウォーク・スルー", "ウォークスルー", "Walk-Through"),
        "Premium 1": ("プレミアム1", "Premium 1"), "Premium 2": ("プレミアム2", "Premium 2"),
        "Premium 3": ("プレミアム3", "Premium 3"), "Premium 5": ("プレミアム5", "Premium 5"),
        "Premium 10": ("プレミアム10", "Premium 10"),
    },
    ("BGS", "US"): {
        "Base": ("Base",), "Base + Subgrades": ("Base + Subgrades", "Base+Subgrades"),
        "Standard": ("Standard",), "Express": ("Express",), "Priority": ("Priority",),
    },
    ("CGC", "US"): {
        "Bulk": ("Bulk",), "Economy": ("Economy",), "Standard": ("Standard",),
        "Express": ("Express",), "WalkThrough": ("WalkThrough", "Walk Through"),
    },
    ("TAG", "US"): {
        "Basic": ("Basic",), "Standard": ("Standard",), "Express": ("Express",),
        "Priority": ("Priority",), "Walkthrough": ("Walkthrough", "Walk Through"),
    },
    ("BRG", "KR"): {
        "Regular": ("Regular", "레귤러"), "Express": ("Express", "익스프레스"),
        "Bulk": ("Bulk", "벌크"), "Reholder": ("Reholder", "리홀더"), "BRG GEN": ("BRG GEN",),
    },
}

SIGNAL_RE = re.compile(
    r"(?i)(service|pricing|price|fee|turnaround|business day|grading|submission|"
    r"event|show|expo|promo|promotion|special|sold out|paused|reopen|"
    r"サービス|料金|価格|納期|営業日|受付|停止|再開|イベント|出展|変更|"
    r"요금|가격|납기|영업일|접수|중지|재개|이벤트|행사|프로모)"
)
ANNOUNCEMENT_RE = re.compile(
    r"(?i)(service|pricing|price|fee|turnaround|grading|submission|"
    r"event|show|expo|promo|promotion|signing|on-site|sold out|paused|reopen|"
    r"サービス|料金|価格|納期|受付|停止|再開|イベント|出展|変更|"
    r"요금|가격|납기|접수|중지|재개|이벤트|행사|프로모)"
)


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.href: str | None = None
        self.parts: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        self.href = next((v for k, v in attrs if k.lower() == "href" and v), None)
        self.parts = []

    def handle_data(self, data):
        if self.href is not None:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.href is not None:
            title = re.sub(r"\s+", " ", unescape(" ".join(self.parts))).strip()
            if title:
                self.links.append((self.href, title[:300]))
            self.href = None
            self.parts = []


def _text(raw: str) -> str:
    raw = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", unescape(raw)).strip()


def _fetch_raw(url: str) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Language": "ko-KR,ja-JP;q=0.9,en-US;q=0.8,en;q=0.7",
    })
    with safe_urlopen(req, timeout=20, allowed_hosts=ALLOWED_HOSTS, max_redirects=3) as response:
        return response.read(MAX_PAGE_BYTES).decode("utf-8", "ignore")


def _source_host_allowed(url: str) -> bool:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return parts.scheme == "https" and (parts.hostname or "").lower() in ALLOWED_HOSTS


def _window(text: str, alias: str, radius: int = 420) -> str | None:
    match = re.search(re.escape(alias), text, re.I)
    if not match:
        return None
    # Never look behind the matched service label: a preceding tier's fee can
    # otherwise be attached to the next tier after a service-table redesign.
    return text[match.start():min(len(text), match.end() + radius)]


def _price(window: str, currency: str) -> float | int | None:
    if currency == "JPY":
        values = [int(v.replace(",", "")) for v in re.findall(r"[￥¥]\s*([0-9][0-9,]*)", window)]
        return next((v for v in values if 500 <= v <= 20_000_000), None)
    if currency == "KRW":
        values = [int(v.replace(",", "")) for v in re.findall(r"(?:₩\s*)?([0-9][0-9,]*)\s*원", window)]
        return next((v for v in values if 1000 <= v <= 5_000_000), None)
    # Prefer explicitly labelled per-card fee fields. Official tables such as
    # CGC put the maximum declared value before the fee, so the first dollar
    # amount is not necessarily the grading price.
    for pattern in (
        r"Fee\s+Per\s+Card\s*\(USD\)\s*\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
        r"\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*(?:per\s*card|/\s*card)\b",
        r"(?:fee|price|pricing)\s*[:=-]?\s*\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
    ):
        match = re.search(pattern, window, re.I)
        if match:
            value = float(match.group(1).replace(",", ""))
            if 5 <= value <= 50_000:
                return value
    values = [float(v.replace(",", "")) for v in re.findall(r"\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)", window)]
    return next((v for v in values if 5 <= v <= 50_000), None)


def _turnaround(window: str) -> int | None:
    for pattern in (
        r"予定納期\s*[:：]?\s*(\d{1,4})\s*営業日",
        r"(\d{1,4})\+?\s*business\s*days?",
        r"Current\s+Turnaround\s*\(working\s+days\)\s*(\d{1,4})\s*days?",
        r"(\d{1,4})\s*영업일",
    ):
        match = re.search(pattern, window, re.I)
        if match:
            value = int(match.group(1))
            if 1 <= value <= 1000:
                return value
    return None


def _max_value(window: str, currency: str) -> float | int | None:
    if currency == "JPY":
        match = re.search(r"申告価格\s*[:：]?\s*[￥¥]?\s*([0-9][0-9,]*)\s*(?:以下|まで)", window)
        return int(match.group(1).replace(",", "")) if match else None
    if currency == "KRW":
        match = re.search(r"(?:신고가액|신고가격).{0,30}?([0-9][0-9,]*)\s*원", window, re.I)
        return int(match.group(1).replace(",", "")) if match else None
    match = re.search(
        r"(?:Max\.?\s+Value\s+per\s+Card(?:\s*\(USD\))?|Max(?:imum)?\s+(?:Insured|Declared)\s+Value|Declared\s+Value).{0,50}?\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
        window, re.I,
    )
    return float(match.group(1).replace(",", "")) if match else None


def _availability(window: str) -> str:
    low = window.lower()
    if any(term in low for term in ("sold out", "temporarily paused", "paused", "受付停止中", "접수 중지", "접수중지")):
        return "paused"
    if any(term in low for term in ("submit now", "申し込む", "접수", "available")):
        return "open"
    return "unknown"


def parse_services(company: str, market: str, currency: str, text: str, source: str) -> list[dict]:
    rows: list[dict] = []
    for canonical, aliases in SERVICE_ALIASES.get((company, market), {}).items():
        best: tuple[str, str] | None = None
        for alias in sorted(aliases, key=len, reverse=True):
            win = _window(text, alias)
            if win:
                best = (alias, win)
                break
        if not best:
            continue
        alias, win = best
        fee = _price(win, currency)
        availability = _availability(win)
        turnaround = _turnaround(win)
        max_value = _max_value(win, currency)
        # A menu label alone is too weak to become a service fact.
        if fee is None and turnaround is None and max_value is None and availability != "paused":
            continue
        row = {
            "name": canonical, "observed_label": alias, "currency": currency,
            "availability": availability, "source": source, "verified_official_source": True,
            "parser_version": PARSER_VERSION,
        }
        if fee is not None:
            row["fee"] = fee
        if turnaround is not None:
            row["turnaround_business_days"] = turnaround
        if max_value is not None:
            row["max_declared_or_insured_value"] = max_value
        rows.append(row)
    return rows


def _relevant_fingerprint(text: str) -> str:
    chunks = re.split(r"(?<=[.!?。！？])\s+|\s{2,}", text)
    relevant = [re.sub(r"\s+", " ", chunk).strip()[:600] for chunk in chunks if SIGNAL_RE.search(chunk)]
    material = "\n".join(relevant[:250]) or text[:50_000]
    return sha256(material.encode("utf-8")).hexdigest()


def extract_announcements(raw: str, base_url: str, company: str, source_id: str) -> list[dict]:
    parser = _Links()
    try:
        parser.feed(raw)
    except Exception:
        return []
    base_host = (urlsplit(base_url).hostname or "").lower()
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for href, title in parser.links:
        if not ANNOUNCEMENT_RE.search(title):
            continue
        url = urljoin(base_url, href)
        if not _source_host_allowed(url):
            continue
        host = (urlsplit(url).hostname or "").lower()
        aliases = {base_host, base_host[4:] if base_host.startswith("www.") else "www." + base_host}
        if host not in aliases:
            continue
        key = (url.split("#", 1)[0], title.casefold())
        if key in seen:
            continue
        seen.add(key)
        date_match = re.search(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})", title)
        row = {
            "company": company, "source_id": source_id, "title": title,
            "url": url.split("#", 1)[0], "verified_official_source": True,
        }
        if date_match:
            row["announced_date"] = f"{int(date_match.group(1)):04d}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"
        rows.append(row)
        if len(rows) >= 40:
            break
    return rows


def _service_map(rows: list[dict]) -> dict[str, dict]:
    return {str(row.get("name")): row for row in rows if isinstance(row, dict) and row.get("name")}


def _service_changes(company: str, source_id: str, before: list[dict], after: list[dict], checked_at: str) -> list[dict]:
    old, new = _service_map(before), _service_map(after)
    changes: list[dict] = []
    # Do not misread a parser collapse as every service being removed.
    allow_removal = bool(after) and len(after) >= max(2, len(before) // 2)
    for name, row in new.items():
        if name not in old:
            changes.append({
                "company": company, "source_id": source_id, "type": "service_added",
                "service": name, "after": row, "detected_at": checked_at,
                "verified_official_source": True, "parser_version": PARSER_VERSION,
            })
            continue
        prior = old[name]
        fields = ("fee", "turnaround_business_days", "max_declared_or_insured_value", "availability")
        diffs = {field: {"before": prior.get(field), "after": row.get(field)}
                 for field in fields if prior.get(field) != row.get(field)}
        if diffs:
            changes.append({
                "company": company, "source_id": source_id, "type": "service_changed",
                "service": name, "changes": diffs, "after": row, "detected_at": checked_at,
                "verified_official_source": True, "parser_version": PARSER_VERSION,
            })
    if allow_removal:
        for name, row in old.items():
            if name not in new:
                changes.append({
                    "company": company, "source_id": source_id, "type": "service_removed",
                    "service": name, "before": row, "detected_at": checked_at,
                    "verified_official_source": True, "parser_version": PARSER_VERSION,
                })
    return changes


def _announcement_key(row: dict) -> tuple[str, str, str]:
    return (str(row.get("company", "")), str(row.get("url", "")), str(row.get("title", "")).casefold())


def _load_previous(path: Path = OUT) -> dict:
    try:
        data = json.loads(safe_read_text(path, max_bytes=8_000_000))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        return {}


def collect(previous: dict | None = None, fetcher=_fetch_raw) -> dict:
    previous = previous if isinstance(previous, dict) else {}
    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    prev_sources = previous.get("sources", {}) if isinstance(previous.get("sources"), dict) else {}
    sources: dict[str, dict] = {}
    companies: dict[str, dict] = {}
    changes: list[dict] = []
    announcements: list[dict] = []

    for company, specs in WATCH_SOURCES.items():
        markets: dict[str, dict] = {}
        health: list[dict] = []
        for spec in specs:
            source_id = spec["id"]
            old = prev_sources.get(source_id, {}) if isinstance(prev_sources.get(source_id), dict) else {}
            try:
                raw = fetcher(spec["url"])
                text = _text(raw)
                if len(text) < 80:
                    raise ValueError("official page body too short")
                services = parse_services(company, spec["market"], spec["currency"], text, spec["url"]) if "pricing" in spec["kind"] else []
                if "pricing" in spec["kind"] and not services:
                    raise ValueError("pricing parser yielded zero verified services")
                found = extract_announcements(raw, spec["url"], company, source_id) if spec["kind"] in {"news", "events", "pricing_news"} else []
                fingerprint = _relevant_fingerprint(text)
                row = {
                    "company": company, "source_id": source_id, "kind": spec["kind"],
                    "market": spec["market"], "currency": spec["currency"], "url": spec["url"],
                    "status": "ok", "checked_at": checked_at, "signal_fingerprint": fingerprint,
                    "services": services, "announcements": found, "verified_official_source": True,
                    "parser_version": PARSER_VERSION,
                }
                # First successful observation of a source establishes its baseline.
                # A previously verified source may emit service changes, including
                # recovery after a temporary degraded fetch that retained last-good data.
                structured = (
                    _service_changes(company, source_id, old.get("services", []) or [], services, checked_at)
                    if old.get("verified_official_source") is True and old.get("parser_version") == PARSER_VERSION else []
                )
                changes.extend(structured)
                old_fp = old.get("signal_fingerprint")
                if old.get("parser_version") == PARSER_VERSION and old_fp and old_fp != fingerprint and not structured and not found:
                    changes.append({
                        "company": company, "source_id": source_id, "type": "official_page_changed_unparsed",
                        "detected_at": checked_at, "source": spec["url"], "requires_review": True,
                        "verified_official_source": True,
                    })
                sources[source_id] = row
                if services:
                    markets[spec["market"]] = {
                        "currency": spec["currency"], "source": spec["url"], "services": services,
                        "verified_official_source": True,
                    }
                announcements.extend(found)
                health.append({"source_id": source_id, "status": "ok", "url": spec["url"]})
            except Exception as exc:
                old_verified = bool(
                    old.get("verified_official_source") is True
                    and old.get("signal_fingerprint")
                )
                retained = dict(old) if old else {
                    "company": company, "source_id": source_id, "kind": spec["kind"],
                    "market": spec["market"], "currency": spec["currency"], "url": spec["url"],
                    "services": [], "announcements": [],
                }
                retained.update({
                    "status": "degraded", "checked_at": checked_at,
                    "last_error": diagnostic_exception(exc), "verified_official_source": old_verified,
                })
                sources[source_id] = retained
                if old_verified and retained.get("services"):
                    markets[spec["market"]] = {
                        "currency": spec["currency"], "source": spec["url"],
                        "services": retained["services"], "retained_last_good": True,
                        "verified_official_source": True,
                    }
                if old_verified:
                    announcements.extend(retained.get("announcements", []) or [])
                health.append({
                    "source_id": source_id, "status": "degraded", "url": spec["url"],
                    "error": diagnostic_exception(exc),
                })
        companies[company] = {"markets": markets, "source_health": health}

    previous_announcements = previous.get("announcements", []) if isinstance(previous.get("announcements"), list) else []
    old_keys = {_announcement_key(row) for row in previous_announcements if isinstance(row, dict)}
    for row in announcements:
        prior_source = prev_sources.get(str(row.get("source_id", "")), {})
        # A newly introduced official source is baseline inventory even when the
        # repository already has snapshots for other companies/sources.
        if not (isinstance(prior_source, dict) and prior_source.get("verified_official_source") is True):
            continue
        if _announcement_key(row) not in old_keys:
            changes.append({
                "company": row["company"], "source_id": row["source_id"], "type": "official_announcement",
                "title": row["title"], "url": row["url"], "detected_at": checked_at,
                "verified_official_source": True,
            })

    announcement_map: dict[tuple[str, str, str], dict] = {}
    for row in [*previous_announcements, *announcements]:
        if isinstance(row, dict) and row.get("url") and row.get("title"):
            announcement_map[_announcement_key(row)] = row
    merged_announcements = list(announcement_map.values())[-MAX_ANNOUNCEMENTS:]

    prior_history = previous.get("history", []) if isinstance(previous.get("history"), list) else []
    seen_changes: set[str] = set()
    merged_history: list[dict] = []
    for row in [*prior_history, *changes]:
        if not isinstance(row, dict):
            continue
        stable = {k: v for k, v in row.items() if k != "detected_at"}
        key = sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")).hexdigest()
        if key in seen_changes:
            continue
        seen_changes.add(key)
        merged_history.append(row)

    health_rows = [row for company in companies.values() for row in company["source_health"]]
    ok_sources = sum(1 for row in health_rows if row["status"] == "ok")
    return {
        "schema_version": 1,
        "checked_at": checked_at,
        "policy": {
            "official_sources_only": True,
            "community_posts_are_leads_only": True,
            "last_good_retained_on_failure": True,
            "automatic_source_code_mutation": False,
            "tracks": ["fee", "service_level", "turnaround", "availability", "official_events", "official_announcements"],
        },
        "summary": {
            "companies": len(WATCH_SOURCES), "sources": len(health_rows), "healthy_sources": ok_sources,
            "degraded_sources": len(health_rows) - ok_sources, "new_changes": len(changes),
        },
        "companies": companies,
        "sources": sources,
        "announcements": merged_announcements,
        "recent_changes": changes[-80:],
        "history": merged_history[-MAX_HISTORY:],
    }


def update(path: Path = OUT) -> dict:
    data = collect(_load_previous(path))
    atomic_write_json(path, data, suffix=".grading-company-watch.tmp")
    return data


def main() -> int:
    data = update()
    print(json.dumps({
        "checked_at": data["checked_at"], "summary": data["summary"],
        "recent_changes": data["recent_changes"][-10:],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
