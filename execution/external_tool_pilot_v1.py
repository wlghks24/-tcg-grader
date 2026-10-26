#!/usr/bin/env python3
"""Offline, dependency-free safety gate for *already extracted* web evidence.

Not a crawler, SSRF defense, OpenHands executor, publication path, or device test.
The output is an unsigned diagnostic receipt, never trusted for promotion.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import json
from urllib.parse import urlsplit

MAX_URL_CHARS = 2048
MAX_HOST_CHARS = 253
MAX_TIME_CHARS = 64
MAX_TEXT_CHARS = 200_000
MAX_TEXT_BYTES = 256_000
MAX_ALLOWED_HOSTS = 32
MAX_COMPARE_RECEIPTS = 5000
HEX_DIGITS = frozenset("0123456789abcdef")
DENIED_HOSTS = frozenset({"localhost", "metadata.google.internal"})
DENIED_SUFFIXES = (".localhost", ".local", ".internal")


def _hostname_format_ok(host: str) -> bool:
    if (not isinstance(host, str) or not (1 <= len(host) <= MAX_HOST_CHARS)
            or not host.isascii() or host != host.lower() or "." not in host):
        return False
    labels = host.split(".")
    return all(1 <= len(part) <= 63 and part[0].isalnum() and part[-1].isalnum()
               and all(c in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in part)
               for part in labels)


def _source_host(url: str, allowed_hosts: frozenset[str]) -> str:
    if (not isinstance(url, str) or len(url) > MAX_URL_CHARS or not url
            or any(ord(c) <= 32 or ord(c) == 127 or c == "\\" for c in url)):
        raise ValueError("INVALID_URL")
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("INVALID_URL") from exc
    if (parsed.scheme != "https" or not host or parsed.username is not None
            or parsed.password is not None or port not in (None, 443)
            or parsed.fragment):
        raise ValueError("INVALID_URL")
    if host in DENIED_HOSTS or host.endswith(DENIED_SUFFIXES):
        raise ValueError("PRIVATE_HOST")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("IP_LITERAL_DENIED")
    if not _hostname_format_ok(host):
        raise ValueError("INVALID_HOST")
    if host not in allowed_hosts:
        raise ValueError("UNAPPROVED_HOST")
    return host


def vet_extraction(candidate: dict, *, allowed_hosts: set[str],
                   now: datetime, max_age_hours: int = 48) -> dict:
    """Reject unsafe offline metadata; successful results remain REVIEW_ONLY."""
    blocked = {"accepted": False, "state": "BLOCKED", "publishable": False}
    if (not isinstance(candidate, dict) or not isinstance(allowed_hosts, set)
            or not allowed_hosts or len(allowed_hosts) > MAX_ALLOWED_HOSTS
            or any(not isinstance(host, str) or len(host) > MAX_HOST_CHARS
                   or not host.isascii() or host != host.lower()
                   or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-." for c in host)
                   for host in allowed_hosts)):
        return {**blocked, "reason": "INVALID_CONFIGURATION"}
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        return {**blocked, "reason": "INVALID_CLOCK"}
    if type(max_age_hours) is not int or not (1 <= max_age_hours <= 168):
        return {**blocked, "reason": "INVALID_FRESHNESS_POLICY"}
    try:
        trusted_hosts = frozenset(allowed_hosts)
        original = _source_host(candidate.get("source_url"), trusted_hosts)
        final = _source_host(candidate.get("final_url"), trusted_hosts)
    except ValueError as exc:
        return {**blocked, "reason": str(exc)}
    if original != final:
        return {**blocked, "reason": "CROSS_HOST_REDIRECT"}
    observed = candidate.get("observed_at")
    if not isinstance(observed, str):
        return {**blocked, "reason": "MISSING_TIMESTAMP"}
    if not (1 <= len(observed) <= MAX_TIME_CHARS):
        return {**blocked, "reason": "INVALID_TIMESTAMP"}
    try:
        date = datetime.fromisoformat(observed.replace("Z", "+00:00"))
    except ValueError:
        return {**blocked, "reason": "INVALID_TIMESTAMP"}
    if date.tzinfo is None or date.utcoffset() is None:
        return {**blocked, "reason": "NAIVE_TIMESTAMP"}
    delta = now.astimezone(timezone.utc) - date.astimezone(timezone.utc)
    if delta < -timedelta(minutes=5):
        return {**blocked, "reason": "FUTURE_TIMESTAMP"}
    if delta > timedelta(hours=max_age_hours):
        return {**blocked, "reason": "STALE_CONTENT"}
    content = candidate.get("markdown")
    if not isinstance(content, str) or not content.strip():
        return {**blocked, "reason": "EMPTY_CONTENT"}
    if len(content) > MAX_TEXT_CHARS:
        return {**blocked, "reason": "CONTENT_TOO_LARGE"}
    try:
        encoded = content.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        return {**blocked, "reason": "INVALID_CONTENT_ENCODING"}
    if len(encoded) > MAX_TEXT_BYTES:
        return {**blocked, "reason": "CONTENT_TOO_LARGE"}
    return {"accepted": True, "state": "REVIEW_ONLY", "publishable": False,
            "origin_host": original, "text_chars": len(content),
            "content_sha256": hashlib.sha256(encoded).hexdigest(),
            "observed_at": date.astimezone(timezone.utc).isoformat(),
            "reason": "UNVERIFIED_EXTERNAL_EVIDENCE"}


def compare_receipts(baseline: list[dict], proposed: list[dict]) -> dict:
    """Bound memory/CPU and reject malformed accepted receipts, no live claims."""
    blocked = {"comparison_valid": False, "baseline_unique": 0,
               "proposed_unique": 0, "new_review_candidates": 0,
               "production_improvement_proven": False}
    if (not isinstance(baseline, list) or not isinstance(proposed, list)
            or len(baseline) > MAX_COMPARE_RECEIPTS
            or len(proposed) > MAX_COMPARE_RECEIPTS):
        return {**blocked, "reason": "INVALID_BATCH"}

    def unique_reviewed(rows: list[dict]) -> set[tuple[str, str]] | None:
        unique = set()
        for row in rows:
            if not isinstance(row, dict):
                return None
            if row.get("accepted") is not True:
                continue  # ordinary BLOCKED receipts do not count as source evidence
            host = row.get("origin_host")
            digest = row.get("content_sha256")
            size = row.get("text_chars")
            if (row.get("state") != "REVIEW_ONLY" or row.get("publishable") is not False
                    or row.get("reason") != "UNVERIFIED_EXTERNAL_EVIDENCE"
                    or not _hostname_format_ok(host)
                    or not isinstance(digest, str) or len(digest) != 64
                    or any(c not in HEX_DIGITS for c in digest)
                    or type(size) is not int or not (1 <= size <= MAX_TEXT_CHARS)):
                return None
            unique.add((host, digest))
        return unique

    old = unique_reviewed(baseline)
    new = unique_reviewed(proposed)
    if old is None or new is None:
        return {**blocked, "reason": "INVALID_RECEIPT"}
    return {"comparison_valid": True, "baseline_unique": len(old),
            "proposed_unique": len(new), "new_review_candidates": len(new - old),
            "production_improvement_proven": False}


if __name__ == "__main__":
    print(json.dumps({"mode": "offline_policy_gate", "live_crawl_tested": False,
                      "agent_executed": False, "production_changes": False}))
