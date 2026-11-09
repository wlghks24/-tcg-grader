#!/usr/bin/env python3
"""Refresh KRW reference exchange rates; preserve last values on failure."""
import datetime as dt,json,math,urllib.error,urllib.request
from pathlib import Path
from safe_runtime import atomic_write_json, diagnostic_exception, env_int, safe_read_text, safe_urlopen
from tcg_reliability.fx_eur_reference_v980 import verified_eur_krw
DATA=Path(__file__).resolve().parent/'exchange_rates.json'
SOURCES=(
    ('frankfurter-v2','https://api.frankfurter.dev/v2/rates?base=USD&quotes=KRW,JPY,EUR'),
    ('frankfurter-v1','https://api.frankfurter.dev/v1/latest?base=USD&symbols=KRW,JPY,EUR'),
    ('frankfurter-legacy','https://api.frankfurter.app/latest?from=USD&to=KRW,JPY,EUR'),
)
ALLOWED_HOSTS={'api.frankfurter.dev','api.frankfurter.app'}

def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':'TCG-Grader-FX-Updater/2.0'})
    with safe_urlopen(req,timeout=env_int('TCG_HTTP_TIMEOUT',20,5,60),allowed_hosts=ALLOWED_HOSTS) as r:
        return json.load(r)

def _quote_number(value, label):
    """Provider quotes must be actual finite numbers, never booleans or text."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'환율 {label} 자료가 유효한 숫자가 아닙니다')
    return float(value)


def parse_rates(raw):
    """Read one USD-base KRW and JPY quote; reject duplicate/conflicting rows."""
    if isinstance(raw, dict) and isinstance(raw.get('rates'), dict):
        if raw.get('base') not in (None, 'USD'):
            raise ValueError('환율 응답 기준통화가 USD가 아닙니다')
        rates = raw['rates']
        return _quote_number(rates['KRW'], 'KRW'), _quote_number(rates['JPY'], 'JPY')
    rows = raw.get('data') if isinstance(raw, dict) and isinstance(raw.get('data'), list) else raw
    if isinstance(rows, list):
        quotes = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            quote = str(row.get('quote') or row.get('currency') or '').upper()
            if quote not in ('KRW', 'JPY'):
                continue
            if row.get('base') not in (None, 'USD'):
                raise ValueError('환율 관측 기준통화가 USD가 아닙니다')
            if quote in quotes:
                raise ValueError(f'중복된 환율 {quote} 행은 사용하지 않습니다')
            quotes[quote] = _quote_number(row.get('rate'), quote)
        return quotes['KRW'], quotes['JPY']
    raise ValueError('환율 응답의 KRW·JPY 필수값을 읽지 못했습니다')


def _parse_observed_at(value):
    if not isinstance(value, str):
        return None
    raw = value.strip()
    # Frankfurter date-only observations are UTC days. Full timestamps need
    # an explicit timezone; treating a local clock as UTC creates false freshness.
    if not (len(raw) == 10 and raw[4:5] == '-' and raw[7:8] == '-') and (
        'T' not in raw or not (raw.endswith('Z') or
        (len(raw) >= 6 and raw[-6] in ('+', '-') and raw[-3] == ':'))
    ):
        return None
    try:
        parsed = dt.datetime.fromisoformat(raw.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            if len(raw) != 10:
                return None
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def parse_source_timestamp(raw):
    """Bound both required USD-base quote dates; reject mixed-day observations."""
    rows = raw.get('data') if isinstance(raw, dict) and isinstance(raw.get('data'), list) else (raw if isinstance(raw, list) else [])
    parsed_values = []
    if rows:
        required = {'KRW', 'JPY'}
        quote_values = {quote: [] for quote in required}
        for row in rows:
            if not isinstance(row, dict):
                continue
            quote = str(row.get('quote') or row.get('currency') or '').upper()
            if quote not in required:
                continue
            for key in ('date', 'timestamp', 'updated_at'):
                parsed = _parse_observed_at(row.get(key))
                if parsed is not None:
                    quote_values[quote].append(parsed)
        if any(not quote_values[quote] for quote in required):
            raise ValueError('환율 응답의 KRW·JPY source timestamp가 모두 필요합니다')
        # Distinct trade days are not a single coherent USD/JPY/KRW snapshot.
        oldest = min(value for quote in required for value in quote_values[quote])
        newest = max(value for quote in required for value in quote_values[quote])
        if newest - oldest > dt.timedelta(hours=24):
            raise ValueError('환율 KRW·JPY 출처 관측일 차이가 24시간을 초과합니다')
        parsed_values = [oldest]
    elif isinstance(raw, dict):
        parsed_values = [parsed for key in ('date', 'timestamp', 'updated_at')
                         if (parsed := _parse_observed_at(raw.get(key))) is not None]
    if not parsed_values:
        raise ValueError('환율 응답의 source timestamp가 없습니다')
    observed = min(parsed_values)
    age = (dt.datetime.now(dt.timezone.utc) - observed).total_seconds()
    if not (-6*60*60 <= age <= 72*60*60):
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
            eur_krw=verified_eur_krw(raw, krw, source_timestamp)
            if not (math.isfinite(krw) and math.isfinite(jpy) and 500<krw<3000 and 50<jpy<250):
                raise ValueError('원화 환산 환율 수집값이 허용 범위를 벗어났습니다')
            selected=(label,url,krw,jpy,source_timestamp,eur_krw);break
        except (urllib.error.URLError,TimeoutError,OSError,KeyError,TypeError,ValueError,ZeroDivisionError) as exc:
            errors.append(f'{label}: {diagnostic_exception(exc)}')
    if selected:
        label,url,krw,jpy,source_timestamp,eur_krw=selected
        current['rates']={'JPY_KRW':round(krw/jpy,5),'USD_KRW':round(krw,2)}
        if eur_krw is not None:
            current['rates']['EUR_KRW']=eur_krw
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
