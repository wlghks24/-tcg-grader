#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Conservative official certification lookup for supported grading companies."""
from __future__ import annotations

import html
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request

from safe_runtime import safe_urlopen

OFFICIAL = {
    "PSA": {
        "home": "https://www.psacard.com/cert",
        "direct": "https://www.psacard.com/cert/{cert}/psa",
        "hosts": {"psacard.com", "www.psacard.com"},
        "marker": re.compile(r"\bPSA\b|PROFESSIONAL\s+SPORTS\s+AUTHENTICATOR", re.I),
    },
    "BGS": {
        "home": "https://www.beckett.com/grading/card-lookup",
        "direct": "https://www.beckett.com/grading/card-lookup?flag=1&item_id={cert}&item_type=BGS",
        "hosts": {"beckett.com", "www.beckett.com"},
        "marker": re.compile(r"\b(?:BGS|BECKETT)\b", re.I),
    },
    "CGC": {
        "home": "https://www.cgccards.com/certlookup/",
        "direct": "https://www.cgccards.com/certlookup/{cert}/",
        "hosts": {"cgccards.com", "www.cgccards.com"},
        "marker": re.compile(r"\bCGC\b|CERTIFIED\s+GUARANTY", re.I),
    },
    "TAG": {
        "home": "https://taggrading.com/pages/cert-search",
        "direct": "https://taggrading.com/pages/cert-search?cert={cert}",
        "hosts": {"taggrading.com", "www.taggrading.com", "my.taggrading.com"},
        "marker": re.compile(r"\bTAG\b|TECHNICAL\s+AUTHENTICATION", re.I),
    },
    "BRG": {
        "home": "https://www.brgcard.com/certification",
        "direct": "https://www.brgcard.com/certification?cert={cert}",
        "hosts": {"brgcard.com", "www.brgcard.com", "tw.brgcard.com"},
        "marker": re.compile(r"\bBRG\b|BREAK\s+GRADING", re.I),
    },
}

FAILURE_MARKERS = (
    "cannot be found", "not found", "invalid cert", "no certification",
    "인증번호를 찾을 수", "查無",
)
BLOCKING_HTTP_STATUSES = {401, 403, 407, 429}
TRANSIENT_HTTP_STATUSES = {408, 425, 429, 500, 502, 503, 504}


def _clean_cert(value):
    return re.sub(r"[^A-Za-z0-9]", "", str(value or "").strip()).upper()[:24]


def lookup_url(company, cert):
    company = str(company or "").upper()
    cert = _clean_cert(cert)
    cfg = OFFICIAL.get(company)
    return cfg["direct"].format(cert=quote(cert)) if cfg else ""


def _request(company, url, timeout=10):
    cfg = OFFICIAL[company]
    request = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 Chrome/137 Mobile Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.8,ko;q=0.7,zh;q=0.5",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    })
    with safe_urlopen(
        request,
        timeout=max(3, min(int(timeout), 20)),
        allowed_hosts=set(cfg["hosts"]),
        max_redirects=4,
    ) as response:
        raw = response.read(1_200_001)
        charset = response.headers.get_content_charset() or "utf-8"
        status = int(getattr(response, "status", 200) or 200)
        final_url = str(getattr(response, "url", url) or url)
    if len(raw) > 1_200_000:
        raise ValueError("official page too large")
    return raw.decode(charset, "ignore"), status, final_url


def _retry_after_seconds(exc):
    try:
        value = (getattr(exc, "headers", None) or {}).get("Retry-After")
        seconds = float(value)
        return max(0.0, min(seconds, 86400.0))
    except (AttributeError, TypeError, ValueError):
        return None


def _fetch(company, url, timeout=10, retries=1):
    attempt = 0
    while True:
        try:
            return _request(company, url, timeout=timeout)
        except HTTPError as exc:
            status = int(getattr(exc, "code", 0) or 0)
            if attempt >= retries or status not in TRANSIENT_HTTP_STATUSES:
                raise
            retry_after = _retry_after_seconds(exc) or 0.0
            time.sleep(min(8.0, max(1.5, retry_after)))
            attempt += 1
        except (URLError, TimeoutError, OSError):
            if attempt >= retries:
                raise
            time.sleep(1.5)
            attempt += 1


def _text(raw):
    raw = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(raw)).strip()


def _normalized_text(value):
    return re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()


def _grade_from_text(company, text):
    patterns = {
        "PSA": (
            r"ITEM\s+GRADE\s*(?:GEM\s*MT|GEM\s*MINT|PRISTINE|MINT|NM-MT)?\s*([0-9]+(?:\.[0-9])?)\b",
            r"\bGRADE\s*(?:PSA\s*)?(?:GEM\s*MT|GEM\s*MINT|PRISTINE|MINT|NM-MT)?\s*([0-9]+(?:\.[0-9])?)\b",
        ),
        "BGS": (r"FINAL\s+GRADE\s*([0-9]+(?:\.[0-9])?)\b", r"CARD\s+GRADE\s*([0-9]+(?:\.[0-9])?)\b"),
        "CGC": (r"(?:CGC\s+)?(?:CARD\s+)?GRADE\s*(?:PRISTINE|GEM\s*MINT|MINT)?\s*([0-9]+(?:\.[0-9])?)\b",),
        "TAG": (r"(?:TAG\s+)?(?:CARD\s+)?GRADE\s*(?:PRISTINE|GEM\s*MINT|MINT)?\s*([0-9]+(?:\.[0-9])?)\b",),
        "BRG": (r"(?:BRG\s+)?(?:CARD\s+)?GRADE\s*(?:PRISTINE|GEM\s*MINT|MINT)?\s*([0-9]+(?:\.[0-9])?)\b",),
    }.get(str(company or "").upper(), ())
    for pattern in patterns:
        match = re.search(pattern, text or "", re.I)
        if match:
            try:
                grade = float(match.group(1))
            except (TypeError, ValueError):
                continue
            if 1 <= grade <= 10:
                return grade
    return None


def _page_evidence(company, cert, text):
    cfg = OFFICIAL[company]
    normalized_cert = _clean_cert(cert)
    return {
        "cert_match": bool(normalized_cert and normalized_cert in _normalized_text(text)),
        "company_match": bool(cfg["marker"].search(text or "")),
        "failure_marker": any(marker in (text or "").lower() for marker in FAILURE_MARKERS),
        "grade": _grade_from_text(company, text),
    }


def verify_cert(company, cert, expected_grade=None, timeout=10):
    company = str(company or "").upper()
    cert = _clean_cert(cert)
    if company not in OFFICIAL:
        return {"ok": False, "verified": False, "error": "지원하지 않는 등급사"}
    if len(cert) < 6:
        return {"ok": False, "verified": False, "error": "인증번호를 확인하세요", "official_url": OFFICIAL[company]["home"]}

    url = lookup_url(company, cert)
    result = {
        "ok": True, "verified": False, "company": company,
        "certification_id": cert, "official_url": url, "grade": None,
        "expected_grade": expected_grade, "mode": "official_lookup",
    }
    try:
        raw, http_status, final_url = _fetch(company, url, timeout=timeout, retries=1)
        result["http_status"] = http_status
        result["final_url"] = final_url
        evidence = _page_evidence(company, cert, _text(raw))
        result["evidence"] = evidence
        if evidence["failure_marker"]:
            result["notice"] = "공식 페이지에서 해당 인증번호를 찾지 못했습니다."
            return result
        if not evidence["company_match"] or not evidence["cert_match"]:
            result["notice"] = "공식 페이지에서 등급사·인증번호 일치를 확인하지 못했습니다."
            return result
        grade = evidence["grade"]
        if grade is None:
            result["notice"] = "공식 페이지는 열렸지만 등급을 안전하게 추출하지 못했습니다."
            return result
        result["grade"] = grade
        if expected_grade is not None and abs(float(expected_grade) - float(grade)) > 1e-9:
            result["conflict"] = True
            result["notice"] = "후보 등급과 공식 등급이 달라 격리했습니다."
            return result
        result.update({"verified": True, "notice": "공식 등급사에서 인증번호와 등급을 확인했습니다."})
        return result
    except HTTPError as exc:
        status = int(getattr(exc, "code", 0) or 0)
        retry_after = _retry_after_seconds(exc)
        default_cooldown = 1800.0 if status == 429 else (7200.0 if status in {401, 403, 407} else 0.0)
        result.update({
            "lookup_error": "HTTPError",
            "http_status": status,
            "blocked_or_challenged": status in BLOCKING_HTTP_STATUSES,
            "transient_error": status in TRANSIENT_HTTP_STATUSES,
            "retry_after_seconds": retry_after,
            "recommended_cooldown_seconds": retry_after if retry_after is not None else default_cooldown,
        })
        if status in BLOCKING_HTTP_STATUSES:
            result["notice"] = "공식 사이트가 자동 요청을 차단하거나 속도 제한했습니다. 공식 조회 링크를 보존하고 재시도 전 대기합니다."
        elif status == 404:
            result["notice"] = "공식 조회 URL이 HTTP 404를 반환했습니다. 인증 실패로 단정하지 않고 수동 확인 대상으로 보존합니다."
        else:
            result["notice"] = f"공식 사이트가 HTTP {status or '오류'}를 반환해 자동확인하지 못했습니다."
        return result
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        result.update({
            "lookup_error": type(exc).__name__,
            "transient_error": isinstance(exc, (URLError, TimeoutError, OSError)),
            "notice": "공식 사이트 응답 제한 또는 네트워크 오류로 자동확인하지 못했습니다. 공식 조회 링크는 유지합니다.",
        })
        return result
