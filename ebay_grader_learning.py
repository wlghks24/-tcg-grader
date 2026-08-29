#!/usr/bin/env python3
"""eBay graded-card photo dataset collector and safe learning-row builder.

Design goals
------------
* Uses the official eBay Browse API only. It does not bypass bot protection.
* Collects Graded trading-card listings (condition ID 2750), structured grader,
  grade, certification number, title metadata, and listing images.
* Keeps eBay seller metadata as *candidate evidence*. It is never marked as an
  official grading result until the certification is separately verified.
* Deduplicates by eBay item, certification number, and downloaded image hash.
* Keeps slab photographs separate from raw-card user captures.
* Groups repeated copies of the same card design so train/holdout splitting can
  prevent artwork leakage.

The collector is useful for PSA/BGS/CGC/TAG/BRG reference corpora.  The output
can be fed to provider_segment_learning.py after certification verification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable

from safe_runtime import (
    atomic_write_json,
    safe_urlopen,
    safe_urlopen_no_redirect,
    validate_public_https_url,
)
from grading_accuracy_v99 import valid_actual_grade

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "ebay_grader_candidates.json"
DEFAULT_VERIFIED = ROOT / "verified_certifications.json"
DEFAULT_LEARNING_EXPORT = ROOT / "ebay_verified_learning_rows.json"

API_HOSTS = {"api.ebay.com"}
IMAGE_HOSTS = {"i.ebayimg.com"}
BROWSE_BASE = "https://api.ebay.com/buy/browse/v1"
GRADED_CONDITION_ID = "2750"
COMPANIES = ("PSA", "BGS", "CGC", "TAG", "BRG")
GAMES = ("pokemon", "onepiece", "naruto")
MAX_ITEMS_PER_QUERY = 25
MAX_ITEMS_PER_RUN = 120
MAX_IMAGES_PER_ITEM = 4
MAX_IMAGE_BYTES = 8_000_000
CERT_RE = re.compile(r"^[A-Za-z0-9._/-]{4,120}$")

COMPANY_PATTERNS = {
    "PSA": re.compile(r"\bPSA\b", re.I),
    "BGS": re.compile(r"\b(?:BGS|BECKETT)\b", re.I),
    "CGC": re.compile(r"\bCGC\b", re.I),
    "TAG": re.compile(r"\bTAG\b", re.I),
    "BRG": re.compile(r"\bBRG\b", re.I),
}
GAME_PATTERNS = {
    "pokemon": re.compile(r"\b(?:pokemon|pok[eé]mon)\b", re.I),
    "onepiece": re.compile(r"\b(?:one\s*piece|onepiece)\b", re.I),
    "naruto": re.compile(r"\bnaruto\b", re.I),
}
LANGUAGE_PATTERNS = {
    "jp": re.compile(r"\b(?:japanese|japan|jp)\b", re.I),
    "kr": re.compile(r"\b(?:korean|korea|kr)\b", re.I),
    "cn": re.compile(r"\b(?:chinese|china|cn)\b", re.I),
    "en": re.compile(r"\b(?:english|eng)\b", re.I),
}
FINISH_PATTERNS = {
    "manga": re.compile(r"\bmanga\b", re.I),
    "parallel": re.compile(r"\b(?:parallel|alt(?:ernative)?\s*art|alt\s*art)\b", re.I),
    "promo": re.compile(r"\bpromo\b", re.I),
    "holo": re.compile(r"\b(?:holo|holographic|foil)\b", re.I),
}


@dataclass(frozen=True)
class Candidate:
    item_id: str
    item_url: str
    title: str
    company: str
    grade: float
    certification_id: str
    game: str
    language: str
    finish: str
    card_identity: str
    image_urls: tuple[str, ...]
    structured_label: bool
    source: str = "ebay-browse-api"
    mode: str = "slab"


def _text(value: Any, limit: int = 500) -> str:
    value = str(value or "").strip()
    return re.sub(r"\s+", " ", value)[:limit]


def _finite_grade(value: Any) -> float | None:
    text = _text(value, 60)
    m = re.search(r"(?<!\d)(10(?:\.0)?|[1-9](?:\.5|\.0)?)(?!\d)", text)
    if not m:
        return None
    try:
        number = float(m.group(1))
    except ValueError:
        return None
    return number if 1 <= number <= 10 and math.isfinite(number) else None


def _descriptor_map(item: dict[str, Any]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    rows = item.get("conditionDescriptors")
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = _text(row.get("name"), 100).lower()
        values: list[str] = []
        for value in row.get("values", []) if isinstance(row.get("values"), list) else []:
            if not isinstance(value, dict):
                continue
            content = _text(value.get("content"), 120)
            if content:
                values.append(content)
            extra = value.get("additionalInfo")
            if isinstance(extra, list):
                values.extend(_text(x, 120) for x in extra if _text(x, 120))
        if name and values:
            out.setdefault(name, []).extend(values)
    return out


def _find_company(descriptors: dict[str, list[str]], title: str) -> tuple[str, bool]:
    joined = " ".join(v for values in descriptors.values() for v in values)
    for name, values in descriptors.items():
        if "grader" in name.lower():
            for company, pattern in COMPANY_PATTERNS.items():
                if pattern.search(" ".join(values)):
                    return company, True
    for company, pattern in COMPANY_PATTERNS.items():
        if pattern.search(joined):
            return company, True
    for company, pattern in COMPANY_PATTERNS.items():
        if pattern.search(title):
            return company, False
    return "", False


def _find_grade(descriptors: dict[str, list[str]], title: str, company: str) -> tuple[float | None, bool]:
    for name, values in descriptors.items():
        if "grade" in name.lower():
            for value in values:
                grade = _finite_grade(value)
                if grade is not None and valid_actual_grade(company, grade):
                    return grade, True
    # Some API payloads expose localized descriptor names.  If a descriptor value
    # itself is a valid numeric grade, accept it as structured only when there is
    # exactly one unambiguous grade-like value.
    numeric = []
    for values in descriptors.values():
        for value in values:
            grade = _finite_grade(value)
            if grade is not None and valid_actual_grade(company, grade):
                numeric.append(grade)
    unique = sorted(set(numeric))
    if len(unique) == 1:
        return unique[0], True
    pattern = re.compile(rf"\b{re.escape(company)}\s*(10|[1-9](?:\.5)?)\b", re.I)
    m = pattern.search(title)
    if m:
        grade = float(m.group(1))
        if valid_actual_grade(company, grade):
            return grade, False
    return None, False


def _find_certification(descriptors: dict[str, list[str]]) -> str:
    # Prefer explicit certification descriptor.  In localized payloads, open-text
    # additionalInfo is usually the certification number; only accept safe tokens.
    preferred: list[str] = []
    fallback: list[str] = []
    for name, values in descriptors.items():
        target = preferred if "cert" in name.lower() else fallback
        target.extend(values)
    for value in preferred + fallback:
        token = _text(value, 120).replace(" ", "")
        if CERT_RE.fullmatch(token) and not _finite_grade(token):
            return token
    return ""


def infer_game(title: str) -> str:
    return next((game for game, pattern in GAME_PATTERNS.items() if pattern.search(title)), "unknown")


def infer_language(title: str) -> str:
    return next((language for language, pattern in LANGUAGE_PATTERNS.items() if pattern.search(title)), "unknown")


def infer_finish(title: str) -> str:
    return next((finish for finish, pattern in FINISH_PATTERNS.items() if pattern.search(title)), "standard")


def card_identity(title: str, company: str, grade: float, game: str, language: str) -> str:
    """Build a conservative artwork identity for leakage-safe grouping.

    It intentionally removes grader/grade/sales noise but keeps set/card number,
    character, year, language, and game words whenever present.
    """
    text = title.lower()
    for pattern in COMPANY_PATTERNS.values():
        text = pattern.sub(" ", text)
    text = re.sub(r"\b(?:gem\s*mint|pristine|black\s*label|graded|grade|mint|pop\s*\d+)\b", " ", text)
    text = re.sub(r"(?<!\d)(?:10(?:\.0)?|[1-9](?:\.5|\.0)?)(?!\d)", " ", text, count=1)
    text = re.sub(r"\b(?:rare|card|tcg|ccg|authentic|authenticity|guarantee|free\s*shipping)\b", " ", text)
    text = re.sub(r"[^a-z0-9가-힣ぁ-んァ-ヶ一-龯#./+-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()[:140]
    prefix = f"{game}|{language}|"
    return prefix + (text or hashlib.sha256(title.encode("utf-8")).hexdigest()[:24])


def _image_urls(item: dict[str, Any]) -> tuple[str, ...]:
    urls: list[str] = []
    primary = item.get("image")
    if isinstance(primary, dict):
        url = _text(primary.get("imageUrl"), 2048)
        if url:
            urls.append(url)
    for row in item.get("additionalImages", []) if isinstance(item.get("additionalImages"), list) else []:
        if isinstance(row, dict):
            url = _text(row.get("imageUrl"), 2048)
            if url:
                urls.append(url)
    safe: list[str] = []
    for url in urls:
        try:
            validate_public_https_url(url, IMAGE_HOSTS)
        except ValueError:
            continue
        if url not in safe:
            safe.append(url)
        if len(safe) >= MAX_IMAGES_PER_ITEM:
            break
    return tuple(safe)


def parse_item(item: dict[str, Any]) -> Candidate | None:
    if not isinstance(item, dict):
        return None
    condition_id = _text(item.get("conditionId"), 20)
    if condition_id and condition_id != GRADED_CONDITION_ID:
        return None
    item_id = _text(item.get("itemId"), 160)
    title = _text(item.get("title"), 300)
    item_url = _text(item.get("itemWebUrl"), 2048)
    if not item_id or not title:
        return None
    try:
        validate_public_https_url(item_url, {"www.ebay.com", "ebay.com"})
    except ValueError:
        return None
    descriptors = _descriptor_map(item)
    company, structured_company = _find_company(descriptors, title)
    if company not in COMPANIES:
        return None
    grade, structured_grade = _find_grade(descriptors, title, company)
    if grade is None or not valid_actual_grade(company, grade):
        return None
    certification = _find_certification(descriptors)
    if not certification:
        return None
    images = _image_urls(item)
    if not images:
        return None
    game = infer_game(title)
    language = infer_language(title)
    finish = infer_finish(title)
    return Candidate(
        item_id=item_id,
        item_url=item_url,
        title=title,
        company=company,
        grade=float(grade),
        certification_id=certification,
        game=game,
        language=language,
        finish=finish,
        card_identity=card_identity(title, company, grade, game, language),
        image_urls=images,
        structured_label=bool(structured_company and structured_grade),
    )


def _api_get(url: str, token: str, timeout: int = 20) -> dict[str, Any]:
    validate_public_https_url(url, API_HOSTS)
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        "User-Agent": "TCG-Grader-Reference-Learner/1.0",
    })
    with safe_urlopen_no_redirect(req, timeout=timeout, allowed_hosts=API_HOSTS) as response:
        data = response.read(3_000_001)
    if len(data) > 3_000_000:
        raise ValueError("eBay API response too large")
    payload = json.loads(data.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("invalid eBay API payload")
    return payload


def _search_url(query: str, limit: int) -> str:
    params = {
        "q": query,
        "limit": str(max(1, min(MAX_ITEMS_PER_QUERY, limit))),
        "filter": f"conditionIds:{{{GRADED_CONDITION_ID}}}",
    }
    return f"{BROWSE_BASE}/item_summary/search?{urllib.parse.urlencode(params)}"


def _detail_url(item_id: str) -> str:
    return f"{BROWSE_BASE}/item/{urllib.parse.quote(item_id, safe='')}"


def discover(token: str, companies: Iterable[str] = COMPANIES,
             games: Iterable[str] = GAMES, per_query: int = 8,
             max_items: int = MAX_ITEMS_PER_RUN, pause: float = 0.15) -> list[Candidate]:
    if not token or len(token) < 20:
        raise ValueError("EBAY_OAUTH_TOKEN is required")
    candidates: dict[str, Candidate] = {}
    cert_seen: set[tuple[str, str]] = set()
    # Rotate games inside each grader.  If max_items is reached early, each
    # game has already received the same number of API query opportunities.
    for company in companies:
        for game in games:
            game_term = {"pokemon": "Pokemon", "onepiece": "One Piece", "naruto": "Naruto"}.get(game, game)
            company = company.upper()
            if company not in COMPANIES:
                continue
            summary = _api_get(_search_url(f"{game_term} {company} graded card", per_query), token)
            items = summary.get("itemSummaries", []) if isinstance(summary.get("itemSummaries"), list) else []
            for row in items[:per_query]:
                item_id = _text(row.get("itemId"), 160) if isinstance(row, dict) else ""
                if not item_id or item_id in candidates:
                    continue
                detail = _api_get(_detail_url(item_id), token)
                candidate = parse_item(detail)
                if candidate is None:
                    continue
                cert_key = (candidate.company, candidate.certification_id)
                if cert_key in cert_seen:
                    continue
                cert_seen.add(cert_key)
                candidates[candidate.item_id] = candidate
                if len(candidates) >= max_items:
                    return list(candidates.values())
                if pause:
                    time.sleep(max(0.0, min(2.0, pause)))
    return list(candidates.values())


def candidate_payload(rows: Iterable[Candidate]) -> dict[str, Any]:
    rows = list(rows)
    by_company = {company: sum(1 for row in rows if row.company == company) for company in COMPANIES}
    by_game = {game: sum(1 for row in rows if row.game == game) for game in (*GAMES, "unknown")}
    return {
        "version": 1,
        "source": "eBay Browse API",
        "policy": {
            "graded_condition_id": GRADED_CONDITION_ID,
            "seller_metadata_is_not_official_grade": True,
            "certification_verification_required_before_training": True,
            "slab_images_kept_separate_from_raw_user_photos": True,
            "same_card_artwork_grouped_for_leakage_safe_validation": True,
        },
        "counts": {"total": len(rows), "company": by_company, "game": by_game},
        "items": [asdict(row) for row in rows],
    }


def load_verified(path: Path) -> dict[tuple[str, str], float]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("certifications", []) if isinstance(data, dict) else []
    out: dict[tuple[str, str], float] = {}
    conflicts: set[tuple[str, str]] = set()
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or row.get("verified") is not True:
            continue
        company = _text(row.get("company"), 10).upper()
        cert = _text(row.get("certification_id"), 120).replace(" ", "")
        try:
            grade = float(row.get("grade"))
        except (TypeError, ValueError, OverflowError):
            continue
        key = (company, cert)
        if company not in COMPANIES or not CERT_RE.fullmatch(cert) or not valid_actual_grade(company, grade):
            continue
        if key in out and abs(out[key] - grade) > 1e-9:
            out.pop(key, None); conflicts.add(key); continue
        if key not in conflicts:
            out[key] = grade
    return out


def promote_verified(candidates: Iterable[Candidate], verified: dict[tuple[str, str], float]) -> list[dict[str, Any]]:
    """Promote only cert-verified rows. No raw prediction is invented here.

    Image analysis can later populate raw_pred/vision.  Keeping this export as
    ground-truth metadata prevents feedback loops and false precision.
    """
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        key = (candidate.company, candidate.certification_id)
        official = verified.get(key)
        if official is None or abs(official - candidate.grade) > 1e-9:
            continue
        rows.append({
            "company": candidate.company,
            "actual": official,
            "official_result": True,
            "certification_id": candidate.certification_id,
            "card_id": candidate.card_identity,
            "card_key": candidate.card_identity,
            "game": candidate.game,
            "language": candidate.language,
            "finish": candidate.finish,
            "mode": "slab",
            "source": "ebay-browse-api+official-cert-verification",
            "item_id": candidate.item_id,
            "item_url": candidate.item_url,
            "image_urls": list(candidate.image_urls),
        })
    return rows


def download_reference_image(url: str, target: Path, timeout: int = 20) -> dict[str, Any]:
    validate_public_https_url(url, IMAGE_HOSTS)
    request = urllib.request.Request(url, headers={"User-Agent": "TCG-Grader-Reference-Learner/1.0"})
    with safe_urlopen(request, timeout=timeout, allowed_hosts=IMAGE_HOSTS, max_redirects=2) as response:
        data = response.read(MAX_IMAGE_BYTES + 1)
        content_type = _text(response.headers.get("Content-Type"), 80).lower()
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("reference image too large")
    if not content_type.startswith("image/"):
        raise ValueError("reference URL did not return an image")
    digest = hashlib.sha256(data).hexdigest()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {"sha256": digest, "bytes": len(data), "content_type": content_type, "path": str(target)}


def _load_candidates(path: Path) -> list[Candidate]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("items", []) if isinstance(data, dict) else []
    out = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        try:
            out.append(Candidate(
                item_id=_text(row.get("item_id"), 160), item_url=_text(row.get("item_url"), 2048),
                title=_text(row.get("title"), 300), company=_text(row.get("company"), 10).upper(),
                grade=float(row.get("grade")), certification_id=_text(row.get("certification_id"), 120),
                game=_text(row.get("game"), 20), language=_text(row.get("language"), 20),
                finish=_text(row.get("finish"), 30), card_identity=_text(row.get("card_identity"), 180),
                image_urls=tuple(str(x) for x in row.get("image_urls", []) if isinstance(x, str))[:MAX_IMAGES_PER_ITEM],
                structured_label=row.get("structured_label") is True,
                source=_text(row.get("source"), 80) or "ebay-browse-api", mode="slab",
            ))
        except (TypeError, ValueError, OverflowError):
            continue
    return [row for row in out if row.company in COMPANIES and valid_actual_grade(row.company, row.grade)]


def self_test() -> dict[str, Any]:
    fixture = {
        "itemId": "v1|123456|0",
        "itemWebUrl": "https://www.ebay.com/itm/123456",
        "title": "2025 Pokemon Japanese Pikachu Promo PSA 10",
        "conditionId": "2750",
        "conditionDescriptors": [
            {"name": "Professional Grader", "values": [{"content": "PSA"}]},
            {"name": "Grade", "values": [{"content": "10"}]},
            {"name": "Certification Number", "values": [{"content": "12345678"}]},
        ],
        "image": {"imageUrl": "https://i.ebayimg.com/images/g/test/s-l1600.jpg"},
        "additionalImages": [{"imageUrl": "https://i.ebayimg.com/images/g/test2/s-l1600.jpg"}],
    }
    parsed = parse_item(fixture)
    assert parsed and parsed.company == "PSA" and parsed.grade == 10
    assert parsed.structured_label and parsed.game == "pokemon" and parsed.language == "jp"
    assert parsed.certification_id == "12345678" and len(parsed.image_urls) == 2
    verified = {("PSA", "12345678"): 10.0}
    promoted = promote_verified([parsed], verified)
    assert len(promoted) == 1 and promoted[0]["official_result"] is True
    assert promoted[0]["mode"] == "slab" and "raw_pred" not in promoted[0]
    # Seller/title evidence alone must not be promoted.
    assert promote_verified([parsed], {}) == []
    # Ungraded listing cannot enter the corpus.
    bad = dict(fixture); bad["conditionId"] = "4000"
    assert parse_item(bad) is None
    return {"ok": True, "tests": 8, "parsed_company": parsed.company,
            "card_identity": parsed.card_identity, "policy": "cert-verified-only-promotion"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="eBay 업체별 등급카드 사진 학습자료 수집")
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("discover")
    d.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    d.add_argument("--per-query", type=int, default=8)
    d.add_argument("--max-items", type=int, default=MAX_ITEMS_PER_RUN)
    p = sub.add_parser("promote")
    p.add_argument("--candidates", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--verified", type=Path, default=DEFAULT_VERIFIED)
    p.add_argument("--output", type=Path, default=DEFAULT_LEARNING_EXPORT)
    sub.add_parser("self-test")
    args = parser.parse_args(argv)
    if args.command == "discover":
        token = os.environ.get("EBAY_OAUTH_TOKEN", "").strip()
        rows = discover(token, per_query=max(1, min(25, args.per_query)), max_items=max(1, min(MAX_ITEMS_PER_RUN, args.max_items)))
        payload = candidate_payload(rows)
        atomic_write_json(args.output, payload, suffix=".ebay-candidates.tmp")
        print(json.dumps(payload["counts"], ensure_ascii=False, indent=2))
        return 0
    if args.command == "promote":
        rows = _load_candidates(args.candidates)
        verified = load_verified(args.verified)
        promoted = promote_verified(rows, verified)
        payload = {"version": 1, "rows": promoted, "count": len(promoted),
                   "policy": "official cert verification required; raw prediction added only after image analysis"}
        atomic_write_json(args.output, payload, suffix=".ebay-learning.tmp")
        print(json.dumps({"count": len(promoted)}, ensure_ascii=False))
        return 0
    print(json.dumps(self_test(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
