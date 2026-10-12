#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V657 free, offline, additive manufacturer BOX audit.

This overlay is deliberately review-only: no paid dependency, HTTP request,
SNS scraping, market-price synthesis, main catalog overwrite, or live app promotion.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

from execution.official_box_coverage_audit_v623 import (
    ROOT, CoverageError, _load_json, _trusted_url, audit
)

OLD_CATALOGS = (
    "tcg_official_product_catalog_v599.json",
    "tcg_official_product_supplement_v630.json",
    "tcg_official_product_supplement_v636.json",
    "tcg_official_product_supplement_v637.json",
    "tcg_official_product_supplement_v649.json",
    "tcg_official_product_supplement_v654.json",
)
OVERLAY_NAME = "tcg_official_product_supplement_v657.json"
FORBIDDEN = ("market_price", "verified_sales", "verified_stock", "psa_grade", "pull_rate")


def validate_overlay(doc, registry):
    if not isinstance(doc, dict):
        raise CoverageError("INVALID_V657_SUPPLEMENT_CHAIN")
    policy = doc.get("policy")
    if not isinstance(policy, dict) or policy.get("no_paid_dependency") is not True:
        raise CoverageError("PAID_DEPENDENCY_NOT_PERMITTED")
    if not isinstance(registry, dict) or not isinstance(registry.get("games"), list):
        raise CoverageError("INVALID_V657_REGISTRY")
    if (not isinstance(doc, dict) or doc.get("schema_version") != 1
            or doc.get("type") != "official_product_specifications_supplement"
            or doc.get("base_catalog") != OLD_CATALOGS[0]
            or doc.get("append_after") != OLD_CATALOGS[-1]
            or not isinstance(doc.get("products"), list)
            or not 1 <= len(doc["products"]) <= 100):
        raise CoverageError("INVALID_V657_SUPPLEMENT_CHAIN")
    expected = {
        "lorcana-US-shimmering-skies-2024": ("Disney Lorcana", "US", "2024-08-23", "12", "LOCAL-LOR-SHIMMERING-SKIES-US"),
        "digi-US-EX12-digital-world-shambala-2026": ("Digimon Card Game", "US", "2026-07-03", "12", "EX-12"),
        "swu-US-spark-of-rebellion-2024": ("Star Wars: Unlimited", "US", "2024-03-08", "16", "LOCAL-SWU-SPARK-OF-REBELLION-US"),
    }
    games = {g["canonical"]: g for g in registry["games"]}
    seen = set()
    for product in doc["products"]:
        if not isinstance(product, dict) or any(key in product for key in FORBIDDEN):
            raise CoverageError("UNSUPPORTED_V657_PRODUCT_CLAIM")
        proof_id = product.get("id")
        expected_row = expected.get(proof_id)
        if not expected_row or proof_id in seen:
            raise CoverageError("UNTRUSTED_V657_IDENTITY")
        seen.add(proof_id)
        g = games.get(product.get("game"))
        if (product.get("game") != expected_row[0]
                or product.get("country") != expected_row[1]
                or product.get("release_date") != expected_row[2]
                or product.get("cards_per_pack") != expected_row[3]
                or product.get("set_code") != expected_row[4]
                or type(product.get("packs_per_box")) is not int
                or product["packs_per_box"] != 24
                or "msrp" in product):
            raise CoverageError("UNTRUSTED_V657_IDENTITY")
        if (not g or product.get("country") not in ("KR", "JP", "US")
                or (product["country"] not in g["regions"] and "GLOBAL" not in g["regions"])
                or product.get("product_type") != "BOX"
                or not _trusted_url(product.get("source"), product["game"])):
            raise CoverageError("UNTRUSTED_V657_BOX_OR_LOCALE")
        extra_source = product.get("release_date_source")
        if extra_source and not _trusted_url(extra_source, product["game"]):
            raise CoverageError("UNTRUSTED_V657_RELEASE_DATE_SOURCE")
    if len(seen) != len(expected):
        raise CoverageError("MISSING_V657_OFFICIAL_PROOF")
    return doc["products"]


def build(*, directory=ROOT, as_of=None, overlay=None):
    """Audit old six local product files and additive V657 independently."""
    directory = Path(directory)
    reg = _load_json(directory / "tcg_game_registry.json")
    products = []
    for filename in OLD_CATALOGS:
        document = _load_json(directory / filename)
        if not isinstance(document.get("products"), list):
            raise CoverageError("INVALID_CATALOG_PRODUCTS")
        products.extend(document["products"])
    additions = validate_overlay(
        overlay if overlay is not None else _load_json(directory / OVERLAY_NAME), reg
    )
    old = audit(reg, {"schema_version": 1, "products": products}, as_of=as_of)
    new = audit(reg, {"schema_version": 1, "products": products + additions}, as_of=as_of)
    def count(report):
        valid = [c for c in report["cells"] if c["region_declared"]]
        return {
            "product_samples": report["reviewed_official_product_records"],
            "box_samples": sum(c["official_box_count"] for c in report["cells"]),
            "declared_region_pairs": len(valid),
            "regions_with_box_sample": sum(c["official_box_count"] > 0 for c in valid),
            "regions_without_box_sample": sum(c["official_box_count"] == 0 for c in valid),
        }
    before, after = count(old), count(new)
    old_box_scopes = {(c["game_id"], c["country"])
                      for c in old["cells"] if c["region_declared"] and c["official_box_count"]}
    new_box_scopes = {(c["game_id"], c["country"])
                      for c in new["cells"] if c["region_declared"] and c["official_box_count"]}
    if not old_box_scopes <= new_box_scopes:
        raise CoverageError("BOX_EVIDENCE_REGRESSION")
    return {
        "schema_version": 1, "status": "V657_OFFLINE_OVERLAY_VALIDATED_NOT_PROMOTED",
        "network_calls": 0, "paid_dependencies": 0, "source_rows_added": len(additions),
        "existing_catalog_untouched": True, "main_ui_updated": False,
        "before": before, "with_overlay": after,
        "additional_scopes_with_box": len(new_box_scopes - old_box_scopes),
        "sources": [{"game": p["game"], "country": p["country"],
                     "name": p["name"], "manufacturer_page": p["source"]}
                    for p in additions],
        "limitations": [
            "This check validates the persisted source-domain allowlist and sealed product schema, not live page content.",
            "Official source claims were manually reviewed; actual current availability, price, and hit odds remain unknown.",
            "The V657 supplement must be integrated across all consumers and pass latest-head CI before app deployment.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline 30-TCG additive sealed BOX manufacturer proof")
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = build(as_of=date.today())
        if args.summary_only:
            result.pop("sources")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (CoverageError, ValueError, TypeError, OSError, KeyError) as error:
        print(json.dumps({"status": "HOLD", "reason": str(error), "network_calls": 0},
                         ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
