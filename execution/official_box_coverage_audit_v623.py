#!/usr/bin/env python3
"""V623: deterministic OFFLINE audit of official BOX/pack coverage, not a price feed.

Reads only locally packaged registry/catalog JSON. Does not crawl, publish data,
grade cards, invent product specifications or treat listings as completed sales.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
COUNTRIES = ("KR", "JP", "US")
PRODUCT_TYPES = ("BOX", "BOOSTER_PACK", "PRERELEASE_BOX")
HOSTS = {
    "Pokémon": ("pokemoncard.co.kr", "pokemon-card.com", "30th.pokemon-card.com"),
    "ONE PIECE": ("onepiece-cardgame.kr", "en.onepiece-cardgame.com"),
    "GUNDAM CARD GAME": ("gundam-gcg.com",),
    "Digimon Card Game": ("digimoncard.com",),
    "Star Wars: Unlimited": ("starwarsunlimited.com",),
    "DRAGON BALL SUPER: FUSION WORLD": ("dbs-cardgame.com",),
    "Yu-Gi-Oh!": ("yugioh-card.com",),
    "Disney Lorcana": ("disneylorcana.com",),
    "Godzilla Card Game": ("godzilla-cardgame.com",),
    "Palworld OFFICIAL CARD GAME": ("palworld-official-cardgame.com",),
    "Magic: The Gathering": ("magic.wizards.com",),
    "NARUTO": ("narutotcgmythos.com",),
    "UNION ARENA": ("unionarena-tcg.com",),
    "Weiß Schwarz": ("ws-tcg.com",),
    "Flesh and Blood TCG": ("fabtcg.com",),
    "Final Fantasy TCG": ("fftcg.square-enix-games.com",),
    "Cardfight!! Vanguard": ("cf-vanguard.com",),
}
MAX_FILE_BYTES = 3_000_000
MAX_PRODUCTS = 3000
CARD_COUNT = re.compile(r"^[1-9][0-9]{0,2}(?:\+[1-9][0-9]?)?$")
CODE = re.compile(r"^[A-Za-z0-9_-]{2,80}$")


class CoverageError(ValueError):
    pass


def _load_json(path: Path):
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_FILE_BYTES:
        raise CoverageError("MISSING_OR_OVERSIZED_LOCAL_FILE")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise CoverageError("INVALID_LOCAL_JSON") from exc


def _trusted_url(value, game):
    if not isinstance(value, str) or len(value) > 500:
        return False
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError:
        return False
    return (parsed.scheme == "https" and bool(host)
            and parsed.username is None and parsed.password is None
            and port in (None, 443)
            and not parsed.fragment
            and any(host == allowed or host.endswith("." + allowed)
                    for allowed in HOSTS.get(game, ())))


def audit(registry, catalog, *, as_of=None):
    """Return explicit sampling gaps across declared game-region pairs."""
    today = as_of or date.today()
    if not isinstance(today, date):
        raise CoverageError("INVALID_AS_OF")
    if not isinstance(registry, dict) or registry.get("schema_version") != 1:
        raise CoverageError("INVALID_GAME_REGISTRY")
    games = registry.get("games")
    if not isinstance(games, list) or not 1 <= len(games) <= 64:
        raise CoverageError("INVALID_GAME_REGISTRY")
    if not isinstance(catalog, dict) or catalog.get("schema_version") != 1:
        raise CoverageError("INVALID_OFFICIAL_CATALOG")
    products = catalog.get("products")
    if not isinstance(products, list) or len(products) > MAX_PRODUCTS:
        raise CoverageError("INVALID_OFFICIAL_CATALOG")
    canonical = {}
    for g in games:
        if not isinstance(g, dict) or not isinstance(g.get("id"), str) or not isinstance(g.get("canonical"), str):
            raise CoverageError("INVALID_GAME_ROW")
        if g["id"] in canonical:
            raise CoverageError("DUPLICATE_GAME")
        regions = g.get("regions")
        if not isinstance(regions, list) or any(r not in (*COUNTRIES, "GLOBAL") for r in regions):
            raise CoverageError("INVALID_GAME_REGIONS")
        canonical[g["id"]] = g
    by_name = {g["canonical"]: g for g in canonical.values()}
    if len(by_name) != len(canonical):
        raise CoverageError("DUPLICATE_CANONICAL_GAME")
    by_cell = defaultdict(list)
    ids = set()
    distinct = set()
    for p in products:
        if not isinstance(p, dict) or not isinstance(p.get("id"), str):
            raise CoverageError("INVALID_PRODUCT_ROW")
        if p["id"] in ids:
            raise CoverageError("DUPLICATE_OFFICIAL_PRODUCT_ID")
        ids.add(p["id"])
        name, country, kind = p.get("game"), p.get("country"), p.get("product_type")
        if name not in by_name or country not in COUNTRIES or kind not in PRODUCT_TYPES:
            raise CoverageError("INVALID_PRODUCT_CLASSIFICATION")
        regions = by_name[name].get("regions", [])
        if country not in regions and "GLOBAL" not in regions:
            raise CoverageError("PRODUCT_COUNTRY_OUTSIDE_GAME_REGION")
        if not _trusted_url(p.get("source"), name):
            raise CoverageError("UNTRUSTED_OR_UNMATCHED_OFFICIAL_SOURCE")
        if not CODE.fullmatch(str(p.get("set_code") or "")) or not isinstance(p.get("name"), str) or not p["name"].strip():
            raise CoverageError("INVALID_PRODUCT_IDENTITY")
        if p["set_code"].startswith("LOCAL-") and p.get("set_code_verified") is not False:
            raise CoverageError("UNVERIFIED_LOCAL_CODE_MUST_BE_MARKED")
        ident = (name, country, kind, p["set_code"].casefold())
        if ident in distinct:
            raise CoverageError("DUPLICATE_OFFICIAL_PRODUCT_VARIANT")
        distinct.add(ident)
        when = p.get("release_date")
        if when:
            try:
                if date.fromisoformat(when).isoformat() != when:
                    raise ValueError
            except (ValueError, TypeError) as exc:
                raise CoverageError("INVALID_PRODUCT_RELEASE_DATE") from exc
        elif kind != "PRERELEASE_BOX" and not (p.get("release_date_unverified") is True and p.get("source_checked_at")):
            raise CoverageError("MISSING_PRODUCT_RELEASE_DATE")
        elif p.get("set_release_date"):
            try:
                if date.fromisoformat(p["set_release_date"]).isoformat() != p["set_release_date"]:
                    raise ValueError
            except (TypeError, ValueError) as exc:
                raise CoverageError("INVALID_SET_RELEASE_DATE") from exc
        if p.get("release_date_unverified") is True and bool(when):
            raise CoverageError("UNVERIFIED_RELEASE_DATE_CONFLICT")
        if "event_start_date" in p:
            event_date = p.get("event_start_date")
            try:
                if not isinstance(event_date, str) or date.fromisoformat(event_date).isoformat() != event_date:
                    raise ValueError
            except (ValueError, TypeError) as exc:
                raise CoverageError("INVALID_PRERELEASE_EVENT_DATE") from exc
            if kind != "PRERELEASE_BOX":
                raise CoverageError("EVENT_DATE_NOT_PRODUCT_RELEASE")
        count = p.get("packs_per_box")
        if kind in ("BOX", "PRERELEASE_BOX"):
            if type(count) is not int or not 1 <= count <= 100:
                raise CoverageError("BOX_PACK_COUNT_REQUIRED")
        elif count is not None:
            raise CoverageError("PACK_IS_NOT_BOX")
        cards = p.get("cards_per_pack")
        if cards is not None and (not isinstance(cards, str) or not CARD_COUNT.fullmatch(cards)):
            raise CoverageError("INVALID_CARDS_PER_PACK")
        msrp = p.get("msrp")
        if msrp is not None:
            if not isinstance(msrp, dict):
                raise CoverageError("INVALID_MSRP")
            currency = {"KR": "KRW", "JP": "JPY", "US": "USD"}[country]
            amount = msrp.get("amount")
            if msrp.get("currency") != currency or msrp.get("unit") != ("PACK" if kind == "BOOSTER_PACK" else "BOX"):
                raise CoverageError("INVALID_MSRP_CURRENCY_OR_UNIT")
            if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not 0 < amount < 100000000:
                raise CoverageError("INVALID_MSRP_AMOUNT")
        forbidden = ("market_price", "verified_sales", "verified_stock", "psa_grade", "pull_rate")
        if any(f in p for f in forbidden):
            raise CoverageError("UNSUPPORTED_MARKET_OR_GRADE_CLAIM")
        by_cell[(name, country)].append(p)
    cells = []
    by_game = {}
    reported_pairs = 0
    declared_pairs = 0
    gaps = 0
    for game_id, g in sorted(canonical.items()):
        n = g["canonical"]
        per_game = {"id": game_id, "state": g.get("state"), "official_product_records": 0,
                    "declared_regions": [], "regions_with_official_records": []}
        for country in COUNTRIES:
            declared = country in g["regions"] or "GLOBAL" in g["regions"]
            entries = by_cell[(n, country)]
            kinds = Counter(e["product_type"] for e in entries)
            if declared:
                declared_pairs += 1
                per_game["declared_regions"].append(country)
                if entries:
                    reported_pairs += 1
                    per_game["regions_with_official_records"].append(country)
                else:
                    gaps += 1
            cell = {"game_id": game_id, "country": country, "region_declared": declared,
                    "official_box_count": kinds["BOX"],
                    "official_booster_pack_count": kinds["BOOSTER_PACK"],
                    "official_prerelease_box_count": kinds["PRERELEASE_BOX"],
                    "official_product_count": len(entries),
                    "status": ("NOT_DECLARED_FOR_GAME" if not declared
                               else "OFFICIAL_PRODUCT_SAMPLE_PRESENT" if entries
                               else "OFFICIAL_PRODUCT_COVERAGE_GAP"),
                    "missing": ([] if not declared else [
                        *([] if kinds["BOX"] else ["SEALED_BOX_SPEC_NOT_YET_REVIEWED"]),
                        *([] if kinds["BOOSTER_PACK"] else ["PACK_PRODUCT_NOT_SEPARATELY_REVIEWED"]),
                    ]),
                    "noncatalog_evidence_not_audited": ["FULL_CARD_LIST", "HIT_IDENTITY",
                        "PULL_RATE", "COMPLETED_SALE", "LIVE_STOCK", "IMAGE_LICENSE"]}
            cells.append(cell)
            per_game["official_product_records"] += len(entries)
        by_game[game_id] = per_game
    return {"schema_version": 1, "status": "PARTIAL_OFFICIAL_PRODUCT_COVERAGE",
            "as_of": today.isoformat(), "registry_games": len(canonical),
            "reviewed_official_product_records": len(products),
            "declared_game_country_pairs": declared_pairs,
            "pairs_with_any_official_product": reported_pairs,
            "game_country_product_coverage_gaps": gaps,
            "game_summary": by_game, "cells": cells,
            "limitations": [
                "OFFLINE_SNAPSHOT_ONLY_NOT_LIVE_CRAWL",
                "OFFICIAL_PRODUCT_IS_NOT_COMPLETED_SALE_OR_LIVE_STOCK",
                "OFFICIAL_PRODUCT_IS_NOT_FULL_CARD_LIST_OR_VERIFIED_HIT_PROBABILITY",
                "MISSING_FROM_LOCAL_CATALOG_DOES_NOT_MEAN_NO_PRODUCT_EXISTS",
                "NEW_RETAIL_PRICE_OR_BOX_QUANTITY_MUST_NOT_BE_INFERRED",
            ]}


def main():
    ap = argparse.ArgumentParser(description="Free local official BOX and TCG data-gap audit")
    ap.add_argument("--registry", type=Path, default=ROOT / "tcg_game_registry.json")
    ap.add_argument("--catalog", type=Path, default=ROOT / "tcg_official_product_catalog_v599.json")
    ap.add_argument("--output", type=Path, help="Optional local result JSON. Never auto-upload.")
    args = ap.parse_args()
    try:
        report = audit(_load_json(args.registry), _load_json(args.catalog))
        output = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.write_text(output, encoding="utf-8")
        else:
            print(output, end="")
        return 0
    except (CoverageError, OSError) as exc:
        print(json.dumps({"status":"HOLD", "reason":str(exc) if isinstance(exc,CoverageError) else "LOCAL_READ_ERROR"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
