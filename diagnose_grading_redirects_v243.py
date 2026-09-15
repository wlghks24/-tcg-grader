#!/usr/bin/env python3
"""Read-only grading-source transport diagnostics.

Redirects are never followed in probes. Full redirect URLs are never printed; only
status/host are emitted. This isolates benign request-shape differences without
weakening production allowlists or bypassing provider policy.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

import grading_company_watch as grading
from safe_runtime import diagnostic_exception, validate_public_https_url

PSA_URL = "https://www.psacard.com/services/tradingcardgrading"
BGS_URLS = {
    "grading": "https://www.beckett.com/grading",
    "grading-modal": "https://www.beckett.com/grading?slide=modal",
    "grading-bare": "https://beckett.com/grading",
    "grading-submit": "https://www.beckett.com/grading/submit",
    "turnaround-policy": "https://www.beckett.com/grading/turnaround-policy",
    "availability": "https://www.beckett.com/card-grading-availability",
    "global-services": "https://www.beckett.com/grading/beckett-global-services",
    "news-index": "https://www.beckett.com/news/",
    "news-turnaround": "https://www.beckett.com/news/beckett-turnaround-time-updates/",
    "nscc-2026": "https://www.beckett.com/nscc-2026",
}
ALLOWED_INITIAL = {"psacard.com", "www.psacard.com", "beckett.com", "www.beckett.com"}
PRODUCTION_UA = grading.UA
DIAGNOSTIC_UA = "Mozilla/5.0 TCG-Grader-GradingSourceDiagnostic/1.0"


class NoFollow(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        absolute = urllib.parse.urljoin(req.full_url, newurl)
        host = (urllib.parse.urlsplit(absolute).hostname or "").rstrip(".").lower()
        raise urllib.error.HTTPError(req.full_url, code, f"redirect host={host or 'missing'}", headers, fp)


def probe(label: str, url: str, headers: dict[str, str]) -> dict:
    validate_public_https_url(url, ALLOWED_INITIAL)
    req = urllib.request.Request(url, headers=headers)
    opener = urllib.request.build_opener(NoFollow())
    try:
        with opener.open(req, timeout=20) as response:
            return {"probe": label, "status": int(response.status), "redirect": False,
                    "host": (urllib.parse.urlsplit(response.geturl()).hostname or "").lower()}
    except urllib.error.HTTPError as exc:
        location = exc.headers.get("Location") if exc.headers else None
        host = None
        if location:
            absolute = urllib.parse.urljoin(url, location)
            host = (urllib.parse.urlsplit(absolute).hostname or "").rstrip(".").lower() or None
        return {"probe": label, "status": int(exc.code), "redirect": 300 <= int(exc.code) < 400,
                "target_host": host}
    except urllib.error.URLError as exc:
        return {"probe": label, "status": None, "redirect": False,
                "network_error": type(exc.reason).__name__}


def production_probe(label: str, url: str) -> dict:
    try:
        body = grading._fetch_raw(url)
        return {"probe": label, "ok": True, "bytes": len(body.encode("utf-8"))}
    except (OSError, ValueError) as exc:
        return {"probe": label, "ok": False, "error": diagnostic_exception(exc)}


def main() -> int:
    psa_matrix = [
        ("prod-shape", {"User-Agent": PRODUCTION_UA,
                        "Accept-Language": "ko-KR,ja-JP;q=0.9,en-US;q=0.8,en;q=0.7"}),
        ("prod-plus-range", {"User-Agent": PRODUCTION_UA,
                             "Accept-Language": "ko-KR,ja-JP;q=0.9,en-US;q=0.8,en;q=0.7",
                             "Range": "bytes=0-1999999"}),
        ("diag-ua-no-range", {"User-Agent": DIAGNOSTIC_UA,
                              "Accept-Language": "en-US,en;q=0.8"}),
        ("diag-ua-range", {"User-Agent": DIAGNOSTIC_UA,
                           "Accept-Language": "en-US,en;q=0.8",
                           "Range": "bytes=0-1999999"}),
    ]
    print("PSA_MATRIX")
    print(json.dumps([probe(label, PSA_URL, headers) for label, headers in psa_matrix], ensure_ascii=False, indent=2))
    print("BGS_ENDPOINTS")
    bgs_headers = {"User-Agent": PRODUCTION_UA,
                   "Accept-Language": "ko-KR,ja-JP;q=0.9,en-US;q=0.8,en;q=0.7",
                   "Range": "bytes=0-1999999"}
    print(json.dumps([probe(label, url, bgs_headers) for label, url in BGS_URLS.items()], ensure_ascii=False, indent=2))
    print("PRODUCTION_FETCH")
    targets = {"psa": PSA_URL, **{f"bgs-{key}": value for key, value in BGS_URLS.items()}}
    print(json.dumps([production_probe(label, url) for label, url in targets.items()], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
