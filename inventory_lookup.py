#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Official inventory / product availability lookup registry.

Rules
- Prefer the retailer's own public inventory/product lookup surface.
- Never fabricate stock quantities.
- When a retailer only provides store/customer-center confirmation, expose that
  path honestly instead of calling it realtime inventory.
"""
from __future__ import annotations
from datetime import datetime, timezone

OFFICIAL_LOOKUPS = [
    {
        "id": "cu-pocketcu",
        "retailer": "CU",
        "region": "KR",
        "mode": "official_app",
        "capability": "realtime_stock",
        "realtime": True,
        "label": "포켓CU 재고조회",
        "action_label": "실시간 재고조회",
        "url": "https://cu.bgfretail.com/membership/app_info.do?category=membership_info&depth2=4",
        "instructions": "포켓CU 앱의 재고조회에서 상품명을 검색하면 주변 점포별 구매 가능 수량을 확인할 수 있습니다.",
        "verification": "official",
    },
    {
        "id": "gs25-ourgs",
        "retailer": "GS25",
        "region": "KR",
        "mode": "official_app",
        "capability": "realtime_stock",
        "realtime": True,
        "label": "우리동네GS 재고찾기",
        "action_label": "실시간 재고조회",
        "url": "https://gs25.gsretail.com/gscvs/ko/store-services/woodongs",
        "instructions": "우리동네GS 앱의 재고찾기에서 원하는 상품을 검색하면 매장별 재고 수량을 확인할 수 있습니다.",
        "verification": "official",
    },
    {
        "id": "emart24-web",
        "retailer": "이마트24",
        "region": "KR",
        "mode": "official_web",
        "capability": "realtime_stock",
        "realtime": True,
        "label": "이마트24 내 주변매장 재고확인",
        "action_label": "실시간 재고조회",
        "url": "https://everse.emart24.co.kr/monthGds",
        "instructions": "공식 웹 재고확인 화면에서 상품명을 입력해 주변매장 재고를 조회할 수 있습니다.",
        "verification": "official",
    },
    {
        "id": "emart-app",
        "retailer": "이마트",
        "region": "KR",
        "mode": "official_app",
        "capability": "realtime_stock",
        "realtime": True,
        "label": "이마트 앱 점포별 실시간 재고",
        "action_label": "실시간 재고조회",
        "url": "https://store.emart.com/guide/mobile.do",
        "instructions": "이마트 공식 앱에서 상품을 검색하면 상품 정보·가격과 점포별 실시간 재고를 확인할 수 있습니다.",
        "verification": "official",
    },
    {
        "id": "lottemart-dowa",
        "retailer": "롯데마트",
        "region": "KR",
        "mode": "official_web",
        "capability": "store_stock_lookup",
        "realtime": False,
        "label": "롯데마트 모바일 도와센터 상품 확인",
        "action_label": "점포 상품·재고 확인",
        "url": "https://company.lottemart.com/mobiledowa/",
        "instructions": "롯데마트 공식 모바일 도와센터의 상품 확인에서 지역·점포를 선택하고 상품명을 검색해 재고/상품 정보를 확인할 수 있습니다.",
        "verification": "official",
    },
    {
        "id": "traders-official",
        "retailer": "트레이더스",
        "region": "KR",
        "mode": "official_guided",
        "capability": "guided_stock_check",
        "realtime": False,
        "label": "트레이더스 공식 점포·상담 확인",
        "action_label": "점포 재고 확인 경로",
        "url": "https://www.traders.co.kr/",
        "instructions": "트레이더스 공식 사이트에서 점포를 선택해 점포 정보/문의 경로를 이용합니다. 점포별 상품 재고는 공식 안내·디지털상담에서 최종 확인하세요.",
        "verification": "official",
    },
    {
        "id": "homeplus-online",
        "retailer": "홈플러스",
        "region": "KR",
        "mode": "official_web",
        "capability": "online_store_availability",
        "realtime": False,
        "label": "홈플러스 점포별 온라인 취급·재고 확인",
        "action_label": "온라인 취급·재고 확인",
        "url": "https://mfront.homeplus.co.kr/",
        "instructions": "홈플러스 공식 온라인몰은 선택 점포/배송권역에 따라 취급 상품과 재고가 달라집니다. 상품 검색 후 현재 선택 점포 기준 구매 가능 여부를 확인하세요.",
        "verification": "official",
    },
    {
        "id": "costco-contact",
        "retailer": "코스트코",
        "region": "KR",
        "mode": "official_contact",
        "capability": "phone_confirmation",
        "realtime": False,
        "label": "코스트코 매장 재고 고객센터 확인",
        "action_label": "매장 재고 문의",
        "url": "https://www.costco.co.kr/contactUs",
        "instructions": "코스트코 공식 FAQ는 온라인 상품이 매장에 있는지 확인하려면 매장 고객센터(1899-9900)로 문의하도록 안내합니다.",
        "verification": "official",
    },
]

UNSUPPORTED = {
    "세븐일레븐": "공식 공개 점포 재고조회 경로를 현재 검증하지 못해 매장/앱 안내 수준으로 유지합니다.",
    "코스트코 직접조회": "공개 점포 재고검색 페이지는 없으며 공식 고객센터 문의 방식입니다.",
}


def get_inventory_options(query: str = "", game: str = "") -> dict:
    query = (query or "").strip()[:120]
    game = (game or "").strip()[:40]
    items = [dict(x) for x in OFFICIAL_LOOKUPS]
    return {
        "ok": True,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "query": query,
        "game": game,
        "items": items,
        "realtime_count": sum(1 for x in items if x.get("realtime") is True),
        "official_lookup_count": len(items),
        "unsupported": dict(UNSUPPORTED),
        "notice": "업체별 기능 수준을 그대로 표시합니다. '실시간 재고조회'가 아닌 항목은 점포 상품확인·온라인 취급확인·고객센터 확인이며 재고 수량을 임의 생성하지 않습니다.",
    }
