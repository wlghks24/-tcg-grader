#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V642 — free CSV source-evidence staging, never writes the official catalog.

Import user-supplied source links and observed offers for V639 task_ids.
Strict types, public HTTPS only, regional currency, limited size, dedup,
out-of-date warnings, manual review queue and atomic JSON export. NO scraping.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit

from tcg_multi_source_queue_v639 import build_queue
from execution.official_box_coverage_audit_v623 import _trusted_url

MAX_CSV_BYTES = 2_000_000
MAX_ROWS = 10000
SOURCE_TYPES = {"manufacturer", "store_buy_offer", "sale_listing", "completed_sale", "community_index"}
CURRENCY = {"KR": "KRW", "JP": "JPY", "US": "USD"}
REQUIRED = ("task_id", "source_url", "source_type", "observed_at", "amount", "currency")
KST = timezone(timedelta(hours=9))


def current_kst_day(now=None):
    """Use Korea calendar date independently of Termux/Actions host timezone."""
    if now is None:
        now = datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("AWARE_TIMESTAMP_REQUIRED")
    return now.astimezone(KST).date()


def source_host(value):
    if not isinstance(value, str) or len(value) > 1000:
        return None
    try:
        u = urlsplit(value)
        if (u.scheme != "https" or u.username or u.password or u.fragment or
                u.port not in (None, 443) or not u.hostname):
            return None
        host = u.hostname.lower().strip(".")
        if host == "localhost" or host.endswith((".localhost", ".local", ".test", ".invalid")):
            return None
        try:
            ipaddress.ip_address(host)
            return None
        except ValueError:
            pass
        return host if "." in host else None
    except ValueError:
        return None


def parse_amount(value):
    if not value:
        return None
    try:
        amount = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        raise ValueError("BAD_AMOUNT")
    if not amount.is_finite() or not (Decimal("0") < amount <= Decimal("1000000000")):
        raise ValueError("BAD_AMOUNT")
    if amount.as_tuple().exponent < -2:
        raise ValueError("TOO_MANY_DECIMALS")
    return str(amount)


def stage_csv(text, jobs_by_id=None, *, today=None):
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_CSV_BYTES:
        raise ValueError("OVERSIZED_INPUT")
    today = current_kst_day() if today is None else today
    if not isinstance(today, date):
        raise ValueError("INVALID_DATE")
    if jobs_by_id is None:
        jobs_by_id = {row["task_id"]: row for row in build_queue()["jobs"]}
    reader = csv.DictReader(text.lstrip("\ufeff").splitlines())
    if not reader.fieldnames or any(k not in reader.fieldnames for k in REQUIRED):
        raise ValueError("MISSING_REQUIRED_COLUMNS")
    accepted, rejected, seen = [], [], set()
    for rownum, row in enumerate(reader, start=2):
        if rownum > MAX_ROWS + 1:
            raise ValueError("TOO_MANY_ROWS")
        if not row or None in row or any(v is None for v in row.values()):
            rejected.append({"row": rownum, "reason": "BAD_CSV_ROW"})
            continue
        try:
            task_id = row["task_id"].strip()
            job = jobs_by_id.get(task_id)
            if not job:
                raise ValueError("UNKNOWN_TASK_ID")
            source = row["source_url"].strip()
            host = source_host(source)
            if not host:
                raise ValueError("UNSAFE_SOURCE_URL")
            src_type = row["source_type"].strip().lower()
            if src_type not in SOURCE_TYPES:
                raise ValueError("INVALID_SOURCE_TYPE")
            day = date.fromisoformat(row["observed_at"].strip())
            if day > today:
                raise ValueError("FUTURE_OBSERVATION")
            if (today - day).days > 365 * 5:
                raise ValueError("TOO_OLD_TO_CONSIDER")
            amount = parse_amount(row["amount"])
            currency = row["currency"].strip().upper()
            if amount is None and currency:
                raise ValueError("CURRENCY_WITHOUT_AMOUNT")
            if amount is not None and currency != CURRENCY[job["market"]]:
                raise ValueError("CURRENCY_MARKET_MISMATCH")
            # Manufacturer MSRP must be independently confirmed from its page;
            # no pasted number can be auto-certified as an official MSRP.
            official_domain = _trusted_url(source, job["canonical_game"])
            record = {
                "task_id": task_id, "game_id": job["game_id"], "market": job["market"],
                "kind": job["kind"], "candidate": job["candidate"],
                "source_url": source, "source_host": host, "source_type": src_type,
                "observed_at": day.isoformat(), "reported_amount": amount,
                "reported_currency": currency if amount else None,
                "manufacturer_host_on_allowlist": bool(official_domain) if src_type == "manufacturer" else None,
                "evidence_level": "USER_SUPPLIED_UNVERIFIED_LINK",
                "validation_status": ("MANUFACTURER_DOMAIN_REVIEW_REQUIRED" if src_type == "manufacturer" and not official_domain
                                      else "SOURCE_CONTENT_REVIEW_REQUIRED"),
                "manual_approval": False, "is_completed_sale_verified": False,
                "is_official_product_verified": False,
            }
            key = (task_id, source.casefold(), src_type, day.isoformat(), amount, currency)
            if key in seen:
                continue
            seen.add(key)
            record["evidence_id"] = hashlib.sha256(repr(key).encode("utf-8")).hexdigest()[:24]
            accepted.append(record)
        except (ValueError, TypeError, KeyError) as error:
            rejected.append({"row": rownum, "reason": str(error)})
    return {
        "schema_version": 1, "status": "EVIDENCE_STAGING_ONLY",
        "accepted_count": len(accepted), "rejected_count": len(rejected),
        "accepted": accepted, "rejected": rejected,
        "policy": "NO_AUTOMATIC_BOX_PRICE_HIT_OR_SALE_PROMOTION",
    }


def save_new(path, content):
    original = Path(path)
    if original.is_symlink():
        raise ValueError("UNSAFE_OUTPUT_SYMLINK")
    path = original.resolve()
    if path.suffix.lower() != ".json" or path.exists() or path.parent.is_symlink() or path.parent == Path(__file__).resolve().parent:
        raise ValueError("UNSAFE_OUTPUT_PATH")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=".stage_", suffix=".tmp", delete=False) as fp:
            temporary = Path(fp.name)
            json.dump(content, fp, ensure_ascii=False, indent=2)
            fp.write("\n")
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Offline CSV source staging: no automatic publication")
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args(argv)
    if not args.input.is_file() or args.input.is_symlink() or args.input.stat().st_size > MAX_CSV_BYTES:
        ap.error("INVALID_INPUT_CSV")
    try:
        result = stage_csv(args.input.read_text(encoding="utf-8-sig"))
        save_new(args.output, result)
        print(json.dumps({"accepted": result["accepted_count"], "rejected": result["rejected_count"],
                          "status": result["status"], "network_calls": 0}, ensure_ascii=False))
        return 0 if not result["rejected_count"] else 2
    except (ValueError, OSError, UnicodeError) as e:
        ap.error(str(e))


if __name__ == "__main__":
    raise SystemExit(main())
