#!/usr/bin/env python3
from source_verification_engine import Observation, verify_fact, strategy_for_retry, x10_fact_gate


def obs(provider, tier, value='100', fact='completed_sale', code='P-S01'):
    return Observation(
        game='pokemon', fact_type=fact, canonical_key='pokemon:test:psa10', value=value,
        source_code=code, source_name=provider, source_locator='https://example.invalid/'+provider,
        source_tier=tier, collector_id='collector:'+provider, provider_id=provider,
        fetched_at_kst='2026-09-04T22:00:00+09:00'
    )


def main():
    # Completed sale: one original source is not enough.
    r = verify_fact([obs('ebay','completed_sale_original')])
    assert r.status == 'partial', r

    # Two independent original completed-sale sources with same value verify.
    r = verify_fact([
        obs('ebay','completed_sale_original','100','completed_sale','P-S01'),
        obs('goldin','completed_sale_original','100','completed_sale','P-S02'),
    ])
    assert r.status == 'verified', r
    assert r.independent_source_count == 2

    # Aggregator / market reference cannot promote completed sale to verified.
    r = verify_fact([
        obs('ebay','completed_sale_original','100','completed_sale','P-S01'),
        obs('pricecharting','market_reference','100','completed_sale','P-S02'),
    ])
    assert r.status == 'partial', r

    # Conflicting independent values fail closed.
    r = verify_fact([
        obs('ebay','completed_sale_original','100','completed_sale','P-S01'),
        obs('goldin','completed_sale_original','110','completed_sale','P-S02'),
    ])
    assert r.status == 'conflict', r

    # Official schedule requires official primary.
    r = verify_fact([obs('news','official_secondary','2026-09-16','official_release','P-S03')])
    assert r.status == 'partial', r
    r = verify_fact([obs('pokemon-official-jp','official_primary','2026-09-16','official_release','P-S04')])
    assert r.status == 'verified', r

    # Market reference can verify only with two independent market providers.
    r = verify_fact([obs('pricecharting','market_reference','200','market_reference','P-S05')])
    assert r.status == 'probable', r
    r = verify_fact([
        obs('pricecharting','market_reference','200','market_reference','P-S05'),
        obs('tcgplayer','market_reference','200','market_reference','P-S06'),
    ])
    assert r.status == 'verified', r

    # SELF-HEAL strategy must change and quarantine by 3+.
    assert strategy_for_retry(0) == 'same_source_backoff'
    assert strategy_for_retry(1) == 'alternate_source'
    assert strategy_for_retry(2) == 'alternate_parser_and_source'
    assert strategy_for_retry(3) == 'quarantine_and_exclude'

    good = verify_fact([
        obs('ebay','completed_sale_original','100','completed_sale','P-S01'),
        obs('goldin','completed_sale_original','100','completed_sale','P-S02'),
    ])
    ok, reasons = x10_fact_gate([good])
    assert ok and not reasons

    bad = verify_fact([obs('ebay','completed_sale_original','100','completed_sale','P-S01')])
    ok, reasons = x10_fact_gate([bad])
    assert not ok and reasons

    print('Instagram TCG source verification regression: PASS')


if __name__ == '__main__':
    main()
