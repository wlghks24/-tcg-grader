#!/usr/bin/env python3
"""Discover and recheck dated events from approved public official pages."""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from safe_runtime import atomic_write_json, env_int, require_public_https, safe_read_text, validate_public_https_url

import supplementary_discovery

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "promo_events.json"
ALLOWED = {
    "www.pokemon-card.com", "www.30th.pokemon-card.com",
    "pokemon.co.jp", "www.pokemon.co.jp",
    "pokemoncard.co.kr", "www.pokemoncard.co.kr",
    "pokemonkorea.co.kr", "www.pokemonkorea.co.kr",
    "onepiece-cardgame.kr", "www.onepiece-cardgame.kr",
    "www.onepiece-cardgame.com", "en.onepiece-cardgame.com",
    "cp.onepiece-cardgame.com", "one-piece.com", "www.one-piece.com",
    "shop.bandainamco-am.com", "playgo.bandainamcokorea.co.kr", "www.pokemon.com",
    "naruto-cardgame.com", "www.naruto-cardgame.com",
    "naruto-official.com", "www.naruto-official.com",
    "kobis.or.kr", "www.kobis.or.kr",
    "daewonmedia.com", "www.daewonmedia.com",
}
INDEXES = (
    ("KR", "원피스 카드", "https://onepiece-cardgame.kr/events.do"),
    ("KR", "원피스 카드", "https://onepiece-cardgame.kr/topics.do"),
    ("KR", "포켓몬 카드", "https://pokemonkorea.co.kr/"),
    ("KR", "나루토 카드", "https://www.naruto-cardgame.com/asia-en/"),
    ("JP", "포켓몬 카드", "https://www.pokemon-card.com/info/"),
    ("JP", "포켓몬 카드", "https://www.pokemon.co.jp/info/"),
    ("JP", "원피스 카드", "https://www.onepiece-cardgame.com/events/"),
    ("JP", "원피스 카드", "https://one-piece.com/news/"),
    ("US", "원피스 카드", "https://en.onepiece-cardgame.com/events/"),
    ("US", "포켓몬 카드", "https://www.pokemon.com/us/play-pokemon"),
    ("JP", "나루토 카드", "https://www.naruto-cardgame.com/jp/"),
    ("JP", "나루토 카드", "https://naruto-official.com/news/"),
    ("US", "나루토 카드", "https://www.naruto-cardgame.com/en/"),
)
GAMES = ("포켓몬 카드", "원피스 카드", "나루토 카드")
REGIONS = ("KR", "JP", "US")
DATE_PRECISIONS = {"day", "month", "season", "start-only", "unannounced"}


# 한국 영화 정보는 "없음"으로 숨기지 않고, 한국 공식/공공 출처에서
# 개봉일이 확인될 때까지 명시적인 추적 카드로 유지한다.
# 확인되지 않은 날짜를 임의 생성하지 않는 것이 원칙이다.
KR_MOVIE_TRACKERS = (
    {
        "game": "포켓몬 카드", "region": "KR", "category": "movie",
        "name_ko": "한국 포켓몬 영화·극장판 개봉 확인",
        "name_native": "Pokémon Movie Korea Release Watch",
        "start_date": "2026-08-23", "end_date": "2027-12-31", "claim_deadline": "2027-12-31",
        "reward": "한국 극장 개봉·재개봉·특별상영 일정이 공식 발표되면 날짜와 극장 정보를 표시",
        "condition": "포켓몬코리아 및 KOBIS 기준. 현재 확인 가능한 2026년 한국 신작 극장 개봉일은 공식 발표되지 않아 임의 날짜를 만들지 않음.",
        "location": "대한민국", "status": "한국 개봉일 미발표",
        "source": "https://www.pokemonkorea.co.kr/",
        "verification_source": "https://www.kobis.or.kr/kobis/business/mast/mvie/searchMovieList.do",
        "tracking_only": True,
    },
    {
        "game": "원피스 카드", "region": "KR", "category": "movie",
        "name_ko": "한국 원피스 극장판 개봉 확인",
        "name_native": "ONE PIECE Movie Korea Release Watch",
        "start_date": "2026-08-23", "end_date": "2027-12-31", "claim_deadline": "2027-12-31",
        "reward": "한국 극장 개봉·재개봉·특별상영 일정이 확정되면 개봉일·배급 정보를 표시",
        "condition": "대원미디어(국내 원피스 IP 사업)와 KOBIS 기준. 현재 확인 가능한 2026년 한국 신작 극장판 개봉일은 공식 발표되지 않음.",
        "location": "대한민국", "status": "한국 개봉일 미발표",
        "source": "https://daewonmedia.com/business",
        "verification_source": "https://www.kobis.or.kr/kobis/business/mast/mvie/searchMovieList.do",
        "tracking_only": True,
    },
    {
        "game": "나루토 카드", "region": "KR", "category": "movie",
        "name_ko": "한국 나루토 영화 개봉 확인",
        "name_native": "NARUTO Film Korea Release Watch",
        "start_date": "2026-08-23", "end_date": "2027-12-31", "claim_deadline": "2027-12-31",
        "reward": "실사 영화 또는 애니 극장판의 한국 개봉·배급 일정이 확정되면 한국 일정 표시",
        "condition": "NARUTO 공식 제작 발표와 KOBIS 한국 개봉 등록을 교차 확인. 실사 영화는 제작 진행 중이지만 한국 개봉일은 아직 공식 발표되지 않음.",
        "location": "대한민국", "status": "한국 개봉일 미발표",
        "source": "https://www.kobis.or.kr/kobis/business/mast/mvie/searchMovieList.do",
        "verification_source": "https://naruto-official.com/en/news/01_2649",
        "tracking_only": True,
    },
)


def movie_tracker(game: str, region: str, source: str, *, condition: str,
                  verification_source: str | None = None) -> dict:
    country = {"KR": "한국", "JP": "일본", "US": "미국"}[region]
    item = {
        "game": game, "region": region, "category": "movie",
        "name_ko": f"{country} {game.replace(' 카드', '')} 영화·영상 공개 정보",
        "name_native": f"{game.replace(' 카드', '')} {region} Official Film Watch",
        "start_date": "2026-08-25", "end_date": "2027-12-31",
        "claim_deadline": "2027-12-31", "date_precision": "unannounced",
        "date_label": "개봉·공개일 공식 미발표 · 공식 발표 추적 중",
        "reward": f"{country} 극장 개봉·공식 영상 공개 일정은 실제 발표 후에만 표시",
        "condition": condition, "location": country,
        "status": f"{country} 개봉일 공식 미발표", "source": source,
        "source_grade": "official", "tracking_only": True,
    }
    if verification_source:
        item["verification_source"] = verification_source
    return item


REGIONAL_MOVIE_TRACKERS = KR_MOVIE_TRACKERS + (
    movie_tracker("포켓몬 카드", "JP", "https://www.pokemon.co.jp/info/",
                  condition="포켓몬 일본 공식 발표를 확인하며 새 극장판 개봉일을 임의로 생성하지 않습니다."),
    movie_tracker("나루토 카드", "JP", "https://naruto-official.com/en/news/01_2649",
                  condition="실사 영화의 제작·글로벌 캐스팅만 공식 발표됐으며 일본 개봉일은 발표되지 않았습니다."),
    movie_tracker("원피스 카드", "US", "https://one-piece.com/news/",
                  condition="미국 극장 개봉 또는 현지 배급 일정은 공식 발표가 확인될 때만 표시합니다."),
    movie_tracker("나루토 카드", "US", "https://naruto-official.com/en/news/01_2649",
                  condition="Lionsgate 실사 영화의 제작·글로벌 캐스팅은 공식 발표됐으나 미국 개봉일은 미발표입니다."),
)

# 2026-08-25에 실제 공식 페이지에서 대조한 최소 사실만 유지한다.
# 월/계절/시작일만 발표된 정보에서 내부 검토 범위를 실제 확정일처럼 표시하지 않는다.
OFFICIAL_VERIFIED_SEEDS = (
    {
        "game": "원피스 카드", "region": "KR", "category": "promo",
        "name_ko": "PLAYGO 출시 알림 · 신사황 프로모션 팩 재배포",
        "name_native": "반다이남코코리아 PLAYGO 서비스 출시 알림 프로모션 안내",
        "start_date": "2026-09-01", "end_date": "2027-12-31", "claim_deadline": "2027-12-31",
        "date_precision": "start-only",
        "date_label": "2026년 9월 1일 시작 · PLAYGO 앱 출시 시 종료(종료일 미발표)",
        "internal_tracking_end": True,
        "reward": "출시 알림 신청 후 발급되는 QR을 이벤트 진행 점포에서 제시하면 특별 프로모션 팩 수령. FUN EXPO 2026 수령자는 중복 수령 불가.",
        "condition": "매장별 재고가 다르며 소진 시 종료될 수 있습니다. 공식 공지와 PLAYGO QR 교환 상태를 확인하세요.",
        "location": "한국 PLAYGO 이벤트 진행 점포",
        "status": "2026-09-01 시작 예정 · 앱 출시 시까지",
        "source": "https://onepiece-cardgame.kr/topics/view.do?brdno=6516",
        "verification_source": "https://playgo.bandainamcokorea.co.kr/",
        "source_grade": "official",
    },
    {
        "game": "나루토 카드", "region": "JP", "category": "collaboration",
        "name_ko": "NARUTO & BORUTO 닌자마을 한여름 수둔 축제",
        "name_native": "Midsummer Water Style Festival 2026 · Shinobi-Zato",
        "start_date": "2026-07-10", "end_date": "2026-09-30", "claim_deadline": "2026-09-30",
        "reward": "수둔 미션 성공자에게 공식 한정 스티커 4종 중 1종 지급 · 소진 시 종료",
        "condition": "매일 15시 체험. 닌자마을 입장권 별도 필요. 공식 현장 안내를 확인하세요.",
        "location": "일본 아와지시마 NARUTO & BORUTO Shinobi-Zato",
        "status": "진행 중", "source": "https://naruto-official.com/en/news/01_2648",
        "source_grade": "official", "date_precision": "day",
    },
    {
        "game": "원피스 카드", "region": "JP", "category": "collaboration",
        "name_ko": "원피스 밀짚모자 스토어 나고야 공식 개점 행사",
        "name_native": "ONE PIECE 麦わらストア 名古屋店 オープン",
        "start_date": "2026-09-04", "end_date": "2026-09-04", "claim_deadline": "2026-09-04",
        "reward": "나고야점 한정 상품과 공식 오픈 기념 이벤트 정보 확인",
        "condition": "공식 안내 기준 나고야 PARCO 서관 8층에서 2026년 9월 4일 개점합니다.",
        "location": "일본 나고야 PARCO 서관 8층", "status": "예정",
        "source": "https://one-piece.com/news/80639/index.html", "source_grade": "official",
        "date_precision": "day",
    },
    {
        "game": "원피스 카드", "region": "JP", "category": "collaboration",
        "name_ko": "ONE PIECE × NBA HOUSE JAPAN 공식 콜라보 배송",
        "name_native": "LUFFY's NBA HOUSE JAPAN -LOGOTYPE-",
        "start_date": "2026-09-01", "end_date": "2026-09-30", "claim_deadline": "2026-09-30",
        "date_precision": "month", "date_label": "2026년 9월 배송 예정 · 정확한 날짜 미발표",
        "reward": "LUFFY's NBA HOUSE JAPAN 공식 협업 상품 배송 예정월 확인",
        "condition": "공식 발표상 예약은 2026년 5월 31일 종료됐고 배송은 2026년 9월 예정입니다.",
        "location": "일본", "status": "예약 종료 · 2026년 9월 배송 예정",
        "source": "https://one-piece.com/news/79713/index.html", "source_grade": "official",
    },
    {
        "game": "원피스 카드", "region": "JP", "category": "movie",
        "name_ko": "THE ONE PIECE 공식 애니메이션 영상 공개",
        "name_native": "THE ONE PIECE · Netflix 配信予定",
        "start_date": "2027-02-01", "end_date": "2027-02-28", "claim_deadline": "2027-02-28",
        "date_precision": "month", "date_label": "2027년 2월 공개 예정 · 정확한 날짜 미발표",
        "media_type": "streaming_series",
        "reward": "WIT STUDIO 제작 THE ONE PIECE의 공식 Netflix 공개 예정월 확인",
        "condition": "공식 발표는 2027년 2월까지이며 공개일의 일자는 발표되지 않았습니다. 극장 영화로 분류하지 않습니다.",
        "location": "일본 공식 발표 · Netflix", "status": "2027년 2월 공개 예정",
        "source": "https://one-piece.com/news/79329/index.html", "source_grade": "official",
    },
    {
        "game": "포켓몬 카드", "region": "JP", "category": "promo",
        "name_ko": "포켓몬 데크 그대로 배틀 공식 체험 행사",
        "name_native": "デッキそのままバトル、開催！",
        "start_date": "2026-09-02", "end_date": "2027-03-02", "claim_deadline": "2027-03-02",
        "date_precision": "start-only", "date_label": "2026-09-02 시작 · 종료일 공식 미발표",
        "internal_review_until": "2027-03-02",
        "reward": "지정 스타터 덱을 사용하는 공식 체험 배틀 참가 조건 확인",
        "condition": "일본 전국 포켓몬 카드짐·포켓몬센터에서 장기 개최 예정. 종료일은 공식 미발표입니다.",
        "location": "일본 전국 포켓몬 카드짐·포켓몬센터", "status": "2026-09-02 시작 예정",
        "source": "https://www.pokemon-card.com/info/005604.html", "source_grade": "official",
    },
    {
        "game": "나루토 카드", "region": "KR", "category": "promo",
        "name_ko": "한국 나루토 카드게임 행사·정식 출시 공식 발표 추적",
        "name_native": "NARUTO CARD GAME Asia · Global Release Watch",
        "start_date": "2027-06-01", "end_date": "2027-08-31", "claim_deadline": "2027-08-31",
        "date_precision": "season",
        "date_label": "2027년 여름 글로벌 출시 예정 · 한국 행사·발매일 미발표",
        "reward": "한국 출시 여부, 체험회, 프로모 제공 여부를 아시아 공식 공지에서 추적",
        "condition": "글로벌 동시 출시 예정 계절만 발표됐습니다. 한국 개최·한국판 발매·정확한 날짜는 아직 확인되지 않았습니다.",
        "location": "대한민국 공식 일정 확인 중", "status": "한국 행사 공식 미발표",
        "source": "https://www.naruto-cardgame.com/asia-en/", "source_grade": "official",
        "tracking_only": True,
    },
)

OUTSIDE_TARGET_REGION = re.compile(
    r"\b(?:utrecht|netherlands|holland|manila|jakarta|hong\s*kong|singapore|"
    r"kuala\s*lumpur|malaysia|indonesia|philippines|paris|france|essen|germany|"
    r"lucca|italy|london|england|canada|toronto|vancouver|guangzhou|china|taiwan)\b|"
    r"위트레흐트|네덜란드|마닐라|자카르타|홍콩|싱가포르|독일|프랑스|이탈리아|광저우|대만",
    re.I,
)
TARGET_REGION_HINTS = {
    "KR": re.compile(r"\b(?:south\s*korea|republic\s+of\s+korea|seoul|busan|seongnam)\b|대한민국|한국|서울|부산|성남", re.I),
    "JP": re.compile(r"\b(?:japan|tokyo|osaka|kyoto|nagoya|yokohama|awaji|shinobi-zato)\b|일본|東京|大阪|名古屋|横浜|淡路", re.I),
    "US": re.compile(r"\b(?:u\.?s\.?a\.?|united\s+states|new\s+york|san\s+francisco|dallas|orlando|anaheim|los\s+angeles)\b|미국|뉴욕|샌프란시스코|댈러스|올랜도", re.I),
}

TIMEOUT_SECONDS = env_int('TCG_HTTP_TIMEOUT',20,5,60)
MAX_DISCOVERED_PER_INDEX = 2
EVENT_WORDS = re.compile(
    r"이벤트|행사|배틀|교류회|챔피언|토너먼트|프로모|"
    r"イベント|バトル|キャンペーン|チャンピオン|"
    r"event|battle|championship|tournament|promo|league|cup|tutorial|fest|comic con|game night|night|giveaway|teaching session|collab|collaboration|convention|expo",
    re.I,
)


def approved_url(url: str) -> str:
    return validate_public_https_url(url, ALLOWED)


class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        absolute = urllib.parse.urljoin(req.full_url, newurl)
        approved_url(absolute)
        require_public_https(absolute, ALLOWED)
        return super().redirect_request(req, fp, code, msg, headers, absolute)


def fetch(url: str) -> str:
    approved_url(url)
    require_public_https(url, ALLOWED)
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 TCG-Grader-Promo-Checker/2.0"})
    opener = urllib.request.build_opener(OfficialRedirect)
    with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
        approved_url(response.geturl())
        require_public_https(response.geturl(), ALLOWED)
        return response.read(1_500_000).decode("utf-8", "replace")


def plain(value: str) -> str:
    value = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"(?s)<[^>]+>", " ", value))).strip()


class AnchorParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.href = None
        self.parts = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.href = dict(attrs).get("href")
            self.parts = []

    def handle_data(self, value):
        if self.href is not None:
            self.parts.append(value)

    def handle_endtag(self, tag):
        if tag == "a" and self.href is not None:
            text = re.sub(r"\s+", " ", " ".join(self.parts)).strip()
            if text:
                self.links.append((self.href, text))
            self.href = None
            self.parts = []


def explicit_local_date_range(text: str) -> tuple[str, str] | None:
    """Parse ranges where the year/month are written only once.

    Examples: 2026년 8월 22일 ~ 9월 4일, 2026.8.22 - 9.4
    """
    cleaned = plain(text)
    patterns = (
        r"(20\d{2})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일?\s*(?:\([^)]*\))?\s*[-–~〜～]\s*(?:(\d{1,2})\s*월\s*)?(\d{1,2})\s*일?",
        r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})\s*[-–~〜～]\s*(?:(\d{1,2})[./-])?(\d{1,2})",
    )
    for pattern in patterns:
        m = re.search(pattern, cleaned)
        if not m:
            continue
        year, month, start_day, end_month, end_day = m.groups()
        try:
            start = dt.date(int(year), int(month), int(start_day))
            end = dt.date(int(year), int(end_month or month), int(end_day))
            if end < start and not end_month:
                # December -> January style range with omitted year/month.
                end = dt.date(int(year) + 1, 1, int(end_day))
            return start.isoformat(), end.isoformat()
        except ValueError:
            continue
    return None


def date_range(text: str) -> tuple[str, str] | None:
    explicit = explicit_local_date_range(text)
    if explicit:
        start, end = map(dt.date.fromisoformat, explicit)
        today = dt.date.today()
        if end >= today and start <= today + dt.timedelta(days=550) and (end - start).days <= 370:
            return explicit
    dates = []
    patterns = (
        r"(20\d{2})[.년/\-]\s*(\d{1,2})[.월/\-]\s*(\d{1,2})",
        r"([A-Za-z]+)\s+(\d{1,2})(?:\s*[-–~]\s*(\d{1,2}))?,?\s+(20\d{2})",
    )
    for year, month, day in re.findall(patterns[0], text):
        try:
            dates.append(dt.date(int(year), int(month), int(day)))
        except ValueError:
            continue
    for month, start, end, year in re.findall(patterns[1], text):
        try:
            first = dt.datetime.strptime(f"{month} {start} {year}", "%B %d %Y").date()
            dates.append(first)
            if end:
                dates.append(first.replace(day=int(end)))
        except ValueError:
            continue
    if not dates:
        month_day = re.findall(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일", text)
        if len(month_day) >= 2:
            year = dt.date.today().year
            for month, day in month_day[:2]:
                try:
                    dates.append(dt.date(year, int(month), int(day)))
                except ValueError:
                    continue
    if not dates:
        return None
    start, end = min(dates), max(dates)
    today = dt.date.today()
    if end < today or start > today + dt.timedelta(days=550):
        return None
    if (end - start).days > 370:
        return None
    return start.isoformat(), end.isoformat()


def detail_date_range(text: str) -> tuple[str, str] | None:
    """Extract an event period from an official detail page without using the news publication date."""
    explicit = explicit_local_date_range(text)
    if explicit:
        return explicit
    cleaned = plain(text)
    # Official franchise articles: Event Dates: July 10th to September 30th, 2026.
    cross_month = re.search(
        r"(?:Event\s+Dates?|Period|Date)\s*:?\s*([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?"
        r"\s*(?:to|[-–~])\s*([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d{2})",
        cleaned, re.I,
    )
    if cross_month:
        first_month, first_day, last_month, last_day, year = cross_month.groups()
        try:
            start = dt.datetime.strptime(f"{first_month} {first_day} {year}", "%B %d %Y").date()
            end = dt.datetime.strptime(f"{last_month} {last_day} {year}", "%B %d %Y").date()
            if end >= start:
                return start.isoformat(), end.isoformat()
        except ValueError:
            pass
    # English NARUTO/event pages: Period October 8 – 11, 2026 / Date January 7-10, 2027
    m = re.search(r"(?:Period|Date)\s+([A-Za-z]+)\s+(\d{1,2})\s*[-–~]\s*(\d{1,2}),?\s+(20\d{2})", cleaned, re.I)
    if m:
        month, start_day, end_day, year = m.groups()
        try:
            start = dt.datetime.strptime(f"{month} {start_day} {year}", "%B %d %Y").date()
            end = dt.datetime.strptime(f"{month} {end_day} {year}", "%B %d %Y").date()
            return start.isoformat(), end.isoformat()
        except ValueError:
            pass
    m = re.search(r"(?:Period|Date)\s+([A-Za-z]+)\s+(\d{1,2}),?\s+(20\d{2})", cleaned, re.I)
    if m:
        month, day, year = m.groups()
        try:
            value = dt.datetime.strptime(f"{month} {day} {year}", "%B %d %Y").date()
            return value.isoformat(), value.isoformat()
        except ValueError:
            pass
    # Japanese pages: 2026.10.08 - 10.11 / 2026年10月8日～11日
    m = re.search(r"(20\d{2})[./年](\d{1,2})[./月](\d{1,2})\s*(?:日)?\s*[-–~〜～]\s*(?:(\d{1,2})[./月])?(\d{1,2})\s*(?:日)?", cleaned)
    if m:
        year, month, start_day, end_month, end_day = m.groups()
        try:
            start = dt.date(int(year), int(month), int(start_day))
            end = dt.date(int(year), int(end_month or month), int(end_day))
            return start.isoformat(), end.isoformat()
        except ValueError:
            pass
    return None


def _parse_date(value: object) -> dt.date | None:
    """Return an ISO date or None. Never guesses malformed dates."""
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def normalize_event_dates(item: dict) -> dict:
    """Repair obviously truncated stored dates from the event title itself.

    This prevents an active event from being deleted when an older collector saved
    only the first day of a range such as '8월 22일 ~ 9월 4일'.
    """
    repaired = dict(item)
    text = " ".join(str(repaired.get(k, "")) for k in ("name_native", "name_ko"))
    parsed = explicit_local_date_range(text)
    if parsed:
        parsed_start, parsed_end = map(dt.date.fromisoformat, parsed)
        stored_start = _parse_date(repaired.get("start_date"))
        stored_end = _parse_date(repaired.get("end_date"))
        if stored_start is None or stored_start == parsed_start:
            repaired["start_date"] = parsed_start.isoformat()
        if stored_end is None or parsed_end > stored_end:
            repaired["end_date"] = parsed_end.isoformat()
            claim = _parse_date(repaired.get("claim_deadline"))
            if claim is None or claim < parsed_end:
                repaired["claim_deadline"] = parsed_end.isoformat()
    if repaired.get("category") == "movie" and not repaired.get("date_precision"):
        repaired["tracking_only"] = True
        repaired["date_precision"] = "unannounced"
        repaired["date_label"] = "개봉·공개일 공식 미발표 · 공식 발표 추적 중"
    repaired.setdefault("source_grade", "official")
    return repaired


def event_region(default: str, *values: object) -> str | None:
    """Classify the actual venue, never the language of the publisher's website."""
    evidence = " ".join(str(value or "") for value in values)
    if OUTSIDE_TARGET_REGION.search(evidence):
        return None
    found = {region for region, pattern in TARGET_REGION_HINTS.items() if pattern.search(evidence)}
    if len(found) == 1:
        return found.pop()
    if default in found or not found:
        return default
    return None


def event_key(item: dict) -> tuple[str, str, str, str, str]:
    title = str(item.get("name_native") or item.get("name_ko") or "").lower()
    aliases = (
        ("limited-battle", r"리미티드\s*배틀|limited\s*battle"),
        ("flagship-battle", r"플래그쉽\s*배틀|flagship\s*battle"),
        ("standard-battle", r"스탠다드\s*배틀|standard\s*battle"),
        ("exchange-meeting", r"교류회"),
        ("new-york-comic-con", r"new\s*york\s*comic\s*con"),
    )
    normalized = next((key for key, pattern in aliases if re.search(pattern, title, re.I)), "")
    if not normalized:
        normalized = re.sub(r"[^0-9a-z가-힣ぁ-ゟ゠-ヿ一-鿿]+", "", title)
    category = str(item.get("category", "promo"))
    if category in {"promo", "collaboration"}:
        category = "event"
    return (str(item.get("game", "")), str(item.get("region", "")),
            category, str(item.get("start_date", "")), normalized)


def merge_duplicate_events(items: list[dict]) -> tuple[list[dict], int]:
    """Merge index/detail duplicates while preserving the best official details."""
    rows: dict[tuple[str, str, str, str, str], dict] = {}
    removed = 0
    for item in items:
        key = event_key(item)
        previous = rows.get(key)
        if previous is None:
            rows[key] = dict(item)
            continue
        removed += 1
        combined = dict(previous)
        if len(str(item.get("source", ""))) > len(str(previous.get("source", ""))):
            combined["source"] = item["source"]
        for field in ("reward", "condition", "location"):
            if len(str(item.get(field, ""))) > len(str(combined.get(field, ""))):
                combined[field] = item[field]
        if len(str(item.get("name_ko", ""))) < len(str(combined.get("name_ko", ""))):
            combined["name_ko"] = item["name_ko"]
        previous_claim = _parse_date(combined.get("claim_deadline"))
        next_claim = _parse_date(item.get("claim_deadline"))
        if next_claim and (not previous_claim or next_claim > previous_claim):
            combined["claim_deadline"] = next_claim.isoformat()
        rows[key] = combined
    return list(rows.values()), removed


def coverage_summary(items: list[dict]) -> dict:
    watched = {(game, region) for region, game, _ in INDEXES}
    actual = {(str(item.get("game")), str(item.get("region"))) for item in items}
    movies = {(str(item.get("game")), str(item.get("region")))
              for item in items if item.get("category") == "movie"}
    matrix = []
    for game in GAMES:
        for region in REGIONS:
            count = sum(item.get("game") == game and item.get("region") == region for item in items)
            movie_count = sum(item.get("game") == game and item.get("region") == region
                              and item.get("category") == "movie" for item in items)
            matrix.append({"game": game, "region": region, "official_source_count": sum(
                source_game == game and source_region == region
                for source_region, source_game, _ in INDEXES),
                "official_item_count": count, "movie_item_count": movie_count,
                "status": "공식 정보 확인" if count else "공식 발표 확인 중"})
    return {"expected_game_region_pairs": len(GAMES) * len(REGIONS),
            "watched_game_region_pairs": len(watched), "covered_game_region_pairs": len(actual),
            "movie_game_region_pairs": len(movies),
            "missing_source_pairs": [f"{game}:{region}" for game in GAMES for region in REGIONS
                                     if (game, region) not in watched],
            "missing_movie_pairs": [f"{game}:{region}" for game in GAMES for region in REGIONS
                                    if (game, region) not in movies],
            "matrix": matrix}


def effective_expiry(item: dict) -> dt.date | None:
    """Last date on which an event still has user value.

    If a reward/claim deadline exists after the event end, keep the item until
    that deadline so users do not lose still-actionable redemption info.
    """
    end = _parse_date(item.get("end_date"))
    claim = _parse_date(item.get("claim_deadline"))
    if end and claim:
        return max(end, claim)
    return claim or end


def is_expired(item: dict, today: dt.date | None = None) -> bool:
    today = today or dt.date.today()
    expiry = effective_expiry(item)
    return bool(expiry and expiry < today)


def purge_expired(items: list[dict], today: dt.date | None = None) -> tuple[list[dict], list[dict]]:
    """Split records into active/actionable and expired records."""
    today = today or dt.date.today()
    kept, removed = [], []
    for item in items:
        (removed if is_expired(item, today) else kept).append(item)
    return kept, removed


def valid(item: dict) -> bool:
    required = ("game", "region", "name_ko", "start_date", "end_date", "reward", "condition", "source")
    if not isinstance(item, dict) or not all(item.get(key) for key in required):
        return False
    if item.get("region") not in REGIONS or item.get("game") not in GAMES:
        return False
    if item.get("category", "promo") not in {"promo", "collaboration", "movie"}:
        return False
    if item.get("source_grade", "official") != "official":
        return False
    try:
        approved_url(item["source"])
        if item.get("verification_source"):
            approved_url(item["verification_source"])
        start = dt.date.fromisoformat(item["start_date"])
        end = dt.date.fromisoformat(item["end_date"])
        claim = _parse_date(item.get("claim_deadline"))
        if item.get("claim_deadline") and claim is None:
            return False
        precision = item.get("date_precision", "day")
        if precision not in DATE_PRECISIONS:
            return False
        if precision != "day" and not item.get("date_label"):
            return False
        if precision == "month" and (start.day != 1 or start.year != end.year
                                      or start.month != end.month
                                      or (end + dt.timedelta(days=1)).month == end.month):
            return False
        if precision == "start-only" and item.get("internal_review_until") != item.get("end_date"):
            return False
        if precision == "unannounced" and item.get("tracking_only") is not True:
            return False
    except (ValueError, TypeError):
        return False
    return start <= end and (claim is None or claim >= start)


def discover(index: tuple[str, str, str]) -> tuple[list[dict], list[str]]:
    region, game, root_url = index
    rows = []
    errors = []
    try:
        raw = fetch(root_url)
        parser = AnchorParser()
        parser.feed(raw)
        for href, label in parser.links:
            if len(rows) >= MAX_DISCOVERED_PER_INDEX:
                break
            if not EVENT_WORDS.search(label) or len(label) < 8:
                continue
            target = urllib.parse.urljoin(root_url, href).split("#", 1)[0]
            try:
                approved_url(target)
            except ValueError:
                continue
            dates = date_range(label)
            detail_text = ""
            if dates is None:
                try:
                    detail_text = fetch(target)
                    dates = detail_date_range(detail_text)
                except (urllib.error.URLError, TimeoutError, OSError, ValueError, UnicodeDecodeError):
                    dates = None
            if dates is None:
                continue
            start, end = dates
            native = re.sub(r"\s+", " ", label).strip()[:140]
            actual_region = event_region(region, native, target)
            if actual_region is None:
                continue
            rows.append({
                "game": game,
                "region": actual_region,
                "category": "collaboration" if EVENT_WORDS.search(native) and re.search(r"교류|collab|champion|チャンピオン|fest|comic con|night|convention|expo", native, re.I) else "promo",
                "name_ko": native if actual_region == "KR" else f"{'일본' if actual_region == 'JP' else '미국'} 공식 행사 · {native}",
                "name_native": native,
                "start_date": start,
                "end_date": end,
                "claim_deadline": end,
                "reward": "공식 행사 안내에서 참가·입상 보상 확인",
                "condition": "공식 안내의 참가 자격·접수 일정·현장 조건을 확인하세요.",
                "location": {"KR": "한국 공식 개최점", "JP": "일본 공식 개최점", "US": "미국 공식 개최점"}[actual_region],
                "status": "진행 중" if dt.date.fromisoformat(start) <= dt.date.today() else "예정",
                "source": target,
                "source_grade": "official",
                "discovered_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            })
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, UnicodeDecodeError) as exc:
        errors.append(f"{region} {game} 신규행사 탐색: {type(exc).__name__}")
    return rows, errors


def check_existing(item: dict) -> tuple[dict, str | None]:
    try:
        page = fetch(item["source"])
        if not item.get("tracking_only"):
            native_tokens = re.findall(r"[가-힣ァ-ヶ一-龠]{4,}|[A-Za-z]{5,}", item.get("name_native", ""))[:4]
            korean_tokens = re.findall(r"[가-힣]{4,}", item.get("name_ko", ""))[:3]
            if native_tokens or korean_tokens:
                lowered = page.lower()
                if not any(token.lower() in lowered for token in native_tokens + korean_tokens):
                    raise ValueError("행사명 확인 실패")
        return item, None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, UnicodeDecodeError) as exc:
        return item, f"{item['name_ko']}: {type(exc).__name__}"


def main() -> dict:
    data = json.loads(safe_read_text(DATA))
    original = data.get("items", [])
    if not isinstance(original, list):
        raise ValueError("행사 목록 형식 오류")
    errors = []
    valid_original = []
    repaired_count = 0
    outside_region_names = []
    for item in original:
        if not isinstance(item, dict):
            errors.append("구조 오류: 잘못된 행사 항목")
            continue
        repaired = normalize_event_dates(item)
        actual_region = event_region(str(repaired.get("region", "")), repaired.get("name_native"),
                                     repaired.get("name_ko"), repaired.get("source"), repaired.get("location"))
        if actual_region is None:
            outside_region_names.append(str(repaired.get("name_ko", "이름 없음")))
            continue
        if actual_region != repaired.get("region"):
            repaired["region"] = actual_region
            repaired_count += 1
        if repaired.get("end_date") != item.get("end_date") or repaired.get("claim_deadline") != item.get("claim_deadline"):
            repaired_count += 1
        if valid(repaired):
            valid_original.append(repaired)
        else:
            errors.append(f"구조 오류: {item.get('name_ko', '이름 없음')}")

    # 한국·일본·미국 영화 항목을 보장하되, 날짜가 발표되지 않은 상태를
    # 내부 검토 기한과 분리해서 화면에 정확하게 표시한다.
    movie_tracker_key = {(x.get("game"), x.get("region"), x.get("category"), x.get("name_ko")) for x in valid_original}
    for tracker in REGIONAL_MOVIE_TRACKERS:
        key = (tracker["game"], tracker["region"], tracker["category"], tracker["name_ko"])
        if key not in movie_tracker_key:
            valid_original.append(normalize_event_dates(dict(tracker)))
            movie_tracker_key.add(key)

    seeded_count = 0
    for seed in OFFICIAL_VERIFIED_SEEDS:
        found = next((index for index, current in enumerate(valid_original)
                      if current.get("game") == seed["game"]
                      and current.get("region") == seed["region"]
                      and current.get("category") == seed["category"]
                      and current.get("source") == seed["source"]), None)
        if found is None:
            valid_original.append(dict(seed))
            seeded_count += 1
        else:
            valid_original[found] = {**valid_original[found], **seed}

    # 일본 공식 기사도 샌프란시스코 개최를 독립적으로 확인한다.
    for item in valid_original:
        if item.get("region") == "US" and item.get("game") == "포켓몬 카드" \
                and "world" in str(item.get("name_native", "")).lower():
            item["verification_source"] = "https://www.pokemon-card.com/info/005605.html"

    valid_original, merged_existing = merge_duplicate_events(valid_original)

    # 네트워크 확인 전에 날짜가 지난 항목을 먼저 제거한다. 행사 종료 뒤
    # 수령 기한이 더 늦으면 그 수령 기한까지는 유지한다.
    existing, expired = purge_expired(valid_original)
    expired_names = [item.get("name_ko", "이름 없음") for item in expired]
    if original and not existing and not expired:
        raise ValueError("기존 행사 대량 삭제 방지")

    # 기존 행사 재확인과 신규 행사 탐색을 동시에 수행한다.
    # 느린 공식 사이트 하나 때문에 전체 업데이트가 직렬로 지연되지 않도록 격리한다.
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        checked_futures = [pool.submit(check_existing, item) for item in existing]
        discovery_futures = [pool.submit(discover, idx) for idx in INDEXES]
        checked_results = [future.result() for future in checked_futures]
        discovery_results = [future.result() for future in discovery_futures]

    checked = []
    known_keys = set()
    for item, error in checked_results:
        checked.append(item)
        known_keys.add(event_key(item))
        if error:
            errors.append(error)

    added = 0
    for discovered, discovery_errors in discovery_results:
        errors.extend(discovery_errors)
        for item in discovered:
            key = event_key(item)
            if key not in known_keys and valid(item):
                checked.append(item)
                known_keys.add(key)
                added += 1

    checked, merged_discovered = merge_duplicate_events(checked)

    data["items"] = checked
    data["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    # 발견 직후에도 방어적으로 한 번 더 만료 필터를 적용한다.
    checked, newly_expired = purge_expired(checked)
    if newly_expired:
        expired.extend(newly_expired)
        expired_names.extend(item.get("name_ko", "이름 없음") for item in newly_expired)
    data["items"] = checked
    data["new_event_count"] = added
    data["official_seed_refresh_count"] = seeded_count
    data["merged_duplicate_event_count"] = merged_existing + merged_discovered
    data["excluded_outside_region_count"] = len(outside_region_names)
    data["excluded_outside_region_names"] = outside_region_names[:30]
    data["expired_event_count"] = len(expired)
    data["repaired_date_count"] = repaired_count
    data["expired_event_names"] = expired_names[:50]
    data["last_expiry_cleanup_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    data["expiry_policy"] = "end_date/claim_deadline 중 더 늦은 날짜가 오늘보다 이전이면 자동 삭제"
    data["discovery_sources"] = len(INDEXES)
    data["coverage"] = coverage_summary(checked)
    data["official_source_policy"] = "공식 HTTPS 허용목록 + 실제 개최지 판별 + 월/계절/미발표 날짜 정확도 보존 + SNS/Google 후보는 공식 검증 전 자동승격 금지"
    data["official_reference_checked_on"] = "2026-08-25"
    kr_movie_count = sum(1 for x in checked if x.get("region") == "KR" and x.get("category") == "movie")
    data["kr_movie_tracking_count"] = kr_movie_count
    movie_pairs = data["coverage"]["movie_game_region_pairs"]
    data["collection_status"] = (
        f"정상 · 한·일·미 영화정보 {movie_pairs}/9 조합 추적" if not errors
        else f"기존 확인자료 유지 · 일부 출처 재확인 필요 · 한·일·미 영화정보 {movie_pairs}/9 조합 추적"
    )
    data["collection_errors"] = errors
    # v64: 보조출처 탐색은 auto_update_all의 통합 보조작업에서 별도로 1회 실행한다.
    # 프로모 수집기 안에서 다시 네트워크 탐색하면 동일 출처를 중복 요청해 지연/429를 늘릴 수 있으므로
    # 여기서는 직전 후보 DB의 개수만 읽어 표시한다. 통합 보조작업 실패 시에도 기존 후보는 유지된다.
    try:
        supplementary_path = ROOT / "supplementary_candidates.json"
        supplementary = json.loads(safe_read_text(supplementary_path)) if supplementary_path.exists() else {}
        data["supplementary_candidate_count"] = len(supplementary.get("items", []))
        data["supplementary_collection_mode"] = "deferred-to-integration-stage"
    except Exception as exc:
        data["supplementary_candidate_count"] = 0
        data["supplementary_collection_mode"] = "deferred-read-error"
        errors.append(f"보조후보 DB 읽기: {type(exc).__name__}")
    try:
        social_path = ROOT / "social_event_candidates.json"
        social = json.loads(safe_read_text(social_path)) if social_path.exists() else {}
        data["social_candidate_count"] = len(social.get("items", []))
        data["official_social_candidate_count"] = int(social.get("official_social_candidate_count") or 0)
        data["social_cross_checked_count"] = int(social.get("cross_checked_count") or 0)
        data["social_collection_mode"] = "deferred-to-integration-stage"
    except Exception as exc:
        data["social_candidate_count"] = 0
        data["official_social_candidate_count"] = 0
        data["social_cross_checked_count"] = 0
        data["social_collection_mode"] = "deferred-read-error"
        errors.append(f"SNS/Google 후보 DB 읽기: {type(exc).__name__}")
    atomic_write_json(DATA,data,suffix=".json.tmp")
    return data


if __name__ == "__main__":
    main()
