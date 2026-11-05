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

    def test_video_all_tcg_series_and_release_are_not_blank(self):
        base=self.rows()[0]
        for game_id,series in (('onepiece','로맨스 던'),('naruto','나루토 신규 세트'),
                               ('mtg','어둠의 승천'),('gundam','건담 시즌 원')):
            row=dict(base,game_id=game_id,name=series,source_url='',image_id=None,image_url=None)
            row['card_metadata']={'set_name':series,'set_code':'SET-01','language':'ja','card_number':'001'}
            row['observed_release_date']='2026-10-01'
            page=view.render(row,'<p>fixture</p>')
            self.assertIn('등록된 발매 시리즈·세트',page)
            self.assertIn(series,page)
            self.assertIn('공개 출처 출시일 참고',page)
            self.assertIn('2026-10-01',page)
            self.assertNotIn('출시 시리즈 수집 대기',page)
            self.assertNotIn('포켓몬 세대',page)
            self.assertIn('언어·희귀도·인쇄판본 대조 대기',page)
            self.assertNotIn('3세대',page)

    def test_video_market_reference_is_not_presented_as_live_trade(self):
        self.assertIn('오래된 공개 참고가',
                      view.market_observed_state('2026-10-08',NOW))
        self.assertIn('최근 공개 참고가',
                      view.market_observed_state('2026-11-03',NOW))
        self.assertIn('미래 관측일',
                      view.market_observed_state('2026-11-05',NOW))
        self.assertIn('관측일 미확인',
                      view.market_observed_state('',NOW))
        self.assertIn('관측일 확인 필요',
                      view.market_observed_state('2026-11-99',NOW))
        self.assertEqual('',view.checked_release_date('2026-02-30'))
        self.assertEqual('',view.checked_release_date('<script>'))
        base=self.rows()[0]
        row=dict(base,game_id='naruto',kind='BOX',image_id=None,image_url=None,
                 card_metadata={'set_name':'나루토 BOX','language':'ja'},
                 market_quote={'display':'₩37,000','market':'기록된 시장 자료',
                               'basis':'공개 표시가격','observed_at':'2026-10-08',
                               'sale_confirmed':False},
                 source_health='UNVERIFIED')
        page=view.render(row,'<p>fixture</p>')
        self.assertIn('상품·BOX 시장 참고가',page)
        self.assertIn('₩37,000',page)
        self.assertIn('오래된 공개 참고가',page)
        self.assertIn('출처 연결 재확인 필요',page)
        self.assertIn('실제 체결가',page)
        self.assertNotIn('포켓몬 세대',page)

    def test_market_selection_has_evidenced_set_and_printing_identity(self):
        base=self.rows()[0]
        row=dict(base,game_id='onepiece',image_id=None,image_url=None,
                 card_metadata={'card_code':'OP01-001','set_code':'OP01',
                                'set_name':'로맨스 던','printing':'holo','language':'ja'})
        page=view.render(row,'<p>fixture</p>')
        self.assertIn('data-card-code="OP01-001"',page)
        self.assertIn('data-set-code="OP01"',page)
        self.assertIn('data-printing="holo"',page)
        self.assertIn('판본별 시장 참고가',page)
        self.assertNotIn('실제 체결가 확정',page)

        # Verified card-facts set is the fallback only when exact metadata set
        # was not recorded; never infer a set from a shared numeric card code.
        row['card_metadata']={'card_code':'OP01-001','printing':'reverse'}
        row['card_facts']={'set_id':'OP02'}
        fallback=view.render(row,'<p>fixture</p>')
        self.assertIn('data-set-code="OP02"',fallback)
        self.assertIn('data-printing="reverse"',fallback)
        row['card_facts']={}
        unknown=view.render(row,'<p>fixture</p>')
        self.assertIn('data-set-code=""',unknown)

    def test_market_identity_attributes_html_escape_untrusted_metadata(self):
        row=dict(self.rows()[0],game_id='onepiece',image_id=None,image_url=None,
                 card_metadata={'card_code':'OP01-001',
                                'set_code':'OP01" onmouseover="alert(1)',
                                'printing':'holo"><script>alert(1)</script>',
                                'language':'ja'})
        page=view.render(row,'<p>fixture</p>')
        self.assertIn('data-set-code="OP01&quot; onmouseover=&quot;alert(1)"',page)
        self.assertIn('data-printing="holo&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;"',page)
        self.assertNotIn('data-set-code="OP01" onmouseover=',page)
        self.assertNotIn('<script>alert(1)</script>',page)


    def test_catalog_conflict_and_partial_view_do_not_allow_grade_or_cached_price(self):
        rows=self.rows();self.seed()
        attached=facts.attach(rows,self.store)[0]
        self.assertIn('card_facts',attached)
        self.assertIn('USD 4.5',view.render(attached,'<p>fixture</p>'))
        before=(self.store/'index.json').read_bytes()
        # Even if a previous/caller row contains attached values, the
        # renderer must enforce the catalog trust status independently.
        for status,extra in (('METADATA_CONFLICT',{}),
                             ('SOURCE_COVERAGE_INCOMPLETE',{'display_only':True}),
                             ('NEEDS_EXACT_IDENTITY',{'display_only':True})):
            with self.subTest(status=status,extra=extra):
                unsafe=dict(attached,link_status=status,
                            market_quote={'display':'$999','observed_at':'2026-11-04'},
                            **extra)
                page=view.render(unsafe,'<p>fixture</p>')
                self.assertIn('data-card-actions-blocked="true"',page)
                # Source HTML itself must be safe without JS interception.
                self.assertNotIn('href="/index.html?feature=auto-grade"',page)
                self.assertNotIn('href="/index.html?feature=grading-economics"',page)
                self.assertNotIn('data-source-identity-conflict="true"',page)
                self.assertIn('role="alert"',page)
                self.assertIn('연결을 보류',page)
                self.assertNotIn('USD 4.5',page)
                self.assertNotIn('$999',page)
                self.assertIn('market_quote',unsafe)
                self.assertIn('card_facts',unsafe)
        safe_page=view.render(attached,'<p>fixture</p>')
        self.assertNotIn('data-card-actions-blocked="true"',safe_page)
        self.assertEqual(before,(self.store/'index.json').read_bytes())

    def test_boxes_packs_and_products_do_not_offer_individual_card_grading(self):
        base=self.rows()[0]
        for kind in ('BOX','PRODUCT','PACK'):
            with self.subTest(kind=kind):
                row=dict(base,game_id='onepiece',kind=kind,image_id=None,image_url=None,
                         card_metadata={'set_name':'안전 검증 상품','language':'ja'})
                page=view.render(row,'<p>상품 사진 확인 대기</p>')
                self.assertIn('상품·BOX 시장 참고가',page)
                self.assertIn('상품·BOX 가격·출처 보기',page)
                self.assertIn('BOX·팩·상품은 개별 카드 등급 측정 대상이 아닙니다',page)
                self.assertIn('상품·BOX 참고시세는 위의 가격 근거 영역',page)
                self.assertNotIn('href="/index.html?feature=auto-grade"',page)
                self.assertNotIn('href="/index.html?feature=grading-economics"',page)
                self.assertNotIn('<summary>등급·판매가·출처 보기</summary>',page)
        for kind in ('CARD','PROMO'):
            with self.subTest(kind=kind):
                row=dict(base,game_id='onepiece',kind=kind,image_id=None,image_url=None)
                page=view.render(row,'<p>카드 사진 확인 대기</p>')
                self.assertIn('href="/index.html?feature=auto-grade"',page)
                self.assertIn('href="/index.html?feature=grading-economics"',page)
                self.assertIn('판본별 시장 참고가',page)


    def test_video_all_tcg_html_escaped_and_missing_fields_not_invented(self):
        row=dict(self.rows()[0],game_id='onepiece',image_id=None,image_url=None,
                 source_url='',card_metadata={'set_name':'<script>alert(1)</script>','language':'ja'},
                 observed_release_date='2026-02-30')
        page=view.render(row,'<p>fixture</p>')
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;',page)
        self.assertNotIn('<script>alert(1)</script>',page)
        self.assertNotIn('공개 출처 출시일 참고',page)
        self.assertIn('카드 상세·가격 수집 대기',page)
        row['card_metadata']={'language':'ja'}
        self.assertIn('시리즈·세트 근거 수집 대기',
                      view.render(row,'<p>fixture</p>'))


    def test_market_low_and_median_never_substitute_for_market_price(self):
        d=detail();d['pricing']['tcgplayer']={'unit':'USD','normal':{'lowPrice':99,'midPrice':999}}
        self.assertEqual([],facts.prices(d,'en'))
        self.assertEqual([],facts.prices(detail(),'ja'))
        for value in (True,-1,float('nan'),float('inf'),100_000_001,10**1000,'4.50'):
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
        for change in ({'region':'JP'},{'game_id':'onepiece'},{'kind':'BOX'},{'card_metadata':{'card_code':'hgss4-2','set_code':'hgss4','language':'en'}}, {'card_metadata':{'card_code':'hgss4-1','set_code':'wrong','language':'en'}}):
            self.assertNotIn('card_facts',facts.attach([dict(rows[0],**change)],self.store)[0])

    def test_conflicting_photo_metadata_is_visible_read_only_and_never_inherits_price(self):
        rows=self.rows();self.seed()
        good=facts.attach(rows,self.store)[0]
        self.assertIn('card_facts',good)
        self.assertNotIn('card_facts_conflict',good)
        before=(self.store/'index.json').read_bytes()
        metadata=rows[0]['card_metadata']
        for change in ({'card_code':'hgss4-2'},{'language':'ja'},{'set_code':'wrong'}):
            with self.subTest(change=change):
                bad=dict(rows[0],card_metadata=dict(metadata,**change))
                linked=facts.attach([bad],self.store)[0]
                self.assertTrue(linked['card_facts_conflict'])
                self.assertEqual('METADATA_CONFLICT',linked['link_status'])
                self.assertNotIn('card_facts',linked)
                injected=dict(linked,market_quote={'display':'$999','observed_at':'2026-11-04'})
                page=view.render(injected,'<p>fixture</p>')
                self.assertIn('상세·시세 연결을 보류',page)
                self.assertIn('data-source-identity-conflict="true"',page)
                self.assertIn('원본은 보존',page)
                self.assertNotIn('$999',page)
                self.assertNotIn('USD 4.5',page)
        self.assertEqual(before,(self.store/'index.json').read_bytes())
        for change in ({'region':'JP'},{'game_id':'onepiece'},{'kind':'BOX'}):
            unrelated=facts.attach([dict(rows[0],**change)],self.store)[0]
            self.assertNotIn('card_facts_conflict',unrelated)

    def test_missing_photo_or_provider_identity_is_not_a_false_conflict(self):
        rows=self.rows();self.seed()
        original=rows[0]
        metadata=original['card_metadata']
        before=(self.store/'index.json').read_bytes()
        for missing in ({'card_code':None},{'card_code':''},
                        {'language':''},{'set_code':''}):
            with self.subTest(missing=missing):
                candidate=dict(original,card_metadata=dict(metadata,**missing))
                linked=facts.attach([candidate],self.store)[0]
                self.assertNotIn('card_facts_conflict',linked)
                self.assertNotIn('card_facts',linked)
                self.assertEqual('NEEDS_EXACT_IDENTITY',linked['link_status'])
                page=view.render(linked,'<p>fixture</p>')
                self.assertNotIn('data-source-identity-conflict="true"',page)
                self.assertNotIn('상세·시세 연결을 보류',page)
        # Provider response without a set cannot prove a set mismatch.
        cache=copy.deepcopy(facts.read(self.store))
        cache['items']['en/cards/hgss4-1'].pop('set_id')
        with patch.object(facts,'read',return_value=cache):
            linked=facts.attach([original],self.store)[0]
        self.assertNotIn('card_facts_conflict',linked)
        self.assertNotIn('card_facts',linked)
        self.assertEqual('NEEDS_EXACT_IDENTITY',linked['link_status'])
        self.assertEqual(before,(self.store/'index.json').read_bytes())

    def test_repeated_enrichment_drops_stale_detail_and_blocks_unverified_catalog(self):
        rows=self.rows();self.seed()
        original=rows[0]
        first=facts.attach(rows,self.store)[0]
        self.assertIn('card_facts',first)
        before=(self.store/'index.json').read_bytes()
        # Reusing a prior display row with a newly contradictory identity
        # cannot preserve yesterday's provider detail or price evidence.
        changed=dict(first,card_metadata=dict(original['card_metadata'],set_code='wrong'))
        again=facts.attach([changed],self.store)[0]
        self.assertTrue(again['card_facts_conflict'])
        self.assertEqual('METADATA_CONFLICT',again['link_status'])
        self.assertNotIn('card_facts',again)
        page=view.render(again,'<p>fixture</p>')
        self.assertIn('상세·시세 연결을 보류',page)
        self.assertNotIn('USD 4.5',page)

        # Source/catalog conflicts and incomplete reads must not be
        # promoted to exact card facts merely because the photo ID matches.
        for extra in ({'link_status':'METADATA_CONFLICT'},
                      {'link_status':'SOURCE_COVERAGE_INCOMPLETE','display_only':True}):
            with self.subTest(extra=extra):
                guarded=dict(first,**extra)
                linked=facts.attach([guarded],self.store)[0]
                self.assertNotIn('card_facts',linked)
                self.assertNotIn('market_quote',linked)
                self.assertNotIn('card_facts_conflict',linked)
                self.assertEqual(extra['link_status'],linked['link_status'])
                self.assertNotIn('USD 4.5',view.render(linked,'<p>fixture</p>'))
        changed_source=dict(first,region='JP')
        stale=facts.attach([changed_source],self.store)[0]
        self.assertNotIn('card_facts',stale)
        self.assertNotIn('card_facts_conflict',stale)
        self.assertEqual(before,(self.store/'index.json').read_bytes())
        self.assertIn('card_facts',first) # No mutation of caller input.

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

    def test_main_keeps_provider_facts_when_separate_public_market_read_fails(self):
        from execution import tablet_live_view_v898 as live
        from execution import tablet_menu_shell_v903 as shell
        rows=self.rows();self.seed()
        with patch.object(live,'read_view',return_value={'view_state':'COMPLETE','rows':rows,'events':{'ok':False}}), patch.object(facts,'attach_market',side_effect=ValueError('unreadable')):
            data=shell.gallery(self.repo)
        self.assertTrue(data['facts_error'])
        self.assertIn('USD 4.5',data['cards'])
        self.assertIn('3세대',data['cards'])

    def test_japanese_plus_set_uses_only_canonical_encoded_source(self):
        url='https://api.tcgdex.net/v2/ja/sets/SM1%2B'
        payload={'id':'SM1+','name':'Expansion Pack +','serie':{'id':'SM','name':'Sun & Moon'},'releaseDate':'2017-01-01'}
        self.assertTrue(facts.observe(url,payload,self.store,now=NOW))
        self.assertIn('ja/sets/SM1+',facts.read(self.store)['items'])
        self.assertEqual('2017-01-01',facts.read(self.store)['items']['ja/sets/SM1+']['release_date'])
        before=(self.store/facts.FILE).read_bytes()
        for invalid in ('SM1+', 'SM1%252B', 'SM1%2b', '..%2B'):
            self.assertFalse(facts.observe('https://api.tcgdex.net/v2/ja/sets/'+invalid,payload,self.store,now=NOW))
        self.assertEqual(before,(self.store/facts.FILE).read_bytes())

    def test_detailed_variant_pricing_is_distinct_from_photo_printing(self):
        rows=self.rows()
        d=detail();d.pop('pricing')
        d['variants_detailed']=[
            {'variantId':'genuine_variant_13','pricing':{'tcgplayer':{'unit':'USD','updated':NOW.isoformat(),'holofoil':{'marketPrice':9.87}}}},
            {'variantId':'generated','pricing':{'tcgplayer':{'unit':'USD','normal':{'marketPrice':999}}}},
            {'variantId':'genuine_variant_14','pricing':{'cardmarket':{'unit':'EUR','trend':0,'trend-holo':5.43}}}
        ]
        quotes=facts.prices(d,'en')
        self.assertEqual(2,len(quotes))
        self.assertEqual({'USD','EUR'},{q['currency'] for q in quotes})
        self.assertTrue(all(q['price_scope']=='DETAILED_VARIANT' and q['sale_confirmed'] is False for q in quotes))
        self.assertEqual([],facts.prices(d,'ja'))
        facts.observe(CARD,d,self.store,now=NOW)
        linked=facts.attach(rows,self.store)[0]
        self.assertEqual('NEEDS_EXACT_IDENTITY',linked['link_status'])
        page=view.render(linked,'<p>fixture</p>')
        for field in ('USD 9.87','EUR 5.43','세부 발매판 참고','실제 판본과는 별도'):
            self.assertIn(field,page)
        self.assertNotIn('USD 999',page)
        self.assertNotIn('EUR 0',page)

    def test_incomplete_set_refresh_retains_old_release_without_overwriting_identity(self):
        self.seed();old=facts.read(self.store)['items']['en/sets/hgss4']
        facts.observe(SET,{'id':'hgss4','name':'Triumphant','serie':{}},self.store,now=NOW+timedelta(days=1))
        saved=facts.read(self.store)['items']['en/sets/hgss4']
        self.assertEqual(old['release_date'],saved['release_date'])
        self.assertEqual(old['series_name'],saved['series_name'])
        self.assertIn('release_date',saved['retained_fields'])
        page=view.render(facts.attach(self.rows(),self.store)[0],'<p>fixture</p>')
        self.assertIn('누적 상세값 보존',page)
        before=(self.store/facts.FILE).read_bytes()
        with self.assertRaises(ValueError):
            facts.observe(SET,{'id':'hgss4','serie':{'id':'wrong'}},self.store,now=NOW+timedelta(days=2))
        self.assertEqual(before,(self.store/facts.FILE).read_bytes())

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

    def test_partial_set_facts_retry_after_daily_backoff_instead_of_staying_missing_forever(self):
        self.photo();facts.observe(CARD,detail(),self.store,now=NOW);facts.observe(SET,{'id':'hgss4'},self.store,now=NOW)
        budget=self.budget()
        calls=self.install_fetch(budget,lambda url:{'id':'hgss4','serie':{'id':'hgss','name':'HGSS'},'releaseDate':'2010-11-03'} if '/sets/' in url else detail())
        records=library._load(self.store)['items']
        facts.collect(auto,self.store,records,budget,threading.Event(),now=NOW)
        self.assertEqual([],calls)
        facts.collect(auto,self.store,records,budget,threading.Event(),now=NOW+timedelta(hours=25))
        self.assertEqual([CARD,SET],calls)
        self.assertEqual(1,facts.summary(self.store)['sets_with_series_and_date'])

    def test_failed_card_backoff_allows_other_cards_to_continue(self):
        self.photo();records=library._load(self.store)['items'];other=copy.deepcopy(records[0])
        other['source_id']='pokemon/en/hgss4-2';other['card_metadata'].update(card_code='hgss4-2',card_number='2');records.append(other)
        budget=self.budget()
        def reply(url):
            if url==CARD: raise auto.ProviderError('fixture unavailable')
            if url==SET: return {'id':'hgss4','serie':{'id':'hgss','name':'HGSS'},'releaseDate':'2010-11-03'}
            d=detail();d.update(id='hgss4-2',localId='2');return d
        calls=self.install_fetch(budget,reply)
        result=facts.collect(auto,self.store,records,budget,threading.Event(),now=NOW)
        self.assertEqual(1,result['saved']);self.assertEqual(1,len(result['issues']))
        before=len(calls);facts.collect(auto,self.store,records,budget,threading.Event(),now=NOW)
        self.assertEqual(before,len(calls))
        self.assertIn(CARD,facts.read(self.store)['failures'])

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
        self.assertFalse(errors)
        self.assertNotIn('market_quote',sources[0])  # the frozen historical parser is unchanged
        source=sources[0]
        rows=unified_feed({'ok':True,'summary':{},'local_catalog':[],'source_catalog':[source],'catalog_matches':[]})
        rows=facts.attach_market(rows,self.repo)
        self.assertEqual('$4.50',rows[0]['market_quote']['display'])
        self.assertEqual('NEEDS_IMAGE',rows[0]['link_status'])
        for changes in ({'region':'JP'},{'kind':'BOX'},{'display_only':True},{'link_status':'METADATA_CONFLICT'}):
            # Pass the already-enriched object, not a cleaned fixture, so the
            # regression catches stale quotes surviving a new validation pass.
            other=dict(rows[0],**changes)
            self.assertIn('market_quote',other)
            invalid=facts.attach_market([other],self.repo)[0]
            self.assertNotIn('market_quote',invalid)
            self.assertIn('market_quote',other)  # Caller input unchanged.


if __name__=='__main__':
    unittest.main()
