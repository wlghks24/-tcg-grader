#!/usr/bin/env python3
"""V627: No-network quality and collection gap triage for official TCG products.

Source links alone are not proof that a spec matches the source; this reports
provenance limitations rather than inventing sales, pull rates or accuracy.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit
import argparse
import json

from execution.official_box_coverage_audit_v623 import _load_json, audit, CoverageError

ROOT = Path(__file__).resolve().parent


def _specificity(url: str) -> str:
    parsed = urlsplit(url)
    path = parsed.path.rstrip("/").lower()
    if path in ("", "/products", "/en/products", "/en-us/products") or path.endswith("/products.do"):
        return "CATEGORY_INDEX_ONLY"
    return "PRODUCT_OR_EDITORIAL_PAGE_UNVERIFIED_CONTENT_MATCH"


def build_report(registry, catalog, *, as_of: date | None = None):
    if not isinstance(registry, dict) or not isinstance(catalog, dict):
        raise CoverageError("INVALID_DATA")
    base = audit(registry, catalog, as_of=as_of)
    products = catalog["products"]
    needs = []
    count = Counter()
    for item in products:
        source_kind = _specificity(item["source"])
        if source_kind == "CATEGORY_INDEX_ONLY":
            count["category_index_only"] += 1
        else:
            count["product_or_article_link"] += 1
        missing = []
        if not item.get("release_date"):
            missing.append("PRODUCT_RELEASE_DATE_NOT_CONFIRMED")
        if item["product_type"] == "BOOSTER_PACK":
            # A pack is not a display and must not fabricate BOX quantities.
            missing.append("DISPLAY_BOX_CONFIGURATION_NOT_REVIEWED")
        if not item.get("cards_per_pack"):
            missing.append("CARDS_PER_PACK_NOT_REVIEWED")
        if not item.get("msrp"):
            missing.append("PRODUCT_MSRP_NOT_REVIEWED")
        if item.get("set_code_verified") is False:
            missing.append("MANUFACTURER_SET_CODE_NOT_CONFIRMED")
        if not item.get("source_checked_at"):
            missing.append("SOURCE_RECHECK_TIMESTAMP_NOT_RECORDED")
        if source_kind == "CATEGORY_INDEX_ONLY":
            missing.append("DIRECT_PRODUCT_EVIDENCE_LINK_NOT_RECORDED")
        for key in missing:
            count[key] += 1
        needs.append({
            "id": item["id"],
            "game": item["game"],
            "country": item["country"],
            "product_type": item["product_type"],
            "source_specificity": source_kind,
            "missing_evidence": missing,
            # A simple prioritization count, NOT a 0-100 product-quality score.
            "missing_count": len(missing),
        })
    needs.sort(key=lambda row: (-row["missing_count"], row["game"], row["country"], row["id"]))
    return {
        "schema_version": 1,
        "status": "PARTIAL_REVIEW_REQUIRED",
        "report_date": (as_of or date.today()).isoformat(),
        "product_sample_count": len(products),
        "registered_games": base["registry_games"],
        "declared_game_country_pairs": base["declared_game_country_pairs"],
        "pairs_with_product_sample": base["pairs_with_any_official_product"],
        "zero_product_record_pairs": base["game_country_product_coverage_gaps"],
        "missing_evidence_counts": dict(sorted(count.items())),
        "review_queue": needs,
        "no_official_full_cardlist_certification": True,
        "no_verified_hit_pull_rate": True,
        "no_verified_completed_market_sales": True,
        "no_verified_live_inventory": True,
        "no_independent_source_content_match_audit": True,
        "no_claim_of_complete_game_catalog": True,
        "observations": [
            "CATEGORY_INDEX_ONLY shows lack of an item-specific URL, not a claim that an entry is false.",
            "PRODUCT_OR_EDITORIAL_PAGE_UNVERIFIED_CONTENT_MATCH is a URL-shape heuristic, not independent fact checking.",
            "SOURCE_RECHECK_TIMESTAMP_NOT_RECORDED is not the same as a stale product.",
            "A product missing from this local snapshot may exist and be on sale.",
            "Official publisher pack counts are not a verified marketplace price or guaranteed rare-card hit.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="Free, offline official TCG BOX/source quality gaps")
    parser.add_argument("--registry", type=Path, default=ROOT / "tcg_game_registry.json")
    parser.add_argument("--catalog", type=Path, default=ROOT / "tcg_official_product_catalog_v599.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = build_report(_load_json(args.registry), _load_json(args.catalog))
        body = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.write_text(body, encoding="utf-8")
        else:
            print(body, end="")
        return 0
    except (CoverageError, OSError, ValueError) as exc:
        print(json.dumps({"status": "HOLD", "reason": str(exc) if isinstance(exc, CoverageError) else "INVALID_INPUT"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
