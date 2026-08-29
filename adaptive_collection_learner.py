#!/usr/bin/env python3
"""Adaptive query/source learner for TCG event discovery.

This module learns *collection strategy*, not grading labels.  It never promotes a
source to official merely because it was found often.  Official trust remains
controlled by the existing official-domain/social registries.

Persistent learning goals
- Remember which query families actually return relevant/official/cross-checked
  Pokemon, ONE PIECE and NARUTO event leads.
- Learn useful event terms and source hosts from already verified candidates.
- Rotate a small exploration budget so the collector does not get trapped using
  only historically successful queries.
- Penalize repeated empty/error queries and recover gradually after success.
- Keep bounded, atomic, backup-protected memory suitable for Termux tablets.
- Accept an optional collection_feedback.json file so future "missed event"
  corrections can immediately teach the next search cycle.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import re
import urllib.parse
from pathlib import Path
from typing import Iterable

from safe_runtime import atomic_write_json, safe_read_text
import collection_meta_learning

ROOT = Path(__file__).resolve().parent
MEMORY = ROOT / "collection_learning_memory.json"
BACKUP = ROOT / "collection_learning_memory.json.bak"
REPORT = ROOT / "collection_learning_report.json"
FEEDBACK = ROOT / "collection_feedback.json"
SCHEMA_VERSION = 2
MAX_QUERY_STATS = 500
MAX_TERM_STATS = 500
MAX_HOST_STATS = 300

GAME_CONFIG = {
    "포켓몬": {
        "canonical": "포켓몬 카드",
        "aliases": ("포켓몬", "포켓몬카드", "포켓몬 카드", "pokemon", "pokémon", "pokemon tcg", "ポケモン", "ポケカ"),
        "official_hosts": (
            "pokemonkorea.co.kr", "www.pokemonkorea.co.kr", "pokemoncard.co.kr", "www.pokemoncard.co.kr",
            "pokemon.co.jp", "www.pokemon.co.jp", "pokemon-card.com", "www.pokemon-card.com",
            "pokemon.com", "www.pokemon.com", "pokemongo.com", "www.pokemongo.com",
        ),
        "official_social": ("pokemonkrmkt", "pokemonkoreainc"),
    },
    "원피스": {
        "canonical": "원피스 카드",
        "aliases": ("원피스", "원피스카드", "원피스 카드", "one piece", "one piece card game", "ワンピース", "ワンピカード"),
        "official_hosts": (
            "onepiece-cardgame.kr", "www.onepiece-cardgame.kr", "onepiece-cardgame.com", "www.onepiece-cardgame.com",
            "en.onepiece-cardgame.com", "one-piece.com", "www.one-piece.com",
        ),
        "official_social": ("onepiece_tcg_kr", "onepiece_kr_"),
    },
    "나루토": {
        "canonical": "나루토 카드",
        "aliases": ("나루토", "나루토카드", "나루토 카드", "naruto", "naruto card game", "ナルト", "naruto tcg"),
        "official_hosts": (
            "naruto-cardgame.com", "www.naruto-cardgame.com", "naruto-official.com", "www.naruto-official.com",
        ),
        "official_social": ("narutotcg_jp", "narutotcg_eng", "naruto_tcg_en"),
    },
}

REGION_SEEDS = {
    "KR": {
        "event": ("행사", "이벤트", "프로모", "프로모카드", "콜라보", "팝업", "사전예약", "발매", "출시", "재발매", "한정", "증정", "대회", "야구", "영화"),
        "phrase": "행사 이벤트 프로모 프로모카드 콜라보 팝업 사전예약 발매 출시 재발매 한정 증정 대회 영화",
    },
    "JP": {
        "event": ("イベント", "プロモ", "プロモカード", "コラボ", "ポップアップ", "予約", "発売", "再販", "限定", "配布", "大会", "映画"),
        "phrase": "イベント プロモ プロモカード コラボ ポップアップ 予約 発売 再販 限定 配布 大会 映画",
    },
    "US": {
        "event": ("event", "promo", "promo card", "collab", "collaboration", "pop-up", "preorder", "release", "restock", "exclusive", "giveaway", "tournament", "movie"),
        "phrase": "event promo promo-card collab collaboration pop-up preorder release restock exclusive giveaway tournament movie",
    },
}

SOCIAL_SITES = ("x.com", "instagram.com", "youtube.com")
STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "card", "cards", "game", "official", "news",
    "카드", "카드게임", "관련", "공식", "안내", "이벤트", "행사", "프로모", "콜라보", "출시", "발매",
    "について", "公式", "カード", "ゲーム", "イベント", "発売",
}
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,24}|[가-힣]{2,12}|[ァ-ヶ一-龠]{2,12}")


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _bounded_int(value, default=0, low=0, high=1_000_000) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError, OverflowError):
        return default


def _bounded_float(value, default=0.0, low=-100.0, high=100.0) -> float:
    try:
        number = float(value)
        if not math.isfinite(number):
            return default
        return max(low, min(high, number))
    except (TypeError, ValueError, OverflowError):
        return default


def _host(url: str) -> str:
    try:
        return (urllib.parse.urlsplit(str(url or "")).hostname or "").lower()
    except ValueError:
        return ""


def _norm(text: object) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _signature(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.lower()).strip()[:600]
    return hashlib.sha1(normalized.encode("utf-8", "ignore")).hexdigest()[:16]


def canonical_game(keyword: object) -> str:
    text = _norm(keyword).lower()
    for short, cfg in GAME_CONFIG.items():
        if short in text or any(alias.lower() in text for alias in cfg["aliases"]):
            return short
    return text[:30] or "기타"


def _fresh_memory() -> dict:
    return {
        "version": SCHEMA_VERSION,
        "updated_at": None,
        "rotation": 0,
        "query_stats": {},
        "term_stats": {},
        "host_stats": {},
        "channel_stats": {},
        "feedback_seen": [],
        "totals": {"searches": 0, "results": 0, "relevant": 0, "official": 0, "errors": 0},
    }


def _sanitize_stat_map(value: object, *, kind: str) -> dict:
    if not isinstance(value, dict):
        return {}
    out = {}
    cap = MAX_QUERY_STATS if kind == "query" else MAX_TERM_STATS if kind == "term" else MAX_HOST_STATS
    for key, raw in list(value.items())[: cap * 2]:
        if not isinstance(key, str) or not isinstance(raw, dict):
            continue
        row = dict(raw)
        for field in ("runs", "hits", "relevant", "official", "cross_checked", "errors", "empty", "successes", "failures"):
            row[field] = _bounded_int(row.get(field))
        row["quality"] = _bounded_float(row.get("quality"), 0.0, -20.0, 20.0)
        row["score"] = _bounded_float(row.get("score"), 0.0, -50.0, 50.0)
        row["last_seen"] = row.get("last_seen") if isinstance(row.get("last_seen"), str) else None
        out[key[:500]] = row
    if len(out) > cap:
        ranked = sorted(out.items(), key=lambda kv: (_bounded_float(kv[1].get("score")), _bounded_int(kv[1].get("runs"))), reverse=True)
        out = dict(ranked[:cap])
    return out


def sanitize_memory(data: object) -> dict:
    if not isinstance(data, dict):
        return _fresh_memory()
    out = _fresh_memory()
    out["rotation"] = _bounded_int(data.get("rotation"), 0, 0, 10_000_000)
    out["query_stats"] = _sanitize_stat_map(data.get("query_stats"), kind="query")
    out["term_stats"] = _sanitize_stat_map(data.get("term_stats"), kind="term")
    out["host_stats"] = _sanitize_stat_map(data.get("host_stats"), kind="host")
    out["channel_stats"] = _sanitize_stat_map(data.get("channel_stats"), kind="host")
    seen = data.get("feedback_seen") if isinstance(data.get("feedback_seen"), list) else []
    out["feedback_seen"] = [str(x)[:80] for x in seen[-300:]]
    totals = data.get("totals") if isinstance(data.get("totals"), dict) else {}
    out["totals"] = {k: _bounded_int(totals.get(k)) for k in ("searches", "results", "relevant", "official", "errors")}
    out["updated_at"] = data.get("updated_at") if isinstance(data.get("updated_at"), str) else None
    return out


class AdaptiveCollectionLearner:
    def __init__(self, memory_path: Path | str = MEMORY, backup_path: Path | str | None = None, report_path: Path | str = REPORT):
        self.memory_path = Path(memory_path)
        self.backup_path = Path(backup_path) if backup_path else self.memory_path.with_suffix(self.memory_path.suffix + ".bak")
        self.report_path = Path(report_path)
        self.memory = self._load()

    def _load(self) -> dict:
        for path in (self.memory_path, self.backup_path):
            try:
                data = json.loads(safe_read_text(path))
                if isinstance(data, dict) and isinstance(data.get("query_stats", {}), dict):
                    return sanitize_memory(data)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
        return _fresh_memory()

    def save(self) -> None:
        self.memory["version"] = SCHEMA_VERSION
        self.memory["updated_at"] = _now()
        self.memory = sanitize_memory(self.memory)
        if self.memory_path.exists():
            try:
                old = json.loads(safe_read_text(self.memory_path))
                if isinstance(old, dict) and isinstance(old.get("query_stats", {}), dict):
                    atomic_write_json(self.backup_path, sanitize_memory(old), suffix=".learn.bak.tmp")
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pass
        atomic_write_json(self.memory_path, self.memory, suffix=".learn.tmp")
        atomic_write_json(self.report_path, self.report(), suffix=".learn.report.tmp")

    def _query_score(self, query: str) -> float:
        row = self.memory["query_stats"].get(_signature(query), {})
        quality = _bounded_float(row.get("quality"))
        runs = max(1, _bounded_int(row.get("runs"), 1))
        hits = max(1, _bounded_int(row.get("hits"), 1))
        error_rate = _bounded_int(row.get("errors")) / runs
        empty_rate = _bounded_int(row.get("empty")) / runs
        relevant_rate = _bounded_int(row.get("relevant")) / hits
        official_rate = _bounded_int(row.get("official")) / max(1, _bounded_int(row.get("relevant"), 1))
        exploration = 0.9 / math.sqrt(runs)
        # Use rates, not lifetime absolute failures, so mature high-volume queries are
        # not punished merely because they have been used for a long time.
        return (
            quality + exploration + min(1.2, relevant_rate * 0.8) + min(0.8, official_rate * 0.5)
            - min(1.8, error_rate * 2.0) - min(1.0, empty_rate * 0.8)
        )

    def _learned_terms(self, game: str, region: str, limit: int = 5) -> list[str]:
        prefix = f"{game}|{region}|"
        rows = []
        for key, stat in self.memory["term_stats"].items():
            if not key.startswith(prefix):
                continue
            term = key[len(prefix):]
            rows.append((self._term_score(stat), term))
        rows.sort(reverse=True)
        return [term for score, term in rows[:limit] if score > -2.0]

    @staticmethod
    def _term_score(row: dict) -> float:
        return (
            _bounded_float(row.get("score"))
            + _bounded_int(row.get("official")) * 0.8
            + _bounded_int(row.get("cross_checked")) * 0.35
            + _bounded_int(row.get("relevant")) * 0.08
            - _bounded_int(row.get("failures")) * 0.25
        )

    def plan_queries(self, keyword: str, max_queries: int | None = None) -> list[dict]:
        game = canonical_game(keyword)
        cfg = GAME_CONFIG.get(game)
        if not cfg:
            return [{"query": f"{_norm(keyword)[:80]} 카드 프로모 콜라보 이벤트", "family": "base", "region": "KR"}]
        is_android = "com.termux" in os.environ.get("PREFIX", "") or "ANDROID_ROOT" in os.environ
        budget = max_queries or (5 if is_android else 8)
        budget = max(3, min(12, int(budget)))
        rotation = _bounded_int(self.memory.get("rotation"))
        self.memory["rotation"] = rotation + 1
        canonical = cfg["canonical"]
        candidates: list[dict] = []

        # Three regional baselines prevent a KR-only success history from hiding JP/US news.
        regional_names = {
            "KR": canonical,
            "JP": next((x for x in cfg["aliases"] if re.search(r"[ァ-ヶ一-龠]", x)), canonical),
            "US": next((x for x in cfg["aliases"] if re.search(r"[A-Za-z]", x)), canonical),
        }
        for region in ("KR", "JP", "US"):
            learned = " ".join(self._learned_terms(game, region, 3))
            query = f"{regional_names[region]} {REGION_SEEDS[region]['phrase']} {learned}".strip()
            candidates.append({"query": query, "family": "regional", "region": region})

        # Cross-collector meta learning identifies the most under-covered
        # game/region/topic from event, stock, market and graded-photo outputs.
        # Only search-relevant topics are injected here; trust/verification remains separate.
        try:
            focus = collection_meta_learning.recommended_focus(game)
        except Exception:
            focus = None
        if isinstance(focus, dict):
            focus_region = str(focus.get("region") or "KR")
            if focus_region not in regional_names:
                focus_region = "KR"
            focus_topic = str(focus.get("topic") or "event")[:30]
            focus_terms = str(focus.get("terms") or REGION_SEEDS[focus_region]["phrase"])[:180]
            candidates.append({
                "query": f"{regional_names[focus_region]} {focus_terms}",
                "family": f"coverage-gap:{focus_topic}",
                "region": focus_region,
                "coverage_gap_score": float(focus.get("gap_score") or 0.0),
            })

        # Explicit platform probes catch posts/videos that news feeds index late.
        social_region = ("KR", "JP", "US")[rotation % 3]
        for site in SOCIAL_SITES:
            query = f"{regional_names[social_region]} {REGION_SEEDS[social_region]['phrase']} site:{site}"
            candidates.append({"query": query, "family": f"social:{site}", "region": social_region})

        # Official-domain probe rotates through known primary sites, preserving source authority.
        official_hosts = tuple(cfg.get("official_hosts") or ())
        if official_hosts:
            host = official_hosts[rotation % len(official_hosts)]
            region = ("KR", "JP", "US")[(rotation // max(1, len(official_hosts))) % 3]
            candidates.append({"query": f"{regional_names[region]} {REGION_SEEDS[region]['phrase']} site:{host}", "family": "official-site", "region": region})

        # Exploration: rotate one event concept that has little history. This is deliberate
        # anti-overfitting so new types such as baseball nights, pop-ups and movie promos
        # can still be discovered even if old searches favored tournaments.
        region = ("KR", "JP", "US")[(rotation + 1) % 3]
        seed_terms = list(REGION_SEEDS[region]["event"])
        explored = []
        for term in seed_terms:
            stat = self.memory["term_stats"].get(f"{game}|{region}|{term}", {})
            explored.append((_bounded_int(stat.get("runs")), self._term_score(stat), term))
        explored.sort(key=lambda row: (row[0], -row[1]))
        if explored:
            term = explored[rotation % min(len(explored), 6)][2]
            candidates.append({"query": f"{regional_names[region]} {term} 한정 카드 행사", "family": "exploration", "region": region})

        # Learned host discovery never upgrades trust, but a useful non-official host can
        # be queried as an extra lead source when it repeatedly yielded cross-checks.
        learned_hosts = []
        for host, row in self.memory["host_stats"].items():
            if host in official_hosts or host in SOCIAL_SITES:
                continue
            score = _bounded_float(row.get("score")) + _bounded_int(row.get("cross_checked")) * 0.5
            if score > 1.5:
                learned_hosts.append((score, host))
        if learned_hosts:
            learned_hosts.sort(reverse=True)
            host = learned_hosts[rotation % min(len(learned_hosts), 5)][1]
            candidates.append({"query": f"{canonical} 행사 프로모 콜라보 site:{host}", "family": "learned-host", "region": "KR"})

        # Deduplicate then favor historically useful query families while retaining the
        # first three regional baselines and at least one exploration/social query.
        dedup = []
        seen = set()
        for row in candidates:
            q = _norm(row["query"])[:280]
            key = q.lower()
            if not q or key in seen:
                continue
            seen.add(key)
            row = dict(row); row["query"] = q; row["learned_score"] = round(self._query_score(q), 4)
            dedup.append(row)
        baseline = dedup[:3]
        remainder = dedup[3:]
        remainder.sort(key=lambda row: row["learned_score"], reverse=True)
        # Rotate the tail before slicing to guarantee exploration over repeated runs.
        if remainder:
            shift = rotation % len(remainder)
            remainder = remainder[shift:] + remainder[:shift]
        chosen = baseline + remainder[: max(0, budget - len(baseline))]
        # Reserve one exploration slot for the learned coverage gap when possible.
        # This prevents historically successful KR/event queries from starving an
        # under-covered JP/US release/promo/collab/movie combination.
        focus_rows = [row for row in dedup if str(row.get("family") or "").startswith("coverage-gap:")]
        if focus_rows and budget > len(baseline) and not any(str(x.get("family") or "").startswith("coverage-gap:") for x in chosen):
            if len(chosen) >= budget:
                chosen[-1] = focus_rows[0]
            else:
                chosen.append(focus_rows[0])
        return chosen[:budget]

    def _is_official(self, game: str, url: str, title: str = "") -> bool:
        cfg = GAME_CONFIG.get(game, {})
        host = _host(url)
        if host in set(cfg.get("official_hosts") or ()):
            return True
        hay = f"{url} {title}".lower()
        return any(name in hay for name in cfg.get("official_social") or ())

    def relevance_score(self, game: str, title: str, url: str) -> float:
        cfg = GAME_CONFIG.get(game, {})
        text = f"{title} {url}".lower()
        aliases = cfg.get("aliases") or ()
        score = 0.0
        if any(alias.lower() in text for alias in aliases):
            score += 2.5
        event_terms = tuple(x.lower() for seed in REGION_SEEDS.values() for x in seed["event"])
        matches = sum(1 for term in event_terms if term in text)
        score += min(3.0, matches * 0.55)
        host = _host(url)
        host_stat = self.memory["host_stats"].get(host, {})
        score += max(-1.0, min(2.0, _bounded_float(host_stat.get("score")) * 0.2))
        if self._is_official(game, url, title):
            score += 4.0
        if host in SOCIAL_SITES:
            score += 0.4
        negative = ("wallpaper", "fanart", "cosplay only", "download apk", "torrent", "wiki fandom")
        if any(x in text for x in negative):
            score -= 2.0
        return round(score, 4)

    def rank_results(self, keyword: str, rows: Iterable[dict], limit: int = 10) -> list[dict]:
        game = canonical_game(keyword)
        merged = {}
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            title = _norm(raw.get("title"))[:240]
            url = _norm(raw.get("url"))[:900]
            if not title or not url.startswith("https://"):
                continue
            key = re.sub(r"[#?].*$", "", url).rstrip("/").lower()
            row = dict(raw)
            row["relevance_score"] = self.relevance_score(game, title, url)
            row["official_hint"] = self._is_official(game, url, title)
            old = merged.get(key)
            if old is None or row["relevance_score"] > old["relevance_score"]:
                merged[key] = row
        ranked = sorted(merged.values(), key=lambda x: (float(x.get("relevance_score") or 0), bool(x.get("official_hint"))), reverse=True)
        return ranked[: max(1, min(50, int(limit)))]

    def observe_search(self, keyword: str, query: str, rows: Iterable[dict], *, error: str = "", family: str = "web", region: str = "KR") -> dict:
        game = canonical_game(keyword)
        rows = list(rows)
        relevant_rows = [r for r in rows if self.relevance_score(game, str(r.get("title", "")), str(r.get("url", ""))) >= 2.6]
        official_rows = [r for r in relevant_rows if self._is_official(game, str(r.get("url", "")), str(r.get("title", "")))]
        qkey = _signature(query)
        qrow = self.memory["query_stats"].setdefault(qkey, {"query": query[:280], "family": family, "region": region, "game": game})
        qrow["runs"] = _bounded_int(qrow.get("runs")) + 1
        qrow["hits"] = _bounded_int(qrow.get("hits")) + len(rows)
        qrow["relevant"] = _bounded_int(qrow.get("relevant")) + len(relevant_rows)
        qrow["official"] = _bounded_int(qrow.get("official")) + len(official_rows)
        qrow["errors"] = _bounded_int(qrow.get("errors")) + (1 if error else 0)
        qrow["empty"] = _bounded_int(qrow.get("empty")) + (1 if not rows and not error else 0)
        sample_quality = len(relevant_rows) * 0.7 + len(official_rows) * 1.4 - (1.5 if error else 0.0) - (0.25 if not rows else 0.0)
        old_quality = _bounded_float(qrow.get("quality"), sample_quality)
        qrow["quality"] = round(old_quality * 0.72 + sample_quality * 0.28, 4)
        qrow["score"] = round(qrow["quality"] + min(2.0, _bounded_int(qrow.get("official")) * 0.1), 4)
        qrow["last_seen"] = _now()

        channel = self.memory["channel_stats"].setdefault(family, {})
        channel["runs"] = _bounded_int(channel.get("runs")) + 1
        channel["hits"] = _bounded_int(channel.get("hits")) + len(rows)
        channel["relevant"] = _bounded_int(channel.get("relevant")) + len(relevant_rows)
        channel["official"] = _bounded_int(channel.get("official")) + len(official_rows)
        channel["errors"] = _bounded_int(channel.get("errors")) + (1 if error else 0)
        channel["score"] = round((_bounded_int(channel.get("relevant")) + 2 * _bounded_int(channel.get("official"))) / max(1, _bounded_int(channel.get("runs"))) - _bounded_int(channel.get("errors")) * 0.15, 4)
        channel["last_seen"] = _now()

        totals = self.memory["totals"]
        totals["searches"] = _bounded_int(totals.get("searches")) + 1
        totals["results"] = _bounded_int(totals.get("results")) + len(rows)
        totals["relevant"] = _bounded_int(totals.get("relevant")) + len(relevant_rows)
        totals["official"] = _bounded_int(totals.get("official")) + len(official_rows)
        totals["errors"] = _bounded_int(totals.get("errors")) + (1 if error else 0)

        for row in relevant_rows:
            self._learn_row(game, region, row, weight=1.0, verified=bool(row.get("official_hint")))
        # The query itself teaches seed concepts enough to track exploration frequency.
        for term in REGION_SEEDS.get(region, REGION_SEEDS["KR"])["event"]:
            if term.lower() in query.lower():
                self._bump_term(game, region, term, relevant=len(relevant_rows), official=len(official_rows), weight=0.08, run=True)
        return {"results": len(rows), "relevant": len(relevant_rows), "official": len(official_rows), "error": bool(error)}

    def _extract_terms(self, game: str, text: str) -> list[str]:
        cfg = GAME_CONFIG.get(game, {})
        alias_tokens = {x.lower() for alias in cfg.get("aliases") or () for x in TOKEN_RE.findall(alias)}
        terms = []
        for token in TOKEN_RE.findall(_norm(text)):
            low = token.lower()
            if low in STOPWORDS or low in alias_tokens or len(low) < 2:
                continue
            if token not in terms:
                terms.append(token)
        return terms[:20]

    def _bump_term(self, game: str, region: str, term: str, *, relevant: int = 0, official: int = 0, cross_checked: int = 0, weight: float = 1.0, run: bool = False) -> None:
        key = f"{game}|{region}|{term[:50]}"
        row = self.memory["term_stats"].setdefault(key, {})
        if run:
            row["runs"] = _bounded_int(row.get("runs")) + 1
        row["relevant"] = _bounded_int(row.get("relevant")) + max(0, int(relevant))
        row["official"] = _bounded_int(row.get("official")) + max(0, int(official))
        row["cross_checked"] = _bounded_int(row.get("cross_checked")) + max(0, int(cross_checked))
        delta = weight * (0.2 + relevant * 0.25 + official * 0.8 + cross_checked * 0.35)
        row["score"] = round(max(-20.0, min(50.0, _bounded_float(row.get("score")) * 0.985 + delta)), 4)
        row["last_seen"] = _now()

    def _learn_row(self, game: str, region: str, row: dict, *, weight: float, verified: bool = False, cross_checked: bool = False) -> None:
        url = str(row.get("url") or row.get("source") or "")
        title = str(row.get("title") or row.get("name_ko") or row.get("name_native") or "")
        excerpt = str(row.get("excerpt") or row.get("reward") or row.get("condition") or "")
        host = _host(url)
        if host:
            stat = self.memory["host_stats"].setdefault(host, {})
            stat["runs"] = _bounded_int(stat.get("runs")) + 1
            stat["relevant"] = _bounded_int(stat.get("relevant")) + 1
            stat["official"] = _bounded_int(stat.get("official")) + (1 if verified or self._is_official(game, url, title) else 0)
            stat["cross_checked"] = _bounded_int(stat.get("cross_checked")) + (1 if cross_checked else 0)
            bonus = weight * (0.3 + (1.0 if stat["official"] else 0.0) + (0.5 if cross_checked else 0.0))
            stat["score"] = round(max(-20.0, min(50.0, _bounded_float(stat.get("score")) * 0.99 + bonus)), 4)
            stat["last_seen"] = _now()
        for region_name in (region,) if region in REGION_SEEDS else ("KR", "JP", "US"):
            for term in self._extract_terms(game, f"{title} {excerpt}"):
                self._bump_term(game, region_name, term, relevant=1, official=1 if verified else 0,
                                cross_checked=1 if cross_checked else 0, weight=weight)

    def learn_from_payload(self, payload: object, *, origin: str = "candidate") -> int:
        if not isinstance(payload, dict):
            return 0
        rows = payload.get("items")
        if not isinstance(rows, list):
            return 0
        learned = 0
        for raw in rows[:250]:
            if not isinstance(raw, dict):
                continue
            game = canonical_game(raw.get("game"))
            if game not in GAME_CONFIG:
                continue
            region = str(raw.get("region") or "KR")
            if region not in REGION_SEEDS:
                region = "KR"
            verified = bool(raw.get("verified") is True or raw.get("source_grade") == "official" or raw.get("official_domain_match") is True or raw.get("official_account_verified") is True)
            cross_checked = bool(raw.get("cross_checked") is True or _bounded_int(raw.get("independent_source_count")) >= 2)
            weight = 1.5 if verified else 0.9 if cross_checked else 0.25
            # Weak discovery-only rows may teach vocabulary a little, never authority.
            self._learn_row(game, region, raw, weight=weight, verified=verified, cross_checked=cross_checked)
            learned += 1
        channel = self.memory["channel_stats"].setdefault(f"payload:{origin[:40]}", {})
        channel["runs"] = _bounded_int(channel.get("runs")) + 1
        channel["hits"] = _bounded_int(channel.get("hits")) + learned
        channel["score"] = round(_bounded_float(channel.get("score")) * 0.95 + min(5.0, learned * 0.02), 4)
        channel["last_seen"] = _now()
        return learned

    def learn_feedback_file(self, feedback_path: Path | str = FEEDBACK) -> int:
        path = Path(feedback_path)
        if not path.exists():
            return 0
        try:
            data = json.loads(safe_read_text(path))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return 0
        rows = data.get("items", []) if isinstance(data, dict) else []
        if not isinstance(rows, list):
            return 0
        seen = set(self.memory.get("feedback_seen", []))
        learned = 0
        for raw in rows[-300:]:
            if not isinstance(raw, dict):
                continue
            marker = str(raw.get("id") or _signature(json.dumps(raw, ensure_ascii=False, sort_keys=True)))[:80]
            if marker in seen:
                continue
            game = canonical_game(raw.get("game"))
            if game not in GAME_CONFIG:
                continue
            region = str(raw.get("region") or "KR")
            if region not in REGION_SEEDS:
                region = "KR"
            verdict = str(raw.get("verdict") or "missed").lower()
            if verdict in {"false_positive", "irrelevant", "reject"}:
                # Negative feedback only penalizes terms/query signatures; it never blacklists
                # an entire domain after a single correction.
                for term in self._extract_terms(game, f"{raw.get('title','')} {raw.get('excerpt','')}"):
                    key = f"{game}|{region}|{term[:50]}"
                    stat = self.memory["term_stats"].setdefault(key, {})
                    stat["failures"] = _bounded_int(stat.get("failures")) + 1
                    stat["score"] = round(_bounded_float(stat.get("score")) - 0.8, 4)
                    stat["last_seen"] = _now()
            else:
                # A user/officially corrected missed event is the strongest signal for
                # future query vocabulary but still does not mark arbitrary hosts official.
                self._learn_row(game, region, raw, weight=2.0, verified=bool(raw.get("verified")), cross_checked=bool(raw.get("cross_checked")))
            seen.add(marker); learned += 1
        self.memory["feedback_seen"] = list(seen)[-300:]
        return learned

    def report(self) -> dict:
        query_rows = []
        for row in self.memory.get("query_stats", {}).values():
            if not isinstance(row, dict):
                continue
            query_rows.append({
                "game": row.get("game"), "region": row.get("region"), "family": row.get("family"),
                "query": row.get("query"), "runs": _bounded_int(row.get("runs")),
                "relevant": _bounded_int(row.get("relevant")), "official": _bounded_int(row.get("official")),
                "errors": _bounded_int(row.get("errors")), "quality": round(_bounded_float(row.get("quality")), 3),
            })
        query_rows.sort(key=lambda x: (x["quality"], x["official"], x["relevant"]), reverse=True)
        hosts = []
        for host, row in self.memory.get("host_stats", {}).items():
            hosts.append({"host": host, "score": round(_bounded_float(row.get("score")), 3),
                          "official_hits": _bounded_int(row.get("official")), "cross_checked": _bounded_int(row.get("cross_checked")),
                          "relevant": _bounded_int(row.get("relevant"))})
        hosts.sort(key=lambda x: (x["score"], x["official_hits"], x["cross_checked"]), reverse=True)
        terms = []
        for key, row in self.memory.get("term_stats", {}).items():
            parts = key.split("|", 2)
            if len(parts) != 3:
                continue
            terms.append({"game": parts[0], "region": parts[1], "term": parts[2], "score": round(self._term_score(row), 3),
                          "official_hits": _bounded_int(row.get("official")), "cross_checked": _bounded_int(row.get("cross_checked"))})
        terms.sort(key=lambda x: (x["score"], x["official_hits"], x["cross_checked"]), reverse=True)
        return {
            "version": SCHEMA_VERSION,
            "updated_at": _now(),
            "policy": "수집전략만 자가학습. 반복 발견만으로 출처를 공식승격하지 않으며 공식도메인/SNS 검증정책은 별도 유지.",
            "anti_blindspot": "KR/JP/US 기본 검색 + 공식도메인 + X/Instagram/YouTube + 저사용 검색어 탐색을 회전하여 성공기록 과적합 방지.",
            "memory_file": self.memory_path.name,
            "totals": dict(self.memory.get("totals", {})),
            "learned_queries": len(self.memory.get("query_stats", {})),
            "learned_terms": len(self.memory.get("term_stats", {})),
            "learned_hosts": len(self.memory.get("host_stats", {})),
            "top_queries": query_rows[:15],
            "top_terms": terms[:30],
            "top_hosts": hosts[:20],
            "channel_stats": self.memory.get("channel_stats", {}),
        }


def main() -> dict:
    learner = AdaptiveCollectionLearner()
    learner.learn_feedback_file()
    learner.save()
    return learner.report()


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False, indent=2))
