#!/usr/bin/env python3
import validate_external_links as links


def main():
    original_probe=links.probe
    try:
        calls=[]
        def fake_probe(url,request_timeout=None):
            calls.append(url)
            if url=='https://example.com/':
                return {'state':'ok','code':200,'final_url':url}
            return {'state':'broken','code':404,'confirmed_by':'GET'}
        links.probe=fake_probe

        row={'url':'https://example.com/retired/card'}
        tasks={'https://example.com/retired/card':[('releases.json',row,'url')]}
        results={'https://example.com/retired/card':{'state':'broken','code':404,'confirmed_by':'GET'}}
        stats=links._attach_same_host_fallbacks(tasks,results,5)
        assert stats=={'eligible':1,'probes':1,'verified':1},stats
        assert results['https://example.com/retired/card']['fallback_url']=='https://example.com/'
        counts,details=links._apply_results(tasks,results,'2026-09-02T00:00:00+00:00')
        assert counts['broken']==1 and counts['repaired']==1 and counts['unresolved_broken']==0,counts
        assert details==[],details
        assert row['url']=='https://example.com/'
        assert row['original_url']=='https://example.com/retired/card'
        assert '동일 도메인 홈' in row['link_status']

        # A dead homepage must not hide the original broken deep link.
        def dead_home(url,request_timeout=None):
            return {'state':'broken','code':404,'confirmed_by':'GET'}
        links.probe=dead_home
        row2={'url':'https://dead.example/path'}
        tasks2={'https://dead.example/path':[('promo_events.json',row2,'url')]}
        results2={'https://dead.example/path':{'state':'broken','code':410,'confirmed_by':'GET'}}
        stats2=links._attach_same_host_fallbacks(tasks2,results2,5)
        assert stats2['verified']==0,stats2
        counts2,details2=links._apply_results(tasks2,results2,'2026-09-02T00:00:00+00:00')
        assert counts2['unresolved_broken']==1 and counts2['repaired']==0,counts2
        assert row2['url']=='https://dead.example/path'
        assert len(details2)==1

        # url_template behavior must never be silently downgraded to a homepage.
        links.probe=fake_probe
        row3={'url_template':'https://search.example/find?q={query}'}
        tasks3={'https://search.example/find?q={query}':[('purchase_sources.json',row3,'url_template')]}
        results3={'https://search.example/find?q={query}':{'state':'broken','code':404,'confirmed_by':'GET'}}
        stats3=links._attach_same_host_fallbacks(tasks3,results3,5)
        assert stats3=={'eligible':0,'probes':0,'verified':0},stats3
        assert 'fallback_url' not in results3['https://search.example/find?q={query}']

        # Automation-restricted home pages still exist for real browser users.
        def restricted_home(url,request_timeout=None):
            return {'state':'restricted','code':403}
        links.probe=restricted_home
        row4={'source':'https://shop.example/old-product'}
        tasks4={'https://shop.example/old-product':[('market_watch.json',row4,'source')]}
        results4={'https://shop.example/old-product':{'state':'broken','code':404,'confirmed_by':'GET'}}
        stats4=links._attach_same_host_fallbacks(tasks4,results4,5)
        assert stats4['verified']==1,stats4
        assert results4['https://shop.example/old-product']['fallback_url']=='https://shop.example/'

    finally:
        links.probe=original_probe

    print('[OK] same-host broken-link fallback v189')


if __name__=='__main__':
    main()
