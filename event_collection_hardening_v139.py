#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Runtime hardening for fast-moving TCG movie/collab/event discovery.

This patch deliberately strengthens *discovery* without weakening trust rules:
- expands movie/collab announcement vocabulary (teaser/trailer/visual/etc.);
- performs one extra account-targeted public search for trusted official SNS;
- lets verified manual official evidence teach future search vocabulary;
- never turns a search hit into verified/trusted merely because it matched a query.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import event_gap_learning
import multi_route_event_discovery
import social_event_discovery
from safe_runtime import safe_read_text, safe_urlopen, validate_public_https_url

ROOT = Path(__file__).resolve().parent
MANUAL_EVIDENCE = ROOT / "manual_event_evidence.json"
PATCH_ID = 139
_APPLIED = False
_ORIGINAL_DDG_SOCIAL_ONE = social_event_discovery._ddg_social_one
_ORIGINAL_LEARN_VERIFIED_FILE = event_gap_learning.EventGapLearner.learn_verified_file

EXTRA_EVENT_TERMS = {
    "ko": (
        "티저", "예고", "예고편", "트레일러", "비주얼", "신작", "장편", "애니메이션",
        "THE MOVIE", "특별영상", "특별 상영", "시사회", "관람특전", "입장특전", "극장 개봉",
        "공개 예정", "발표", "공식 발표",
    ),
    "ja": (
        "ティザー", "予告", "予告編", "トレーラー", "ビジュアル", "新作", "長編", "アニメーション",
        "THE MOVIE", "特別映像", "特別上映", "試写会", "入場者特典", "劇場公開", "発表",
    ),
    "en": (
        "teaser", "trailer", "visual", "new movie", "feature animation", "animated film", "THE MOVIE",
        "special video", "special screening", "premiere", "admission bonus", "theatrical release", "announced",
    ),
}

EXTRA_ROUTE_TERMS = {
    "ko": {
        "movie": "티저 예고 예고편 트레일러 비주얼 신작 장편 애니메이션 THE MOVIE 특별영상 특별상영 시사회 관람특전 입장특전 극장개봉 발표",
        "collab": "콜라보레이션 협업 제휴 한정 캠페인 브랜드 협업 카페 편의점 마트 백화점 스포츠 야구 축구 테마파크",
        "event": "신규행사 사전예약 사전응모 현장행사 오프라인행사 전시 페스티벌 체험 부스 특별전",
        "promo": "프로모션 특전 증정품 한정카드 기념카드 영화특전 입장특전 구매특전 응모특전",
    },
    "ja": {
        "movie": "ティザー 予告 予告編 トレーラー ビジュアル 新作 長編 アニメーション THE MOVIE 特別映像 特別上映 試写会 入場者特典 劇場公開 発表",
        "collab": "コラボレーション タイアップ 限定 キャンペーン ブランド カフェ コンビニ 百貨店 スポーツ 野球 テーマパーク",
        "event": "新イベント 事前予約 事前応募 現地イベント 展示 フェス 体験 ブース 特別展",
        "promo": "プロモーション 特典 限定カード 記念カード 映画特典 入場者特典 購入特典 応募特典",
    },
    "en": {
        "movie": "teaser trailer visual new movie feature animation animated film THE MOVIE special video special screening premiere admission bonus theatrical announced",
        "collab": "collaboration partnership limited campaign brand cafe retailer department store sports baseball theme park",
        "event": "new event preregistration application onsite offline exhibition festival demo booth special exhibition",
        "promo": "promotion bonus exclusive card commemorative card movie bonus admission bonus purchase bonus campaign reward",
    },
}

FOCUS_TOPICS = ("movie", "collab", "event", "promo")
FOCUS_TERMS = {
    "ko": "영화 극장판 개봉 티저 예고 예고편 트레일러 비주얼 신작 장편 애니메이션 콜라보 협업 제휴 행사 이벤트 팝업 프로모 특전 증정 발표",
    "ja": "映画 劇場版 公開 ティザー 予告 予告編 トレーラー ビジュアル 新作 長編 アニメーション コラボ タイアップ イベント ポップアップ プロモ 特典 発表",
    "en": "movie film theatrical teaser trailer visual animation collaboration collab partnership event pop-up promo bonus announced",
}

MANUAL_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,28}|[가-힣]{2,16}|[ァ-ヶ一-龠]{2,16}")
MANUAL_PHRASE_RE = re.compile(r"\b[A-Z][A-Z0-9-]{2,}(?:\s+[A-Z][A-Z0-9-]{2,}){1,3}\b")
MANUAL_STOP = {
    "카드", "카드게임", "공식", "행사", "이벤트", "안내", "판매", "상품", "관련", "확인", "발표",
    "영화", "극장", "개봉", "예정", "공개", "신작", "애니메이션", "THE", "AND", "FOR", "MOVIE",
}


def _append_terms(existing: str, additions: tuple[str, ...] | list[str]) -> str:
    tokens = str(existing or "").split()
    seen = {token.lower() for token in tokens}
    for value in additions:
        value = str(value).strip()
        if value and value.lower() not in seen:
            tokens.append(value)
            seen.add(value.lower())
    return " ".join(tokens)


def _harden_vocab() -> None:
    for lang, additions in EXTRA_EVENT_TERMS.items():
        social_event_discovery.EVENT_TERMS[lang] = _append_terms(
            social_event_discovery.EVENT_TERMS.get(lang, ""), additions
        )
    for lang, topics in EXTRA_ROUTE_TERMS.items():
        families = multi_route_event_discovery.QUERY_FAMILIES.get(lang, {})
        for topic, additions in topics.items():
            families[topic] = _append_terms(families.get(topic, ""), additions.split())

    movie_extra = r"티저|예고편|트레일러|비주얼|장편\s*애니메이션|THE\s+MOVIE|특별\s*상영|시사회|입장특전|관람특전|ティザー|予告編|トレーラー|ビジュアル|長編|アニメーション|特別上映|試写会|theatrical|teaser|trailer|feature\s+animation|animated\s+film|premiere|admission\s+bonus"
    collab_extra = r"제휴|브랜드\s*협업|테마파크|타이업|タイアップ|partnership|theme\s*park"
    promo_extra = r"입장특전|관람특전|구매특전|응모특전|入場者特典|購入特典|応募特典|admission\s+bonus|purchase\s+bonus"
    social_event_discovery.CATEGORY_PATTERNS = (
        ("movie", re.compile(social_event_discovery.CATEGORY_PATTERNS[0][1].pattern + "|" + movie_extra, re.I)),
        ("collaboration", re.compile(social_event_discovery.CATEGORY_PATTERNS[1][1].pattern + "|" + collab_extra, re.I)),
        ("promo", re.compile(social_event_discovery.CATEGORY_PATTERNS[2][1].pattern + "|" + promo_extra, re.I)),
    )
    multi_route_event_discovery.KEYWORD_RE = re.compile(
        multi_route_event_discovery.KEYWORD_RE.pattern + "|" + movie_extra + "|" + collab_extra + "|" + promo_extra,
        re.I,
    )


def _trusted_accounts(registry: dict, game: str, region: str) -> list[dict]:
    supported = {"x", "instagram", "youtube_handle", "youtube_channel"}
    rows = []
    for row in registry.get("accounts", []):
        if not isinstance(row, dict) or row.get("trusted") is not True:
            continue
        if row.get("game") != game or row.get("region") != region:
            continue
        if row.get("platform") not in supported:
            continue
        username = str(row.get("username") or "").strip().lstrip("@")
        if username:
            clean = dict(row)
            clean["username"] = username
            rows.append(clean)
    return rows[:8]


def _strip_markup(value: str) -> str:
    value = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", value or "")
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def focused_official_social_search(game: str, region: str, registry: dict) -> tuple[list[dict], str | None]:
    """One bounded, account-targeted public search for fast official announcements."""
    accounts = _trusted_accounts(registry, game, region)
    if not accounts:
        return [], None
    lang = social_event_discovery.REGION_LANG[region]["lang"]
    names = social_event_discovery.GAMES[game][lang][:2]
    name_expr = " OR ".join(f'"{name}"' for name in names)
    account_expr = " OR ".join(f'"{row["username"]}"' for row in accounts)
    focus_tokens = [x for x in FOCUS_TERMS[lang].split() if x][:28]
    focus_expr = " OR ".join(f'"{token}"' if " " in token else token for token in focus_tokens)
    query = f"(({name_expr}) OR ({account_expr})) ({account_expr}) ({focus_expr}) (site:x.com OR site:instagram.com OR site:youtube.com)"
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 TCG-Grader-OfficialPriority/3.0"})
    try:
        with safe_urlopen(req, timeout=social_event_discovery.SOURCE_TIMEOUT, allowed_hosts=social_event_discovery.DDG_HOSTS) as response:
            raw = response.read(900_000).decode("utf-8", "replace")
        rows: list[dict] = []
        for match in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', raw, re.I | re.S):
            href, raw_title = match.group(1), match.group(2)
            source = social_event_discovery._decode_ddg_href(href)
            if not source or social_event_discovery._host(source) not in social_event_discovery.SOCIAL_HOSTS:
                continue
            try:
                validate_public_https_url(source)
            except (TypeError, ValueError):
                continue
            title = social_event_discovery._short(_strip_markup(raw_title), 220)
            context = _strip_markup(raw[max(0, match.start() - 500): min(len(raw), match.end() + 900)])
            combined = social_event_discovery._short(f"{title} {context}", 700)
            if not title:
                continue
            official, author = social_event_discovery._official_social_match(registry, source, combined, game, region)
            queried_author = next((row["username"] for row in accounts if row["username"].lower() in combined.lower()), None)
            host = social_event_discovery._host(source)
            kind = "x" if "x.com" in host or "twitter.com" in host else ("instagram" if "instagram.com" in host else "youtube")
            rows.append({
                "game": game,
                "region": region,
                "category": social_event_discovery._category(combined),
                "title": title,
                "source": source,
                "source_kind": f"{kind}_official_priority_search",
                "source_tier": "A-social" if official else "B-social-targeted",
                "source_label": "공식 SNS 집중탐색" if official else "공식계정 표적 공개검색 후보",
                "author": author or queried_author,
                "official_account_verified": bool(official),
                "official_query_target": True,
                "queried_official_account": queried_author,
                "dates": social_event_discovery._dates(combined),
                "excerpt": social_event_discovery._short(context or title, 300),
                "status": "공식 SNS 후보" if official else "공식계정 표적검색 · 게시자 재확인 필요",
                "verified": bool(official),
                "confidence": 0.95 if official else (0.74 if queried_author else 0.64),
                "priority_watch": True,
                "collected_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            })
            if len(rows) >= social_event_discovery.MAX_PER_QUERY:
                break
        return rows, None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError, UnicodeDecodeError) as exc:
        return [], f"공식 SNS 집중탐색 {game}/{region}: {type(exc).__name__}"


def _hardened_ddg_social_one(game: str, region: str, registry: dict, fan_learner=None):
    rows, error = _ORIGINAL_DDG_SOCIAL_ONE(game, region, registry, fan_learner)
    focused, focused_error = focused_official_social_search(game, region, registry)
    rows.extend(focused)
    if error and focused_error:
        return rows, f"{error}; {focused_error}"
    return rows, error or focused_error


def _manual_topic(row: dict) -> str:
    category = str(row.get("category") or "").lower()
    if category == "collaboration":
        return "collab"
    if category in {"movie", "promo", "event", "release", "reprint", "popup", "tournament", "anniversary", "merch"}:
        return category
    text = " ".join(str(row.get(k) or "") for k in ("title", "excerpt", "category"))
    return multi_route_event_discovery._topic(text)


def _manual_terms(row: dict) -> list[str]:
    text = " ".join(str(row.get(k) or "") for k in ("title", "excerpt"))
    out: list[str] = []
    for value in MANUAL_PHRASE_RE.findall(text) + MANUAL_TOKEN_RE.findall(text):
        clean = re.sub(r"\s+", " ", value).strip()[:50]
        if len(clean) < 2 or clean.upper() in MANUAL_STOP or clean in out:
            continue
        out.append(clean)
    return out[:24]


def learn_manual_official_evidence(learner: event_gap_learning.EventGapLearner, path: Path = MANUAL_EVIDENCE) -> int:
    """Teach search terms from user-provided evidence only after official verification flags exist."""
    try:
        payload = json.loads(safe_read_text(Path(path), max_bytes=500_000))
    except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        return 0
    seen = set(learner.data.get("seen_verified") or [])
    learned = 0
    for row in (payload.get("items") or [])[:200]:
        if not isinstance(row, dict):
            continue
        if row.get("manual_evidence") is not True or row.get("verified") is not True or row.get("official_account_verified") is not True:
            continue
        game = str(row.get("game") or "")
        region = str(row.get("region") or "")
        source = str(row.get("source") or "")
        if game not in social_event_discovery.GAMES or region not in social_event_discovery.REGION_LANG or not source.startswith("https://"):
            continue
        marker = hashlib.sha256(f"manual|{game}|{region}|{source}|{row.get('title')}".encode("utf-8")).hexdigest()[:24]
        if marker in seen:
            continue
        topic = _manual_topic(row)
        for term in _manual_terms(row):
            key = f"{game}|{region}|{topic}|{term}"
            stat = learner.data["terms"].setdefault(key, {})
            try:
                verified_events = int(stat.get("verified_events") or 0)
            except (TypeError, ValueError, OverflowError):
                verified_events = 0
            try:
                score = float(stat.get("score") or 0.0)
            except (TypeError, ValueError, OverflowError):
                score = 0.0
            stat["verified_events"] = max(0, min(1_000_000, verified_events + 1))
            stat["score"] = round(min(20.0, max(0.0, score) * 0.98 + 1.25), 4)
            stat["last_seen"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            stat["learned_from"] = "manual_official_evidence"
        seen.add(marker)
        learned += 1
    learner.data["seen_verified"] = list(seen)[-event_gap_learning.MAX_SEEN:]
    return learned


def _hardened_learn_verified_file(self, path=event_gap_learning.PROMO):
    learned = _ORIGINAL_LEARN_VERIFIED_FILE(self, path)
    try:
        is_default = Path(path).resolve() == Path(event_gap_learning.PROMO).resolve()
    except (OSError, ValueError):
        is_default = False
    if is_default:
        learned += learn_manual_official_evidence(self, MANUAL_EVIDENCE)
    return learned


def apply() -> dict:
    global _APPLIED
    if _APPLIED:
        return {"ok": True, "patch": PATCH_ID, "already_applied": True}
    _harden_vocab()
    social_event_discovery._ddg_social_one = _hardened_ddg_social_one
    event_gap_learning.EventGapLearner.learn_verified_file = _hardened_learn_verified_file
    # multi_route imported the class object, so patching its method is enough; keep
    # the assignment explicit for readability and future refactors.
    multi_route_event_discovery.EventGapLearner = event_gap_learning.EventGapLearner
    _APPLIED = True
    return {
        "ok": True,
        "patch": PATCH_ID,
        "official_priority_search": True,
        "manual_official_term_learning": True,
        "trust_auto_promotion": False,
    }


if __name__ == "__main__":
    print(json.dumps(apply(), ensure_ascii=False))
