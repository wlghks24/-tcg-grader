#!/usr/bin/env python3
from instagram_tcg_content.source_route_resilience import (
    ProviderState,
    choose_routes,
    coverage_ok,
    next_strategy,
)


def main():
    states = [
        ProviderState("ebay", "completed_sale_original", "rate_limited", 1),
        ProviderState("goldin", "completed_sale_original", "ok", 0),
        ProviderState("heritage", "completed_sale_original", "ok", 0),
        ProviderState("pricecharting", "market_reference", "ok", 0),
    ]
    decision = choose_routes("completed_sale", states)
    assert decision.independent_target == 2
    assert "goldin" in decision.selected and "heritage" in decision.selected, decision
    assert coverage_ok(
        "completed_sale",
        [
            ProviderState("goldin", "completed_sale_original", "ok", 0),
            ProviderState("heritage", "completed_sale_original", "ok", 0),
        ],
    )
    assert not coverage_ok(
        "completed_sale",
        [
            ProviderState("pricecharting", "market_reference", "ok", 0),
            ProviderState("tcgplayer", "market_reference", "ok", 0),
        ],
    )
    assert not coverage_ok(
        "completed_sale",
        [ProviderState("goldin", "completed_sale_original", "ok", 0)],
    )

    assert (
        next_strategy("rate_limited", 1)
        == "respect_retry_after_then_alternate_provider"
    )
    assert (
        next_strategy("forbidden", 1)
        == "respect_retry_after_then_alternate_provider"
    )
    assert (
        next_strategy("parser_error", 1)
        == "alternate_parser_then_alternate_provider"
    )
    assert (
        next_strategy("stale", 1)
        == "alternate_provider_then_recheck_primary"
    )
    assert next_strategy("quarantined", 3) == "quarantine_and_exclude"

    official = choose_routes(
        "official_event",
        [
            ProviderState("homepage", "official_primary", "stale", 1),
            ProviderState("campaign-detail", "official_primary", "fresh", 0),
            ProviderState("news-index", "official_primary", "ok", 0),
        ],
    )
    assert official.selected[0] in {"campaign-detail", "news-index"}, official

    blocked = choose_routes(
        "completed_sale",
        [
            ProviderState("a", "completed_sale_original", "quarantined", 3),
            ProviderState("b", "completed_sale_original", "ok", 0),
        ],
    )
    assert "a" not in blocked.selected
    assert blocked.reason.startswith("insufficient qualifying independent routes"), blocked

    print("Instagram TCG route resilience regression: PASS")


if __name__ == "__main__":
    main()
