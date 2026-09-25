#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, quote_plus, urlencode, urlparse
from urllib.request import Request
from html import unescape
from xml.etree import ElementTree as ET
import json, os, re, statistics, time

from safe_runtime import diagnostic_exception, safe_urlopen

BASE=Path(__file__).resolve().parent
CACHE=BASE/'multi_market_price_cache.json'
LEARNING=BASE/'multi_market_source_learning.json'
FX=BASE/'exchange_rates.json'
CACHE_TTL=15*60
UA='Mozilla/5.0 TCG-Grader/1.0'

SOURCES=[
 {'id':'ebay','name':'eBay','domain':'ebay.com','weight':0.95,'kind':'글로벌 마켓'},
 {'id':'amazon_us','name':'Amazon US','domain':'amazon.com','weight':0.72,'kind':'판매가'},
 {'id':'amazon_jp','name':'Amazon JP','domain':'amazon.co.jp','weight':0.75,'kind':'판매가'},
 {'id':'kream','name':'KREAM','domain':'kream.co.kr','weight':0.92,'kind':'국내 거래/호가'},
 {'id':'daangn','name':'당근','domain':'daangn.com','weight':0.76,'kind':'지역 중고'},
 {'id':'bunjang','name':'번개장터','domain':'bunjang.co.kr','weight':0.82,'kind':'국내 중고'},
 {'id':'joongna','name':'중고나라','domain':'joongna.com','weight':0.80,'kind':'국내 중고'},
 {'id':'collectory','name':'Collectory','domain':'collectory.cc','weight':0.90,'kind':'카드시세'},
 {'id':'tcgplayer','name':'TCGplayer','domain':'tcgplayer.com','weight':0.88,'kind':'TCG 마켓'},
 {'id':'cardmarket','name':'Cardmarket','domain':'cardmarket.com','weight':0.86,'kind':'유럽 TCG'},
 {'id':'mercari_jp','name':'Mercari JP','domain':'jp.mercari.com','weight':0.84,'kind':'일본 중고'},
 {'id':'yahoo_jp','name':'Yahoo! Auctions JP','domain':'auctions.yahoo.co.jp','weight':0.82,'kind':'일본 경매'},
 {'id':'snkrdunk','name':'SNKRDUNK','domain':'snkrdunk.com','weight':0.91,'kind':'일본 TCG 참고시세'},
 {'id':'justtcg','name':'JustTCG','domain':'justtcg.com','weight':0.91,'kind':'TCG 가격 API 참고'},
 {'id':'tcgdex','name':'TCGdex','domain':'tcgdex.net','weight':0.89,'kind':'포켓몬 가격 API 참고'},
 {'id':'pavilion','name':'Pavilion TCG','domain':'pavilion-tcg.com','weight':0.90,'kind':'통합 참고시세'},
]

PRICE_PATTERNS=[
 ('KRW',re.compile(r'(?:₩\s*|KRW\s*)([0-9][0-9,]{2,})',re.I)),
 ('KRW',re.compile(r'([0-9][0-9,]{2,})\s*원')),
 ('JPY',re.compile(r'(?:¥|￥|JPY\s*)([0-9][0-9,]{2,})',re.I)),
 ('USD',re.compile(r'(?:US\s*)?\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)',re.I)),
]

SOLD_WORDS=('sold','completed','판매완료','거래완료','낙찰','체결')

def _safe_json(path,default):
    try:
        value=json.loads(Path(path).read_text(encoding='utf-8'))
        return value if isinstance(value,type(default)) else default
    except Exception:return default

def _atomic(path,data):
    try:
        tmp=Path(str(path)+'.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(path)
    except Exception:pass

def _fx():
    d=_safe_json(FX,{})
    rates=d.get('rates') if isinstance(d,dict) else {}
    return {'USD':float((rates or {}).get('USD_KRW') or 0),'JPY':float((rates or {}).get('JPY_KRW') or 0),
            'EUR':float((rates or {}).get('EUR_KRW') or 0),'KRW':1.0}

def _to_krw(amount,currency,fx):
    rate=fx.get(currency,0)
    return int(round(float(amount)*rate)) if rate and amount else 0

def _extract_price(text,fx):
    """Choose the most price-like amount instead of blindly taking the maximum.

    Search snippets frequently contain MSRP, shipping, discount, coupon or bundle
    amounts next to the actual market/transaction price.  Ranking by amount alone
    biases the result upward and can turn unrelated values into "current price".
    """
    raw=str(text or '')
    values=[]
    positive=('sold','completed','market price','current price','price','거래가','체결가','현재가','시세','판매가','낙찰가')
    negative=('shipping','ship ','delivery','tax','coupon','discount','save ','msrp','list price','retail price','배송','택배','쿠폰','할인','정가','출시가')
    for currency,pat in PRICE_PATTERNS:
        for m in pat.finditer(raw):
            try:a=float(m.group(1).replace(',',''))
            except Exception:continue
            krw=_to_krw(a,currency,fx)
            if not (100<=krw<=100_000_000):continue
            low=raw.lower()
            center=(m.start()+m.end())//2
            left=max(0,m.start()-64);right=min(len(raw),m.end()+64)
            nearby=low[left:right]
            score=0
            # Attribute labels to the nearest amount. A flat "keyword exists in
            # 48 chars" score lets an adjacent MSRP label contaminate the real
            # current price (and vice versa).
            for word in positive:
                start=0
                while True:
                    pos=nearby.find(word,start)
                    if pos<0:break
                    absolute=left+pos+len(word)//2
                    score+=max(1,80-min(79,abs(center-absolute)))
                    start=pos+len(word)
            for word in negative:
                start=0
                while True:
                    pos=nearby.find(word,start)
                    if pos<0:break
                    absolute=left+pos+len(word)//2
                    score-=max(1,100-min(99,abs(center-absolute)))
                    start=pos+len(word)
            values.append((score,m.start(),krw,a,currency))
    if not values:return None
    # Highest semantic score wins; on a tie prefer the first explicit amount,
    # which avoids the previous "largest number always wins" inflation bias.
    _,_,krw,a,c=max(values,key=lambda x:(x[0],-x[1]))
    return {'price_krw':krw,'price_native':a,'currency':c}

def _rss(query,limit=8):
    url='https://www.bing.com/search?format=rss&q='+quote_plus(query)
    req=Request(url,headers={'User-Agent':UA,'Accept-Language':'ko-KR,ko;q=0.9,en;q=0.7,ja;q=0.5'})
    with safe_urlopen(req,timeout=12,allowed_hosts={'www.bing.com','bing.com'}) as r: raw=r.read(1_500_000)
    root=ET.fromstring(raw)
    out=[]
    for item in root.findall('.//item')[:limit]:
        title=unescape(item.findtext('title') or '').strip()
        link=(item.findtext('link') or '').strip()
        desc=re.sub(r'<[^>]+>',' ',unescape(item.findtext('description') or ''))
        desc=re.sub(r'\s+',' ',desc).strip()
        date=(item.findtext('pubDate') or '').strip()
        out.append({'title':title[:240],'url':link[:800],'snippet':desc[:600],'date':date[:80]})
    return out

def _region_query_term(region):
    region=str(region or 'ALL').upper()
    return {'KR':'Korean 한국판','JP':'Japanese 일본판','US':'English'}.get(region,'')

def _ebay_api(query,region,fx):
    token=os.environ.get('EBAY_OAUTH_TOKEN','').strip()
    if not token:return []
    # Region means card edition/language in this UI, not seller geography.
    # eBay Browse is queried through EBAY_US, so scope the text query instead
    # of pretending that an EBAY_JP marketplace exists.
    region_term=_region_query_term(region)
    scoped_query=(str(query).strip()+' '+region_term).strip()
    marketplace='EBAY_US'
    url='https://api.ebay.com/buy/browse/v1/item_summary/search?q='+quote_plus(scoped_query)+'&limit=20'
    req=Request(url,headers={'Authorization':'Bearer '+token,'X-EBAY-C-MARKETPLACE-ID':marketplace,'User-Agent':UA})
    with safe_urlopen(req,timeout=15,allowed_hosts={'api.ebay.com'}) as r:d=json.loads(r.read(2_000_000).decode('utf-8','ignore'))
    rows=[]
    for x in (d.get('itemSummaries') or []):
        p=x.get('price') or {};cur=str(p.get('currency') or 'USD').upper()
        try:amt=float(p.get('value'))
        except Exception:continue
        krw=_to_krw(amt,cur,fx)
        if not krw:continue
        rows.append({'source':'eBay','source_id':'ebay','title':str(x.get('title') or '')[:240],'url':str(x.get('itemWebUrl') or '')[:800],
                     'price_krw':krw,'price_native':amt,'currency':cur,'price_kind':'판매중','verified_api':True,'date':''})
    return rows

def _game_key(game):
    value=str(game or '').strip().lower().replace('é','e')
    if 'pokemon' in value or '포켓몬' in value:return 'pokemon'
    if 'one piece' in value or '원피스' in value:return 'onepiece'
    if 'naruto' in value or '나루토' in value:return 'naruto'
    return 'all'

def _pavilion_url(query,game):
    game_id={'pokemon':'1','onepiece':'2'}.get(_game_key(game))
    params={'language':'ko','q':query}
    if game_id:params={'gameId':game_id,**params}
    return 'https://pavilion-tcg.com/search?'+urlencode(params)

def _reference_links(query,game):
    key=_game_key(game)
    links=[]
    if key in ('pokemon','onepiece','all'):
        links.append({'source':'Pavilion TCG','source_id':'pavilion','label':'Pavilion 등급별 통합 참고시세',
                      'detail':'SNKRDUNK · JustTCG · TCGdex 참고값을 원문에서 교차확인',
                      'url':_pavilion_url(query,game),'supports_grade_prices':True})
    snkr={'pokemon':'https://snkrdunk.com/en/brands/pokemon/trading-cards?categoryId=25',
          'onepiece':'https://snkrdunk.com/en/brands/onepiece/trading-cards?categoryId=14'}.get(key)
    if snkr:links.append({'source':'SNKRDUNK','source_id':'snkrdunk','label':'SNKRDUNK 원문시세 확인','detail':'일본 판매·거래 참고','url':snkr})
    links.append({'source':'JustTCG','source_id':'justtcg','label':'JustTCG 가격 API 안내','detail':'서버 API 키가 있을 때 자동조회','url':'https://justtcg.com/docs/quickstart'})
    if key in ('pokemon','all'):
        links.append({'source':'TCGdex','source_id':'tcgdex','label':'TCGdex 포켓몬 가격정보','detail':'TCGplayer·Cardmarket 가격 API 참고','url':'https://tcgdex.dev/markets-prices'})
    return links

def _json_request(url,headers,allowed_hosts,max_bytes=2_000_000,timeout=15):
    req=Request(url,headers={**headers,'User-Agent':UA,'Accept':'application/json'})
    with safe_urlopen(req,timeout=timeout,allowed_hosts=set(allowed_hosts)) as response:
        raw=response.read(max_bytes+1)
    if len(raw)>max_bytes:raise ValueError('response exceeds safe size limit')
    return json.loads(raw.decode('utf-8','strict'))


def _normalize_card_number(value):
    """Canonicalize a card number without turning substring overlap into identity."""
    text=str(value or '').upper().strip().replace('–','-').replace('—','-')
    text=re.sub(r'\s+','',text)
    text=re.sub(r'[^A-Z0-9/-]','',text)
    suffix=re.fullmatch(r'(\d{1,3})/(SV-P|S-P|SM-P|XY-P|BW-P|DP-P|M-P)',text)
    if suffix:return f"{suffix.group(2)}{int(suffix.group(1)):03d}"
    prefix=re.fullmatch(r'(SV-P|S-P|SM-P|XY-P|BW-P|DP-P|M-P)-?(\d{1,3})',text)
    if prefix:return f"{prefix.group(1)}{int(prefix.group(2)):03d}"
    english=re.fullmatch(r'(SWSH|SVP|MEP)-?(\d{1,3})',text)
    if english:return f"{english.group(1)}{int(english.group(2)):03d}"
    return text


def _has_explicit_set_prefix(value):
    token=_normalize_card_number(value)
    if not token:return False
    if re.match(r'^[A-Z]{1,6}\d{0,3}-',token):return True
    # Modern EN codes such as SVI001 or MEW025 carry a set prefix even without '-'.
    return bool(re.match(r'^[A-Z]{2,6}\d',token))


def _local_card_number(value):
    token=_normalize_card_number(value)
    if not token:return ''
    fraction=re.search(r'([A-Z]?\d{1,4}/[A-Z]?\d{1,4})$',token)
    if fraction:return fraction.group(1)
    if '-' in token:
        tail=token.rsplit('-',1)[-1]
        if re.fullmatch(r'[A-Z]?\d{1,4}',tail):return tail
    simple=re.fullmatch(r'[A-Z]?\d{1,4}',token)
    return simple.group(0) if simple else token


def _card_number_matches(wanted, actual):
    """Fail closed on explicit set numbers; local-only queries compare exact local IDs."""
    wanted_token=_normalize_card_number(wanted)
    actual_token=_normalize_card_number(actual)
    if not wanted_token or not actual_token:return False
    if wanted_token==actual_token:return True
    if _has_explicit_set_prefix(wanted_token):return False
    return _local_card_number(wanted_token)==_local_card_number(actual_token)

def _justtcg_api(query,game,fx,region='ALL'):
    token=os.environ.get('JUSTTCG_API_KEY','').strip()
    if not token:return [],'not_configured'
    if str(region or 'ALL').upper() not in ('ALL','US'):
        # JustTCG's USD reference feed must not be presented as KR/JP-edition
        # evidence merely because the card identity happens to match.
        return [],'region_unsupported'
    game_name={'pokemon':'Pokemon','onepiece':'One Piece'}.get(_game_key(game))
    if not game_name:return [],'unsupported'
    params={'query':query,'game':game_name,'limit':'12','include_statistics':'30d','include_null_prices':'false'}
    data=_json_request('https://api.justtcg.com/v1/cards?'+urlencode(params),{'x-api-key':token},{'api.justtcg.com'})
    rows=[]
    for card in (data.get('data') or [])[:12] if isinstance(data,dict) else []:
        if not isinstance(card,dict):continue
        _,wanted_number=_tcgdex_query_parts(query)
        if wanted_number and not _card_number_matches(wanted_number, card.get('number')):
            continue
        variants=card.get('variants') or []
        priced=[v for v in variants if isinstance(v,dict) and isinstance(v.get('price'),(int,float)) and v.get('price',0)>0]
        # Never select the most expensive variant as the card's representative
        # price. Preserve each condition/printing as a separate comparable row.
        for variant in priced[:8]:
            amount=float(variant['price']);krw=_to_krw(amount,'USD',fx)
            if not krw:continue
            title=' · '.join(x for x in [str(card.get('name') or ''),str(card.get('number') or ''),str(variant.get('condition') or ''),str(variant.get('printing') or '')] if x)
            updated=variant.get('lastUpdated');date=''
            try:date=datetime.fromtimestamp(int(updated),timezone.utc).isoformat(timespec='seconds') if updated else ''
            except (TypeError,ValueError,OverflowError,OSError):pass
            rows.append({'source':'JustTCG','source_id':'justtcg','title':title[:240],'url':'https://justtcg.com/',
                         'price_krw':krw,'price_native':amount,'currency':'USD','price_kind':'API 현재가',
                         'verified_api':True,'date':date,'score':0.98,'card_number':str(card.get('number') or '')[:60],
                         'condition':str(variant.get('condition') or '')[:80],
                         'printing':str(variant.get('printing') or '')[:80],
                         'region_scope':'US'})
    return rows[:24],'ok'

CARD_NUMBER_QUERY_RE=re.compile(
    r'(?<![A-Z0-9])(?:'
    r'\d{1,3}/(?:SV-P|S-P|SM-P|XY-P|BW-P|DP-P|M-P)'
    r'|(?:SV-P|S-P|SM-P|XY-P|BW-P|DP-P|M-P)\s*\d{1,3}'
    r'|(?:SWSH|SVP|MEP)\s*-?\s*\d{1,3}'
    r'|(?:SVI|PAL|OBF|MEW|PAR|PAF|TEF|TWM|SFA|SCR|SSP|PRE|JTG|DRI|BLK|WHT|MEG|PFL|ASC|POR|CRI|PBL)\s*-?\s*\d{1,4}(?:/\d{2,4})?'
    r'|[A-Z]{1,4}\d{1,3}[A-Z]{0,2}-?\d{1,4}(?:/\d{2,4})?'
    r'|\d{1,4}/\d{2,4}'
    r'|\d{1,4}'
    r')(?![A-Z0-9])',re.I
)
GRADER_QUERY_RE=re.compile(
    r'\b(?:PSA|BGS|CGC|TAG|BRG)\s*[:#-]?\s*(?:10|[1-9])(?:\s*\.\s*(?:0|5))?(?:\s*BLACK\s*LABEL)?\b',
    re.I,
)


def _iter_card_number_matches(text):
    """Yield card-number tokens while excluding grader scores and copyright years.

    Decimal grading labels such as BGS 9.5 or PSA 10.0 contain standalone digit
    fragments that also satisfy the generic card-number regex.  Excluding the
    complete grader span prevents the decimal tail from becoming a fake card ID
    in both query parsing and listing identity checks.
    """
    text=str(text or '')
    grade_spans=[(match.start(),match.end()) for match in GRADER_QUERY_RE.finditer(text)]
    for match in CARD_NUMBER_QUERY_RE.finditer(text):
        if any(match.start()<end and match.end()>start for start,end in grade_spans):
            continue
        token=match.group(0).strip()
        prefix=text[max(0,match.start()-16):match.start()]
        if re.search(r'(?:PSA|BGS|CGC|TAG|BRG)\s*[:#-]?\s*$',prefix,re.I):
            continue
        compact=_normalize_card_number(token)
        if compact.isdigit() and len(compact)==4 and 1996<=int(compact)<=2099:
            continue
        yield match


def _query_card_number_match(query):
    return next(_iter_card_number_matches(query),None)


def _tcgdex_query_parts(query):
    text=str(query or '').strip();match=_query_card_number_match(text);card_number=''
    if match:card_number=match.group(0).strip();name=(text[:match.start()]+' '+text[match.end():]).strip()
    else:name=text
    name=GRADER_QUERY_RE.sub(' ',name)
    name=re.sub(r'\b(?:pokemon|pok[eé]mon|card|tcg|korean|japanese|english|kr|jp|us|usa)\b',' ',name,flags=re.I)
    return re.sub(r'\s+',' ',name).strip(),card_number


def _identity_blob_numbers(value):
    text=str(value or '').upper().replace('–','-').replace('—','-')
    found=[]
    for match in _iter_card_number_matches(text):
        token=_normalize_card_number(match.group(0))
        if token and token not in found:found.append(token)
    return found[:32]


def _identity_name_token(value):
    return re.sub(r'[^0-9a-z가-힣ぁ-んァ-ヶ一-龯]+','',str(value or '').casefold())[:160]


_PRINT_VARIANT_RULES=(
    ('manga',re.compile(r'\b(?:manga(?:\s+rare)?)\b|만화\s*(?:레어)?|マンガ',re.I)),
    ('parallel',re.compile(r'\bparallel\b|패러렐|パラレル',re.I)),
    ('special_art',re.compile(r'\b(?:special\s+art(?:\s+rare)?|sar)\b|스페셜\s*아트',re.I)),
    ('alt_art',re.compile(r'\b(?:alt(?:ernate|ernative)?\s+art)\b|얼터(?:너티브)?\s*아트|別イラスト',re.I)),
    ('full_art',re.compile(r'\bfull\s+art\b|풀\s*아트',re.I)),
    ('reverse_holo',re.compile(r'\b(?:reverse\s+(?:holo(?:foil)?|foil)|reverseholofoil)\b|리버스\s*홀로|リバース',re.I)),
    ('standard',re.compile(r'\b(?:normal|regular|standard|non[- ]?holo)\b|일반판|ノーマル',re.I)),
    ('holo',re.compile(r'\b(?:holo(?:foil)?|holographic)\b|홀로|キラ',re.I)),
    ('foil',re.compile(r'\bfoil\b|포일|フォイル',re.I)),
    ('promo',re.compile(r'\bpromo(?:tional)?\b|프로모|プロモ',re.I)),
)


def _card_variant(value):
    text=str(value or '')[:500]
    for key,pattern in _PRINT_VARIANT_RULES:
        if pattern.search(text):
            return key
    return ''


def _item_variant(item):
    return _card_variant(' '.join(str(item.get(key) or '') for key in ('variant_name','print_variant','title','snippet')))


def _explicit_listing_regions(item):
    blob=' '.join(str(item.get(key) or '') for key in ('title','snippet')).casefold()
    found=set()
    patterns=(
        ('KR',r'\b(?:korean|korea\s+(?:version|edition)|kr\s+(?:version|edition))\b|한국판|한글판|국판'),
        ('JP',r'\b(?:japanese|japan\s+(?:version|edition)|jp\s+(?:version|edition))\b|日本版|日版|일판'),
        ('US',r'\b(?:english|us\s+(?:version|edition)|en\s+(?:version|edition))\b|영문판|미국판'),
    )
    for region,pattern in patterns:
        if re.search(pattern,blob,re.I):found.add(region)
    return found


def _item_region_eligibility(region,item):
    requested=str(region or 'ALL').upper()
    if requested not in ('KR','JP','US'):
        return True,'edition_unscoped'
    structured=str(item.get('region_scope') or '').upper()
    if structured in ('KR','JP','US') and structured!=requested:
        return False,'edition_scope_mismatch'
    explicit=_explicit_listing_regions(item)
    if len(explicit)>1:
        return False,'edition_evidence_conflict'
    if explicit and requested not in explicit:
        return False,'edition_explicit_mismatch'
    return True,'edition_match_or_neutral'


def _item_variant_eligibility(query,item):
    wanted=_card_variant(query)
    actual=_item_variant(item)
    if not wanted:
        return True,'variant_unspecified',actual
    if actual==wanted:
        return True,'variant_exact',actual
    if actual:
        return False,'variant_mismatch',actual
    return False,'variant_evidence_missing',actual


def _variant_summary_state(query,items):
    wanted=_card_variant(query)
    variants=[]
    for item in items:
        if int(item.get('price_krw') or 0)<=0:continue
        variants.append(_item_variant(item))
    explicit=sorted({value for value in variants if value})
    has_unknown=any(not value for value in variants)
    ambiguous=bool(not wanted and (len(explicit)>1 or (explicit and has_unknown)))
    scope=wanted or ('AMBIGUOUS' if ambiguous else (explicit[0] if len(explicit)==1 and not has_unknown else 'UNSPECIFIED'))
    return {'wanted':wanted,'observed':explicit,'has_unknown':has_unknown,'ambiguous':ambiguous,'scope':scope}


def _item_identity_eligibility(query,item,region='ALL'):
    """Fail closed on wrong edition, wrong print variant, or card-number mismatch."""
    region_ok,region_basis=_item_region_eligibility(region,item)
    if not region_ok:return False,region_basis
    variant_ok,variant_basis,_=_item_variant_eligibility(query,item)
    if not variant_ok:return False,variant_basis
    wanted_name,wanted_number=_tcgdex_query_parts(query)
    def accepted(base):return True,base+'+'+region_basis+'+'+variant_basis
    if not wanted_number:return accepted('name_only_query')
    wanted=_normalize_card_number(wanted_number)
    actual=_normalize_card_number(item.get('card_number'))
    title_blob=' '.join(str(item.get(key) or '') for key in ('title','snippet'))
    name_token=_identity_name_token(wanted_name)
    name_ok=bool(name_token and name_token in _identity_name_token(title_blob))
    if actual and _card_number_matches(wanted,actual):
        if _has_explicit_set_prefix(wanted) or name_ok:return accepted('structured_card_number_exact')
        return False,'local_number_without_name_corroboration'
    candidates=_identity_blob_numbers(title_blob)
    if any(_card_number_matches(wanted,candidate) for candidate in candidates):
        if _has_explicit_set_prefix(wanted) or name_ok:return accepted('text_card_number_exact')
        return False,'local_number_without_name_corroboration'
    return False,'card_number_mismatch'


def _tcgdex_api(query,game,fx,region='ALL'):
    if _game_key(game) not in ('pokemon','all'):return [],'unsupported'
    region=str(region or 'ALL').upper()
    if region=='KR':return [],'region_unsupported'
    name,card_number=_tcgdex_query_parts(query)
    if not name or not re.search(r'[A-Za-z\u3040-\u30ff\u3400-\u9fff]',name):return [],'query_language_unsupported'
    rows=[];seen=set()
    languages=('ja',) if region=='JP' else (('en',) if region=='US' else ('en','ja'))
    for language in languages:
        params={'name':name,'pagination:page':'1','pagination:itemsPerPage':'6'}
        if card_number and re.fullmatch(r'[A-Za-z]?\d{1,4}',card_number):params['localId']=card_number
        briefs=_json_request(f'https://api.tcgdex.net/v2/{language}/cards?'+urlencode(params),{}, {'api.tcgdex.net'})
        for brief in briefs[:6] if isinstance(briefs,list) else []:
            card_id=str((brief or {}).get('id') or '')
            if not card_id or card_id in seen:continue
            seen.add(card_id)
            card=_json_request(f'https://api.tcgdex.net/v2/{language}/cards/'+quote(card_id,safe=''),{}, {'api.tcgdex.net'})
            if not isinstance(card,dict):continue
            if name.casefold() not in str(card.get('name') or '').casefold():continue
            if card_number and not (
                _card_number_matches(card_number, card.get('localId'))
                or _card_number_matches(card_number, card_id)
            ):
                continue
            pricing=card.get('pricing') or {};tcgp=pricing.get('tcgplayer') or {}
            for variant_name,variant in tcgp.items():
                if variant_name in ('updated','unit') or not isinstance(variant,dict):continue
                amount=variant.get('marketPrice') or variant.get('midPrice') or variant.get('lowPrice')
                if not isinstance(amount,(int,float)) or amount<=0:continue
                krw=_to_krw(amount,'USD',fx)
                if not krw:continue
                rows.append({'source':'TCGdex','source_id':'tcgdex','title':f'{card.get("name","")} · {card.get("localId","")} · {variant_name}',
                             'url':f'https://api.tcgdex.net/v2/{language}/cards/{card_id}','price_krw':krw,
                             'price_native':float(amount),'currency':'USD','price_kind':'TCGplayer API 통합시세',
                             'verified_api':True,'date':str(tcgp.get('updated') or ''),'score':0.96,
                             'card_number':str(card.get('localId') or '')[:60],
                             'variant_name':str(variant_name)[:60],
                             'print_variant':_card_variant(variant_name),
                             'region_scope':'JP' if language=='ja' else 'US'})
    return rows[:18],'ok'

PSA_GRADE_LABELS=tuple(f'PSA {grade}' for grade in range(10,0,-1))
GRADE_ORDER=('미감정',*PSA_GRADE_LABELS,'BGS 10 블랙라벨')


def _grade_number_label(company,value):
    try:number=float(value)
    except (TypeError,ValueError,OverflowError):return ''
    if not (1<=number<=10) or number*2!=int(number*2):return ''
    text=str(int(number)) if number.is_integer() else f'{number:.1f}'
    return f'{company} {text}'


def _grade_label(item):
    text=' '.join(str(item.get(k) or '') for k in ('title','snippet','price_kind'))
    if re.search(r'\bBGS\s*10(?:\.0)?\b[^\n]{0,28}\b(?:black\s*label|블랙\s*라벨)\b',text,re.I):return 'BGS 10 블랙라벨'
    for company in ('PSA','BGS','CGC','TAG','BRG'):
        match=re.search(rf'\b{company}\s*(10|[1-9])(?:\s*\.\s*(5))?\b',text,re.I)
        if match:
            value=float(match.group(1))+(.5 if match.group(2) else 0)
            label=_grade_number_label(company,value)
            if label:return label
    match=re.search(r'(?:등급|grade)\s*[:\-]?\s*([ABCD])\b',text,re.I)
    if match:return match.group(1).upper()
    return '미감정'


def _grade_sort_key(label):
    if label=='미감정':return (0,0,0)
    if label=='BGS 10 블랙라벨':return (2,-10.5,0)
    match=re.fullmatch(r'(PSA|BGS|CGC|TAG|BRG)\s+(10|[1-9])(?:\.(5))?',label)
    if match:
        company_order={'PSA':1,'BGS':2,'CGC':3,'TAG':4,'BRG':5}
        grade=float(match.group(2))+(.5 if match.group(3) else 0)
        return (company_order[match.group(1)],-grade,0)
    return (9,0,str(label))

PRICE_EVIDENCE_PRIORITY=(
    ('completed','완료거래'),
    ('api_reference','API 참고시세'),
    ('asking','판매중/호가'),
)


def _price_evidence_class(item):
    kind=str(item.get('price_kind') or '')
    blob=' '.join(str(item.get(k) or '') for k in ('title','snippet','price_kind')).casefold()
    if kind=='실거래/완료 신호' or any(word in blob for word in SOLD_WORDS):return 'completed'
    if item.get('verified_api') is True and kind not in ('판매중','판매가'):
        return 'api_reference'
    return 'asking'


def _select_price_evidence(items):
    buckets={key:[] for key,_ in PRICE_EVIDENCE_PRIORITY}
    for item in items:
        if int(item.get('price_krw') or 0)>0:
            buckets[_price_evidence_class(item)].append(item)
    for key,label in PRICE_EVIDENCE_PRIORITY:
        if buckets[key]:return buckets[key],label,buckets
    return [],'자료 없음',buckets


def _grade_reference(items):
    grouped={label:[] for label in GRADE_ORDER}
    for item in items:
        if int(item.get('price_krw') or 0)>0:
            grouped.setdefault(_grade_label(item),[]).append(item)
    labels=sorted(grouped,key=_grade_sort_key)
    rows=[]
    for label in labels:
        grade_items=grouped[label]
        chosen,basis,buckets=_select_price_evidence(grade_items)
        values=[int(item.get('price_krw') or 0) for item in chosen]
        rows.append({
            'grade':label,'count':len(values),'total_count':len(grade_items),'basis':basis,
            'completed_count':len(buckets['completed']),'api_reference_count':len(buckets['api_reference']),
            'asking_count':len(buckets['asking']),
            'price_krw':int(statistics.median(values)) if values else 0,
            'min_krw':min(values) if values else 0,'max_krw':max(values) if values else 0,
        })
    return rows

def _query_grade_label(query):
    label=_grade_label({'title':str(query or '')})
    return '' if label=='미감정' else label

def _comparable_summary_items(query,items):
    """Keep the headline median on one grading basis.

    The detailed rows can still show all evidence, but a raw-card query must not
    average PSA/BGS prices into the number labelled as the central reference.
    """
    wanted=_query_grade_label(query)
    valid=[x for x in items if int(x.get('price_krw') or 0)>0]
    same_grade=[x for x in valid if _grade_label(x)==wanted] if wanted else [x for x in valid if _grade_label(x)=='미감정']
    chosen,evidence_basis,_=_select_price_evidence(same_grade)
    grade_basis=wanted or '미감정'
    return chosen, f'{grade_basis} · {evidence_basis}'

def _learning():
    d=_safe_json(LEARNING,{})
    return d if isinstance(d,dict) else {}

def _health(source_id,learn):
    s=(learn.get('sources') or {}).get(source_id,{})
    runs=max(1,int(s.get('runs') or 0));hits=int(s.get('hits') or 0);errors=int(s.get('errors') or 0)
    return max(.75,min(1.15,0.90+(hits/runs)*.18-(errors/runs)*.12))

def _cooling(source_id,learn):
    row=(learn.get('sources') or {}).get(source_id,{})
    try:return float(row.get('cooldown_until_epoch') or 0)>time.time()
    except (TypeError,ValueError,OverflowError):return False

def _failure_stats(exc):
    detail=diagnostic_exception(exc)
    status=0
    match=re.search(r'status\s+(\d{3})',detail)
    if match:status=int(match.group(1))
    retry=0
    retry_match=re.search(r'Retry-After\s+(\d+)s',detail,re.I)
    if retry_match:retry=max(30,min(3600,int(retry_match.group(1))))
    elif status==429:retry=300
    elif status==403:retry=1800
    return {'error':1,'detail':detail,'cooldown_seconds':retry,'status':'cooldown' if retry else 'error'}

def _save_learning(stats):
    old=_learning();src=old.setdefault('sources',{})
    for sid,x in stats.items():
        row=src.setdefault(sid,{'runs':0,'hits':0,'errors':0})
        if x.get('status') in ('not_configured','unsupported','region_unsupported','query_language_unsupported','cooldown_skip'):continue
        row['runs']=int(row.get('runs',0))+1;row['hits']=int(row.get('hits',0))+int(x.get('hits',0));row['errors']=int(row.get('errors',0))+int(x.get('error',0));row['last_at']=datetime.now(timezone.utc).isoformat(timespec='seconds')
        if int(x.get('error',0)):
            row['consecutive_errors']=int(row.get('consecutive_errors',0))+1
            row['last_error']=str(x.get('detail') or '')[:240]
        else:row['consecutive_errors']=0;row.pop('last_error',None)
        cooldown=max(0,min(3600,int(x.get('cooldown_seconds') or 0)))
        if cooldown:row['cooldown_until_epoch']=time.time()+cooldown
        elif not int(x.get('error',0)):row.pop('cooldown_until_epoch',None)
    old['updated_at']=datetime.now(timezone.utc).isoformat(timespec='seconds');_atomic(LEARNING,old)

def _cache_key(query,region,game):
    api_mode='justtcg:1' if os.environ.get('JUSTTCG_API_KEY','').strip() else 'justtcg:0'
    return re.sub(r'\s+',' ',f'{query}|{region}|{game}|{api_mode}').strip().lower()

def _host_matches(host,domain):
    host=str(host or '').lower().rstrip('.');domain=str(domain or '').lower().rstrip('.')
    return bool(host and domain and (host==domain or host.endswith('.'+domain)))

def _cached(key):
    d=_safe_json(CACHE,{})
    row=(d.get('items') or {}).get(key) if isinstance(d,dict) else None
    if isinstance(row,dict) and time.time()-float(row.get('_epoch',0))<CACHE_TTL:return row
    return None

def _save_cache(key,data):
    d=_safe_json(CACHE,{})
    if not isinstance(d,dict):d={}
    items=d.setdefault('items',{});items[key]=data
    # bounded cache
    if len(items)>80:
        for k,_ in sorted(items.items(),key=lambda kv:float(kv[1].get('_epoch',0)))[:-60]:items.pop(k,None)
    _atomic(CACHE,d)

def search_multi_market(query,region='ALL',game='ALL',force=False):
    query=re.sub(r'[\x00-\x1f\x7f]',' ',str(query or '')).strip()[:160]
    region=str(region or 'ALL').upper();game=str(game or 'ALL')[:40]
    if not query:return {'ok':False,'error':'검색어가 필요합니다.','items':[]}
    key=_cache_key(query,region,game)
    if not force:
        c=_cached(key)
        if c:return {**c,'cache':'hit'}
    fx=_fx();learn=_learning();items=[];stats={};errors=[]
    # eBay API first when configured; RSS discovery remains as fallback/extra coverage.
    try:
        api_rows=_ebay_api(query,region,fx);items.extend(api_rows);stats['ebay']={'hits':len(api_rows),'error':0}
    except Exception as e:
        failure=_failure_stats(e);stats['ebay']={'hits':0,**failure};errors.append('eBay API:'+failure['detail'])
    # Structured APIs are queried first. Missing keys and unsupported games are visible states,
    # not failures, and therefore never lower the source-learning score.
    for sid,name,loader in (('justtcg','JustTCG',_justtcg_api),('tcgdex','TCGdex',_tcgdex_api)):
        if _cooling(sid,learn):
            stats[sid]={'hits':0,'error':0,'status':'cooldown_skip'};continue
        try:
            direct,status=loader(query,game,fx,region);items.extend(direct)
            stats[sid]={'hits':len(direct),'error':0,'status':status}
        except Exception as exc:
            failure=_failure_stats(exc);stats[sid]={'hits':0,**failure};errors.append(name+':'+failure['detail'])
    ordered=sorted(SOURCES,key=lambda src:float(src['weight'])*_health(src['id'],learn),reverse=True)
    for src in ordered:
        sid=src['id'];stats.setdefault(sid,{'hits':0,'error':0,'status':'ready'})
        if _cooling(sid,learn):
            stats[sid]['status']='cooldown_skip';continue
        if sid=='tcgdex' and _game_key(game) not in ('pokemon','all'):
            stats[sid]['status']='unsupported';continue
        q=f'site:{src["domain"]} {query}'
        if game not in ('ALL',''):q+=' '+game
        region_term=_region_query_term(region)
        if region_term:q+=' '+region_term
        try:rows=_rss(q,6)
        except Exception as e:
            failure=_failure_stats(e);stats[sid].update(failure);errors.append(src['name']+':'+failure['detail']);continue
        seen=0
        for r in rows:
            host=(urlparse(r['url']).hostname or '').lower()
            if not _host_matches(host,src['domain']):continue
            p=_extract_price(r['title']+' '+r['snippet'],fx)
            if not p:continue
            blob=(r['title']+' '+r['snippet']).lower();kind='실거래/완료 신호' if any(w in blob for w in SOLD_WORDS) else src['kind']
            weight=float(src['weight'])*_health(sid,learn)*(1.08 if kind=='실거래/완료 신호' else 1.0)
            listing_regions=_explicit_listing_regions(r)
            listing_region=next(iter(listing_regions)) if len(listing_regions)==1 else 'ALL'
            items.append({'source':src['name'],'source_id':sid,'title':r['title'],'url':r['url'],'snippet':r['snippet'],'date':r['date'],
                          **p,'price_kind':kind,'verified_api':False,'score':round(weight,3),
                          # RSS discovery is not edition proof. Preserve only explicit
                          # listing evidence; never stamp the requested region onto a row.
                          'region_scope':listing_region})
            seen+=1
        stats[sid]['hits']+=seen
        if seen:stats[sid]['status']='ok'
        elif stats[sid].get('status') not in ('not_configured','unsupported','region_unsupported','query_language_unsupported'):stats[sid]['status']='no_result'
    # Dedupe URL + near-identical title/price.
    dedup={}
    for x in items:
        url=x.get('url') or '';title=re.sub(r'\W+','',str(x.get('title') or '').lower())[:80];bucket=int(x.get('price_krw',0)//1000)
        k=url or f'{x.get("source_id")}|{title}|{bucket}'
        old=dedup.get(k)
        if not old or float(x.get('score',1))>float(old.get('score',1)):dedup[k]=x
    items=list(dedup.values());items.sort(key=lambda x:(-float(x.get('score',1)),-int(x.get('price_krw',0))))
    for item in items:
        eligible,identity_basis=_item_identity_eligibility(query,item,region)
        item['summary_eligible']=bool(eligible);item['identity_basis']=identity_basis
        item['print_variant']=_item_variant(item)
    eligible_items=[item for item in items if item.get('summary_eligible') is True]
    variant_state=_variant_summary_state(query,eligible_items)
    _,query_card_number=_tcgdex_query_parts(query)
    identity_ambiguous=not bool(_normalize_card_number(query_card_number))
    if identity_ambiguous:
        # A name-only query can span many sets, promos, reprints and printings.
        # Keep raw evidence visible, but never manufacture one headline/grade price.
        comparable=[];basis='카드번호/세트 식별자 필요 · 이름만으로 시세 요약 보류'
    elif variant_state['ambiguous']:
        comparable=[];basis='인쇄/아트 변형 미지정 · 서로 다른 변형 혼재'
    else:
        comparable,basis=_comparable_summary_items(query,eligible_items)
    prices=[int(x['price_krw']) for x in comparable if int(x.get('price_krw',0))>0]
    summary={'count':len(prices),'total_count':len([x for x in eligible_items if int(x.get('price_krw',0))>0]),
             'observed_total_count':len([x for x in items if int(x.get('price_krw',0))>0]),
             'identity_excluded_count':len([x for x in items if x.get('summary_eligible') is False and int(x.get('price_krw',0))>0]),
             'identity_scope':'exact_card_number' if query_card_number else 'name_only_hold',
             'identity_ambiguous':identity_ambiguous,
             'variant_scope':variant_state['scope'],'variant_ambiguous':variant_state['ambiguous'],
             'observed_variants':variant_state['observed'],'variant_unknown_evidence':variant_state['has_unknown'],
             'median_krw':int(statistics.median(prices)) if prices else 0,'min_krw':min(prices) if prices else 0,'max_krw':max(prices) if prices else 0,
             'source_count':len({x.get('source_id') for x in comparable}),'basis':basis,
             'region_scope':region if region in ('KR','JP','US') else 'ALL'}
    source_status=[{'source_id':src['id'],'source':src['name'],'hits':int((stats.get(src['id']) or {}).get('hits') or 0),
                    'status':str((stats.get(src['id']) or {}).get('status') or 'ready')}
                   for src in SOURCES if src['id'] in ('snkrdunk','justtcg','tcgdex','pavilion')]
    data={'ok':True,'query':query,'region':region,'game':game,'checked_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),'refresh_minutes':15,
          'summary':summary,'items':items[:60],'errors':errors,'source_stats':stats,'source_status':source_status,
          'reference_links':_reference_links(query,game),'grade_reference':_grade_reference(eligible_items) if query_card_number and not variant_state['ambiguous'] else [],
          'notice':'SNKRDUNK·JustTCG·TCGdex·Pavilion을 포함한 공개 참고시세를 교차수집합니다. 카드번호·판본·인쇄/아트 변형이 확인된 자료만 중앙값·등급별 시세에 사용합니다. 카드명만 입력한 경우 여러 세트·프로모·재록이 섞일 수 있어 중앙값과 등급별 시세를 보류하고 원자료만 표시합니다. 같은 카드번호에서 Standard·Holo·Reverse Holo·Parallel·Alt Art·Manga 등이 섞여도 자동 중앙값을 보류합니다. 완료거래→API 참고시세→호가 순으로 분리하며, 없는 등급값은 추정하지 않습니다. RSS 검색의 요청 판본은 증거로 재사용하지 않으며 실제 매물의 판본 표기만 보존합니다. 403/429는 우회하지 않고 안전 대기합니다.',
          '_epoch':time.time(),'cache':'refresh'}
    _save_learning(stats);_save_cache(key,data);return data

if __name__=='__main__':
    import sys
    print(json.dumps(search_multi_market(' '.join(sys.argv[1:]) or '피카츄',force=True),ensure_ascii=False,indent=2))
