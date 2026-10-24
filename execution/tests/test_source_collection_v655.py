"""Actual collection behavior, ownership, rotating coverage and provider failures."""
import json
import unittest
import urllib.error
import urllib.parse
from pathlib import Path
from unittest.mock import patch
import multi_route_event_discovery as routes
import social_event_discovery as social
from execution import official_social_discovery as scoped

NOW=1800000000

def account(user='pokemon_korea_official', game='포켓몬 카드', region='KR', platform='instagram'):
    host=scoped.PLATFORM_HOSTS[platform]
    return dict(platform=platform,username=user,game=game,region=region,trusted=True,manual=True,profile_url=f'https://{host}/{user}/')

def rss(url='https://www.instagram.com/p/ABC/', title='Pokemon promo event pokemon_korea_official'):
    return f'<rss><channel><item><title>{title}</title><link>{url}</link><pubDate>Fri, 23 Oct 2026 10:00:00 GMT</pubDate></item></channel></rss>'.encode()

class Response:
    def __init__(self, raw, url='https://www.pokemon-card.com/'):
        self.raw,self.url=raw,url
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,limit):return self.raw[:limit]
    def geturl(self):return self.url

class OfficialAccountCollectionTests(unittest.TestCase):
    def setUp(self):
        self.a=account();self.registry={'accounts':[self.a]}
    def test_real_registry_selects_bounded_valid_accounts(self):
        registry=json.loads(Path(social.REGISTRY).read_text())
        rows,total=scoped.select_accounts(registry,NOW)
        self.assertGreater(total,0);self.assertLessEqual(len(rows),6)
        self.assertTrue(all(a['trusted'] is True for a in rows))
    def test_rotation_covers_all_game_country_groups_and_platform_accounts(self):
        rows=[account('fixture'+str(i),game,region,platform) for i,(game,region,platform) in enumerate((g,r,p) for g in social.GAMES for r in social.REGION_LANG for p in ('instagram','x'))]
        seen=set()
        for slot in range(18):
            chosen,total=scoped.select_accounts({'accounts':rows},slot*21600)
            self.assertEqual(18,total);self.assertEqual(6,len(chosen))
            self.assertEqual(6,len({(a['game'],a['region']) for a in chosen}))
            seen.update(a['username'] for a in chosen)
        self.assertEqual({a['username'] for a in rows},seen)
    def test_invalid_untrusted_profiles_and_duplicates_are_excluded(self):
        rows=[self.a,self.a,{**self.a,'trusted':False},{**self.a,'profile_url':'http://instagram.com/a'},{**self.a,'profile_url':'https://attacker.example/pokemon_korea_official/'},{**self.a,'username':'wrong'},{**self.a,'region':'UNKNOWN'}]
        self.assertEqual(([self.a],1),scoped.select_accounts({'accounts':rows},NOW))
        self.assertEqual(([],0),scoped.select_accounts({'accounts':None},NOW))
    def test_both_provider_queries_include_exact_account_and_bounded_terms(self):
        for provider in scoped.PROVIDER_HOSTS:
            url=scoped.search_url(provider,self.a)
            self.assertLessEqual(len(url),1900)
            from urllib.parse import urlsplit,parse_qs
            query=parse_qs(urlsplit(url).query)['q'][0]
            self.assertIn('site:instagram.com',query);self.assertIn('"pokemon_korea_official"',query)
    def test_generic_instagram_post_and_title_spoof_never_become_official(self):
        rows=scoped._parse(rss(), 'bing',self.a,self.registry,NOW)
        self.assertEqual(1,len(rows));self.assertFalse(rows[0]['verified'])
        self.assertFalse(rows[0]['official_account_verified']);self.assertEqual([],rows[0]['dates'])
        for url in ['https://attacker.example/pokemon_korea_official/', 'https://instagram.com/p/ABC/', 'https://x.com/not_official/status/1']:
            self.assertEqual((False,None),social._official_social_match(self.registry,url,'pokemon_korea_official',self.a['game'],'KR'))
    def test_shared_publisher_account_cannot_assign_other_game_post(self):
        a=account('sharedpublisher',platform='x')
        registry={'accounts':[a,{**a,'game':'원피스 카드'}]}
        self.assertEqual([],scoped._parse(rss('https://x.com/sharedpublisher/status/1','ONE PIECE promo event'),'bing',a,registry,NOW))
        self.assertEqual(1,len(scoped._parse(rss('https://x.com/sharedpublisher/status/2','포켓몬 promo event'),'bing',a,registry,NOW)))

    def test_actual_owner_path_is_official_and_wrong_country_is_not(self):
        a=account('pokemonkrmkt',platform='x');registry={'accounts':[a]}
        rows=scoped._parse(rss('https://x.com/pokemonkrmkt/status/1'),'bing',a,registry,NOW)
        self.assertTrue(rows[0]['official_account_verified']);self.assertEqual([],rows[0]['dates'])
        self.assertEqual((False,None),social._official_social_match(registry,rows[0]['source'],'','포켓몬 카드','JP'))
    def test_external_or_private_or_insecure_result_dropped(self):
        for url in ['http://instagram.com/p/ABC','https://127.0.0.1/x','https://evil.example/promo','https://instagram.com.evil.example/promo','https://u:p@instagram.com/p/ABC']:
            self.assertEqual([],scoped._parse(rss(url),'bing',self.a,self.registry,NOW))
    def test_bad_oversized_or_entity_responses_fail(self):
        for raw in [b'<html>challenge</html>',b'<!DOCTYPE rss><rss/>',b'<!ENTITY x "x"><rss/>',b'x'*(scoped.MAX_BYTES+1),b'<rss>']:
            with self.assertRaises((ValueError,scoped.ET.ParseError)):
                scoped._parse(raw,'bing',self.a,self.registry,NOW)
    def test_successful_empty_is_distinct_from_failed(self):
        with patch.object(scoped,'safe_urlopen',return_value=Response(b'<rss><channel/></rss>')):
            rows,errors,status=scoped._provider('bing',[self.a],self.registry,{},NOW)
        self.assertEqual([],rows);self.assertEqual([],errors);self.assertEqual('HEALTHY',status['state']);self.assertEqual(1,status['successful'])
    def test_successful_two_sources_are_independent_requests_and_bounded(self):
        with patch.object(scoped,'safe_urlopen',return_value=Response(rss())) as fetch:
            rows,errors,status=scoped.collect(self.registry,now=NOW)
        self.assertEqual(2,fetch.call_count);self.assertEqual(2,len(rows));self.assertEqual([],errors)
        self.assertEqual(2,status['attempted_query_count']);self.assertEqual(2,status['success_query_count'])
        self.assertTrue(all(not r['verified'] for r in rows))
    def test_429_stops_provider_and_persists_cooldown_across_runs(self):
        error=urllib.error.HTTPError('https://www.bing.com/',429,'slow',{'Retry-After':'30000'},None)
        with patch.object(scoped,'safe_urlopen',side_effect=error) as fetch:
            rows,errors,status=scoped._provider('bing',[self.a]*6,self.registry,{},NOW)
        self.assertEqual(1,fetch.call_count);self.assertEqual('RATE_LIMITED',status['state']);self.assertEqual(NOW+30000,status['blocked_until'])
        with patch.object(scoped,'safe_urlopen') as fetch:
            _,_,later=scoped._provider('bing',[self.a],self.registry,status,NOW+1)
        fetch.assert_not_called();self.assertEqual('COOLDOWN',later['state'])
    def test_403_is_not_retried_and_diagnostics_do_not_store_secret_urls(self):
        error=urllib.error.HTTPError('https://www.bing.com/?access_token=secret',403,'blocked',{},None)
        with patch.object(scoped,'safe_urlopen',side_effect=error) as fetch:
            _,errors,status=scoped._provider('bing',[self.a]*6,self.registry,{},NOW)
        self.assertEqual(1,fetch.call_count);self.assertEqual(NOW+86400,status['blocked_until'])
        self.assertNotIn('secret',str(errors));self.assertIn('403',str(errors))
    def test_provider_requests_are_spaced_and_response_reads_bounded(self):
        with patch.object(scoped,'safe_urlopen',return_value=Response(rss())),patch.object(scoped.time,'sleep') as sleep:
            _,_,status=scoped._provider('bing',[self.a]*6,self.registry,{},NOW)
        self.assertEqual(6,status['attempted']);self.assertEqual(5,sleep.call_count)
        sleep.assert_called_with(2.0)
    def test_same_six_hour_slot_does_not_repeat_even_if_hourly_watch_runs(self):
        with patch.object(scoped,'safe_urlopen',return_value=Response(rss())):
            _,_,first=scoped.collect(self.registry,now=NOW)
        with patch.object(scoped,'safe_urlopen') as fetch:
            _,_,second=scoped.collect(self.registry,first,now=NOW+1)
        fetch.assert_not_called();self.assertEqual(0,second['attempted_query_count'])
        self.assertTrue(all(x['state']=='SLOT_ALREADY_ATTEMPTED' for x in second['providers'].values()))
        with patch.object(scoped,'safe_urlopen',return_value=Response(rss())) as fetch:
            _,_,third=scoped.collect(self.registry,second,now=NOW+21600)
        self.assertEqual(2,fetch.call_count);self.assertEqual(2,third['attempted_query_count'])

    def test_one_provider_failure_does_not_hide_other_provider_success(self):
        def fetch(request,**kwargs):
            if urllib.parse.urlsplit(request.full_url).hostname in scoped.PROVIDER_HOSTS['bing']:raise OSError('offline')
            return Response(rss())
        with patch.object(scoped,'safe_urlopen',side_effect=fetch):
            _,errors,status=scoped.collect(self.registry,now=NOW)
        self.assertEqual(1,status['success_query_count']);self.assertEqual(1,len(errors));self.assertEqual('DEGRADED',status['providers']['bing']['state'])

class MainCollectorIntegrationTests(unittest.TestCase):
    def test_normal_main_calls_new_route_with_prior_cooldown_and_keeps_channel_status(self):
        from contextlib import ExitStack
        from tempfile import TemporaryDirectory
        from unittest.mock import Mock
        with TemporaryDirectory() as directory, ExitStack() as stack:
            output=Path(directory)/'social.json'
            previous={'providers':{'bing':{'blocked_until':NOW+600}}}
            output.write_text(json.dumps({'items':[],'channel_status':{'official_account_search':previous}}))
            registry={'accounts':[account()]}
            stack.enter_context(patch.object(social,'OUT',output))
            stack.enter_context(patch.object(social,'refresh_registry',return_value=(registry,[])))
            learner=Mock();learner.observe_discovered.return_value=0;learner.observe_selected.return_value=0;learner.report.return_value={}
            stack.enter_context(patch.object(social.fan_social_learning,'FanSocialLearner',return_value=learner))
            for name in ['collect_google_news','collect_public_social_search','collect_x','collect_instagram','collect_google_cse']:
                stack.enter_context(patch.object(social,name,return_value=([],[],{'configured':True,'success_query_count':1})))
            stack.enter_context(patch.object(routes,'collect_all',return_value=([],[],{'configured':True,'success_query_count':1})))
            scoped_collect=stack.enter_context(patch.object(scoped,'collect',return_value=([],[],{'configured':True,'success_query_count':0,'providers':previous['providers']})))
            result=social.main()
            scoped_collect.assert_called_once_with(registry,previous)
            self.assertEqual(previous['providers'],result['channel_status']['official_account_search']['providers'])
            self.assertEqual(result['channel_status'],json.loads(output.read_text())['channel_status'])

class OfficialBannerCollectionTests(unittest.TestCase):
    def test_image_alt_aria_title_and_text_are_read_but_script_is_not(self):
        parser=routes._AnchorParser();parser.feed('<a href="/event/1" aria-label="Pokemon event"><img alt="promo card" title="distribution"><script>malicious event</script><span>October</span></a>')
        self.assertEqual(1,len(parser.links))
        text=parser.links[0][1]
        for expected in ['Pokemon event','promo card','distribution','October']:self.assertIn(expected,text)
        self.assertNotIn('malicious',text)
    def test_specific_banner_is_collected_generic_navigation_and_repeated_target_not(self):
        raw=b'<a href="/event/">Events</a><a href="/event/one"><img alt="Pokemon promo card distribution event"></a><a href="/event/one#top">Pokemon promo card distribution event details</a><a href="https://evil.example/event/">Pokemon promo event</a>'
        with patch.object(routes,'safe_urlopen',return_value=Response(raw)):
            rows,error=routes._official_scan_one('포켓몬 카드','JP','https://www.pokemon-card.com/')
        self.assertIsNone(error);self.assertEqual(1,len(rows));self.assertIn('details',rows[0]['title'])
        self.assertEqual([],rows[0]['dates']);self.assertTrue(rows[0]['verified'])
    def test_official_korean_www_alias_can_pass_transport_allowlist(self):
        from safe_runtime import validate_public_https_url
        validate_public_https_url('https://www.pokemonkorea.co.kr/', routes.OFFICIAL_HOSTS)
        self.assertTrue(routes._official_for('포켓몬 카드','KR','www.pokemonkorea.co.kr'))
        raw=b'<a href="https://www.pokemonkorea.co.kr/news/2/123"><img alt="Pokemon promo event"></a>'
        with patch.object(routes,'safe_urlopen',return_value=Response(raw,'https://www.pokemonkorea.co.kr/')):
            rows,error=routes._official_scan_one('포켓몬 카드','KR','https://pokemonkorea.co.kr/news/2')
        self.assertIsNone(error);self.assertEqual(1,len(rows))

    def test_budget_remains_bounded_with_many_banners(self):
        raw=''.join(f'<a href="/event/{i}"><img alt="Pokemon promo event {i}"></a>' for i in range(50)).encode()
        with patch.object(routes,'safe_urlopen',return_value=Response(raw)):
            rows,error=routes._official_scan_one('포켓몬 카드','JP','https://www.pokemon-card.com/')
        self.assertEqual(routes.MAX_PER_QUERY,len(rows))

if __name__=='__main__':unittest.main()
