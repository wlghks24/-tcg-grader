#!/usr/bin/env python3
"""Read-only grading-source redirect diagnostics.

Never follows redirects and never prints full redirect URLs. Only status and host are
reported so allowlist changes can be evidence-based without leaking query/path data.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from safe_runtime import validate_public_https_url

SOURCES = {
    "psa-us-pricing": "https://www.psacard.com/services/tradingcardgrading",
    "psa-jp-pricing": "https://www.psacard.com/ja-JP/services/tradingcardgrading/grading",
    "psa-jp-news": "https://www.psacard.com/ja-JP/articles",
    "bgs-pricing": "https://www.beckett.com/grading",
    "bgs-news": "https://www.beckett.com/news/",
}
ALLOWED_INITIAL = {"psacard.com", "www.psacard.com", "beckett.com", "www.beckett.com"}


class NoFollow(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        absolute = urllib.parse.urljoin(req.full_url, newurl)
        host = (urllib.parse.urlsplit(absolute).hostname or "").rstrip(".").lower()
        raise urllib.error.HTTPError(req.full_url, code, f"redirect host={host or 'missing'}", headers, fp)


def inspect(source_id: str, url: str) -> dict:
    validate_public_https_url(url, ALLOWED_INITIAL)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 TCG-Grader-GradingSourceDiagnostic/1.0",
        "Accept-Language": "en-US,en;q=0.8",
        "Range": "bytes=0-2047",
    })
    opener = urllib.request.build_opener(NoFollow())
    try:
        with opener.open(req, timeout=20) as response:
            final_host = (urllib.parse.urlsplit(response.geturl()).hostname or "").lower()
            return {"source": source_id, "status": int(response.status), "final_host": final_host, "redirect": False}
    except urllib.error.HTTPError as exc:
        location = exc.headers.get("Location") if exc.headers else None
        target_host = ""
        if location:
            absolute = urllib.parse.urljoin(url, location)
            target_host = (urllib.parse.urlsplit(absolute).hostname or "").rstrip(".").lower()
        return {
            "source": source_id,
            "status": int(exc.code),
            "redirect": 300 <= int(exc.code) < 400,
            "target_host": target_host or None,
        }
    except urllib.error.URLError as exc:
        return {"source": source_id, "status": None, "redirect": False, "network_error": type(exc.reason).__name__}


def main() -> int:
    rows = [inspect(source_id, url) for source_id, url in SOURCES.items()]
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
