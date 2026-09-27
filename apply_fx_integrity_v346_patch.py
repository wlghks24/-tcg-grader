#!/usr/bin/env python3
"""Apply v346 FX provenance/freshness hardening with exact fail-closed replacements."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one patch anchor, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "multi_market_price_collector.py",
    """FX_MAX_AGE_SECONDS=72*60*60
FX_MAX_FUTURE_SKEW_SECONDS=6*60*60

def _fx():
    d=_safe_json(FX,{})
    rates=d.get('rates') if isinstance(d,dict) else {}
    stamp=str(d.get('updated_at') or '') if isinstance(d,dict) else ''
    try:
        parsed=datetime.fromisoformat(stamp.replace('Z','+00:00'))
        if parsed.tzinfo is None:
            raise ValueError('timezone_required')
        age=(datetime.now(timezone.utc)-parsed.astimezone(timezone.utc)).total_seconds()
        fresh=(-FX_MAX_FUTURE_SKEW_SECONDS <= age <= FX_MAX_AGE_SECONDS)
    except (TypeError,ValueError,OverflowError):
        fresh=False
    if not fresh:
        return {'USD':0.0,'JPY':0.0,'EUR':0.0,'KRW':1.0}
    return {'USD':float((rates or {}).get('USD_KRW') or 0),'JPY':float((rates or {}).get('JPY_KRW') or 0),
            'EUR':float((rates or {}).get('EUR_KRW') or 0),'KRW':1.0}
""",
    """def _fx():
    from fx_policy import load_krw_rates
    return load_krw_rates(FX)
""",
)

replace_once(
    "auto_repair_engine.py",
    """        elif filename == \"exchange_rates.json\":
            rates = data[\"rates\"]
            values = [rates.get(\"JPY_KRW\"), rates.get(\"USD_KRW\")]
            if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
                return False
            if not (0 < values[0] < 30 and 500 < values[1] < 3000):
                return False
""",
    """        elif filename == \"exchange_rates.json\":
            from fx_policy import validate_exchange_payload
            valid_fx, _reason = validate_exchange_payload(data, require_fresh=True)
            if not valid_fx:
                return False
""",
)

replace_once(
    "auto_update_all.py",
    "data=json.loads(safe_read_text(candidate))",
    "data=auto_repair_engine._load_strict_json(candidate)",
)
replace_once(
    "auto_update_all.py",
    "old=json.loads(safe_read_text(ADAPTIVE_STATS))",
    "old=auto_repair_engine._load_strict_json(ADAPTIVE_STATS)",
)
replace_once(
    "auto_update_all.py",
    """    elif name == \"exchange_rates.json\":
        rates = data.get(\"rates\", {})
        if not isinstance(rates,dict):
            raise ValueError(\"환율 rates 구조 오류\")
        if any(isinstance(rates.get(key),bool) for key in (\"JPY_KRW\",\"USD_KRW\")):
            raise ValueError(\"환율 값은 숫자여야 합니다\")
        try:
            jpy_krw=float(rates.get(\"JPY_KRW\",0));usd_krw=float(rates.get(\"USD_KRW\",0))
        except (TypeError,ValueError,OverflowError) as exc:
            raise ValueError(\"환율 값은 유한한 숫자여야 합니다\") from exc
        if not (0 < jpy_krw < 30 and 500 < usd_krw < 3000):
            raise ValueError(\"환율 범위 오류\")
""",
    """    elif name == \"exchange_rates.json\":
        from fx_policy import validate_exchange_payload
        valid_fx, reason = validate_exchange_payload(data, require_fresh=True)
        if not valid_fx:
            raise ValueError(f\"환율 provenance/freshness 오류: {reason}\")
""",
)

replace_once(
    "index.html",
    """function fxTimestampFresh(value,now=Date.now()){const parsed=Date.parse(String(value||''));if(!Number.isFinite(parsed))return false;const age=now-parsed;return age>=-FX_MAX_FUTURE_SKEW_MS&&age<=FX_MAX_AGE_MS}
function clearFxConversionDisplay()""",
    """function fxTimestampFresh(value,now=Date.now()){const parsed=Date.parse(String(value||''));if(!Number.isFinite(parsed))return false;const age=now-parsed;return age>=-FX_MAX_FUTURE_SKEW_MS&&age<=FX_MAX_AGE_MS}
const FX_ROUTE_SOURCE={\"frankfurter-v2\":\"https://api.frankfurter.dev/v2/rates?base=USD&quotes=KRW,JPY\",\"frankfurter-v1\":\"https://api.frankfurter.dev/v1/latest?base=USD&symbols=KRW,JPY\",\"frankfurter-legacy\":\"https://api.frankfurter.app/latest?from=USD&to=KRW,JPY\"};
function fxSourceTrusted(d){const route=String(d?.source_route||'');return Object.prototype.hasOwnProperty.call(FX_ROUTE_SOURCE,route)&&String(d?.source||'')===FX_ROUTE_SOURCE[route]}
function clearFxConversionDisplay()""",
)
replace_once(
    "index.html",
    """  if(!fxTimestampFresh(stamp))throw new Error(\"fx timestamp stale\");
  fxRates={JPY_KRW:jpy,USD_KRW:usd};""",
    """  if(!fxTimestampFresh(stamp))throw new Error(\"fx timestamp stale\");
  if(!fxSourceTrusted(d))throw new Error(\"fx provenance\");
  fxRates={JPY_KRW:jpy,USD_KRW:usd};""",
)

print("v346 FX integrity patch applied")
