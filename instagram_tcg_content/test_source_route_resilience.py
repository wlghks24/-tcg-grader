#!/usr/bin/env python3
from source_route_resilience import ProviderState, choose_routes, next_strategy, coverage_ok


def main():
    states = [
        ProviderState('ebay','completed_sale_original','rate_limited',1),
        ProviderState('goldin','completed_sale_original','ok',0),
        ProviderState('heritage','completed_sale_original','ok',0),
        ProviderState('pricecharting','market_reference','ok',0),
    ]
    d = choose_routes('completed_sale', states)
    assert d.independent_target == 2
    assert 'goldin' in d.selected and 'heritage' in d.selected, d
    assert coverage_ok('completed_sale', ['goldin','heritage'])
    assert not coverage_ok('completed_sale', ['goldin'])

    assert next_strategy('rate_limited', 1) == 'respect_retry_after_then_alternate_provider'
    assert next_strategy('forbidden', 1) == 'respect_retry_after_then_alternate_provider'
    assert next_strategy('parser_error', 1) == 'alternate_parser_then_alternate_provider'
    assert next_strategy('stale', 1) == 'alternate_provider_then_recheck_primary'
    assert next_strategy('quarantined', 3) == 'quarantine_and_exclude'

    official = choose_routes('official_event', [
        ProviderState('homepage','official_primary','stale',1),
        ProviderState('campaign-detail','official_primary','fresh',0),
        ProviderState('news-index','official_primary','ok',0),
    ])
    assert official.selected[0] in {'campaign-detail','news-index'}, official

    blocked = choose_routes('completed_sale', [
        ProviderState('a','completed_sale_original','quarantined',3),
        ProviderState('b','completed_sale_original','ok',0),
    ])
    assert 'a' not in blocked.selected
    assert blocked.reason.startswith('insufficient independent routes'), blocked

    print('Instagram TCG route resilience regression: PASS')


if __name__ == '__main__':
    main()
