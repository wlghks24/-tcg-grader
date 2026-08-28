#!/usr/bin/env python3
"""Supplementary discovery for promo/movie/collaboration leads.

Source policy:
- Tier A: official/public primary sources. May be shown as confirmed.
- Tier B: reputable news / public databases. Used for cross-checking.
- Tier C: community wiki (Namuwiki or mirror). Discovery only; never upgrades a
  claim to official by itself.

Only metadata, dates and short snippets are retained from secondary sources.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from safe_runtime import atomic_write_json, env_int, safe_urlopen, validate_public_https_url

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "supplementary_candidates.json"
TIMEOUT = env_int('TCG_HTTP_TIMEOUT',20,5,60)

# Search/landing pages. Direct Namuwiki may reject automated access; an accessible
# mirror is used only as a fallback discovery source and is always labelled Tier C.
NAMU_TOPICS = (
    ("나루토 카드", "movie", "나루토(영화)"),
    ("포켓몬 카드", "movie", "포켓몬스터(애니메이션)/극장판"),
    ("원피스 카드", "movie", "원피스(애니메이션)/극장판"),
    ("원피스 카드", "collaboration", "원피스/콜라보레이션"),
    ("포켓몬 카드", "collaboration", "포켓몬스터/이벤트"),
)

ALLOWED_SECONDARY = {
    "namu.wiki", "www.namu.wiki", "namu.moe", "www.namu.moe",
    "news.google.com", "v.daum.net", "www.hankyung.com", "hankyung.com",
    "biz.chosun.com", "www.newspim.com", "newspim.com",
}
ALLOWED_OFFICIAL_EVIDENCE = {
    "one-piece.com", "www.one-piece.com", "www.onepiece-cardgame.com",
    "en.onepiece-cardgame.com", "onepiece-cardgame.kr", "www.onepiece-cardgame.kr",
    "naruto-official.com", "www.naruto-official.com",
    "naruto-cardgame.com", "www.naruto-cardgame.com",
    "www.pokemon-card.com", "pokemonkorea.co.kr", "www.pokemonkorea.co.kr",
    "pokemon.co.jp", "www.pokemon.co.jp", "www.pokemon.com",
    "kobis.or.kr", "www.kobis.or.kr", "daewonmedia.com", "www.daewonmedia.com",
}


def secondary_url(url: str) -> str:
    p = urllib.parse.urlsplit(url)
    if p.scheme != "https" or p.hostname not in ALLOWED_SECONDARY:
        raise ValueError("허용되지 않은 보조 출처")
    if p.username or p.password or p.port not in (None, 443):
        raise ValueError("위험 주소")
    return url


def fetch(url: str) -> str:
    secondary_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 TCG-Grader-Supplementary/1.0"})
    with safe_urlopen(req, timeout=TIMEOUT, allowed_hosts=ALLOWED_SECONDARY) as r:
        final = r.geturl()
        secondary_url(final)
        return r.read(900_000).decode("utf-8", "replace")


def clean(text: str) -> str:
    text = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def find_dates(text: str) -> list[str]:
    dates = []
    for y, m, d in re.findall(r"(20\d{2})[년./-]\s*(\d{1,2})[월./-]\s*(\d{1,2})", text):
        try:
            dates.append(dt.date(int(y), int(m), int(d)).isoformat())
        except ValueError:
            pass
    return sorted(set(dates))[:8]


def namu_discovery() -> list[dict]:
    rows = []
    for game, category, topic in NAMU_TOPICS:
        encoded = urllib.parse.quote(topic, safe="")
        urls = [f"https://namu.wiki/w/{encoded}", f"https://www.namu.moe/w/{encoded}"]
        last_error = None
        for url in urls:
            try:
                raw = fetch(url)
                text = clean(raw)
                if len(text) < 80:
                    continue
                dates = find_dates(text)
                # Keep only a short discovery excerpt; never store the article body.
                excerpt = text[:220]
                rows.append({
                    "game": game,
                    "category": category,
                    "region": "KR",
                    "title": topic,
                    "source": url,
                    "source_tier": "C",
                    "source_label": "나무위키 보조탐색" if "namu.wiki" in url else "나무위키 미러 보조탐색",
                    "dates": dates,
                    "excerpt": excerpt,
                    "status": "보조출처 후보",
                    "verified": False,
                    "collected_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                })
                break
            except (urllib.error.URLError, TimeoutError, OSError, ValueError, UnicodeDecodeError) as exc:
                # v73: only expected fetch/security failures become "retry later".
                # Programming regressions must escape so the outer learner/test suite records them.
                last_error = type(exc).__name__
        if last_error and not any(x.get("title") == topic for x in rows):
            rows.append({
                "game": game, "category": category, "region": "KR", "title": topic,
                "source": urls[0], "source_tier": "C", "source_label": "나무위키 보조탐색",
                "dates": [], "excerpt": "자동 접근 제한 또는 네트워크 지연으로 다음 업데이트에서 재확인",
                "status": "재확인 대기", "verified": False, "error": last_error,
                "collected_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            })
    return rows


# Curated cross-checks discovered from public web research. These are deliberately
# small and structured. They complement, rather than replace, the live collectors.
CROSS_CHECK_SEEDS = [
    {
        "game": "나루토 카드", "category": "movie", "region": "KR",
        "title": "나루토 실사 영화 제작·글로벌 캐스팅 보조 확인",
        "source": "https://www.namu.moe/w/%EB%82%98%EB%A3%A8%ED%86%A0%28%EC%98%81%ED%99%94%29",
        "source_tier": "C", "source_label": "나무위키 미러 보조정보",
        "dates": [], "date_precision": "unannounced",
        "date_label": "한국 개봉일 공식 미발표",
        "excerpt": "실사 영화 제작과 글로벌 캐스팅은 공식 발표됐지만 한국 캐스팅·개봉일은 공식 확인되지 않았습니다.",
        "status": "보조후보 · 한국 개봉일 미발표", "verified": False,
        "official_source": "https://naruto-official.com/en/news/01_2649",
        "confidence": 0.60,
    },
    {
        "game": "원피스 카드", "category": "collaboration", "region": "JP",
        "title": "ONE PIECE × NBA 스페셜 콜라보",
        "source": "https://one-piece.com/news/79713/index.html",
        "source_tier": "A", "source_label": "ONE PIECE 공식",
        "dates": [], "release_window": "2026-09", "date_precision": "month",
        "date_label": "2026년 9월 배송 예정 · 정확한 날짜 미발표",
        "excerpt": "NBA HOUSE JAPAN 협업 상품은 예약이 종료됐으며 공식 배송 예정은 2026년 9월입니다.",
        "status": "공식확인", "verified": True, "confidence": 1.0,
    },
    {
        "game": "원피스 카드", "category": "movie", "region": "JP",
        "title": "THE ONE PIECE · 2027년 2월 Netflix 공개",
        "source": "https://one-piece.com/news/79329/index.html",
        "source_tier": "A", "source_label": "ONE PIECE 공식",
        "dates": [], "release_window": "2027-02", "date_precision": "month",
        "date_label": "2027년 2월 공개 예정 · 정확한 날짜 미발표",
        "excerpt": "WIT STUDIO의 새 애니메이션 시리즈는 2027년 2월 Netflix 공개 예정이며 정확한 공개일은 미발표입니다.",
        "status": "공식확인", "verified": True, "confidence": 1.0,
    },
]


def normalize_candidate(row: dict) -> dict:
    """Never promote community claims or manufacture a day from a month."""
    if not isinstance(row, dict):
        raise ValueError("보조후보 형식 오류")
    cleaned = dict(row)
    if cleaned.get("region") not in {"KR", "JP", "US"}:
        raise ValueError("보조후보 국가 오류")
    if cleaned.get("category") not in {"promo", "collaboration", "movie"}:
        raise ValueError("보조후보 종류 오류")
    tier = cleaned.get("source_tier")
    if tier == "A":
        validate_public_https_url(str(cleaned.get("source", "")), ALLOWED_OFFICIAL_EVIDENCE)
    elif tier in {"B", "C"}:
        secondary_url(str(cleaned.get("source", "")))
    else:
        raise ValueError("보조후보 출처등급 오류")

    official = cleaned.get("official_source")
    if official:
        validate_public_https_url(str(official), ALLOWED_OFFICIAL_EVIDENCE)
    verified = cleaned.get("verified") is True
    independently_confirmed = cleaned.get("official_claim_confirmed") is True
    cleaned["verified"] = verified and (tier == "A" or bool(official and independently_confirmed))
    if not cleaned["verified"] and tier != "A":
        cleaned["status"] = cleaned.get("status") or "보조출처 후보"

    precision = cleaned.get("date_precision", "day")
    dates = cleaned.get("dates", [])
    if not isinstance(dates, list):
        raise ValueError("보조후보 날짜 목록 오류")
    if precision in {"month", "unannounced"}:
        if dates:
            raise ValueError("월/미발표 정보를 임의 확정일로 저장할 수 없습니다")
        if not isinstance(cleaned.get("date_label"), str) or not cleaned["date_label"].strip():
            raise ValueError("미확정 날짜 설명 누락")
        if precision == "month" and not re.fullmatch(r"20\d{2}-(?:0[1-9]|1[0-2])",
                                                      str(cleaned.get("release_window", ""))):
            raise ValueError("공식 공개 예정월 오류")
    elif precision == "day":
        for value in dates:
            if not isinstance(value, str) or dt.date.fromisoformat(value).isoformat() != value:
                raise ValueError("보조후보 확정 날짜 오류")
    else:
        raise ValueError("보조후보 날짜 정확도 오류")
    return cleaned


def merge_unique(rows: list[dict]) -> list[dict]:
    out, seen = [], set()
    for row in rows:
        row = normalize_candidate(row)
        key = (row.get("game"), row.get("category"), row.get("region"), row.get("title"))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def main() -> dict:
    discovered = namu_discovery()
    rows = merge_unique(CROSS_CHECK_SEEDS + discovered)
    payload = {
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "policy": "Tier C(나무위키/커뮤니티)는 발견용이며 단독으로 공식확정 처리하지 않음. 공식/공공/복수 독립출처와 교차 확인 후 승격.",
        "date_policy": "공식 발표가 월까지만 있으면 예정월만 표시하고 정확한 일자를 만들지 않습니다.",
        "items": rows,
    }
    atomic_write_json(OUT,payload,suffix=".json.tmp")
    return payload


if __name__ == "__main__":
    main()
