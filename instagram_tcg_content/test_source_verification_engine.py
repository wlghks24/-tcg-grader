#!/usr/bin/env python3
from instagram_tcg_content.source_verification_engine import (
    Observation,
    strategy_for_retry,
    verify_fact,
    x10_fact_gate,
)


def obs(
    provider,
    tier,
    value="100",
    fact="completed_sale",
    code="P-S01",
    *,
    key="pokemon:test:psa10",
    game="pokemon",
    status="observed",
    event_time=None,
    locator=None,
    lineage_key=None,
):
    return Observation(
        game=game,
        fact_type=fact,
        canonical_key=key,
        value=value,
        source_code=code,
        source_name=provider,
        source_locator=locator or ("https://example.invalid/" + provider),
        source_tier=tier,
        collector_id="collector:" + provider,
        provider_id=provider,
        fetched_at_kst="2026-09-04T22:00:00+09:00",
        event_or_trade_time=event_time,
        status=status,
        lineage_key=lineage_key,
    )


def main():
    # One realized-sale source is insufficient.
    r = verify_fact([obs("ebay", "completed_sale_original")])
    assert r.status == "partial", r

    # Two independent realized-sale sources verify; newest sale is display value.
    r = verify_fact(
        [
            obs(
                "ebay",
                "completed_sale_original",
                "100",
                event_time="2026-09-03T20:00:00+09:00",
            ),
            obs(
                "goldin",
                "completed_sale_original",
                "110",
                event_time="2026-09-04T09:00:00+09:00",
                code="P-S02",
            ),
        ]
    )
    assert r.status == "verified", r
    assert r.independent_source_count == 2, r
    assert r.canonical_value == "110", r

    # A realized auction/grade registry is transaction evidence, not a market reference.
    r = verify_fact(
        [
            obs("ebay", "completed_sale_original", "100", code="P-S01"),
            obs("psa-apr", "grading_auction_original", "105", code="P-S02"),
        ]
    )
    assert r.status == "verified", r

    # Same underlying sale lineage must never be double-counted across providers.
    same_lineage = "sale:ebay:123"
    r = verify_fact(
        [
            obs(
                "ebay",
                "completed_sale_original",
                "100",
                code="P-S01",
                lineage_key=same_lineage,
            ),
            obs(
                "psa-apr",
                "grading_auction_original",
                "100",
                code="P-S02",
                lineage_key=same_lineage,
            ),
        ]
    )
    assert r.status == "partial", r
    assert r.independent_source_count == 1, r

    # Market-reference data cannot independently promote a completed sale.
    r = verify_fact(
        [
            obs("ebay", "completed_sale_original", "100", code="P-S01"),
            obs("pricecharting", "market_reference", "100", code="P-S02"),
        ]
    )
    assert r.status == "partial", r

    # Cancelled/refunded/relisted evidence is excluded.
    r = verify_fact(
        [
            obs(
                "ebay",
                "completed_sale_original",
                "100",
                code="P-S01",
                status="cancelled",
            ),
            obs(
                "goldin",
                "completed_sale_original",
                "110",
                code="P-S02",
                status="completed",
            ),
        ]
    )
    assert r.status == "partial", r
    assert r.independent_source_count == 1, r

    # Different identities must never cross-verify.
    r = verify_fact(
        [
            obs("ebay", "completed_sale_original", key="pokemon:a"),
            obs(
                "goldin",
                "completed_sale_original",
                key="pokemon:b",
                code="P-S02",
            ),
        ]
    )
    assert r.status == "conflict", r

    # Unknown tiers/provenance fail closed.
    r = verify_fact([obs("mystery", "unknown_tier")])
    assert r.status == "unverified", r

    # Official facts require an official primary source.
    r = verify_fact(
        [obs("news", "official_secondary", "2026-09-16", "official_release")]
    )
    assert r.status == "partial", r
    r = verify_fact(
        [
            obs(
                "pokemon-official",
                "official_primary",
                "2026-09-16",
                "official_release",
            )
        ]
    )
    assert r.status == "verified", r

    # Official-source disagreement fails closed.
    r = verify_fact(
        [
            obs(
                "official-a",
                "official_primary",
                "2026-09-16",
                "official_release",
            ),
            obs(
                "official-b",
                "official_secondary",
                "2026-09-17",
                "official_release",
                code="P-S02",
            ),
        ]
    )
    assert r.status == "conflict", r

    # Market reference needs two independent agreeing providers.
    r = verify_fact(
        [obs("pricecharting", "market_reference", "200", "market_reference")]
    )
    assert r.status == "probable", r
    r = verify_fact(
        [
            obs("pricecharting", "market_reference", "200", "market_reference"),
            obs(
                "tcgplayer",
                "market_reference",
                "200",
                "market_reference",
                code="P-S02",
            ),
        ]
    )
    assert r.status == "verified", r

    # Retry strategy changes and eventually quarantines.
    assert strategy_for_retry(0) == "same_source_backoff"
    assert strategy_for_retry(1) == "alternate_source"
    assert strategy_for_retry(2) == "alternate_parser_and_source"
    assert strategy_for_retry(3) == "quarantine_and_exclude"

    good = verify_fact(
        [
            obs("ebay", "completed_sale_original"),
            obs("goldin", "completed_sale_original", code="P-S02"),
        ]
    )
    ok, reasons = x10_fact_gate([good])
    assert ok and not reasons, reasons

    bad = verify_fact([obs("ebay", "completed_sale_original")])
    ok, reasons = x10_fact_gate([bad])
    assert not ok and reasons

    print("Instagram TCG source verification regression: PASS")


if __name__ == "__main__":
    main()
