#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v140 reward/giveaway discovery overlay.

Goal: if a public post/page says a Pokemon / ONE PIECE / NARUTO card-related
promo, limited item, collaboration item, pack, photocard or goods is being
given/distributed/awarded, keep it as a visible candidate even when the post
would not otherwise match the normal event/movie/collab collection scope.

Trust is deliberately unchanged: broad discovery may create a candidate, but
only existing official-account/domain/cross-check rules may mark it verified.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

import event_collection_hardening_v139 as base
import multi_route_event_discovery
import social_event_discovery
from safe_runtime import atomic_write_json, safe_urlopen, validate_public_https_url

PATCH_ID = 140
FOCUS_TOPICS = base.FOCUS_TOPICS
_trusted_accounts = base._trusted_accounts
_APPLIED = False
_PREVIOUS_DDG_SOCIAL_ONE = None
_ORIGINAL_MERGE = social_event_discovery.merge_candidates
_ORIGINAL_MAIN = social_event_discovery.main

REWARD_TERMS = {
    "ko": (
        "카드 증정", "프로모 카드", "프로모션 카드", "프로모션 팩", "한정 카드", "한정판 카드",
        "한정판", "한정 굿즈", "콜라보 카드", "콜라보 한정", "포토카드", "기념 카드", "스페셜 카드",
        "사은품", "특전", "구매특전", "예약특전", "방문특전", "참가특전", "관람특전", "입장특전",
        "응모특전", "선착순", "추첨", "경품", "무료 배포", "무료 증정", "재배포", "지급", "수령",
        "제공", "증정", "배포", "받을 수", "받을수", "준다", "드립니다", "이벤트 경품",
    ),
    "ja": (
        "カード配布", "プロモカード", "プロモーションカード", "プロモパック", "限定カード", "限定版",
        "コラボカード", "記念カード", "フォトカード", "特典", "購入特典", "予約特典", "来場者特典",
        "参加特典", "入場者特典", "先着", "抽選", "景品", "無料配布", "プレゼント", "配布", "贈呈",
        "もらえる", "ノベルティ",
    ),
    "en": (
        "card giveaway", "free card", "promo card", "promotional card", "promo pack", "exclusive card",
        "limited edition card", "limited-edition card", "limited edition", "collaboration card", "collab card",
        "commemorative card", "photocard", "bonus card", "attendee bonus", "admission bonus", "purchase bonus",
        "preorder bonus", "participation prize", "giveaway", "free distribution", "free gift", "reward", "prize",
        "while supplies last", "first come", "lottery", "receive", "distributed", "gift with purchase",
    ),
}

REWARD_ACTION_RE = re.compile(
    r"증정|배포|재배포|지급|수령|제공|선착순|추첨|응모|경품|사은품|특전|받을\s*수|준다|드립니|무료|"
    r"配布|再配布|贈呈|先着|抽選|景品|特典|プレゼント|もらえる|無料|"
    r"giveaway|give\s*away|free\s+(?:gift|card|pack|item|distribution)|bonus|reward|prize|"
    r"receive|distributed|distribution|while\s+supplies\s+last|first\s+come|lottery|gift\s+with\s+purchase",
    re.I,
)
REWARD_ITEM_RE = re.compile(
    r"카드|프로모|프로모션\s*팩|한정(?:판)?|콜라보|포토카드|기념|스페셜|팩|굿즈|"
    r"カード|プロモ|パック|限定|コラボ|フォトカード|記念|ノベルティ|グッズ|"
    r"card|promo|pack|exclusive|limited(?:[- ]edition)?|collab|collaboration|photocard|commemorative|special\s+item|merch",
    re.I,
)
# One regex for collectors that accept only a Pattern object. Both semantics must
# occur somewhere in the same title/caption; a bare "card" or "limited" is not enough.
REWARD_BOTH_PATTERN = (
    r"(?=.*(?:" + REWARD_ACTION_RE.pattern + r"))(?=.*(?:" + REWARD_ITEM_RE.pattern + r"))"
)


def _append_terms(existing: str, additions) -> str:
    return base._append_terms(existing, tuple(additions))


def reward_signal(text: object) -> bool:
    value = str(text or "")
    return bool(REWARD_ACTION_RE.search(value) and REWARD_ITEM_RE.search(value))


def reward_kind(text: object) -> str:
    value = str(text or "")
    if re.search(r"프로모|プロモ|promo", value, re.I):
        return "promo_card_or_pack"
    if re.search(r"콜라보|コラボ|collab|collaboration", value, re.I):
        return "collaboration_reward"
    if re.search(r"한정|限定|exclusive|limited", value, re.I):
        return "limited_reward"
    if re.search(r"포토카드|フォトカード|photocard", value, re.I):
        return "photocard_reward"
    if re.search(r"팩|パック|pack", value, re.I):
        return "pack_reward"
    return "card_or_goods_reward"


def _annotate_reward_row(raw: dict) -> dict:
    row = dict(raw)
    text = " ".join(str(row.get(key) or "") for key in ("title", "excerpt", "status", "source_label"))
    if not reward_signal(text):
        return row
    row["reward_watch"] = True
    row["reward_kind"] = reward_kind(text)
    row["collection_scope_override"] = "tcg_reward_or_giveaway"
    row["must_show_candidate"] = True
    if row.get("category") not in {"movie", "collaboration"}:
        row["category"] = "promo"
    try:
        confidence = float(row.get("confidence") or 0.0)
    except (TypeError, ValueError, OverflowError):
        confidence = 0.0
    # Discovery priority only. This DOES NOT set verified/trusted.
    row["confidence"] = max(confidence, 0.64)
    current_status = str(row.get("status") or "후보")
    if "증정" not in current_status and "reward" not in current_status.lower():
        row["status"] = f"{current_status} · 카드/한정품 증정 감지"
    return row


def _harden_vocab() -> None:
    for lang, terms in REWARD_TERMS.items():
        social_event_discovery.EVENT_TERMS[lang] = _append_terms(
            social_event_discovery.EVENT_TERMS.get(lang, ""), terms
        )
        social_event_discovery.FAN_TERMS[lang] = _append_terms(
            social_event_discovery.FAN_TERMS.get(lang, ""), terms
        )
        families = multi_route_event_discovery.QUERY_FAMILIES.get(lang, {})
        compact = " ".join(terms)
        families["promo"] = _append_terms(families.get("promo", ""), compact.split())
        families["event"] = _append_terms(families.get("event", ""), compact.split())
        families["collab"] = _append_terms(families.get("collab", ""), compact.split())

    rebuilt = []
    for category, pattern in social_event_discovery.CATEGORY_PATTERNS:
        if category == "promo":
            pattern = re.compile(pattern.pattern + "|" + REWARD_BOTH_PATTERN, re.I)
        rebuilt.append((category, pattern))
    social_event_discovery.CATEGORY_PATTERNS = tuple(rebuilt)
    multi_route_event_discovery.KEYWORD_RE = re.compile(
        multi_route_event_discovery.KEYWORD_RE.pattern + "|" + REWARD_BOTH_PATTERN,
        re.I,
    )


def _reward_query_terms(lang: str) -> str:
    # Keep the public query bounded; the local post/title filter enforces both
    # reward-action and relevant-item semantics before a candidate is accepted.
    tokens = []
    for phrase in REWARD_TERMS[lang]:
        phrase = str(phrase).strip()
        if phrase and phrase not in tokens:
            tokens.append(phrase)
        if len(tokens) >= 24:
            break
    return " OR ".join(f'"{x}"' if " " in x else x for x in tokens)


def reward_social_search(game: str, region: str, registry: dict, *, official_only: bool = False):
    """Independent reward/giveaway search, not dependent on normal event scope."""
    lang = social_event_discovery.REGION_LANG[region]["lang"]
    names = social_event_discovery.GAMES[game][lang][:3]
    name_expr = " OR ".join(f'"{name}"' for name in names)
    reward_expr = _reward_query_terms(lang)
    accounts = _trusted_accounts(registry, game, region) if official_only else []
    account_expr = " OR ".join(f'"{row["username"]}"' for row in accounts)
    if official_only and not account_expr:
        return [], None
    if official_only:
        query = f"(({name_expr}) OR ({account_expr})) ({account_expr}) ({reward_expr}) (site:x.com OR site:instagram.com OR site:youtube.com)"
    else:
        query = f"({name_expr}) ({reward_expr}) (site:x.com OR site:instagram.com OR site:youtube.com)"
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 TCG-Grader-RewardWatch/4.0"})
    try:
        with safe_urlopen(
            req,
            timeout=social_event_discovery.SOURCE_TIMEOUT,
            allowed_hosts=social_event_discovery.DDG_HOSTS,
        ) as response:
            raw = response.read(900_000).decode("utf-8", "replace")
        rows = []
        for match in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', raw, re.I | re.S):
            source = social_event_discovery._decode_ddg_href(match.group(1))
            if not source or social_event_discovery._host(source) not in social_event_discovery.SOCIAL_HOSTS:
                continue
            try:
                validate_public_https_url(source)
            except (TypeError, ValueError):
                continue
            title = social_event_discovery._short(base._strip_markup(match.group(2)), 220)
            context = base._strip_markup(raw[max(0, match.start() - 600): min(len(raw), match.end() + 1100)])
            combined = social_event_discovery._short(f"{title} {context}", 900)
            if not title or not reward_signal(combined):
                continue
            official, author = social_event_discovery._official_social_match(registry, source, combined, game, region)
            if official_only and not official:
                continue
            host = social_event_discovery._host(source)
            kind = "x" if "x.com" in host or "twitter.com" in host else ("instagram" if "instagram.com" in host else "youtube")
            row = {
                "game": game,
                "region": region,
                "category": social_event_discovery._category(combined),
                "title": title,
                "source": source,
                "source_kind": f"{kind}_reward_watch",
                "source_tier": "A-social" if official else "C-community",
                "source_label": "공식 SNS 카드/한정품 증정 탐색" if official else "카드/한정품 증정 공개검색 후보",
                "author": author,
                "official_account_verified": bool(official),
                "dates": social_event_discovery._dates(combined),
                "excerpt": social_event_discovery._short(context or title, 320),
                "status": "공식 SNS 증정정보 후보" if official else "증정정보 후보 · 공식 교차확인 필요",
                "verified": bool(official),
                "confidence": 0.96 if official else 0.68,
                "reward_watch": True,
                "reward_kind": reward_kind(combined),
                "collection_scope_override": "tcg_reward_or_giveaway",
                "must_show_candidate": True,
                "collected_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            }
            rows.append(row)
            if len(rows) >= social_event_discovery.MAX_PER_QUERY:
                break
        return rows, None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError, UnicodeDecodeError) as exc:
        return [], f"카드/한정품 증정 탐색 {game}/{region}: {type(exc).__name__}"


def focused_official_social_search(game: str, region: str, registry: dict):
    """v139 fast official search plus an independent official reward search."""
    normal, normal_error = base.focused_official_social_search(game, region, registry)
    reward, reward_error = reward_social_search(game, region, registry, official_only=True)
    rows = normal + reward
    if normal_error and reward_error:
        return rows, f"{normal_error}; {reward_error}"
    return rows, normal_error or reward_error


def _reward_ddg_social_one(game: str, region: str, registry: dict, fan_learner=None):
    rows, error = _PREVIOUS_DDG_SOCIAL_ONE(game, region, registry, fan_learner)
    reward_rows, reward_error = reward_social_search(game, region, registry, official_only=False)
    rows.extend(reward_rows)
    if error and reward_error:
        return rows, f"{error}; {reward_error}"
    return rows, error or reward_error


def _row_identity(row: dict) -> str:
    source = str(row.get("source") or "").strip().lower()
    title = re.sub(r"\s+", " ", str(row.get("title") or "").strip().lower())
    raw = f"{row.get('game')}|{row.get('region')}|{row.get('category')}|{source}|{title}"
    return hashlib.sha256(raw.encode("utf-8", "ignore")).hexdigest()[:24]


def _reward_priority(row: dict) -> tuple[int, int, float, str]:
    official = int(row.get("official_account_verified") is True or row.get("official_domain_match") is True)
    cross = int(row.get("cross_checked") is True or int(row.get("independent_source_count") or 0) >= 2)
    try:
        confidence = float(row.get("confidence") or 0.0)
    except (TypeError, ValueError, OverflowError):
        confidence = 0.0
    return official, cross, confidence, str(row.get("collected_at") or row.get("published_at") or "")


def _reward_merge(rows: list[dict]):
    annotated = [_annotate_reward_row(row) if isinstance(row, dict) else row for row in rows]
    normal_result = _ORIGINAL_MERGE(annotated)
    reward_inputs = [row for row in annotated if isinstance(row, dict) and row.get("must_show_candidate") is True]
    if not reward_inputs:
        return normal_result

    # Merge reward rows on their own so the general topic-volume cap cannot evict
    # a giveaway merely because release/tournament news is more numerous.
    reward_result = _ORIGINAL_MERGE(reward_inputs)
    reward_result.sort(key=_reward_priority, reverse=True)
    cap = max(10, int(social_event_discovery.MAX_ITEMS))
    selected = []
    seen = set()
    for row in reward_result + normal_result:
        if not isinstance(row, dict):
            continue
        marker = _row_identity(row)
        if marker in seen:
            continue
        seen.add(marker)
        selected.append(row)
        if len(selected) >= cap:
            break
    return selected


def _reward_main() -> dict:
    result = _ORIGINAL_MAIN()
    if not isinstance(result, dict):
        return result
    payload = dict(result)
    items = [dict(x) for x in payload.get("items", []) if isinstance(x, dict)]
    payload["reward_watch_count"] = sum(1 for x in items if x.get("reward_watch") is True)
    payload["reward_watch_official_count"] = sum(
        1 for x in items
        if x.get("reward_watch") is True
        and (x.get("official_account_verified") is True or x.get("official_domain_match") is True)
    )
    payload["reward_watch_policy"] = (
        "포켓몬/원피스/나루토 관련 카드·프로모·한정판·콜라보·팩·포토카드·굿즈를 "
        "증정/배포/선착순/추첨/특전으로 준다는 내용은 일반 수집범위 밖이어도 후보로 보존·표시. "
        "미검증 공개글은 후보로만 표시하고 자동 공식승격하지 않음."
    )
    atomic_write_json(social_event_discovery.OUT, payload, suffix=".reward-watch.tmp")
    return payload


def apply() -> dict:
    global _APPLIED, _PREVIOUS_DDG_SOCIAL_ONE
    if _APPLIED:
        return {"ok": True, "patch": PATCH_ID, "already_applied": True}
    base.apply()
    _harden_vocab()
    if "TCG_SOCIAL_MAX_ITEMS" not in os.environ:
        social_event_discovery.MAX_ITEMS = max(int(social_event_discovery.MAX_ITEMS), 180)
    _PREVIOUS_DDG_SOCIAL_ONE = social_event_discovery._ddg_social_one
    social_event_discovery._ddg_social_one = _reward_ddg_social_one
    social_event_discovery.merge_candidates = _reward_merge
    social_event_discovery.main = _reward_main
    _APPLIED = True
    return {
        "ok": True,
        "patch": PATCH_ID,
        "reward_scope_override": True,
        "reward_public_social_search": True,
        "reward_terms_ko": len(REWARD_TERMS["ko"]),
        "reward_terms_ja": len(REWARD_TERMS["ja"]),
        "reward_terms_en": len(REWARD_TERMS["en"]),
        "candidate_cap": social_event_discovery.MAX_ITEMS,
        "reward_candidates_prioritized": True,
        "trust_auto_promotion": False,
    }


if __name__ == "__main__":
    print(json.dumps(apply(), ensure_ascii=False))
