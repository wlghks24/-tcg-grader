#!/usr/bin/env python3
from __future__ import annotations

import urllib.error
import urllib.request

import auto_repair_engine
import validate_external_links as links


class _Response:
    status = 200

    def __init__(self, url: str):
        self._url = url

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeOpener:
    def __init__(self, *, get_code: int | None):
        self.get_code = get_code

    def open(self, req, timeout=None):
        method = req.get_method()
        if method == "HEAD":
            raise urllib.error.HTTPError(req.full_url, 404, "HEAD not supported", {}, None)
        if self.get_code is not None:
            raise urllib.error.HTTPError(req.full_url, self.get_code, "GET result", {}, None)
        return _Response(req.full_url)


def _probe_with(get_code: int | None):
    original_safe = links._safe
    original_resolve = links._resolve_public
    original_build = urllib.request.build_opener
    try:
        links._safe = lambda url: url
        links._resolve_public = lambda host: None
        urllib.request.build_opener = lambda *handlers: _FakeOpener(get_code=get_code)
        return links.probe("https://example.com/card", request_timeout=5)
    finally:
        links._safe = original_safe
        links._resolve_public = original_resolve
        urllib.request.build_opener = original_build


def main():
    # HEAD-only 404 must never condemn a URL that works with GET.
    recovered = _probe_with(None)
    assert recovered["state"] == "ok", recovered

    # A permanent missing result requires GET confirmation.
    confirmed = _probe_with(404)
    assert confirmed["state"] == "broken", confirmed
    assert confirmed.get("confirmed_by") == "GET", confirmed

    # Repair counters must use unique URL units even when one URL is referenced
    # by several rows/files.
    row_a, row_b = {"source": "https://www.pokemon.com/dead"}, {"url": "https://www.pokemon.com/dead"}
    tasks = {
        "https://www.pokemon.com/dead": [
            ("releases.json", row_a, "source"),
            ("purchase_sources.json", row_b, "url"),
        ]
    }
    counts, details = links._apply_results(
        tasks,
        {"https://www.pokemon.com/dead": {"state": "broken", "code": 404, "confirmed_by": "GET"}},
        "2026-09-02T00:00:00+00:00",
    )
    assert counts["broken"] == 1, counts
    assert counts["repaired"] == 1, counts
    assert counts["unresolved_broken"] == 0, counts
    assert details == [], details

    # An unrepaired URL is also counted once and carries bounded diagnostics.
    row_c, row_d = {"source": "https://example.com/dead"}, {"url": "https://example.com/dead"}
    counts, details = links._apply_results(
        {"https://example.com/dead": [("releases.json", row_c, "source"), ("market_watch.json", row_d, "url")]},
        {"https://example.com/dead": {"state": "broken", "code": 410, "confirmed_by": "GET"}},
        "2026-09-02T00:00:00+00:00",
    )
    assert counts["broken"] == 1 and counts["repaired"] == 0, counts
    assert counts["unresolved_broken"] == 1, counts
    assert len(details) == 1 and len(details[0]["references"]) == 2, details

    # UI summary wording must classify as a known permanent HTTP/link issue,
    # not as a novel UNCLASSIFIED_ERROR.
    analysis = auto_repair_engine.analyze_error(
        "외부 링크 검사 — 미보정 깨진 링크 4개",
        use_scenario_profile=False,
    )
    assert analysis["code"] == "NETWORK_HTTP_ERROR", analysis
    assert analysis["error_subtype"] == "broken-link-no-status", analysis
    assert analysis["bounded_retry_allowed"] is False, analysis

    print("[OK] external link audit hardening v184")


if __name__ == "__main__":
    main()
