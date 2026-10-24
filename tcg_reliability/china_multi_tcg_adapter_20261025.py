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
        if not source.detail_path_pattern.endswith("$") or not source.detail_path_pattern.startswith("^/"):
            return False
        # Disallow pathological backtracking, lookarounds and capturing groups.
        # Only simple anchored official product paths are permitted.
        if not re.fullmatch(r"[A-Za-z0-9_./-]+", source.detail_path_pattern[2:-1].replace("[0-9]+", "0")):
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


def catalog_candidate(source: OfficialCatalogSource, *, title: str, detail_url: str, checked_at: str, verified_hosts: frozenset[str] = frozenset()) -> dict | None:
    """Create a review-only candidate only from an independently approved source."""
    if not validate_source(source, verified_hosts=verified_hosts):
        return None
    if not isinstance(title, str) or not 3 <= len(title.strip()) <= 150:
        return None
    if not isinstance(detail_url, str) or len(detail_url) > 450:
        return None
    try:
        index = urlsplit(source.index_url)
        detail = urlsplit(detail_url)
        if (detail.scheme != "https" or detail.hostname != index.hostname or detail.netloc != index.netloc
                or detail.username or detail.password or detail.port):
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


# Keep a single CN UI tab while preserving exact edition identity in data.
# This mirrors the existing KR/JP/US per-game structure without conflating
# publisher coverage, language, market eligibility or physical product type.
DISPLAY_REGIONS = ("ALL", "KR", "JP", "US", "CN")


def display_region(edition: str) -> str | None:
    if edition in ("KR", "JP", "US"):
        return edition
    if edition in EDITIONS:
        return "CN"
    return None


def catalog_identity(row: dict) -> tuple[str, str, str, str] | None:
    """Never deduplicate different games, Chinese scripts or HK/TW locales."""
    if not isinstance(row, dict):
        return None
    game, edition, locale = row.get("game"), row.get("region"), row.get("market_locale")
    url = row.get("source")
    if game not in GAMES or edition not in EDITIONS or locale not in LOCALES[edition]:
        return None
    if not isinstance(url, str) or len(url) > 450:
        return None
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.port or parsed.query or parsed.fragment or not parsed.path.startswith("/")):
            return None
    except (ValueError, TypeError):
        return None
    return game, edition, locale, url


def group_catalog_by_game(rows: list[dict]) -> dict[str, dict[str, list[dict]]]:
    """UI projection only; do not write into the existing market watch schema."""
    result = {game: {region: [] for region in DISPLAY_REGIONS} for game in GAMES}
    seen: set[tuple[str, str, str, str]] = set()
    for row in rows:
        identity = catalog_identity(row)
        if identity is None or identity in seen:
            continue
        seen.add(identity)
        game = identity[0]
        result[game]["CN"].append(dict(row))
        result[game]["ALL"].append(dict(row))
    return result
