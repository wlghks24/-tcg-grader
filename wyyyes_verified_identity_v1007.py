"""V1007: fail-closed binding of public WYYYES quotes to independently reviewed cards.

A marketplace title, fuzzy OCR result, reference-only catalog, or previous quote
must never become an authoritative card name. No network requests or writes.
"""
from __future__ import annotations

from datetime import datetime, timezone, date
import json
import math
import os
from pathlib import Path
import re
import stat
import unicodedata
from urllib.parse import urlsplit

CATALOG_SCHEMA = "tcg-reviewed-market-identity/v1007"
MAX_CATALOG_BYTES = 120_000
MAX_ENTRIES = 500
MAX_QUOTE_AGE_SECONDS = 72 * 3600
OFFICIAL_HOSTS = {
    "pokemon": frozenset(("www.pokemon-card.com", "pokemon-card.com", "www.pokemon.com", "pokemon.com")),
    "onepiece": frozenset(("en.onepiece-cardgame.com", "onepiece-cardgame.com")),
    # No independently confirmed Naruto card-level catalogue host yet.
    "naruto": frozenset(),
}
MARKET_HOSTS = frozenset(("wyyyes.com", "www.wyyyes.com"))


def _game(value: object) -> str:
    raw = unicodedata.normalize("NFKD", str(value or "")).casefold()
    game = re.sub(r"[^a-z0-9]", "", raw)
    return game if game in OFFICIAL_HOSTS else ""


def _text(value: object) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value or "")).strip()).upper()


def _exact_token(title: str, value: str) -> bool:
    token = _text(value)
    if not token or len(token) > 120:
        return False
    return re.search(r"(?<!\w)" + re.escape(token) + r"(?!\w)", _text(title)) is not None


def _official_url(url: object, game: str) -> bool:
    try:
        split = urlsplit(str(url or ""))
        return (split.scheme == "https" and not split.username and not split.password
                and split.port in (None, 443) and split.hostname in OFFICIAL_HOSTS.get(game, ()))
    except ValueError:
        return False


def _market_url(url: object) -> bool:
    try:
        split = urlsplit(str(url or ""))
        return (split.scheme == "https" and not split.username and not split.password
                and split.port in (None, 443) and split.hostname in MARKET_HOSTS
                and split.path.startswith("/category/"))
    except ValueError:
        return False


def _fresh_at(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 48:
        return False
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return False
        delta = (datetime.now(timezone.utc) - stamp.astimezone(timezone.utc)).total_seconds()
        return 0 <= delta <= MAX_QUOTE_AGE_SECONDS
    except (ValueError, TypeError, OverflowError):
        return False


def _approved_rows(catalog: object) -> list[dict]:
    if (not isinstance(catalog, dict) or catalog.get("schema") != CATALOG_SCHEMA
            or catalog.get("reviewed_for_auto_price_link") is not True):
        return []
    records = catalog.get("entries")
    if not isinstance(records, list) or len(records) > MAX_ENTRIES:
        return []
    accepted = []
    for record in records:
        if not isinstance(record, dict) or record.get("identity_verified") is not True:
            continue
        if record.get("source_grade") != "official_card_catalog":
            continue
        game = _game(record.get("game"))
        region = str(record.get("region") or "").upper()
        fields = ("card_name", "card_number", "set_code", "printing")
        if not game or region not in {"KR", "JP", "US"}:
            continue
        if any(not isinstance(record.get(key), str) or not record[key].strip()
               or len(record[key]) > 120 for key in fields):
            continue
        if not _official_url(record.get("source_url"), game):
            continue
        try:
            reviewed = date.fromisoformat(record["reviewed_on"])
        except (KeyError, TypeError, ValueError):
            continue
        if reviewed > datetime.now(timezone.utc).date():
            continue
        accepted.append(record)
    return accepted


def load_reviewed_catalog(path: Path) -> dict | None:
    """Bounded read only; fail closed for symlink, oversized or malformed input."""
    try:
        if path.is_symlink():
            return None
        mode = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(str(path), mode)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_CATALOG_BYTES:
                return None
            with os.fdopen(fd, "rb", closefd=False) as handle:
                data = handle.read(MAX_CATALOG_BYTES + 1)
        finally:
            os.close(fd)
        if len(data) > MAX_CATALOG_BYTES:
            return None
        parsed = json.loads(data.decode("utf-8"))
        return parsed if isinstance(parsed, dict) else None
    except (OSError, UnicodeError, ValueError, TypeError):
        return None


def _printing_matches(title: str, printing: str) -> bool:
    name = _text(printing)
    if name in ("HOLO", "HOLOFOIL") and any(
        _exact_token(title, other) for other in ("REVERSE HOLO", "REVERSE HOLOFOIL")
    ):
        return False
    return _exact_token(title, name.replace("_", " "))


def _eligible_quote(quote: dict) -> bool:
    try:
        price = float(quote.get("price"))
    except (TypeError, ValueError, OverflowError):
        return False
    return (
        quote.get("platform") == "WYYYES"
        and _market_url(quote.get("source_url"))
        and _fresh_at(quote.get("collected_at"))
        and math.isfinite(price) and 100 <= price <= 100_000_000
        and quote.get("currency") == "KRW"
        and _game(quote.get("game")) != ""
        and quote.get("card_region") in ("KR", "JP", "US")
        and isinstance(quote.get("title"), str) and bool(quote["title"].strip())
        and isinstance(quote.get("card_number"), str) and bool(quote["card_number"].strip())
        and _exact_token(quote["title"], quote["card_number"])
    )


def bind_quote(quote: dict, catalog: object) -> dict:
    """Only one distinct *reviewed* printing can produce an automatic card name."""
    if not isinstance(quote, dict):
        return {"identity_binding_status": "HOLD_INVALID_QUOTE"}
    sanitized = dict(quote)
    for field in (
        "card_name", "identity_verified", "identity_binding_status",
        "identity_source_url", "identity_set_code", "identity_printing",
    ):
        sanitized.pop(field, None)
    sanitized["identity_binding_status"] = "HOLD_UNVERIFIED"
    if not _eligible_quote(sanitized):
        return sanitized
    title = sanitized["title"]
    matches = []
    for candidate in _approved_rows(catalog):
        if (_game(candidate.get("game")) != _game(sanitized.get("game"))
                or candidate.get("region") != sanitized.get("card_region")
                or _text(candidate.get("card_number")) != _text(sanitized.get("card_number"))):
            continue
        if not all((
            _exact_token(title, candidate["card_name"]),
            _exact_token(title, candidate["card_number"]),
            _exact_token(title, candidate["set_code"]),
            _printing_matches(title, candidate["printing"]),
        )):
            continue
        matches.append(candidate)
    if len(matches) != 1:
        return sanitized
    matched = matches[0]
    sanitized.update({
        "card_name": matched["card_name"],
        "identity_verified": True,
        "identity_binding_status": "VERIFIED_EXACT",
        "identity_source_url": matched["source_url"],
        "identity_set_code": matched["set_code"],
        "identity_printing": matched["printing"],
    })
    return sanitized


def bind_quotes(quotes: object, catalog: object) -> list[dict]:
    if not isinstance(quotes, list):
        return []
    return [bind_quote(q, catalog) for q in quotes[:36] if isinstance(q, dict)]
