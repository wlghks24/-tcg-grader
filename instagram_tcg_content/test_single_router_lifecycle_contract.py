#!/usr/bin/env python3
from datetime import datetime, timezone

from instagram_tcg_content.canonical_taxonomy import lifecycle_bucket
from instagram_tcg_content.collection_health import (
    EXPECTED_OUTPUTS,
    MIN_COMPLETED_SALES_PER_OUTPUT,
    VERIFICATION_ENGINE,
    VERIFICATION_MODE,
    audit_collection,
)
from instagram_tcg_content.collection_normalizer import normalize_collector_record
from instagram_tcg_content.persisted_crosscheck_export import build_snapshot
from instagram_tcg_content.cardinfo_quality_learning_current import binding_status
from instagram_tcg_content.source_verification_engine import CORE_FACTS


def routes():
    return {"provider_groups": {game: {
        "official_primary": ["official"],
        "completed_sale_original": ["sale-a", "sale-b"],
        "grading_auction_original": [],
        "market_reference": ["market-a", "market-b"],
    } for game in ("pokemon", "one_piece", "naruto")}}


def verified_row(game, language, family, lineage, **extra):
    return {
        "canonical_key": f"{game}|{family}|{language.lower()}|{lineage}",
        "information_family": family,
        "value": "verified",
        "identity": {"game": game, "language": language},
        "language": language,
        "source_code": "official" if "completed" not in family else "sale-a",
        "source_locator": "https://example.invalid/item",
        "checked_at_kst": "2026-09-11T08:00:00+09:00",
        "verification": "verified",
        "verification_mode": VERIFICATION_MODE,
        "verification_engine": VERIFICATION_ENGINE,
        "lineage_key": lineage,
        **extra,
    }


def test_end_plus_five_then_archive():
    assert lifecycle_bucket(end_date="2026-09-05", as_of="2026-09-10") == "CURRENT"
    assert lifecycle_bucket(end_date="2026-09-05", as_of="2026-09-11") == "ARCHIVE"


def test_festival_and_news_are_normalized_before_verification():
    festival = normalize_collector_record({"information_family": "official_festival"})
    assert festival["content_type"] == "festival"
    assert festival["fact_type"] == "official_event"
    assert festival["fact_type"] in CORE_FACTS
    news = normalize_collector_record({"fact_type": "official_product_news"})
    assert news["content_type"] == "product_news"
    assert news["fact_type"] == "official_release"
    assert news["fact_type"] in CORE_FACTS


def test_snapshot_persists_content_subtype_and_lifecycle():
    row = verified_row("pokemon", "KR", "official_festival", "festival-1", end_date="2026-09-05")
    snapshot = build_snapshot([row], now=datetime(2026, 9, 11, 3, 0, tzinfo=timezone.utc))
    fact = snapshot["facts"][0]
    assert fact["fact_type"] == "event"
    assert fact["content_type"] == "festival"
    assert fact["lifecycle_bucket"] == "ARCHIVE"


def test_open_ended_period_content_stays_current_until_end_is_verified():
    row = verified_row(
        "pokemon", "KR", "official_festival", "festival-open",
        start_date="2026-09-01",
    )
    snapshot = build_snapshot([row], now=datetime(2026, 10, 1, 3, 0, tzinfo=timezone.utc))
    fact = snapshot["facts"][0]
    assert fact["content_type"] == "festival"
    assert fact["lifecycle_bucket"] == "CURRENT"
    assert "end_date" not in fact


def test_sales_only_never_satisfies_general_cardinfo_matrix():
    sales = []
    for game, language in EXPECTED_OUTPUTS:
        for index in range(MIN_COMPLETED_SALES_PER_OUTPUT):
            row = verified_row(game, language, "completed_sale", f"sale-{game}-{language}-{index}")
            row["fact_type"] = "completed_sale"
            row.pop("information_family", None)
            sales.append(row)
    snapshot = build_snapshot(sales, now=datetime(2026, 9, 11, 0, 0, tzinfo=timezone.utc))
    report = audit_collection(snapshot, routes(), now=datetime(2026, 9, 11, 0, 5, tzinfo=timezone.utc))
    assert report["general_cardinfo_ready"] is False
    assert report["market_price_ready"] is True
    assert all(value == 0 for value in report["matrix_counts"].values())


def test_archived_general_facts_do_not_satisfy_current_matrix():
    rows = [
        verified_row(game, language, "official_release", f"release-{game}-{language}", release_date="2026-09-01")
        for game, language in EXPECTED_OUTPUTS
    ]
    snapshot = build_snapshot(rows, now=datetime(2026, 9, 11, 0, 0, tzinfo=timezone.utc))
    report = audit_collection(snapshot, routes(), now=datetime(2026, 9, 11, 0, 5, tzinfo=timezone.utc))
    assert report["general_cardinfo_ready"] is False
    assert report["archived_general_fact_count"] == 6


def test_quality_adapter_uses_current_canonical_binding_without_fact_authority():
    status = binding_status()
    assert status["binding_ok"] is True
    assert status["factual_authority"] is False
    assert status["production_authority"] is False


if __name__ == "__main__":
    test_end_plus_five_then_archive()
    test_festival_and_news_are_normalized_before_verification()
    test_snapshot_persists_content_subtype_and_lifecycle()
    test_open_ended_period_content_stays_current_until_end_is_verified()
    test_sales_only_never_satisfies_general_cardinfo_matrix()
    test_archived_general_facts_do_not_satisfy_current_matrix()
    test_quality_adapter_uses_current_canonical_binding_without_fact_authority()
    print("single-router lifecycle contract: PASS")
