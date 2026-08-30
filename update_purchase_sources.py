#!/usr/bin/env python3
"""Safely validate and refresh the curated purchase-source directory."""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import ipaddress
import json
import math
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from safe_runtime import atomic_write_json, diagnostic_exception, env_int, require_public_https, safe_read_text, validate_public_https_url

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "purchase_sources.json"
REGIONS = {"KR", "JP", "US"}
GAMES = {"Pokemon", "ONE PIECE", "NARUTO"}
TYPES = {"official", "marketplace", "used", "blog", "map", "tracker"}
RETAILER_CATEGORIES = {
    "general", "convenience", "hypermarket", "stationery", "toy",
    "bookstore", "cardshop", "discount",
}
UNVERIFIED_INVENTORY = "TCG 취급·재고 미확인 · 방문 전 공식 매장/전화 확인"
TIMEOUT_SECONDS = env_int('TCG_HTTP_TIMEOUT',20,5,60)
MAX_ONLINE_CHECKS = 12
CANONICAL_URLS = {
    "https://events.pokemon.com/en-us/locations": "https://events.pokemon.com/EventLocator",
    "https://www.gamestop.com/stores/": "https://www.gamestop.com/stores",
}

# 주소·좌표는 거리 정렬용이며, 카드 재고는 매장별 전화/지도 검색으로만 확정한다.
# 안산과 가까운 점포부터 경기도 북부까지 확인할 수 있도록 별도 지점 항목을 유지한다.
GYEONGGI_LOTTE_STORES = (
    ("롯데마트 선부점", "경기도 안산시 단원구 달미로 64", "031-487-2500", 37.3340, 126.8050),
    ("롯데마트 상록점", "경기도 안산시 상록구 반석로 8", "031-8086-0800", 37.3022, 126.8662),
    ("롯데마트 안산점", "경기도 안산시 상록구 항가울로 422", "031-508-2500", 37.2967, 126.8658),
    ("롯데마트 시화점", "경기도 시흥시 마유로 238번길 26", "031-496-7700", 37.3447, 126.7375),
    ("롯데마트 시흥배곧점", "경기도 시흥시 서울대학로278번길 67", "031-299-2500", 37.3696, 126.7292),
    ("토이저러스 광명점", "경기도 광명시 일직로 17 롯데몰 광명점 2층", "매장 안내 확인", 37.4242, 126.8847),
    ("롯데마트 의왕점", "경기도 의왕시 계원대학로 7", "031-470-2500", 37.3792, 126.9768),
    ("롯데마트 권선점", "경기도 수원시 권선구 동수원로 232", "031-229-7700", 37.2519, 127.0293),
    ("롯데마트 광교점", "경기도 수원시 영통구 센트럴타운로 85", "031-410-2500", 37.2850, 127.0578),
    ("롯데마트 천천점", "경기도 수원시 장안구 만석로19번길 25-10", "031-240-2500", 37.2988, 126.9822),
    ("롯데마트 수원점", "경기도 수원시 권선구 세화로 134", "031-8067-2500", 37.2643, 126.9972),
    ("롯데마트 롯데몰수지점", "경기도 용인시 수지구 성복2로 38", "031-5174-2500", 37.3137, 127.0804),
    ("토이저러스 기흥점", "경기도 용인시 기흥구 신고매로 124 롯데프리미엄아울렛", "매장 안내 확인", 37.2257, 127.1209),
    ("롯데마트 오산점", "경기도 오산시 경기대로 271", "031-371-2500", 37.1448, 127.0729),
    ("롯데마트 서현점", "경기도 성남시 분당구 황새울로311번길 28", "031-789-2500", 37.3850, 127.1220),
    ("롯데마트 김포한강점", "경기도 김포시 김포한강2로 41", "031-8049-2500", 37.6445, 126.6298),
    ("롯데마트 고양점", "경기도 고양시 덕양구 충장로 150", "031-930-7000", 37.6631, 126.8318),
    ("롯데마트 화정점", "경기도 고양시 덕양구 화중로 66", "031-947-2500", 37.6343, 126.8326),
    ("롯데마트 주엽점", "경기도 고양시 일산서구 중앙로 1496", "031-913-2500", 37.6706, 126.7556),
    ("토이저러스 파주점", "경기도 파주시 회동길 390 롯데프리미엄아울렛", "매장 안내 확인", 37.7176, 126.6932),
    ("롯데마트 덕소점", "경기도 남양주시 와부읍 월문천로 33", "031-579-7700", 37.5864, 127.2133),
    ("롯데마트 마석점", "경기도 남양주시 화도읍 경춘로 1992", "031-748-2500", 37.6522, 127.3068),
    ("롯데마트 장암점", "경기도 의정부시 장곡로 224", "031-849-2500", 37.7001, 127.0534),
    ("롯데마트 의정부점", "경기도 의정부시 산단로76번길 116", "031-850-2500", 37.7450, 127.1060),
    ("롯데마트 동두천점", "경기도 동두천시 평화로2169번길 21", "031-830-2500", 37.8927, 127.0532),
    ("롯데마트 경기양평점", "경기도 양평군 양평읍 남북로 76", "031-8079-2500", 37.4919, 127.4921),
    ("토이저러스 이천점", "경기도 이천시 호법면 프리미엄아울렛로 177-74", "매장 안내 확인", 37.2427, 127.6124),
)

# Names are taken from the retailers' public store directories. A directory
# proves a branch exists, never that a specific trading card is stocked.
GYEONGGI_EMART_STORES = (
    "이마트 경기광주점", "이마트 과천점", "이마트 광교점", "이마트 광명소하점",
    "이마트 김포한강점", "이마트 남양주점", "이마트 다산점", "이마트 동백점",
    "이마트 별내점", "이마트 보라점", "이마트 부천점", "이마트 분당점",
    "이마트 산본점", "이마트 서수원점", "이마트 성남점", "이마트 수원점",
    "이마트 수지점", "이마트 안산고잔점", "이마트 안성점", "이마트 안양점",
    "이마트 양주점", "이마트 여주점", "이마트 오산점", "이마트 용인점",
    "이마트 의왕점", "이마트 의정부점", "이마트 이천점", "이마트 일산점",
    "이마트 중동점", "이마트 진접점", "이마트 파주운정점", "이마트 파주점",
    "이마트 평촌점", "이마트 평택점", "이마트 포천점", "이마트 풍산점",
    "이마트 하남점", "이마트 화성봉담점", "이마트 화정점", "이마트 흥덕점",
)
GYEONGGI_TRADERS_STORES = (
    "트레이더스 홀세일 클럽 고양점", "트레이더스 홀세일 클럽 구성점",
    "트레이더스 홀세일 클럽 군포점", "트레이더스 홀세일 클럽 김포점",
    "트레이더스 홀세일 클럽 동탄점", "트레이더스 홀세일 클럽 부천점",
    "트레이더스 홀세일 클럽 수원점", "트레이더스 홀세일 클럽 수원화서점",
    "트레이더스 홀세일 클럽 안산점", "트레이더스 홀세일 클럽 안성점",
    "트레이더스 홀세일 클럽 위례점", "트레이더스 홀세일 클럽 일산점",
    "트레이더스 홀세일 클럽 하남점",
)

# Only public HTTPS company pages are treated as official. Independent shops
# and chains whose current official page is uncertain are map discoveries only.
RETAIL_CHANNEL_DEFINITIONS = (
    ("CU 편의점", "convenience", "CU", "https://cu.bgfretail.com/"),
    ("GS25 편의점", "convenience", "GS25", "https://gs25.gsretail.com/"),
    ("세븐일레븐 편의점", "convenience", "세븐일레븐", "https://www.7-eleven.co.kr/"),
    ("이마트24 편의점", "convenience", "이마트24", "https://m.emart24.co.kr/store"),
    ("씨스페이스 편의점", "convenience", "씨스페이스", None),
    ("동네 개인 편의점", "convenience", "편의점", None),
    ("이마트 대형마트", "hypermarket", "이마트", "https://store.emart.com/branch/list.do"),
    ("이마트 트레이더스", "hypermarket", "트레이더스 홀세일 클럽", "https://store.emart.com/branch/list.do"),
    ("홈플러스 대형마트", "hypermarket", "홈플러스", "https://my.homeplus.co.kr/store"),
    ("롯데마트 대형마트", "hypermarket", "롯데마트", None),
    ("코스트코 창고형마트", "hypermarket", "코스트코", "https://www.costco.co.kr/store-finder"),
    ("농협 하나로마트", "hypermarket", "하나로마트", None),
    ("이마트 에브리데이", "hypermarket", "이마트 에브리데이", "https://store.emart.com/branch/list.do"),
    ("GS THE FRESH 슈퍼마켓", "hypermarket", "GS THE FRESH", None),
    ("동네 대형마트·슈퍼마켓", "hypermarket", "대형마트 슈퍼마켓", None),
    ("알파문구", "stationery", "알파문구", "https://www.alpha.co.kr/"),
    ("모닝글로리 문구점", "stationery", "모닝글로리 문구", None),
    ("오피스디포 문구점", "stationery", "오피스디포 문구", None),
    ("오피스넥스 문구점", "stationery", "오피스넥스 문구", None),
    ("학교 앞 문구점", "stationery", "학교 앞 문구점", None),
    ("동네 문구·팬시점", "stationery", "문구점 팬시점", None),
    ("무인 문구점", "stationery", "무인 문구점", None),
    ("아트박스 팬시점", "bookstore", "아트박스", "https://company.artbox.kr/"),
    ("교보문고·핫트랙스", "bookstore", "교보문고 핫트랙스", "https://store.kyobobook.co.kr/"),
    ("영풍문고·팬시매장", "bookstore", "영풍문고", None),
    ("동네 서점·캐릭터굿즈점", "bookstore", "서점 캐릭터 굿즈", None),
    ("토이킹덤 완구점", "toy", "토이킹덤", "https://store.emart.com/branch/list.do"),
    ("토이저러스 완구점", "toy", "토이저러스", None),
    ("완구할인점", "toy", "완구할인점", None),
    ("동네 장난감·완구점", "toy", "장난감 완구점", None),
    ("포켓몬 카드 전문점", "cardshop", "포켓몬 카드샵", "https://pokemoncard.co.kr/card/225"),
    ("원피스 카드 전문점", "cardshop", "원피스 카드샵", "https://www.onepiece-cardgame.kr/shoplist.do"),
    ("TCG 트레이딩카드 전문점", "cardshop", "TCG 카드샵 카드게임", None),
    ("보드게임·취미 전문점", "cardshop", "보드게임 카드게임 전문점", None),
    ("다이소 생활용품점", "discount", "다이소", "https://www.daisomall.co.kr/"),
    ("노브랜드 생활용품점", "discount", "노브랜드", "https://store.emart.com/branch/list.do"),
    ("캐릭터·랜덤카드 할인매장", "discount", "캐릭터 랜덤카드 할인매장", None),
)

VERIFIED_LOCATION_DETAILS = {
    "이마트 안산고잔점": {
        "address": "경기도 안산시 단원구 원포공원1로 46",
        "lat": 37.302925143491, "lon": 126.8132034864,
    },
    "트레이더스 홀세일 클럽 안산점": {
        "address": "경기도 안산시 단원구 중앙대로 397", "phone": "031-363-1234",
        "lat": 37.331021166203, "lon": 126.78449703496,
    },
    "알파문구 경기대점": {
        "address": "경기도 수원시 영통구 대학3로 7 2층 211호",
        "phone": "031-8007-3172", "lat": 37.2997691086, "lon": 127.04217618519,
    },
}
OFFICIAL_CHAIN_HOSTS = {
    "CU": {"cu.bgfretail.com"},
    "GS25": {"gs25.gsretail.com"},
    "세븐일레븐": {"www.7-eleven.co.kr"},
    "이마트24": {"m.emart24.co.kr"},
    "이마트": {"store.emart.com"},
    "트레이더스": {"store.emart.com"},
    "트레이더스 홀세일 클럽": {"store.emart.com"},
    "이마트 에브리데이": {"store.emart.com"},
    "홈플러스": {"my.homeplus.co.kr"},
    "코스트코": {"www.costco.co.kr"},
    "알파문구": {"www.alpha.co.kr", "alloffice.alphachain.co.kr"},
    "아트박스": {"company.artbox.kr"},
    "교보문고 핫트랙스": {"store.kyobobook.co.kr"},
    "토이킹덤": {"store.emart.com"},
    "포켓몬 카드샵": {"pokemoncard.co.kr"},
    "원피스 카드샵": {"www.onepiece-cardgame.kr"},
    "다이소": {"www.daisomall.co.kr"},
    "노브랜드": {"store.emart.com"},
}
EXPECTED_RETAIL_IDENTITIES = {
    **{f"{label} 주변 매장": (chain, category)
       for label, category, chain, _ in RETAIL_CHANNEL_DEFINITIONS},
    **{f"{label} 공식 매장 안내": (chain, category)
       for label, category, chain, official in RETAIL_CHANNEL_DEFINITIONS if official},
    **{name: ("이마트", "hypermarket") for name in GYEONGGI_EMART_STORES},
    **{name: ("트레이더스", "hypermarket") for name in GYEONGGI_TRADERS_STORES},
    "알파문구 경기대점": ("알파문구", "stationery"),
    "이마트몰 공식 카드·BOX 상품 검색": ("이마트", "hypermarket"),
}


def retailer_category(source: dict) -> str:
    """Classify existing stores without mistaking 이마트24 for a hypermarket."""
    existing = source.get("retailer_category")
    if existing:
        if not isinstance(existing, str) or existing not in RETAILER_CATEGORIES:
            raise ValueError("구매처 매장 분류 오류")
        return existing
    text = f"{source.get('name', '')} {source.get('chain', '')}".casefold()
    if any(word in text for word in ("이마트24", "gs25", "세븐일레븐", "편의점", "lawson", "familymart")) or text.startswith("cu "):
        return "convenience"
    if any(word in text for word in ("토이저러스", "토이킹덤", "완구", "장난감")):
        return "toy"
    if any(word in text for word in ("문구", "모닝글로리", "오피스디포", "오피스넥스")):
        return "stationery"
    if any(word in text for word in ("아트박스", "교보", "핫트랙스", "영풍", "서점")):
        return "bookstore"
    if any(word in text for word in ("카드샵", "카드 전문", "취급 점포", "공인 카드", "보드게임")):
        return "cardshop"
    if any(word in text for word in ("다이소", "노브랜드", "할인매장")):
        return "discount"
    if any(word in text for word in ("이마트", "트레이더스", "롯데마트", "홈플러스", "코스트코", "하나로마트", "슈퍼마켓", "walmart", "target")):
        return "hypermarket"
    return "general"


def _retail_row(name: str, category: str, chain: str, *, url: str | None = None,
                official_url: str | None = None, search: str | None = None,
                source_type: str = "map", details: dict | None = None) -> dict:
    row = {
        "name": name, "region": "KR", "games": ["Pokemon", "ONE PIECE", "NARUTO"],
        "type": source_type, "channel": "offline", "retailer_category": category,
        "chain": chain, "inventory_status": UNVERIFIED_INVENTORY,
        "inventory_checked_at": None, "inventory_verified": False,
        "note": "영업·카드 취급·재고는 점포별로 다르므로 공식 안내 또는 전화 확인",
        "data_basis": "공식 점포 안내 또는 지역 지도 검색 · 개별 카드 재고 미검증",
    }
    if url:
        row["url"] = url
    else:
        keywords = urllib.parse.quote(search or chain)
        row["url_template"] = f"https://map.naver.com/p/search/{keywords}%20{{query}}"
    if official_url:
        row["official_reference_url"] = official_url
    if details:
        row.update(details)
    return row


def ensure_diverse_retail_channels(sources: list) -> list:
    """Restore curated channels on every update; never synthesize stock claims."""
    merged = list(sources)
    known = {
        (row.get("name"), row.get("region"), row.get("channel", "online"))
        for row in merged if isinstance(row, dict)
    }

    def add(row: dict) -> None:
        key = (row["name"], row["region"], row.get("channel", "online"))
        if key not in known:
            merged.append(row)
            known.add(key)

    for label, category, chain, official in RETAIL_CHANNEL_DEFINITIONS:
        add(_retail_row(f"{label} 주변 매장", category, chain,
                        official_url=official, search=chain))
        if official:
            add(_retail_row(f"{label} 공식 매장 안내", category, chain,
                            url=official, official_url=official, source_type="official"))

    directory = "https://store.emart.com/branch/list.do"
    for name in (*GYEONGGI_EMART_STORES, *GYEONGGI_TRADERS_STORES):
        chain = "트레이더스" if name.startswith("트레이더스") else "이마트"
        details = VERIFIED_LOCATION_DETAILS.get(name)
        target = " ".join((name, details.get("address", ""))) if details else name
        add(_retail_row(name, "hypermarket", chain,
                        url=f"https://map.naver.com/p/search/{urllib.parse.quote(target)}",
                        official_url=directory, details=details))

    alpha_name = "알파문구 경기대점"
    alpha_details = VERIFIED_LOCATION_DETAILS[alpha_name]
    add(_retail_row(alpha_name, "stationery", "알파문구",
                    url=f"https://map.naver.com/p/search/{urllib.parse.quote(alpha_name + ' ' + alpha_details['address'])}",
                    official_url="https://alloffice.alphachain.co.kr/company/storeInfo.do",
                    details=alpha_details))
    add({
        "name": "이마트몰 공식 카드·BOX 상품 검색", "region": "KR",
        "games": ["Pokemon", "ONE PIECE", "NARUTO"], "type": "marketplace",
        "channel": "online", "retailer_category": "hypermarket", "chain": "이마트",
        "url_template": "https://emart.ssg.com/search.ssg?query={query}",
        "official_reference_url": "https://store.emart.com/branch/list.do",
        "note": "공식 이마트몰 검색 · 온라인 목록과 오프라인 지점 재고는 별개",
        "data_basis": "이마트 공식 온라인 검색과 공식 점포 안내",
    })
    return merged


def ensure_gyeonggi_lotte_stores(sources: list) -> list:
    merged = list(sources)
    known = {(row.get("name"), row.get("region")) for row in merged if isinstance(row, dict)}
    for name, address, phone, lat, lon in GYEONGGI_LOTTE_STORES:
        if (name, "KR") in known:
            continue
        query = urllib.parse.quote(f"{name} {address}")
        merged.append({
            "name": name,
            "region": "KR",
            "games": ["Pokemon", "ONE PIECE", "NARUTO"],
            "type": "map",
            "channel": "offline",
            "retailer_category": "toy" if "토이저러스" in name else "hypermarket",
            "chain": "토이저러스" if "토이저러스" in name else "롯데마트",
            "url": f"https://map.naver.com/p/search/{query}",
            "address": address,
            "phone": phone,
            "lat": lat,
            "lon": lon,
            "inventory_status": "TCG 재고 미확인 · 방문 전 전화/지도 확인",
            "inventory_checked_at": None,
            "note": "경기도 롯데마트·토이저러스 지점 · 포켓몬/원피스/나루토 카드 취급·재고는 점포별 확인",
            "data_basis": "공개 점포 주소·지도 좌표",
        })
        known.add((name, "KR"))
    return merged


def checked_url(value: str, template: bool = False) -> str:
    if not isinstance(value, str) or not value or len(value) > 2048:
        raise ValueError("구매처 주소 형식 오류")
    if template and value.count("{query}") != 1:
        raise ValueError("구매처 검색어 자리표시자 오류")
    if not template and "{query}" in value:
        raise ValueError("일반 구매처 주소에 검색어 자리표시자를 사용할 수 없습니다")
    probe = value.replace("{query}", "TCG")
    validate_public_https_url(probe)
    return CANONICAL_URLS.get(value, value)



def resolve_public_host(host: str) -> None:
    """Block DNS names that resolve to loopback/private/link-local/reserved addresses."""
    try:
        rows = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise urllib.error.URLError("도메인 확인 실패") from exc
    if not rows:
        raise urllib.error.URLError("도메인 확인 실패")
    usable = 0
    for row in rows:
        try:
            address = ipaddress.ip_address(row[4][0])
        except (IndexError, TypeError, ValueError):
            continue
        usable += 1
        if not address.is_global:
            raise ValueError("사설·로컬 IP로 연결되는 주소 차단")
    if usable == 0:
        raise urllib.error.URLError("사용할 수 있는 공개 DNS 주소 없음")


def normalize_source(source: dict) -> dict:
    if not isinstance(source, dict):
        raise ValueError("구매처 항목 형식 오류")
    clean = dict(source)
    if not isinstance(clean.get("name"), str) or not clean["name"].strip():
        raise ValueError("구매처 이름 누락")
    if clean.get("region") not in REGIONS or clean.get("type") not in TYPES:
        raise ValueError("구매처 국가 또는 유형 오류")
    games = clean.get("games")
    if not isinstance(games, list) or not games or not set(games).issubset(GAMES):
        raise ValueError("구매처 카드게임 분류 오류")
    if clean.get("channel", "online") not in {"online", "offline"}:
        raise ValueError("구매처 채널 오류")
    clean["retailer_category"] = retailer_category(clean)
    chain = clean.get("chain")
    if chain is not None and (not isinstance(chain, str) or not chain.strip()
                              or len(chain) > 80 or any(ord(char) < 32 for char in chain)):
        raise ValueError("구매처 매장 체인 이름 오류")
    identity = EXPECTED_RETAIL_IDENTITIES.get(clean["name"])
    if identity is not None and (chain, clean["retailer_category"]) != identity:
        raise ValueError("구매처 공식 체인 또는 매장 분류 불일치")
    if clean.get("official_reference_url"):
        clean["official_reference_url"] = checked_url(clean["official_reference_url"])
        approved_hosts = OFFICIAL_CHAIN_HOSTS.get(chain)
        host = urllib.parse.urlsplit(clean["official_reference_url"]).hostname
        if approved_hosts and host not in approved_hosts:
            raise ValueError("구매처 공식 매장 도메인 불일치")
    coordinates = [field in clean for field in ("lat", "lon")]
    if any(coordinates) and not all(coordinates):
        raise ValueError("구매처 좌표 일부 누락")
    if all(coordinates):
        lat, lon = clean["lat"], clean["lon"]
        if (isinstance(lat, bool) or isinstance(lon, bool)
                or not isinstance(lat, (int, float)) or not isinstance(lon, (int, float))
                or not math.isfinite(lat) or not math.isfinite(lon)
                or not -90 <= lat <= 90 or not -180 <= lon <= 180):
            raise ValueError("구매처 지도 좌표 범위 오류")
    if clean.get("channel", "online") == "offline":
        current_status = clean.get("inventory_status")
        if not isinstance(current_status, str) or "미확인" not in current_status:
            clean["inventory_status"] = UNVERIFIED_INVENTORY
        clean["inventory_checked_at"] = None
        clean["inventory_verified"] = False
    has_url = bool(clean.get("url"))
    has_template = bool(clean.get("url_template"))
    if has_url:
        clean["url"] = checked_url(clean["url"])
        approved_hosts = OFFICIAL_CHAIN_HOSTS.get(chain)
        if clean.get("type") == "official" and approved_hosts:
            if urllib.parse.urlsplit(clean["url"]).hostname not in approved_hosts:
                raise ValueError("구매처 공식 안내 링크 도메인 불일치")
    if has_template:
        clean["url_template"] = checked_url(clean["url_template"], template=True)
    if not has_url and not has_template:
        raise ValueError("구매처 연결 주소 누락")
    return clean


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        absolute = urllib.parse.urljoin(req.full_url, newurl)
        checked_url(absolute)
        require_public_https(absolute)  # Validate DNS/public IP before following.
        return super().redirect_request(req, fp, code, msg, headers, absolute)


def probe(source: dict) -> tuple[str, str]:
    value = source.get("url")
    if not value:
        return source["name"], "검색주소 형식 정상"
    host = urllib.parse.urlsplit(value).hostname
    if not host:
        return source['name'], '재확인 필요·기존 주소 유지 (HostError)'
    try:
        resolve_public_host(host)
    except urllib.error.URLError as exc:
        return source['name'], f'재확인 필요·기존 주소 유지 ({diagnostic_exception(exc)})'
    except ValueError as exc:
        return source['name'], f'보안 검증 실패·기존 주소 유지 ({diagnostic_exception(exc)})'
    opener = urllib.request.build_opener(SafeRedirect)
    headers = {"User-Agent": "Mozilla/5.0 TCG-Grader-Link-Checker/1.0"}
    try:
        request = urllib.request.Request(value, headers=headers, method="HEAD")
        try:
            response = opener.open(request, timeout=TIMEOUT_SECONDS)
        except urllib.error.HTTPError as exc:
            if exc.code not in {403, 405, 429}:
                raise
            return source["name"], f"접속 제한·기존 주소 유지 (HTTP {exc.code})"
        with response:
            checked_url(response.geturl())
            require_public_https(response.geturl())
            return source["name"], "정상"
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, socket.timeout) as exc:
        return source["name"], f"재확인 필요·기존 주소 유지 ({diagnostic_exception(exc)})"


def main() -> dict:
    current = json.loads(safe_read_text(DATA))
    original = current.get("sources")
    if not isinstance(original, list) or not original:
        raise ValueError("구매처 목록이 비어 있습니다")
    original = ensure_diverse_retail_channels(ensure_gyeonggi_lotte_stores(original))
    normalized = []
    seen = set()
    errors = []
    for source in original:
        try:
            clean = normalize_source(source)
            key = (clean["name"], clean["region"], clean.get("channel", "online"))
            if key in seen:
                errors.append(f"{clean['name']}: 중복 구매처 유지")
            else:
                seen.add(key)
                normalized.append(clean)
        except ValueError as exc:
            errors.append(f"{source.get('name', '이름 없음')}: {exc}")
            # A malformed record is never exposed as an executable link.
    if len(normalized) < max(1, len(original) // 2):
        raise ValueError("구매처 대량 감소 차단·기존 정상자료 유지")

    targets = [s for s in normalized if s.get("url") and s.get("type") == "official"][:MAX_ONLINE_CHECKS]
    statuses = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for name, state in pool.map(probe, targets):
            statuses[name] = state
            if state.startswith("재확인 필요"):
                errors.append(f"{name}: {state}")

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    for source in normalized:
        source["link_status"] = statuses.get(source["name"], "주소 형식 검증 완료")
        source["last_checked_at"] = now
    current["sources"] = normalized
    current["updated_at"] = now
    current["collection_status"] = "정상" if not errors else "일부 구매처 재확인 필요·기존 목록 유지"
    current["collection_errors"] = errors
    current["checked_source_count"] = len(normalized)
    current["online_checked_count"] = len(targets)
    current["retailer_category_counts"] = {
        category: sum(row.get("retailer_category") == category for row in normalized)
        for category in sorted(RETAILER_CATEGORIES)
    }
    current["inventory_policy"] = "개별 오프라인 점포 취급·재고는 검증하지 않았으며 방문 전 확인이 필요합니다."
    # v112: keep social stock discovery inside existing auto-update step 5.
    # It produces reference signals only and can never overwrite official inventory capabilities.
    try:
        import social_stock_discovery
        stock = social_stock_discovery.main()
        summary = stock.get("summary", {}) if isinstance(stock, dict) else {}
        current["social_stock_signal_count"] = int(summary.get("active_signals") or 0)
        current["social_stock_stale_count"] = int(summary.get("stale_signals") or 0)
        current["social_stock_updated_at"] = stock.get("updated_at") if isinstance(stock, dict) else None
        current["social_stock_collection_mode"] = "step5-public-search-reference-only"
    except Exception as exc:
        current["social_stock_collection_mode"] = f"degraded-{type(exc).__name__}"
        current.setdefault("collection_errors", []).append(f"SNS 재고제보 수집: {diagnostic_exception(exc)}")
    atomic_write_json(DATA,current)
    return current


if __name__ == "__main__":
    main()
