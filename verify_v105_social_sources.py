#!/usr/bin/env python3
from __future__ import annotations
import contextlib
import io
import json
import os
import tempfile
from pathlib import Path
import social_event_discovery as s

checks=[]
def check(name, fn):
    try:
        fn(); checks.append({'name':name,'ok':True})
    except Exception as exc:
        checks.append({'name':name,'ok':False,'detail':f'{type(exc).__name__}: {exc}'})

def t_social_links():
    assert s._parse_social_link('https://x.com/Pokemon') == ('x','Pokemon')
    assert s._parse_social_link('https://www.instagram.com/pokemon/') == ('instagram','pokemon')
    assert s._parse_social_link('https://x.com/intent/post?text=x') is None
    assert s._parse_social_link('https://www.instagram.com/p/ABC/') is None

def t_category_dates():
    text='포켓몬 콜라보 팝업 2026년 9월 12일 오픈'
    assert s._category(text)=='collaboration'
    assert s._dates(text)==['2026-09-12']
    assert s._category('NARUTO movie release 2026-10-03')=='movie'

def t_x_query():
    q=s._game_query_terms('원피스 카드','JP')
    assert 'lang:ja' in q and '-is:retweet' in q and ('ワンピース' in q or 'ONE PIECE' in q)
    assert len(q) < 512

def t_secret_redaction():
    old=os.environ.get('X_BEARER_TOKEN')
    os.environ['X_BEARER_TOKEN']='SUPER_SECRET_TOKEN'
    try:
        red=s._secret_safe('Authorization Bearer SUPER_SECRET_TOKEN access_token=SUPER_SECRET_TOKEN')
        assert 'SUPER_SECRET_TOKEN' not in red and '[REDACTED]' in red
    finally:
        if old is None: os.environ.pop('X_BEARER_TOKEN',None)
        else: os.environ['X_BEARER_TOKEN']=old

def t_x_parse_official():
    old_token=os.environ.get('X_BEARER_TOKEN')
    os.environ['X_BEARER_TOKEN']='TOKEN'
    old=s._x_request
    try:
        def fake(query):
            return {'ok':True,'configured':True,'payload':{
                'data':[{'id':'123','text':'ONE PIECE コラボイベント 2026年9月4日','author_id':'u1','created_at':'2026-08-28T00:00:00Z'}],
                'includes':{'users':[{'id':'u1','username':'onepiece_official','verified':True}]}}}
        s._x_request=fake
        reg={'accounts':[{'platform':'x','username':'onepiece_official','game':'원피스 카드','region':'JP','trusted':True,'verified_via_official_site':'https://one-piece.com/'}]}
        rows,errors,status=s.collect_x(reg)
        hit=next(x for x in rows if x['game']=='원피스 카드' and x['region']=='JP')
        assert not errors and status['configured'] is True
        assert hit['official_account_verified'] is True and hit['source_tier']=='A-social'
        assert hit['dates']==['2026-09-04']
    finally:
        s._x_request=old
        if old_token is None: os.environ.pop('X_BEARER_TOKEN',None)
        else: os.environ['X_BEARER_TOKEN']=old_token

def t_instagram_parse_official():
    old_token=os.environ.get('INSTAGRAM_ACCESS_TOKEN'); old_id=os.environ.get('INSTAGRAM_IG_USER_ID')
    os.environ['INSTAGRAM_ACCESS_TOKEN']='TOKEN'; os.environ['INSTAGRAM_IG_USER_ID']='999'
    old=s._instagram_request
    try:
        def fake(viewer,username,token):
            return {'ok':True,'payload':{'business_discovery':{'media':{'data':[{
                'caption':'포켓몬 영화 특별 이벤트 2026년 9월 20일',
                'permalink':'https://www.instagram.com/p/ABC123/','timestamp':'2026-08-28T00:00:00+0000','media_type':'IMAGE'}]}}}}
        s._instagram_request=fake
        reg={'accounts':[{'platform':'instagram','username':'pokemon_official','game':'포켓몬 카드','region':'KR','trusted':True,'verified_via_official_site':'https://www.pokemonkorea.co.kr/'}]}
        rows,errors,status=s.collect_instagram(reg)
        assert not errors and len(rows)==1 and rows[0]['official_account_verified'] is True
        assert rows[0]['category']=='movie' and rows[0]['dates']==['2026-09-20']
    finally:
        s._instagram_request=old
        if old_token is None: os.environ.pop('INSTAGRAM_ACCESS_TOKEN',None)
        else: os.environ['INSTAGRAM_ACCESS_TOKEN']=old_token
        if old_id is None: os.environ.pop('INSTAGRAM_IG_USER_ID',None)
        else: os.environ['INSTAGRAM_IG_USER_ID']=old_id

def t_google_news_parse():
    xml=b'''<?xml version="1.0"?><rss><channel><item><title>Pokemon collaboration event announced</title><link>https://news.google.com/rss/articles/abc</link><pubDate>Fri, 28 Aug 2026 01:00:00 GMT</pubDate><description>Movie collaboration event on 2026-09-18</description><source url="https://www.pokemon.com/">Pokemon</source></item></channel></rss>'''
    class Resp:
        def __enter__(self): return self
        def __exit__(self,*a): return False
        def read(self,n=-1): return xml[:n] if n>=0 else xml
        def geturl(self): return 'https://news.google.com/rss/search?q=x'
    old=s.safe_urlopen
    try:
        s.safe_urlopen=lambda *a,**k: Resp()
        rows,error=s._google_news_one('포켓몬 카드','US')
        assert error is None and len(rows)==1
        assert rows[0]['official_domain_match'] is True and rows[0]['source_tier']=='A-search'
        assert rows[0]['dates']==['2026-09-18']
    finally:
        s.safe_urlopen=old

def t_merge_crosscheck():
    a={'game':'나루토 카드','region':'US','category':'movie','title':'Naruto movie event 2026','source':'https://x.com/a/status/1','source_kind':'x','confidence':0.60,'verified':False}
    b={'game':'나루토 카드','region':'US','category':'movie','title':'Naruto movie event 2026','source':'https://news.google.com/rss/articles/2','source_kind':'google_news','confidence':0.65,'verified':False}
    rows=s.merge_candidates([a,b])
    assert len(rows)==1 and rows[0]['cross_checked'] is True
    assert rows[0]['independent_source_count']>=2 and rows[0]['confidence']>0.65

def t_optional_credentials():
    keep={k:os.environ.pop(k,None) for k in ('X_BEARER_TOKEN','INSTAGRAM_ACCESS_TOKEN','INSTAGRAM_IG_USER_ID','GOOGLE_CSE_API_KEY','GOOGLE_CSE_ID')}
    try:
        xr=s.collect_x({'accounts':[]}); ig=s.collect_instagram({'accounts':[]}); gc=s.collect_google_cse()
        assert xr[2]['configured'] is False and ig[2]['configured'] is False and gc[2]['configured'] is False
        assert not xr[1] and not ig[1] and not gc[1]
    finally:
        for k,v in keep.items():
            if v is not None: os.environ[k]=v

def t_ui_and_pipeline_contract():
    root=Path(__file__).resolve().parent
    idx=(root/'index.html').read_text(encoding='utf-8')
    pipe=(root/'auto_pipeline_runner.py').read_text(encoding='utf-8')
    sw=(root/'sw.js').read_text(encoding='utf-8')
    promo=(root/'update_promo_events.py').read_text(encoding='utf-8')
    assert 'social_event_candidates.json' in idx and 'normalizedSocialEventItems' in idx
    assert 'Instagram·X·Google News' in idx
    assert 'social_event_discovery.main()' in pipe and 'supplementary_discovery.main()' in pipe
    assert 'social_event_candidates.json' in sw
    assert 'social_candidate_count' in promo and '자동승격 금지' in promo


def t_pipeline_exec_once():
    import auto_pipeline_runner as a
    # run_pipeline() applies this hardening layer before it calls the
    # collectors. Apply it before installing test doubles as well; otherwise a
    # clean Python process replaces the mocked social collector during the
    # test and accidentally performs live collection.
    a.collection_learning_hardening_v142.apply()
    old_collector=a.MultiChannelCollector
    old_official=a._collect_official_sources
    old_supp=a.supplementary_discovery.main
    old_social=a.social_event_discovery.main
    old_diag=a.CrossPlatformSelfHealingEngine.diagnostics
    old_health=a.provider_health_learning.observe
    old_meta=a.collection_meta_learning.refresh_profile
    old_social_out=a.social_event_discovery.OUT
    old_out=a.OUT
    calls={'supp':0,'social':0}
    try:
        class Learner:
            def rank_results(self,keyword,rows,limit=30): return [dict(x,relevance_score=3.0) for x in rows][:limit]
            def learn_from_payload(self,payload,origin=''): return len(payload.get('items',[]))
            def learn_feedback_file(self): return 0
            def save(self): return None
            def report(self): return {'learned_queries':0,'learned_terms':0,'learned_hosts':0}
        class MethodLearner:
            def report(self): return {'providers':[]}
        class Collector:
            def __init__(self): self.learner=Learner();self.method_learner=MethodLearner()
            def search_web(self,k): return {'ok':True,'keyword':k,'results':[{'title':k,'url':'https://example.com/'+k,'verified':False}]}
        a.MultiChannelCollector=Collector
        a._collect_official_sources=lambda keywords:{provider:{key:{'ok':True,'degraded':False,'results':[],'errors':[]} for key in keywords} for provider in a.DIRECT_PROVIDER_ORDER}
        def supp(): calls['supp']+=1; return {'updated_at':'x','items':[{'title':'s'}]}
        def social(): calls['social']+=1; return {'updated_at':'x','items':[{'title':'x'}],'degraded':False,'official_social_candidate_count':1,'official_domain_search_count':0,'cross_checked_count':0,'channel_status':{}}
        a.supplementary_discovery.main=supp; a.social_event_discovery.main=social
        a.CrossPlatformSelfHealingEngine.diagnostics=lambda self:{'ok':True}
        a.provider_health_learning.observe=lambda rows:{'providers':[]}
        a.collection_meta_learning.refresh_profile=lambda:{'ok':True}
        with tempfile.TemporaryDirectory() as td:
            a.OUT=Path(td)/'out.json'
            a.social_event_discovery.OUT=Path(td)/'social.json'
            payload=a.run_pipeline()
            assert payload['ok'] is True and payload['degraded'] is False
            # Current pipeline merges one mocked social row with three mocked
            # adaptive web rows; exact count may grow as independent providers
            # are added, but both branches must execute once and remain healthy.
            assert payload['social']['candidate_count']>=1 and payload['social']['adaptive_merge_count']==3
            assert payload['supplementary']['candidate_count']==1
            assert calls=={'supp':1,'social':1}
            assert a.OUT.is_file()
    finally:
        a.MultiChannelCollector=old_collector;a._collect_official_sources=old_official
        a.supplementary_discovery.main=old_supp;a.social_event_discovery.main=old_social
        a.CrossPlatformSelfHealingEngine.diagnostics=old_diag;a.provider_health_learning.observe=old_health
        a.collection_meta_learning.refresh_profile=old_meta;a.social_event_discovery.OUT=old_social_out;a.OUT=old_out

def t_registry_official_link_only():
    # Parser rejects social action URLs and accepts only profile-like paths.
    assert s._parse_social_link('https://twitter.com/share?url=https://example.com') is None
    assert s._parse_social_link('https://instagram.com/explore/tags/pokemon') is None
    assert s._parse_social_link('https://youtube.com/channel/UC123456789') == ('youtube_channel','UC123456789')

for name,fn in [
    ('social_link_validation',t_social_links),('category_and_date_parser',t_category_dates),('x_query_bounded',t_x_query),
    ('secret_redaction',t_secret_redaction),('x_official_account_label',t_x_parse_official),('instagram_official_account_label',t_instagram_parse_official),
    ('google_news_official_domain',t_google_news_parse),('cross_source_merge',t_merge_crosscheck),('optional_credentials_no_failure',t_optional_credentials),
    ('ui_pipeline_contract',t_ui_and_pipeline_contract),('integration_exec_once',t_pipeline_exec_once),('registry_profile_link_filter',t_registry_official_link_only)
]: check(name,fn)

report={'version':'v105-social-google-event-discovery','ok':all(x['ok'] for x in checks),'successful':sum(x['ok'] for x in checks),'failed':sum(not x['ok'] for x in checks),'checks':checks}
print(json.dumps(report,ensure_ascii=False,indent=2))
raise SystemExit(0 if report['ok'] else 1)
