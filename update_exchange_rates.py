#!/usr/bin/env python3
"""Refresh KRW reference exchange rates; preserve only trusted fresh last values on failure."""
import datetime as dt,json,math,urllib.error,urllib.request
from pathlib import Path

from fx_policy import TRUSTED_ROUTE_SOURCES, validate_exchange_payload
from safe_runtime import (
    atomic_write_json,
    diagnostic_exception,
    env_int,
    reject_nonstandard_json,
    safe_read_text,
    safe_urlopen,
    unique_json_object,
)

DATA=Path(__file__).resolve().parent/'exchange_rates.json'
SOURCES=tuple(TRUSTED_ROUTE_SOURCES.items())
ALLOWED_HOSTS={'api.frankfurter.dev','api.frankfurter.app'}
MAX_RESPONSE_BYTES=500_000


def _empty_current():
    return {
        'updated_at':None,
        'base':'KRW',
        'rates':{'JPY_KRW':0.0,'USD_KRW':0.0},
        'source':None,
        'source_route':None,
        'collection_status':'유효 환율 없음',
        'collection_error':'기존 환율 파일 무결성 오류',
        'collection_errors':[],
    }


def _strict_json_bytes(raw: bytes):
    if len(raw)>MAX_RESPONSE_BYTES:
        raise ValueError('환율 응답 크기 제한 초과')
    try:
        text=raw.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise ValueError('환율 응답 UTF-8 오류') from exc
    return json.loads(
        text,
        parse_constant=reject_nonstandard_json,
        object_pairs_hook=unique_json_object,
    )


def _load_current():
    """Load only a trusted, fresh last-good state; stale/unproven values fail closed."""
    try:
        current=json.loads(
            safe_read_text(DATA),
            parse_constant=reject_nonstandard_json,
            object_pairs_hook=unique_json_object,
        )
        valid,_reason=validate_exchange_payload(current,require_fresh=True)
        if not valid:
            raise ValueError('기존 환율 provenance/freshness 오류')
        return current,True
    except (OSError,ValueError,TypeError,json.JSONDecodeError):
        return _empty_current(),False


def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':'TCG-Grader-FX-Updater/2.0'})
    with safe_urlopen(req,timeout=env_int('TCG_HTTP_TIMEOUT',20,5,60),allowed_hosts=ALLOWED_HOSTS) as r:
        raw=r.read(MAX_RESPONSE_BYTES+1)
    return _strict_json_bytes(raw)


def parse_rates(raw):
    """Accept Frankfurter v1 mapping or v2 rows, always bound to USD as base."""
    if isinstance(raw,dict) and isinstance(raw.get('rates'),dict):
        base=str(raw.get('base') or 'USD').upper()
        if base!='USD':
            raise ValueError('환율 응답 base가 USD가 아닙니다')
        rates=raw['rates']
        return float(rates['KRW']),float(rates['JPY'])
    rows=raw.get('data') if isinstance(raw,dict) and isinstance(raw.get('data'),list) else raw
    if isinstance(rows,list):
        quotes={}
        for row in rows:
            if not isinstance(row,dict):
                raise ValueError('환율 응답 행 구조 오류')
            base=str(row.get('base') or 'USD').upper()
            if base!='USD':
                raise ValueError('환율 응답 행 base가 USD가 아닙니다')
            quote=str(row.get('quote') or row.get('currency') or '').upper()
            if not quote:
                continue
            if quote in quotes:
                raise ValueError(f'환율 응답 중복 통화: {quote}')
            quotes[quote]=row.get('rate')
        return float(quotes['KRW']),float(quotes['JPY'])
    raise ValueError('환율 응답의 KRW·JPY 필수값을 읽지 못했습니다')


def main():
    current,has_valid_current=_load_current()
    errors=[];selected=None
    for label,url in SOURCES:
        try:
            krw,jpy=parse_rates(fetch(url))
            if not (math.isfinite(krw) and math.isfinite(jpy) and 500<krw<3000 and 50<jpy<250):
                raise ValueError('원화 환산 환율 수집값이 허용 범위를 벗어났습니다')
            selected=(label,url,krw,jpy);break
        except (urllib.error.URLError,TimeoutError,OSError,KeyError,TypeError,ValueError,ZeroDivisionError) as exc:
            errors.append(f'{label}: {diagnostic_exception(exc)}')
    if selected:
        label,url,krw,jpy=selected
        current['base']='KRW'
        current['rates']={'JPY_KRW':round(krw/jpy,5),'USD_KRW':round(krw,2)}
        current['updated_at']=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
        current['source']=url;current['source_route']=label;current['collection_status']='정상'
        current['collection_error']=None;current['collection_errors']=[]
    else:
        current['collection_status']='기존 확인환율 유지' if has_valid_current else '유효 환율 없음'
        current['collection_error']=errors[-1] if errors else '환율 수집 실패'
        current['collection_errors']=errors
    atomic_write_json(DATA,current);return current
if __name__=='__main__':main()
