"""Fail-closed adapter registry for Chinese-edition official TCG catalogs.

A provider must be independently verified before registration. This module
does not scrape arbitrary URLs, promote candidates or infer market prices.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit
import re

EDITIONS = frozenset({"CN-S", "CN-T"})
LOCALES = {"CN-S": frozenset({"CN"}), "CN-T": frozenset({"HK", "TW"})}
GAMES = frozenset({"Pokémon", "One Piece", "Naruto"})
MAX_SOURCES = 12


@dataclass(frozen=True)
class OfficialCatalogSource:
    game: str
    edition: str
    locale: str
    index_url: str
    detail_path_pattern: str
    evidence_id: str


def validate_source(source: OfficialCatalogSource, *, verified_hosts: frozenset[str]) -> bool:
    if not isinstance(source, OfficialCatalogSource):
        return False
    if source.game not in GAMES or source.edition not in EDITIONS:
        return False
    if source.locale not in LOCALES[source.edition]:
        return False
    if not isinstance(source.evidence_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{8,80}", source.evidence_id):
        return False
    try:
        parsed = urlsplit(source.index_url)
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port:
            return False
        if parsed.hostname not in verified_hosts or parsed.query or parsed.fragment:
            return False
        if not parsed.path.startswith("/") or ".." in parsed.path:
            return False
        if len(source.detail_path_pattern) > 160 or not source.detail_path_pattern.startswith("^"):
            return False
        if not source.detail_path_pattern.endswith("$"):
            return False
        re.compile(source.detail_path_pattern)
    except (ValueError, TypeError, re.error):
        return False
    return True


def validate_sources(sources, *, verified_hosts: frozenset[str]) -> bool:
    if not isinstance(sources, (tuple, list)) or len(sources) > MAX_SOURCES:
        return False
    if not all(validate_source(source, verified_hosts=verified_hosts) for source in sources):
        return False
    identities = [(source.game, source.edition, source.locale, source.index_url) for source in sources]
    return len(identities) == len(set(identities))


def catalog_candidate(source: OfficialCatalogSource, *, title: str, detail_url: str, checked_at: str) -> dict | None:
    """Create a review-only candidate, never a confirmed BOX or sale."""
    if not isinstance(title, str) or not 3 <= len(title.strip()) <= 150:
        return None
    if not isinstance(detail_url, str) or len(detail_url) > 450:
        return None
    try:
        index = urlsplit(source.index_url)
        detail = urlsplit(detail_url)
        if detail.scheme != "https" or detail.hostname != index.hostname or detail.netloc != index.netloc:
            return None
        if detail.query or detail.fragment or not re.fullmatch(source.detail_path_pattern, detail.path):
            return None
    except (TypeError, ValueError, re.error):
        return None
    return {
        "game": source.game,
        "region": source.edition,
        "market_locale": source.locale,
        "name": title.strip(),
        "asset": "UNVERIFIED_PRODUCT",
        "package_type": "상품 형태 확인 필요",
        "source": detail_url,
        "source_grade": "official_catalog_candidate",
        "source_evidence_id": source.evidence_id,
        "source_checked_at": checked_at,
        "market_eligible": False,
        "price_evidence": "NONE",
        "official_price": "확인 중",
        "market_decision": "HOLD",
        "investment_score": None,
    }


# Official landing pages verified through the publishers' own language/region
# navigation. These are discovery watch targets, NOT enabled product parsers.
# Never promote a landing-page mention to a verified BOX or market listing.
OFFICIAL_WATCH_SOURCES = (
    {"game": "One Piece", "edition": "CN-S", "locale": "CN",
     "url": "https://www.onepiece-cardgame.cn/", "state": "watch_only"},
    {"game": "One Piece", "edition": "CN-T", "locale": "HK",
     "url": "https://asia-tc.onepiece-cardgame.com/", "state": "watch_only"},
    {"game": "One Piece", "edition": "CN-T", "locale": "TW",
     "url": "https://asia-tc.onepiece-cardgame.com/", "state": "watch_only"},
    {"game": "Naruto", "edition": "CN-S", "locale": "CN",
     "url": "https://naruto-ncg.cn/", "state": "watch_only"},
    {"game": "Naruto", "edition": "CN-T", "locale": "HK",
     "url": "https://www.naruto-cardgame.com/asia-tc/", "state": "watch_only"},
    {"game": "Naruto", "edition": "CN-T", "locale": "TW",
     "url": "https://www.naruto-cardgame.com/asia-tc/", "state": "watch_only"},
)


def official_watch_targets() -> tuple[dict, ...]:
    """Return read-only source candidates; no unverified HTML parser enabled."""
    return tuple(dict(row) for row in OFFICIAL_WATCH_SOURCES)
