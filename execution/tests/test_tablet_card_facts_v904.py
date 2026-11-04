"""Exact-card enrichment, variants, price freshness and shared-quota fixtures.

No provider requests, servers, photo downloads or training are performed.
"""
import base64
import copy
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import tablet_image_auto_v2 as auto
import tablet_image_library_v1 as library
from execution.tests import test_image_metadata_enrichment as fixtures
from execution import tablet_card_facts_v904 as facts
from execution import tablet_card_view_v904 as view
from execution.tablet_image_unified_v888 import unified_feed
from execution.tablet_catalog_bridge import source_rows, registry

NOW=datetime(2026,11,4,6,tzinfo=timezone.utc)
CARD='https://api.tcgdex.net/v2/en/cards/hgss4-1'
SET='https://api.tcgdex.net/v2/en/sets/hgss4'


def detail():
    return {'id':'hgss4-1','localId':'1','name':'Aggron','category':'Pokemon','dexId':[306],
            'set':{'id':'hgss4','name':'Triumphant'},'variants':{'holo':True,'reverse':True,'normal':False},
            'pricing':{'tcgplayer':{'unit':'USD','updated':NOW.isoformat(),'holofoil':{'marketPrice':4.5},
                                    'reverse-holofoil':{'marketPrice':2.25}}}}


class FactsTests(unittest.TestCase):
    write=fixtures.ImageMetadataTests.write
    def setUp(self):
        fixtures.ImageMetadataTests.setUp(self)

    def photo(self):
        return library.save_image(self.repo,{'game_id':'pokemon','region':'US','kind':'CARD','name':'Aggron · hgss4-1',
          'provider':'TCGdex','source_id':'pokemon/en/hgss4-1','source_url':CARD,
          'card_metadata':{'card_code':'hgss4-1','set_code':'hgss4','set_name':'Triumphant','language':'en','card_number':'1'},
          'image_base64':'data:image/png;base64,'+base64.b64encode(self.png).decode()},trusted_auto=True)

    def rows(self):
        saved=self.photo()
        return [{'entity_id':'photo:'+saved['id'],'image_id':saved['id'],'source_record_id':None,
                 'image_url':'/api/local-card-images/file/'+saved['id'],'game_id':'pokemon','region':'US','kind':'CARD',
                 'name':'Aggron · hgss4-1','card_metadata':library.list_images()['items'][0]['card_metadata'],
                 'link_status':'NEEDS_EXACT_IDENTITY','source_url':CARD}]

    def seed(self):
        facts.observe(CARD,detail(),self.store,now=NOW)
        facts.observe(SET,{'id':'hgss4','name':'Triumphant','serie':{'id':'hgss','name':'HeartGold & SoulSilver'},'releaseDate':'2010-11-03'},self.store,now=NOW)

    def test_species_generation_is_distinct_from_card_release_series(self):
        self.assertEqual('3세대',facts.generation([306]))
        self.assertEqual('2세대',facts.generation([182]))
        self.assertEqual('1세대 · 3세대',facts.generation([25,306]))
        for value in ([True],[0],[1026],'306',[],[306]*5):
            self.assertEqual('',facts.generation(value))
        rows=self.rows();self.seed();linked=facts.attach(rows,self.store)[0]
        self.assertEqual('3세대',linked['card_facts']['generation'])
        self.assertEqual('HeartGold & SoulSilver',linked['card_facts']['series_name'])
        self.assertEqual('NEEDS_EXACT_IDENTITY',linked['link_status'])
        self.assertNotIn('generation',linked['card_metadata'])

    def test_visible_prices_keep_variant_currency_updated_and_reference_semantics(self):
        rows=self.rows();self.seed();page=view.render(facts.attach(rows,self.store)[0],'<img alt="fixture">')
        for value in ('포켓몬 세대','3세대','HeartGold &amp; SoulSilver','2010-11-03','USD 4.5','USD 2.25','리버스 홀로','판본별 시장 참고가'):
            self.assertIn(value,page)
        self.assertLess(page.index('USD 4.5'),page.index('<details>'))
        self.assertIn('홀로·리버스 등 대조 대기',page)
        self.assertNotIn('출시일 미확인',page)

    def test_market_low_and_median_never_substitute_for_market_price(self):
        d=detail();d['pricing']['tcgplayer']={'unit':'USD','normal':{'lowPrice':99,'midPrice':999}}
        self.assertEqual([],facts.prices(d,'en'))
        self.assertEqual([],facts.prices(detail(),'ja'))
        for value in (True,-1,float('nan'),float('inf'),100_000_001,'4.50'):
            d=detail();d['pricing']['tcgplayer']={'unit':'USD','normal':{'marketPrice':value}}
            self.assertEqual([],facts.prices(d,'en'))

    def test_missing_adapter_or_unqualified_price_is_reported_without_false_completion(self):
        marker=object()
        minimal=SimpleNamespace(_BUDGET_CONTEXT=SimpleNamespace(current=marker))
        result=facts.collect(minimal,self.store,[],marker,threading.Event())
        self.assertEqual('FACTS_HOOK_INACTIVE',result['status'])
        self.assertEqual(0,result['saved'])
        d=detail();d['pricing']['tcgplayer']['unit']='unknown'
        self.assertEqual('UNSUPPORTED_OR_UNQUALIFIED',facts.normalize(CARD,d,now=NOW)['price_state'])
        self.assertEqual('LANGUAGE_SCOPE_UNVERIFIED',facts.normalize(CARD.replace('/en/','/ja/'),detail(),now=NOW)['price_state'])

    def test_cardmarket_trend_is_not_called_actual_sale_and_currency_is_explicit(self):
        d=detail();d['pricing']={'cardmarket':{'unit':'EUR','updated':NOW.timestamp()*1000,'trend':1.23,'trend-holo':4.56}}
        prices=facts.prices(d,'en')
        self.assertEqual(['EUR','EUR'],[p['currency'] for p in prices])
        self.assertTrue(all(p['sale_confirmed'] is False and p['metric']=='시장 추세가' for p in prices))

    def test_wrong_provider_url_id_set_or_language_cannot_enrich_another_card(self):
        for url in (CARD+'?x=1',CARD.replace('https:','http:'),CARD.replace('api.tcgdex.net','evil.example')):
            self.assertFalse(facts.observe(url,detail(),self.store,now=NOW))
        d=detail();d['id']='hgss4-2';self.assertFalse(facts.observe(CARD,d,self.store,now=NOW))
        self.assertFalse((self.store/facts.FILE).exists())
        rows=self.rows();self.seed()
        for change in ({'region':'JP'},{'game_id':'onepiece'},{'card_metadata':{'card_code':'hgss4-2','set_code':'hgss4','language':'en'}}, {'card_metadata':{'card_code':'hgss4-1','set_code':'wrong','language':'en'}}):
            self.assertNotIn('card_facts',facts.attach([dict(rows[0],**change)],self.store)[0])

    def test_missing_price_is_not_zero_and_trainer_generation_is_not_guessed(self):
        d=detail();d.pop('pricing');d.pop('dexId');d['category']='Trainer'
        rows=self.rows();facts.observe(CARD,d,self.store,now=NOW)
        row=facts.attach(rows,self.store)[0];page=view.render(row,'<p>fixture</p>')
        self.assertIn('공급사에 가격 자료가 없습니다',page)
        self.assertIn('해당 없음 · Trainer',page)
        self.assertNotIn('USD 0',page)

    def test_stale_future_and_undated_quotes_are_never_reported_recent(self):
        self.assertEqual('최근 참고시세',view.freshness(NOW.isoformat(),NOW))
        self.assertIn('오래된',view.freshness((NOW-timedelta(days=8)).isoformat(),NOW))
        self.assertIn('미래',view.freshness((NOW+timedelta(hours=1)).isoformat(),NOW))
        self.assertEqual('갱신일 미확인',view.freshness('',NOW))

    def test_missing_refresh_fields_retain_previous_facts_and_label_price_as_retained(self):
        rows=self.rows();self.seed();d=detail();d.pop('pricing');d.pop('dexId')
        facts.observe(CARD,d,self.store,now=NOW+timedelta(days=1))
        attached=facts.attach(rows,self.store)[0]
        self.assertEqual('3세대',attached['card_facts']['generation'])
        page=view.render(attached,'<p>fixture</p>')
        self.assertIn('USD 4.5',page);self.assertIn('이전 참고가 보존',page)
        self.assertIn('누적 상세값 보존',page)

    def test_changed_generation_or_card_number_never_overwrites_previous_fact(self):
        self.seed();before=(self.store/facts.FILE).read_bytes()
        for field,value in [('dexId',[182]),('localId','2')]:
            d=detail();d[field]=value
            with self.assertRaises(ValueError): facts.observe(CARD,d,self.store,now=NOW)
            self.assertEqual(before,(self.store/facts.FILE).read_bytes())

    def test_corrupt_symlink_duplicate_json_and_invalid_quotes_preserve_previous_bytes(self):
        self.seed();path=self.store/facts.FILE;before=path.read_bytes()
        d=detail();d['set']['id']='different'
        with self.assertRaises(ValueError): facts.observe(CARD,d,self.store,now=NOW)
        self.assertEqual(before,path.read_bytes())
        data=json.loads(before);data['items']['en/cards/hgss4-1']['prices'][0]['amount']=True
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError): facts.read(self.store)
        path.write_text('{"version":904,"version":904,"items":{}}')
        with self.assertRaises(ValueError): facts.read(self.store)
        path.unlink();target=self.store/'target';target.write_bytes(before);path.symlink_to(target)
        with self.assertRaises(ValueError): facts.observe(CARD,detail(),self.store,now=NOW)
        self.assertEqual(before,target.read_bytes())

    def test_attach_and_summary_are_read_only_and_do_not_read_photo_pixels(self):
        rows=self.rows();self.seed();before={str(p):p.read_bytes() for p in self.store.rglob('*') if p.is_file()}
        with patch.object(library,'get_image',side_effect=AssertionError('pixel read')):
            facts.attach(rows,self.store);result=facts.summary(self.store)
        self.assertEqual(1,result['cards_with_species_generation'])
        self.assertEqual(1,result['cards_with_price_references'])
        self.assertFalse(result['identity_verified'])
        self.assertEqual(before,{str(p):p.read_bytes() for p in self.store.rglob('*') if p.is_file()})

    def budget(self):
        state=auto._state(self.store);return auto.policy.Budget(state,lambda:None,clock=lambda:NOW.timestamp(),timer=lambda:1)

    def install_fetch(self,budget,reply):
        calls=[]
        def fetch(url):
            budget.reserve_request('TCGdex',sleeper=lambda _:None);calls.append(url)
            return copy.deepcopy(reply(url))
        fetch._tcg_raw_json_v900=True
        patch.object(auto,'fetch_json',fetch).start();facts.install(auto)
        auto._BUDGET_CONTEXT.current=budget
        self.addCleanup(lambda:delattr(auto._BUDGET_CONTEXT,'current'))
        return calls

    def test_complete_existing_metadata_is_revisited_in_same_persisted_request_budget(self):
        self.photo();records=library._load(self.store)['items'];budget=self.budget()
        original=library.get_image(records[0]['id'])
        index_before=(self.store/'index.json').read_bytes()
        def reply(url):
            return {'id':'hgss4','serie':{'id':'hgss','name':'HeartGold & SoulSilver'},'releaseDate':'2010-11-03'} if '/sets/' in url else detail()
        calls=self.install_fetch(budget,reply)
        self.assertTrue(auto.fetch_json._tcg_raw_json_v900)
        result=facts.collect(auto,self.store,records,budget,threading.Event(),now=NOW)
        self.assertEqual(2,result['attempted']);self.assertEqual([CARD,SET],calls)
        self.assertEqual(2,len(budget.state['image_budget_events']))
        self.assertEqual(1,facts.summary(self.store)['cards_with_price_references'])
        self.assertEqual(original,library.get_image(records[0]['id']))
        self.assertEqual(index_before,(self.store/'index.json').read_bytes())
        before=len(calls);facts.collect(auto,self.store,records,budget,threading.Event(),now=NOW)
        self.assertEqual(before,len(calls))

    def test_deferred_set_is_retried_without_redownloading_fresh_card(self):
        self.photo();facts.observe(CARD,detail(),self.store,now=NOW)
        budget=self.budget();calls=self.install_fetch(budget,lambda url:{'id':'hgss4','serie':{'id':'hgss','name':'HGSS'}})
        result=facts.collect(auto,self.store,library._load(self.store)['items'],budget,threading.Event(),now=NOW)
        self.assertEqual([SET],calls);self.assertEqual(1,result['attempted'])

    def test_existing_provider_cooldown_stops_without_any_request_or_cache_write(self):
        self.photo();budget=self.budget();budget.state['image_provider_cooldowns']['TCGdex']=NOW.timestamp()+3600
        calls=self.install_fetch(budget,lambda url:detail())
        result=facts.collect(auto,self.store,library._load(self.store)['items'],budget,threading.Event(),now=NOW)
        self.assertTrue(result['deferred']);self.assertEqual([],budget.events)
        self.assertFalse((self.store/facts.FILE).exists())

    def test_enrichment_fanout_is_bounded_and_duplicate_provider_ids_do_not_repeat(self):
        self.photo();record=library._load(self.store)['items'][0];budget=self.budget()
        def reply(url):
            if '/sets/' in url: return {'id':'hgss4'}
            d=detail();d['id']=url.rsplit('/',1)[1];d['localId']=d['id'].split('-')[-1];return d
        calls=self.install_fetch(budget,reply)
        records=[]
        for i in range(1,12):
            item=copy.deepcopy(record);item['source_id']='pokemon/en/hgss4-'+str(i)
            item['card_metadata'].update(card_code='hgss4-'+str(i),card_number=str(i));records.extend([item,item])
        result=facts.collect(auto,self.store,records,budget,threading.Event(),now=NOW)
        self.assertEqual(facts.MAX_REQUESTS,result['attempted'])
        self.assertEqual(facts.MAX_REQUESTS,len(budget.events))
        self.assertEqual(len(calls),len(set(calls)))

    def test_catalog_reference_price_survives_the_exact_source_feed_without_photo_merge(self):
        self.write('market_watch.json',{'items':[{'game_id':'pokemon','region':'US','name':'Aggron hgss4-1','kind':'CARD','card_metadata':{'card_code':'hgss4-1','language':'en','printing':'holo'},'source':'https://example.com/price','display':'$4.50','market':'fixture','kind_note':'reference','source_date':'2026-11-04','link_status':'정상'}]})
        games,aliases=registry(self.repo);sources,errors,_,_=source_rows(self.repo,games,aliases)
        self.assertFalse(errors);self.assertEqual('$4.50',sources[0]['market_quote']['display'])
        source=sources[0]
        rows=unified_feed({'ok':True,'summary':{},'local_catalog':[],'source_catalog':[source],'catalog_matches':[]})
        self.assertEqual('$4.50',rows[0]['market_quote']['display'])
        self.assertEqual('NEEDS_IMAGE',rows[0]['link_status'])


if __name__=='__main__':
    unittest.main()
