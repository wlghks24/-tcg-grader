#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v141 verified reward-learning overlay.

Adds one more safety-preserving learning layer on top of v140:
- verified official/cross-checked reward candidates can teach future search anchors;
- unverified community candidates never change learned search vocabulary;
- reward learning gets a bounded weight boost without changing trust/verification;
- the 30-minute priority watcher can reuse the v140 reward-aware official search.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import event_collection_hardening_v140 as base
import event_gap_learning
import multi_route_event_discovery
import social_event_discovery
from safe_runtime import safe_read_text

ROOT = Path(__file__).resolve().parent
SOCIAL_CANDIDATES = ROOT / "social_event_candidates.json"
PATCH_ID = 141
FOCUS_TOPICS = base.FOCUS_TOPICS
_trusted_accounts = base._trusted_accounts
focused_official_social_search = base.focused_official_social_search
reward_signal = base.reward_signal
reward_kind = base.reward_kind
_annotate_reward_row = base._annotate_reward_row
_APPLIED = False
_PREVIOUS_LEARN_VERIFIED_FILE = None

# Generic giveaway vocabulary is already hard-coded in v140. Learning should
# mainly retain campaign/place/partner anchors that help find the next missed post.
REWARD_LEARN_STOP = {
    "카드", "카드게임", "포켓몬", "원피스", "나루토", "프로모", "프로모션", "증정", "배포", "지급",
    "수령", "제공", "무료", "한정", "한정판", "굿즈", "팩", "특전", "이벤트", "행사", "선착순", "추첨",
    "경품", "사은품", "콜라보", "포토카드", "CARD", "CARDS", "POKEMON", "POKÉMON", "NARUTO",
    "PROMO", "PROMOTIONAL", "GIVEAWAY", "FREE", "LIMITED", "EXCLUSIVE", "BONUS", "REWARD", "PRIZE",
    "PACK", "COLLAB", "COLLABORATION", "プロモ", "カード", "配布", "特典", "限定", "景品", "無料",
    "プレゼント", "コラボ", "パック", "グッズ",
}


def _candidate_grade(row: dict) -> str | None:
    if row.get("verified") is not True:
        return None
    official = row.get("official_account_verified") is True or row.get("official_domain_match") is True
    try:
        independent = int(row.get("independent_source_count") or 0)
    except (TypeError, ValueError, OverflowError):
        independent = 0
    cross = row.get("cross_checked") is True and independent >= 2
    if official:
        return "official_reward_social"
    if cross:
        return "cross_checked_reward_social"
    return None


def _reward_learning_terms(row: dict) -> tuple[str, ...]:
    pseudo = {
        "name_ko": row.get("title"),
        "name_native": row.get("author"),
        "reward": row.get("excerpt"),
        "condition": f"{row.get('source_label') or ''} {row.get('status') or ''}",
        "location": row.get("location"),
    }
    out: list[str] = []
    for term in event_gap_learning._terms(pseudo):
        clean = re.sub(r"\s+", " ", str(term)).strip()[:50]
        if not clean or clean.upper() in REWARD_LEARN_STOP or clean in REWARD_LEARN_STOP:
            continue
        if clean not in out:
            out.append(clean)

    # Preserve short two-token campaign anchors such as "KANTO FESTA" or
    # "피카피카 페스타" even when the generic reward words around them are removed.
    raw_tokens = [re.sub(r"\s+", " ", x).strip()[:24] for x in event_gap_learning.TOKEN_RE.findall(str(row.get("title") or ""))]
    for left, right in zip(raw_tokens, raw_tokens[1:]):
        if left.upper() in REWARD_LEARN_STOP or left in REWARD_LEARN_STOP:
            continue
        if right.upper() in REWARD_LEARN_STOP or right in REWARD_LEARN_STOP:
            continue
        phrase = f"{left} {right}"[:50]
        if phrase not in out:
            out.append(phrase)
        if len(out) >= 20:
            break
    return tuple(out[:20])


def learn_verified_reward_candidates(learner: event_gap_learning.EventGapLearner, path=SOCIAL_CANDIDATES) -> int:
    """Learn search anchors from verified reward candidates only.

    Weight policy:
      official account/domain + verified: +1.35
      independently cross-checked (2+) + verified: +0.90
      unverified/community: +0.00
    These values affect search-term priority only, never source trust.
    """
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
        grade = _candidate_grade(row)
        if grade is None:
            continue
        game = str(row.get("game") or "")
        region = str(row.get("region") or "")
        source = str(row.get("source") or "")
        if game not in social_event_discovery.GAMES or region not in social_event_discovery.REGION_LANG or not source.startswith("https://"):
            continue
        marker_raw = f"reward|{game}|{region}|{source}|{row.get('title')}"
        marker = hashlib.sha256(marker_raw.encode("utf-8", "ignore")).hexdigest()[:24]
        if marker in seen:
            continue
        try:
            topic = social_event_discovery._coverage_topic(row)
        except (AttributeError, TypeError, ValueError):
            topic = "promo"
        if topic not in multi_route_event_discovery.COVERAGE_TOPICS:
            topic = "promo"
        terms = _reward_learning_terms(row)
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


def _hardened_learn_verified_file(self, path=event_gap_learning.PROMO):
    learned = _PREVIOUS_LEARN_VERIFIED_FILE(self, path)
    try:
        is_default = Path(path).resolve() == Path(event_gap_learning.PROMO).resolve()
    except (OSError, ValueError):
        is_default = False
    if is_default:
        learned += learn_verified_reward_candidates(self, SOCIAL_CANDIDATES)
    return learned


def apply() -> dict:
    global _APPLIED, _PREVIOUS_LEARN_VERIFIED_FILE
    if _APPLIED:
        return {"ok": True, "patch": PATCH_ID, "already_applied": True}
    base.apply()
    # More room for verified campaign anchors while retaining bounded memory.
    event_gap_learning.MAX_TERMS = max(int(event_gap_learning.MAX_TERMS), 900)
    event_gap_learning.MAX_SEEN = max(int(event_gap_learning.MAX_SEEN), 800)
    _PREVIOUS_LEARN_VERIFIED_FILE = event_gap_learning.EventGapLearner.learn_verified_file
    event_gap_learning.EventGapLearner.learn_verified_file = _hardened_learn_verified_file
    multi_route_event_discovery.EventGapLearner = event_gap_learning.EventGapLearner
    _APPLIED = True
    return {
        "ok": True,
        "patch": PATCH_ID,
        "reward_scope_override": True,
        "verified_reward_term_learning": True,
        "official_reward_learning_weight": 1.35,
        "cross_checked_reward_learning_weight": 0.90,
        "unverified_reward_learning_weight": 0.0,
        "max_learned_terms": event_gap_learning.MAX_TERMS,
        "max_seen_verified": event_gap_learning.MAX_SEEN,
        "trust_auto_promotion": False,
    }


if __name__ == "__main__":
    print(json.dumps(apply(), ensure_ascii=False))
