#!/usr/bin/env python3
from datetime import datetime, timezone

from instagram_tcg_content.source_verification_engine import (
    Observation,
    build_production_verification_receipt,
    strategy_for_retry,
    validate_production_verification_receipt,
    verify_fact as _verify_fact,
    x10_fact_gate,
)

FIXED_NOW = datetime(2026, 9, 4, 14, 0, tzinfo=timezone.utc)
SNAPSHOT_FINGERPRINT = "c" * 64


def verify_fact(rows):
    return _verify_fact(rows, now=FIXED_NOW)


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
    lineage_key="auto",
    currency="USD",
    condition="graded",
    grade="PSA 10",
    finality="final",
    price_basis="realized",
    quantity=1,
    unit="card",
):
    if fact == "completed_sale":
        if status == "observed":
            status = "completed"
        if event_time is None:
            event_time = "2026-09-04T21:30:00+09:00"
    resolved_lineage = lineage_key
    if lineage_key == "auto":
        resolved_lineage = f"sale:{provider}" if fact == "completed_sale" else None
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
        original_currency=currency if fact == "completed_sale" else None,
        condition=condition if fact == "completed_sale" else None,
        grade=grade if fact == "completed_sale" else None,
        finality=finality if fact == "completed_sale" else None,
        price_basis=price_basis if fact == "completed_sale" else None,
        quantity=quantity if fact == "completed_sale" else None,
        unit=unit if fact == "completed_sale" else None,
        lineage_key=resolved_lineage,
    )


def main():
    # Production fact gate must fail closed on no evidence or reference-only evidence.
    ok, reasons = x10_fact_gate([])
    assert not ok and reasons == ["NO_VERIFICATION_RESULTS"], reasons

    reference_only = verify_fact(
        [obs("pricecharting", "market_reference", "200", "market_reference")]
    )
    ok, reasons = x10_fact_gate([reference_only])
    assert not ok and "NO_CORE_FACTS" in reasons, reasons

    # Stale source capture and completed-sale evidence older than 30 days are rejected.
    stale_capture = _verify_fact(
        [obs("pokemon-official", "official_primary", "2026-09-16", "official_release")],
        now=datetime(2026, 9, 7, 0, 0, tzinfo=timezone.utc),
    )
    assert stale_capture.status == "unverified", stale_capture
    assert stale_capture.uncertainty_reason == "stale source capture", stale_capture

    old_sale = _verify_fact(
        [
            obs(
                "ebay",
                "completed_sale_original",
                "100",
                event_time="2026-07-01T20:00:00+09:00",
            ),
            obs(
                "goldin",
                "completed_sale_original",
                "110",
                event_time="2026-07-02T20:00:00+09:00",
                code="P-S02",
            ),
        ],
        now=FIXED_NOW,
    )
    assert old_sale.status == "unverified", old_sale
    assert "older than 30 days" in (old_sale.uncertainty_reason or ""), old_sale

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

    # Contradictory facts on one explicit lineage are a conflict, never a silent duplicate.
    r = verify_fact(
        [
            obs("ebay", "completed_sale_original", "100", code="P-S01", lineage_key=same_lineage),
            obs("psa-apr", "grading_auction_original", "110", code="P-S02", lineage_key=same_lineage),
        ]
    )
    assert r.status == "conflict", r
    assert "lineage disagrees" in (r.uncertainty_reason or ""), r

    # Numeric formatting differences for the same sale remain one deduped transaction.
    r = verify_fact(
        [
            obs("ebay", "completed_sale_original", "100", code="P-S01", lineage_key="sale:format:1"),
            obs("psa-apr", "grading_auction_original", "100.00", code="P-S02", lineage_key="sale:format:1"),
        ]
    )
    assert r.status == "partial", r
    assert r.independent_source_count == 1, r

    # Completed-sale evidence with missing hard-gate fields must fail closed.
    r = verify_fact(
        [
            obs(
                "ebay",
                "completed_sale_original",
                "100",
                code="P-S01",
                currency=None,
            ),
            obs(
                "goldin",
                "completed_sale_original",
                "110",
                code="P-S02",
            ),
        ]
    )
    assert r.status == "partial", r
    assert r.independent_source_count == 1, r
    assert "currency invalid" in (r.uncertainty_reason or ""), r

    # Transaction evidence must carry explicit lineage; synthetic lineage is not accepted.
    r = verify_fact(
        [
            obs(
                "ebay",
                "completed_sale_original",
                "100",
                code="P-S01",
                lineage_key=None,
            ),
            obs(
                "goldin",
                "completed_sale_original",
                "110",
                code="P-S02",
            ),
        ]
    )
    assert r.status == "partial", r
    assert r.independent_source_count == 1, r
    assert "explicit lineage missing" in (r.uncertainty_reason or ""), r

    # Currency, realized amount, and grade must be semantically valid.
    r = verify_fact(
        [
            obs("ebay", "completed_sale_original", "100", currency="usd"),
            obs("goldin", "completed_sale_original", "110", code="P-S02"),
        ]
    )
    assert r.status == "partial", r
    assert "currency invalid" in (r.uncertainty_reason or ""), r

    r = verify_fact(
        [
            obs("ebay", "completed_sale_original", "0"),
            obs("goldin", "completed_sale_original", "110", code="P-S02"),
        ]
    )
    assert r.status == "partial", r
    assert "realized amount invalid" in (r.uncertainty_reason or ""), r

    r = verify_fact(
        [
            obs("ebay", "completed_sale_original", "NaN"),
            obs("goldin", "completed_sale_original", "110", code="P-S02"),
        ]
    )
    assert r.status == "partial", r
    assert "realized amount invalid" in (r.uncertainty_reason or ""), r

    r = verify_fact(
        [
            obs("ebay", "completed_sale_original", "100", grade=None),
            obs("goldin", "completed_sale_original", "110", code="P-S02"),
        ]
    )
    assert r.status == "partial", r
    assert "grade missing" in (r.uncertainty_reason or ""), r

    # Incompatible transaction bases cannot cross-verify merely because two providers exist.
    r = verify_fact(
        [
            obs("ebay", "completed_sale_original", "100", code="P-S01", price_basis="realized"),
            obs("goldin", "completed_sale_original", "110", code="P-S02", price_basis="hammer"),
        ]
    )
    assert r.status == "partial", r
    assert "basis mismatch" in (r.uncertainty_reason or ""), r

    r = verify_fact(
        [
            obs("ebay", "completed_sale_original", "100", code="P-S01", currency="USD"),
            obs("goldin", "completed_sale_original", "110", code="P-S02", currency="JPY"),
        ]
    )
    assert r.status == "partial", r
    assert "basis mismatch" in (r.uncertainty_reason or ""), r

    r = verify_fact(
        [
            obs("ebay", "completed_sale_original", "100", code="P-S01", finality="pending"),
            obs("goldin", "completed_sale_original", "110", code="P-S02"),
        ]
    )
    assert r.status == "partial", r
    assert "finality invalid" in (r.uncertainty_reason or ""), r

    # Equivalent condition/finality synonyms for one lineage still dedupe once.
    r = verify_fact(
        [
            obs("ebay", "completed_sale_original", "100", code="P-S01", lineage_key="sale:synonym:1", condition="graded", finality="final"),
            obs("psa-apr", "grading_auction_original", "100.00", code="P-S02", lineage_key="sale:synonym:1", condition="slabbed", finality="settled"),
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

    # Reused lineage cannot hide a canonical-identity conflict.
    r = verify_fact(
        [
            obs("ebay", "completed_sale_original", key="pokemon:a", lineage_key="sale:shared:1"),
            obs("goldin", "completed_sale_original", key="pokemon:b", code="P-S02", lineage_key="sale:shared:1"),
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

    good_observations = [
        obs("ebay", "completed_sale_original"),
        obs("goldin", "completed_sale_original", code="P-S02"),
    ]
    good = verify_fact(good_observations)
    ok, reasons = x10_fact_gate([good])
    assert ok and not reasons, reasons

    bad_observations = [obs("ebay", "completed_sale_original")]
    bad = verify_fact(bad_observations)
    ok, reasons = x10_fact_gate([bad])
    assert not ok and reasons

    receipt = build_production_verification_receipt(
        [good_observations],
        snapshot_id="snapshot-verified-1",
        snapshot_fingerprint=SNAPSHOT_FINGERPRINT,
        required_core_keys=[(good.canonical_key, good.fact_type)],
        now=FIXED_NOW,
    )
    assert receipt["status"] == "pass", receipt
    assert receipt["verification_mode"] == "INSTAGRAM_LOCAL_EVIDENCE_ONLY", receipt
    assert (
        validate_production_verification_receipt(
            receipt,
            expected_snapshot_id="snapshot-verified-1",
            expected_snapshot_fingerprint=SNAPSHOT_FINGERPRINT,
        )
        == []
    )

    assert receipt["schema_version"] == 2, receipt
    assert receipt["verification_contract"] == "OBSERVATION_GROUPS_V1", receipt
    assert receipt["snapshot_fingerprint"] == SNAPSHOT_FINGERPRINT, receipt
    assert receipt["observation_count"] == 2, receipt
    assert len(receipt["observation_fingerprint"]) == 64, receipt

    # Pre-computed VerificationResult objects are not accepted as receipt input.
    try:
        build_production_verification_receipt(
            [good],
            snapshot_id="snapshot-bypass",
            snapshot_fingerprint=SNAPSHOT_FINGERPRINT,
            required_core_keys=[(good.canonical_key, good.fact_type)],
            now=FIXED_NOW,
        )
        raise AssertionError("pre-computed VerificationResult bypass was accepted")
    except ValueError as exc:
        assert str(exc).startswith("OBSERVATION_GROUP_REQUIRED:"), exc

    # Duplicate canonical/fact groups cannot inflate verified counts.
    try:
        build_production_verification_receipt(
            [good_observations, good_observations],
            snapshot_id="snapshot-duplicate",
            snapshot_fingerprint=SNAPSHOT_FINGERPRINT,
            required_core_keys=[(good.canonical_key, good.fact_type)],
            now=FIXED_NOW,
        )
        raise AssertionError("duplicate verification group was accepted")
    except ValueError as exc:
        assert str(exc).startswith("DUPLICATE_VERIFICATION_GROUP:"), exc

    snapshot_mismatch = validate_production_verification_receipt(
        receipt,
        expected_snapshot_id="snapshot-verified-1",
        expected_snapshot_fingerprint="d" * 64,
    )
    assert "verification_receipt snapshot fingerprint mismatch" in snapshot_mismatch

    tampered = dict(receipt)
    tampered["verified_core_fact_count"] = 999
    receipt_errors = validate_production_verification_receipt(
        tampered,
        expected_snapshot_id="snapshot-verified-1",
    )
    assert "verification_receipt verified_core_fact_count mismatch" in receipt_errors
    assert "verification_receipt hash mismatch" in receipt_errors

    try:
        build_production_verification_receipt(
            [bad_observations],
            snapshot_id="snapshot-blocked",
            snapshot_fingerprint=SNAPSHOT_FINGERPRINT,
            required_core_keys=[(bad.canonical_key, bad.fact_type)],
            now=FIXED_NOW,
        )
        raise AssertionError("non-verified evidence created a production receipt")
    except ValueError as exc:
        assert str(exc).startswith("VERIFICATION_GATE_FAILED:"), exc

    print("Instagram TCG source verification regression: PASS")


if __name__ == "__main__":
    main()
