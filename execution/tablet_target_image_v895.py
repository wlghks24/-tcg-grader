"""Catalog-to-image repair for explicit TCGdex card-detail identities only.

Same existing budget/downloader/private cache; never infer printing from artwork.
No search-page scraping, new scheduler, quota increase, or owner-deletion recovery.
"""
import base64
from datetime import datetime, timezone
import hashlib
import math
import re
import time
from urllib.parse import urlsplit

LIMIT = 1
WAIT = 6 * 3600


def collect(auto, library, repo, root, state, budget, stop, *, report=None, clock=time.time):
    result={'attempted':0,'saved':0,'stored_bytes':0,'compression_bytes_saved':0,'issues':[],'deferred':False}
    if getattr(auto._BUDGET_CONTEXT,'current',None) is not budget or budget.state is not state:
        raise ValueError('shared collector budget required')
    if root != library.storage_root():raise ValueError('private storage mismatch')
    if report is None:
        from execution.tablet_catalog_bridge import build_report
        report=build_report(repo)
    if isinstance(report,dict) and not isinstance(report.get('summary',{}),dict):return result
    if (not isinstance(report,dict) or report.get('ok') is not True or report.get('source_errors')
            or report.get('summary',{}).get('source_limit_reached')):return result
    sources,gaps=report.get('source_catalog'),report.get('gap_queue')
    if not isinstance(sources,list) or len(sources)>1500 or not isinstance(gaps,list) or len(gaps)>3000:return result
    wanted={g.get('source_record_id') for g in gaps if isinstance(g,dict) and g.get('direction')=='CATALOG_NEEDS_IMAGE' and isinstance(g.get('source_record_id'),str)}
    now=clock()
    if type(now) not in (int,float) or not math.isfinite(now):raise ValueError('target repair clock')
    history=state.setdefault('target_image_retries_v895',{})
    if (not isinstance(history,dict) or len(history)>1500 or any(not isinstance(k,str) or type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=now+86400 for k,v in history.items())):
        raise ValueError('target retry state')
    for old in list(history):
        if history[old]<=now:del history[old]
    with library.LOCK:
        records=library._load(root)['items']
    known={r.get('source_id') for r in records if isinstance(r,dict) and r.get('provider')=='TCGdex'}
    completed=state.setdefault('completed',{})
    if not isinstance(completed,dict) or len(completed)>4000:raise ValueError('completed state bounds')
    from execution.tablet_catalog_bridge import language_key, norm
    for source in sources:
        if stop.is_set() or result['attempted']>=LIMIT:break
        if not isinstance(source,dict):continue
        ident=source.get('source_record_id')
        if ident not in wanted or not isinstance(ident,str) or not re.fullmatch(r'[0-9a-f]{32}',ident):continue
        if source.get('game_id')!='pokemon' or source.get('kind')!='CARD' or source.get('source_health')!='HEALTHY':continue
        locale=auto.POKEMON_LOCALES.get(source.get('region'))
        if not locale:continue
        url=source.get('source_url')
        if not isinstance(url,str):continue
        u=urlsplit(url)
        if (u.scheme!='https' or u.netloc!='api.tcgdex.net' or u.query or u.fragment):continue
        prefix='/v2/'+locale+'/cards/'
        code=u.path[len(prefix):] if u.path.startswith(prefix) else ''
        if not auto._valid_id(code) or not re.fullmatch(r'[A-Za-z0-9._-]+',code):continue
        metadata=source.get('card_metadata',{})
        if not isinstance(metadata,dict):continue
        language=source.get('language') or metadata.get('language')
        set_code=source.get('set_code') or metadata.get('set_code')
        if language_key(language)!=language_key(locale) or not isinstance(set_code,str) or not set_code:continue
        if source.get('product_codes')!=[norm(code).upper()]:continue
        try:
            checked=datetime.fromisoformat(source.get('source_checked_at','').replace('Z','+00:00'))
            if checked.tzinfo is None or not 0<=now-checked.timestamp()<=7*86400:continue
        except (ValueError,TypeError,AttributeError):continue
        key='pokemon/'+locale+'/'+code
        fingerprint=hashlib.sha256(key.encode()).hexdigest()
        # Completed-but-deleted remains deleted; missing pagination is not consent to restore.
        if key in known or fingerprint in completed or history.get(ident,0)>now:continue
        if len(history)>=1500 and ident not in history:
            result['issues'].append('target retry capacity');break
        history[ident]=now+WAIT
        budget.save();budget.provider='TCGdex';result['attempted']+=1
        try:
            budget.can_save('TCGdex')
            detail=auto.fetch_json(url)
            if not isinstance(detail,dict) or detail.get('id')!=code:raise auto.ProviderError('target card ID mismatch')
            card_set=detail.get('set');local=detail.get('localId');image=detail.get('image')
            if not isinstance(card_set,dict) or norm(card_set.get('id'))!=norm(set_code):raise auto.ProviderError('target set mismatch')
            if not isinstance(local,str) or code!=str(card_set.get('id'))+'-'+local:raise auto.ProviderError('target number mismatch')
            if not isinstance(image,str):raise auto.ProviderError('target image unavailable')
            p=urlsplit(image)
            if (p.scheme!='https' or p.netloc!='assets.tcgdex.net' or p.query or p.fragment
                    or '/tcgp/' in p.path.lower() or not re.fullmatch('/'+locale+r'/[A-Za-z0-9_-]{1,60}/[A-Za-z0-9_-]{1,70}/[A-Za-z0-9_-]{1,65}',p.path)
                    or p.path.split('/')[-2:]!=[card_set.get('id'),local]):raise auto.ProviderError('target image identity mismatch')
            if not isinstance(detail.get('name'),str):raise auto.ProviderError('target card name missing')
            name=auto._safe_name(detail['name'])
            if not name:raise auto.ProviderError('target card name missing')
            fields=auto._metadata(card_code=code,card_number=local,set_code=card_set.get('id'),set_name=card_set.get('name'),language=locale,rarity=detail.get('rarity'),card_type=detail.get('category'))
            if any(k in metadata and metadata[k]!=v for k,v in fields.items()):raise auto.ProviderError('target metadata conflict')
            binary=auto.fetch_binary(image+'/high.webp')
            mime,_=library.sniff(binary)
            added=library.save_image(repo,{'game_id':'pokemon','region':source['region'],'kind':'CARD','name':name+' · '+code,'provider':'TCGdex','source_url':url,'source_id':key,'card_metadata':fields,'image_base64':'data:'+mime+';base64,'+base64.b64encode(binary).decode('ascii')},trusted_auto=True)
            if len(completed)>=3800:completed.pop(next(iter(completed)))
            completed[fingerprint]={'id':added['id'],'provider':'TCGdex','key':key,'source':url}
            budget.record_image('TCGdex',added.get('stored_bytes',0));known.add(key)
            stats=state.setdefault('source_stats',{}).setdefault('pokemon|'+source['region'],{'saved_total':0})
            stats['saved_total']=int(stats.get('saved_total',0))+1
            result['saved']+=1;result['stored_bytes']+=added.get('stored_bytes',0)
            result['compression_bytes_saved']+=max(0,added.get('source_bytes',0)-added.get('stored_bytes',0))
            budget.save()
        except auto.policy.Deferred as exc:
            result['deferred']=True;result['issues'].append(str(exc)[:120]);break
        except (OSError,ValueError,TypeError) as exc:
            result['issues'].append(str(exc)[:120])
    return result
