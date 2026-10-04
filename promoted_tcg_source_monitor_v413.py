#!/usr/bin/env python3
"""V413 auxiliary source monitor for promoted non-core TCG categories.

The monitor is evidence-only. It verifies the official and marketplace URLs
already present in the declarative registry, extracts bounded marketplace
catalog depth when the public page exposes it, records collectibility keywords,
and updates only registry evidence. It never predicts price direction, profit,
stock, or grading outcomes and it never writes source code or Git state.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from copy import deepcopy
from pathlib import Path
from typing import Any

import tcg_game_registry
from safe_runtime import (
    atomic_write_json,
    diagnostic_exception,
    env_int,
    safe_urlopen,
    validate_public_https_url,
)

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "promoted_tcg_source_signals_v413.json"
TIMEOUT_SECONDS = env_int("TCG_HTTP_TIMEOUT", 20, 5, 60)
MAX_RESPONSE_BYTES = 2_000_000
MAX_DATE_HINTS = 12
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 "
                  "Chrome/126.0 Safari/537.36 TCG-Grader-Promoted-Monitor/1.0",
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.7",
    "Accept-Language": "en-US,en;q=0.8,ko;q=0.6,ja;q=0.5",
}
RARITY_RE = re.compile(
    r"serial(?:ized| numbered)|numbered card|showcase|alternate art|parallel rare|"
    r"illustr(?:ious|ation rare)|autograph|signature card|collector booster",
    re.I,
)
RESULT_COUNT_RE = re.compile(
    r"(?<!\d)([1-9]\d{0,2}(?:,\d{3})+|[1-9]\d{2,6})\s+results(?:\s+in\b|\b)",
    re.I,
)
DATE_HINT_RE = re.compile(
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},\s+20\d{2}|20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}",
    re.I,
)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _host_allowlist(url: str) -> set[str]:
    validate_public_https_url(url)
    host = (urllib.parse.urlsplit(url).hostname or "").rstrip(".").lower()
    values = {host}
    if host.startswith("www."):
        values.add(host[4:])
    else:
        values.add("www." + host)
    return {value for value in values if value}


def _fetch(url: str) -> str:
    allowed = _host_allowlist(url)
    request = urllib.request.Request(url, headers=HEADERS)
    with safe_urlopen(request, timeout=TIMEOUT_SECONDS, allowed_hosts=allowed) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("source response exceeds bounded size")
    text = raw.decode("utf-8", "replace")
    if len(text.strip()) < 120:
        raise ValueError("source response too small")
    return text


def _catalog_count(text: str) -> int | None:
    values = []
    for raw in RESULT_COUNT_RE.findall(str(text or "")):
        try:
            value = int(raw.replace(",", ""))
        except (TypeError, ValueError, OverflowError):
            continue
        if 1 <= value <= 1_000_000:
            values.append(value)
    return max(values) if values else None


def _date_hints(text: str) -> list[str]:
    found = []
    for value in DATE_HINT_RE.findall(str(text or "")):
        clean = re.sub(r"\s+", " ", value).strip()
        if clean not in found:
            found.append(clean)
        if len(found) >= MAX_DATE_HINTS:
            break
    return found


def _source_status(url: str, *, market: bool = False) -> dict[str, Any]:
    checked_at = _now().isoformat(timespec="seconds")
    try:
        text = _fetch(url)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError, UnicodeError) as exc:
        return {
            "ok": False,
            "checked_at": checked_at,
            "url": url,
            "error": diagnostic_exception(exc, 500),
            "catalog_count": None,
            "collector_rarity_signal": False,
            "date_hints": [],
        }
    return {
        "ok": True,
        "checked_at": checked_at,
        "url": url,
        "catalog_count": _catalog_count(text) if market else None,
        "collector_rarity_signal": bool(RARITY_RE.search(text)),
        "date_hints": _date_hints(text),
    }


def _promoted_non_core(root: Path) -> list[dict[str, Any]]:
    registry = tcg_game_registry.load_registry(root)
    return [
        deepcopy(row)
        for row in registry["games"]
        if row["id"] not in tcg_game_registry.CORE_IDS
        and row["state"] == "promoted"
        and (
            row["capabilities"].get("market") is True
            or row["capabilities"].get("release") is True
        )
    ]


def collect(root: Path = ROOT) -> dict[str, Any]:
    checked_at = _now().isoformat(timespec="seconds")
    rows = []
    for game in _promoted_non_core(root)[: tcg_game_registry.MAX_GAMES]:
        official = _source_status(game["official_source"], market=False)
        market = _source_status(game["market_source"], market=True)
        rows.append({
            "id": game["id"],
            "canonical": game["canonical"],
            "label_ko": game["label_ko"],
            "regions": list(game["regions"]),
            "official": official,
            "market": market,
            "official_live": official["ok"] is True,
            "market_live": market["ok"] is True,
            "marketplace_catalog_count": market.get("catalog_count"),
            "collector_rarity_signal": bool(
                official.get("collector_rarity_signal") or market.get("collector_rarity_signal")
            ),
            "date_hints": list(dict.fromkeys(
                list(official.get("date_hints") or []) + list(market.get("date_hints") or [])
            ))[:MAX_DATE_HINTS],
        })
    return {
        "schema_version": 1,
        "controller_version": "v413",
        "updated_at": checked_at,
        "items": rows,
        "policy": {
            "promoted_non_core_only": True,
            "registry_urls_only": True,
            "public_https_only": True,
            "bounded_response_bytes": MAX_RESPONSE_BYTES,
            "marketplace_depth_advisory_evidence_only": True,
            "price_direction_inferred": False,
            "profit_guaranteed": False,
            "stock_claimed": False,
            "grading_enabled": False,
            "source_code_modified": False,
            "git_write": False,
            "user_behavior_tracking": False,
        },
    }


def apply_verified_evidence(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    registry = tcg_game_registry.load_registry(root)
    by_id = {
        str(row.get("id")): row
        for row in payload.get("items", [])
        if isinstance(row, dict) and row.get("id")
    }
    rows = deepcopy(registry["games"])
    changed = False
    updated = []
    for row in rows:
        signal = by_id.get(row["id"])
        if not signal or row["id"] in tcg_game_registry.CORE_IDS:
            continue
        evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
        evidence = dict(evidence)
        official = signal.get("official") if isinstance(signal.get("official"), dict) else {}
        market = signal.get("market") if isinstance(signal.get("market"), dict) else {}
        if official.get("ok") is True:
            evidence["official_live"] = True
            evidence["last_verified_at"] = str(official.get("checked_at") or payload.get("updated_at"))
            updated.append(f"{row['id']}:official")
        count = signal.get("marketplace_catalog_count")
        if isinstance(count, int) and not isinstance(count, bool) and 1 <= count <= 1_000_000:
            evidence["marketplace_catalog_count"] = count
            evidence["marketplace_catalog_checked_at"] = str(
                market.get("checked_at") or payload.get("updated_at")
            )
            updated.append(f"{row['id']}:catalog")
        if signal.get("collector_rarity_signal") is True:
            evidence["collector_rarity_signal"] = True
            updated.append(f"{row['id']}:rarity")
        evidence["source_monitor_v413"] = {
            "official_ok": official.get("ok") is True,
            "market_ok": market.get("ok") is True,
            "checked_at": payload.get("updated_at"),
            "date_hint_count": len(signal.get("date_hints") or []),
        }
        if evidence != row.get("evidence"):
            row["evidence"] = evidence
            changed = True
    if changed:
        output = deepcopy(registry)
        output["games"] = rows
        output["updated_at"] = str(payload.get("updated_at") or _now().isoformat(timespec="seconds"))
        if not tcg_game_registry.validate_registry(output):
            raise ValueError("V413_REGISTRY_EVIDENCE_INVALID")
        atomic_write_json(root / tcg_game_registry.REGISTRY_PATH.name, output, suffix=".v413-registry.tmp")
    return {
        "changed": changed,
        "updated_fields": sorted(set(updated)),
        "source_code_modified": False,
        "git_write": False,
    }


def main(root: Path = ROOT) -> dict[str, Any]:
    payload = collect(root)
    apply = apply_verified_evidence(root, payload)
    payload["registry_apply"] = apply
    atomic_write_json(root / OUT.name, payload, suffix=".v413-signals.tmp")
    return payload


if __name__ == "__main__":
    result = main()
    print(json.dumps({
        "updated_at": result.get("updated_at"),
        "items": len(result.get("items") or []),
        "registry_changed": (result.get("registry_apply") or {}).get("changed", False),
    }, ensure_ascii=False))
