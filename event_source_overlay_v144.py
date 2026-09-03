#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Runtime source overlay for v144 missed-event recovery.

The base registry stays backward-compatible. This overlay adds verified publisher /
ONE PIECE official JP accounts and marks the existing Korean community watcher as
cross-region discovery-only. It changes discovery coverage only; it never makes the
community watcher trusted or verified.
"""
from __future__ import annotations

import json

import social_event_discovery

PATCH_ID = 144
_APPLIED = False
_ORIGINAL_LOAD_REGISTRY = None

OFFICIAL_ACCOUNT_OVERLAY = (
    {
        "platform": "x",
        "username": "Eiichiro_Staff",
        "game": "원피스 카드",
        "region": "JP",
        "profile_url": "https://x.com/Eiichiro_Staff",
        "trusted": True,
        "manual": True,
        "role": "onepiece_official_staff",
        "verified_via_official_site": "https://one-piece.com/index.html",
        "verification_note": "ONE PIECE.com이 공식 SNS로 직접 명시한 ONE PIECE 스태프 X · 원작/카드/콜라보 공지 교차검증용",
        "verified_at": "2026-09-03T19:21:00+09:00",
    },
    {
        "platform": "x",
        "username": "jump_henshubu",
        "game": "원피스 카드",
        "region": "JP",
        "profile_url": "https://x.com/jump_henshubu",
        "trusted": True,
        "manual": True,
        "role": "publisher_official",
        "verified_via_official_site": "https://www.shonenjump.com/j/",
        "verification_note": "집영사 주간소년점프 공식 사이트가 SNS로 직접 명시한 편집부 X · 부록/응모자 전원 서비스/카드 공지 교차검증용",
        "verified_at": "2026-09-03T19:21:00+09:00",
    },
)

WATCH_OVERRIDES = {
    ("onepiececard_news", "원피스 카드"): {
        "content_regions": ["KR", "JP", "US"],
        "search_languages": ["ko", "ja", "en"],
        "role": "community_watch_cross_region",
        "verification_note": (
            "한국어 커뮤니티 정보 발견용 교차지역 감시채널. 일본/미국 소식도 발견 후보로 사용할 수 있으나 "
            "trusted=false를 유지하고 공식 웹·공식 SNS 교차확인 전 확정정보 승격 금지."
        ),
    },
}


def merge_registry(registry: dict) -> dict:
    out = dict(registry) if isinstance(registry, dict) else {}
    accounts = [dict(x) for x in (out.get("accounts") or []) if isinstance(x, dict)]
    index = {
        (
            str(x.get("platform") or "").lower(),
            str(x.get("username") or "").lower().lstrip("@"),
            str(x.get("game") or ""),
            str(x.get("region") or ""),
        ): i
        for i, x in enumerate(accounts)
    }
    for row in OFFICIAL_ACCOUNT_OVERLAY:
        key = (
            str(row.get("platform") or "").lower(),
            str(row.get("username") or "").lower().lstrip("@"),
            str(row.get("game") or ""),
            str(row.get("region") or ""),
        )
        if key in index:
            merged = dict(accounts[index[key]])
            merged.update(row)
            accounts[index[key]] = merged
        else:
            index[key] = len(accounts)
            accounts.append(dict(row))
    out["accounts"] = accounts

    watches = [dict(x) for x in (out.get("watch_accounts") or []) if isinstance(x, dict)]
    for row in watches:
        key = (str(row.get("username") or "").lower().lstrip("@"), str(row.get("game") or ""))
        override = WATCH_OVERRIDES.get(key)
        if override:
            # Safety: overlay may broaden discovery scope but never trust the row.
            row.update(override)
            row["trusted"] = False
    out["watch_accounts"] = watches
    out["runtime_source_overlay"] = {
        "patch": PATCH_ID,
        "official_accounts_added": len(OFFICIAL_ACCOUNT_OVERLAY),
        "cross_region_watch_overrides": len(WATCH_OVERRIDES),
        "trust_auto_promotion": False,
    }
    return out


def _v144_load_registry() -> dict:
    return merge_registry(_ORIGINAL_LOAD_REGISTRY())


def apply() -> dict:
    global _APPLIED, _ORIGINAL_LOAD_REGISTRY
    if _APPLIED:
        return {"ok": True, "patch": PATCH_ID, "already_applied": True, "trust_auto_promotion": False}
    _ORIGINAL_LOAD_REGISTRY = social_event_discovery.load_registry
    social_event_discovery.load_registry = _v144_load_registry
    _APPLIED = True
    return {
        "ok": True,
        "patch": PATCH_ID,
        "official_accounts_added": len(OFFICIAL_ACCOUNT_OVERLAY),
        "cross_region_watch_overrides": len(WATCH_OVERRIDES),
        "trust_auto_promotion": False,
    }


if __name__ == "__main__":
    print(json.dumps(apply(), ensure_ascii=False))
