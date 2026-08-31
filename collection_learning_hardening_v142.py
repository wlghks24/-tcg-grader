#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v142 collection/self-learning hardening.

This layer keeps v141 event/reward discovery while closing collection-learning gaps:
- repeated routes from the same publisher cannot inflate independent-source count;
- unverified social/supplementary/search rows cannot poison persistent host/term memory;
- query yield may still be measured without teaching unverified vocabulary;
- fan accounts are re-used automatically only after corroboration or explicit watch;
- adaptive official-social detection requires a real social profile/account URL,
  never a mere username mention in an arbitrary page title.

Trust is never auto-promoted. Verified/cross-checked signals only influence future
search priority and vocabulary.
"""
from __future__ import annotations

import hashlib
import json
import urllib.parse
from pathlib import Path

import adaptive_collection_learner
import event_collection_hardening_v141 as base
import event_gap_learning
import fan_social_learning
import multi_route_event_discovery
import social_event_discovery
from safe_runtime import safe_read_text

ROOT = Path(__file__).resolve().parent
SOCIAL_CANDIDATES = ROOT / "social_event_candidates.json"
PATCH_ID = 142
FOCUS_TOPICS = base.FOCUS_TOPICS
_trusted_accounts = base._trusted_accounts
focused_official_social_search = base.focused_official_social_search
reward_signal = base.reward_signal
reward_kind = base.reward_kind
_annotate_reward_row = base._annotate_reward_row

_APPLIED = False
_ORIGINAL_MERGE_CANDIDATES = None
_ORIGINAL_ADAPTIVE_INIT = None
_ORIGINAL_ADAPTIVE_IS_OFFICIAL = None
_ORIGINAL_OBSERVE_SEARCH = None
_ORIGINAL_LEARN_FROM_PAYLOAD = None
_ORIGINAL_PREFERRED_AUTHORS = None


def _status(*, already_applied: bool = False) -> dict:
    return {
        "ok": True,
        "patch": PATCH_ID,
        "already_applied": bool(already_applied),
        "reward_scope_override": True,
        "verified_reward_term_learning": True,
        "official_reward_learning_weight": 1.35,
        "cross_checked_reward_learning_weight": 0.90,
        "unverified_reward_learning_weight": 0.0,
        "unverified_payload_learning_weight": 0.0,
        "unverified_search_host_term_learning_weight": 0.0,
        "unique_evidence_host_counting": True,
        "fan_reuse_requires_corroboration_or_watch": True,
        "strict_official_social_url_match": True,
        "max_learned_terms": event_gap_learning.MAX_TERMS,
        "max_seen_verified": event_gap_learning.MAX_SEEN,
        "trust_auto_promotion": False,
    }


def _host(url: object) -> str:
    try:
        return (urllib.parse.urlsplit(str(url or "")).hostname or "").lower()
    except ValueError:
        return ""


def _social_account_from_url(url: object) -> str | None:
    try:
        parsed = urllib.parse.urlsplit(str(url or ""))
    except ValueError:
        return None
    host = (parsed.hostname or "").lower().removeprefix("www.")
    parts = [urllib.parse.unquote(x).strip() for x in parsed.path.split("/") if x.strip()]
    if not parts:
        return None
    if host in {"x.com", "twitter.com"}:
        candidate = parts[0].lstrip("@").lower()
        if candidate not in {"home", "search", "share", "intent", "i"}:
            return candidate
    if host == "instagram.com":
        candidate = parts[0].lstrip("@").lower()
        if candidate not in {"p", "reel", "explore", "stories"}:
            return candidate
    if host == "youtube.com" and parts[0].startswith("@"):
        return parts[0].lstrip("@").lower()
    return None


def _hardened_is_official(self, game: str, url: str, title: str = "") -> bool:
    """Official domains are exact-host; social authority requires the URL account."""
    cfg = adaptive_collection_learner.GAME_CONFIG.get(game, {})
    host = _host(url)
    if host in set(cfg.get("official_hosts") or ()):
        return True
    account = _social_account_from_url(url)
    if not account:
        return False
    trusted = {str(x).lower().lstrip("@") for x in (cfg.get("official_social") or ()) if str(x).strip()}
    return account in trusted


def _evidence_hosts(row: dict) -> set[str]:
    hosts = {
        str(x).strip().lower()
        for x in (row.get("evidence_hosts") or [])
        if isinstance(x, str) and str(x).strip()
    }
    host = _host(row.get("publisher_url") or row.get("source"))
    if host:
        hosts.add(host)
    return hosts


def _hardened_merge_candidates(rows: list[dict]) -> list[dict]:
    """Use unique publisher hosts for corroboration instead of route count.

    The older merge could count A→B→B as three independent sources because it only
    compared each new row with the current winner. v142 retains an explicit host set.
    """
    evidence: dict[tuple[str, str, str, str], set[str]] = {}
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        try:
            key = social_event_discovery._candidate_key(raw)
        except (AttributeError, TypeError, ValueError):
            continue
        evidence.setdefault(key, set()).update(_evidence_hosts(raw))

    merged = _ORIGINAL_MERGE_CANDIDATES(rows)
    for row in merged:
        try:
            key = social_event_discovery._candidate_key(row)
        except (AttributeError, TypeError, ValueError):
            continue
        hosts = sorted(evidence.get(key) or _evidence_hosts(row))[:9]
        if hosts:
            row["evidence_hosts"] = hosts
            row["independent_source_count"] = len(hosts)
            if len(hosts) >= 2:
                row["cross_checked"] = True
                if row.get("verified") is not True:
                    row["status"] = "복수 독립출처 교차확인 후보"
            else:
                row["cross_checked"] = False
                if row.get("verified") is not True and "복수" in str(row.get("status") or ""):
                    row["status"] = "검색 교차확인 후보"
    return merged


def _sanitize_untrusted_adaptive_memory(learner) -> tuple[int, int]:
    """Remove old host/term memory that has no official or cross-check evidence."""
    removed_hosts = 0
    removed_terms = 0
    hosts = learner.memory.get("host_stats") if isinstance(learner.memory, dict) else None
    if isinstance(hosts, dict):
        for key in list(hosts):
            row = hosts.get(key) if isinstance(hosts.get(key), dict) else {}
            if adaptive_collection_learner._bounded_int(row.get("official")) <= 0 and adaptive_collection_learner._bounded_int(row.get("cross_checked")) <= 0:
                hosts.pop(key, None)
                removed_hosts += 1
    terms = learner.memory.get("term_stats") if isinstance(learner.memory, dict) else None
    if isinstance(terms, dict):
        for key in list(terms):
            row = terms.get(key) if isinstance(terms.get(key), dict) else {}
            if adaptive_collection_learner._bounded_int(row.get("official")) <= 0 and adaptive_collection_learner._bounded_int(row.get("cross_checked")) <= 0:
                terms.pop(key, None)
                removed_terms += 1
    learner.memory.setdefault("channel_stats", {}).setdefault("v142_learning_safety", {}).update({
        "removed_unverified_hosts": removed_hosts,
        "removed_unverified_terms": removed_terms,
        "policy": "official/cross-checked evidence 없는 과거 host/term 학습값 제거",
        "last_seen": adaptive_collection_learner._now(),
    })
    return removed_hosts, removed_terms


def _hardened_adaptive_init(self, *args, **kwargs):
    _ORIGINAL_ADAPTIVE_INIT(self, *args, **kwargs)
    _sanitize_untrusted_adaptive_memory(self)


def _hardened_observe_search(self, keyword: str, query: str, rows, *, error: str = "", family: str = "web", region: str = "KR") -> dict:
    """Keep query-yield learning, but persist host/term vocabulary from official hits only."""
    game = adaptive_collection_learner.canonical_game(keyword)
    rows = list(rows)
    relevant_rows = []
    official_rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        score, official = self._result_features(game, str(row.get("title", "")), str(row.get("url", "")))
        if score < 2.6:
            continue
        relevant_rows.append(row)
        if official:
            official_rows.append(row)

    qkey = adaptive_collection_learner._signature(query)
    qrow = self.memory["query_stats"].setdefault(qkey, {"query": query[:280], "family": family, "region": region, "game": game})
    qrow["runs"] = adaptive_collection_learner._bounded_int(qrow.get("runs")) + 1
    qrow["hits"] = adaptive_collection_learner._bounded_int(qrow.get("hits")) + len(rows)
    qrow["relevant"] = adaptive_collection_learner._bounded_int(qrow.get("relevant")) + len(relevant_rows)
    qrow["official"] = adaptive_collection_learner._bounded_int(qrow.get("official")) + len(official_rows)
    qrow["errors"] = adaptive_collection_learner._bounded_int(qrow.get("errors")) + (1 if error else 0)
    qrow["empty"] = adaptive_collection_learner._bounded_int(qrow.get("empty")) + (1 if not rows and not error else 0)
    sample_quality = len(relevant_rows) * 0.7 + len(official_rows) * 1.4 - (1.5 if error else 0.0) - (0.25 if not rows else 0.0)
    old_quality = adaptive_collection_learner._bounded_float(qrow.get("quality"), sample_quality)
    qrow["quality"] = round(old_quality * 0.72 + sample_quality * 0.28, 4)
    qrow["score"] = round(qrow["quality"] + min(2.0, adaptive_collection_learner._bounded_int(qrow.get("official")) * 0.1), 4)
    qrow["last_seen"] = adaptive_collection_learner._now()

    channel = self.memory["channel_stats"].setdefault(family, {})
    channel["runs"] = adaptive_collection_learner._bounded_int(channel.get("runs")) + 1
    channel["hits"] = adaptive_collection_learner._bounded_int(channel.get("hits")) + len(rows)
    channel["relevant"] = adaptive_collection_learner._bounded_int(channel.get("relevant")) + len(relevant_rows)
    channel["official"] = adaptive_collection_learner._bounded_int(channel.get("official")) + len(official_rows)
    channel["errors"] = adaptive_collection_learner._bounded_int(channel.get("errors")) + (1 if error else 0)
    channel["score"] = round(
        (adaptive_collection_learner._bounded_int(channel.get("relevant")) + 2 * adaptive_collection_learner._bounded_int(channel.get("official")))
        / max(1, adaptive_collection_learner._bounded_int(channel.get("runs")))
        - adaptive_collection_learner._bounded_int(channel.get("errors")) * 0.15,
        4,
    )
    channel["last_seen"] = adaptive_collection_learner._now()

    totals = self.memory["totals"]
    totals["searches"] = adaptive_collection_learner._bounded_int(totals.get("searches")) + 1
    totals["results"] = adaptive_collection_learner._bounded_int(totals.get("results")) + len(rows)
    totals["relevant"] = adaptive_collection_learner._bounded_int(totals.get("relevant")) + len(relevant_rows)
    totals["official"] = adaptive_collection_learner._bounded_int(totals.get("official")) + len(official_rows)
    totals["errors"] = adaptive_collection_learner._bounded_int(totals.get("errors")) + (1 if error else 0)

    # Persistent host/term vocabulary changes only after official proof.
    for row in official_rows:
        self._learn_row(game, region, row, weight=1.0, verified=True)
    if official_rows:
        for term in adaptive_collection_learner.REGION_SEEDS.get(region, adaptive_collection_learner.REGION_SEEDS["KR"])["event"]:
            if term.lower() in query.lower():
                self._bump_term(game, region, term, relevant=len(official_rows), official=len(official_rows), weight=0.05, run=True)
    safety = self.memory["channel_stats"].setdefault("v142_learning_safety", {})
    safety["ignored_unverified_search_rows"] = adaptive_collection_learner._bounded_int(safety.get("ignored_unverified_search_rows")) + max(0, len(relevant_rows) - len(official_rows))
    safety["last_seen"] = adaptive_collection_learner._now()
    return {"results": len(rows), "relevant": len(relevant_rows), "official": len(official_rows), "error": bool(error)}


def _safe_payload_row(raw: dict) -> bool:
    verified = bool(
        raw.get("verified") is True
        or raw.get("source_grade") == "official"
        or raw.get("official_domain_match") is True
        or raw.get("official_account_verified") is True
    )
    independent = adaptive_collection_learner._bounded_int(raw.get("independent_source_count"))
    cross_checked = bool(raw.get("cross_checked") is True and independent >= 2)
    if verified:
        return True
    if not cross_checked:
        return False
    if raw.get("fan_candidate") is True or str(raw.get("source_tier") or "").lower().startswith("c-community"):
        return False
    try:
        confidence = float(raw.get("confidence") or 0.0)
    except (TypeError, ValueError, OverflowError):
        confidence = 0.0
    return confidence >= 0.72


def _hardened_learn_from_payload(self, payload: object, *, origin: str = "candidate") -> int:
    if str(origin).lower() not in {"social", "supplementary"} or not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        return _ORIGINAL_LEARN_FROM_PAYLOAD(self, payload, origin=origin)
    rows = [row for row in payload.get("items", []) if isinstance(row, dict)]
    safe_rows = [row for row in rows if _safe_payload_row(row)]
    learned = _ORIGINAL_LEARN_FROM_PAYLOAD(self, {**payload, "items": safe_rows}, origin=origin)
    safety = self.memory["channel_stats"].setdefault("v142_learning_safety", {})
    safety["ignored_unverified_payload_rows"] = adaptive_collection_learner._bounded_int(safety.get("ignored_unverified_payload_rows")) + max(0, len(rows) - len(safe_rows))
    safety["last_seen"] = adaptive_collection_learner._now()
    return learned


def _hardened_preferred_authors(self, game: str, region: str, limit: int = 6) -> list[str]:
    rows = []
    for stat in (self.data.get("sources") or {}).values():
        if not isinstance(stat, dict):
            continue
        author = str(stat.get("author") or "").strip().lstrip("@")
        if not author or stat.get("game") != game or stat.get("region") != region:
            continue
        corroborated = fan_social_learning._int(stat.get("corroborated"))
        selected = fan_social_learning._int(stat.get("selected"))
        known = bool(stat.get("known_watch_account"))
        if not ((corroborated >= 1 and selected >= 1) or (known and selected >= 1)):
            continue
        rows.append((fan_social_learning._score(stat), corroborated, selected, author))
    rows.sort(reverse=True)
    return [author for _, _, _, author in rows[: max(1, min(12, int(limit)))]]


def _reward_grade(row: dict) -> str | None:
    official = bool(row.get("verified") is True and (row.get("official_account_verified") is True or row.get("official_domain_match") is True))
    if official:
        return "official_reward_social"
    independent = adaptive_collection_learner._bounded_int(row.get("independent_source_count"))
    cross = bool(row.get("cross_checked") is True and independent >= 2)
    if not cross or row.get("fan_candidate") is True or str(row.get("source_tier") or "").lower().startswith("c-community"):
        return None
    try:
        confidence = float(row.get("confidence") or 0.0)
    except (TypeError, ValueError, OverflowError):
        confidence = 0.0
    return "cross_checked_reward_social" if confidence >= 0.78 else None


def learn_verified_reward_candidates(learner: event_gap_learning.EventGapLearner, path=SOCIAL_CANDIDATES) -> int:
    """Learn reward anchors from official or strong independent corroboration only."""
    try:
        payload = json.loads(safe_read_text(Path(path), max_bytes=3_000_000))
    except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        return 0
    rows = payload.get("items", []) if isinstance(payload, dict) else []
    seen = set(learner.data.get("seen_verified") or [])
    learned = 0
    for row in rows[:600]:
        if not isinstance(row, dict):
            continue
        text = " ".join(str(row.get(k) or "") for k in ("title", "excerpt", "status", "source_label"))
        if row.get("reward_watch") is not True and not reward_signal(text):
            continue
        grade = _reward_grade(row)
        if grade is None:
            continue
        game = str(row.get("game") or "")
        region = str(row.get("region") or "")
        source = str(row.get("source") or "")
        if game not in social_event_discovery.GAMES or region not in social_event_discovery.REGION_LANG or not source.startswith("https://"):
            continue
        marker = hashlib.sha256(f"reward|{game}|{region}|{source}|{row.get('title')}".encode("utf-8", "ignore")).hexdigest()[:24]
        if marker in seen:
            continue
        try:
            topic = social_event_discovery._coverage_topic(row)
        except (AttributeError, TypeError, ValueError):
            topic = "promo"
        if topic not in multi_route_event_discovery.COVERAGE_TOPICS:
            topic = "promo"
        terms = base._reward_learning_terms(row)
        if not terms:
            seen.add(marker)
            continue
        weight = 1.35 if grade == "official_reward_social" else 0.90
        for term in terms:
            key = f"{game}|{region}|{topic}|{term}"
            stat = learner.data["terms"].setdefault(key, {})
            score = max(0.0, event_gap_learning._float(stat.get("score")))
            stat["score"] = round(min(20.0, score * 0.985 + weight), 4)
            stat["reward_verified_events"] = event_gap_learning._int(stat.get("reward_verified_events")) + 1
            if grade == "official_reward_social":
                stat["verified_events"] = event_gap_learning._int(stat.get("verified_events")) + 1
            else:
                stat["cross_checked_events"] = event_gap_learning._int(stat.get("cross_checked_events")) + 1
            stat["last_seen"] = event_gap_learning._now()
            stat["learned_from"] = grade
            stat["last_learning_weight"] = weight
        seen.add(marker)
        learned += 1
    learner.data["seen_verified"] = list(seen)[-event_gap_learning.MAX_SEEN:]
    return learned


def apply() -> dict:
    global _APPLIED, _ORIGINAL_MERGE_CANDIDATES, _ORIGINAL_ADAPTIVE_INIT, _ORIGINAL_ADAPTIVE_IS_OFFICIAL
    global _ORIGINAL_OBSERVE_SEARCH, _ORIGINAL_LEARN_FROM_PAYLOAD, _ORIGINAL_PREFERRED_AUTHORS
    if _APPLIED:
        return _status(already_applied=True)

    base.apply()
    event_gap_learning.MAX_TERMS = max(int(event_gap_learning.MAX_TERMS), 900)
    event_gap_learning.MAX_SEEN = max(int(event_gap_learning.MAX_SEEN), 800)

    # Keep the adaptive official detector aligned with the trusted registry entry
    # that caught the missed Pokémon Wild Card announcement.
    pokemon_social = tuple(adaptive_collection_learner.GAME_CONFIG["포켓몬"].get("official_social") or ())
    if "pokemon_korea_official" not in pokemon_social:
        adaptive_collection_learner.GAME_CONFIG["포켓몬"]["official_social"] = pokemon_social + ("pokemon_korea_official",)

    _ORIGINAL_MERGE_CANDIDATES = social_event_discovery.merge_candidates
    social_event_discovery.merge_candidates = _hardened_merge_candidates

    _ORIGINAL_ADAPTIVE_INIT = adaptive_collection_learner.AdaptiveCollectionLearner.__init__
    _ORIGINAL_ADAPTIVE_IS_OFFICIAL = adaptive_collection_learner.AdaptiveCollectionLearner._is_official
    _ORIGINAL_OBSERVE_SEARCH = adaptive_collection_learner.AdaptiveCollectionLearner.observe_search
    _ORIGINAL_LEARN_FROM_PAYLOAD = adaptive_collection_learner.AdaptiveCollectionLearner.learn_from_payload
    adaptive_collection_learner.AdaptiveCollectionLearner.__init__ = _hardened_adaptive_init
    adaptive_collection_learner.AdaptiveCollectionLearner._is_official = _hardened_is_official
    adaptive_collection_learner.AdaptiveCollectionLearner.observe_search = _hardened_observe_search
    adaptive_collection_learner.AdaptiveCollectionLearner.learn_from_payload = _hardened_learn_from_payload

    _ORIGINAL_PREFERRED_AUTHORS = fan_social_learning.FanSocialLearner.preferred_authors
    fan_social_learning.FanSocialLearner.preferred_authors = _hardened_preferred_authors

    # v141's patched EventGapLearner resolves this module-global function at call
    # time, so replacing it here upgrades both hourly and full route learning.
    base.learn_verified_reward_candidates = learn_verified_reward_candidates
    multi_route_event_discovery.EventGapLearner = event_gap_learning.EventGapLearner

    _APPLIED = True
    return _status(already_applied=False)


if __name__ == "__main__":
    print(json.dumps(apply(), ensure_ascii=False))
