#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v145 bounded source-coverage expansion and learned-host targeting.

This layer increases discovery breadth without weakening source trust.

Goals
-----
* Cover more publisher, retailer, official-store, tournament-platform and press
  domains for Pokemon / ONE PIECE / NARUTO across KR / JP / US.
* Reuse source hosts that previously participated in an officially verified or
  independently cross-checked event, scoped to the exact game + region that
  produced the evidence.
* Rotate large site lists in bounded 8-host windows so Termux does not hammer all
  sources every cycle or create avoidable 403/429 bursts.
* Learn whether a scoped learned-host query succeeds or returns nothing without
  mistaking Bing/search-provider transport failures for target-host failures.
* Never auto-promote a learned/static discovery host to official/trusted/verified.

The existing v142 anti-poisoning layer remains authoritative. v145 adds a second
fail-closed guard: unverified direct _learn_row calls cannot create persistent
host/term learning, and learned-host evidence is isolated per exact game+region.
"""
from __future__ import annotations

import datetime as dt
import ipaddress
import json
import math
import os
import re
import threading
import urllib.parse
from pathlib import Path

import adaptive_collection_learner
import collection_learning_hardening_v142 as learning_guard
import multi_route_event_discovery
from safe_runtime import safe_read_text

ROOT = Path(__file__).resolve().parent
MANUAL_EVIDENCE = ROOT / "manual_event_evidence.json"
PROMO_EVENTS = ROOT / "promo_events.json"
PATCH_ID = 145
ROTATION_HOURS = 6
MAX_SCOPED_HOSTS_PER_QUERY = 8
PINNED_HOSTS_PER_QUERY = 4
MAX_TARGETS_PER_CELL = 24
MAX_LEARNED_TARGETS_PER_CELL = 5
MAX_EVIDENCE_ROWS = 1_200
MAX_EVIDENCE_SOURCES_PER_ROW = 24

# Discovery-only targets. Presence here NEVER means official/trusted. Primary
# brand authority is still controlled by OFFICIAL_ROUTES / GAME_CONFIG and the
# verified social registry.
STATIC_DISCOVERY_TARGETS = {
    ("포켓몬 카드", "KR"): (
        "emart.ssg.com", "ssg.com", "lotteon.com", "lottemart.com",
        "toysrus.lottemart.com", "pokemon-go.com",
    ),
    ("포켓몬 카드", "JP"): (
        "pokemoncenter-online.com", "www.pokemoncenter-online.com",
        "players.pokemon-card.com", "pokemon.co.jp", "www.pokemon.co.jp",
    ),
    ("포켓몬 카드", "US"): (
        "pokemoncenter.com", "www.pokemoncenter.com", "events.pokemon.com",
        "target.com", "walmart.com", "gamestop.com", "bestbuy.com",
        "barnesandnoble.com",
    ),
    ("원피스 카드", "KR"): (
        "bandainamcokorea.co.kr", "www.bandainamcokorea.co.kr",
        "playgo.bandainamcokorea.co.kr", "seoulmediacomics.com",
        "www.seoulmediacomics.com", "shinsegae.com", "www.shinsegae.com",
        "lotteon.com", "lottemart.com", "toysrus.lottemart.com",
    ),
    ("원피스 카드", "JP"): (
        "p-bandai.jp", "bandai-tcg-plus.com", "www.bandai-tcg-plus.com",
        "shonenjump.com", "www.shonenjump.com", "sp.shonenjump.com",
        "shueisha.co.jp", "www.shueisha.co.jp", "jumpcs.shueisha.co.jp",
        "nike.com", "www.nike.com",
    ),
    ("원피스 카드", "US"): (
        "bandai.com", "www.bandai.com", "bandai-tcg-plus.com",
        "www.bandai-tcg-plus.com", "p-bandai.com", "www.p-bandai.com",
        "target.com", "walmart.com", "gamestop.com", "barnesandnoble.com",
        "viz.com", "www.viz.com",
    ),
    ("나루토 카드", "KR"): (
        "bandainamcokorea.co.kr", "www.bandainamcokorea.co.kr",
        "playgo.bandainamcokorea.co.kr", "seoulmediacomics.com",
        "www.seoulmediacomics.com", "shinsegae.com", "www.shinsegae.com",
        "lotteon.com", "lottemart.com", "toysrus.lottemart.com",
    ),
    ("나루토 카드", "JP"): (
        "bandai-tcg-plus.com", "www.bandai-tcg-plus.com", "p-bandai.jp",
        "shonenjump.com", "www.shonenjump.com", "sp.shonenjump.com",
        "shueisha.co.jp", "www.shueisha.co.jp", "jumpcs.shueisha.co.jp",
    ),
    ("나루토 카드", "US"): (
        "bandai.com", "www.bandai.com", "bandai-tcg-plus.com",
        "www.bandai-tcg-plus.com", "p-bandai.com", "www.p-bandai.com",
        "target.com", "walmart.com", "gamestop.com", "barnesandnoble.com",
        "viz.com", "www.viz.com",
    ),
}

PRESS_ADDITIONS = {
    "KR": (
        "hankyung.com", "biz.chosun.com", "mk.co.kr", "etnews.com",
        "sedaily.com", "sports.donga.com",
    ),
    "JP": (
        "game.watch.impress.co.jp", "hobby.watch.impress.co.jp", "4gamer.net",
        "natalie.mu", "mantan-web.jp", "oricon.co.jp",
    ),
    "US": (
        "icv2.com", "animenewsnetwork.com", "gamespot.com", "ign.com",
        "polygon.com",
    ),
}

GAME_LABEL_TO_SHORT = {
    "포켓몬 카드": "포켓몬",
    "원피스 카드": "원피스",
    "나루토 카드": "나루토",
}
SHORT_TO_GAME_LABEL = {value: key for key, value in GAME_LABEL_TO_SHORT.items()}

# Search engines, APIs and social networks are handled by dedicated collectors.
# They must not become generic learned-host site probes.
EXCLUDED_LEARNED_HOSTS = {
    "google.com", "www.google.com", "news.google.com", "bing.com", "www.bing.com",
    "duckduckgo.com", "www.duckduckgo.com", "html.duckduckgo.com",
    "x.com", "www.x.com", "twitter.com", "www.twitter.com",
    "instagram.com", "www.instagram.com", "youtube.com", "www.youtube.com", "youtu.be",
    "facebook.com", "www.facebook.com", "tiktok.com", "www.tiktok.com",
    "threads.net", "www.threads.net", "twitch.tv", "www.twitch.tv",
}

_APPLIED = False
_APPLY_LOCK = threading.RLock()
_STATE_LOCK = threading.RLock()
_COLLECT_LOCK = threading.Lock()
_ORIGINAL_ROUTE_QUERY = None
_ORIGINAL_BING_ONE = None
_ORIGINAL_COLLECT_ALL = None
_ORIGINAL_ADAPTIVE_INIT = None
_ORIGINAL_ADAPTIVE_LEARN_ROW = None
_ORIGINAL_ADAPTIVE_PLAN = None
_ORIGINAL_ADAPTIVE_OBSERVE = None
_RUNTIME_TARGETS: dict[tuple[str, str], tuple[str, ...]] = {}
_LEARNED_TARGETS: dict[tuple[str, str], set[str]] = {}
_LAST_SELECTED: dict[str, tuple[str, ...]] = {}


def _bounded_int(value, default=0, low=0, high=1_000_000) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError, OverflowError):
        return default


def _bounded_float(value, default=0.0, low=-50.0, high=50.0) -> float:
    try:
        number = float(value)
        return max(low, min(high, number)) if math.isfinite(number) else default
    except (TypeError, ValueError, OverflowError):
        return default


def _host(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "://" not in text:
        text = "https://" + text
    try:
        host = (urllib.parse.urlsplit(text).hostname or "").strip().lower().rstrip(".")
    except ValueError:
        return ""
    if not host or len(host) > 253 or host == "localhost" or host.endswith(".local"):
        return ""
    try:
        ipaddress.ip_address(host)
        return ""
    except ValueError:
        pass
    if not re.fullmatch(r"[a-z0-9.-]+", host):
        return ""
    labels = host.split(".")
    if len(labels) < 2 or any(
        not label or len(label) > 63 or label.startswith("-") or label.endswith("-")
        for label in labels
    ):
        return ""
    return host


def _host_key(value: object) -> str:
    """Canonical comparison key without broadening arbitrary subdomains."""
    host = _host(value)
    return host.removeprefix("www.") if host else ""


def _merge_hosts(*groups, cap: int = MAX_TARGETS_PER_CELL) -> tuple[str, ...]:
    """Merge valid hosts while treating www/non-www aliases as one search target."""
    out: list[str] = []
    seen: set[str] = set()
    safe_cap = max(1, _bounded_int(cap, MAX_TARGETS_PER_CELL, 1, 100))
    for group in groups:
        for value in group or ():
            host = _host(value)
            key = _host_key(host)
            if host and key and key not in seen:
                out.append(host)
                seen.add(key)
            if len(out) >= safe_cap:
                return tuple(out)
    return tuple(out)


def _source_values(row: dict) -> list[str]:
    values = [row.get("source"), row.get("url"), row.get("publisher_url"), row.get("verification_source")]
    for field in ("evidence_sources", "evidence_hosts"):
        evidence = row.get(field)
        if isinstance(evidence, (list, tuple)):
            values.extend(evidence[:MAX_EVIDENCE_SOURCES_PER_ROW])
    return [str(value) for value in values if value]


def _evidence_host_keys(row: dict) -> set[str]:
    return {key for value in _source_values(row) if (key := _host_key(value))}


def _strong_evidence_row(row: dict) -> bool:
    """Require strong event evidence before a host may affect discovery planning.

    Self-declared ``source_grade=official`` or ``official_domain_match=True`` alone
    is insufficient. Official rows must also be verified; cross-check rows must
    carry at least two concrete host evidences and a high-confidence non-community
    classification.
    """
    game = str(row.get("game") or "")
    region = str(row.get("region") or "")
    if game not in GAME_LABEL_TO_SHORT or region not in {"KR", "JP", "US"}:
        return False

    source_host = _host(row.get("source") or row.get("url") or row.get("publisher_url"))
    actual_official_domain = bool(
        source_host and multi_route_event_discovery._official_for(game, region, source_host)
    )
    official_social = row.get("official_account_verified") is True
    if row.get("verified") is True and (actual_official_domain or official_social):
        return True

    if row.get("cross_checked") is not True:
        return False
    if row.get("fan_candidate") is True or str(row.get("source_tier") or "").lower().startswith("c-community"):
        return False
    if len(_evidence_host_keys(row)) < 2:
        return False
    try:
        confidence = float(row.get("confidence") or 0.0)
    except (TypeError, ValueError, OverflowError):
        confidence = 0.0
    return math.isfinite(confidence) and confidence >= 0.78


def _bounded_evidence_rows(rows: object, limit: int = MAX_EVIDENCE_ROWS) -> list[dict]:
    """Cover both head and tail so append/prepend ordering cannot hide new evidence."""
    if not isinstance(rows, list):
        return []
    safe_limit = max(1, min(2_000, _bounded_int(limit, MAX_EVIDENCE_ROWS, 1, 2_000)))
    valid = [row for row in rows if isinstance(row, dict)]
    if len(valid) <= safe_limit:
        return valid
    head = safe_limit // 2
    return valid[:head] + valid[-(safe_limit - head):]


def _verified_file_targets() -> dict[tuple[str, str], set[str]]:
    """Recover discovery hosts from strong evidence without trust promotion."""
    out: dict[tuple[str, str], set[str]] = {}
    sources = (
        (MANUAL_EVIDENCE, 1_000_000, True),
        (PROMO_EVENTS, 3_000_000, False),
    )
    excluded = {_host_key(x) for x in EXCLUDED_LEARNED_HOSTS}
    for path, max_bytes, manual_only in sources:
        try:
            payload = json.loads(safe_read_text(path, max_bytes=max_bytes))
        except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError):
            continue
        rows = payload.get("items", []) if isinstance(payload, dict) else []
        for row in _bounded_evidence_rows(rows):
            if manual_only and row.get("manual_evidence") is not True:
                continue
            if not _strong_evidence_row(row):
                continue
            game = str(row.get("game") or "")
            region = str(row.get("region") or "")
            key = (game, region)
            bucket = out.setdefault(key, set())
            for value in _source_values(row):
                host = _host(value)
                canonical = _host_key(host)
                if (
                    host
                    and canonical
                    and canonical not in excluded
                    and not multi_route_event_discovery._official_for(game, region, host)
                ):
                    bucket.add(canonical)
    return out


def _sanitize_scope_map(raw: object) -> dict[str, int]:
    if not isinstance(raw, dict):
        return {}
    clean: dict[str, int] = {}
    allowed_games = set(adaptive_collection_learner.GAME_CONFIG)
    allowed_regions = set(adaptive_collection_learner.REGION_SEEDS)
    for key, value in list(raw.items())[:36]:
        if not isinstance(key, str) or "|" not in key:
            continue
        game, region = key.split("|", 1)
        if game not in allowed_games or region not in allowed_regions:
            continue
        count = _bounded_int(value)
        if count > 0:
            clean[f"{game}|{region}"] = count
    return clean


def _scope_map(stat: dict, field: str) -> dict[str, int]:
    clean = _sanitize_scope_map(stat.get(field))
    stat[field] = clean
    return clean


def _sanitize_adaptive_host_scopes(learner) -> None:
    hosts = learner.memory.get("host_stats") if isinstance(getattr(learner, "memory", None), dict) else None
    if not isinstance(hosts, dict):
        return
    for host in list(hosts):
        row = hosts.get(host)
        clean_host = _host(host)
        if not clean_host or clean_host != host or not isinstance(row, dict):
            hosts.pop(host, None)
            continue
        scopes = _scope_map(row, "game_regions")
        verified_scopes = _scope_map(row, "game_region_verified")
        cross_scopes = _scope_map(row, "game_region_cross_checked")
        _scope_map(row, "game_region_probe_relevant")
        _scope_map(row, "game_region_probe_empty")
        _scope_map(row, "game_region_probe_errors")

        # Safe one-scope migration from the first v145 schema. If a host had
        # multiple scopes, old global counters cannot prove which scope earned
        # the evidence, so fail closed until fresh scoped evidence arrives.
        if len(scopes) == 1 and not verified_scopes and not cross_scopes:
            only_scope = next(iter(scopes))
            old_verified = _bounded_int(row.get("scoped_verified"))
            old_cross = _bounded_int(row.get("scoped_cross_checked"))
            if old_verified:
                verified_scopes[only_scope] = old_verified
            if old_cross:
                cross_scopes[only_scope] = old_cross
            row["game_region_verified"] = verified_scopes
            row["game_region_cross_checked"] = cross_scopes

        row["scoped_verified"] = sum(verified_scopes.values())
        row["scoped_cross_checked"] = sum(cross_scopes.values())


def _record_scope(self, host: str, game: str, region: str, *, verified: bool, cross_checked: bool,
                  extra_evidence: bool, weight: float) -> None:
    host = _host(host)
    if not host or game not in adaptive_collection_learner.GAME_CONFIG or region not in adaptive_collection_learner.REGION_SEEDS:
        return
    host_stats = self.memory.setdefault("host_stats", {})
    if not isinstance(host_stats, dict):
        self.memory["host_stats"] = {}
        host_stats = self.memory["host_stats"]
    stat = host_stats.setdefault(host, {})
    if not isinstance(stat, dict):
        stat = {}
        host_stats[host] = stat

    scope_key = f"{game}|{region}"
    scopes = _scope_map(stat, "game_regions")
    scopes[scope_key] = _bounded_int(scopes.get(scope_key)) + 1
    stat["game_regions"] = scopes

    verified_scopes = _scope_map(stat, "game_region_verified")
    cross_scopes = _scope_map(stat, "game_region_cross_checked")
    if verified:
        verified_scopes[scope_key] = _bounded_int(verified_scopes.get(scope_key)) + 1
    if cross_checked:
        cross_scopes[scope_key] = _bounded_int(cross_scopes.get(scope_key)) + 1
    stat["game_region_verified"] = verified_scopes
    stat["game_region_cross_checked"] = cross_scopes
    stat["scoped_verified"] = sum(verified_scopes.values())
    stat["scoped_cross_checked"] = sum(cross_scopes.values())

    # Extra evidence URLs did not pass through the original _learn_row host path.
    # Preserve them only when the parent event itself is verified/cross-checked.
    if extra_evidence and (verified or cross_checked):
        stat["runs"] = _bounded_int(stat.get("runs")) + 1
        stat["relevant"] = _bounded_int(stat.get("relevant")) + 1
        # This only means the host participated in a strong evidence chain. It
        # does NOT make the domain an official brand authority.
        stat["cross_checked"] = _bounded_int(stat.get("cross_checked")) + 1
        safe_weight = _bounded_float(weight, 0.0, 0.0, 2.5)
        delta = safe_weight * (0.55 if verified else 0.35)
        stat["score"] = round(max(-20.0, min(50.0, _bounded_float(stat.get("score")) * 0.99 + delta)), 4)
    stat["last_seen"] = adaptive_collection_learner._now()


def _v145_adaptive_init(self, *args, **kwargs):
    _ORIGINAL_ADAPTIVE_INIT(self, *args, **kwargs)
    _sanitize_adaptive_host_scopes(self)


def _v145_learn_row(self, game: str, region: str, row: dict, *, weight: float,
                    verified: bool = False, cross_checked: bool = False) -> None:
    # v142 intends unverified host/term learning weight to be zero. Enforce that
    # invariant even if a future/legacy caller invokes _learn_row directly.
    if not (bool(verified) or bool(cross_checked)):
        channels = self.memory.setdefault("channel_stats", {})
        if not isinstance(channels, dict):
            self.memory["channel_stats"] = {}
            channels = self.memory["channel_stats"]
        safety = channels.setdefault("v145_source_scope_safety", {})
        if not isinstance(safety, dict):
            safety = {}
            channels["v145_source_scope_safety"] = safety
        safety["ignored_unverified_learn_rows"] = _bounded_int(safety.get("ignored_unverified_learn_rows")) + 1
        safety["last_seen"] = adaptive_collection_learner._now()
        return

    _ORIGINAL_ADAPTIVE_LEARN_ROW(
        self, game, region, row, weight=weight, verified=verified, cross_checked=cross_checked
    )
    primary = _host(row.get("url") or row.get("source"))
    if primary:
        _record_scope(
            self, primary, game, region,
            verified=bool(verified), cross_checked=bool(cross_checked), extra_evidence=False, weight=weight,
        )
    seen = {_host_key(primary)} if primary else set()
    excluded = {_host_key(x) for x in EXCLUDED_LEARNED_HOSTS}
    extras = [row.get("publisher_url"), row.get("verification_source")]
    evidence = row.get("evidence_sources")
    if isinstance(evidence, (list, tuple)):
        extras.extend(evidence[:MAX_EVIDENCE_SOURCES_PER_ROW])
    for value in extras:
        host = _host(value)
        key = _host_key(host)
        if not host or not key or key in seen or key in excluded:
            continue
        seen.add(key)
        _record_scope(
            self, host, game, region,
            verified=bool(verified), cross_checked=bool(cross_checked), extra_evidence=True, weight=weight,
        )


def _scoped_learned_hosts(learner, game: str, limit: int = MAX_LEARNED_TARGETS_PER_CELL):
    cfg = adaptive_collection_learner.GAME_CONFIG.get(game, {})
    official = {_host_key(x) for x in (cfg.get("official_hosts") or ())}
    excluded = {_host_key(x) for x in EXCLUDED_LEARNED_HOSTS}
    rows = []
    seen_pairs: set[tuple[str, str]] = set()
    host_stats = learner.memory.get("host_stats") if isinstance(getattr(learner, "memory", None), dict) else {}
    if not isinstance(host_stats, dict):
        return []

    for host, stat in host_stats.items():
        canonical = _host_key(host)
        if not isinstance(stat, dict) or not canonical or canonical in excluded or canonical in official:
            continue
        scopes = _sanitize_scope_map(stat.get("game_regions"))
        verified_scopes = _sanitize_scope_map(stat.get("game_region_verified"))
        cross_scopes = _sanitize_scope_map(stat.get("game_region_cross_checked"))
        relevant_scopes = _sanitize_scope_map(stat.get("game_region_probe_relevant"))
        empty_scopes = _sanitize_scope_map(stat.get("game_region_probe_empty"))

        for scope_key, count in scopes.items():
            if not scope_key.startswith(game + "|"):
                continue
            _, region = scope_key.split("|", 1)
            scoped_verified = _bounded_int(verified_scopes.get(scope_key))
            scoped_cross = _bounded_int(cross_scopes.get(scope_key))
            if scoped_verified + scoped_cross <= 0:
                continue
            pair = (canonical, region)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            scoped_relevant = _bounded_int(relevant_scopes.get(scope_key))
            scoped_empty = _bounded_int(empty_scopes.get(scope_key))
            score = (
                max(-1.0, min(2.0, _bounded_float(stat.get("score")) * 0.15))
                + scoped_verified * 0.80
                + scoped_cross * 0.55
                + min(1.5, _bounded_int(count) * 0.08)
                + min(1.5, scoped_relevant * 0.12)
                - min(1.5, scoped_empty * 0.08)
            )
            if score > 0.25:
                rows.append((score, _bounded_int(count), canonical, region))
    rows.sort(reverse=True)
    safe_limit = max(1, min(12, _bounded_int(limit, MAX_LEARNED_TARGETS_PER_CELL, 1, 12)))
    return rows[:safe_limit]


def _regional_name(game: str, region: str) -> str:
    cfg = adaptive_collection_learner.GAME_CONFIG.get(game, {})
    canonical = str(cfg.get("canonical") or game)
    aliases = tuple(cfg.get("aliases") or ())
    if region == "JP":
        return next((x for x in aliases if re.search(r"[ァ-ヶ一-龠]", x)), canonical)
    if region == "US":
        return next((x for x in aliases if re.search(r"[A-Za-z]", x)), canonical)
    return canonical


def _v145_plan_queries(self, keyword: str, max_queries: int | None = None) -> list[dict]:
    rows = [dict(row) for row in _ORIGINAL_ADAPTIVE_PLAN(self, keyword, max_queries=max_queries)]
    game = adaptive_collection_learner.canonical_game(keyword)
    if game not in adaptive_collection_learner.GAME_CONFIG:
        return rows

    budget = max_queries or (5 if ("com.termux" in os.environ.get("PREFIX", "") or "ANDROID_ROOT" in os.environ) else 8)
    budget = max(3, min(12, _bounded_int(budget, 8, 3, 12)))

    # v145 rejects legacy learned-host probes with no exact game/region evidence.
    removed = [row for row in rows if str(row.get("family") or "") == "learned-host"]
    rows = [row for row in rows if str(row.get("family") or "") != "learned-host"]
    scoped = _scoped_learned_hosts(self, game, limit=5)
    if scoped:
        rotation = adaptive_collection_learner._bounded_int(self.memory.get("rotation"))
        score, _, host, region = scoped[rotation % len(scoped)]
        query = f"{_regional_name(game, region)} {adaptive_collection_learner.REGION_SEEDS[region]['phrase']} site:{host}"
        candidate = {
            "query": adaptive_collection_learner._norm(query)[:280],
            "family": "learned-host",
            "region": region,
            "learned_host": host,
            "source_scope_verified": True,
            "source_scope_strong_evidence": True,
            "learned_score": round(float(score), 4),
        }
        if removed or len(rows) < budget:
            rows.append(candidate)
        elif budget >= 6:
            # Replace only a low-priority exploration row; never remove the three
            # regional baselines or a reserved social/coverage-gap query.
            replace = next(
                (i for i in range(len(rows) - 1, 2, -1) if rows[i].get("family") in {"exploration", "official-site"}),
                None,
            )
            if replace is not None:
                rows[replace] = candidate
    # Important: if the original planner produced fewer rows than its budget,
    # retain the newly-added scoped probe instead of slicing back to old length.
    return rows[:budget]


def _site_host_from_query(query: str) -> str:
    match = re.search(r"(?:^|\s)site:([A-Za-z0-9.-]+)", str(query or ""), re.I)
    return _host(match.group(1)) if match else ""


def _bump_scope_counter(stat: dict, field: str, scope_key: str, amount: int = 1) -> None:
    values = _scope_map(stat, field)
    values[scope_key] = _bounded_int(values.get(scope_key)) + max(0, _bounded_int(amount))
    stat[field] = values


def _v145_observe_search(self, keyword: str, query: str, rows, *, error: str = "", family: str = "web", region: str = "KR") -> dict:
    result = _ORIGINAL_ADAPTIVE_OBSERVE(
        self, keyword, query, rows, error=error, family=family, region=region
    )
    if str(family) != "learned-host":
        return result
    host = _site_host_from_query(query)
    stat = self.memory.get("host_stats", {}).get(host) if host else None
    if not isinstance(stat, dict) and host:
        # Memory may contain the www alias while the query uses the canonical host.
        key = _host_key(host)
        host_stats = self.memory.get("host_stats") or {}
        if isinstance(host_stats, dict):
            for candidate_host, candidate_stat in host_stats.items():
                if _host_key(candidate_host) == key and isinstance(candidate_stat, dict):
                    stat = candidate_stat
                    break
    if not isinstance(stat, dict):
        return result

    game = adaptive_collection_learner.canonical_game(keyword)
    if game not in adaptive_collection_learner.GAME_CONFIG or region not in adaptive_collection_learner.REGION_SEEDS:
        return result
    scope_key = f"{game}|{region}"
    relevant = _bounded_int(result.get("relevant")) if isinstance(result, dict) else 0

    if error:
        # This query is executed through a search provider. Timeout/403/429 here
        # says the provider/probe failed, not that the learned target host is bad.
        stat["probe_errors"] = _bounded_int(stat.get("probe_errors")) + 1
        _bump_scope_counter(stat, "game_region_probe_errors", scope_key)
        delta = 0.0
        decay = 1.0
    else:
        stat["probe_successes"] = _bounded_int(stat.get("probe_successes")) + 1
        stat["successes"] = _bounded_int(stat.get("successes")) + 1
        if relevant:
            _bump_scope_counter(stat, "game_region_probe_relevant", scope_key, relevant)
            delta = min(0.70, relevant * 0.18)
        else:
            stat["empty_probes"] = _bounded_int(stat.get("empty_probes")) + 1
            _bump_scope_counter(stat, "game_region_probe_empty", scope_key)
            delta = -0.08
        decay = 0.99
    stat["score"] = round(max(-20.0, min(50.0, _bounded_float(stat.get("score")) * decay + delta)), 4)
    stat["last_seen"] = adaptive_collection_learner._now()
    return result


def _adaptive_targets() -> dict[tuple[str, str], set[str]]:
    out: dict[tuple[str, str], set[str]] = {}
    try:
        learner = adaptive_collection_learner.AdaptiveCollectionLearner()
    except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError, AttributeError):
        return out
    for short_game, game_label in SHORT_TO_GAME_LABEL.items():
        for _, _, host, region in _scoped_learned_hosts(learner, short_game, limit=12):
            canonical = _host_key(host)
            if canonical:
                out.setdefault((game_label, region), set()).add(canonical)
    return out


def _balanced_runtime_hosts(existing, verified_hosts, adaptive_hosts, static_hosts, *, cap: int = MAX_TARGETS_PER_CELL) -> tuple[str, ...]:
    """Preserve four baseline targets, then fairly fill all discovery families."""
    safe_cap = max(1, min(100, _bounded_int(cap, MAX_TARGETS_PER_CELL, 1, 100)))
    baseline = list(_merge_hosts(existing, cap=min(PINNED_HOSTS_PER_QUERY, safe_cap)))
    out = list(baseline)
    seen = {_host_key(host) for host in out}

    groups = [
        list(_merge_hosts(verified_hosts, cap=safe_cap)),
        list(_merge_hosts(adaptive_hosts, cap=safe_cap)),
        list(_merge_hosts(static_hosts, cap=safe_cap)),
        list(_merge_hosts(existing, cap=safe_cap))[len(baseline):],
    ]
    positions = [0] * len(groups)
    while len(out) < safe_cap:
        progressed = False
        for idx, group in enumerate(groups):
            while positions[idx] < len(group):
                host = group[positions[idx]]
                positions[idx] += 1
                key = _host_key(host)
                if not key or key in seen:
                    continue
                out.append(host)
                seen.add(key)
                progressed = True
                break
            if len(out) >= safe_cap:
                break
        if not progressed:
            break
    return tuple(out)


def _build_runtime_targets() -> None:
    global _RUNTIME_TARGETS, _LEARNED_TARGETS
    verified = _verified_file_targets()
    adaptive = _adaptive_targets()
    runtime: dict[tuple[str, str], tuple[str, ...]] = {}
    learned: dict[tuple[str, str], set[str]] = {}
    for game in GAME_LABEL_TO_SHORT:
        for region in ("KR", "JP", "US"):
            key = (game, region)
            existing = tuple(multi_route_event_discovery.PARTNER_DOMAINS.get(key) or ())
            verified_hosts = sorted(verified.get(key, set()))
            adaptive_hosts = sorted(adaptive.get(key, set()))
            learned[key] = {_host_key(x) for x in verified_hosts + adaptive_hosts if _host_key(x)}
            runtime[key] = _balanced_runtime_hosts(
                existing,
                verified_hosts,
                adaptive_hosts,
                STATIC_DISCOVERY_TARGETS.get(key, ()),
                cap=MAX_TARGETS_PER_CELL,
            )
            multi_route_event_discovery.PARTNER_DOMAINS[key] = runtime[key]
    _RUNTIME_TARGETS = runtime
    _LEARNED_TARGETS = learned
    multi_route_event_discovery.PARTNER_HOSTS = {
        host for hosts in multi_route_event_discovery.PARTNER_DOMAINS.values() for host in hosts
    }

    for region in ("KR", "JP", "US"):
        current = tuple(multi_route_event_discovery.PRESS_DOMAINS.get(region) or ())
        merged = _merge_hosts(current, PRESS_ADDITIONS.get(region, ()), cap=24)
        multi_route_event_discovery.PRESS_DOMAINS[region] = merged
    multi_route_event_discovery.PRESS_HOSTS = {
        host for hosts in multi_route_event_discovery.PRESS_DOMAINS.values() for host in hosts
    }


def _rotation_slot(now: dt.datetime | None = None) -> int:
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    else:
        now = now.astimezone(dt.timezone.utc)
    return int(now.timestamp() // (ROTATION_HOURS * 3600))


def _target_window(hosts, key: str, *, limit: int = MAX_SCOPED_HOSTS_PER_QUERY, slot: int | None = None) -> tuple[str, ...]:
    clean = list(_merge_hosts(hosts, cap=MAX_TARGETS_PER_CELL))
    cap = max(1, min(MAX_SCOPED_HOSTS_PER_QUERY, _bounded_int(limit, MAX_SCOPED_HOSTS_PER_QUERY, 1, MAX_SCOPED_HOSTS_PER_QUERY)))
    if len(clean) <= cap:
        return tuple(clean)
    pinned_count = min(PINNED_HOSTS_PER_QUERY, cap, len(clean))
    pinned = clean[:pinned_count]
    rest = clean[pinned_count:]
    need = cap - len(pinned)
    if need <= 0 or not rest:
        return tuple(pinned[:cap])
    safe_slot = _rotation_slot() if slot is None else _bounded_int(slot, _rotation_slot(), 0, 10**12)
    offset = (safe_slot + sum(ord(ch) for ch in str(key)[:200])) % len(rest)
    rotated = rest[offset:] + rest[:offset]
    return tuple(pinned + rotated[:need])


def _route_kind(game: str, region: str, scoped_hosts: tuple[str, ...]) -> str:
    values = {_host_key(x) for x in scoped_hosts if _host_key(x)}
    partner = {_host_key(x) for x in multi_route_event_discovery.PARTNER_DOMAINS.get((game, region), ()) if _host_key(x)}
    press = {_host_key(x) for x in multi_route_event_discovery.PRESS_DOMAINS.get(region, ()) if _host_key(x)}
    social = {_host_key(x) for x in multi_route_event_discovery.SOCIAL_DISCOVERY_HOSTS if _host_key(x)}
    if values and values.issubset(partner):
        return "partner"
    if values and values.issubset(press):
        return "press"
    if values and values.issubset(social):
        return "social"
    return "other"


def _v145_route_query(game: str, region: str, *, scoped_hosts: tuple[str, ...] = (), topic: str | None = None,
                      extra_terms: tuple[str, ...] = ()) -> str:
    selected = tuple(scoped_hosts)
    if selected:
        kind = _route_kind(game, region, selected)
        selected = _target_window(selected, f"{game}|{region}|{kind}")
        with _STATE_LOCK:
            _LAST_SELECTED[f"{game}|{region}|{kind}"] = selected
    return _ORIGINAL_ROUTE_QUERY(
        game, region, scoped_hosts=selected, topic=topic, extra_terms=extra_terms
    )


def _v145_bing_one(game: str, region: str, route: str, hosts: tuple[str, ...] = (), topic: str | None = None,
                   extra_terms: tuple[str, ...] = ()):
    rows, error = _ORIGINAL_BING_ONE(
        game, region, route, hosts=hosts, topic=topic, extra_terms=extra_terms
    )
    learned = {_host_key(x) for x in _LEARNED_TARGETS.get((game, region), set()) if _host_key(x)}
    partner = {_host_key(x) for x in multi_route_event_discovery.PARTNER_DOMAINS.get((game, region), ()) if _host_key(x)}
    press = {_host_key(x) for x in multi_route_event_discovery.PRESS_DOMAINS.get(region, ()) if _host_key(x)}
    for row in rows:
        if not isinstance(row, dict):
            continue
        host = _host_key(row.get("source"))
        official = row.get("official_domain_match") is True
        if not official and host in partner:
            row["partner_domain_match"] = True
            if host not in learned:
                row["source_label"] = "Bing RSS · 파트너/유통처"
                try:
                    row["confidence"] = max(0.73, min(0.90, float(row.get("confidence") or 0.0)))
                except (TypeError, ValueError, OverflowError):
                    row["confidence"] = 0.73
        if not official and host in press:
            row["press_domain_match"] = True
        if host not in learned or official:
            continue
        row["learned_source_target"] = True
        row["discovery_target_only"] = True
        row["source_label"] = "Bing RSS · 검증결과 학습 출처(발견용)"
        row["status"] = "학습 출처 발견후보 · 공식/독립출처 재확인 필요"
        row["verified"] = False
        try:
            row["confidence"] = min(0.72, float(row.get("confidence") or 0.0))
        except (TypeError, ValueError, OverflowError):
            row["confidence"] = 0.60
    return rows, error


def _coverage_status() -> dict:
    with _STATE_LOCK:
        selected_snapshot = dict(_LAST_SELECTED)
    cells = {}
    for game in GAME_LABEL_TO_SHORT:
        for region in ("KR", "JP", "US"):
            key = (game, region)
            partner = tuple(multi_route_event_discovery.PARTNER_DOMAINS.get(key, ()))
            learned = _LEARNED_TARGETS.get(key, set())
            selected = selected_snapshot.get(f"{game}|{region}|partner", ())
            cells[f"{game}/{region}"] = {
                "target_count": len(partner),
                "learned_target_count": len(learned),
                "selected_this_window": list(selected),
            }
    return {
        "patch": PATCH_ID,
        "games": list(GAME_LABEL_TO_SHORT),
        "regions": ["KR", "JP", "US"],
        "game_region_cells": len(cells),
        "cells": cells,
        "rotation_hours": ROTATION_HOURS,
        "max_hosts_per_scoped_query": MAX_SCOPED_HOSTS_PER_QUERY,
        "learned_host_scope": "exact-game+region-strong-evidence",
        "verified_or_cross_checked_learning_only": True,
        "provider_errors_do_not_demote_target_host": True,
        "trust_auto_promotion": False,
    }


def _v145_collect_all():
    # Quick-watch, priority-watch and the normal updater may wake near the same
    # boundary. Serialize this expensive route scan in-process to avoid duplicate
    # bursts and unnecessary 403/429 pressure.
    with _COLLECT_LOCK:
        with _STATE_LOCK:
            _LAST_SELECTED.clear()
        rows, errors, status = _ORIGINAL_COLLECT_ALL()
        status = dict(status) if isinstance(status, dict) else {}
        status["source_expansion_v145"] = _coverage_status()
        return rows, errors, status


def _status(*, already_applied: bool = False) -> dict:
    return {
        "ok": True,
        "patch": PATCH_ID,
        "already_applied": bool(already_applied),
        "games": tuple(GAME_LABEL_TO_SHORT),
        "regions": ("KR", "JP", "US"),
        "static_target_cells": len(STATIC_DISCOVERY_TARGETS),
        "static_target_count": sum(len(values) for values in STATIC_DISCOVERY_TARGETS.values()),
        "press_target_count": sum(len(values) for values in PRESS_ADDITIONS.values()),
        "runtime_target_count": sum(len(values) for values in _RUNTIME_TARGETS.values()),
        "learned_target_count": sum(len(values) for values in _LEARNED_TARGETS.values()),
        "scoped_learned_host_queries": True,
        "scope_evidence_isolation": True,
        "verified_evidence_source_learning": True,
        "source_health_feedback": True,
        "provider_errors_do_not_demote_target_host": True,
        "rotating_target_windows": True,
        "balanced_source_pool": True,
        "www_alias_dedup": True,
        "apply_thread_safe": True,
        "collection_call_serialized": True,
        "rotation_hours": ROTATION_HOURS,
        "max_hosts_per_scoped_query": MAX_SCOPED_HOSTS_PER_QUERY,
        "unverified_source_learning_weight": 0.0,
        "unverified_direct_learn_blocked": True,
        "trust_auto_promotion": False,
    }


def apply() -> dict:
    global _APPLIED, _ORIGINAL_ROUTE_QUERY, _ORIGINAL_BING_ONE, _ORIGINAL_COLLECT_ALL
    global _ORIGINAL_ADAPTIVE_INIT, _ORIGINAL_ADAPTIVE_LEARN_ROW, _ORIGINAL_ADAPTIVE_PLAN, _ORIGINAL_ADAPTIVE_OBSERVE
    with _APPLY_LOCK:
        if _APPLIED:
            return _status(already_applied=True)

        # Install v142 first so v145 wraps the hardened, not permissive, learner.
        learning_guard.apply()

        _ORIGINAL_ADAPTIVE_INIT = adaptive_collection_learner.AdaptiveCollectionLearner.__init__
        _ORIGINAL_ADAPTIVE_LEARN_ROW = adaptive_collection_learner.AdaptiveCollectionLearner._learn_row
        _ORIGINAL_ADAPTIVE_PLAN = adaptive_collection_learner.AdaptiveCollectionLearner.plan_queries
        _ORIGINAL_ADAPTIVE_OBSERVE = adaptive_collection_learner.AdaptiveCollectionLearner.observe_search
        adaptive_collection_learner.AdaptiveCollectionLearner.__init__ = _v145_adaptive_init
        adaptive_collection_learner.AdaptiveCollectionLearner._learn_row = _v145_learn_row
        adaptive_collection_learner.AdaptiveCollectionLearner.plan_queries = _v145_plan_queries
        adaptive_collection_learner.AdaptiveCollectionLearner.observe_search = _v145_observe_search

        _build_runtime_targets()

        _ORIGINAL_ROUTE_QUERY = multi_route_event_discovery._query
        _ORIGINAL_BING_ONE = multi_route_event_discovery._bing_one
        _ORIGINAL_COLLECT_ALL = multi_route_event_discovery.collect_all
        multi_route_event_discovery._query = _v145_route_query
        multi_route_event_discovery._bing_one = _v145_bing_one
        multi_route_event_discovery.collect_all = _v145_collect_all

        _APPLIED = True
        return _status(already_applied=False)


if __name__ == "__main__":
    print(json.dumps(apply(), ensure_ascii=False, indent=2))
