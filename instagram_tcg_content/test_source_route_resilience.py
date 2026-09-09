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
    assert "ebay" not in decision.selected, decision
    assert len(decision.selected) == 2, decision
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
    assert len(official.selected) == 1, official

    blocked = choose_routes(
        "completed_sale",
        [
            ProviderState("a", "completed_sale_original", "quarantined", 3),
            ProviderState("b", "completed_sale_original", "ok", 0),
        ],
    )
    assert "a" not in blocked.selected
    assert blocked.reason.startswith("insufficient qualifying independent routes"), blocked

    fixed_now = "2026-09-09T21:30:00+09:00"
    cooldown = choose_routes(
        "completed_sale",
        [
            ProviderState(
                "cooling",
                "completed_sale_original",
                "rate_limited",
                1,
                "2026-09-09T22:00:00+09:00",
            ),
            ProviderState("goldin", "completed_sale_original", "ok", 0),
            ProviderState("heritage", "completed_sale_original", "ok", 0),
        ],
        now_kst=fixed_now,
    )
    assert "cooling" not in cooldown.selected, cooldown
    assert set(cooldown.selected) == {"goldin", "heritage"}, cooldown

    expired = choose_routes(
        "completed_sale",
        [
            ProviderState(
                "retry-a",
                "completed_sale_original",
                "rate_limited",
                1,
                "2026-09-09T21:00:00+09:00",
            ),
            ProviderState(
                "retry-b",
                "completed_sale_original",
                "forbidden",
                1,
                "2026-09-09T21:05:00+09:00",
            ),
        ],
        now_kst=fixed_now,
    )
    assert set(expired.selected) == {"retry-a", "retry-b"}, expired
    assert "fallback route" in expired.reason, expired

    for bad_max_routes in (0, True, 9):
        try:
            choose_routes("completed_sale", states, max_routes=bad_max_routes)
            raise AssertionError("invalid max_routes failed open")
        except ValueError as exc:
            assert str(exc) == "MAX_ROUTES_OUT_OF_RANGE", exc

    bad_cases = (
        [ProviderState("dup", "completed_sale_original"), ProviderState("dup", "completed_sale_original")],
        [ProviderState("x", "unknown_tier")],
        [ProviderState("x", "completed_sale_original", "mystery")],
        [ProviderState("x", "completed_sale_original", "ok", -1)],
        [ProviderState("x", "completed_sale_original", "ok", 0, "2026-09-09T22:00:00")],
    )
    expected = (
        "DUPLICATE_PROVIDER_STATE",
        "UNKNOWN_PROVIDER_TIER",
        "UNKNOWN_PROVIDER_STATUS",
        "INVALID_FAILURE_COUNT",
        "cooldown_until_kst must be timezone-aware",
    )
    for rows, expected_error in zip(bad_cases, expected):
        try:
            choose_routes("completed_sale", rows, now_kst=fixed_now)
            raise AssertionError(f"{expected_error} failed open")
        except ValueError as exc:
            assert str(exc) == expected_error, (expected_error, exc)

    # A provider cooldown blocks contacting it again, but does not invalidate an
    # already captured healthy evidence item when coverage is evaluated.
    assert coverage_ok(
        "completed_sale",
        [
            ProviderState("a", "completed_sale_original", "ok", 0, "2026-09-09T22:00:00+09:00"),
            ProviderState("b", "completed_sale_original", "fresh", 0),
        ],
    )

    print("Instagram TCG route resilience regression: PASS")


if __name__ == "__main__":
    main()
