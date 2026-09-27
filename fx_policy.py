#!/usr/bin/env python3
"""Shared fail-closed validation for exchange_rates.json consumers."""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path
from urllib.parse import urlsplit

from safe_runtime import reject_nonstandard_json, safe_read_text, unique_json_object

FX_MAX_AGE_SECONDS = 72 * 60 * 60
FX_MAX_FUTURE_SKEW_SECONDS = 6 * 60 * 60
TRUSTED_ROUTE_HOSTS = {
    "frankfurter-v2": "api.frankfurter.dev",
    "frankfurter-v1": "api.frankfurter.dev",
    "frankfurter-legacy": "api.frankfurter.app",
}
TRUSTED_ROUTE_PATHS = {
    "frankfurter-v2": "/v2/rates",
    "frankfurter-v1": "/v1/latest",
    "frankfurter-legacy": "/latest",
}


def _strict_load(path: Path):
    return json.loads(
        safe_read_text(path),
        parse_constant=reject_nonstandard_json,
        object_pairs_hook=unique_json_object,
    )


def validate_exchange_payload(data, *, now: dt.datetime | None = None, require_fresh: bool = True):
    """Return ``(ok, reason)`` for a provenance-bound KRW FX payload."""
    if not isinstance(data, dict) or data.get("base") != "KRW":
        return False, "base"
    rates = data.get("rates")
    if not isinstance(rates, dict):
        return False, "rates"
    jpy = rates.get("JPY_KRW")
    usd = rates.get("USD_KRW")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in (jpy, usd)):
        return False, "rate_type"
    if not (math.isfinite(float(jpy)) and math.isfinite(float(usd))):
        return False, "rate_finite"
    if not (0 < float(jpy) < 30 and 500 < float(usd) < 3000):
        return False, "rate_range"

    stamp = data.get("updated_at")
    if not isinstance(stamp, str) or not stamp.strip():
        return False, "timestamp"
    try:
        parsed = dt.datetime.fromisoformat(stamp.strip().replace("Z", "+00:00"))
    except ValueError:
        return False, "timestamp"
    if parsed.tzinfo is None:
        return False, "timestamp_timezone"
    if require_fresh:
        reference = now or dt.datetime.now(dt.timezone.utc)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=dt.timezone.utc)
        age = (reference.astimezone(dt.timezone.utc) - parsed.astimezone(dt.timezone.utc)).total_seconds()
        if not (-FX_MAX_FUTURE_SKEW_SECONDS <= age <= FX_MAX_AGE_SECONDS):
            return False, "timestamp_freshness"

    route = data.get("source_route")
    source = data.get("source")
    if route not in TRUSTED_ROUTE_HOSTS or not isinstance(source, str):
        return False, "source_route"
    try:
        parts = urlsplit(source)
    except ValueError:
        return False, "source_url"
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or parts.username or parts.password or parts.port not in (None, 443):
        return False, "source_url"
    if host != TRUSTED_ROUTE_HOSTS[route] or parts.path != TRUSTED_ROUTE_PATHS[route]:
        return False, "source_provenance"
    return True, "ok"


def load_krw_rates(path: Path, *, now: dt.datetime | None = None):
    """Load conversion rates or return zero conversions when any proof is invalid."""
    try:
        data = _strict_load(Path(path))
        ok, _ = validate_exchange_payload(data, now=now, require_fresh=True)
        if not ok:
            raise ValueError("untrusted exchange-rate payload")
        rates = data["rates"]
        return {
            "USD": float(rates["USD_KRW"]),
            "JPY": float(rates["JPY_KRW"]),
            "EUR": 0.0,
            "KRW": 1.0,
        }
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {"USD": 0.0, "JPY": 0.0, "EUR": 0.0, "KRW": 1.0}
