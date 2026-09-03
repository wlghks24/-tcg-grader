#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v144 verified missed-event recovery and cross-region social discovery.

This overlay builds on v142 without weakening its trust rules.

What improves over time
-----------------------
1. A missed event that is later verified through an official account/domain is
   stored as manual evidence and teaches bounded search terms + region anchors.
2. Those learned terms are reused in later public social searches and multi-route
   event searches.
3. Community/watch accounts may cover multiple content regions. Their language is
   no longer assumed to be the event region, so a Korean-language account can help
   discover a Japan or US event.
4. Strong geographic/publisher signals can correct the *candidate region* while
   keeping the source unverified. Region correction never upgrades trust.

Safety invariants
-----------------
- unverified community rows never teach verified vocabulary or region hints;
- social official matching requires the actual social profile URL/account, not a
  username merely mentioned in a title;
- learned values affect search priority/classification only, never trusted or
  verified flags;
- memory stays bounded in event_gap_learning.py.
"""
from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import collection_learning_hardening_v142 as base
import event_gap_learning
import fan_social_learning
import multi_route_event_discovery
import social_event_discovery
from safe_runtime import safe_urlopen

ROOT = Path(__file__).resolve().parent
MANUAL_EVIDENCE = ROOT / "manual_event_evidence.json"
PATCH_ID = 144

RECOVERY_TERMS = {
    "ko": (
        "콜라보", "프로모", "팝업", "증정", "배포", "응모", "신청", "정기구독", "대상상품",
        "구매", "응모자전원", "전원서비스", "특전", "한정카드", "프로모카드", "공식발표",
    ),
    "ja": (
        "コラボ", "プロモ", "ポップアップ", "配布", "応募", "申込", "定期購読", "対象商品",
        "購入", "応募者全員サービス", "全員サービス", "特典", "限定カード", "公式発表",
    ),
    "en": (
        "collab", "collaboration", "promo", "pop-up", "distribution", "giveaway", "apply",
        "application", "subscription", "subscriber", "eligible purchase", "bonus card",
        "limited card", "official announcement",
    ),
}

_APPLIED = False
_ORIGINAL_DDG_SOCIAL_ONE = None
_ORIGINAL_ANNOTATE_SOCIAL_ROWS = None
_ORIGINAL_FAN_ACCOUNT_MATCH = None
_ORIGINAL_OFFICIAL_SOCIAL_MATCH = None


def _status(*, already_applied: bool = False) -> dict:
    return {
        "ok": True,
        "patch": PATCH_ID,
        "already_applied": bool(already_applied),
        "base_patch": base.PATCH_ID,
        "verified_miss_learning": True,
        "cross_region_watch_search": True,
        "multilingual_watch_query": True,
        "learned_region_inference": True,
        "strict_official_social_url_match": True,
        "unverified_learning_weight": 0.0,
        "trust_auto_promotion": False,
        "max_learned_terms": event_gap_learning.MAX_TERMS,
        "max_region_hints": event_gap_learning.MAX_REGION_HINTS,
        "max_miss_recoveries": event_gap_learning.MAX_RECOVERIES,
    }


def _social_platform_matches(configured: object, parsed: str) -> bool:
    left = str(configured or "").lower().split("_", 1)[0]
    right = str(parsed or "").lower().split("_", 1)[0]
    return bool(left and left == right)


def _strict_official_social_match(registry: dict, source: str, title: str, game: str, region: str):
    """Official status requires the URL to resolve to the registered account."""
    social = social_event_discovery._parse_social_link(source)
    if not social:
        return False, None
    platform, username = social
    wanted = username.lower().lstrip("@")
    for account in registry.get("accounts", []):
        if not isinstance(account, dict) or account.get("trusted") is not True:
            continue
        if account.get("game") != game or account.get("region") != region:
            continue
        if not _social_platform_matches(account.get("platform"), platform):
            continue
        current = str(account.get("username") or "").lower().lstrip("@")
        if current and current == wanted:
            return True, str(account.get("username"))
    return False, None


def _watch_regions(account: dict) -> set[str]:
    values = account.get("content_regions")
    if not isinstance(values, list):
        values = [account.get("region")]
    return {str(x) for x in values if str(x) in social_event_discovery.REGION_LANG}


def _watch_account_applies(account: dict, game: str, region: str) -> bool:
    if not isinstance(account, dict) or account.get("game") != game or account.get("trusted") is True:
        return False
    role = str(account.get("role") or "").lower()
    if not any(token in role for token in ("community", "fan", "watch", "collector", "stock")):
        return False
    return region in _watch_regions(account)


def _v144_fan_account_match(registry: dict, source: str, title: str, game: str, region: str):
    known, author = _ORIGINAL_FAN_ACCOUNT_MATCH(registry, source, title, game, region)
    if known:
        return known, author
    social = social_event_discovery._parse_social_link(source)
    source_lower = str(source or "").lower().rstrip("/")
    title_lower = str(title or "").lower()
    for account in registry.get("watch_accounts", []):
        if not _watch_account_applies(account, game, region):
            continue
        username = str(account.get("username") or "").lower().lstrip("@")
        profile = str(account.get("profile_url") or "").lower().rstrip("/")
        if social and username and social[1].lower().lstrip("@") == username:
            return True, str(account.get("username"))
        if username and (username in title_lower or (profile and source_lower.startswith(profile))):
            return True, str(account.get("username"))
    return False, None


def _quoted_terms(values, limit=28):
    out = []
    for value in values:
        clean = re.sub(r"\s+", " ", str(value or "")).strip()[:50]
        if len(clean) < 2 or clean in out:
            continue
        if not re.search(r"[0-9A-Za-z가-힣ぁ-んァ-ヶ一-龠]", clean):
            continue
        out.append(clean)
        if len(out) >= max(1, min(40, int(limit))):
            break
    return " OR ".join(f'"{x}"' if " " in x or "-" in x else x for x in out)


def _watch_names_for(registry: dict, game: str, region: str):
    names = []
    for account in registry.get("watch_accounts", []):
        if not _watch_account_applies(account, game, region):
            continue
        username = str(account.get("username") or "").strip().lstrip("@")
        if username and username not in names:
            names.append(username)
    return names[:10]


def build_public_social_query(game: str, region: str, registry: dict, fan_learner=None, gap_learner=None) -> str:
    """Build a region-aware query whose watch-account clause is multilingual."""
    lang = social_event_discovery.REGION_LANG[region]["lang"]
    names = social_event_discovery.GAMES[game][lang][:2]
    name_expr = " OR ".join(f'"{x}"' for x in names)
    local_event = social_event_discovery._or_terms(social_event_discovery.EVENT_TERMS[lang], 18)
    local_fan = social_event_discovery._or_terms(social_event_discovery.FAN_TERMS[lang], 14)

    watch_names = _watch_names_for(registry, game, region)
    learned_names = []
    if fan_learner is not None:
        try:
            learned_names = fan_learner.preferred_authors(game, region, limit=6)
        except Exception:
            learned_names = []
    account_names = list(dict.fromkeys(watch_names + [str(x).lstrip("@") for x in learned_names]))[:12]
    account_expr = _quoted_terms(account_names, 12)

    if gap_learner is None:
        gap_learner = event_gap_learning.EventGapLearner()
    try:
        learned_terms = gap_learner.top_terms_for_region(game, region, limit=8)
    except Exception:
        learned_terms = ()

    multilingual = []
    for key in ("ko", "ja", "en"):
        multilingual.extend(RECOVERY_TERMS[key])
    multilingual.extend(learned_terms)
    watch_term_expr = _quoted_terms(multilingual, 34)

    general = f"({name_expr}) (({local_event}) OR ({local_fan}))"
    if learned_terms:
        learned_expr = _quoted_terms(learned_terms, 8)
        if learned_expr:
            general = f"({general}) OR (({name_expr}) ({learned_expr}))"
    if account_expr and watch_term_expr:
        general = f"({general}) OR (({account_expr}) ({watch_term_expr}))"
    return f"({general}) (site:x.com OR site:instagram.com OR site:youtube.com)"


def _infer_region(learner, game: str, row: dict, default: str):
    text = " ".join(
        str(row.get(key) or "")
        for key in ("title", "excerpt", "location", "source_label", "publisher", "author")
    )
    try:
        return learner.infer_region(game, text, default)
    except (AttributeError, TypeError, ValueError):
        return default, 0.5, ()


def _v144_ddg_social_one(game: str, region: str, registry: dict, fan_learner=None):
    gap_learner = event_gap_learning.EventGapLearner()
    query = build_public_social_query(game, region, registry, fan_learner, gap_learner)
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 TCG-Grader-SocialFallback/2.1"})
    try:
        with safe_urlopen(
            req,
            timeout=social_event_discovery.SOURCE_TIMEOUT,
            allowed_hosts=social_event_discovery.DDG_HOSTS,
        ) as response:
            raw = response.read(800_000).decode("utf-8", "replace")
        rows = []
        matches = re.findall(
            r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            raw,
            re.I | re.S,
        )
        for href, raw_title in matches[: social_event_discovery.MAX_PER_QUERY * 2]:
            source = social_event_discovery._decode_ddg_href(href)
            if not source or social_event_discovery._host(source) not in social_event_discovery.SOCIAL_HOSTS:
                continue
            title = social_event_discovery._short(re.sub(r"<[^>]+>", " ", html.unescape(raw_title)), 220)
            if not title:
                continue
            detected_region, region_confidence, region_signals = gap_learner.infer_region(game, title, region)
            official, author = _strict_official_social_match(registry, source, title, game, detected_region)
            host = social_event_discovery._host(source)
            kind = "x" if "x.com" in host or "twitter.com" in host else ("instagram" if "instagram.com" in host else "youtube")
            row = {
                "game": game,
                "region": detected_region,
                "query_region": region,
                "category": social_event_discovery._category(title),
                "title": title,
                "source": source,
                "source_kind": f"{kind}_public_search",
                "source_tier": "A-social" if official else "B-social",
                "source_label": f"{kind.upper()} 공식채널 검색" if official else f"{kind.upper()} 공개검색 후보",
                "author": author,
                "official_account_verified": official,
                "dates": social_event_discovery._dates(title),
                "excerpt": title,
                "status": "공식 SNS/영상 후보" if official else "SNS·유튜버 보조후보",
                "verified": official,
                "confidence": 0.93 if official else 0.57,
                "collected_at": social_event_discovery._now(),
                "region_inference_confidence": region_confidence,
                "region_inference_signals": list(region_signals),
            }
            if detected_region != region:
                row["region_inferred_from_content"] = True
                row["region_original"] = region
            rows.append(row)
            if len(rows) >= social_event_discovery.MAX_PER_QUERY:
                break
        return rows, None
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        OSError,
        ValueError,
        UnicodeDecodeError,
    ) as exc:
        return [], f"공개 SNS/YouTube v144 검색 {game}/{region}: {type(exc).__name__}"


def _v144_annotate_social_rows(rows: list[dict], registry: dict) -> list[dict]:
    """Correct candidate region before normal trust annotation.

    Only classification fields are changed. The original annotation layer still
    decides official/community status, and v144's strict URL matcher prevents title
    mentions from granting official status.
    """
    learner = event_gap_learning.EventGapLearner()
    prepared = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        source = str(row.get("source") or "")
        game = str(row.get("game") or "")
        default = str(row.get("region") or "KR")
        if (
            game in social_event_discovery.GAMES
            and default in social_event_discovery.REGION_LANG
            and social_event_discovery._host(source) in social_event_discovery.SOCIAL_HOSTS
        ):
            detected, confidence, signals = _infer_region(learner, game, row, default)
            row["region_inference_confidence"] = confidence
            row["region_inference_signals"] = list(signals)
            if detected != default:
                row["region_original"] = default
                row["region"] = detected
                row["region_inferred_from_content"] = True
        prepared.append(row)
    annotated = _ORIGINAL_ANNOTATE_SOCIAL_ROWS(prepared, registry)
    # Explicitly document the safety invariant on region-corrected community rows.
    for row in annotated:
        if row.get("region_inferred_from_content") is True and row.get("fan_candidate") is True:
            row["verified"] = False
            row["official_account_verified"] = False
            row["region_inference_trust_effect"] = "none"
    return annotated


def learn_verified_miss_evidence(learner: event_gap_learning.EventGapLearner, path=MANUAL_EVIDENCE) -> int:
    """Feed official recovered misses into bounded event-gap memory."""
    return int(learner.learn_verified_evidence_file(path))


def _extend_search_vocabulary() -> None:
    additions = {
        "ko": "응모 신청 정기구독 대상상품 구매 응모자전원 전원서비스 전원증정",
        "ja": "応募 申込 定期購読 対象商品 購入 応募者全員サービス 全員サービス",
        "en": "application subscriber subscription eligible purchase distribution bonus",
    }
    for lang, extra in additions.items():
        current = str(social_event_discovery.EVENT_TERMS.get(lang) or "")
        for token in extra.split():
            if token.lower() not in current.lower():
                current += " " + token
        social_event_discovery.EVENT_TERMS[lang] = current.strip()

    family_additions = {
        ("ja", "promo"): "応募 応募者全員サービス 定期購読 対象商品 購入 配布 特典",
        ("ja", "collab"): "ブランド コラボ 対象商品 購入",
        ("ja", "popup"): "東京 原宿 渋谷 ポップアップ 対象商品",
        ("ko", "promo"): "응모 정기구독 대상상품 구매 전원서비스 전원증정",
        ("en", "promo"): "subscriber subscription eligible purchase application distribution",
    }
    for (lang, family), extra in family_additions.items():
        current = str((multi_route_event_discovery.QUERY_FAMILIES.get(lang) or {}).get(family) or "")
        for token in extra.split():
            if token.lower() not in current.lower():
                current += " " + token
        multi_route_event_discovery.QUERY_FAMILIES[lang][family] = current.strip()

    key = ("원피스 카드", "JP")
    current_hosts = tuple(multi_route_event_discovery.PARTNER_DOMAINS.get(key) or ())
    extra_hosts = (
        "shonenjump.com", "www.shonenjump.com", "jumpcs.shueisha.co.jp", "shueisha.co.jp", "www.shueisha.co.jp",
    )
    merged = tuple(dict.fromkeys(current_hosts + extra_hosts))
    multi_route_event_discovery.PARTNER_DOMAINS[key] = merged
    multi_route_event_discovery.PARTNER_HOSTS.update(extra_hosts)


def apply() -> dict:
    global _APPLIED, _ORIGINAL_DDG_SOCIAL_ONE, _ORIGINAL_ANNOTATE_SOCIAL_ROWS
    global _ORIGINAL_FAN_ACCOUNT_MATCH, _ORIGINAL_OFFICIAL_SOCIAL_MATCH
    if _APPLIED:
        return _status(already_applied=True)

    base.apply()
    event_gap_learning.MAX_TERMS = max(int(event_gap_learning.MAX_TERMS), 1000)
    event_gap_learning.MAX_SEEN = max(int(event_gap_learning.MAX_SEEN), 900)
    event_gap_learning.MAX_REGION_HINTS = max(int(event_gap_learning.MAX_REGION_HINTS), 420)
    event_gap_learning.MAX_RECOVERIES = max(int(event_gap_learning.MAX_RECOVERIES), 260)
    _extend_search_vocabulary()

    _ORIGINAL_DDG_SOCIAL_ONE = social_event_discovery._ddg_social_one
    _ORIGINAL_ANNOTATE_SOCIAL_ROWS = social_event_discovery._annotate_social_rows
    _ORIGINAL_FAN_ACCOUNT_MATCH = social_event_discovery._fan_account_match
    _ORIGINAL_OFFICIAL_SOCIAL_MATCH = social_event_discovery._official_social_match

    social_event_discovery._official_social_match = _strict_official_social_match
    social_event_discovery._fan_account_match = _v144_fan_account_match
    social_event_discovery._ddg_social_one = _v144_ddg_social_one
    social_event_discovery._annotate_social_rows = _v144_annotate_social_rows
    multi_route_event_discovery.EventGapLearner = event_gap_learning.EventGapLearner

    _APPLIED = True
    return _status(already_applied=False)


if __name__ == "__main__":
    print(json.dumps(apply(), ensure_ascii=False))
