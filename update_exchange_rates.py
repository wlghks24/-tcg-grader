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

def main():
    current=json.loads(safe_read_text(DATA))
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
        current['rates']={'JPY_KRW':round(krw/jpy,5),'USD_KRW':round(krw,2)}
        current['updated_at']=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
        current['source']=url;current['source_route']=label;current['collection_status']='정상'
        current['collection_error']=None;current['collection_errors']=[]
    else:
        current['collection_status']='기존 확인환율 유지'
        # Keep the singular compatibility field equal to one list entry.  The
        # orchestrator merges both fields and de-duplicates exact strings; a
        # concatenated summary made the same outage look like an extra failure.
        current['collection_error']=errors[-1] if errors else '환율 수집 실패'
        current['collection_errors']=errors
    atomic_write_json(DATA,current);return current
if __name__=='__main__':main()
