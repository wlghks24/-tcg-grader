#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Official inventory lookup launcher/registry.

Only marks a retailer as real inventory lookup when the retailer itself publicly
provides that function. It never fabricates store stock and never calls private
or reverse-engineered APIs.
"""
from __future__ import annotations
from datetime import datetime, timezone

OFFICIAL_LOOKUPS = [
    {
        "id": "cu-pocketcu",
        "retailer": "CU",
        "region": "KR",
        "mode": "official_app",
        "realtime": True,
        "label": "포켓CU 재고조회",
        "url": "https://cu.bgfretail.com/membership/app_info.do?category=membership_info&depth2=4",
        "instructions": "포켓CU 앱의 재고조회에서 상품명을 검색하면 주변 점포별 구매 가능 수량을 확인할 수 있습니다.",
        "verification": "official",
    },
    {
        "id": "gs25-ourgs",
        "retailer": "GS25",
        "region": "KR",
        "mode": "official_app",
        "realtime": True,
        "label": "우리동네GS 재고찾기",
        "url": "https://gs25.gsretail.com/gscvs/ko/store-services/woodongs",
        "instructions": "우리동네GS 앱의 재고찾기에서 원하는 상품을 검색하면 매장별 재고 수량을 확인할 수 있습니다.",
        "verification": "official",
    },
    {
        "id": "emart24-web",
        "retailer": "이마트24",
        "region": "KR",
        "mode": "official_web",
        "realtime": True,
        "label": "이마트24 내 주변매장 재고확인",
        "url": "https://everse.emart24.co.kr/monthGds",
        "instructions": "공식 웹 재고확인 화면에서 상품명을 입력해 주변매장 재고를 조회할 수 있습니다.",
        "verification": "official",
    },
]

UNSUPPORTED = {
    "세븐일레븐": "현재 공개 웹 재고조회 경로를 검증하지 못해 매장/전화 확인만 표시합니다.",
    "이마트": "상품 상세/배송 재고는 확인 가능하지만 TCG 점포 재고를 직접 검색하는 공개 통합 조회 경로는 검증되지 않았습니다.",
    "트레이더스": "공개 통합 점포 재고조회 경로를 검증하지 못했습니다.",
    "홈플러스": "공개 통합 점포 재고조회 경로를 검증하지 못했습니다.",
    "코스트코": "공개 통합 점포 재고조회 경로를 검증하지 못했습니다.",
}


def get_inventory_options(query: str = "", game: str = "") -> dict:
    query = (query or "").strip()[:120]
    game = (game or "").strip()[:40]
    return {
        "ok": True,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "query": query,
        "game": game,
        "items": [dict(x) for x in OFFICIAL_LOOKUPS],
        "unsupported": dict(UNSUPPORTED),
        "notice": "실제 재고 수량은 각 업체의 공식 재고조회 화면에서 확인합니다. 공개/공식 재고조회가 없는 업체는 재고 있음으로 표시하지 않습니다.",
    }
