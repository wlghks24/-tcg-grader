#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V639 — free offline evidence discovery queue for ALL 30 TCGs.

30 games x 3 market scopes x 4 independent candidate types (BOX/set, upcoming,
HIT, promo). Zero API calls, zero paid services, zero browser scraping.
Entries and links are research leads, NEVER verified stock, sealed BOX, pricing,
pull rate, or completed sales. Python standard library only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from tcg_x_buylist_search_v631 import build_search_config, MARKET, LOCALES
from execution.official_box_coverage_audit_v623 import _trusted_url

ROOT = Path(__file__).resolve().parent
FIELD_KIND = (
    ("product_name_candidates", "BOX_SET"),
    ("upcoming_name_candidates", "UPCOMING_SET"),
    ("hit_name_candidates", "HIT_CARD"),
    ("promo_name_candidates", "PROMO_CARD"),
)
LABELS = {
    "JP": {"BOX_SET": "BOX", "UPCOMING_SET": "発売予定", "HIT_CARD": "買取", "PROMO_CARD": "プロモ"},
    "KR": {"BOX_SET": "박스", "UPCOMING_SET": "출시 예정", "HIT_CARD": "매입", "PROMO_CARD": "프로모"},
    "US": {"BOX_SET": "booster box", "UPCOMING_SET": "upcoming", "HIT_CARD": "buylist", "PROMO_CARD": "promo"},
}
MAX_TASKS = 6000
MAX_URL_LENGTH = 2000


def load_local(name):
    path = ROOT / name
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 3_000_000:
        raise ValueError("INVALID_LOCAL_FILE")
    return json.loads(path.read_text(encoding="utf-8"))


def identity(value):
    if not isinstance(value, str) or not 0 < len(value) <= 250:
        raise ValueError("INVALID_CANDIDATE_NAME")
    normalized = " ".join(unicodedata.normalize("NFKC", value).casefold().split())
    if not normalized or any(ord(c) < 32 for c in normalized):
        raise ValueError("INVALID_CANDIDATE_CONTROL")
    return normalized


def trusted_host(value):
    if not isinstance(value, str) or len(value) > 1000:
        return None
    try:
        u = urlsplit(value)
        if u.scheme != "https" or u.username or u.password or u.fragment or u.port not in (None, 443):
            return None
        host = (u.hostname or "").lower()
        if not host or "." not in host or host.endswith((".invalid", ".test", ".local")):
            return None
        return host
    except ValueError:
        return None


def search_url(engine, query):
    base = {"google": "https://www.google.com/search",
            "bing": "https://www.bing.com/search",
            "x": "https://x.com/search",
            "youtube": "https://www.youtube.com/results"}.get(engine)
    if not base or not query or len(query) > 900:
        raise ValueError("INVALID_SEARCH_QUERY")
    args = {"search_query" if engine == "youtube" else "q": query}
    if engine == "x":
        args["f"] = "live"
    uri = base + "?" + urlencode(args)
    if len(uri) > MAX_URL_LENGTH:
        raise ValueError("EXCESSIVELY_LONG_SEARCH_URL")
    return uri


def phrase(value):
    # Quoted search strings, not a query operator injection channel.
    safe = re.sub(r"[\"\\\r\n<>]", " ", str(value)).strip()
    safe = " ".join(safe.split())[:180]
    if not safe:
        raise ValueError("EMPTY_SEARCH_PHRASE")
    return '"' + safe + '"'


def raw_snapshot():
    reg = load_local("tcg_game_registry.json")
    leads = load_local("tcg_user_research_intake_v625.json")
    catalog = load_local("tcg_official_product_catalog_v599.json")
    supplements = [load_local("tcg_official_product_supplement_v" + version + ".json")
                   for version in ("630", "636", "637", "649", "654")]
    # Additive V657 is optional: absent files keep all earlier 91 records.
    # Present but malformed proof is never promoted or silently reclassified.
    v657_path = ROOT / "tcg_official_product_supplement_v657.json"
    if v657_path.exists() or v657_path.is_symlink():
        from tcg_official_overlay_v657 import validate_overlay
        extra = load_local(v657_path.name)
        supplements.append({"products": validate_overlay(extra, reg)})
    v659_path = ROOT / "tcg_official_product_supplement_v659.json"
    if v659_path.exists() or v659_path.is_symlink():
        from tcg_official_overlay_v659 import validate_additions
        if not (v657_path.exists() or v657_path.is_symlink()):
            raise ValueError("V659_REQUIRES_V657")
        supplements.append({"products": validate_additions(load_local(v659_path.name), reg)})
    v662_path = ROOT / "tcg_official_product_supplement_v662.json"
    if v662_path.exists() or v662_path.is_symlink():
        if not (v659_path.exists() or v659_path.is_symlink()):
            raise ValueError("V662_REQUIRES_V659")
        from tcg_official_overlay_v662 import validate_v662
        prior = catalog["products"] + sum((part["products"] for part in supplements), [])
        supplements.append({"products": validate_v662(load_local(v662_path.name), reg, prior)})
    if reg.get("schema_version") != 1 or not isinstance(reg.get("games"), list) or len(reg["games"]) != 30:
        raise ValueError("INVALID_30_REGISTRY")
    if leads.get("data_evidence_level") != "UNVERIFIED" or not isinstance(leads.get("records"), list) or len(leads["records"]) != 30:
        raise ValueError("INVALID_30_INTAKE")
    if catalog.get("schema_version") != 1 or not isinstance(catalog.get("products"), list):
        raise ValueError("INVALID_BASE_CATALOG")
    expected_append = ["tcg_official_product_catalog_v599.json",
                       "tcg_official_product_supplement_v630.json",
                       "tcg_official_product_supplement_v636.json",
                       "tcg_official_product_supplement_v637.json",
                       "tcg_official_product_supplement_v649.json"]
    for addon, parent in zip(supplements[:5], expected_append):
        if addon.get("schema_version") != 1 or addon.get("type") != "official_product_specifications_supplement" or not isinstance(addon.get("products"), list):
            raise ValueError("INVALID_OFFICIAL_SUPPLEMENT")
        if addon.get("base_catalog") != "tcg_official_product_catalog_v599.json":
            raise ValueError("INVALID_SUPPLEMENT_BASE")
        if parent != expected_append[0] and addon.get("append_after") != parent:
            raise ValueError("INVALID_SUPPLEMENT_CHAIN")
    return reg, leads, catalog["products"] + sum([s["products"] for s in supplements], [])


def prepare():
    reg, leads, official = raw_snapshot()
    names = {g["id"]: g for g in reg["games"]}
    rows = {r["game_id"]: r for r in leads}
    if len(names) != 30 or len(rows) != 30 or set(names) != set(rows):
        raise ValueError("DUPLICATE_OR_MISSING_GAME")
    for r in leads:
        if r.get("status") != "USER_SUBMITTED_UNVERIFIED":
            raise ValueError("UNVERIFIED_INPUT_MISCLASSIFIED")
        for field, _ in FIELD_KIND:
            if not isinstance(r.get(field), list):
                raise ValueError("MISSING_CANDIDATE_FIELD")
            for candidate in r[field]:
                identity(candidate)
    # A known region's source link is preferred to an unrelated language landing page.
    sources, box_count, product_count = {}, Counter(), Counter()
    if len({p.get("id") for p in official})!=len(official):
        raise ValueError("DUPLICATE_OFFICIAL_RECORD")
    for p in official:
        if not _trusted_url(p.get("source"),p.get("game")):
            raise ValueError("UNTRUSTED_OFFICIAL_RECORD")
        if p.get("product_type") not in ("BOX","BOOSTER_PACK","PRERELEASE_BOX"):
            raise ValueError("INVALID_PRODUCT_TYPE")
        if p["product_type"] in ("BOX","PRERELEASE_BOX"):
            if type(p.get("packs_per_box")) is not int or not 1<=p["packs_per_box"]<=100:
                raise ValueError("INVALID_BOX_PACK_QUANTITY")
        elif p.get("packs_per_box") is not None:
            raise ValueError("BOOSTER_PACK_NOT_SEALED_BOX")
        key = (p["game"], p["country"])
        if _trusted_url(p.get("source"), p["game"]):
            sources.setdefault(key, p["source"])
        product_count[key] += 1
        if p["product_type"] == "BOX":
            box_count[key] += 1
    return reg, leads, sources, box_count, product_count


def build_queue(*, game="ALL", region="ALL", kind="ALL", limit=None):
    reg, leads, sources, boxes, products = prepare()
    valid_game = {"ALL"} | {g["id"] for g in reg["games"]}
    if game not in valid_game or region not in ("ALL", *LOCALES) or kind not in ("ALL", *(x[1] for x in FIELD_KIND)):
        raise ValueError("UNKNOWN_QUEUE_FILTER")
    if limit is not None and (type(limit) is not int or not 1 <= limit <= MAX_TASKS):
        raise ValueError("INVALID_QUEUE_LIMIT")
    config = build_search_config()
    queue, seen = [], set()
    lookup = {r["game_id"]: r for r in leads}
    # Coverage/gap first; within each scope preserve source list order.
    for g in reg["games"]:
        if game != "ALL" and g["id"] != game:
            continue
        r = lookup[g["id"]]
        for market in LOCALES:
            if region != "ALL" and region != market:
                continue
            declared = market in g["regions"] or "GLOBAL" in g["regions"]
            key = (g["canonical"], market)
            site_source = sources.get(key) or g.get("official_source")
            host = trusted_host(site_source)
            if not host:
                raise ValueError("UNSAFE_REGISTRY_OFFICIAL_SOURCE")
            origin = "COUNTRY_MANUFACTURER_PRODUCT_SOURCE" if key in sources else "REGISTRY_SITE_SEARCH_SEED_ONLY"
            for field, item_kind in FIELD_KIND:
                if kind != "ALL" and item_kind != kind:
                    continue
                for candidate in r[field]:
                    normalized = identity(candidate)
                    unique = (g["id"], market, item_kind, normalized)
                    if unique in seen:
                        continue
                    seen.add(unique)
                    tag = LABELS[market][item_kind]
                    market_name = config[g["id"]][market]["hashtag"]
                    # One broad and one type-specific query: improve recall without asserting locality.
                    base = phrase(market_name) + " " + phrase(candidate)
                    typed = base + " " + phrase(tag)
                    doc_q = "site:" + host + " " + phrase(candidate)
                    task_id = hashlib.sha256("|".join(unique).encode("utf-8")).hexdigest()[:20]
                    queue.append({
                        "task_id": task_id, "game_id": g["id"], "canonical_game": g["canonical"], "market": market,
                        "region_declared": declared, "kind": item_kind, "candidate": candidate,
                        "evidence": "USER_SUBMITTED_UNVERIFIED",
                        "official_product_samples_in_scope": products[key],
                        "official_box_samples_in_scope": boxes[key],
                        "review_priority": ("P0_DECLARED_BOX_GAP" if declared and not boxes[key] else
                                            "P1_DECLARED_SAMPLE" if declared else "P2_UNDECLARED_EXPLORATORY"),
                        "manufacturer_source_seed": site_source,
                        "manufacturer_seed_level": origin,
                        "search_links": {
                            "manufacturer_google": search_url("google", doc_q),
                            "manufacturer_bing": search_url("bing", doc_q),
                            "market_broad_google": search_url("google", base),
                            "market_typed_bing": search_url("bing", typed),
                            "market_x_latest": search_url("x", typed + " " +
                                ("買取" if market == "JP" else "매입" if market == "KR" else "buylist")),
                            "instagram_public_google": search_url("google", "site:instagram.com " + typed),
                            "youtube_research": search_url("youtube", typed),
                            "identifier_google": search_url("google", base + " " + phrase(
                                "JAN UPC barcode" if item_kind in ("BOX_SET", "UPCOMING_SET") else "card number set code")),
                        },
                        "price_kind": "NONE",
                        "review_status": "PENDING_HUMAN_SOURCE_VERIFICATION",
                        "manufacturer_approved": False,
                    })
                    if len(queue) > MAX_TASKS:
                        raise ValueError("QUEUE_TOO_LARGE")
    priority = {"P0_DECLARED_BOX_GAP": 0, "P1_DECLARED_SAMPLE": 1, "P2_UNDECLARED_EXPLORATORY": 2}
    queue.sort(key=lambda t: (priority[t["review_priority"]], t["game_id"], t["market"], t["kind"], t["task_id"]))
    if limit is not None:
        queue = queue[:limit]
    summary = {
        "games_in_registry": 30, "market_scopes": 90, "original_candidate_records": 338,
        "jobs_returned": len(queue), "review_priority_counts": dict(Counter(t["review_priority"] for t in queue)),
        "kind_counts": dict(Counter(t["kind"] for t in queue)),
        "network_calls": 0, "free_paid_dependencies": 0, "verified_box_by_search": 0,
        "research_links_per_job": 8,
        "note": "Manual leads only; a search result must never be promoted to manufacturer proof automatically.",
    }
    return {"schema_version": 1, "policy": "LOCAL_MANUAL_SOURCE_REVIEW_ONLY", "summary": summary, "jobs": queue}


def encode_csv(jobs):
    out = io.StringIO()
    cols = ("task_id", "game_id", "market", "kind", "candidate", "review_priority",
            "region_declared", "review_status", "manufacturer_source_seed",
            "manufacturer_google", "manufacturer_bing", "market_broad_google",
            "market_typed_bing", "market_x_latest",
            "instagram_public_google", "youtube_research", "identifier_google")
    writer = csv.DictWriter(out, fieldnames=cols)
    writer.writeheader()
    for row in jobs:
        # Spreadsheet formula injection prevention: candidates are never treated as formulas.
        field = {}
        for k in cols:
            v = row.get(k, row.get("search_links", {}).get(k, ""))
            if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@")):
                v = "'" + v
            field[k] = v
        writer.writerow(field)
    return out.getvalue()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Free, fully offline 30-TCG research queue")
    parser.add_argument("--game", default="ALL")
    parser.add_argument("--region", choices=("ALL", *LOCALES), default="ALL")
    parser.add_argument("--kind", choices=("ALL", *(x[1] for x in FIELD_KIND)), default="ALL")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--format", choices=("summary", "json", "jsonl", "csv"), default="summary")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = build_queue(game=args.game, region=args.region, kind=args.kind, limit=args.limit)
        if args.format == "summary":
            contents = json.dumps(result["summary"], ensure_ascii=False, indent=2) + "\n"
        elif args.format == "json":
            contents = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        elif args.format == "jsonl":
            contents = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in result["jobs"])
        else:
            contents = encode_csv(result["jobs"])
        if args.output:
            output = args.output.resolve()
            # Refuse to overwrite source, scripts, or uncontrolled repository files.
            if output.suffix.lower() not in (".csv", ".json", ".jsonl", ".txt") or output.parent == ROOT.resolve() or output.is_symlink():
                raise ValueError("UNSAFE_OUTPUT_FILE")
            if output.exists():
                raise ValueError("OUTPUT_EXISTS")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(contents, encoding="utf-8")
            print(json.dumps({"saved": str(output), "jobs": len(result["jobs"])}))
        else:
            print(contents, end="")
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
