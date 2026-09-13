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
from safe_runtime import (atomic_write_json, diagnostic_exception, env_int,
                          normalize_public_https_redirect, require_public_https,
                          safe_read_text, validate_public_https_url)

import multi_route_event_discovery
import supplementary_discovery

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "promo_events.json"
POKEMON_KR_EVENT_INDEX = "https://pokemonkorea.co.kr/news/2"
POKEMON_KR_SEONGNAM_TOURNAMENT_PAGE = "https://pokemonkorea.co.kr/2026_battle_tournament3/menu800"
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
    "seoulmediacomics.com", "www.seoulmediacomics.com",
    "tw.portal-pokemon.com", "hk.portal-pokemon.com", "sg.portal-pokemon.com",
    "my.portal-pokemon.com", "ph.portal-pokemon.com", "th.portal-pokemon.com",
    "id.portal-pokemon.com", "pokemongo.com", "www.pokemongo.com",
}
OFFICIAL_SOCIAL_HOSTS = {"x.com", "www.x.com"}
OFFICIAL_SOCIAL_POSTS = {("smg_comic", "2081560207646441942")}
FETCH_ALLOWED = ALLOWED | OFFICIAL_SOCIAL_HOSTS
INDEXES = (
    ("KR", "원피스 카드", "https://onepiece-cardgame.kr/events.do"),
    ("KR", "원피스 카드", "https://onepiece-cardgame.kr/topics.do"),
    ("KR", "포켓몬 카드", POKEMON_KR_EVENT_INDEX),
    ("KR", "나루토 카드", "https://www.naruto-cardgame.com/asia-en/"),
    ("JP", "포켓몬 카드", "https://www.pokemon-card.com/info/"),
    ("JP", "포켓몬 카드", "https://www.pokemon.co.jp/info/"),
    ("JP", "원피스 카드", "https://www.onepiece-cardgame.com/events/"),
    ("JP", "원피스 카드", "https://one-piece.com/news/index.html"),
    ("US", "원피스 카드", "https://en.onepiece-cardgame.com/events/"),
    ("US", "포켓몬 카드", "https://www.pokemon.com/us/play-pokemon"),
    ("ASIA", "포켓몬 카드", "https://tw.portal-pokemon.com/30th/?lang=en"),
    ("ASIA", "포켓몬 카드", "https://hk.portal-pokemon.com/30th/?lang=en"),
    ("ASIA", "포켓몬 카드", "https://sg.portal-pokemon.com/30th/"),
    ("ASIA", "포켓몬 카드", "https://my.portal-pokemon.com/30th/"),
    ("ASIA", "포켓몬 카드", "https://ph.portal-pokemon.com/30th/"),
    ("ASIA", "포켓몬 카드", "https://th.portal-pokemon.com/30th/?lang=en"),
    ("ASIA", "포켓몬 카드", "https://id.portal-pokemon.com/30th/?lang=en"),
    ("JP", "나루토 카드", "https://www.naruto-cardgame.com/jp/"),
    ("JP", "나루토 카드", "https://naruto-official.com/news/"),
    ("US", "나루토 카드", "https://www.naruto-cardgame.com/en/"),
)
GAMES = ("포켓몬 카드", "원피스 카드", "나루토 카드")
CORE_REGIONS = ("KR", "JP", "US")
REGIONS = CORE_REGIONS
EVENT_REGIONS = CORE_REGIONS + ("ASIA",)
EVENT_SCOPE_PAIRS = tuple((game, region) for game in GAMES for region in CORE_REGIONS) + (("포켓몬 카드", "ASIA"),)
DATE_PRECISIONS = {"day", "month", "season", "start-only", "unannounced"}
ARCHIVE_GRACE_DAYS = 5
OFFICIAL_SOURCE_REPLACEMENTS = {
    "https://new.pokemonkorea.co.kr/card": POKEMON_KR_EVENT_INDEX,
    "https://new.pokemonkorea.co.kr/card/": POKEMON_KR_EVENT_INDEX,
    "https://new.pokemonkorea.co.kr/card/category/5": POKEMON_KR_EVENT_INDEX,
    "https://pokemoncard.co.kr/card/category/5": POKEMON_KR_EVENT_INDEX,
    "https://pokemonkorea.co.kr/2026_battle_tournament3": POKEMON_KR_SEONGNAM_TOURNAMENT_PAGE,
    "https://pokemonkorea.co.kr/": POKEMON_KR_EVENT_INDEX,
    "https://www.pokemonkorea.co.kr/": POKEMON_KR_EVENT_INDEX,
}


# 한국 영화 정보는 "없음"으로 숨기지 않고, 한국 공식 출처에서
# 개봉일이 확인될 때까지 명시적인 추적 카드로 유지한다.
# KOBIS의 일반 검색화면은 특정 영화의 검증 증거가 아니므로 건강성 probe에 쓰지 않는다.
# 후보 영화의 개별 KOBIS 레코드가 발견됐을 때만 별도 교차검증한다.
KR_MOVIE_TRACKERS = (
    {
        "game": "포켓몬 카드", "region": "KR", "category": "movie",
        "name_ko": "한국 포켓몬 영화·극장판 개봉 확인",
        "name_native": "Pokémon Movie Korea Release Watch",
        "start_date": "2026-08-23", "end_date": "2027-12-31", "claim_deadline": "2027-12-31",
        "reward": "한국 극장 개봉·재개봉·특별상영 일정이 공식 발표되면 날짜와 극장 정보를 표시",
        "condition": "포켓몬코리아 공식 발표를 우선 확인하고, 후보 영화가 발견되면 해당 영화의 KOBIS 개별 레코드를 교차검증. 미발표 날짜는 만들지 않음.",
        "location": "대한민국", "status": "한국 개봉일 미발표",
        "source": POKEMON_KR_EVENT_INDEX,
        "collection_source": POKEMON_KR_EVENT_INDEX,
        "tracking_only": True,
    },
    {
        "game": "원피스 카드", "region": "KR", "category": "movie",
        "name_ko": "한국 원피스 극장판 개봉 확인",
        "name_native": "ONE PIECE Movie Korea Release Watch",
        "start_date": "2026-08-23", "end_date": "2027-12-31", "claim_deadline": "2027-12-31",
        "reward": "한국 극장 개봉·재개봉·특별상영 일정이 확정되면 개봉일·배급 정보를 표시",
        "condition": "대원미디어 공식 발표를 우선 확인하고, 후보 영화가 발견되면 해당 영화의 KOBIS 개별 레코드를 교차검증. 미발표 날짜는 만들지 않음.",
        "location": "대한민국", "status": "한국 개봉일 미발표",
        "source": "https://daewonmedia.com/business",
        "tracking_only": True,
    },
    {
        "game": "나루토 카드", "region": "KR", "category": "movie",
        "name_ko": "한국 나루토 영화 개봉 확인",
        "name_native": "NARUTO Film Korea Release Watch",
        "start_date": "2026-08-23", "end_date": "2027-12-31", "claim_deadline": "2027-12-31",
        "reward": "실사 영화 또는 애니 극장판의 한국 개봉·배급 일정이 확정되면 한국 일정 표시",
        "condition": "NARUTO 공식 제작 발표를 우선 확인하고, 후보 영화가 발견되면 해당 영화의 KOBIS 개별 레코드를 교차검증. 한국 개봉일은 임의 생성하지 않음.",
        "location": "대한민국", "status": "한국 개봉일 미발표",
        "source": "https://naruto-official.com/en/news/01_2649",
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
    movie_tracker("원피스 카드", "US", "https://one-piece.com/news/index.html",
                  condition="미국 극장 개봉 또는 현지 배급 일정은 공식 발표가 확인될 때만 표시합니다."),
    movie_tracker("나루토 카드", "US", "https://naruto-official.com/en/news/01_2649",
                  condition="Lionsgate 실사 영화의 제작·글로벌 캐스팅은 공식 발표됐으나 미국 개봉일은 미발표입니다."),
)

# 2026-08-25에 실제 공식 페이지에서 대조한 최소 사실만 유지한다.
# 월/계절/시작일만 발표된 정보에서 내부 검토 범위를 실제 확정일처럼 표시하지 않는다.
OFFICIAL_VERIFIED_SEEDS = (
    {
        "game": "포켓몬 카드", "region": "ASIA", "category": "promo",
        "name_ko": "Pokémon RUN 30 완주자 피카츄 프로모 카드",
        "name_native": "Pokémon RUN Pikachu at Pokémon RUN 30!",
        "start_date": "2026-10-03", "end_date": "2027-01-24", "claim_deadline": "2027-01-24",
        "date_precision": "day",
        "reward": "Pokémon RUN 30 코스를 완주한 검증 참가자에게 Pokémon RUN Pikachu 프로모 카드 1장 지급",
        "condition": "Pokémon RUN 30 등록 참가자가 각 개최지 코스를 완주해야 합니다. 프로모 카드는 양도·현금교환 불가이며 향후 다른 행사에서 배포될 수 있습니다.",
        "location": "필리핀·대만·싱가포르·말레이시아·인도네시아·태국·홍콩",
        "status": "예정",
        "source": "https://tw.portal-pokemon.com/30th/topics/20260902_02/?lang=en",
        "verification_source": "https://pokemongo.com/news/pokemon-run-30-2026",
        "source_grade": "official",
        "event_scope": "official_asia_participation_promo",
        "reward_watch": True,
        "must_show_candidate": True,
        "region_members": ["PH", "TW", "SG", "MY", "ID", "TH", "HK"],
        "excluded_regions": ["KR"],
        "korea_included": False,
    },
    {
        "game": "원피스 카드", "region": "KR", "category": "collaboration",
        "name_ko": "JUMP SHOP in SEOUL 제3탄 · 원피스 포함 공식 팝업",
        "name_native": "期間限定 JUMP SHOP in SEOUL 第3弾",
        "start_date": "2026-09-23", "end_date": "2026-10-06", "claim_deadline": "2026-10-06",
        "date_precision": "day",
        "reward": "ONE PIECE·NARUTO 등 점프 작품의 슈에이샤 공식 라이선스 굿즈 판매. 카드 프로모 증정은 공식 공지에서 별도 확인되지 않음.",
        "condition": "운영시간 10:00~21:00. 상품·재고·입장 방식은 서울미디어코믹스 공식 공지와 현장 안내를 확인하세요.",
        "location": "신세계백화점 강남점 센트럴 1F 오픈 스테이지 · 서울 서초구 신반포로 176",
        "status": "2026-09-23 시작 예정",
        "source": "https://x.com/smg_comic/status/2081560207646441942",
        "verification_source": "https://www.seoulmediacomics.com/",
        "source_grade": "official", "event_scope": "licensed_ip_popup_not_tcg_tournament",
    },
    {
        "game": "나루토 카드", "region": "KR", "category": "collaboration",
        "name_ko": "JUMP SHOP in SEOUL 제3탄 · 나루토 포함 공식 팝업",
        "name_native": "期間限定 JUMP SHOP in SEOUL 第3弾",
        "start_date": "2026-09-23", "end_date": "2026-10-06", "claim_deadline": "2026-10-06",
        "date_precision": "day",
        "reward": "ONE PIECE·NARUTO 등 점프 작품의 슈에이샤 공식 라이선스 굿즈 판매. 카드 프로모 증정은 공식 공지에서 별도 확인되지 않음.",
        "condition": "운영시간 10:00~21:00. 상품·재고·입장 방식은 서울미디어코믹스 공식 공지와 현장 안내를 확인하세요.",
        "location": "신세계백화점 강남점 센트럴 1F 오픈 스테이지 · 서울 서초구 신반포로 176",
        "status": "2026-09-23 시작 예정",
        "source": "https://x.com/smg_comic/status/2081560207646441942",
        "verification_source": "https://www.seoulmediacomics.com/",
        "source_grade": "official", "event_scope": "licensed_ip_popup_not_tcg_tournament",
    },
    {
        "game": "원피스 카드", "region": "KR", "category": "promo",
        "name_ko": "PLAYGO 출시 알림 · 신사황 프로모션 팩 재배포",
        "name_native": "반다이남코코리아 PLAYGO 서비스 출시 알림 프로모션 안내",
        "start_date": "2026-09-01", "end_date": "2027-12-31", "claim_deadline": "2027-12-31",
        "date_precision": "start-only",
        "date_label": "2026년 9월 1일 시작 · PLAYGO 앱 출시 시 종료(종료일 미발표)",
        "internal_review_until": "2027-12-31",
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
    "KR": re.compile(r"\b(?:south\s+korea|republic\s+of\s+korea|seoul|busan|seongnam)\b|대한민국|한국|서울|부산|성남", re.I),
    "JP": re.compile(r"\b(?:japan|tokyo|osaka|kyoto|nagoya|yokohama|awaji|shinobi-zato)\b|일본|東京|大阪|名古屋|横浜|淡路", re.I),
    "US": re.compile(r"\b(?:u\.?s\.?a\.?|united\s+states|new\s+york|san\s+francisco|dallas|orlando|anaheim|los\s+angeles)\b|미국|뉴욕|샌프란시스코|댈러스|올랜도", re.I),
    "ASIA": re.compile(r"\b(?:asia|taiwan|taichung|kaohsiung|new\s+taipei|hong\s+kong|singapore|malaysia|kuala\s+lumpur|philippines|manila|thailand|bangkok|indonesia|jakarta)\b|아시아|대만|타이중|가오슝|신베이|홍콩|싱가포르|말레이시아|쿠알라룸푸르|필리핀|마닐라|태국|방콕|인도네시아|자카르타", re.I),
}

TIMEOUT_SECONDS = env_int('TCG_HTTP_TIMEOUT',20,5,60)
MAX_DISCOVERED_PER_INDEX = 2
EVENT_WORDS = re.compile(
    r"이벤트|행사|축제|페스티벌|페스타|축전|박람회|배틀|교류회|챔피언|토너먼트|프로모|증정|캠페인|팝업|팝업스토어|점프샵|JUMP SHOP|챌린지|도전|개최|특전|배포|콜라보|협업|영화|극장판|개봉|티저|예고편|출시|발매|신탄|부스터|스타터|예약|재발매|재판|재입고|굿즈|공식숍|공식샵|기념|주년|"
    r"러닝|달리기|완주|완주자|참가자|참가보상|참가특전|프로모카드|"
    r"イベント|祭り|祭典|フェス|フェスティバル|バトル|キャンペーン|チャンピオン|チャレンジ|開催|特典|配布|参加|完走|コラボ|映画|劇場版|上映|ティザー|予告編|発売|新弾|ブースター|スターター|予約|再販|再版|再入荷|グッズ|公式ショップ|記念|周年|"
    r"event|festival|card fest|fan fest|battle|championship|tournament|promo|giveaway|league|cup|tutorial|comic con|game night|night|collab|collaboration|convention|expo|challenge|special mission|distribution|movie|film|cinema|screening|teaser|trailer|release|launch|new set|booster|starter|preorder|reprint|re-release|restock|merch|merchandise|official shop|anniversary|commemorative|fun run|pokemon run|pokémon run|runner|participant|completion|finisher|participation reward|promo card",
    re.I,
)

EVENT_CATEGORIES = {
    "promo", "collaboration", "movie", "event", "festival", "tournament",
    "popup", "release", "reprint", "merch", "anniversary",
}


def classify_information_category(text: str) -> str:
    """Map every collected information row into one UI lifecycle category."""
    topic = multi_route_event_discovery._topic(text or "")
    if topic == "collab":
        return "collaboration"
    if topic == "stock":
        return "reprint"
    if topic in EVENT_CATEGORIES:
        return topic
    return "event"


def approved_url(url: str) -> str:
    value = validate_public_https_url(url, FETCH_ALLOWED)
    parsed = urllib.parse.urlsplit(value)
    host = (parsed.hostname or "").lower()
    if host in OFFICIAL_SOCIAL_HOSTS:
        parts = [urllib.parse.unquote(part) for part in parsed.path.split("/") if part]
        if len(parts) != 3 or parts[1] != "status" or (parts[0].lower(), parts[2]) not in OFFICIAL_SOCIAL_POSTS:
            raise ValueError("승인되지 않은 공식 SNS 게시물")
    return value


class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        absolute = normalize_public_https_redirect(req.full_url, newurl, FETCH_ALLOWED)
        approved_url(absolute)
        require_public_https(absolute, FETCH_ALLOWED)
        return super().redirect_request(req, fp, code, msg, headers, absolute)


def fetch(url: str) -> str:
    approved_url(url)
    require_public_https(url, FETCH_ALLOWED)
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 TCG-Grader-Promo-Checker/2.0"})
    opener = urllib.request.build_opener(OfficialRedirect)
    with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
        approved_url(response.geturl())
        require_public_https(response.geturl(), FETCH_ALLOWED)
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
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def normalize_event_dates(item: dict) -> dict:
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
    evidence = " ".join(str(value or "") for value in values)
    if default != "ASIA" and OUTSIDE_TARGET_REGION.search(evidence):
        return None
    found = {region for region, pattern in TARGET_REGION_HINTS.items() if pattern.search(evidence)}
    if len(found) == 1:
        return found.pop()
    if default in found or not found:
        return default
    return None


def _normalized_category(item: dict) -> str:
    category = str(item.get("category", "promo"))
    return "event" if category in {"promo", "collaboration"} else category


def _stable_source(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = urllib.parse.urlsplit(text)
    except ValueError:
        return text
    return urllib.parse.urlunsplit((parsed.scheme.lower(), (parsed.netloc or "").lower(),
                                    parsed.path.rstrip("/") or "/", parsed.query, ""))


def event_identity_key(item: dict) -> tuple[str, str, str, str, str]:
    title = str(item.get("name_native") or item.get("name_ko") or "").lower()
    title = re.sub(
        r"일정\s*(?:변경|연기|취소)\s*(?:안내|공지)?|시간\s*변경|장소\s*변경|"
        r"schedule\s*(?:change|update)|reschedul(?:e|ed|ing)|postpon(?:e|ed|ement)|cancel(?:led|ed|ation)?|"
        r"日程変更|時間変更|会場変更|延期|中止|変更のお知らせ",
        " ", title, flags=re.I,
    )
    normalized = re.sub(r"[^0-9a-z가-힣ぁ-ゟ゠-ヿ一-鿿]+", "", title)
    return (
        str(item.get("game", "")), str(item.get("region", "")),
        _normalized_category(item), _stable_source(item.get("source")), normalized,
    )


def _version_stamp(item: dict) -> dt.datetime:
    best = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    for field in ("discovered_at", "updated_at", "collected_at", "published_at"):
        raw = str(item.get(field) or "").strip()
        if not raw:
            continue
        try:
            stamp = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=dt.timezone.utc)
            stamp = stamp.astimezone(dt.timezone.utc)
            if stamp > best:
                best = stamp
        except ValueError:
            continue
    return best


def _supersede_event(previous: dict, newer: dict) -> dict:
    combined = dict(previous)
    combined.update(newer)
    history = [x for x in (previous.get("change_history") or []) if isinstance(x, dict)][-9:]
    prior_state = {
        "start_date": previous.get("start_date"),
        "end_date": previous.get("end_date"),
        "claim_deadline": previous.get("claim_deadline"),
        "status": previous.get("status"),
        "source": previous.get("source"),
    }
    current_state = {
        "start_date": newer.get("start_date"),
        "end_date": newer.get("end_date"),
        "claim_deadline": newer.get("claim_deadline"),
        "status": newer.get("status"),
        "source": newer.get("source"),
    }
    if prior_state != current_state and prior_state not in history:
        history.append(prior_state)
    if history:
        combined["change_history"] = history[-10:]
        combined["superseded_version_count"] = max(
            int(previous.get("superseded_version_count") or 0) + 1, len(history)
        )
        combined["latest_version_wins"] = True
    for field in ("link_checked_at", "link_status", "link_statuses"):
        if field not in combined and field in previous:
            combined[field] = previous[field]
    return combined


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
    category = _normalized_category(item)
    return (str(item.get("game", "")), str(item.get("region", "")),
            category, str(item.get("start_date", "")), normalized)


def merge_duplicate_events(items: list[dict]) -> tuple[list[dict], int]:
    rows: dict[tuple[str, str, str, str, str], dict] = {}
    identities: dict[tuple[str, str, str, str, str], tuple[str, str, str, str, str]] = {}
    removed = 0
    for item in items:
        key = event_key(item)
        identity = event_identity_key(item)
        previous_key = identities.get(identity) if identity[3] and identity[4] else None
        previous = rows.get(previous_key) if previous_key is not None else rows.get(key)

        if previous is None:
            rows[key] = dict(item)
            if identity[3] and identity[4]:
                identities[identity] = key
            continue

        removed += 1
        same_event_changed_version = previous_key is not None and previous_key != key
        if same_event_changed_version:
            previous_stamp = _version_stamp(previous)
            incoming_stamp = _version_stamp(item)
            newer = item if incoming_stamp >= previous_stamp else previous
            older = previous if newer is item else item
            combined = _supersede_event(older, newer)
            rows.pop(previous_key, None)
            rows[event_key(combined)] = combined
            identities[identity] = event_key(combined)
            continue

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
        if identity[3] and identity[4]:
            identities[identity] = key
    return list(rows.values()), removed


def coverage_summary(items: list[dict]) -> dict:
    watched = {(game, region) for region, game, _ in INDEXES}
    actual = {(str(item.get("game")), str(item.get("region"))) for item in items}
    movies = {(str(item.get("game")), str(item.get("region")))
              for item in items if item.get("category") == "movie"}
    matrix = []
    for game, region in EVENT_SCOPE_PAIRS:
        count = sum(item.get("game") == game and item.get("region") == region for item in items)
        movie_count = sum(item.get("game") == game and item.get("region") == region
                          and item.get("category") == "movie" for item in items)
        matrix.append({"game": game, "region": region, "official_source_count": sum(
            source_game == game and source_region == region
            for source_region, source_game, _ in INDEXES),
            "official_item_count": count, "movie_item_count": movie_count,
            "status": "공식 정보 확인" if count else "공식 발표 확인 중"})
    return {"expected_game_region_pairs": len(EVENT_SCOPE_PAIRS),
            "watched_game_region_pairs": len(watched), "covered_game_region_pairs": len(actual),
            "movie_game_region_pairs": len(movies),
            "missing_source_pairs": [f"{game}:{region}" for game, region in EVENT_SCOPE_PAIRS
                                     if (game, region) not in watched],
            "missing_movie_pairs": [f"{game}:{region}" for game, region in EVENT_SCOPE_PAIRS
                                    if (game, region) not in movies],
            "matrix": matrix}


def social_topic_expected_keys() -> list[str]:
    return [
        f"{game}/{region}/{topic}"
        for game in GAMES
        for region in REGIONS
        for topic in multi_route_event_discovery.COVERAGE_TOPICS
    ]


def effective_expiry(item: dict) -> dt.date | None:
    end = _parse_date(item.get("end_date"))
    claim = _parse_date(item.get("claim_deadline"))
    if end and claim:
        return max(end, claim)
    return claim or end


def is_expired(item: dict, today: dt.date | None = None) -> bool:
    today = today or dt.date.today()
    expiry = effective_expiry(item)
    return bool(expiry and today > expiry + dt.timedelta(days=ARCHIVE_GRACE_DAYS))


def lifecycle_state(item: dict, today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    expiry = effective_expiry(item)
    if expiry is None:
        return "current"
    if today > expiry + dt.timedelta(days=ARCHIVE_GRACE_DAYS):
        return "archive"
    if today > expiry:
        return "recently_ended"
    return "current"


def partition_event_lifecycle(items: list[dict], today: dt.date | None = None) -> tuple[list[dict], list[dict]]:
    today = today or dt.date.today()
    current, archived = [], []
    for source in items:
        item = dict(source)
        state = lifecycle_state(item, today)
        item["lifecycle"] = state
        expiry = effective_expiry(item)
        if expiry is not None:
            item["archive_on"] = (expiry + dt.timedelta(days=ARCHIVE_GRACE_DAYS + 1)).isoformat()
        (archived if state == "archive" else current).append(item)
    return current, archived


def purge_expired(items: list[dict], today: dt.date | None = None) -> tuple[list[dict], list[dict]]:
    return partition_event_lifecycle(items, today)


def valid(item: dict) -> bool:
    required = ("game", "region", "name_ko", "start_date", "end_date", "reward", "condition", "source")
    if not isinstance(item, dict) or not all(item.get(key) for key in required):
        return False
    if item.get("region") not in EVENT_REGIONS or item.get("game") not in GAMES:
        return False
    if item.get("category", "promo") not in EVENT_CATEGORIES:
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
                "category": classify_information_category(native),
                "name_ko": native if actual_region == "KR" else f"{ {'JP':'일본','US':'미국','ASIA':'아시아'}[actual_region] } 공식 행사 · {native}",
                "name_native": native,
                "start_date": start,
                "end_date": end,
                "claim_deadline": end,
                "reward": "공식 행사 안내에서 참가·입상 보상 확인",
                "condition": "공식 안내의 참가 자격·접수 일정·현장 조건을 확인하세요.",
                "location": {"KR": "한국 공식 개최점", "JP": "일본 공식 개최점", "US": "미국 공식 개최점", "ASIA": "아시아 공식 개최지"}[actual_region],
                "status": "진행 중" if dt.date.fromisoformat(start) <= dt.date.today() else "예정",
                "source": target,
                "source_grade": "official",
                "discovered_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            })
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, UnicodeDecodeError) as exc:
        errors.append(f"{region} {game} 신규행사 탐색: {diagnostic_exception(exc)}")
    return rows, errors


def _secondary_verification_transient(exc: BaseException) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return int(exc.code) in {401, 403, 405, 406, 409, 429, 500, 502, 503, 504}
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(token in text for token in (
        "timeout", "timed out", "urlerror", "temporary", "connection",
        "name resolution", "remote end closed", "reset by peer",
    ))


def check_existing(item: dict) -> tuple[dict, str | None]:
    checked = dict(item)
    try:
        collection_url = str(checked.get("collection_source") or checked["source"])
        page = fetch(collection_url)
        if checked.get("tracking_only"):
            secondary = str(checked.get("verification_source") or "").strip()
            if secondary and secondary != checked.get("source"):
                checked["verification_checked_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
                try:
                    fetch(secondary)
                except (urllib.error.URLError, TimeoutError, OSError, ValueError, UnicodeDecodeError) as exc:
                    if not _secondary_verification_transient(exc):
                        return checked, f"{checked['name_ko']} 보조검증: {diagnostic_exception(exc)}"
                    checked["verification_status"] = "secondary_temporarily_unavailable"
                    checked["verification_error"] = diagnostic_exception(exc)
                else:
                    checked["verification_status"] = "secondary_reachable"
                    checked.pop("verification_error", None)
            return checked, None

        native_tokens = re.findall(r"[가-힣ァ-ヶ一-龠]{4,}|[A-Za-z]{5,}", checked.get("name_native", ""))[:4]
        korean_tokens = re.findall(r"[가-힣]{4,}", checked.get("name_ko", ""))[:3]
        if native_tokens or korean_tokens:
            lowered = page.lower()
            if not any(token.lower() in lowered for token in native_tokens + korean_tokens):
                raise ValueError("행사명 확인 실패")
        return checked, None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, UnicodeDecodeError) as exc:
        return checked, f"{checked['name_ko']}: {diagnostic_exception(exc)}"


def refresh_auxiliary_coverage_metadata(data: dict | None = None, *, write: bool = False) -> dict:
    if data is None:
        data = json.loads(safe_read_text(DATA))
    if not isinstance(data, dict):
        raise ValueError("행사 메타데이터 형식 오류")
    errors: list[str] = []
    try:
        supplementary_path = ROOT / "supplementary_candidates.json"
        supplementary = json.loads(safe_read_text(supplementary_path)) if supplementary_path.exists() else {}
        data["supplementary_candidate_count"] = len(supplementary.get("items", [])) if isinstance(supplementary, dict) else 0
        data["supplementary_collection_mode"] = "post-integration-synchronized"
    except Exception as exc:
        data["supplementary_candidate_count"] = 0
        data["supplementary_collection_mode"] = "deferred-read-error"
        errors.append(f"보조후보 DB 읽기: {diagnostic_exception(exc)}")

    expected_keys = social_topic_expected_keys()
    try:
        social_path = ROOT / "social_event_candidates.json"
        social = json.loads(safe_read_text(social_path)) if social_path.exists() else {}
        if not isinstance(social, dict):
            raise ValueError("SNS/Google 후보 최상위 형식 오류")
        data["social_candidate_count"] = len(social.get("items", []))
        data["official_social_candidate_count"] = int(social.get("official_social_candidate_count") or 0)
        data["social_cross_checked_count"] = int(social.get("cross_checked_count") or 0)
        coverage = social.get("topic_coverage") if isinstance(social.get("topic_coverage"), dict) else {}
        data["social_topic_coverage"] = coverage
        data["social_topic_expected_cells"] = len(expected_keys)
        data["social_topic_covered_cells"] = sum(1 for key in expected_keys if int(coverage.get(key) or 0) > 0)
        undiscovered = [key for key in expected_keys if int(coverage.get(key) or 0) == 0]
        data["social_topic_missing_cells"] = undiscovered
        data["social_topic_undiscovered_cells"] = undiscovered
        data["social_topic_attempted_cells"] = int(social.get("topic_query_attempted_cells") or 0)
        data["social_topic_successful_cells"] = int(social.get("topic_query_successful_cells") or 0)
        failed_cells = social.get("topic_query_failed_cells")
        data["social_topic_failed_cells"] = [str(x) for x in failed_cells if str(x).strip()] if isinstance(failed_cells, list) else []
        data["social_topic_collection_complete"] = bool(len(expected_keys) and data["social_topic_attempted_cells"] >= len(expected_keys))
        data["social_topic_source_updated_at"] = social.get("updated_at")
        data["social_collection_mode"] = "post-integration-synchronized"
    except Exception as exc:
        data["social_candidate_count"] = 0
        data["official_social_candidate_count"] = 0
        data["social_cross_checked_count"] = 0
        data["social_topic_coverage"] = {}
        data["social_topic_expected_cells"] = len(expected_keys)
        data["social_topic_covered_cells"] = 0
        data["social_topic_missing_cells"] = expected_keys
        data["social_topic_undiscovered_cells"] = expected_keys
        data["social_topic_attempted_cells"] = 0
        data["social_topic_successful_cells"] = 0
        data["social_topic_failed_cells"] = []
        data["social_topic_collection_complete"] = False
        data["social_collection_mode"] = "deferred-read-error"
        errors.append(f"SNS/Google 후보 DB 읽기: {diagnostic_exception(exc)}")
    data["auxiliary_coverage_synced_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    data["auxiliary_coverage_errors"] = errors[:20]
    if errors:
        current_errors = [str(x) for x in (data.get("collection_errors") or []) if str(x).strip()]
        data["collection_errors"] = list(dict.fromkeys(current_errors + errors))[:80]
    if write:
        atomic_write_json(DATA, data, suffix=".aux-sync.tmp")
    return data



def _migrate_pokemon_kr_event_source(item: dict) -> tuple[dict, int]:
    """Move retired Korean Pokémon routes without discarding live event-level evidence."""
    repaired = dict(item)
    if repaired.get("game") != "포켓몬 카드" or repaired.get("region") != "KR":
        return repaired, 0

    changes = 0
    old_source = str(repaired.get("source") or "")
    original_source = str(repaired.get("original_source") or "")
    label = f"{repaired.get('name_ko', '')} {repaired.get('name_native', '')}".casefold()

    # The Seongnam tournament detail page is still live and contains the exact
    # event title/schedule. Prefer it over a generic news index when provenance
    # already points to that page, otherwise title verification loses evidence.
    seongnam_specific = (
        old_source == POKEMON_KR_SEONGNAM_TOURNAMENT_PAGE
        or old_source == "https://pokemonkorea.co.kr/2026_battle_tournament3"
        or original_source == POKEMON_KR_SEONGNAM_TOURNAMENT_PAGE
        or ("성남city" in label and original_source.startswith("https://pokemonkorea.co.kr/2026_battle_tournament3"))
    )
    if seongnam_specific:
        new_source = POKEMON_KR_SEONGNAM_TOURNAMENT_PAGE
    else:
        new_source = OFFICIAL_SOURCE_REPLACEMENTS.get(old_source, old_source)

    if new_source and new_source != old_source:
        repaired["source"] = new_source
        changes += 1
        # Link-health evidence belongs to the old URL and must not be carried
        # forward as though the replacement endpoint had already been checked.
        for field in ("link_checked_at", "link_status", "link_statuses"):
            repaired.pop(field, None)

    existing_collection = str(repaired.get("collection_source") or "")
    legacy_collection = {
        "https://new.pokemonkorea.co.kr/card",
        "https://new.pokemonkorea.co.kr/card/",
        "https://new.pokemonkorea.co.kr/card/category/5",
        "https://pokemoncard.co.kr/card/category/5",
    }
    desired_collection = None
    if str(repaired.get("source") or "") == POKEMON_KR_SEONGNAM_TOURNAMENT_PAGE:
        desired_collection = POKEMON_KR_SEONGNAM_TOURNAMENT_PAGE
    elif not existing_collection or existing_collection in legacy_collection:
        desired_collection = POKEMON_KR_EVENT_INDEX

    if desired_collection and desired_collection != existing_collection:
        repaired["collection_source"] = desired_collection
        changes += 1
        for field in ("link_checked_at", "link_status", "link_statuses"):
            repaired.pop(field, None)
    return repaired, changes


def _refresh_movie_tracker(previous: dict, tracker: dict) -> dict:
    """Refresh a tracker without retaining verification fields removed by policy."""
    refreshed = {**previous, **tracker}
    same_source = str(previous.get("source") or "") == str(tracker.get("source") or "")
    if same_source:
        for field in ("link_checked_at", "link_status", "link_statuses"):
            if field in previous:
                refreshed[field] = previous[field]

    if "verification_source" not in tracker:
        for field in (
            "verification_source", "verification_checked_at",
            "verification_status", "verification_error",
        ):
            refreshed.pop(field, None)
        statuses = refreshed.get("link_statuses")
        if isinstance(statuses, dict) and "verification_source" in statuses:
            statuses = dict(statuses)
            statuses.pop("verification_source", None)
            if statuses:
                refreshed["link_statuses"] = statuses
            else:
                refreshed.pop("link_statuses", None)
    return normalize_event_dates(refreshed)

def main() -> dict:
    data = json.loads(safe_read_text(DATA))
    original = data.get("items", [])
    original_archive = data.get("archive_items", [])
    if not isinstance(original, list) or not isinstance(original_archive, list):
        raise ValueError("행사 목록 형식 오류")
    errors = []
    valid_original = []
    repaired_count = 0
    outside_region_names = []
    for item in [*original, *original_archive]:
        if not isinstance(item, dict):
            errors.append("구조 오류: 잘못된 행사 항목")
            continue
        repaired = normalize_event_dates(item)
        repaired, source_repairs = _migrate_pokemon_kr_event_source(repaired)
        repaired_count += source_repairs
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

    movie_tracker_key = {(x.get("game"), x.get("region"), x.get("category"), x.get("name_ko")) for x in valid_original}
    for tracker in REGIONAL_MOVIE_TRACKERS:
        key = (tracker["game"], tracker["region"], tracker["category"], tracker["name_ko"])
        found = next((i for i,x in enumerate(valid_original)
                      if (x.get("game"),x.get("region"),x.get("category"),x.get("name_ko")) == key), None)
        if found is None:
            valid_original.append(normalize_event_dates(dict(tracker)))
            movie_tracker_key.add(key)
        else:
            previous=valid_original[found]
            valid_original[found]=_refresh_movie_tracker(previous, tracker)

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

    for item in valid_original:
        if item.get("region") == "US" and item.get("game") == "포켓몬 카드" \
                and "world" in str(item.get("name_native", "")).lower():
            item["verification_source"] = "https://www.pokemon-card.com/info/005605.html"

    valid_original, merged_existing = merge_duplicate_events(valid_original)
    existing, archived = partition_event_lifecycle(valid_original)
    archived_names = [item.get("name_ko", "이름 없음") for item in archived]
    if (original or original_archive) and not existing and not archived:
        raise ValueError("기존 행사 대량 삭제 방지")

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        checked_futures = [pool.submit(check_existing, item) for item in existing]
        discovery_futures = [pool.submit(discover, idx) for idx in INDEXES]
        checked_results = [future.result() for future in checked_futures]
        discovery_results = [future.result() for future in discovery_futures]

    checked = []
    known_keys = set()
    known_identities = set()
    secondary_verification_warnings = []
    for item, error in checked_results:
        checked.append(item)
        known_keys.add(event_key(item))
        known_identities.add(event_identity_key(item))
        if item.get("verification_status") == "secondary_temporarily_unavailable":
            secondary_verification_warnings.append(
                f"{item.get('name_ko', '이름 없음')}: {item.get('verification_error', '보조검증 일시 확인불가')}"
            )
        if error:
            errors.append(error)

    added = 0
    updated = 0
    for discovered, discovery_errors in discovery_results:
        errors.extend(discovery_errors)
        for item in discovered:
            key = event_key(item)
            identity = event_identity_key(item)
            if key not in known_keys and valid(item):
                checked.append(item)
                known_keys.add(key)
                if identity in known_identities:
                    updated += 1
                else:
                    added += 1
                known_identities.add(identity)

    checked, merged_discovered = merge_duplicate_events(checked)
    all_verified, merged_archive = merge_duplicate_events([*checked, *archived])
    checked, archived = partition_event_lifecycle(all_verified)
    archived_names = [item.get("name_ko", "이름 없음") for item in archived]
    data["items"] = checked
    data["archive_items"] = archived
    data["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    data["new_event_count"] = added
    data["updated_event_count"] = updated
    data["event_supersession_policy"] = "same game/region/category + exact official source URL + stable event title: newest observed schedule/status replaces stale duplicate while change_history is retained"
    data["official_seed_refresh_count"] = seeded_count
    data["merged_duplicate_event_count"] = merged_existing + merged_discovered + merged_archive
    data["excluded_outside_region_count"] = len(outside_region_names)
    data["excluded_outside_region_names"] = outside_region_names[:30]
    data["expired_event_count"] = len(archived)
    data["repaired_date_count"] = repaired_count
    data["expired_event_names"] = archived_names[:50]
    data["archive_event_count"] = len(archived)
    data["archive_grace_days"] = ARCHIVE_GRACE_DAYS
    data["last_expiry_cleanup_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    data["expiry_policy"] = "end_date/claim_deadline 중 더 늦은 종료일까지 표시하고 종료 후 5일차까지 현재 목록 유지, 6일째부터 지난 행사 보관함으로 이동하며 삭제하지 않음"
    data["discovery_sources"] = len(INDEXES)
    data["coverage"] = coverage_summary(checked)
    data["official_source_policy"] = "공식 HTTPS 허용목록 + 정확히 승인된 공식 SNS 게시물 + 실제 개최지 판별 + 월/계절/미발표 날짜 정확도 보존 + 일반 SNS/Google 후보는 공식 검증 전 자동승격 금지"
    today_iso = dt.date.today().isoformat()
    data["official_reference_check_attempted_on"] = today_iso
    if not errors:
        data["official_reference_checked_on"] = today_iso
    kr_movie_count = sum(1 for x in checked if x.get("region") == "KR" and x.get("category") == "movie")
    data["kr_movie_tracking_count"] = kr_movie_count
    movie_pairs = data["coverage"]["movie_game_region_pairs"]
    data["secondary_verification_warnings"] = secondary_verification_warnings[:50]
    data["collection_status"] = (
        f"정상 · 보조검증 {len(secondary_verification_warnings)}건 재확인 대기 · 한·일·미 영화정보 {movie_pairs}/9 조합 추적"
        if not errors and secondary_verification_warnings
        else (
            f"정상 · 한·일·미 영화정보 {movie_pairs}/9 조합 추적" if not errors
            else f"기존 확인자료 유지 · 일부 출처 재확인 필요 · 한·일·미 영화정보 {movie_pairs}/9 조합 추적"
        )
    )
    data["collection_errors"] = errors
    data = refresh_auxiliary_coverage_metadata(data, write=False)
    atomic_write_json(DATA,data,suffix=".json.tmp")
    return data


if __name__ == "__main__":
    main()
