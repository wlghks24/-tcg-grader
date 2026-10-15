#!/usr/bin/env python3
"""Offline-first read-only TCG feature & provenance audit (V573).

No marketplace requests, paid APIs, user account writes or source modifications.
A successful audit means input contracts are internally consistent, NOT that
unverified prices are genuine or that physical Lenovo QA was completed.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
KST = timezone(timedelta(hours=9))
COUNTRIES = frozenset({"KR", "JP", "US", "CN-S", "CN-T"})
PRICE_TYPES = frozenset({"completed_sale", "asking", "api_reference"})
BOX_PATTERN = re.compile(r'\{\s*country:"([^"]+)",game:"([^"]+)",name:"([^"]+)"')


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name}: expected JSON object")
    return value


def catalog_rows(html: str) -> list[tuple[str, str, str]]:
    start = html.find("const COUNTRY_BOX_DATA=[")
    if start < 0:
        raise ValueError("static BOX catalog declaration missing")
    end = html.find("\n];", start)
    if end < 0:
        raise ValueError("static BOX catalog terminator missing")
    return BOX_PATTERN.findall(html[start:end])


def valid_observation_day(value: object, today: datetime) -> int | None:
    if not isinstance(value, str) or not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", value):
        return None
    try:
        observed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None
    return (today.date() - observed).days


def is_valid_price_display(row: dict) -> bool:
    display = row.get("display")
    if not isinstance(display, str):
        return False
    return bool(re.fullmatch(
        r"₩\s*\d[\d,]*(?:\s*[~～–]\s*₩?\s*\d[\d,]*)?",
        display.strip(),
    ))


def trusted_https(url: object) -> bool:
    if not isinstance(url, str) or len(url) > 2048:
        return False
    parsed = urlparse(url)
    try:
        return (parsed.scheme == "https" and parsed.hostname is not None
                and parsed.port in (None, 443) and parsed.username is None
                and parsed.password is None)
    except ValueError:
        return False


def audit(root: Path = ROOT, now: datetime | None = None) -> dict:
    now = (now or datetime.now(KST)).astimezone(KST)
    html = (root / "index.html").read_text(encoding="utf-8")
    box_js = (root / "box_knowledge_stats.js").read_text(encoding="utf-8")
    expander = (root / "market_catalog_expander.js").read_text(encoding="utf-8")
    nav = (root / "feature_category_nav.js").read_text(encoding="utf-8")
    price_json = load_json(root / "market_prices.json")
    registry = load_json(root / "tcg_game_registry.json")
    catalog = catalog_rows(html)
    entries = price_json.get("entries")
    if not isinstance(entries, dict):
        raise ValueError("market prices entries must be mapping")
    games = registry.get("games")
    if not isinstance(games, list):
        raise ValueError("game registry games missing")
    official_path = root / "tcg_official_product_catalog_v599.json"
    official = load_json(official_path) if official_path.exists() else {}
    released = official.get("products", [])
    if not isinstance(released, list):
        raise ValueError("official product list malformed")

    p0, p1, p2 = [], [], []
    identifiers = [(country, game, name) for country, game, name in catalog]
    if len(set(identifiers)) != len(identifiers):
        p0.append("duplicate exact game/country/BOX identity in base catalog")
    if any(country not in COUNTRIES for country, _, _ in catalog):
        p0.append("base catalog has unrecognized country")
    if "box_knowledge_stats.js" not in html or "market_catalog_expander.js" not in html:
        p0.append("BOX market JS files not included by index.html")
    if 'window.TCGBoxPriceProofV572' not in box_js:
        p0.append("evidence-gated BOX price evaluator is missing")
    if 'TCGBox' in nav and 'tcg-market-catalog-expanded' not in expander:
        p0.append("market catalog refresh handoff is absent")

    price_boxes = {key: row for key, row in entries.items()
                   if isinstance(key, str) and key.endswith("|BOX")
                   and isinstance(row, dict)}
    mismatched, connected, recent = [], set(), 0
    bad_price, pending_urls, invalid_days = [], [], []
    dates = []
    for key, row in price_boxes.items():
        parts = key.split("|")
        if len(parts) != 3 or parts[0] not in COUNTRIES or not parts[1]:
            p0.append(f"invalid BOX market key: {key[:120]}")
            continue
        comparable = (parts[0], row.get("game"), parts[1])
        if comparable in identifiers:
            connected.add(comparable)
        elif any(x[0] == parts[0] and x[2] == parts[1] for x in identifiers):
            mismatched.append(key)
        a = valid_observation_day(row.get("market_observed_at") or row.get("source_date"), now)
        dates.append(a)
        if a is None or a < 0:
            invalid_days.append(key)
        if a is not None and 0 <= a <= 14 and row.get("link_status") == "정상":
            recent += 1
        if not is_valid_price_display(row):
            bad_price.append(key)
        if row.get("link_status") != "정상" or not trusted_https(row.get("source")):
            pending_urls.append(key)
        evidence = row.get("box_price_evidence")
        if evidence is not None:
            if not isinstance(evidence, list) or len(evidence) > 120:
                p0.append(f"{key}: invalid box_price_evidence container")
                continue
            for i, item in enumerate(evidence):
                if (not isinstance(item, dict) or item.get("product_key") != key
                        or item.get("game") != row.get("game")
                        or item.get("evidence_type") not in PRICE_TYPES
                        or item.get("unit") != "BOX"
                        or item.get("unit_quantity") != 1
                        or item.get("sealed") is not True):
                    p0.append(f"{key}: price evidence #{i} has invalid identity, packaging or kind")
                if isinstance(item, dict) and item.get("evidence_type") == "completed_sale":
                    if item.get("review_status") != "manual_verified":
                        p0.append(f"{key}: unreviewed sold listing must not be promoted to a completed sale")
    if mismatched:
        p0.append(f"{len(mismatched)} market BOX identities collide with another game")
    if invalid_days:
        p1.append(f"{len(invalid_days)} BOX entries have unknown/future/malformed observation dates")
    if pending_urls:
        p1.append(f"{len(pending_urls)} BOX entries lack confirmed HTTPS source status")
    if bad_price:
        p1.append(f"{len(bad_price)} BOX prices are not a simple KRW observed amount or range")

    games_seen = {g.get("canonical") for g in games if isinstance(g, dict)}
    in_base = {game for _, game, _ in catalog}
    if len(games_seen - in_base):
        p1.append(f"{len(games_seen - in_base)} registered games lack a static BOX showcase")
    country_count = Counter(country for country, _, _ in catalog)
    for country in ("CN-S", "CN-T"):
        if country_count[country] == 0:
            p1.append(f"{country} missing from the static BOX showcase")
    if not any(isinstance(row.get("box_price_evidence"), list)
               and row["box_price_evidence"] for row in price_boxes.values()):
        p1.append("no BOX market entry includes independently reviewable sale evidence")
    if len(connected) < len(catalog):
        p1.append(f"{len(catalog) - len(connected)} static BOX products have no exact market price record")

    if not all(marker in html for marker in ("box12section", "boxKbCount", "box-kb-card")):
        p0.append("BOX knowledge base HTML binding is incomplete")
    if "role=\"tablist\"" in box_js and 'aria-selected' not in box_js:
        p2.append("BOX status tabs have no explicit aria-selected state (static inspection)")
    if "CN-S" not in expander or "CN-T" not in expander:
        p2.append("market catalog expander does not explicitly handle CN-S and CN-T")

    totals = {
        "registry_games": len(games_seen),
        "static_box_products": len(catalog),
        "static_box_by_country": dict(sorted(country_count.items())),
        "official_product_rows": len(released),
        "box_market_entries": len(price_boxes),
        "static_box_price_exact_matches": len(connected),
        "market_box_verified_recent_links": recent,
        "market_box_unconfirmed_links": len(pending_urls),
        "market_box_with_sale_evidence": sum(
            1 for row in price_boxes.values()
            if isinstance(row.get("box_price_evidence"), list) and row["box_price_evidence"]
        ),
    }
    return {
        "schema_version": 1,
        "audit_at_kst": now.isoformat(timespec="seconds"),
        "verification_scope": "static files + stored price evidence; NOT live web, UI click or physical tablet",
        "metrics": totals,
        "blocking_errors": p0,
        "coverage_gaps": p1,
        "usability_followups": p2,
        "audit_pass": not p0,
        "data_complete": not p1,
        "device_verified": False,
        "priority": ["P0_BLOCK" if p0 else "P0_CLEAR",
                     "P1_INCOMPLETE" if p1 else "P1_CLEAR",
                     "P2_REVIEW" if p2 else "P2_CLEAR"],
    }


def markdown(result: dict) -> str:
    m = result["metrics"]
    lines = [
        "# TCG V573 repository evidence audit",
        f"Checked (KST): {result['audit_at_kst']}",
        f"Scope: {result['verification_scope']}",
        "",
        f"Catalog: {m['registry_games']} games / {m['static_box_products']} fixed BOX records "
        f"/ {m['box_market_entries']} stored BOX-price records.",
        f"Exact linked prices: {m['static_box_price_exact_matches']}/{m['static_box_products']} "
        f"(only original static catalog; dynamic discovery excluded).",
        f"Stored sale-evidence candidates: {m['market_box_with_sale_evidence']} (not validated sold prices).",
        "",
        "## Verified action queue",
    ]
    for title, key in (("P0 blocking", "blocking_errors"),
                       ("P1 missing evidence", "coverage_gaps"),
                       ("P2 usability", "usability_followups")):
        lines.append(f"### {title}")
        lines.extend("- " + s for s in result[key])
        if not result[key]:
            lines.append("- No finding in this bounded static audit")
    lines.append("")
    lines.append("**HOLD: no physical Lenovo test or verified market-wide sale coverage is implied.**")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = audit(args.root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"TCG_AUDIT_INPUT_ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    text = markdown(result)
    print(text)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                                 encoding="utf-8")
    if args.markdown_out:
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_text(text, encoding="utf-8")
    return 1 if args.strict and result["blocking_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
