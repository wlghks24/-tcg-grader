#!/usr/bin/env python3
"""Refresh KRW reference exchange rates; preserve last values on failure."""
import datetime as dt,json,urllib.request
from pathlib import Path
DATA=Path(__file__).resolve().parent/'exchange_rates.json'
URL='https://api.frankfurter.app/latest?from=USD&to=KRW,JPY'
def fetch():
    req=urllib.request.Request(URL,headers={'User-Agent':'TCG-Grader-FX-Updater/1.0'})
    with urllib.request.urlopen(req,timeout=20) as r:return json.load(r)
def main():
    current=json.loads(DATA.read_text(encoding='utf-8'))
    try:
        raw=fetch();krw=float(raw['rates']['KRW']);jpy=float(raw['rates']['JPY'])
        if not (500<krw<3000 and 50<jpy<250):raise ValueError('환율 범위 오류')
        current['rates']={'JPY_KRW':round(krw/jpy,5),'USD_KRW':round(krw,2)}
        current['updated_at']=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds');current['source']=URL;current['collection_status']='정상';current['collection_error']=None
    except Exception as exc:
        current['collection_status']='기존 확인환율 유지';current['collection_error']=type(exc).__name__
    tmp=DATA.with_suffix('.json.tmp');tmp.write_text(json.dumps(current,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');tmp.replace(DATA);return current
if __name__=='__main__':main()
