#!/usr/bin/env python3
"""OFFLINE, read-only gate for experimental crawler evidence.

No network, subprocess, model, file write, API, or TCG runtime imports.
This is NOT a Crawl4AI adapter and cannot certify redirect/egress safety.
It accepts already-extracted content and emits a non-publishable receipt.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import json
from urllib.parse import urlsplit

MAX_TEXT_CHARS = 200_000
MAX_ALLOWED_HOSTS = 32


def _source_host(url: str, allowed_hosts: frozenset[str]) -> str:
    if not isinstance(url, str) or len(url) > 2048 or any(ord(c) < 32 for c in url):
        raise ValueError("INVALID_URL")
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("INVALID_URL") from exc
    if (parsed.scheme != "https" or not host or parsed.username is not None
            or parsed.password is not None or port not in (None, 443)
            or parsed.fragment or "\\" in url):
        raise ValueError("INVALID_URL")
    if host in ("localhost", "metadata.google.internal") or host.endswith((".local", ".internal")):
        raise ValueError("PRIVATE_HOST")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("IP_LITERAL_DENIED")
    if host not in allowed_hosts:
        raise ValueError("UNAPPROVED_HOST")
    return host


def vet_extraction(candidate: dict, *, allowed_hosts: set[str],
                   now: datetime, max_age_hours: int = 48) -> dict:
    """Return a bounded receipt for **manual evidence review only**.

    allowed_hosts must come from trusted project configuration, not a web page.
    Caller must separately enforce network egress, redirect safety and robots rules.
    """
    denial = {"accepted": False, "state": "BLOCKED", "publishable": False}
    if (not isinstance(candidate, dict) or not isinstance(allowed_hosts, set)
            or not allowed_hosts or len(allowed_hosts) > MAX_ALLOWED_HOSTS
            or any(not isinstance(h, str) or h != h.lower() or
                   not h.isascii() or not h or h.startswith(".") or h.endswith(".")
                   or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-." for c in h)
                   for h in allowed_hosts)):
        return {**denial, "reason": "INVALID_CONFIGURATION"}
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        return {**denial, "reason": "INVALID_CLOCK"}
    if type(max_age_hours) is not int or not (1 <= max_age_hours <= 168):
        return {**denial, "reason": "INVALID_FRESHNESS_POLICY"}
    trusted_hosts = frozenset(allowed_hosts)
    try:
        initial = _source_host(candidate.get("source_url"), trusted_hosts)
        final = _source_host(candidate.get("final_url"), trusted_hosts)
    except ValueError as exc:
        return {**denial, "reason": str(exc)}
    if initial != final:
        return {**denial, "reason": "CROSS_HOST_REDIRECT"}
    observed = candidate.get("observed_at")
    if not isinstance(observed, str):
        return {**denial, "reason": "MISSING_TIMESTAMP"}
    try:
        date = datetime.fromisoformat(observed.replace("Z", "+00:00"))
    except ValueError:
        return {**denial, "reason": "INVALID_TIMESTAMP"}
    if date.tzinfo is None or date.utcoffset() is None:
        return {**denial, "reason": "NAIVE_TIMESTAMP"}
    delta = now.astimezone(timezone.utc) - date.astimezone(timezone.utc)
    if delta < -timedelta(minutes=5):
        return {**denial, "reason": "FUTURE_TIMESTAMP"}
    if delta > timedelta(hours=max_age_hours):
        return {**denial, "reason": "STALE_CONTENT"}
    content = candidate.get("markdown")
    if not isinstance(content, str) or not content.strip():
        return {**denial, "reason": "EMPTY_CONTENT"}
    if len(content) > MAX_TEXT_CHARS:
        return {**denial, "reason": "CONTENT_TOO_LARGE"}
    # Do not expose or interpret scraped instructions, addresses, image URLs or prices.
    return {"accepted": True, "state": "REVIEW_ONLY", "publishable": False,
            "origin_host": initial, "text_chars": len(content),
            "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "observed_at": date.astimezone(timezone.utc).isoformat(),
            "reason": "UNVERIFIED_EXTERNAL_EVIDENCE"}


def compare_receipts(baseline: list[dict], proposed: list[dict]) -> dict:
    """Compare *offline* receipts; does not imply improved live coverage."""
    def unique_accepted(rows: list[dict]) -> set[tuple[str, str]]:
        return {(r["origin_host"], r["content_sha256"]) for r in rows
                if r.get("accepted") is True and r.get("state") == "REVIEW_ONLY"
                and r.get("publishable") is False
                and isinstance(r.get("origin_host"), str)
                and isinstance(r.get("content_sha256"), str)}
    base, new = unique_accepted(baseline), unique_accepted(proposed)
    return {"baseline_unique": len(base), "proposed_unique": len(new),
            "new_review_candidates": len(new - base),
            "production_improvement_proven": False}


if __name__ == "__main__":
    print(json.dumps({"mode": "offline_policy_gate", "live_crawl_tested": False,
                      "agent_executed": False, "production_changes": False}))
