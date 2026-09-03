#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bounded source-gap learning and secondary discovery for TCG information.

This module audits discovery coverage for Pokémon / ONE PIECE / NARUTO across
KR / JP / US without learning trust.  It may learn which *fixed* discovery
families are useful, but it cannot add hosts, source families, code, headers,
credentials, or permissions.

Safety contracts
- X / Instagram / Google / wiki / community hits remain discovery candidates.
- Only explicit official verification can close an information gap.
- 401/403 are access-control blocks and are never bypassed.
- 429 stops same-run secondary discovery and preserves bounded Retry-After.
- Secondary pages are never fetched here; only public search-index metadata is
  retained, so a wiki/community page cannot silently become canonical data.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from safe_runtime import atomic_write_json, env_int, safe_read_text, safe_urlopen, validate_public_https_url

ROOT = Path(__file__).resolve().parent
MEMORY = ROOT / "source_gap_learning.json"
REPORT = ROOT / "source_gap_intelligence.json"
TIMEOUT = env_int("TCG_HTTP_TIMEOUT", 20, 5, 60)
SEARCH_TIMEOUT = max(5, min(12, TIMEOUT))
MAX_MEMORY_CELLS = 120
MAX_PRIORITY_CELLS = 24
MAX_SECONDARY_QUERIES = 12
MAX_RESULTS_PER_QUERY = 4
MAX_SEARCH_BYTES = 700_000

GAMES = ("포켓몬 카드", "원피스 카드", "나루토 카드")
REGIONS = ("KR", "JP", "US")
TOPICS = (
    "event", "tournament", "popup", "promo", "collab",
    "movie", "release", "reprint", "merch", "anniversary",
)
EXPECTED_CELLS = tuple(
    (game, region, topic)
    for game in GAMES for region in REGIONS for topic in TOPICS
)

# Fixed IDs only. Persistent learning may reorder DISCOVERY_FAMILIES but can
# never invent a new family. Primary official verification remains first.
SOURCE_FAMILIES = (
    "official_direct", "official_social", "google", "broad_search",
    "social_x", "social_instagram", "social_youtube", "press_partner",
    "secondary_wiki", "community",
)
PRIMARY_FAMILIES = ("official_direct", "official_social")
DISCOVERY_FAMILIES = tuple(x for x in SOURCE_FAMILIES if x not in PRIMARY_FAMILIES)

DDG_HOSTS = {"html.duckduckgo.com", "duckduckgo.com", "www.duckduckgo.com"}
SECONDARY_HOSTS = {
    "namu.wiki": "secondary_wiki",
    "www.namu.wiki": "secondary_wiki",
    "reddit.com": "community",
    "www.reddit.com": "community",
    "old.reddit.com": "community",
    "blog.naver.com": "community",
    "m.blog.naver.com": "community",
}
SOCIAL_HOSTS = {
    "x.com": "social_x", "www.x.com": "social_x",
    "twitter.com": "social_x", "www.twitter.com": "social_x",
    "instagram.com": "social_instagram", "www.instagram.com": "social_instagram",
    "youtube.com": "social_youtube", "www.youtube.com": "social_youtube",
    "youtu.be": "social_youtube",
}
GOOGLE_HOSTS = {"news.google.com", "www.googleapis.com", "google.com", "www.google.com"}
PRESS_HOST_HINTS = (
    "news", "press", "prtimes", "businesswire", "prnewswire", "yna.co.kr",
    "newsis.com", "famitsu.com", "dengekionline.com", "hankyung.com",
)

GAME_QUERY = {
    "포켓몬 카드": {"KR": "포켓몬 카드", "JP": "ポケモンカード", "US": "Pokemon TCG"},
    "원피스 카드": {"KR": "원피스 카드", "JP": "ワンピースカード", "US": "One Piece Card Game"},
    "나루토 카드": {"KR": "나루토 카드", "JP": "NARUTO CARD GAME", "US": "NARUTO CARD GAME"},
}
TOPIC_QUERY = {
    "KR": {
        "event": "행사 이벤트", "tournament": "대회 챔피언십", "popup": "팝업 팝업스토어",
        "promo": "프로모 증정", "collab": "콜라보 협업", "movie": "영화 극장판",
        "release": "출시 발매 신제품", "reprint": "재발매 재판", "merch": "굿즈 공식샵",
        "anniversary": "기념 주년",
    },
    "JP": {
        "event": "イベント", "tournament": "大会 チャンピオンシップ", "popup": "ポップアップ",
        "promo": "プロモ 配布", "collab": "コラボ", "movie": "映画 劇場版",
        "release": "発売 新商品", "reprint": "再販 再版", "merch": "グッズ 公式ショップ",
        "anniversary": "記念 周年",
    },
    "US": {
        "event": "event", "tournament": "tournament championship", "popup": "pop-up",
        "promo": "promo giveaway", "collab": "collaboration", "movie": "movie film",
        "release": "release new set", "reprint": "reprint restock", "merch": "merch official shop",
        "anniversary": "anniversary",
    },
}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _int(value, default: int = 0, maximum: int = 1_000_000) -> int:
    try:
        return max(0, min(maximum, int(value)))
    except (TypeError, ValueError, OverflowError):
        return default


def _float(value, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError, OverflowError):
        return default


def _short(value: object, limit: int = 300) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()[:limit]


def _host(url: object) -> str:
    try:
        return (urllib.parse.urlsplit(str(url or "")).hostname or "").lower()
    except ValueError:
        return ""


def _game(value: object) -> str:
    raw = str(value or "").strip()
    text = raw.lower()
    if "포켓몬" in text or "pokemon" in text or "pokémon" in text:
        return "포켓몬 카드"
    if "원피스" in text or "one piece" in text or "ワンピ" in raw:
        return "원피스 카드"
    if "나루토" in text or "naruto" in text or "ナルト" in raw:
        return "나루토 카드"
    return raw if raw in GAMES else ""


def _region(value: object) -> str:
    region = str(value or "").upper().strip()
    return region if region in REGIONS else ""


def _topic(row: dict) -> str:
    explicit = str(row.get("topic") or "").strip().lower()
    explicit = {"collaboration": "collab", "stock": "release"}.get(explicit, explicit)
    if explicit in TOPICS:
        return explicit
    text = " ".join(str(row.get(k) or "") for k in (
        "category", "title", "name_ko", "name_native", "excerpt",
        "status", "reward", "condition",
    ))
    checks = (
        ("movie", r"영화|극장판|movie|film|cinema|映画|劇場版"),
        ("anniversary", r"기념|주년|anniversary|周年|記念"),
        ("merch", r"굿즈|점프샵|official shop|merch|グッズ|ショップ"),
        ("popup", r"팝업|pop[- ]?up|ポップアップ"),
        ("tournament", r"대회|리그|championship|tournament|大会|リーグ"),
        ("promo", r"프로모|증정|배포|promo|giveaway|配布|特典"),
        ("collab", r"콜라보|협업|collab|partnership|コラボ"),
        ("reprint", r"재발매|재판|reprint|restock|再販|再版"),
        ("release", r"출시|발매|신탄|release|launch|発売|新弾"),
    )
    return next((name for name, pattern in checks if re.search(pattern, text, re.I)), "event")


def classify_source(row: dict) -> str:
    """Map a candidate to one fixed discovery family; never learn a host here."""
    if not isinstance(row, dict):
        return "broad_search"
    kind = str(row.get("source_kind") or "").lower()
    provider = str(row.get("search_provider") or row.get("provider") or "").lower()
    tier = str(row.get("source_tier") or "").upper()
    host = _host(row.get("source") or row.get("url"))
    if row.get("official_account_verified") is True or kind.startswith("official_youtube"):
        return "official_social"
    if (
        row.get("official_domain_match") is True
        or str(row.get("source_grade") or "").lower() == "official"
        or kind in {"official_direct", "official_sitemap"}
    ):
        return "official_direct"
    if host in SOCIAL_HOSTS:
        return SOCIAL_HOSTS[host]
    if host in SECONDARY_HOSTS:
        return SECONDARY_HOSTS[host]
    if host in GOOGLE_HOSTS or provider in {"google_news", "google_cse", "google"}:
        return "google"
    if (
        provider in {"duckduckgo", "bing", "bing_rss", "bing_news", "naver_news", "multi_provider"}
        or "search" in kind
    ):
        return "broad_search"
    if tier.startswith("B") or any(hint in host for hint in PRESS_HOST_HINTS):
        return "press_partner"
    return "broad_search"


def _verified(row: dict) -> bool:
    """Only explicit verification backed by primary trust may close a gap."""
    if not isinstance(row, dict) or row.get("verified") is not True:
        return False
    return bool(
        row.get("official_account_verified") is True
        or row.get("official_domain_match") is True
        or str(row.get("source_grade") or "").lower() == "official"
        or str(row.get("source_tier") or "").upper() == "A"
    )


def _corroborated(row: dict) -> bool:
    return bool(row.get("cross_checked") is True or _int(row.get("independent_source_count")) >= 2)


def _normalize_row(row: dict) -> dict | None:
    if not isinstance(row, dict):
        return None
    game = _game(row.get("game") or row.get("keyword"))
    region = _region(row.get("region") or row.get("query_region"))
    if not game or not region:
        return None
    out = dict(row)
    out["game"] = game
    out["region"] = region
    out["topic"] = _topic(out)
    out["source_family"] = classify_source(out)
    return out


def _rows_from_pipeline(
    social: dict | None,
    supplementary: dict | None,
    broad_blocks: list[dict] | None,
) -> list[dict]:
    rows: list[dict] = []
    for payload in (social or {}, supplementary or {}):
        for item in (payload.get("items") or [])[:600]:
            normalized = _normalize_row(item)
            if normalized:
                rows.append(normalized)
    for block in (broad_blocks or [])[:20]:
        if not isinstance(block, dict):
            continue
        game = _game(block.get("keyword"))
        for item in (block.get("results") or [])[:100]:
            if not isinstance(item, dict):
                continue
            candidate = dict(item)
            candidate.setdefault("game", game)
            candidate.setdefault("region", item.get("query_region") or "KR")
            candidate.setdefault("source", item.get("url"))
            normalized = _normalize_row(candidate)
            if normalized:
                rows.append(normalized)
    return rows[:1600]


def audit_pipeline(
    social: dict | None,
    supplementary: dict | None,
    broad_blocks: list[dict] | None,
) -> dict:
    """Audit 90 cells without pretending every empty cell must contain an event."""
    rows = _rows_from_pipeline(social, supplementary, broad_blocks)
    buckets = {
        cell: {"candidate_count": 0, "verified_count": 0, "corroborated_count": 0, "families": {}}
        for cell in EXPECTED_CELLS
    }
    for row in rows:
        cell = (row["game"], row["region"], row["topic"])
        if cell not in buckets:
            continue
        stat = buckets[cell]
        family = row["source_family"] if row["source_family"] in SOURCE_FAMILIES else "broad_search"
        stat["candidate_count"] += 1
        stat["families"][family] = _int(stat["families"].get(family)) + 1
        if _verified(row):
            stat["verified_count"] += 1
        if _corroborated(row):
            stat["corroborated_count"] += 1

    cells: list[dict] = []
    priority: list[dict] = []
    for game, region, topic in EXPECTED_CELLS:
        raw = buckets[(game, region, topic)]
        family_count = len(raw["families"])
        lead_gap = raw["candidate_count"] > 0 and raw["verified_count"] == 0
        corroborated_gap = raw["corroborated_count"] > 0 and raw["verified_count"] == 0
        risk = 0
        reasons: list[str] = []
        if lead_gap:
            risk += 5
            reasons.append("후보는 있으나 공식 검증근거 없음")
        if corroborated_gap:
            risk += 3
            reasons.append("복수 발견근거는 있으나 공식확정 없음")
        # Diversity is a *gap* signal only while official evidence is absent.
        # A single authoritative official source is sufficient to close the gap;
        # otherwise an already verified event was incorrectly kept at risk=2.
        if lead_gap and family_count < 2:
            risk += 2
            reasons.append("독립 출처군 다양성 부족")
        item = {
            "game": game,
            "region": region,
            "topic": topic,
            "candidate_count": raw["candidate_count"],
            "verified_count": raw["verified_count"],
            "corroborated_count": raw["corroborated_count"],
            "source_family_count": family_count,
            "source_families": dict(sorted(raw["families"].items())),
            "lead_without_official_confirmation": lead_gap,
            "risk_score": risk,
            "reasons": reasons,
        }
        cells.append(item)
        if risk:
            priority.append(item)
    priority.sort(
        key=lambda x: (x["risk_score"], x["corroborated_count"], x["candidate_count"]),
        reverse=True,
    )
    return {
        "expected_cells": len(EXPECTED_CELLS),
        "observed_rows": len(rows),
        "cells_with_candidates": sum(1 for x in cells if x["candidate_count"]),
        "cells_with_verified_evidence": sum(1 for x in cells if x["verified_count"]),
        "unverified_lead_cells": sum(1 for x in cells if x["lead_without_official_confirmation"]),
        "priority_cells": priority[:MAX_PRIORITY_CELLS],
        "cells": cells,
    }


def _fresh_memory() -> dict:
    return {"version": 1, "updated_at": None, "runs": 0, "cells": {}, "families": {}}


def _load_memory(path: Path | str) -> dict:
    path = Path(path)
    for candidate in (path, path.with_suffix(path.suffix + ".bak")):
        try:
            data = json.loads(safe_read_text(candidate, max_bytes=1_000_000))
            if not isinstance(data, dict) or not isinstance(data.get("cells"), dict) or not isinstance(data.get("families"), dict):
                continue
            clean = _fresh_memory()
            clean["runs"] = _int(data.get("runs"))
            clean["updated_at"] = data.get("updated_at")
            for key, value in list(data["cells"].items())[:MAX_MEMORY_CELLS]:
                if isinstance(value, dict):
                    clean["cells"][str(key)[:100]] = dict(value)
            for key, value in list(data["families"].items())[:len(SOURCE_FAMILIES)]:
                if key in SOURCE_FAMILIES and isinstance(value, dict):
                    clean["families"][key] = dict(value)
            return clean
        except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError):
            continue
    return _fresh_memory()


def _family_score(stat: dict) -> float:
    discovered = max(1, _int(stat.get("discovered"), 1))
    verified = _int(stat.get("verified"))
    corroborated = _int(stat.get("corroborated"))
    blocked = _int(stat.get("access_blocks"))
    limited = _int(stat.get("rate_limits"))
    # Discovery utility only. Never used as a trust score.
    score = (verified / discovered) * 2.2 + (corroborated / discovered) * 1.1
    score += 0.35 / math.sqrt(discovered)
    score -= min(0.8, blocked * 0.04 + limited * 0.02)
    return round(max(-1.0, min(4.0, score)), 5)


def preferred_families(memory: dict) -> list[str]:
    stats = memory.get("families", {}) if isinstance(memory, dict) else {}
    ranked = [
        (_family_score(stats.get(family, {}) if isinstance(stats, dict) else {}), family)
        for family in DISCOVERY_FAMILIES
    ]
    ranked.sort(
        key=lambda pair: (pair[0], -DISCOVERY_FAMILIES.index(pair[1])),
        reverse=True,
    )
    return list(PRIMARY_FAMILIES) + [family for _, family in ranked]


def _parse_channel_failures(social: dict | None) -> dict[str, dict]:
    status = (social or {}).get("channel_status") or {}
    if not isinstance(status, dict):
        return {}
    out: dict[str, dict] = {}
    family_map = {
        "x": "social_x", "instagram": "social_instagram",
        "google_news": "google", "google_cse": "google",
        "public_social_search": "broad_search", "route_diversity": "broad_search",
    }
    for name, row in list(status.items())[:40]:
        if not isinstance(row, dict):
            continue
        text = " ".join(str(row.get(k) or "") for k in ("error", "status", "message", "errors")).lower()
        access = bool(re.search(r"(?:status|http|httperror)\s*[: ]?\s*(?:401|403)\b", text))
        limited = bool(re.search(r"(?:status|http|httperror)\s*[: ]?\s*429\b|retry-after", text))
        out[str(name)[:60]] = {
            "family": family_map.get(str(name), "broad_search"),
            "access_control_blocked": access,
            "rate_limited": limited,
            "next_action": (
                "공개 접근권한/공식 API 상태 확인 · 자동 우회 금지"
                if access else
                "Retry-After/cooldown 후 재확인"
                if limited else "정상/기타"
            ),
        }
    return out


def observe_pipeline(
    social: dict | None,
    supplementary: dict | None,
    broad_blocks: list[dict] | None,
    *,
    secondary_status: dict | None = None,
    memory_path: Path | str = MEMORY,
    report_path: Path | str = REPORT,
) -> dict:
    """Persist bounded utility/gap history while keeping trust immutable."""
    audit = audit_pipeline(social, supplementary, broad_blocks)
    memory_path, report_path = Path(memory_path), Path(report_path)
    memory = _load_memory(memory_path)
    memory["runs"] = _int(memory.get("runs")) + 1
    rows = _rows_from_pipeline(social, supplementary, broad_blocks)

    run_stats = {
        family: {"discovered": 0, "verified": 0, "corroborated": 0}
        for family in SOURCE_FAMILIES
    }
    for row in rows:
        family = row.get("source_family") if row.get("source_family") in SOURCE_FAMILIES else "broad_search"
        run_stats[family]["discovered"] += 1
        if _verified(row):
            run_stats[family]["verified"] += 1
        if _corroborated(row):
            run_stats[family]["corroborated"] += 1
    for family, current in run_stats.items():
        stat = memory.setdefault("families", {}).setdefault(family, {})
        for key in ("discovered", "verified", "corroborated"):
            stat[key] = _int(stat.get(key)) + current[key]
        if current["discovered"]:
            stat["last_seen"] = _now()

    channel_state = _parse_channel_failures(social)
    for row in channel_state.values():
        family = row["family"] if row["family"] in SOURCE_FAMILIES else "broad_search"
        stat = memory.setdefault("families", {}).setdefault(family, {})
        if row["access_control_blocked"]:
            stat["access_blocks"] = _int(stat.get("access_blocks")) + 1
        if row["rate_limited"]:
            stat["rate_limits"] = _int(stat.get("rate_limits")) + 1

    if isinstance(secondary_status, dict):
        # Secondary search is a discovery transport; failures reduce its utility
        # but never authorize a bypass or a new host.
        stat = memory.setdefault("families", {}).setdefault("community", {})
        if secondary_status.get("access_control_blocked"):
            stat["access_blocks"] = _int(stat.get("access_blocks")) + 1
        if secondary_status.get("rate_limited"):
            stat["rate_limits"] = _int(stat.get("rate_limits")) + 1

    for cell in audit["cells"]:
        key = f"{cell['game']}|{cell['region']}|{cell['topic']}"
        stat = memory.setdefault("cells", {}).setdefault(key, {})
        stat["runs"] = _int(stat.get("runs")) + 1
        if cell["candidate_count"]:
            stat["candidate_runs"] = _int(stat.get("candidate_runs")) + 1
        if cell["verified_count"]:
            stat["verified_runs"] = _int(stat.get("verified_runs")) + 1
            stat["unverified_lead_streak"] = 0
        elif cell["candidate_count"]:
            stat["unverified_lead_streak"] = min(1000, _int(stat.get("unverified_lead_streak")) + 1)
        stat["last_candidate_count"] = _int(cell["candidate_count"], maximum=5000)
        stat["last_verified_count"] = _int(cell["verified_count"], maximum=5000)
        stat["last_source_family_count"] = _int(cell["source_family_count"], maximum=20)
        stat["last_seen"] = _now()

    if len(memory.get("cells", {})) > MAX_MEMORY_CELLS:
        ranked_cells = sorted(
            memory["cells"].items(),
            key=lambda pair: (
                _int(pair[1].get("unverified_lead_streak")),
                _int(pair[1].get("candidate_runs")),
            ),
            reverse=True,
        )
        memory["cells"] = dict(ranked_cells[:MAX_MEMORY_CELLS])

    memory["updated_at"] = _now()
    if memory_path.exists():
        previous = _load_memory(memory_path)
        atomic_write_json(
            memory_path.with_suffix(memory_path.suffix + ".bak"),
            previous,
            suffix=".source-gap.bak.tmp",
        )
    atomic_write_json(memory_path, memory, suffix=".source-gap.tmp")

    family_rows = []
    for family in SOURCE_FAMILIES:
        stat = memory.get("families", {}).get(family, {})
        family_rows.append({
            "family": family,
            "discovered": _int(stat.get("discovered")),
            "verified": _int(stat.get("verified")),
            "corroborated": _int(stat.get("corroborated")),
            "access_blocks": _int(stat.get("access_blocks")),
            "rate_limits": _int(stat.get("rate_limits")),
            "utility_score": _family_score(stat),
        })
    order = preferred_families(memory)
    priorities = []
    for cell in audit["priority_cells"]:
        key = f"{cell['game']}|{cell['region']}|{cell['topic']}"
        learned = memory.get("cells", {}).get(key, {})
        item = dict(cell)
        item["unverified_lead_streak"] = _int(learned.get("unverified_lead_streak"))
        item["preferred_families"] = order
        priorities.append(item)
    priorities.sort(
        key=lambda x: (x["risk_score"], x["unverified_lead_streak"], x["candidate_count"]),
        reverse=True,
    )

    report = {
        "version": 1,
        "updated_at": _now(),
        "expected_cells": audit["expected_cells"],
        "observed_rows": audit["observed_rows"],
        "cells_with_candidates": audit["cells_with_candidates"],
        "cells_with_verified_evidence": audit["cells_with_verified_evidence"],
        "unverified_lead_cells": audit["unverified_lead_cells"],
        "priority_cells": priorities[:MAX_PRIORITY_CELLS],
        "source_family_order": order,
        "source_family_stats": family_rows,
        "channel_access_state": channel_state,
        "secondary_status": secondary_status or {},
        "policy": "출처 유용성/누락위험만 제한적으로 학습 · 공식성/사실성 자동승격 금지 · 학습으로 도메인/코드/권한/헤더 추가 금지",
        "access_policy": "401/403 자동우회 금지 · 429 Retry-After/cooldown 준수 · 공개 검색결과의 2차 출처는 후보만 저장",
    }
    atomic_write_json(report_path, report, suffix=".source-gap-report.tmp")
    return report


class _ResultParser(HTMLParser):
    """Minimal DuckDuckGo result parser; target pages are not fetched."""
    def __init__(self) -> None:
        super().__init__()
        self.href = ""
        self.text: list[str] = []
        self.results: list[tuple[str, str]] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        data = dict(attrs)
        classes = str(data.get("class") or "")
        href = str(data.get("href") or "")
        if href and ("result__a" in classes or "result-link" in classes):
            self.href = html.unescape(href)
            self.text = []

    def handle_data(self, data):
        if self.href:
            self.text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.href:
            title = _short(" ".join(self.text), 220)
            if title:
                self.results.append((self.href, title))
            self.href = ""
            self.text = []


def _decode_ddg_target(href: str) -> str:
    absolute = urllib.parse.urljoin("https://duckduckgo.com/", href)
    try:
        parsed = urllib.parse.urlsplit(absolute)
    except ValueError:
        return ""
    if (parsed.hostname or "").lower() in DDG_HOSTS:
        target = (urllib.parse.parse_qs(parsed.query).get("uddg") or [""])[0]
        return urllib.parse.unquote(target) if target else ""
    return absolute


def _retry_after_seconds(headers) -> int | None:
    if headers is None:
        return None
    raw = headers.get("Retry-After")
    try:
        return max(1, min(86_400, int(str(raw).strip()))) if raw is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


def _secondary_sites(region: str) -> list[tuple[str, str]]:
    common = [("community", "reddit.com")]
    if region == "KR":
        return [("secondary_wiki", "namu.wiki"), ("community", "blog.naver.com")] + common
    return common


def _search_secondary(
    game: str,
    region: str,
    topic: str,
    family: str,
    domain: str,
) -> tuple[list[dict], dict]:
    if family not in {"secondary_wiki", "community"} or SECONDARY_HOSTS.get(domain) != family:
        return [], {"ok": False, "error": "unapproved secondary route"}
    query = f'{GAME_QUERY[game][region]} {TOPIC_QUERY[region][topic]} site:{domain}'
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    validate_public_https_url(url, DDG_HOSTS)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 TCG-Grader-GapDiscovery/1.1"},
    )
    try:
        with safe_urlopen(request, timeout=SEARCH_TIMEOUT, allowed_hosts=DDG_HOSTS) as response:
            final = response.geturl()
            validate_public_https_url(final, DDG_HOSTS)
            raw = response.read(MAX_SEARCH_BYTES).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        status = int(getattr(exc, "code", 0) or 0)
        return [], {
            "ok": False,
            "http_status": status,
            "access_control_blocked": status in {401, 403},
            "rate_limited": status == 429,
            "retry_after_seconds": _retry_after_seconds(getattr(exc, "headers", None)) if status == 429 else None,
            "error": f"HTTP {status}",
            "policy": "401/403 우회 금지 · 429 동일 실행 즉시 재시도 금지",
        }
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, UnicodeError) as exc:
        return [], {"ok": False, "error": type(exc).__name__}

    parser = _ResultParser()
    parser.feed(raw)
    rows: list[dict] = []
    for href, title in parser.results:
        target = _decode_ddg_target(href)
        host = _host(target)
        if not target.startswith("https://"):
            continue
        if host != domain and not host.endswith("." + domain):
            continue
        if (SECONDARY_HOSTS.get(host) or SECONDARY_HOSTS.get(domain)) != family:
            continue
        rows.append({
            "game": game,
            "region": region,
            "topic": topic,
            "category": "collaboration" if topic == "collab" else ("movie" if topic == "movie" else "promo"),
            "title": title,
            "source": target[:900],
            "source_kind": "namuwiki_search_candidate" if family == "secondary_wiki" else "community_search_candidate",
            "source_tier": "C",
            "source_label": "나무위키 검색 발견후보" if family == "secondary_wiki" else "커뮤니티 검색 발견후보",
            "verified": False,
            "needs_official_confirmation": True,
            "status": "보조출처 발견후보 · 공식/공공/공식SNS 재확인 필요",
            "discovered_via": "duckduckgo_public_index",
            "collected_at": _now(),
        })
        if len(rows) >= MAX_RESULTS_PER_QUERY:
            break
    return rows, {
        "ok": True,
        "query": query[:300],
        "result_count": len(rows),
        "family": family,
        "domain": domain,
    }


def collect_secondary_leads(
    priority_cells: list[dict] | None,
    max_queries: int = MAX_SECONDARY_QUERIES,
) -> tuple[list[dict], dict]:
    """Search only high-risk cells and stop globally on 403/429."""
    limit = max(1, min(MAX_SECONDARY_QUERIES, _int(max_queries, MAX_SECONDARY_QUERIES, MAX_SECONDARY_QUERIES)))
    rows: list[dict] = []
    attempts: list[dict] = []
    seen_urls: set[str] = set()
    access_blocked = False
    rate_limited = False
    retry_after: int | None = None
    query_count = 0
    for cell in (priority_cells or [])[:MAX_PRIORITY_CELLS]:
        game = _game(cell.get("game"))
        region = _region(cell.get("region"))
        topic = str(cell.get("topic") or "")
        if not game or not region or topic not in TOPICS:
            continue
        for family, domain in _secondary_sites(region):
            if query_count >= limit or access_blocked or rate_limited:
                break
            found, status = _search_secondary(game, region, topic, family, domain)
            query_count += 1
            attempts.append(status)
            access_blocked = access_blocked or bool(status.get("access_control_blocked"))
            rate_limited = rate_limited or bool(status.get("rate_limited"))
            if status.get("retry_after_seconds"):
                retry_after = max(_int(retry_after), _int(status.get("retry_after_seconds"))) or None
            for row in found:
                source = str(row.get("source") or "")
                if source and source not in seen_urls:
                    seen_urls.add(source)
                    rows.append(row)
        if query_count >= limit or access_blocked or rate_limited:
            break
    return rows[:80], {
        "configured": True,
        "query_count": query_count,
        "result_count": len(rows),
        "access_control_blocked": access_blocked,
        "rate_limited": rate_limited,
        "retry_after_seconds": retry_after,
        "attempts": attempts[:MAX_SECONDARY_QUERIES],
        "policy": "검색 인덱스 메타데이터만 수집 · 나무위키/Reddit/Naver 블로그 본문 자동수집·자동확정 금지",
    }


if __name__ == "__main__":
    try:
        social_payload = json.loads(safe_read_text(ROOT / "social_event_candidates.json"))
    except Exception:
        social_payload = {}
    try:
        supplementary_payload = json.loads(safe_read_text(ROOT / "supplementary_candidates.json"))
    except Exception:
        supplementary_payload = {}
    print(json.dumps(observe_pipeline(social_payload, supplementary_payload, []), ensure_ascii=False, indent=2))
