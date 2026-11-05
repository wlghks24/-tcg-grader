"""Exact provider facts retained alongside the existing private image store.

The existing collector owns quotas/scheduling. Reads never fetch or write.
Prices remain provider references, not confirmed sales, grading or match proof.
"""
from datetime import datetime, timezone
import functools
import hashlib
import json
import math
from pathlib import Path
import re
import threading
from urllib.parse import quote

import tablet_image_library_v1 as library

FILE = 'card_provider_facts_v904.json'
MAX_BYTES = 8_000_000
MAX_ITEMS = 4000
MAX_REQUESTS = 8
LOCK = threading.RLock()
URL = re.compile(r'https://api\.tcgdex\.net/v2/(en|ja|zh-tw)/(cards|sets)/([A-Za-z0-9_.-]{1,90}(?:%2B[A-Za-z0-9_.-]{0,90})?)')
LOCALES = {'US':'en', 'JP':'ja', 'CN-T':'zh-tw'}
VARIANTS = {'normal':'일반', 'reverse':'리버스', 'holo':'홀로', 'holofoil':'홀로',
            'reverse-holofoil':'리버스 홀로', '1st-edition':'초판', '1st-edition-holofoil':'초판 홀로',
            'unlimited':'언리미티드', 'unlimited-holofoil':'언리미티드 홀로'}
# Factual National-Dex boundaries verified against PokeAPI/pokeapi
# data/v2/csv/pokemon_species.csv blob 67f0da856d395bbe058cf961edce6ef2f805d1d8.
# Species generation is distinct from a card's release series/era.
DEX_ENDS = (151,251,386,493,649,721,809,905,1025)


def source_identity(url):
    """Accept only canonical exact-source IDs; Japanese set '+' must be %2B."""
    match = URL.fullmatch(url) if isinstance(url, str) else None
    if not match:
        return None
    locale, kind, encoded = match.groups()
    ident = encoded.replace('%2B', '+')
    if (len(ident) > 90 or (kind != 'sets' and '+' in ident)
            or '..' in ident or not re.fullmatch(r'[A-Za-z0-9_.+-]{1,90}', ident)
            or quote(ident, safe='') != encoded):
        return None
    return locale, kind, ident


def text(value, limit=160):
    return value.strip() if isinstance(value,str) and 0<len(value.strip())<=limit and not any(ord(c)<32 for c in value) else ''


def stamp(value):
    try:
        if type(value) in (int,float) and math.isfinite(value):
            value = datetime.fromtimestamp(value/1000 if value>10_000_000_000 else value,timezone.utc).isoformat()
        parsed = datetime.fromisoformat(value.replace('Z','+00:00')) if isinstance(value,str) and len(value)<=64 else None
        return parsed.astimezone(timezone.utc).isoformat() if parsed is not None and parsed.tzinfo is not None else ''
    except (ValueError,OSError,OverflowError):
        return ''


def generation(ids):
    if not isinstance(ids,list) or not 1<=len(ids)<=4 or any(type(i) is not int or not 1<=i<=1025 for i in ids):
        return ''
    values = sorted({next(n for n,end in enumerate(DEX_ENDS,1) if i<=end) for i in ids})
    return ' · '.join(str(n)+'세대' for n in values)


def prices(detail, locale):
    """Source market references, including explicitly identified detailed variants.

    A detailed variant price is NOT evidence that a user's photo is that printing.
    Existing quota, region, provider and price-confidence rules remain unchanged.
    """
    if locale != 'en':
        return []
    sources = [('', detail.get('pricing'))]
    detailed = detail.get('variants_detailed')
    if isinstance(detailed, list):
        for variant in detailed[:16]:
            if not isinstance(variant, dict):
                continue
            ref = variant.get('variantId')
            if not isinstance(ref, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', ref) or ref == 'generated':
                continue
            if isinstance(variant.get('pricing'), dict):
                sources.append((ref, variant['pricing']))
    result, seen = [], set()
    for ref, pricing in sources:
        if not isinstance(pricing, dict):
            continue
        for provider, currency in (('tcgplayer', 'USD'), ('cardmarket', 'EUR')):
            item = pricing.get(provider)
            if not isinstance(item, dict) or item.get('unit') != currency:
                continue
            updated = stamp(item.get('updated'))
            if provider == 'tcgplayer':
                candidates = [(v, 'marketPrice', value) for v, value in item.items()
                              if v in VARIANTS and isinstance(value, dict)]
            else:
                candidates = [('normal', 'trend', item), ('holo', 'trend-holo', item)]
            for variant, field, value in candidates:
                amount = value.get(field)
                # API zero is sometimes an unavailable quote, not a free card.
                if type(amount) not in (int, float) or not 0 < amount <= 100_000_000 or not math.isfinite(amount):
                    continue
                signature = (provider, currency, variant, amount, updated)
                if signature in seen:
                    continue
                seen.add(signature)
                quote = {'provider': provider, 'currency': currency, 'variant': variant, 'amount': amount,
                         'metric': '시장 기준가' if provider == 'tcgplayer' else '시장 추세가',
                         'updated_at': updated, 'sale_confirmed': False}
                if ref:
                    quote.update(price_scope='DETAILED_VARIANT', variant_ref=ref)
                result.append(quote)
                if len(result) >= 12:
                    return result
    return result


def normalize(url, detail, *, now=None):
    source=source_identity(url)
    if not source or not isinstance(detail,dict) or detail.get('id')!=source[2]:
        return None
    locale,kind,ident=source
    now=now or datetime.now(timezone.utc)
    if not isinstance(now,datetime) or now.tzinfo is None: raise ValueError('aware card facts clock required')
    checked=now.isoformat()
    row={'locale':locale,'id':ident,'kind':kind,'source':url,'checked_at':checked}
    if kind=='cards':
        card_set=detail.get('set')
        if not isinstance(card_set,dict) or not text(card_set.get('id'),40):
            return None
        row.update(set_id=card_set['id'], card_number=text(str(detail.get('localId') or ''),30),
                   name=text(detail.get('name')),generation=generation(detail.get('dexId')),category=text(detail.get('category'),40),
                   set_name=text(card_set.get('name')),prices=prices(detail,locale),
                   available_variants=[k for k,v in (detail.get('variants') or {}).items() if k in ('normal','reverse','holo','firstEdition') and v is True] if isinstance(detail.get('variants'),dict) else [])
        detailed=detail.get('variants_detailed')
        has_pricing=bool(detail.get('pricing')) or (isinstance(detailed,list) and any(
            isinstance(v,dict) and bool(v.get('pricing')) for v in detailed[:16]))
        row['price_state']=('REFERENCES_PRESENT' if row['prices'] else 'LANGUAGE_SCOPE_UNVERIFIED' if locale!='en' and has_pricing
                            else 'UNSUPPORTED_OR_UNQUALIFIED' if has_pricing else 'ABSENT')
    else:
        serie=detail.get('serie')
        serie=serie if isinstance(serie,dict) else {}
        release=text(detail.get('releaseDate'),10)
        try:
            if release: datetime.strptime(release,'%Y-%m-%d')
        except ValueError:
            release=''
        row.update(set_name=text(detail.get('name')),series_id=text(serie.get('id'),40),series_name=text(serie.get('name')),
                   release_date=release)
    return row


def read(root):
    from safe_runtime import safe_read_text, unique_json_object, reject_nonstandard_json
    path=Path(root)/FILE
    if path.is_symlink(): raise ValueError('card facts symlink')
    if not path.exists(): return {'version':904,'items':{}}
    data=json.loads(safe_read_text(path,max_bytes=MAX_BYTES),object_pairs_hook=unique_json_object,parse_constant=reject_nonstandard_json)
    if not isinstance(data,dict) or data.get('version')!=904 or not isinstance(data.get('items'),dict) or len(data['items'])>MAX_ITEMS:
        raise ValueError('card facts schema')
    failures=data.get('failures',{})
    if not isinstance(failures,dict) or len(failures)>MAX_ITEMS or any(not source_identity(k) or not stamp(v) for k,v in failures.items()):
        raise ValueError('card facts retry schema')
    for key,row in data['items'].items():
        source=source_identity(row.get('source','')) if isinstance(row,dict) else None
        if not source or key!='/'.join(source) or row.get('id')!=source[2] or not stamp(row.get('checked_at')):
            raise ValueError('card facts identity')
        if row.get('locale')!=source[0] or row.get('kind')!=source[1]: raise ValueError('card facts scope')
        for field in ('set_id','card_number','name','generation','set_name','category','series_id','series_name','release_date'):
            if field in row and row[field]!='' and not text(row[field],200): raise ValueError('card facts text')
        quotes=row.get('prices',[])
        if not isinstance(quotes,list) or len(quotes)>12: raise ValueError('card facts prices')
        for q in quotes:
            if (not isinstance(q,dict) or q.get('provider') not in ('tcgplayer','cardmarket')
                    or q.get('currency')!=('USD' if q['provider']=='tcgplayer' else 'EUR')
                    or q.get('variant') not in VARIANTS or q.get('sale_confirmed') is not False
                    or type(q.get('amount')) not in (int,float) or not 0<=q['amount']<=100_000_000 or not math.isfinite(q['amount'])
                    or not text(q.get('metric'),40) or not isinstance(q.get('updated_at'),str) or q.get('updated_at') and not stamp(q['updated_at'])):
                raise ValueError('card facts quote schema')
            if 'variant_ref' in q:
                if (q.get('price_scope')!='DETAILED_VARIANT'
                        or not isinstance(q['variant_ref'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',q['variant_ref'])
                        or q['variant_ref']=='generated'):
                    raise ValueError('card facts variant source')
            elif 'price_scope' in q:
                raise ValueError('card facts quote scope')
        retained=row.get('retained_fields',[])
        if (not isinstance(retained,list) or len(retained)>5
                or any(type(v) is not str or v not in ('card_number','generation','name','category',
                    'set_name','series_id','series_name','release_date') for v in retained)):
            raise ValueError('card facts retained schema')
        if len(json.dumps(row,ensure_ascii=False))>6000: raise ValueError('card facts row bound')
        variants=row.get('available_variants',[])
        if not isinstance(variants,list) or len(variants)>4 or any(v not in ('normal','reverse','holo','firstEdition') for v in variants):
            raise ValueError('card facts variants')
        if row.get('generation') and not re.fullmatch(r'[1-9]세대(?: · [1-9]세대){0,3}',row['generation']):
            raise ValueError('card facts generation schema')
    return data


def observe(url, detail, root, *, now=None):
    row=normalize(url,detail,now=now)
    if row is None: return False
    from safe_runtime import atomic_write_json
    with LOCK:
        data=read(root)
        key='/'.join((row['locale'],row['kind'],row['id']))
        if key not in data['items'] and len(data['items'])>=MAX_ITEMS:
            raise ValueError('card facts capacity')
        old=data['items'].get(key,{})
        if row['kind']=='cards':
            if any(old.get(k) and row.get(k) and old[k]!=row[k] for k in ('set_id','card_number','generation')):
                raise ValueError('card facts identity conflict')
            retained=[]
            for field in ('card_number','generation','name','category','set_name'):
                if not row.get(field) and old.get(field):
                    row[field]=old[field];retained.append(field)
            if not row['prices'] and old.get('prices'):
                row['prices']=old['prices'];row['price_state']='RETAINED_NO_NEW_PRICE'
            row['retained_fields']=retained
            if retained: row['retained_checked_at']=old['checked_at']
        else:
            if old.get('series_id') and row.get('series_id') and old['series_id']!=row['series_id']:
                raise ValueError('card set identity conflict')
            retained=[]
            for field in ('set_name','series_id','series_name','release_date'):
                if not row.get(field) and old.get(field):
                    row[field]=old[field];retained.append(field)
            row['retained_fields']=retained
            if retained: row['retained_checked_at']=old['checked_at']
        data['items'][key]=row
        data.get('failures',{}).pop(url,None)
        if len(json.dumps(data,ensure_ascii=False).encode())>MAX_BYTES:
            raise ValueError('card facts byte limit')
        atomic_write_json(Path(root)/FILE,data,suffix='.904.tmp')
    return True


def recent(value, now):
    checked=stamp(value)
    return bool(checked and 0<=(now-datetime.fromisoformat(checked)).total_seconds()<86400)


def remember_failure(url, root, now):
    from safe_runtime import atomic_write_json
    with LOCK:
        data=read(root);failed=data.setdefault('failures',{})
        if url not in failed and len(failed)>=MAX_ITEMS: raise ValueError('facts retry capacity')
        failed[url]=now.isoformat()
        if len(json.dumps(data,ensure_ascii=False).encode())>MAX_BYTES: raise ValueError('facts retry bytes')
        atomic_write_json(Path(root)/FILE,data,suffix='.904.retry.tmp')


def install(auto):
    """Observe already-budgeted replies; no extra request or duplicate scheduler."""
    original=auto.fetch_json
    if getattr(original,'_tcg_card_facts_v904',False): return
    @functools.wraps(original)
    def fetch(url):
        result=original(url)
        budget=getattr(auto._BUDGET_CONTEXT,'current',None)
        if URL.fullmatch(url) and budget is not None and budget.provider=='TCGdex':
            # A bad private facts store is reported by the existing collection
            # error boundary; it must never be overwritten with an empty cache.
            observe(url,result,library.storage_root())
        return result
    fetch._tcg_card_facts_v904=True
    auto.fetch_json=fetch


def collect(auto, root, records, budget, stop, *, now=None):
    """Fairly revisit existing complete cards, under the SAME persisted quota."""
    if getattr(auto._BUDGET_CONTEXT,'current',None) is not budget:
        raise ValueError('shared card facts budget required')
    if getattr(getattr(auto,'fetch_json',None),'_tcg_card_facts_v904',False) is not True:
        return {'attempted':0,'saved':0,'pending':None,'deferred':False,'issues':[], 'status':'FACTS_HOOK_INACTIVE'}
    now=now or datetime.now(timezone.utc)
    if not isinstance(now,datetime) or now.tzinfo is None: raise ValueError('aware collection clock required')
    state=read(root)
    result={'attempted':0,'saved':0,'pending':0,'deferred':False,'issues':[]}
    work=[]
    seen=set()
    for row in records:
        locale=LOCALES.get(row.get('region'))
        source=row.get('source_id','')
        prefix='pokemon/'+str(locale)+'/'
        if row.get('origin')!='auto' or row.get('provider')!='TCGdex' or row.get('game_id')!='pokemon' or row.get('kind') not in ('CARD','PROMO') or not source.startswith(prefix): continue
        ident=source[len(prefix):]
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,90}',ident): continue
        metadata=row.get('card_metadata',{})
        if metadata.get('card_code') not in (None,ident) or metadata.get('language') not in (None,locale): continue
        if (locale,ident) in seen: continue
        seen.add((locale,ident))
        old=state['items'].get(locale+'/cards/'+ident,{})
        checked=stamp(old.get('checked_at'));card_recent=recent(checked,now)
        card_url='https://api.tcgdex.net/v2/'+locale+'/cards/'+quote(ident,safe='')
        if recent(state.get('failures',{}).get(card_url),now): continue
        set_id=old.get('set_id');set_info=state['items'].get(locale+'/sets/'+str(set_id),{})
        set_url='https://api.tcgdex.net/v2/'+locale+'/sets/'+quote(str(set_id),safe='')
        missing_set=bool(set_id and (not set_info.get('series_name') or not set_info.get('release_date'))
                         and not recent(set_info.get('checked_at'),now) and not recent(state.get('failures',{}).get(set_url),now))
        if card_recent and not missing_set: continue
        work.append((checked or '',locale,ident,row,set_id if card_recent and missing_set else None))
    work.sort(key=lambda r:(r[4] is None,r[0]))
    result['pending']=len(work)
    set_requests=set()
    for _,locale,ident,row,set_only in work:
        if stop.is_set() or result['attempted']>=MAX_REQUESTS: break
        budget.provider='TCGdex'
        active_url=None;before=len(budget.events)
        try:
            if set_only:
                set_url='https://api.tcgdex.net/v2/'+locale+'/sets/'+quote(set_only,safe='')
                if set_url in set_requests: continue
                set_requests.add(set_url);active_url=set_url;before=len(budget.events)
                result['attempted']+=1
                detail=auto.fetch_json(set_url)
                if normalize(set_url,detail,now=now) is None: raise ValueError('exact set detail missing')
                observe(set_url,detail,root,now=now)
                state=read(root);result['saved']+=1;result['pending']-=1
                continue
            result['attempted']+=1
            url='https://api.tcgdex.net/v2/'+locale+'/cards/'+quote(ident,safe='')
            active_url=url;before=len(budget.events)
            detail=auto.fetch_json(url)
            normalized=normalize(url,detail,now=now)
            if normalized is None: raise ValueError('exact card detail missing')
            metadata=row.get('card_metadata',{})
            if metadata.get('set_code') and metadata['set_code']!=normalized['set_id']: raise ValueError('stored card set conflict')
            observe(url,detail,root,now=now)
            result['saved']+=1;result['pending']-=1
            set_id=normalized['set_id'];set_key=locale+'/sets/'+set_id
            set_info=state['items'].get(set_key,{})
            set_url='https://api.tcgdex.net/v2/'+locale+'/sets/'+quote(set_id,safe='')
            if ((not set_info.get('series_name') or not set_info.get('release_date')) and not recent(set_info.get('checked_at'),now)
                    and not recent(state.get('failures',{}).get(set_url),now) and set_url not in set_requests and result['attempted']<MAX_REQUESTS):
                result['attempted']+=1;set_requests.add(set_url);active_url=set_url;before=len(budget.events)
                set_detail=auto.fetch_json(set_url)
                if normalize(set_url,set_detail,now=now) is None: raise ValueError('exact set detail missing')
                observe(set_url,set_detail,root,now=now)
                state=read(root)
        except auto.policy.Deferred as exc:
            result['deferred']=True;result['issues'].append(str(exc)[:120]);break
        except (OSError,ValueError,TypeError,auto.ProviderError) as exc:
            result['issues'].append(type(exc).__name__+': 카드 상세 보완 보류')
            if active_url and len(budget.events)>before:
                remember_failure(active_url,root,now)
                state=read(root)
    return result


def summary(root):
    data=read(root)['items']
    cards=[r for r in data.values() if r['kind']=='cards']
    return {'schema_version':904,'status':'READABLE_REFERENCE_CACHE' if data else 'WAITING_FOR_COLLECTION',
            'card_details':len(cards),'set_details':sum(r['kind']=='sets' for r in data.values()),
            'sets_with_series_and_date':sum(r['kind']=='sets' and bool(r.get('series_name')) and bool(r.get('release_date')) for r in data.values()),
            'cards_with_species_generation':sum(bool(r.get('generation')) for r in cards),
            'cards_with_price_references':sum(bool(r.get('prices')) for r in cards),
            'identity_verified':False,'sale_prices_confirmed':False,'training_performed':False}


if __name__=='__main__':
    try:
        print(json.dumps(summary(library.storage_root()),ensure_ascii=False,indent=2))
    except (OSError,ValueError,TypeError):
        print(json.dumps({'schema_version':904,'status':'HOLD_PREVIOUS_FACTS','ok':False},ensure_ascii=False))
        raise SystemExit(1)


def catalog_quote(row):
    """Retain an already collected display price; do not infer a sale/valuation."""
    display=text(row.get('display'),200)
    if not display: return None
    return {'display':display,'market':text(row.get('market'),100),
            'observed_at':text(row.get('source_date'),64),
            'basis':text(row.get('kind'),120),'sale_confirmed':False}


def attach_market(rows, repo):
    """Add prices by the frozen bridge's exact source identity, without editing it.

    Reuse its validators/namespaces. These are price references for already
    present source IDs, never a new card/photo match or a second source vote.
    """
    from execution import tablet_catalog_bridge as bridge
    games,aliases=bridge.registry(Path(repo))
    wanted={r.get('source_record_id') for r in rows if r.get('source_record_id')}
    prices={}
    for filename in ('market_watch.json','market_prices.json'):
        data=bridge.read_json(Path(repo)/filename,bridge.MAX_SOURCE_BYTES)
        if filename=='market_prices.json':
            entries=data.get('entries')
            if not isinstance(entries,dict) or len(entries)>10000: raise ValueError('price source bound')
            raw=[]
            for key,value in entries.items():
                parts=key.split('|')
                if len(parts)==3 and isinstance(value,dict): raw.append({**value,'region':parts[0],'name':parts[1],'asset':parts[2]})
        else:
            raw=data.get('items')
            if not isinstance(raw,list) or len(raw)>10000: raise ValueError('market source bound')
            raw=list(raw)
            china=data.get('china_catalog',{})
            extra=china.get('items',[]) if isinstance(china,dict) else []
            if not isinstance(extra,list) or len(extra)>10000: raise ValueError('market extra bound')
            raw+=extra
        for row in raw:
            if not isinstance(row,dict): continue
            price=catalog_quote(row)
            if price is None: continue
            game=bridge.game_id(row,games,aliases);region=row.get('region')
            name=bridge.text(row.get('name'));url=bridge.safe_url(row.get('source'))
            if not game or region not in bridge.REGIONS or not name or not url: continue
            kind=bridge.kind(row)
            # Compatibility with the immutable source_rows identity contract;
            # test against its real output rather than weakening its old pins.
            identity=(game,region,kind,bridge.norm(name),url)
            if kind in ('CARD','PROMO'):
                identity+=(tuple(bridge.codes(game,row)),tuple(sorted(bridge.variant_fields(row).items())))
            ident=hashlib.sha256(json.dumps(identity,ensure_ascii=False).encode()).hexdigest()[:32]
            if ident in wanted and ident not in prices:
                prices[ident]=(dict(price,source_dataset=filename),(game,region,kind,url))
    result=[]
    for row in rows:
        row=dict(row);entry=prices.get(row.get('source_record_id'))
        if entry and not row.get('display_only') and row.get('link_status') not in ('SOURCE_COVERAGE_INCOMPLETE','METADATA_CONFLICT'):
            if tuple(row.get(k) for k in ('game_id','region','kind','source_url'))==entry[1]: row['market_quote']=entry[0]
        result.append(row)
    return result


def attach(rows, root):
    """Display reference facts only for exact stored provider/card/language IDs."""
    state=read(root)['items']
    with library.LOCK:
        photos={r['id']:r for r in library._load(root)['items']}
    result=[]
    for row in rows:
        row=dict(row)
        original=photos.get(row.get('image_id'),{})
        locale=LOCALES.get(row.get('region'))
        source=original.get('source_id','')
        prefix='pokemon/'+str(locale)+'/'
        if (row.get('game_id')=='pokemon' and row.get('kind') in ('CARD','PROMO') and original.get('kind')==row.get('kind')
                and original.get('provider')=='TCGdex' and original.get('origin')=='auto'
                and original.get('region')==row.get('region') and source.startswith(prefix)):
            ident=source[len(prefix):]
            facts=state.get(locale+'/cards/'+ident)
            metadata=row.get('card_metadata',{})
            if facts:
                # An exact photo/source ID does not authorize joining details
                # when saved code, language or set metadata contradicts it.
                # Annotate only the in-memory view; never rewrite photo evidence.
                if (metadata.get('card_code')!=ident or metadata.get('language') not in (None,locale)
                        or metadata.get('set_code') not in (None,facts.get('set_id'))):
                    row['card_facts_conflict']=True
                    row['link_status']='METADATA_CONFLICT'
                else:
                    set_facts=state.get(locale+'/sets/'+facts.get('set_id',''),{})
                    row['card_facts']={**facts,'series_name':set_facts.get('series_name',''),
                                       'release_date':set_facts.get('release_date',''),'set_source':set_facts.get('source',''),
                                       'reference_only':True,'set_facts_retained':bool(set_facts.get('retained_fields'))}
        result.append(row)
    return result
