#!/usr/bin/env python3
"""Canonical mandatory TCG collection job contract.

This module is intentionally lightweight and side-effect free. Runtime status,
the collection executor, tablet bundle validation, and CI all import the same
immutable job tuple so progress totals cannot drift from the work actually run.
"""
from __future__ import annotations

COLLECTION_JOBS = (
    ("출시일", "update_releases", "releases.json"),
    ("판매·재발매 추적", "update_market_watch", "market_watch.json"),
    ("현재 거래시세", "update_market_prices", "market_prices.json"),
    ("프로모·콜라보 행사", "update_promo_events", "promo_events.json"),
    ("구매처·링크 보안 확인", "update_purchase_sources", "purchase_sources.json"),
    ("원화 환산 환율", "update_exchange_rates", "exchange_rates.json"),
    ("등급업체 요금·서비스·이벤트", "grading_company_watch", "grading_company_updates.json"),
    ("업체별 등급카드 사진 후보", "graded_photo_multi_source", "graded_photo_candidates.json"),
)

JOB_COUNT = len(COLLECTION_JOBS)
MANDATORY_OUTPUTS = tuple(row[2] for row in COLLECTION_JOBS)


def validate_contract() -> None:
    if JOB_COUNT != 8:
        raise RuntimeError(f"mandatory collection contract must contain 8 jobs, got {JOB_COUNT}")
    if len(set(MANDATORY_OUTPUTS)) != JOB_COUNT:
        raise RuntimeError("mandatory collection outputs must be unique")
    modules = tuple(row[1] for row in COLLECTION_JOBS)
    if len(set(modules)) != JOB_COUNT:
        raise RuntimeError("mandatory collection modules must be unique")
    if any(not label or not module or not output for label, module, output in COLLECTION_JOBS):
        raise RuntimeError("mandatory collection job entries must be complete")


validate_contract()
