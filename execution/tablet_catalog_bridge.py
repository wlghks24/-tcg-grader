"""Rebuilt private catalog/image reconciliation. No fetch, image upload or source writes.

Compatibility output v46 is derived from the caller contract, not recovered v43 code.
Metadata joins require a unique exact identifier, game, edition and product kind.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlsplit

import tablet_image_library_v1 as library

IMPLEMENTATION='rebuilt-private-catalog-v2'
REGIONS={'KR','JP','US','CN-S','CN-T'}
KINDS={'CARD','PROMO','BOX','PACK','DECK','COLLECTION','BUNDLE','ACCESSORY','OTHER'}
MAX_SOURCES=1500
MAX_SOURCE_BYTES=8_000_000
MAX_GAPS=3000
CODE_PATTERNS={
 'onepiece':r'(?<![A-Z0-9])(?:OPK?|STK?|EBK?|PRBK?)-?\d{2}(?:-\d{3})?(?![A-Z0-9])',
 'pokemon':r'(?<![A-Z0-9])(?:SV\d{1,2}[A-Z]?|SM\d{1,2}[A-Z]?|S\d{1,2}[A-Z]?|XY\d{1,2}|BW\d{1,2})(?:-\d{1,3})?(?![A-Z0-9])',
 'gundam':r'(?<![A-Z0-9])(?:GD|ST|EX)\d{2}(?:-\d{3})?(?![A-Z0-9])',
}


def text(value,limit=175):
    return value.strip() if isinstance(value,str) and 0<len(value.strip())<=limit and not any(ord(c)<32 for c in value) else ''


def norm(value):
    return ''.join(c for c in unicodedata.normalize('NFKC',str(value)).casefold() if c.isalnum())


def safe_url(value):
    value=text(value,2048)
    if not value:return ''
    try:
        u=urlsplit(value);host=u.hostname or ''
        if u.scheme!='https' or u.username or u.password or u.port not in (None,443) or not host or '.' not in host or host.endswith(('.local','.localhost')) or re.search(r'[\s\\]',value):return ''
        try:
            if not ipaddress.ip_address(host).is_global:return ''
        except ValueError:pass
        return value
    except ValueError:return ''


def read_json(path,limit):
    if path.is_symlink() or not path.is_file() or path.stat().st_size>limit:raise ValueError('unsafe_or_missing_json:'+path.name)
    def pairs(rows):
        result={}
        for key,value in rows:
            if key in result:raise ValueError('duplicate_json_key')
            result[key]=value
        return result
    result=json.loads(path.read_text(encoding='utf-8'),object_pairs_hook=pairs,
                      parse_constant=lambda value:(_ for _ in ()).throw(ValueError('invalid_json_number')))
    if not isinstance(result,dict):raise ValueError('json_object_required')
    return result


def registry(repo):
    d=read_json(repo/'tcg_game_registry.json',1_000_000)
    if d.get('schema_version')!=1 or not isinstance(d.get('games'),list) or len(d['games'])>200:raise ValueError('registry_schema')
    games={};aliases=defaultdict(set)
    for r in d['games']:
        if not isinstance(r,dict) or not re.fullmatch(r'[a-z0-9-]{2,64}',str(r.get('id',''))):raise ValueError('registry_identity')
        ident=r['id']
        if ident in games:raise ValueError('duplicate_game')
        games[ident]=r
        names=[ident,r.get('canonical'),r.get('label_ko')]
        if isinstance(r.get('aliases'),list):names+=r['aliases'][:40]
        for name in names:
            if text(name):aliases[norm(name)].add(ident)
    return games,{k:next(iter(v)) for k,v in aliases.items() if len(v)==1}


def game_id(row,games,aliases):
    explicit=row.get('registry_game_id') or row.get('game_id')
    inferred=aliases.get(norm(row.get('game','')))
    if explicit:
        return explicit if explicit in games and (not inferred or inferred==explicit) else ''
    return inferred or ''


def codes(game,row):
    found=set()
    metadata=row.get('card_metadata',{})
    if not isinstance(metadata,dict):metadata={}
    for key in ('product_code','set_code','card_code','card_number'):
        # A card set code alone cannot identify a single card/printing.
        value=row.get(key) or (metadata.get(key) if key in ('card_code','card_number') else None)
        if isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9/-]{1,39}',value) and re.search('[A-Za-z]',value) and re.search('[0-9]',value):found.add(norm(value).upper())
    pattern=CODE_PATTERNS.get(game)
    if pattern:
        # Never extract numeric IDs or substrings from opaque provider URLs/UUIDs.
        for value in (row.get('name',''),row.get('native',''),str(row.get('source_id','')).split('/')[-1]):
            if isinstance(value,str):found.update(norm(x).upper() for x in re.findall(pattern,value.upper()))
    return sorted(found)[:12]


def kind(row,default='OTHER'):
    value=str(row.get('product_kind') or row.get('asset') or row.get('product_type') or row.get('kind') or '').upper()
    if value=='HIT':return 'CARD'
    if value in KINDS:return value
    return default


def source_rows(repo,games,aliases):
    result=[];errors=[];seen=set();rejected=0;truncated=False
    for filename in ('releases.json','market_watch.json','market_prices.json'):
        try:
            d=read_json(repo/filename,MAX_SOURCE_BYTES)
            if filename=='market_prices.json':
                entries=d.get('entries')
                if not isinstance(entries,dict):raise ValueError('entries_schema')
                rows=[]
                if len(entries)>10000:raise ValueError('source_row_limit')
                for key,row in entries.items():
                    parts=key.split('|')
                    if len(parts)==3 and isinstance(row,dict):rows.append({**row,'region':parts[0],'name':parts[1],'asset':parts[2]})
                    else:rejected+=1
            else:
                rows=d.get('items')
                if not isinstance(rows,list) or len(rows)>10000:raise ValueError('items_schema')
                rows=list(rows)
                extra=d.get('archive_items',[]) if filename=='releases.json' else d.get('china_catalog',{}).get('items',[]) if isinstance(d.get('china_catalog',{}),dict) else []
                if not isinstance(extra,list) or len(extra)>10000:raise ValueError('extra_items_schema')
                rows+=extra
            for row in rows:
                if not isinstance(row,dict):rejected+=1;continue
                game=game_id(row,games,aliases);region=row.get('region');name=text(row.get('name'));url=safe_url(row.get('source'))
                if not game or region not in REGIONS or not name or not url:rejected+=1;continue
                k=kind(row);code=codes(game,row)
                identity=(game,region,k,norm(name),url)
                if identity in seen:continue
                seen.add(identity)
                if len(result)>=MAX_SOURCES:truncated=True;continue
                out={'source_record_id':hashlib.sha256(json.dumps(identity,ensure_ascii=False).encode()).hexdigest()[:32],
                     'game_id':game,'region':region,'kind':k,'name':name,'source_url':url,
                     'signal':'releases' if filename=='releases.json' else 'market','product_codes':code,
                     'source_health':'HEALTHY' if row.get('link_status')=='정상' else 'UNVERIFIED',
                     'source_dataset':filename,'source_checked_at':text(row.get('last_verified_at') or row.get('link_checked_at'),80)}
                # Facts retain source lineage; never turn a listing into verified pricing/grade.
                date=text(row.get('release_date'),10)
                if date:
                    try:
                        datetime.strptime(date,'%Y-%m-%d')
                        if len(date)==10:out['observed_release_date']=date
                    except ValueError:pass
                result.append(out)
        except (OSError,ValueError,TypeError,UnicodeError) as exc:
            errors.append({'dataset':filename,'error':type(exc).__name__})
    return result,errors,rejected,truncated


def local_rows(root,games):
    with library.LOCK:
        payload=library._load(root)
        rows=[];seen=set();missing=[]
        for r in payload['items']:
            if (not isinstance(r,dict) or not re.fullmatch(r'[a-f0-9]{32}',str(r.get('id',''))) or r['id'] in seen
                or r.get('game_id') not in games or r.get('region') not in REGIONS or r.get('kind') not in KINDS or not text(r.get('name'),130)):
                raise ValueError('private_index_identity')
            seen.add(r['id'])
            path=root/'images'/library._image_filename(r)
            if path.is_symlink():raise ValueError('private_image_symlink')
            if not path.is_file() or type(r.get('bytes')) is not int or path.stat().st_size!=r['bytes'] or not 24<=r['bytes']<=library.MAX_IMAGE_BYTES:
                missing.append(r['id']);continue
            out={k:r[k] for k in ('id','game_id','region','kind','name')}
            out.update(image_url='/api/local-card-images/file/'+r['id'],linked_to_existing_catalog=False,
                       identity_verification='UNLINKED',file_validation='PRESENCE_AND_SIZE_SHA256_CHECKED_ON_SERVE',
                       product_codes=codes(r['game_id'],r))
            for key,limit in (('provider',35),('source_id',140)):
                if text(r.get(key),limit):out[key]=r[key]
            if safe_url(r.get('source_url')):out['source_url']=r['source_url']
            if isinstance(r.get('image_storage'),dict):out['image_storage']=r['image_storage']
            metadata=r.get('card_metadata',{})
            if not isinstance(metadata,dict) or set(metadata)-set(library.CARD_METADATA_LIMITS):raise ValueError('private_card_metadata')
            if any(not text(v,library.CARD_METADATA_LIMITS[k]) for k,v in metadata.items()):raise ValueError('private_card_metadata')
            if metadata:out['card_metadata']=dict(metadata)
            if r['kind'] in ('CARD','PROMO'):
                out['missing_metadata_fields']=(['card_code'] if not metadata.get('card_code') else [])+([] if metadata.get('set_code') or metadata.get('set_name') else ['set_reference'])
                out['metadata_status']='MISSING_CARD_METADATA' if out['missing_metadata_fields'] else 'PROVIDER_METADATA_PRESENT'
            rows.append(out)
    return rows,missing,len(payload['items'])


def build_report(repo):
    repo=Path(repo);issues=[]
    try:
        games,aliases=registry(repo)
        root=library.storage_root()
        images,missing,total=local_rows(root,games)
        sources,errors,rejected,truncated=source_rows(repo,games,aliases)
    except (OSError,ValueError,TypeError,UnicodeError) as exc:
        return {'ok':False,'version':46,'implementation':IMPLEMENTATION,'error':type(exc).__name__,
                'local_catalog':[],'source_catalog':[],'catalog_matches':[],'summary':{},'physical_tablet_verified':False}
    index=defaultdict(set);reverse=defaultdict(set)
    for s in sources:
        for code in s['product_codes']:index[(s['game_id'],s['region'],s['kind'],code)].add(s['source_record_id'])
    for image in images:
        for code in image['product_codes']:reverse[(image['game_id'],image['region'],image['kind'],code)].add(image['id'])
    source_map={s['source_record_id']:s for s in sources};matches=[];gaps=[];linked_sources=set();priority=Counter();ambiguous=0;metadata_gaps=0
    for image in images:
        metadata_missing=image.get('missing_metadata_fields',[])
        if metadata_missing:metadata_gaps+=1
        keys=[(image['game_id'],image['region'],image['kind'],c) for c in image['product_codes']]
        refs=set().union(*(index[k] for k in keys)) if keys else set()
        # Ambiguous images sharing a code cannot displace another image/printing.
        unique_images=all(len(reverse[k])==1 for k in keys)
        if not errors and not truncated and len(refs)==1 and source_map[next(iter(refs))]['source_health']=='HEALTHY' and unique_images and set(image['product_codes'])==set(source_map[next(iter(refs))]['product_codes']):
            s=source_map[next(iter(refs))]
            image.update(linked_to_existing_catalog=True,identity_verification='CODE_MATCH',
                         linked_source_record_id=s['source_record_id'],metadata_evidence={k:s[k] for k in ('name','source_url','source_dataset','source_checked_at','product_codes')})
            matches.append({'id':image['id'],'image_url':image['image_url'],'game_id':image['game_id'],
                            'region':image['region'],'kind':image['kind'],'catalog_kind':s['kind'],
                            'catalog_name':s['name'],'source_record_id':s['source_record_id'],'match':'CODE_MATCH'})
            linked_sources.add(s['source_record_id'])
            if metadata_missing:
                gaps.append({'direction':'IMAGE_NEEDS_METADATA','image_id':image['id'],'game_id':image['game_id'],
                             'region':image['region'],'kind':image['kind'],'name':image['name'],
                             'source_url':image.get('source_url',''),'source_id':image.get('source_id',''),
                             'reason':'CARD_METADATA_INCOMPLETE','missing_fields':metadata_missing,
                             'auto_download':False,'requires_verified_identity':True})
        else:
            reason='DATASET_INCOMPLETE' if errors or truncated else 'SOURCE_RECHECK_REQUIRED' if len(refs)==1 and source_map[next(iter(refs))]['source_health']!='HEALTHY' else 'AMBIGUOUS_CODE' if refs else 'NO_EXACT_IDENTIFIER_MATCH'
            if refs:ambiguous+=1
            gaps.append({'direction':'IMAGE_NEEDS_METADATA','image_id':image['id'],'game_id':image['game_id'],
                         'region':image['region'],'kind':image['kind'],'name':image['name'],'product_codes':image['product_codes'],
                         'reason':reason,'missing_fields':metadata_missing,
                         'source_url':image.get('source_url',''),'source_id':image.get('source_id',''),
                         'auto_download':False,'requires_verified_identity':True})
    for s in sources:
        if s['source_record_id'] in linked_sources:continue
        gaps.append({'direction':'CATALOG_NEEDS_IMAGE','source_record_id':s['source_record_id'],
                     'game_id':s['game_id'],'region':s['region'],'kind':s['kind'],'name':s['name'],
                     'product_codes':s['product_codes'],'source_url':s['source_url'],
                     'reason':'NO_UNIQUE_LOCAL_IMAGE','auto_download':False,'requires_verified_identity':True})
        priority[(s['game_id'],s['region'])]+=1
    summary={'catalog_records_analyzed':len(sources),'catalog_records_scanned':len(sources),
             'local_files_present':len(images),'local_all_photos':total,'auto_linked':len(matches),
             'image_backed_card_records':sum(x['kind'] in ('CARD','PROMO') for x in images),
             'image_backed_product_records':sum(x['kind'] not in ('CARD','PROMO') for x in images),
             'catalog_to_image_gaps':len(sources)-len(linked_sources),'image_to_catalog_gaps':len(images)-len(matches),'card_metadata_gaps':metadata_gaps,
             'missing_local_files':len(missing),'ambiguous_images':ambiguous,'source_errors':len(errors),
             'rejected_source_rows':rejected,'source_limit_reached':truncated,'queue_truncated':len(gaps)>MAX_GAPS}
    return {'ok':True,'version':46,'implementation':IMPLEMENTATION,'summary':summary,'local_catalog':images,
            'source_catalog':sources,'catalog_matches':matches,'gap_queue':gaps[:MAX_GAPS],
            'collection_priorities':[{'game_id':g,'region':r,'missing_images':n} for (g,r),n in sorted(priority.items())],
            'source_errors':errors,'missing_image_ids':missing,'physical_tablet_verified':False,
            'prices_inferred':False,'grades_inferred':False,'model_training_performed':False}


def write_gap_queue(repo):
    report=build_report(repo)
    if not report['ok'] or report['source_errors']:return {'ok':False,'status':'HOLD_PREVIOUS_QUEUE_PRESERVED','implementation':IMPLEMENTATION}
    root=library.storage_root()
    payload={'schema':'tablet-private-evidence-gaps/v2','implementation':IMPLEMENTATION,
             'updated_at':datetime.now(timezone.utc).isoformat(),'summary':report['summary'],
             'tasks':report['gap_queue'],'collection_priorities':report['collection_priorities'],
             'source_errors':report['source_errors'],'no_source_rewrite':True,'no_remote_execution':True}
    destination=root/'collection_gap_queue_v2.json'
    if destination.is_symlink():raise ValueError('unsafe_gap_queue')
    data=(json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n').encode()
    if len(data)>2_000_000:raise ValueError('gap_queue_bytes_limit')
    with library.LOCK:library._atomic_write(destination,data)
    return {'ok':True,'status':'PRIVATE_GAP_QUEUE_UPDATED','summary':report['summary'],'implementation':IMPLEMENTATION}
