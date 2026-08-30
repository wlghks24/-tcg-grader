#!/usr/bin/env python3
"""Refresh KRW reference exchange rates; preserve last values on failure."""
import os
import datetime as dt,json,urllib.error,urllib.request
from pathlib import Path
from safe_runtime import atomic_write_json, diagnostic_exception, env_int, safe_read_text, safe_urlopen
DATA=Path(__file__).resolve().parent/'exchange_rates.json'
URL='https://api.frankfurter.app/latest?from=USD&to=KRW,JPY'
def fetch():
    req=urllib.request.Request(URL,headers={'User-Agent':'TCG-Grader-FX-Updater/1.0'})
    with safe_urlopen(req,timeout=env_int('TCG_HTTP_TIMEOUT',20,5,60),allowed_hosts={'api.frankfurter.app'}) as r:
        return json.load(r)
def main():
    current=json.loads(safe_read_text(DATA))
    try:
        raw=fetch();krw=float(raw['rates']['KRW']);jpy=float(raw['rates']['JPY'])
        if not (500<krw<3000 and 50<jpy<250):raise ValueError('환율 범위 오류')
        current['rates']={'JPY_KRW':round(krw/jpy,5),'USD_KRW':round(krw,2)}
        current['updated_at']=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds');current['source']=URL;current['collection_status']='정상';current['collection_error']=None
    except (urllib.error.URLError,TimeoutError,OSError,KeyError,TypeError,ValueError,ZeroDivisionError) as exc:
        current['collection_status']='기존 확인환율 유지';current['collection_error']=diagnostic_exception(exc)
    atomic_write_json(DATA,current);return current
if __name__=='__main__':main()
