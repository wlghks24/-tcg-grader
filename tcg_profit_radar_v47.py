#!/usr/bin/env python3
"""Bounded, local-only incremental TCG market discovery across registry games.

Source: public TCGCSV/Tcgplayer *US marketplace* category/group/product/price
snapshots. These are NOT guaranteed live sale prices or evidence of arbitrage.
No images are downloaded or published; existing private photo library is intact.
SQLite is stored outside GitHub. No paid API, login, or bypass of 403/429.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.error import HTTPError,URLError
import json,os,re,sqlite3,tempfile,threading,time,urllib.request
import math

VERSION=47
ROOT='https://tcgcsv.com/tcgplayer'
MAX_RESPONSE=6*1024*1024
MAX_SOURCE_GAMES=3
GROUPS_PER_GAME=2
MAX_REQUESTS=16
MAX_DB_BYTES=120*1024*1024
MIN_INTERVAL=6*3600
CACHE_TTL=24*3600
RUN_DELAY=90
MAX_RESULTS=120
LOCK=threading.RLock()
# Only exact, disambiguated TCGplayer category names. A US *marketplace* record
# is NOT proof that a card was printed for the US edition.
CATEGORY_ALIASES={
 'pokemon':('Pokemon',), 'onepiece':('One Piece Card Game','One Piece'),
 'gundam':('Gundam Card Game',), 'unionarena':('Union Arena',),
 'dbsfw':('Dragon Ball Super: Fusion World','Dragon Ball Super Fusion World'),
 'lorcana':('Disney Lorcana','Lorcana'), 'swu':('Star Wars: Unlimited','Star Wars Unlimited'),
 'riftbound':('Riftbound','Riftbound: League of Legends'), 'mtg':('Magic',),
 'yugioh':('YuGiOh',), 'digimon':('Digimon Card Game','Digimon'),
 'flesh-and-blood':('Flesh and Blood',), 'weiss-schwarz':('Weiss Schwarz',),
 'cardfight-vanguard':('Cardfight Vanguard',), 'hololive-ocg':('hololive OCG',),
 'shadowverse-evolve':('Shadowverse Evolve',), 'grand-archive':('Grand Archive',),
 'final-fantasy-tcg':('Final Fantasy TCG',),
 'sorcery-contested-realm':('Sorcery: Contested Realm',),
 'godzilla-card-game':('Godzilla Card Game',),
 'palworld-ocg':('Palworld Official Card Game',),
 'cyberpunk-tcg':('Cyberpunk 2077 Trading Card Game',),
 'elestrals':('Elestrals',), 'rush-of-ikorr':('Rush of Ikorr',),
 'cookierun-braverse':('CookieRun: Braverse','CookieRun Braverse'),
 'universus':('UniVersus',), 'alpha-clash':('Alpha Clash',),
 'metazoo':('MetaZoo',), 'wixoss':('WIXOSS',),
}

class RadarError(ValueError):pass


def local_root():
    # SQLite *outside public GitHub tree*; no user photos copied.
    p=(Path.home()/'.local'/'share').resolve()
    p.mkdir(parents=True,exist_ok=True)
    p=p/'TCG_Profit_Radar'
    if p.is_symlink():raise RadarError('심볼릭 링크 저장소 차단')
    p.mkdir(mode=0o700,exist_ok=True)
    return p


def _json_read(path,default,limit=1_500_000):
    if not path.exists():return default
    if path.is_symlink() or not path.is_file() or path.stat().st_size>limit:raise RadarError('로컬 상태 파일 형식/크기 오류')
    return json.loads(path.read_text(encoding='utf-8'))


def _atomic_json(path,data):
    out=json.dumps(data,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    if len(out)>1_500_000:raise RadarError('수집 상태 파일 제한 초과')
    fd,tmp=tempfile.mkstemp(prefix='.radar-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(out);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def _norm(v):return re.sub(r'[^a-z0-9]+','',str(v or '').casefold())


def _safe_url(value,allowed):
    if not isinstance(value,str) or len(value)>750:return ''
    try:
        u=urlsplit(value)
        if u.scheme!='https' or u.hostname not in allowed or u.username or u.password or u.port not in (None,443):return ''
    except ValueError:return ''
    return value


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise RadarError('외부 주소 변경/리다이렉트 차단')


def fetch_json(url):
    if not _safe_url(url,{'tcgcsv.com'}):raise RadarError('미허용 API 주소')
    req=urllib.request.Request(url,headers={'User-Agent':'TCG-Local-Research/1.0 (individual use; bounded requests)','Accept':'application/json'})
    try:
        with urllib.request.build_opener(NoRedirect()).open(req,timeout=12) as response:
            if response.status!=200:raise RadarError('HTTP '+str(response.status))
            ct=response.headers.get('Content-Type','').lower()
            if 'json' not in ct:raise RadarError('JSON 아닌 API 응답')
            buf=response.read(MAX_RESPONSE+1)
            if len(buf)>MAX_RESPONSE:raise RadarError('원격 응답 용량 제한')
            d=json.loads(buf.decode('utf-8'))
            if not isinstance(d,dict) or d.get('success') is not True or not isinstance(d.get('results'),list):
                raise RadarError('API 결과 형식 불일치')
            return d['results']
    except HTTPError as e:raise RadarError('HTTP '+str(e.code)) from e
    except (URLError,TimeoutError,OSError,UnicodeError,ValueError) as e:raise RadarError('연결/형식 오류: '+type(e).__name__) from e


def _schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS catalog (
      category_id INTEGER NOT NULL, product_id INTEGER NOT NULL, variant TEXT NOT NULL,
      game_id TEXT NOT NULL, group_id INTEGER NOT NULL, set_name TEXT NOT NULL,
      name TEXT NOT NULL, kind TEXT NOT NULL, rarity TEXT NOT NULL,
      market_price REAL, low_price REAL, high_price REAL,
      product_url TEXT NOT NULL, image_url TEXT NOT NULL,
      observed_at TEXT NOT NULL, PRIMARY KEY(category_id,product_id,variant))''')
    conn.execute('CREATE INDEX IF NOT EXISTS radar_lookup ON catalog(game_id,kind,market_price DESC)')
    conn.execute('CREATE INDEX IF NOT EXISTS radar_recent ON catalog(observed_at)')


def _db(root):
    target=root/'radar_v47.sqlite3'
    if target.is_symlink() or target.exists() and target.stat().st_size>MAX_DB_BYTES:
        raise RadarError('로컬 수집 DB 용량/경로 제한')
    conn=sqlite3.connect(target,timeout=10)
    conn.execute('PRAGMA journal_mode=DELETE')
    conn.execute('PRAGMA busy_timeout=5000')
    _schema(conn)
    return conn


def _kind(name):
    t=name.casefold()
    if re.search(r'\b(?:booster box|booster display|collector chest)\s*case\b',t):return 'BUNDLE'
    if re.search(r'\b(?:sealed|booster|display)\s*box\b|\b(?:booster box|etb|elite trainer box|collector box)\b',t):return 'BOX'
    if re.search(r'\b(?:booster|sleeved)\s*pack\b|\bblister\b',t):return 'PACK'
    if re.search(r'\b(?:collection|gift|premium|anniversary)\s*(?:box|set|collection)\b|\b(?:tin|bundle|chest)\b',t):return 'COLLECTION'
    if re.search(r'\b(?:starter|structure|theme|trial|commander)\s*deck\b',t):return 'DECK'
    if re.search(r'\b(?:sleeve|playmat|binder|deck case|card case)\b',t):return 'ACCESSORY'
    if re.search(r'\b(?:booster|display)\s*(?:case)\b',t):return 'BUNDLE'
    if re.search(r'\b(?:promo|promotional|prize card|tournament winner)\b',t):return 'PROMO'
    return 'CARD'


def _number(v):
    if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0 or v>1_000_000:return None
    return round(float(v),4)


def _text(v,maxlen=130):
    if not isinstance(v,str):return ''
    return ''.join(x for x in v.strip()[:maxlen] if ord(x)>=32)


def _variant(v):
    return _text(v,90) or 'Unspecified'


def _aliases(repo):
    reg=_json_read(repo/'tcg_game_registry.json',{},1_000_000)
    games=reg.get('games',[]) if isinstance(reg,dict) else []
    return [g['id'] for g in games if isinstance(g,dict) and isinstance(g.get('id'),str) and re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}',g['id'])]


def _state(root):
    st=_json_read(root/'radar_state_v47.json',{})
    if not isinstance(st,dict):raise RadarError('상태 파일 형식 오류')
    return st


def _match_categories(categories,registered):
    names={_norm(x.get('name')):int(x['categoryId']) for x in categories if isinstance(x,dict) and isinstance(x.get('categoryId'),int) and isinstance(x.get('name'),str) and x['categoryId']>0}
    results={}
    for game in registered:
        hits={names[_norm(alias)] for alias in CATEGORY_ALIASES.get(game,()) if _norm(alias) in names}
        if len(hits)==1:results[game]=next(iter(hits))
    return results


def _groups(rows):
    valid=[]
    for r in rows:
        if not isinstance(r,dict):continue
        gid=r.get('groupId')
        if not isinstance(gid,int) or isinstance(gid,bool) or gid<=0:continue
        valid.append({'id':gid,'name':_text(r.get('name'),120),'date':_text(r.get('publishedOn'),35)})
    return sorted(valid,key=lambda r:(r['date'],r['id']),reverse=True)[:2500]


def _product_rows(category,game,group,products,prices,when):
    pricing={};by_pid={}
    for p in prices[:10000]:
        if not isinstance(p,dict):continue
        pid=p.get('productId')
        if not isinstance(pid,int) or isinstance(pid,bool) or pid<=0:continue
        v=_variant(p.get('subTypeName'))
        pricing[(pid,v)]=p
        by_pid.setdefault(pid,[]).append((v,p))
    result=[]
    for p in products[:10000]:
        if not isinstance(p,dict):continue
        pid=p.get('productId')
        if not isinstance(pid,int) or isinstance(pid,bool) or pid<=0:continue
        title=_text(p.get('name'))
        if not title or re.search(r'\b(?:code card|digital code|online code)\b',title,re.I):continue
        kind=_kind(title)
        details=p.get('extendedData')
        rarity=''
        if isinstance(details,list):
            for d in details[:40]:
                if isinstance(d,dict) and _norm(d.get('name'))=='rarity':rarity=_text(d.get('value'),45)
        elif isinstance(details,dict):rarity=_text(details.get('Rarity') or details.get('rarity'),45)
        product_url=_safe_url(p.get('url'),{'www.tcgplayer.com','tcgplayer.com'})
        image_url=_safe_url(p.get('imageUrl'),{'tcgplayer-cdn.tcgplayer.com','product-images.tcgplayer.com'})
        variants=by_pid.get(pid,[])
        if not variants:variants=[('Unspecified',{})]
        for variant,row in variants:
            result.append((category,pid,variant,game,group['id'],group['name'],title,kind,rarity,
                           _number(row.get('marketPrice')),_number(row.get('lowPrice')),_number(row.get('highPrice')),
                           product_url,image_url,when))
    return result


def _run(repo,root,get_json,sleep):
    repo=Path(repo).resolve();root=Path(root)
    st=_state(root); registered=_aliases(repo)
    if not registered:raise RadarError('게임 레지스트리 자료 없음')
    now=time.time();stat={'new_rows':0,'updated_rows':0,'groups':0,'requests':0,'errors':[],
                          'last_run_utc':datetime.now(timezone.utc).isoformat(),'finished':False,'source':'TCGCSV','market_scope':'US_MARKET_ONLY'}
    cats=st.get('categories') if now-float(st.get('categories_epoch',0))<CACHE_TTL else None
    if not isinstance(cats,list):
        cats=get_json(ROOT+'/categories');stat['requests']+=1
        st['categories']=cats[:200];st['categories_epoch']=now
    mapped=_match_categories(cats,registered)
    stat['games_mapped']=len(mapped);stat['games_unmapped']=sorted(set(registered)-set(mapped))
    available=sorted(mapped)
    if not available:raise RadarError('게임 카테고리 연결 0건 (안전 중단)')
    start=int(st.get('game_cursor',0))%len(available)
    selected=[available[(start+i)%len(available)] for i in range(min(MAX_SOURCE_GAMES,len(available)))]
    st['game_cursor']=(start+len(selected))%len(available)
    caches=st.setdefault('groups_cache',{})
    indices=st.setdefault('group_cursors',{})
    conn=_db(root)
    try:
        for game in selected:
            cat=mapped[game];key=str(cat)
            cache=caches.get(key,{})
            groups=cache.get('rows') if isinstance(cache,dict) and now-float(cache.get('epoch',0))<CACHE_TTL else None
            if not isinstance(groups,list):
                groups=_groups(get_json(f'{ROOT}/{cat}/groups'))
                stat['requests']+=1
                caches[key]={'epoch':now,'rows':groups}
            if not groups:continue
            cursor=int(indices.get(key,0))%len(groups)
            for i in range(min(GROUPS_PER_GAME,len(groups))):
                if stat['requests']+2>MAX_REQUESTS:break
                group=groups[(cursor+i)%len(groups)]
                pid=group['id']
                try:
                    prods=get_json(f'{ROOT}/{cat}/{pid}/products');stat['requests']+=1
                    prices=get_json(f'{ROOT}/{cat}/{pid}/prices');stat['requests']+=1
                    rows=_product_rows(cat,game,group,prods,prices,stat['last_run_utc'])
                    with conn:
                        for row in rows:
                            existed=conn.execute('SELECT 1 FROM catalog WHERE category_id=? AND product_id=? AND variant=?',row[:3]).fetchone()
                            conn.execute('''INSERT INTO catalog VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                                ON CONFLICT(category_id,product_id,variant) DO UPDATE SET
                                game_id=excluded.game_id,group_id=excluded.group_id,set_name=excluded.set_name,
                                name=excluded.name,kind=excluded.kind,rarity=excluded.rarity,market_price=excluded.market_price,
                                low_price=excluded.low_price,high_price=excluded.high_price,
                                product_url=excluded.product_url,image_url=excluded.image_url,observed_at=excluded.observed_at''',row)
                            stat['updated_rows' if existed else 'new_rows']+=1
                    stat['groups']+=1
                except RadarError as e:
                    stat['errors'].append(f'{game}/{pid}: {e}'[:140])
                    if any(b in str(e) for b in ('HTTP 403','HTTP 429','HTTP 503')):
                        st['blocked_until']=now+24*3600
                        stat['errors'].append('차단/과부하 응답: 24시간 자동 대기')
                        break
                if stat['errors'] and st.get('blocked_until',0)>now:break
                sleep(1.0)
            # Do not skip a failed group after 403/429.
            if st.get('blocked_until',0)>now:break
            indices[key]=(cursor+min(GROUPS_PER_GAME,len(groups)))%len(groups)
        stat['finished']=True
        st['last_run_epoch']=now;st['last_result']=stat
        # trim source group cache if too large (don't remove DB rows)
        if len(caches)>3:
            for k in list(caches)[:-3]:del caches[k]
        _atomic_json(root/'radar_state_v47.json',st)
        return stat
    finally:conn.close()


def run_once(repo,root=None,get_json=fetch_json,sleep=time.sleep):
    with LOCK:
        root=Path(root) if root is not None else local_root()
        root.mkdir(parents=True,exist_ok=True)
        st=_state(root)
        if st.get('blocked_until',0)>time.time():
            return {'ok':False,'paused':True,'reason':'API 차단/과부하 대기 중'}
        try:
            return {'ok':True,**_run(repo,root,get_json,sleep)}
        except RadarError as exc:
            if any(s in str(exc) for s in ('HTTP 403','HTTP 429','HTTP 503')):
                st['blocked_until']=time.time()+24*3600
                st['last_result']={'errors':[str(exc)],'last_run_utc':datetime.now(timezone.utc).isoformat(),'groups':0,'requests':0}
                _atomic_json(root/'radar_state_v47.json',st)
            raise


def read(repo,root=None,game='',kind='',limit=MAX_RESULTS):
    root=Path(root) if root is not None else local_root()
    st=_state(root); registered=_aliases(Path(repo))
    if game and game not in registered:raise RadarError('미등록 게임 검색 차단')
    if kind and kind not in ('CARD','PROMO','BOX','PACK','COLLECTION','DECK','ACCESSORY','BUNDLE'):raise RadarError('상품종류 검색 오류')
    limit=max(1,min(int(limit),MAX_RESULTS))
    db=root/'radar_v47.sqlite3'
    if not db.is_file():
        return {'ok':True,'version':VERSION,'items':[],'summary':{'total':0,'with_market_price':0,'candidate_count':0,'registered_games':len(registered),
               'source_games_mapped':0,'status':'WAITING_FIRST_SCAN'},
               'last_run':st.get('last_result'),'disclaimer':'시장가격은 실현 수익을 보증하지 않습니다.'}
    conn=_db(root)
    try:
        clauses=[];params=[]
        if game:clauses.append('game_id=?');params.append(game)
        if kind:clauses.append('kind=?');params.append(kind)
        where=(' WHERE '+' AND '.join(clauses)) if clauses else ''
        # Any low/market comparison is a *screening spread*, not actionable profit.
        base='''SELECT category_id,product_id,variant,game_id,group_id,set_name,name,kind,rarity,
                market_price,low_price,high_price,product_url,image_url,observed_at FROM catalog'''
        total=conn.execute('SELECT COUNT(*) FROM catalog'+where,params).fetchone()[0]
        priced=conn.execute('SELECT COUNT(*) FROM catalog'+where+(' AND ' if where else ' WHERE ')+ 'market_price IS NOT NULL',params).fetchone()[0]
        # Market price threshold only. No fabricated earnings/profitability labels.
        rows=conn.execute(base+where+' ORDER BY CASE WHEN market_price>=10 THEN 0 ELSE 1 END, market_price DESC,observed_at DESC LIMIT ?',(*params,limit)).fetchall()
        cutoff=datetime.now(timezone.utc).timestamp()-3*86400
        fields=('category_id','product_id','variant','game_id','group_id','series','name','kind','rarity',
                'market_price_usd','low_listing_usd','high_listing_usd','source_url','image_url','checked_at')
        items=[];spread_count=0
        for row in rows:
            item=dict(zip(fields,row))
            # No guarantee that lowest listing is purchasable; don't call this net profit.
            low=item['low_listing_usd'];mp=item['market_price_usd']
            gap=round(mp*0.87-low-5,2) if mp and low is not None and low>0 else None
            item['preliminary_spread_usd']=gap
            item['signal']='PRICE_GAP_REVIEW' if gap is not None and gap>=10 else 'MARKET_VALUE_ONLY' if mp else 'METADATA_ONLY'
            item['market_region']='US';item['printing_region']='UNVERIFIED'
            item['verified_profit']=False
            item['hit_candidate']=bool(item['kind'] in ('CARD','PROMO') and mp is not None and mp>=40 and any(word in str(item['rarity']).casefold() for word in ('secret','manga','illustration','parallel','ultra','promo','special','legend','rare')))
            try:ts=datetime.fromisoformat(item['checked_at']).timestamp()
            except (ValueError,TypeError):ts=0
            item['stale']=ts<cutoff
            if item['signal']=='PRICE_GAP_REVIEW':spread_count+=1
            items.append(item)
        return {'ok':True,'version':VERSION,'items':items,
                'summary':{'total':total,'with_market_price':priced,'shown_gap_candidates':spread_count,
                           'registered_games':len(registered),'source_games_mapped':(st.get('last_result') or {}).get('games_mapped',0),
                           'status':'ACTIVE','unsupported_games':(st.get('last_result') or {}).get('games_unmapped',[])},
                'last_run':st.get('last_result'),
                'disclaimer':'미국 시장가격/최저 호가는 실제 매입가나 체결가가 아닙니다. 차익 추정은 세금·추가 비용·판매완료/재고를 검증하지 않았습니다. 구매 추천이 아닙니다.'}
    finally:conn.close()

_STARTED=False
_STOP=threading.Event()
def start_scheduler(repo):
    global _STARTED
    with LOCK:
        if _STARTED:return
        _STARTED=True
    def loop():
        if _STOP.wait(RUN_DELAY):return
        while not _STOP.is_set():
            try:
                root=local_root();st=_state(root)
                if time.time()-float(st.get('last_run_epoch',0))>=MIN_INTERVAL and st.get('blocked_until',0)<=time.time():
                    run_once(repo,root)
            except (OSError,RadarError,ValueError,sqlite3.Error) as e:
                # Nonfatal: never break core TCG app on loss of optional data feed.
                print('[안내] 투자후보 수집 보류:',type(e).__name__,flush=True)
            if _STOP.wait(1800):break
    threading.Thread(target=loop,name='tcg-profit-radar-v47',daemon=True).start()
    print('[OK] 30종 등록게임 대상 무료 시장상품·시세 순환탐색 준비 (미국 시장, 6시간 간격)',flush=True)
