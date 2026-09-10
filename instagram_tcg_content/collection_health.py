#!/usr/bin/env python3
"""Read-only readiness audit for the single canonical Instagram card-info router."""
from __future__ import annotations
import argparse, json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from instagram_tcg_content.source_registry import validate_registry

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT=ROOT/'TCG_CROSSCHECK'/'IG_CARDINFO'/'factual_snapshot.json'
DEFAULT_ROUTES=ROOT/'instagram_tcg_content'/'source_routes.json'
DEFAULT_REGISTRY=ROOT/'instagram_tcg_content'/'source_registry.json'
EXPECTED_OUTPUTS=(("pokemon","KR"),("pokemon","EN"),("one_piece","KR"),("one_piece","EN"),("naruto","KR"),("naruto","EN"))
GENERAL_FACT_TYPES=frozenset({"release","rerelease","promo","event","movie_bonus"})
MARKET_FACT_TYPES=frozenset({"completed_sale","market_reference","card_price"})
KNOWN_FACT_TYPES=GENERAL_FACT_TYPES|MARKET_FACT_TYPES
MAX_SNAPSHOT_AGE_HOURS=36.0
MAX_FACT_CAPTURE_AGE_HOURS=36.0
MIN_COMPLETED_SALES_PER_OUTPUT=10
MIN_VERIFIED_MARKET_REFERENCES_PER_OUTPUT=1
VERIFICATION_MODE="INSTAGRAM_LOCAL_EVIDENCE_ONLY"
VERIFICATION_ENGINE="instagram_tcg_content.source_verification_engine.py::verify_fact"
MARKET_ONLY_REASON_PREFIXES=("COMPLETED_SALE_COVERAGE_INSUFFICIENT","MARKET_REFERENCE_COVERAGE_INSUFFICIENT","COMPLETED_SALE_ROUTE_SHORTAGE:","MARKET_ROUTE_SHORTAGE:")
GENERAL_ONLY_REASON_PREFIXES=("OUTPUT_MATRIX_COVERAGE_MISSING:","OFFICIAL_ROUTE_SHORTAGE:","GENERAL_LIFECYCLE_MISSING:")


def _parse_aware(value:object)->datetime|None:
    if not isinstance(value,str) or not value.strip(): return None
    try: parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError: return None
    return parsed if parsed.tzinfo is not None else None


def _game_of(row:dict[str,Any])->str:
    identity=row.get('identity')
    if isinstance(identity,dict):
        value=identity.get('game')
        if isinstance(value,str) and value.strip(): return value.strip().lower()
    key=row.get('canonical_key')
    return str(key).split('|',1)[0].strip().lower() if isinstance(key,str) and key.strip() else ''


def _language_of(row:dict[str,Any])->str:
    value=row.get('language')
    if isinstance(value,str) and value.strip(): return value.strip().upper()
    identity=row.get('identity')
    if isinstance(identity,dict):
        value=identity.get('language')
        if isinstance(value,str) and value.strip(): return value.strip().upper()
    return ''


def _validate_routes(routes:dict[str,Any], registry:dict[str,Any]|None)->list[str]:
    problems=[]; groups=routes.get('provider_groups')
    if not isinstance(groups,dict): return ['PROVIDER_GROUPS_MISSING']
    for game in ('pokemon','one_piece','naruto'):
        group=groups.get(game)
        if not isinstance(group,dict): problems.append(f'PROVIDER_GROUP_MISSING:{game}'); continue
        official=set(group.get('official_primary') or [])
        realized=set(group.get('completed_sale_original') or [])|set(group.get('grading_auction_original') or [])
        market=set(group.get('market_reference') or [])
        if len(official)<1: problems.append(f'OFFICIAL_ROUTE_SHORTAGE:{game}:{len(official)}/1')
        if len(realized)<2: problems.append(f'COMPLETED_SALE_ROUTE_SHORTAGE:{game}:{len(realized)}/2')
        if len(market)<2: problems.append(f'MARKET_ROUTE_SHORTAGE:{game}:{len(market)}/2')
    if (routes.get('rules') or {}).get('source_registry_required') is True:
        if registry is None:
            problems.append('SOURCE_REGISTRY_NOT_SUPPLIED')
        else:
            report=validate_registry(registry,routes)
            problems.extend(report.get('errors') or [])
    return problems


def _has_prefix(reason:str,prefixes:tuple[str,...])->bool:
    return any(reason==p or reason.startswith(p) for p in prefixes)


def audit_collection(snapshot:dict[str,Any],routes:dict[str,Any],*,registry:dict[str,Any]|None=None,now:datetime|None=None,min_completed_sales_per_output:int=MIN_COMPLETED_SALES_PER_OUTPUT,min_market_references_per_output:int=MIN_VERIFIED_MARKET_REFERENCES_PER_OUTPUT)->dict[str,Any]:
    current=now or datetime.now(timezone.utc)
    if current.tzinfo is None: raise ValueError('now must be timezone-aware')
    if isinstance(min_completed_sales_per_output,bool) or not isinstance(min_completed_sales_per_output,int) or min_completed_sales_per_output<1: raise ValueError('min_completed_sales_per_output must be >=1')
    if isinstance(min_market_references_per_output,bool) or not isinstance(min_market_references_per_output,int) or min_market_references_per_output<1: raise ValueError('min_market_references_per_output must be >=1')
    reasons=[]; warnings=[]
    if snapshot.get('namespace')!='IG_CARDINFO': reasons.append('SNAPSHOT_NAMESPACE_INVALID')
    if snapshot.get('status')!='finalized': reasons.append('SNAPSHOT_NOT_FINALIZED')
    validation=snapshot.get('validation')
    if not isinstance(validation,dict) or validation.get('write_readback_verified') is not True: reasons.append('SNAPSHOT_WRITE_READBACK_UNVERIFIED')
    built=_parse_aware(snapshot.get('built_at')); age_hours=None
    if built is None: reasons.append('SNAPSHOT_BUILT_AT_INVALID')
    else:
        age_hours=max(0.0,(current.astimezone(timezone.utc)-built.astimezone(timezone.utc)).total_seconds()/3600)
        if age_hours>MAX_SNAPSHOT_AGE_HOURS: reasons.append(f'SNAPSHOT_STALE:{age_hours:.1f}h>{MAX_SNAPSHOT_AGE_HOURS:.0f}h')
    latest=snapshot.get('latest_attempt')
    if isinstance(latest,dict):
        status=str(latest.get('status') or '')
        if status not in {'','finalized','verified_facts_written'}: reasons.append(f'LATEST_COLLECTION_ATTEMPT_NOT_READY:{status}')
    facts=snapshot.get('facts')
    if not isinstance(facts,list): facts=[]; reasons.append('SNAPSHOT_FACTS_INVALID')
    seen=set(); duplicate=malformed=unsupported=stale=0
    general=Counter(); all_counts=Counter(); completed=Counter(); market_refs=Counter(); archived=Counter()
    current_general=archived_general=0
    lifecycle_enforced=str(snapshot.get('schema_version') or '').startswith('1.1') or (isinstance(validation,dict) and validation.get('lifecycle_routing_enforced') is True)
    for raw in facts:
        if not isinstance(raw,dict): malformed+=1; continue
        key=str(raw.get('canonical_key') or '').strip(); fact=str(raw.get('fact_type') or '').strip(); lineage=str(raw.get('lineage_key') or '').strip()
        if not key or not fact or not lineage or raw.get('verification_status')!='verified': malformed+=1; continue
        if raw.get('verification_mode')!=VERIFICATION_MODE or raw.get('verification_engine')!=VERIFICATION_ENGINE: malformed+=1; continue
        if fact not in KNOWN_FACT_TYPES: unsupported+=1; continue
        dedupe=(key,fact,lineage)
        if dedupe in seen: duplicate+=1; continue
        seen.add(dedupe)
        if not str(raw.get('source_locator') or '').strip(): malformed+=1; continue
        game,language=_game_of(raw),_language_of(raw)
        if not game or not language: malformed+=1; continue
        observed=_parse_aware(raw.get('observed_at'))
        if observed is None: malformed+=1; continue
        fact_age=max(0.0,(current.astimezone(timezone.utc)-observed.astimezone(timezone.utc)).total_seconds()/3600)
        all_counts[(game,language)]+=1
        if fact in GENERAL_FACT_TYPES:
            bucket=raw.get('lifecycle_bucket')
            if bucket not in {None,'','CURRENT','ARCHIVE'}: malformed+=1; continue
            if lifecycle_enforced and bucket in {None,''}: reasons.append(f'GENERAL_LIFECYCLE_MISSING:{game}:{language}:{key}'); continue
            if bucket=='ARCHIVE': archived_general+=1; archived[(game,language)]+=1; continue
            if fact_age>MAX_FACT_CAPTURE_AGE_HOURS: stale+=1; continue
            current_general+=1; general[(game,language)]+=1; continue
        if fact_age>MAX_FACT_CAPTURE_AGE_HOURS: stale+=1; continue
        if fact=='completed_sale': completed[(game,language)]+=1
        elif fact=='market_reference': market_refs[(game,language)]+=1
    if malformed: reasons.append(f'MALFORMED_VERIFIED_FACTS:{malformed}')
    if unsupported: reasons.append(f'UNSUPPORTED_VERIFIED_FACT_TYPES:{unsupported}')
    if duplicate: reasons.append(f'DUPLICATE_FACT_LINEAGE:{duplicate}')
    if stale: warnings.append(f'STALE_VERIFIED_FACTS_EXCLUDED:{stale}')
    if not seen: reasons.append('NO_VERIFIED_FACTS')
    missing=[]; sale_short={}; market_short={}
    for game,language in EXPECTED_OUTPUTS:
        if general[(game,language)]<1: missing.append(f'{game}:{language}')
        sc=completed[(game,language)]
        if sc<min_completed_sales_per_output: sale_short[f'{game}:{language}']={'verified_completed_sales':sc,'required':min_completed_sales_per_output}
        mc=market_refs[(game,language)]
        if mc<min_market_references_per_output: market_short[f'{game}:{language}']={'verified_market_references':mc,'required':min_market_references_per_output}
    if missing: reasons.append('OUTPUT_MATRIX_COVERAGE_MISSING:'+','.join(missing))
    if sale_short: reasons.append('COMPLETED_SALE_COVERAGE_INSUFFICIENT')
    if market_short: reasons.append('MARKET_REFERENCE_COVERAGE_INSUFFICIENT')
    route_problems=_validate_routes(routes,registry); reasons.extend(route_problems)
    unique=list(dict.fromkeys(reasons))
    general_block=[r for r in unique if not _has_prefix(r,MARKET_ONLY_REASON_PREFIXES)]
    market_block=[r for r in unique if not _has_prefix(r,GENERAL_ONLY_REASON_PREFIXES)]
    general_ready=not general_block; market_ready=not market_block
    if general_ready and market_ready: status='READY'; next_action='PROCEED_TO_PRODUCTION_PREFLIGHT'
    elif general_ready: status='GENERAL_READY_MARKET_NOT_READY'; next_action='PROCEED_GENERAL_CARDINFO_WITHOUT_UNVERIFIED_MARKET_SECTIONS'
    elif market_ready: status='MARKET_READY_GENERAL_NOT_READY'; next_action='CONTINUE_GENERAL_CARDINFO_COLLECTION'
    else: status='NOT_READY'; next_action='RUN_BOUNDED_FULL_COLLECTION_AND_PERSIST_VERIFIED_IG_FACTS'
    return {'status':status,'production_ready':general_ready,'general_cardinfo_ready':general_ready,'market_price_ready':market_ready,
        'snapshot_built_at':snapshot.get('built_at'),'snapshot_age_hours':None if age_hours is None else round(age_hours,2),'fact_count':len(facts),'unique_fact_count':len(seen),
        'freshness_excluded_fact_count':stale,'warnings':warnings,'current_general_fact_count':current_general,'archived_general_fact_count':archived_general,
        'matrix_counts':{f'{g}:{l}':general[(g,l)] for g,l in EXPECTED_OUTPUTS},'all_verified_matrix_counts':{f'{g}:{l}':all_counts[(g,l)] for g,l in EXPECTED_OUTPUTS},
        'archive_matrix_counts':{f'{g}:{l}':archived[(g,l)] for g,l in EXPECTED_OUTPUTS},'completed_sale_counts':{f'{g}:{l}':completed[(g,l)] for g,l in EXPECTED_OUTPUTS},
        'market_reference_counts':{f'{g}:{l}':market_refs[(g,l)] for g,l in EXPECTED_OUTPUTS},'completed_sale_shortage':sale_short,'market_reference_shortage':market_short,
        'route_problems':route_problems,'reasons':unique,'general_blocking_reasons':general_block,'market_blocking_reasons':market_block,'next_action':next_action}


def self_test()->None:
    now=datetime(2026,9,11,0,0,tzinfo=timezone.utc)
    routes={'provider_groups':{g:{'official_primary':['official'],'completed_sale_original':['sale-a','sale-b'],'grading_auction_original':[],'market_reference':['market-a','market-b']} for g in ('pokemon','one_piece','naruto')}}
    base={'verification_status':'verified','verification_mode':VERIFICATION_MODE,'verification_engine':VERIFICATION_ENGINE,'observed_at':'2026-09-11T08:30:00+09:00'}
    general=[]; sales=[]; refs=[]
    for game,language in EXPECTED_OUTPUTS:
        general.append({**base,'canonical_key':f'{game}|release|{language}','fact_type':'release','content_type':'release','lifecycle_bucket':'CURRENT','lineage_key':f'{game}:{language}:release','identity':{'game':game},'language':language,'source_locator':'https://example.invalid/official'})
        refs.append({**base,'canonical_key':f'{game}|market|{language}','fact_type':'market_reference','lineage_key':f'{game}:{language}:market','identity':{'game':game},'language':language,'source_locator':'https://example.invalid/market'})
        for i in range(MIN_COMPLETED_SALES_PER_OUTPUT): sales.append({**base,'canonical_key':f'{game}|sale-{i}|{language}','fact_type':'completed_sale','lineage_key':f'{game}:{language}:sale:{i}','identity':{'game':game},'language':language,'source_locator':'https://example.invalid/sale'})
    def snap(rows): return {'schema_version':'1.1-lifecycle','namespace':'IG_CARDINFO','status':'finalized','built_at':'2026-09-11T08:30:00+09:00','facts':rows,'validation':{'write_readback_verified':True,'lifecycle_routing_enforced':True},'latest_attempt':{'status':'verified_facts_written'}}
    ready=audit_collection(snap(general+sales+refs),routes,now=now); assert ready['general_cardinfo_ready'] and ready['market_price_ready'],ready
    sales_only=audit_collection(snap(sales+refs),routes,now=now); assert not sales_only['general_cardinfo_ready'] and sales_only['market_price_ready'],sales_only
    no_refs=audit_collection(snap(general+sales),routes,now=now); assert no_refs['general_cardinfo_ready'] and not no_refs['market_price_ready'],no_refs
    stale=[{**x,'observed_at':'2026-09-08T00:00:00+09:00'} for x in general+sales+refs]
    stale_report=audit_collection(snap(stale),routes,now=now); assert not stale_report['general_cardinfo_ready'] and not stale_report['market_price_ready'] and stale_report['freshness_excluded_fact_count']>0,stale_report
    archived_rows=[{**x,'lifecycle_bucket':'ARCHIVE'} for x in general]
    archived_report=audit_collection(snap(archived_rows+sales+refs),routes,now=now); assert not archived_report['general_cardinfo_ready'] and archived_report['archived_general_fact_count']==6,archived_report
    print('Instagram TCG collection health freshness/market split: PASS')


def main()->int:
    p=argparse.ArgumentParser(); p.add_argument('--snapshot',default=str(DEFAULT_SNAPSHOT)); p.add_argument('--routes',default=str(DEFAULT_ROUTES)); p.add_argument('--registry',default=str(DEFAULT_REGISTRY)); p.add_argument('--strict',action='store_true'); p.add_argument('--self-test',action='store_true'); a=p.parse_args()
    if a.self_test: self_test(); return 0
    snapshot=json.loads(Path(a.snapshot).read_text(encoding='utf-8')); routes=json.loads(Path(a.routes).read_text(encoding='utf-8')); registry=json.loads(Path(a.registry).read_text(encoding='utf-8')) if Path(a.registry).is_file() else None
    report=audit_collection(snapshot,routes,registry=registry); print(json.dumps(report,ensure_ascii=False,indent=2)); return 2 if a.strict and not report['production_ready'] else 0

if __name__=='__main__': raise SystemExit(main())
