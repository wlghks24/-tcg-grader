#!/usr/bin/env python3
"""Refresh KRW reference exchange rates; preserve last values on failure."""
import datetime as dt,json,math,urllib.error,urllib.request
from pathlib import Path
from safe_runtime import atomic_write_json, diagnostic_exception, env_int, safe_read_text, safe_urlopen
DATA=Path(__file__).resolve().parent/'exchange_rates.json'
SOURCES=(
    ('frankfurter-v2','https://api.frankfurter.dev/v2/rates?base=USD&quotes=KRW,JPY'),
    ('frankfurter-v1','https://api.frankfurter.dev/v1/latest?base=USD&symbols=KRW,JPY'),
    ('frankfurter-legacy','https://api.frankfurter.app/latest?from=USD&to=KRW,JPY'),
)
ALLOWED_HOSTS={'api.frankfurter.dev','api.frankfurter.app'}

def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':'TCG-Grader-FX-Updater/2.0'})
    with safe_urlopen(req,timeout=env_int('TCG_HTTP_TIMEOUT',20,5,60),allowed_hosts=ALLOWED_HOSTS) as r:
        return json.load(r)

def parse_rates(raw):
    """Accept Frankfurter v1's mapping and v2's flat rate rows."""
    if isinstance(raw,dict) and isinstance(raw.get('rates'),dict):
        rates=raw['rates']; return float(rates['KRW']),float(rates['JPY'])
    rows=raw.get('data') if isinstance(raw,dict) and isinstance(raw.get('data'),list) else raw
    if isinstance(rows,list):
        quotes={str(row.get('quote') or row.get('currency') or '').upper():row.get('rate')
                for row in rows if isinstance(row,dict)}
        return float(quotes['KRW']),float(quotes['JPY'])
    raise ValueError('환율 응답의 KRW·JPY 필수값을 읽지 못했습니다')

def _parse_observed_at(value):
    if not isinstance(value,str) or not value.strip():
        return None
    try:
        parsed=dt.datetime.fromisoformat(value.strip().replace('Z','+00:00'))
        if parsed.tzinfo is None:
            parsed=parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except (TypeError,ValueError,OverflowError):
        return None

def parse_source_timestamp(raw):
    """Return the oldest required quote observation, rejecting mixed stale/future data."""
    rows=raw.get('data') if isinstance(raw,dict) and isinstance(raw.get('data'),list) else (raw if isinstance(raw,list) else [])
    parsed_values=[]
    if rows:
        required={'KRW','JPY'}
        quote_values={quote:[] for quote in required}
        for row in rows:
            if not isinstance(row,dict):
                continue
            quote=str(row.get('quote') or row.get('currency') or '').upper()
            if quote not in required:
                continue
            for key in ('date','timestamp','updated_at'):
                parsed=_parse_observed_at(row.get(key))
                if parsed is not None:
                    quote_values[quote].append(parsed)
        if any(not quote_values[quote] for quote in required):
            raise ValueError('환율 응답의 KRW·JPY source timestamp가 모두 필요합니다')
        parsed_values=[value for quote in required for value in quote_values[quote]]
    elif isinstance(raw,dict):
        parsed_values=[parsed for key in ('date','timestamp','updated_at')
                       if (parsed:=_parse_observed_at(raw.get(key))) is not None]
    if not parsed_values:
        raise ValueError('환율 응답의 source timestamp가 없습니다')
    # Both quotes are consumed together, so freshness is bounded by the oldest
    # required observation. Using the newest row could let one stale quote ride
    # on the timestamp of the other quote.
    observed=min(parsed_values)
    age=(dt.datetime.now(dt.timezone.utc)-observed).total_seconds()
    if not (0 <= age <= 72*60*60):
        raise ValueError('환율 source timestamp가 stale 또는 future 입니다')
    return observed.isoformat(timespec='seconds')

def _load_current():
    """Load the persisted cache without letting corruption block a fresh fetch."""
    try:
        current=json.loads(safe_read_text(DATA))
        if isinstance(current,dict):
            return current
    except (OSError,TypeError,ValueError):
        pass
    return {
        'base':'KRW','rates':{},'source':'','source_route':'',
        'collection_status':'사용 가능한 확인환율 없음',
        'collection_error':None,'collection_errors':[],
    }

def main():
    current=_load_current()
    errors=[];selected=None
    for label,url in SOURCES:
        try:
            raw=fetch(url)
            krw,jpy=parse_rates(raw)
            source_timestamp=parse_source_timestamp(raw)
            if not (math.isfinite(krw) and math.isfinite(jpy) and 500<krw<3000 and 50<jpy<250):
                raise ValueError('원화 환산 환율 수집값이 허용 범위를 벗어났습니다')
            selected=(label,url,krw,jpy,source_timestamp);break
        except (urllib.error.URLError,TimeoutError,OSError,KeyError,TypeError,ValueError,ZeroDivisionError) as exc:
            errors.append(f'{label}: {diagnostic_exception(exc)}')
    if selected:
        label,url,krw,jpy,source_timestamp=selected
        current['rates']={'JPY_KRW':round(krw/jpy,5),'USD_KRW':round(krw,2)}
        current['updated_at']=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
        current['source_timestamp']=source_timestamp
        current['source']=url;current['source_route']=label;current['collection_status']='정상'
        current['collection_error']=None;current['collection_errors']=[]
    else:
        current['collection_status']='기존 확인환율 유지' if current.get('rates') else '사용 가능한 확인환율 없음'
        # Keep the singular compatibility field equal to one list entry.  The
        # orchestrator merges both fields and de-duplicates exact strings; a
        # concatenated summary made the same outage look like an extra failure.
        current['collection_error']=errors[-1] if errors else '환율 수집 실패'
        current['collection_errors']=errors
    atomic_write_json(DATA,current);return current
if __name__=='__main__':main()
