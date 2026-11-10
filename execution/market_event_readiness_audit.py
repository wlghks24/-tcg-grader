#!/usr/bin/env python3
"""Read-only TCG price/FX/event readiness guard; never collects or installs.

A timestamp on a source page is not proof of a sale or a recent market observation.
This report is an audit input, not a pricing or device-deployment authorization.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
DAY = re.compile(r"20\d{2}-\d{2}-\d{2}\Z")
MAX_BYTES = 4_000_000


def day(value):
    if not isinstance(value, str) or not DAY.fullmatch(value):
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def stamp(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        return parsed.astimezone(dt.timezone.utc) if parsed.tzinfo else None
    except (ValueError, OverflowError):
        return None


def https_source(value):
    if not isinstance(value, str) or not value or len(value) > 2048:
        return False
    try:
        url = urlsplit(value)
        return (url.scheme == "https" and bool(url.hostname) and
                not url.username and not url.password and
                url.port in (None, 443) and not any(ord(c) < 33 for c in value))
    except ValueError:
        return False


def read(root, name):
    target = root / name
    if target.is_symlink() or not target.is_file() or target.stat().st_size > MAX_BYTES:
        raise ValueError("missing_or_unsafe_file")
    value = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("not_an_object")
    return value


def audit(root=ROOT, *, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        raise ValueError("timezone_aware_now_required")
    now = now.astimezone(dt.timezone.utc)
    today = now.date()
    issues = []
    counts = {"market_total": 0, "market_fresh_observed": 0,
              "market_old_or_unknown": 0, "market_source_date_only": 0,
              "market_future": 0, "market_unsafe_link": 0,
              "event_total": 0, "event_expired_active": 0,
              "movie_watch_only": 0}

    def flag(priority, code, location):
        if len(issues) < 120:
            issues.append({"priority": priority, "code": code, "location": location})

    try:
        fx = read(root, "exchange_rates.json")
        rates = fx.get("rates", {})
        obs = stamp(fx.get("source_timestamp"))
        updated = stamp(fx.get("updated_at"))
        vals = [rates.get("USD_KRW"), rates.get("JPY_KRW")] if isinstance(rates, dict) else []
        valid = (len(vals) == 2 and all(type(v) in (int, float) and
                 math.isfinite(v) and v > 0 for v in vals) and
                 https_source(fx.get("source")) and
                 urlsplit(fx["source"]).hostname in {"api.frankfurter.dev", "api.frankfurter.app"} and
                 bool(fx.get("source_route")) and obs is not None and updated is not None and
                 -6 * 3600 <= (now - obs).total_seconds() <= 72 * 3600 and
                 -6 * 3600 <= (now - updated).total_seconds() <= 72 * 3600)
        fx_status = "REFERENCE_ONLY" if valid else "UNAVAILABLE"
        if not valid:
            flag("P1", "FX_UNVERIFIED_OR_STALE", "exchange_rates.json")
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError):
        fx_status = "UNAVAILABLE"
        flag("P1", "FX_FILE_UNREADABLE", "exchange_rates.json")

    try:
        prices = read(root, "market_prices.json")
        entries = prices.get("entries")
        if not isinstance(entries, dict):
            raise ValueError("entries_not_object")
        for key, row in list(entries.items())[:10000]:
            counts["market_total"] += 1
            pieces = key.split("|") if isinstance(key, str) else []
            if (len(pieces) != 3 or not pieces[1] or pieces[2] not in ("BOX", "HIT")
                    or not isinstance(row, dict)):
                counts["market_old_or_unknown"] += 1
                flag("P1", "MARKET_INVALID_IDENTITY", "market_prices.json")
                continue
            observed = day(row.get("market_observed_at"))
            date = observed or day(row.get("source_date"))
            if observed is None and date is not None:
                counts["market_source_date_only"] += 1
            if date is not None and date > today:
                counts["market_future"] += 1
                flag("P1", "MARKET_FUTURE_DATE", "market_prices.json")
            link_ok = https_source(row.get("source")) and row.get("link_status") == "정상"
            if not link_ok:
                counts["market_unsafe_link"] += 1
            displayed = isinstance(row.get("display"), str) and bool(row["display"].strip())
            if (observed is not None and 0 <= (today - observed).days <= 14
                    and link_ok and displayed):
                counts["market_fresh_observed"] += 1
            else:
                counts["market_old_or_unknown"] += 1
        if counts["market_old_or_unknown"]:
            flag("P1", "MARKET_FRESHNESS_REVIEW_REQUIRED", "market_prices.json")
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError):
        flag("P1", "MARKET_FILE_UNREADABLE", "market_prices.json")

    try:
        events = read(root, "promo_events.json")
        items = events.get("items")
        if not isinstance(items, list):
            raise ValueError("items_not_list")
        for item in items[:10000]:
            counts["event_total"] += 1
            if not isinstance(item, dict):
                flag("P1", "EVENT_INVALID_ROW", "promo_events.json")
                continue
            if item.get("category") == "movie" and item.get("tracking_only") is True:
                counts["movie_watch_only"] += 1
            end = day(item.get("end_date"))
            if (end and end < today and
                    item.get("status") in ("진행 중", "배포중", "판매중", "진행중")):
                counts["event_expired_active"] += 1
                flag("P1", "EVENT_EXPIRED_BUT_ACTIVE", "promo_events.json")
            archive = day(item.get("archive_on"))
            if archive and archive < today and item.get("lifecycle") == "current":
                flag("P2", "EVENT_ARCHIVE_OVERDUE", "promo_events.json")
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError):
        flag("P1", "EVENT_FILE_UNREADABLE", "promo_events.json")

    return {"schema": "tcg-market-event-readiness/v1",
            "status": "HOLD" if any(x["priority"] == "P1" for x in issues) else "REVIEW",
            "fx_status": fx_status, "counts": counts, "issues": issues,
            "grading_accuracy": "NOT_MEASURED",
            "hot_price_prediction": "NOT_AUTHORIZED_FROM_SNAPSHOT",
            "physical_tablet_verified": False, "auto_install_allowed": False,
            "network_calls": 0, "source_mutations": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps(audit(args.root), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
