#!/usr/bin/env python3
"""Fail-closed completed-sale / market-reference bridge for IG card-info."""
from __future__ import annotations
import argparse, hashlib, json, os, re, tempfile
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median
from typing import Any, Callable, Iterable
from instagram_tcg_content.source_verification_engine import Observation, VerificationResult, verify_fact

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY=Path(__file__).resolve().with_name('source_registry.json')
DEFAULT_LEDGER=ROOT/'TCG_CROSSCHECK'/'IG_CARDINFO'/'market_evidence_ledger.json'
KST=timezone(timedelta(hours=9))
VERIFICATION_MODE='INSTAGRAM_LOCAL_EVIDENCE_ONLY'
VERIFICATION_ENGINE='instagram_tcg_content.source_verification_engine.py::verify_fact'
MAX_MARKET_REFERENCE_RELATIVE_SPREAD=Decimal('0.35')
FINALITY_TO_ENGINE={'auction_house_realized':'realized','platform_reported_sold':'completed','final':'final','settled':'settled','closed':'closed','completed':'completed','complete':'complete','realized':'realized'}
NON_PROMOTABLE_FINALITY={'settlement_unknown'}
STATUS_TO_ENGINE={'sold':'sold','completed':'completed','ended_sold':'sold','realized':'realized','closed':'closed','settled':'settled'}
COMPLETED_REQUIRED=('canonical_identity','game','region','language','item_or_lot_locator','sold_or_completed_status','event_or_trade_time','currency','realized_amount','condition_or_grade_basis','transaction_finality','price_basis','source_code','source_locator','unit_type','quantity_basis','underlying_lineage_key')
MARKET_REQUIRED=('canonical_identity','game','region','language','value','currency','condition_basis','source_code','source_locator','underlying_lineage_key','unit_type','quantity_basis')

def _clean(v:Any)->str:return str(v or '').strip()
def _dec(v:Any,field:str)->Decimal:
    try:x=Decimal(_clean(v).replace(',',''))
    except (InvalidOperation,ValueError) as e:raise ValueError(f'{field.upper()}_INVALID') from e
    if not x.is_finite() or x<=0:raise ValueError(f'{field.upper()}_INVALID')
    return x
def _fmt(x:Decimal)->str:
    s=format(x.normalize(),'f');return '0' if s=='-0' else s
def _qty(v:Any)->int:
    if isinstance(v,bool):raise ValueError('QUANTITY_BASIS_INVALID')
    try:x=Decimal(_clean(v))
    except (InvalidOperation,ValueError) as e:raise ValueError('QUANTITY_BASIS_INVALID') from e
    if not x.is_finite() or x!=x.to_integral_value() or x<=0:raise ValueError('QUANTITY_BASIS_INVALID')
    return int(x)
def _aware(v:Any,field:str)->str:
    raw=_clean(v)
    try:d=datetime.fromisoformat(raw.replace('Z','+00:00'))
    except ValueError as e:raise ValueError(f'{field.upper()}_INVALID') from e
    if d.tzinfo is None:raise ValueError(f'{field.upper()}_TIMEZONE_REQUIRED')
    return d.isoformat(timespec='seconds')
def _cond(v:Any)->tuple[str,str|None]:
    raw=' '.join(_clean(v).upper().replace('_',' ').split())
    if not raw:raise ValueError('CONDITION_BASIS_REQUIRED')
    m=re.fullmatch(r'(PSA|BGS|CGC|TAG|BRG)\s*([0-9]+(?:\.[0-9]+)?)',raw)
    return ('graded',f'{m.group(1)} {m.group(2)}') if m else (raw.lower().replace(' ','_'),None)
def _digest(v:str)->str:return hashlib.sha256(v.casefold().encode()).hexdigest()[:16]
def _required(row:dict[str,Any],fields:Iterable[str])->None:
    missing=[k for k in fields if row.get(k) in (None,'')]
    if missing:raise ValueError('MARKET_EVIDENCE_MISSING:'+','.join(missing))
def _load_registry()->dict[str,Any]:
    value=json.loads(DEFAULT_REGISTRY.read_text(encoding='utf-8'))
    if not isinstance(value,dict) or not isinstance(value.get('providers'),dict):raise ValueError('SOURCE_REGISTRY_INVALID')
    return value
def _index(reg:dict[str,Any])->dict[str,tuple[str,str]]:
    out={}
    for pid,e in (reg.get('providers') or {}).items():
        if not isinstance(e,dict):continue
        for code in e.get('source_codes') or []:
            key=_clean(code).upper()
            if key in out and out[key][0]!=pid:raise ValueError(f'SOURCE_CODE_COLLISION:{key}')
            out[key]=(_clean(pid),_clean(e.get('tier')))
    return out
def _provider(row:dict[str,Any],idx:dict[str,tuple[str,str]],tiers:set[str])->tuple[str,str]:
    code=_clean(row.get('source_code')).upper();hit=idx.get(code)
    if not hit:raise ValueError(f'SOURCE_REGISTRY_UNRESOLVED_PROVIDER:{code or "MISSING"}')
    if hit[1] not in tiers:raise ValueError(f'SOURCE_TIER_NOT_ALLOWED:{code}:{hit[1]}')
    return hit

def _sale(row:dict[str,Any],idx:dict[str,tuple[str,str]],now:datetime)->dict[str,Any]:
    _required(row,COMPLETED_REQUIRED);pid,tier=_provider(row,idx,{'completed_sale_original','grading_auction_original'})
    fin=_clean(row['transaction_finality']).lower()
    if fin in NON_PROMOTABLE_FINALITY:raise ValueError('SALE_SETTLEMENT_UNKNOWN_NOT_PROMOTABLE')
    engine_fin=FINALITY_TO_ENGINE.get(fin)
    if not engine_fin:raise ValueError(f'SALE_FINALITY_UNSUPPORTED:{fin}')
    status=STATUS_TO_ENGINE.get(_clean(row['sold_or_completed_status']).lower())
    if not status:raise ValueError('SALE_FINAL_STATUS_INVALID')
    event=_aware(row['event_or_trade_time'],'event_or_trade_time');checked=_aware(row.get('checked_at') or now.isoformat(),'checked_at')
    amount=_dec(row['realized_amount'],'realized_amount');q=_qty(row['quantity_basis']);unit=_clean(row['unit_type']).lower()
    if q!=1 or unit!='single_card':raise ValueError('UNIT_QUANTITY_BASIS_MIX')
    cur=_clean(row['currency']).upper();condition,grade=_cond(row['condition_or_grade_basis'])
    identity=_clean(row['canonical_identity']);game=_clean(row['game']).lower();region=_clean(row['region']).upper();lang=_clean(row['language']).upper();basis=_clean(row['price_basis']).lower();lineage=_clean(row['underlying_lineage_key']);locator=_clean(row['item_or_lot_locator'])
    if len(cur)!=3 or not cur.isalpha():raise ValueError('CURRENCY_INVALID')
    if not all((identity,game,region,lang,basis,lineage,locator)):raise ValueError('SALE_IDENTITY_OR_PROVENANCE_MISSING')
    key='completed_sale|'+'|'.join((game,region,lang,_digest(identity),cur,condition,grade or '',basis,unit,str(q),fin))
    obs=Observation(game=game,fact_type='completed_sale',canonical_key=key,value=_fmt(amount),source_code=_clean(row['source_code']).upper(),source_name=_clean(row['source_code']).upper(),source_locator=locator,source_tier=tier,collector_id='market_evidence_bridge:completed_sale',provider_id=pid,fetched_at_kst=checked,event_or_trade_time=event,status=status,original_currency=cur,condition=condition,grade=grade,finality=engine_fin,price_basis=basis,quantity=q,unit=unit,lineage_key=lineage)
    return {'kind':'completed_sale','key':key,'provider_id':pid,'tier':tier,'lineage':lineage,'finality':fin,'amount':_fmt(amount),'currency':cur,'condition':condition,'grade':grade,'basis':basis,'quantity':q,'unit':unit,'event':event,'checked':checked,'raw':dict(row),'obs':obs}

def _ref(row:dict[str,Any],idx:dict[str,tuple[str,str]],now:datetime)->dict[str,Any]:
    _required(row,MARKET_REQUIRED);pid,tier=_provider(row,idx,{'market_reference'})
    if _clean(row.get('value_type') or 'market_reference').lower() not in {'market_reference','market_price','index'}:raise ValueError('MARKET_REFERENCE_VALUE_TYPE_INVALID')
    val=_dec(row['value'],'market_reference_value');cur=_clean(row['currency']).upper();condition,grade=_cond(row['condition_basis']);q=_qty(row['quantity_basis']);unit=_clean(row['unit_type']).lower();checked=_aware(row.get('checked_at') or now.isoformat(),'checked_at')
    identity=_clean(row['canonical_identity']);game=_clean(row['game']).lower();region=_clean(row['region']).upper();lang=_clean(row['language']).upper();lineage=_clean(row['underlying_lineage_key']);locator=_clean(row['source_locator'])
    if len(cur)!=3 or not cur.isalpha():raise ValueError('CURRENCY_INVALID')
    if q!=1 or unit!='single_card':raise ValueError('UNIT_QUANTITY_BASIS_MIX')
    if not all((identity,game,region,lang,lineage,locator)):raise ValueError('MARKET_REFERENCE_IDENTITY_OR_PROVENANCE_MISSING')
    key='market_reference|'+'|'.join((game,region,lang,_digest(identity),cur,condition,grade or '',unit,str(q)))
    return {'kind':'market_reference','key':key,'provider_id':pid,'tier':tier,'lineage':lineage,'value':val,'currency':cur,'condition':condition,'grade':grade,'quantity':q,'unit':unit,'checked':checked,'identity':identity,'game':game,'region':region,'language':lang,'source_code':_clean(row['source_code']).upper(),'source_locator':locator,'raw':dict(row)}

def _signature(x:dict[str,Any])->tuple[Any,...]:
    if x['kind']=='completed_sale':return (x['key'],x['amount'],x['event'],x['finality'],x['basis'],x['condition'],x.get('grade'))
    return (x['key'],_fmt(x['value']),x['currency'],x['condition'],x.get('grade'))
def _dedupe(rows:list[dict[str,Any]])->tuple[list[dict[str,Any]],list[dict[str,Any]]]:
    by=defaultdict(list)
    for x in rows:by[x['lineage']].append(x)
    keep=[];reject=[]
    for lineage,group in by.items():
        if len({_signature(x) for x in group})>1:
            reject += [{'lineage_key':lineage,'source_code':_clean(x['raw'].get('source_code')).upper(),'error':'EVIDENCE_LINEAGE_CONFLICT'} for x in group];continue
        keep.append(group[0]);reject += [{'lineage_key':lineage,'source_code':_clean(x['raw'].get('source_code')).upper(),'error':'DUPLICATE_EVIDENCE_LINEAGE'} for x in group[1:]]
    return keep,reject

def _sale_output(group:list[dict[str,Any]],verifier:Callable[...,VerificationResult],now:datetime)->tuple[list[dict[str,Any]],dict[str,Any]]:
    result=verifier([x['obs'] for x in group],now=now);detail=asdict(result)
    if result.status!='verified':return [],detail
    out=[]
    for x in group:
        r=x['raw'];out.append({'canonical_key':x['key'],'fact_type':'completed_sale','information_family':'completed_sale','lineage_key':x['lineage'],'identity':{'game':x['obs'].game,'region':_clean(r['region']).upper(),'language':_clean(r['language']).upper(),'canonical_identity':_clean(r['canonical_identity']),'transaction_finality':x['finality'],'price_basis':x['basis'],'condition_basis':_clean(r['condition_or_grade_basis']),'unit_type':x['unit'],'quantity_basis':x['quantity']},'value':x['amount'],'value_type':'completed_sale','currency':x['currency'],'region':_clean(r['region']).upper(),'language':_clean(r['language']).upper(),'condition':x['condition'],'grade':x.get('grade'),'observed_at':x['checked'],'source_role':_clean(r['source_code']).upper(),'source_locator':_clean(r['item_or_lot_locator']),'verification':'verified','verification_status':'verified','verification_mode':VERIFICATION_MODE,'verification_engine':VERIFICATION_ENGINE})
    return out,detail

def _ref_output(group:list[dict[str,Any]],cap:Decimal,verifier:Callable[...,VerificationResult],now:datetime)->tuple[list[dict[str,Any]],dict[str,Any]]:
    providers={x['provider_id'] for x in group}
    if len(providers)<2:return [],{'canonical_key':group[0]['key'],'status':'partial','uncertainty_reason':'needs 2 independent market-reference providers'}
    vals=sorted(x['value'] for x in group);med=Decimal(str(median(vals)));lo,hi=vals[0],vals[-1];spread=(hi-lo)/med
    if spread>cap:return [],{'canonical_key':group[0]['key'],'status':'conflict','uncertainty_reason':'MARKET_REFERENCE_DISPERSION_TOO_WIDE','relative_spread':_fmt(spread),'max_relative_spread':_fmt(cap),'low':_fmt(lo),'high':_fmt(hi),'median':_fmt(med),'provider_count':len(providers)}
    agg=_fmt(med);token=f"{group[0]['currency']}|median={agg}|range={_fmt(lo)}-{_fmt(hi)}|n={len(providers)}"
    obs=[Observation(game=x['game'],fact_type='market_reference',canonical_key=x['key'],value=token,source_code=x['source_code'],source_name=x['source_code'],source_locator=x['source_locator'],source_tier='market_reference',collector_id='market_evidence_bridge:market_reference',provider_id=x['provider_id'],fetched_at_kst=x['checked'],status='observed',original_currency=x['currency'],condition=x['condition'],grade=x.get('grade'),price_basis='market_reference',quantity=x['quantity'],unit=x['unit'],lineage_key=x['lineage']) for x in group]
    result=verifier(obs,now=now);detail=asdict(result)|{'derived_median':agg,'derived_low':_fmt(lo),'derived_high':_fmt(hi),'relative_spread':_fmt(spread),'provider_count':len(providers)}
    if result.status!='verified':return [],detail
    out=[]
    for x in group:
        out.append({'canonical_key':x['key'],'fact_type':'market_reference','information_family':'market_reference','lineage_key':x['lineage'],'identity':{'game':x['game'],'region':x['region'],'language':x['language'],'canonical_identity':x['identity'],'condition_basis':x['condition'],'unit_type':x['unit'],'quantity_basis':x['quantity'],'market_reference_low':_fmt(lo),'market_reference_high':_fmt(hi),'market_reference_median':agg,'market_reference_provider_count':len(providers),'market_reference_relative_spread':_fmt(spread)},'value':agg,'value_type':'market_reference_median','currency':x['currency'],'region':x['region'],'language':x['language'],'condition':x['condition'],'grade':x.get('grade'),'observed_at':x['checked'],'source_role':x['source_code'],'source_locator':x['source_locator'],'verification':'verified','verification_status':'verified','verification_mode':VERIFICATION_MODE,'verification_engine':VERIFICATION_ENGINE})
    return out,detail

def verify_market_records(rows:list[dict[str,Any]],*,registry:dict[str,Any]|None=None,now:datetime|None=None,max_market_relative_spread:Decimal=MAX_MARKET_REFERENCE_RELATIVE_SPREAD,verifier:Callable[...,VerificationResult]=verify_fact)->dict[str,Any]:
    if not isinstance(rows,list):raise ValueError('MARKET_RECORD_LIST_REQUIRED')
    current=now or datetime.now(KST)
    if current.tzinfo is None:raise ValueError('now must be timezone-aware')
    if not isinstance(max_market_relative_spread,Decimal) or max_market_relative_spread<=0:raise ValueError('MAX_MARKET_RELATIVE_SPREAD_INVALID')
    idx=_index(registry or _load_registry());norm=[];rejected=[]
    for i,row in enumerate(rows):
        if not isinstance(row,dict):rejected.append({'index':i,'error':'MARKET_EVIDENCE_ROW_INVALID'});continue
        kind=_clean(row.get('value_type') or row.get('fact_type')).lower()
        try:norm.append(_sale(row,idx,current) if kind in {'completed_sale','sale'} or 'realized_amount' in row else _ref(row,idx,current) if kind in {'market_reference','market_price','index'} or ('value' in row and 'condition_basis' in row) else (_ for _ in ()).throw(ValueError('MARKET_EVIDENCE_KIND_UNSUPPORTED')))
        except ValueError as e:rejected.append({'index':i,'source_code':_clean(row.get('source_code')).upper(),'lineage_key':_clean(row.get('underlying_lineage_key')),'error':str(e)})
    norm,rej=_dedupe(norm);rejected+=rej;sales=defaultdict(list);refs=defaultdict(list)
    for x in norm:(sales if x['kind']=='completed_sale' else refs)[x['key']].append(x)
    verified=[];sale_results=[];ref_results=[]
    for group in sales.values():
        out,res=_sale_output(group,verifier,current);verified+=out;sale_results.append(res)
    for group in refs.values():
        out,res=_ref_output(group,max_market_relative_spread,verifier,current);verified+=out;ref_results.append(res)
    ledger=[{'kind':x['kind'],'lineage_key':x['lineage'],'provider_id':x['provider_id'],'source_tier':x['tier'],'source_code':_clean(x['raw'].get('source_code')).upper(),'source_locator':_clean(x['raw'].get('item_or_lot_locator') or x['raw'].get('source_locator')),'raw_evidence':x['raw']} for x in norm]
    return {'schema_version':'1.0-market-evidence-bridge','verification_mode':VERIFICATION_MODE,'verification_engine':VERIFICATION_ENGINE,'observed_at':current.astimezone(KST).isoformat(timespec='seconds'),'verified_records':verified,'verified_completed_sale_count':sum(x['fact_type']=='completed_sale' for x in verified),'verified_market_reference_count':sum(x['fact_type']=='market_reference' for x in verified),'sale_verification_results':sale_results,'market_reference_verification_results':ref_results,'rejected':rejected,'evidence_ledger':ledger,'safety':{'completed_sale_market_reference_separated':True,'settlement_unknown_auto_promotion':False,'finality_class_preserved':True,'lineage_deduplication':True,'lineage_conflict_quarantine':True,'market_reference_relative_spread_cap':_fmt(max_market_relative_spread)}}
def _atomic(path:Path,payload:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True);tmp=None
    try:
        with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=path.parent,prefix=f'.{path.name}.',suffix='.tmp',delete=False) as h:json.dump(payload,h,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False);h.write('\n');h.flush();os.fsync(h.fileno());tmp=Path(h.name)
        os.replace(tmp,path)
    finally:
        if tmp and tmp.exists():tmp.unlink(missing_ok=True)
def persist_evidence_ledger(report:dict[str,Any],path:Path=DEFAULT_LEDGER)->dict[str,Any]:
    payload={'schema_version':report.get('schema_version'),'observed_at':report.get('observed_at'),'verification_mode':report.get('verification_mode'),'verification_engine':report.get('verification_engine'),'safety':report.get('safety'),'rows':report.get('evidence_ledger') or [],'rejected':report.get('rejected') or []};_atomic(path,payload);r=json.loads(path.read_text(encoding='utf-8'))
    if r!=payload:raise RuntimeError('MARKET_EVIDENCE_LEDGER_READBACK_MISMATCH')
    return r
def main()->int:
    p=argparse.ArgumentParser();p.add_argument('--input');p.add_argument('--ledger',default=str(DEFAULT_LEDGER));p.add_argument('--no-persist-ledger',action='store_true');a=p.parse_args()
    if not a.input:raise SystemExit('--input is required')
    v=json.loads(Path(a.input).read_text(encoding='utf-8'));rows=v.get('records',v) if isinstance(v,dict) else v;report=verify_market_records(rows)
    if not a.no_persist_ledger:persist_evidence_ledger(report,Path(a.ledger))
    print(json.dumps({'verified_completed_sale_count':report['verified_completed_sale_count'],'verified_market_reference_count':report['verified_market_reference_count'],'rejected_count':len(report['rejected']),'ledger':None if a.no_persist_ledger else str(Path(a.ledger))},ensure_ascii=False));return 0
if __name__=='__main__':raise SystemExit(main())