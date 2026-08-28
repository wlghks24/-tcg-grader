#!/usr/bin/env python3
"""Bounded five-company pre-grading and verified, exact-grade valuations.

The calculations are advisory. They neither replace physical authentication nor
invent market prices, grading multipliers, or unpublished company standards.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from html.parser import HTMLParser
import math
import re
import statistics
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Mapping

from safe_runtime import env_int, safe_urlopen, validate_public_https_url

COMPANIES = ("PSA", "BGS", "CGC", "TAG", "BRG")
MAX_CARD_NAME = 120
MAX_SOURCE_CHARS = 100_000
MAX_AST_NODES = 5_000
MAX_HTML_BYTES = 1_000_000
MAX_SOLD_SAMPLES = 100
MAX_PRICE_KRW = 1_000_000_000_000
MAX_PRICE_USD = 1_000_000.0
EBAY_HOSTS = {"www.ebay.com", "ebay.com"}
NETWORK_ERRORS = (urllib.error.URLError, TimeoutError, OSError, UnicodeError)
VOID_HTML_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
TAG_SCALE = (
    (990, 10.0, "PRISTINE"),
    (950, 10.0, "GEM MINT"),
    (900, 9.0, "MINT"),
    (850, 8.5, "NM MT+"),
    (800, 8.0, "NM MT"),
    (750, 7.5, "NM+"),
    (700, 7.0, "NM"),
    (650, 6.5, "EX MT+"),
    (600, 6.0, "EX MT"),
    (550, 5.5, "EX+"),
    (500, 5.0, "EX"),
    (450, 4.5, "VG EX+"),
    (400, 4.0, "VG EX"),
    (350, 3.5, "VG+"),
    (300, 3.0, "VG"),
    (250, 2.5, "GOOD+"),
    (200, 2.0, "GOOD"),
    (150, 1.5, "FAIR"),
    (100, 1.0, "POOR"),
)


def safe_float(
    value: Any,
    default: float = 0.0,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    """Convert primitive finite numbers without accepting booleans or objects."""
    try:
        fallback = float(default)
    except (TypeError, ValueError, OverflowError):
        fallback = 0.0
    if not math.isfinite(fallback):
        fallback = 0.0
    try:
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            number = fallback
        elif isinstance(value, str) and len(value.strip()) > 64:
            number = fallback
        else:
            number = float(value)
        if not math.isfinite(number):
            number = fallback
    except (TypeError, ValueError, OverflowError):
        number = fallback
    if minimum is not None:
        number = max(float(minimum), number)
    if maximum is not None:
        number = min(float(maximum), number)
    return number


def safe_int(
    value: Any,
    default: int = 0,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    """Convert a bounded, finite primitive to an integer."""
    try:
        fallback = int(default)
    except (TypeError, ValueError, OverflowError):
        fallback = 0
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        number = fallback
    else:
        try:
            if isinstance(value, str) and len(value.strip()) > 64:
                raise ValueError("number too long")
            converted = float(value)
            if not math.isfinite(converted):
                raise ValueError("non-finite number")
            number = int(converted)
        except (TypeError, ValueError, OverflowError):
            number = fallback
    if minimum is not None:
        number = max(int(minimum), number)
    if maximum is not None:
        number = min(int(maximum), number)
    return number


def safe_bool(value: Any, *, default: bool = False) -> bool:
    """Never mistake the nonempty string 'false' for an authenticity approval."""
    if type(value) is bool:
        return value
    if isinstance(value, int) and not isinstance(value, bool) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
    return bool(default)


def inspect_python_source(source: str) -> dict[str, Any]:
    """Inspect syntax and dangerous calls without evaluating submitted code."""
    if not isinstance(source, str) or len(source) > MAX_SOURCE_CHARS:
        raise ValueError("코드 크기 또는 형식 제한 초과")
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError) as exc:
        return {"ok": False, "executed": False, "issues": [f"문법 오류: {exc}"]}
    issues: list[str] = []
    for index, node in enumerate(ast.walk(tree), 1):
        if index > MAX_AST_NODES:
            raise ValueError("코드 구조 복잡도 제한 초과")
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else (
                node.func.attr if isinstance(node.func, ast.Attribute) else ""
            )
            if name in {"exec", "eval", "compile", "__import__", "system", "Popen"}:
                issues.append(f"임의 실행 위험: {name} (줄 {node.lineno})")
            if name == "getattr" and len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) and (
                node.args[1].value in {"exec", "eval", "compile", "__import__", "system", "Popen"}
            ):
                issues.append(f"숨겨진 임의 실행 위험 (줄 {node.lineno})")
            if name in {"run", "call", "Popen"} and any(
                keyword.arg == "shell"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
                for keyword in node.keywords
            ):
                issues.append(f"셸 실행 위험 (줄 {node.lineno})")
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            if any(name.split(".", 1)[0] in {"requests", "urllib", "subprocess"} for name in names):
                issues.append(f"네트워크·프로세스 의존성 점검 (줄 {node.lineno})")
    return {"ok": not issues, "executed": False, "issues": issues}


def _centering_larger_side(value: Any) -> float:
    # A supplied invalid measurement must never become perfect 50/50 centering.
    ratio = safe_float(value, 100.0, minimum=0.0, maximum=100.0)
    return max(ratio, 100.0 - ratio)


def _half_floor(value: float) -> float:
    return max(1.0, min(10.0, math.floor(value * 2.0) / 2.0))


def _flaw_count(value: Any) -> int:
    number = safe_float(value, 100.0)
    if number < 0 or not number.is_integer():
        return 100
    return min(100, int(number))


def tag_score_to_grade(score: Any) -> dict[str, Any]:
    """Apply TAG's published scale, which deliberately has no 9.5 grade."""
    if isinstance(score, bool) or not isinstance(score, (int, float, str)):
        raise ValueError("TAG 점수는 정수여야 합니다.")
    if isinstance(score, str) and len(score.strip()) > 16:
        raise ValueError("TAG 점수 형식 오류")
    try:
        number = float(score)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("TAG 점수 형식 오류") from None
    if not math.isfinite(number) or not number.is_integer():
        raise ValueError("TAG 점수는 유한한 정수여야 합니다.")
    points = int(number)
    if points < 100 or points > 1000:
        raise ValueError("TAG 점수는 100~1000 사이여야 합니다.")
    for threshold, grade, condition in TAG_SCALE:
        if points >= threshold:
            return {"score": points, "grade": grade, "condition": condition}
    raise ValueError("TAG 점수 변환 실패")


@dataclass(frozen=True)
class GradeInputs:
    centering_front: float
    centering_back: float
    corners: float
    edges: float
    surface: float
    micro_flaws: int
    authentic: bool

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "GradeInputs":
        if not isinstance(value, Mapping) or len(value) > 24:
            raise ValueError("카드 분석자료 형식 오류")
        return cls(
            centering_front=_centering_larger_side(value.get("centering_front", 50.0)),
            centering_back=_centering_larger_side(value.get("centering_back", 50.0)),
            corners=safe_float(value.get("corners", 10.0), 1.0, minimum=1.0, maximum=10.0),
            edges=safe_float(value.get("edges", 10.0), 1.0, minimum=1.0, maximum=10.0),
            surface=safe_float(value.get("surface", 10.0), 1.0, minimum=1.0, maximum=10.0),
            micro_flaws=_flaw_count(value.get("micro_flaws", 0)),
            authentic=safe_bool(value.get("is_authentic", True), default=False),
        )


def estimate_grades(values: Mapping[str, Any]) -> dict[str, Any]:
    """Estimate five grades conservatively using published information only."""
    card = GradeInputs.from_mapping(values)
    if not card.authentic:
        return {"ok": False, "status": "FAILED", "reason": "가품 의심 또는 진위 확인 실패", "grades": {}}

    front, back = card.centering_front, card.centering_back
    centering_score = max(1.0, 10.0 - max(front - 50.0, (back - 50.0) * 0.5) * 0.15)
    surface_adjusted = max(1.0, card.surface - card.micro_flaws * 0.5)
    components = (centering_score, card.corners, card.edges, surface_adjusted)
    weakest = min(components)

    # PSA 10 specifically requires approximately 55/45 front and 75/25 reverse.
    if front <= 55.0 and back <= 75.0 and min(card.corners, card.edges, card.surface) >= 9.5 and card.micro_flaws == 0:
        psa = 10.0
    else:
        psa = min(9.0, max(1.0, float(math.floor(weakest))))

    # BGS Pristine is stricter; exact unpublished subgrade combinations are not fabricated.
    if front == 50.0 and back <= 60.0 and min(card.corners, card.edges, card.surface) >= 10.0 and card.micro_flaws == 0:
        bgs = 10.0
    else:
        bgs = min(9.5, _half_floor(min(weakest + 0.5, sum(components) / 4.0)))

    cgc = min(10.0, _half_floor((sum(components) / 4.0 + weakest) / 2.0 + 0.25))
    if front > 55.0 or back > 75.0 or card.micro_flaws:
        cgc = min(9.5, cgc)

    advisory_score = max(100, min(1000, round(sum(components) * 25.0 - card.micro_flaws * 10.0)))
    tag = tag_score_to_grade(advisory_score)

    # BRG publishes inspection categories, but not a full threshold table.
    brg = _half_floor(min(sum(components) / 4.0, weakest + 0.5))
    if card.micro_flaws:
        brg = min(9.0, brg)

    return {
        "ok": True,
        "status": "SUCCESS",
        "grades": {"PSA": psa, "BGS": bgs, "CGC": cgc, "TAG": tag["grade"], "BRG": brg},
        "tag": {**tag, "score_kind": "photo_advisory_not_official_DIG"},
        "components": {
            "centering_front_larger_side": front,
            "centering_back_larger_side": back,
            "centering": round(centering_score, 2),
            "corners": card.corners,
            "edges": card.edges,
            "surface": card.surface,
            "micro_flaws": card.micro_flaws,
        },
        "official_grade": False,
        "notice": "사진 기반 사전 참고값이며 실제 업체 감정·정가품 판정을 대체하지 않습니다.",
    }


def _card_name(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("카드명 형식 오류")
    name = " ".join(value.split())
    if not name or len(name) > MAX_CARD_NAME or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("카드명 길이 또는 제어문자 오류")
    return name


def _grade_key(grade: float) -> str:
    return str(int(grade)) if grade.is_integer() else str(grade)


def verified_card_valuation(
    card_name: str,
    card_values: Mapping[str, Any],
    grade_prices_krw: Mapping[str, Any] | None = None,
    *,
    raw_krw: Any = 0,
    exchange_rate: Any = 1350.0,
    price_source: str = "exact_company_grade_observation",
) -> dict[str, Any]:
    """Use exact company+grade observations; never manufacture price multipliers."""
    name = _card_name(card_name)
    result = estimate_grades(card_values)
    if not result["ok"]:
        return {**result, "card_name": name, "valuations": {}}
    profiles = grade_prices_krw if isinstance(grade_prices_krw, Mapping) else {}
    source_kind = price_source if price_source in {
        "exact_company_grade_observation", "user_provided_exact_grade"
    } else "user_provided_exact_grade"
    rate = safe_float(exchange_rate, 1350.0, minimum=100.0, maximum=10_000.0)
    raw = safe_int(raw_krw, 0, minimum=0, maximum=MAX_PRICE_KRW)
    valuations = {}
    for company, grade in result["grades"].items():
        company_prices = profiles.get(company, {})
        exact = company_prices.get(_grade_key(float(grade)), 0) if isinstance(company_prices, Mapping) else 0
        krw = safe_int(exact, 0, minimum=0, maximum=MAX_PRICE_KRW)
        valuations[company] = {
            "grade": grade,
            "grade_key": _grade_key(float(grade)),
            "available": krw > 0,
            "krw": krw if krw else None,
            "usd": round(krw / rate, 2) if krw else None,
            "source": source_kind if krw else "unavailable",
            "reason": None if krw else "해당 업체·정확한 등급의 확인 거래가격 없음",
        }
    return {**result, "card_name": name, "raw_krw": raw or None, "exchange_rate": rate, "valuations": valuations}


class _SoldListingParser(HTMLParser):
    """Collect a price only from a listing block with an explicit sold marker."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.listing_depth = 0
        self.listing_parts: list[str] = []
        self.price_depth = 0
        self.price_parts: list[str] = []
        self.listings: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if len(self.listings) >= MAX_SOLD_SAMPLES:
            return
        classes = set((dict(attrs).get("class") or "").split())
        if tag == "li" and "s-item" in classes and self.listing_depth == 0:
            self.listing_depth = 1
            self.listing_parts = []
            self.price_parts = []
            self.price_depth = 0
            return
        if self.listing_depth:
            if tag in VOID_HTML_TAGS:
                return
            self.listing_depth += 1
            if "s-item__price" in classes and self.price_depth == 0:
                self.price_depth = self.listing_depth

    def handle_endtag(self, tag: str) -> None:
        if not self.listing_depth or tag in VOID_HTML_TAGS:
            return
        if self.price_depth == self.listing_depth:
            self.price_depth = 0
        self.listing_depth -= 1
        if self.listing_depth == 0:
            self.listings.append((" ".join(self.listing_parts), " ".join(self.price_parts)))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in VOID_HTML_TAGS:
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if not self.listing_depth or len(data) > 2_000:
            return
        if len(self.listing_parts) < 80:
            self.listing_parts.append(data)
        if self.price_depth and len(self.price_parts) < 10:
            self.price_parts.append(data)


def extract_sold_prices(html: str) -> dict[str, Any]:
    """Return a robust median after rejecting unsold and obvious outlier rows."""
    if not isinstance(html, str) or len(html.encode("utf-8")) > MAX_HTML_BYTES:
        raise ValueError("판매완료 HTML 크기 또는 형식 제한 초과")
    parser = _SoldListingParser()
    parser.feed(html)
    samples: list[float] = []
    for listing_text, price_text in parser.listings:
        lowered = listing_text.lower()
        confirmed = bool(re.search(r"(?<![a-z])sold(?![a-z])", lowered)) or any(
            marker in listing_text for marker in ("판매완료", "구매 완료")
        )
        misleading = bool(re.search(r"\b(?:unsold|not\s+sold|sold\s+out)\b", lowered))
        if not confirmed or misleading:
            continue
        if re.search(r"\bto\b|\s-\s", price_text, re.I):
            continue
        found = re.search(r"(?:US\s*)?\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)", price_text, re.I)
        if not found:
            continue
        amount = safe_float(found.group(1).replace(",", ""), 0.0)
        if 0.0 < amount <= MAX_PRICE_USD:
            samples.append(amount)
    median = statistics.median(samples) if samples else 0.0
    if len(samples) >= 3 and median > 0:
        deviations = [abs(price - median) for price in samples]
        mad = statistics.median(deviations)
        ceiling = max(median * 3.0, median + max(mad, median * 0.1) * 6.0)
        floor = max(0.01, min(median / 3.0, median - max(mad, median * 0.1) * 6.0))
        samples = [price for price in samples if floor <= price <= ceiling]
    return {
        "ok": bool(samples),
        "sold_only": True,
        "sample_count": len(samples),
        "median_usd": round(statistics.median(samples), 2) if samples else None,
        "prices_usd": samples,
        "confidence": "observed_sold_listings" if samples else "no_confirmed_sold_listing",
    }


def ebay_sold_url(card_name: str) -> str:
    query = urllib.parse.urlencode({"_nkw": _card_name(card_name), "LH_Sold": "1", "LH_Complete": "1"})
    url = f"https://www.ebay.com/sch/i.html?{query}"
    return validate_public_https_url(url, EBAY_HOSTS)


def fetch_ebay_sold_prices(card_name: str) -> dict[str, Any]:
    """Optional user-triggered collection; failure never becomes a fake price."""
    url = ebay_sold_url(card_name)
    request = urllib.request.Request(url, headers={"User-Agent": "TCG-Grader/84 verified-sold-price"})
    try:
        with safe_urlopen(request, timeout=env_int("TCG_HTTP_TIMEOUT", 12, 5, 30), allowed_hosts=EBAY_HOSTS) as response:
            kind = response.headers.get("Content-Type", "").lower()
            if kind and "html" not in kind:
                raise ValueError("판매완료 응답 Content-Type 오류")
            payload = response.read(MAX_HTML_BYTES + 1)
            if len(payload) > MAX_HTML_BYTES:
                raise ValueError("판매완료 응답 크기 제한 초과")
        return {**extract_sold_prices(payload.decode("utf-8", "replace")), "url": url}
    except NETWORK_ERRORS as exc:
        return {"ok": False, "sold_only": True, "sample_count": 0, "median_usd": None,
                "error_type": type(exc).__name__, "reason": "판매완료 거래자료에 연결하지 못했습니다."}


if __name__ == "__main__":
    example = verified_card_valuation(
        "LILLIE SM1M 065/060",
        {"centering_front": 50, "centering_back": 50, "corners": 10, "edges": 10,
         "surface": 10, "micro_flaws": 0, "is_authentic": True},
        {"BRG": {"9": 450_000, "10": 2_000_000}},
        raw_krw=300_000,
    )
    assert example["grades"]["PSA"] == 10
    assert example["grades"]["TAG"] == 10
    assert tag_score_to_grade(950)["grade"] == 10
    assert example["valuations"]["BRG"]["krw"] == 2_000_000
    assert example["valuations"]["PSA"]["krw"] is None
    assert not safe_bool("false")
    print("PASS: 5개 업체 공식기준 사전검사 · 정확한 등급 거래가격 · TAG 950점=10")
