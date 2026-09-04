#!/usr/bin/env python3
from source_verification_engine import Observation, verify_fact, strategy_for_retry, x10_fact_gate


def obs(provider, tier, value='100', fact='completed_sale', code='P-S01', *, key='pokemon:test:psa10', game='pokemon', status='observed', event_time=None, locator=None):
    return Observation(
        game=game, fact_type=fact, canonical_key=key, value=value,
        source_code=code, source_name=provider, source_locator=locator or ('https://example.invalid/'+provider),
        source_tier=tier, collector_id='collector:'+provider, provider_id=provider,
        fetched_at_kst='2026-09-04T22:00:00+09:00', event_or_trade_time=event_time,
        status=status,
    )


def main():
    # Completed sale: one original source is not enough.
    r = verify_fact([obs('ebay','completed_sale_original')])
    assert r.status == 'partial', r

    # Two independent original completed-sale sources verify even when prices differ.
    # Distinct sale events naturally have different prices; the most recent valid sale
    # becomes the canonical display value while both sources remain traceable.
    r = verify_fact([
        obs('ebay','completed_sale_original','100','completed_sale','P-S01', event_time='2026-09-03T20:00:00+09:00'),
        obs('goldin','completed_sale_original','110','completed_sale','P-S02', event_time='2026-09-04T09:00:00+09:00'),
    ])
    assert r.status == 'verified', r
    assert r.independent_source_count == 2, r
    assert r.canonical_value == '110', r

    # Aggregator / market reference cannot promote completed sale to verified.
    r = verify_fact([
        obs('ebay','completed_sale_original','100','completed_sale','P-S01'),
        obs('pricecharting','market_reference','100','completed_sale','P-S02'),
    ])
    assert r.status == 'partial', r

    # Cancelled/refunded/relisted rows cannot satisfy completed-sale evidence.
    r = verify_fact([
        obs('ebay','completed_sale_original','100','completed_sale','P-S01', status='cancelled'),
        obs('goldin','completed_sale_original','110','completed_sale','P-S02', status='completed'),
    ])
    assert r.status == 'partial', r
    assert r.independent_source_count == 1, r

    # Different canonical identities must never cross-verify.
    r = verify_fact([
        obs('ebay','completed_sale_original','100','completed_sale','P-S01', key='pokemon:a'),
        obs('goldin','completed_sale_original','100','completed_sale','P-S02', key='pokemon:b'),
    ])
    assert r.status == 'conflict', r
    assert 'mixed canonical' in (r.uncertainty_reason or ''), r

    # Unknown source tier / malformed provenance fail closed.
    r = verify_fact([obs('mystery','unknown_tier','100','completed_sale','P-S07')])
    assert r.status == 'unverified', r

    # Official schedule requires official primary.
    r = verify_fact([obs('news','official_secondary','2026-09-16','official_release','P-S03')])
    assert r.status == 'partial', r
    r = verify_fact([obs('pokemon-official-jp','official_primary','2026-09-16','official_release','P-S04')])
    assert r.status == 'verified', r

    # Official sources disagreeing on the same canonical fact fail closed.
    r = verify_fact([
        obs('official-a','official_primary','2026-09-16','official_release','P-S04'),
        obs('official-b','official_secondary','2026-09-17','official_release','P-S05'),
    ])
    assert r.status == 'conflict', r

    # Market reference can verify only with two independent market providers that
    # agree on the same provider-normalized canonical value.
    r = verify_fact([obs('pricecharting','market_reference','200','market_reference','P-S05')])
    assert r.status == 'probable', r
    r = verify_fact([
        obs('pricecharting','market_reference','200','market_reference','P-S05'),
        obs('tcgplayer','market_reference','200','market_reference','P-S06'),
    ])
    assert r.status == 'verified', r

    # Mirror duplication from the same provider does not create independence.
    r = verify_fact([
        obs('pricecharting','market_reference','200','market_reference','P-S05', locator='https://a.invalid/1'),
        obs('pricecharting','market_reference','200','market_reference','P-S05', locator='https://a.invalid/2'),
    ])
    assert r.status == 'probable', r
    assert r.independent_source_count == 1, r

    # SELF-HEAL strategy must change and quarantine by 3+.
    assert strategy_for_retry(0) == 'same_source_backoff'
    assert strategy_for_retry(1) == 'alternate_source'
    assert strategy_for_retry(2) == 'alternate_parser_and_source'
    assert strategy_for_retry(3) == 'quarantine_and_exclude'

    good = verify_fact([
        obs('ebay','completed_sale_original','100','completed_sale','P-S01'),
        obs('goldin','completed_sale_original','110','completed_sale','P-S02'),
    ])
    ok, reasons = x10_fact_gate([good])
    assert ok and not reasons, reasons

    bad = verify_fact([obs('ebay','completed_sale_original','100','completed_sale','P-S01')])
    ok, reasons = x10_fact_gate([bad])
    assert not ok and reasons

    print('Instagram TCG source verification sample regression: PASS')


if __name__ == '__main__':
    main()
