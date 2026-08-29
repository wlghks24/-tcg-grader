#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Strict official certification lookup for supported grading companies.

A response is verified only when the official host, company marker,
certification number and a grade-context value all agree. A marketplace title,
slab label OCR or a valid-looking cert number alone is never sufficient.
"""
from __future__ import annotations

import html
import re
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
        "direct": "https://www.beckett.com/grading/card-lookup?item_id={cert}&item_type=BGS",
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
    "cannot be found",
    "not found",
    "invalid cert",
    "no certification",
    "인증번호를 찾을 수",
    "查無",
)


def _clean_cert(value):
    return re.sub(r"[^A-Za-z0-9]", "", str(value or "").strip()).upper()[:24]


def lookup_url(company, cert):
    company = str(company or "").upper()
    cert = _clean_cert(cert)
    cfg = OFFICIAL.get(company)
    if not cfg:
        return ""
    return cfg["direct"].format(cert=quote(cert))


def _fetch(company, url, timeout=10):
    cfg = OFFICIAL[company]
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 TCG-Grader-Official-Cert-Check/4.0",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.8,ko;q=0.7,zh;q=0.5",
        },
    )
    with safe_urlopen(request, timeout=max(3, min(int(timeout), 15)), allowed_hosts=set(cfg["hosts"]), max_redirects=3) as response:
        raw = response.read(1_200_001)
        charset = response.headers.get_content_charset() or "utf-8"
    if len(raw) > 1_200_000:
        raise ValueError("official page too large")
    return raw.decode(charset, "ignore")


def _text(raw):
    raw = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(raw)).strip()


def _normalized_text(value):
    return re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()


def _grade_from_text(company, text):
    company = str(company or "").upper()
    patterns = {
        "PSA": (
            r"ITEM\s+GRADE\s*(?:GEM\s*MT|GEM\s*MINT|PRISTINE|MINT|NM-MT)?\s*([0-9]+(?:\.[0-9])?)\b",
            r"\bGRADE\s*(?:PSA\s*)?(?:GEM\s*MT|GEM\s*MINT|PRISTINE|MINT|NM-MT)?\s*([0-9]+(?:\.[0-9])?)\b",
        ),
        "BGS": (r"FINAL\s+GRADE\s*([0-9]+(?:\.[0-9])?)\b", r"CARD\s+GRADE\s*([0-9]+(?:\.[0-9])?)\b"),
        "CGC": (r"(?:CGC\s+)?(?:CARD\s+)?GRADE\s*(?:PRISTINE|GEM\s*MINT|MINT)?\s*([0-9]+(?:\.[0-9])?)\b",),
        "TAG": (r"(?:TAG\s+)?(?:CARD\s+)?GRADE\s*(?:PRISTINE|GEM\s*MINT|MINT)?\s*([0-9]+(?:\.[0-9])?)\b",),
        "BRG": (r"(?:BRG\s+)?(?:CARD\s+)?GRADE\s*(?:PRISTINE|GEM\s*MINT|MINT)?\s*([0-9]+(?:\.[0-9])?)\b",),
    }.get(company, ())
    for pattern in patterns:
        match = re.search(pattern, text or "", re.I)
        if not match:
            continue
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
    cert_match = bool(normalized_cert and normalized_cert in _normalized_text(text))
    company_match = bool(cfg["marker"].search(text or ""))
    failure = any(marker in (text or "").lower() for marker in FAILURE_MARKERS)
    grade = _grade_from_text(company, text)
    return {"cert_match": cert_match, "company_match": company_match, "failure_marker": failure, "grade": grade}


def verify_cert(company, cert, expected_grade=None, timeout=10):
    company = str(company or "").upper()
    cert = _clean_cert(cert)
    if company not in OFFICIAL:
        return {"ok": False, "verified": False, "error": "지원하지 않는 등급사"}
    if len(cert) < 6:
        return {"ok": False, "verified": False, "error": "인증번호를 확인하세요", "official_url": OFFICIAL[company]["home"]}
    url = lookup_url(company, cert)
    result = {
        "ok": True,
        "verified": False,
        "company": company,
        "certification_id": cert,
        "official_url": url,
        "grade": None,
        "expected_grade": expected_grade,
        "mode": "official_lookup",
    }
    try:
        text = _text(_fetch(company, url, timeout=timeout))
        evidence = _page_evidence(company, cert, text)
        result["evidence"] = evidence
        if evidence["failure_marker"] or not evidence["company_match"] or not evidence["cert_match"]:
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
    except (URLError, HTTPError, TimeoutError, OSError, ValueError) as exc:
        result["lookup_error"] = type(exc).__name__
        result["notice"] = "공식 사이트 응답 제한으로 자동확인하지 못했습니다. 공식 조회 링크는 유지합니다."
        return result
