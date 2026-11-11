"""Conservative EUR/KRW reference extraction from *USD-base* Frankfurter data.

This module does no I/O, cannot reprice an item, and never guesses an EUR quote.
The caller must separately validate USD/KRW and JPY/USD reference quotes.
"""
from __future__ import annotations

import datetime as dt
import math
from typing import Any

UTC = dt.timezone.utc
MAX_QUOTE_AGE = dt.timedelta(hours=72)
FUTURE_GRACE = dt.timedelta(hours=6)
MAX_QUOTE_SKEW = dt.timedelta(hours=24)


def _timestamp(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        result = dt.datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
    except (ValueError, OverflowError):
        return None
    # A timezone-less source date does not establish when a quote was observed.
    if result.tzinfo is None:
        # Frankfurter publishes date-only observations. Use 00:00 UTC consistently.
        if len(value.strip()) != 10:
            return None
        result = result.replace(tzinfo=UTC)
    return result.astimezone(UTC)


def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('EUR quote must be a numeric value')
    number = float(value)
    if not math.isfinite(number) or not 0.3 < number < 1.9:
        raise ValueError('USD/EUR quote out of permitted reference range')
    return number


def verified_eur_krw(raw: Any, usd_krw: float, observed_usd_jpy_krw: str,
                     *, now: dt.datetime | None = None) -> float | None:
    """EUR -> KRW if and only if a fresh EUR-per-USD quote is source-proven.

    Returns None for a genuinely absent optional EUR quote; malformed,
    mismatched or stale present quotes raise, so the caller retries a source.
    """
    if isinstance(usd_krw, bool) or not isinstance(usd_krw, (int, float)) or not math.isfinite(usd_krw) or not 500 < usd_krw < 3000:
        raise ValueError('USD/KRW source rate invalid')
    now = (now or dt.datetime.now(UTC)).astimezone(UTC)
    base_ts = _timestamp(observed_usd_jpy_krw)
    if base_ts is None:
        raise ValueError('required FX quote observation missing')

    eur: Any = None
    eur_ts: dt.datetime | None = None
    if isinstance(raw, dict) and isinstance(raw.get('rates'), dict):
        if raw.get('base') not in (None, 'USD'):
            raise ValueError('expected USD base')
        if 'EUR' not in raw['rates']:
            return None
        eur = raw['rates']['EUR']
        eur_ts = _timestamp(raw.get('date') or raw.get('timestamp') or raw.get('updated_at'))
    else:
        rows = raw.get('data') if isinstance(raw, dict) else raw
        if not isinstance(rows, list):
            return None
        matches = [r for r in rows if isinstance(r, dict) and str(r.get('quote') or r.get('currency') or '').upper() == 'EUR']
        if not matches:
            return None
        # A duplicate EUR quote is not sufficient evidence of a single reference rate.
        if len(matches) != 1:
            raise ValueError('ambiguous EUR quote rows')
        row = matches[0]
        if str(row.get('base') or 'USD').upper() != 'USD':
            raise ValueError('expected USD base on EUR quote')
        eur = row.get('rate')
        eur_ts = _timestamp(row.get('date') or row.get('timestamp') or row.get('updated_at'))
    if eur_ts is None:
        raise ValueError('EUR quote source timestamp missing')
    age = now - eur_ts
    if age < -FUTURE_GRACE or age > MAX_QUOTE_AGE:
        raise ValueError('EUR quote stale or from future')
    if abs((base_ts - eur_ts).total_seconds()) > MAX_QUOTE_SKEW.total_seconds():
        raise ValueError('EUR quote observation out of sync with KRW/JPY')
    euro_per_usd = _number(eur)
    rate = float(usd_krw) / euro_per_usd
    if not math.isfinite(rate) or not 100 < rate < 5000:
        raise ValueError('EUR/KRW derived reference invalid')
    return round(rate, 5)
