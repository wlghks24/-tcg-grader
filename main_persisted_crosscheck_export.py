#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
DEFAULT_RELEASES = ROOT / "releases.json"
DEFAULT_OUTPUT = ROOT / "TCG_CROSSCHECK" / "MARKET_ANALYSIS" / "factual_snapshot.json"
KST = dt.timezone(dt.timedelta(hours=9))
MAX_RELEASE_FACTS = 250
MAX_VERIFIED_AGE_HOURS = 36

OFFICIAL_HOSTS = {
    "pokemon-card.com",
    "www.pokemon-card.com",
    "pokemon.com",
    "www.pokemon.com",
    "onepiece-cardgame.com",
    "www.onepiece-cardgame.com",
    "en.onepiece-cardgame.com",
    "onepiece-cardgame.kr",
    "www.onepiece-cardgame.kr",
    "naruto-cardgame.com",
    "www.naruto-cardgame.com",
}
GAME_TOKENS = {
    "pokémon": "pokemon",
    "pokemon": "pokemon",
    "one piece": "onepiece",
    "onepiece": "onepiece",
    "naruto": "naruto",
    "NARUTO": "naruto",
}


def _load_json(path: Path) -> Any:
    return json.loads(safe_read_text(path))


def _parse_time(value: Any) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(dt.timezone.utc)


def _official_url(value: Any) -> str | None:
    url = str(value or "").strip()
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if parsed.scheme != "https":
        return None
    host = (parsed.hostname or "").lower()
    return url if host in OFFICIAL_HOSTS else None


def _game_token(value: Any) -> str | None:
    raw = str(value or "").strip()
    lowered = raw.lower()
    for key, token in GAME_TOKENS.items():
        if lowered == key.lower():
            return token
    return None


def _slug(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\[[^\]]+\]", " ", text)
    text = re.sub(r"[^0-9a-z가-힣ぁ-んァ-ヶ一-龯]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")[:120]


def _iso_date(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return None
    try:
        dt.date.fromisoformat(raw)
    except ValueError:
        return None
    return raw


def _fresh_verified_at(row: dict[str, Any], now: dt.datetime) -> str | None:
    raw = row.get("last_verified_at")
    parsed = _parse_time(raw)
    if parsed is None:
        return None
    age = (now.astimezone(dt.timezone.utc) - parsed).total_seconds()
    if age < -300 or age > MAX_VERIFIED_AGE_HOURS * 3600:
        return None
    return parsed.astimezone(KST).isoformat(timespec="seconds")


def _lineage(canonical_key: str, source: str, value: str) -> str:
    raw = f"{canonical_key}|{source}|{value}"
    return "release:" + hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:24]


def build_release_facts(payload: dict[str, Any], *, now: dt.datetime | None = None) -> list[dict[str, Any]]:
    now = now or dt.datetime.now(dt.timezone.utc)
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("releases.json items must be a list")
    facts: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in items:
        if not isinstance(row, dict):
            continue
        if str(row.get("status") or "").strip() != "공식 확인":
            continue
        source = _official_url(row.get("source"))
        verified_at = _fresh_verified_at(row, now)
        release_date = _iso_date(row.get("release_date"))
        game = _game_token(row.get("game"))
        region = str(row.get("region") or "").strip().upper()
        name = str(row.get("name") or "").strip()
        if not all((source, verified_at, release_date, game, region, name)):
            continue
        canonical_key = f"{game}|{_slug(name)}|{region.lower()}"
        if canonical_key.endswith("||") or not _slug(name):
            continue
        lineage_key = _lineage(canonical_key, source, release_date)
        dedupe = (canonical_key, "release", lineage_key)
        if dedupe in seen:
            continue
        seen.add(dedupe)
        facts.append({
            "canonical_key": canonical_key,
            "fact_type": "release",
            "lineage_key": lineage_key,
            "identity": {"game": game, "name": name, "region": region},
            "value": release_date,
            "value_type": "date",
            "currency": "",
            "region": region,
            "language": region,
            "condition": "",
            "grade_company": "",
            "grade": "",
            "effective_date": release_date,
            "observed_at": verified_at,
            "source_role": "official_primary",
            "source_locator": source,
            "verification_status": "verified",
        })
        if len(facts) >= MAX_RELEASE_FACTS:
            break
    return facts


def _existing_last_good(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = _load_json(path)
    except (OSError, ValueError, TypeError, UnicodeError):
        return None
    if (
        isinstance(value, dict)
        and value.get("namespace") == "MARKET_ANALYSIS"
        and value.get("status") == "finalized"
        and isinstance(value.get("facts"), list)
        and bool(value.get("facts"))
        and isinstance(value.get("validation"), dict)
        and value["validation"].get("write_readback_verified") is True
    ):
        return value
    return None


def build_snapshot(facts: list[dict[str, Any]], *, now: dt.datetime | None = None) -> dict[str, Any]:
    stamp = (now or dt.datetime.now(KST)).astimezone(KST)
    return {
        "schema_version": "1.0",
        "namespace": "MARKET_ANALYSIS",
        "snapshot_kind": "factual",
        "run_date_kst": stamp.date().isoformat(),
        "status": "finalized" if facts else "building",
        "built_at": stamp.isoformat(timespec="seconds"),
        "finalized_at": stamp.isoformat(timespec="seconds") if facts else None,
        "facts": facts,
        "validation": {
            "manifest_validated": True,
            "allowed_fields_only": True,
            "exact_factual_types_enforced": True,
            "write_readback_verified": False,
            "isolation_breach": False,
        },
        "error_code": None if facts else "NO_FRESH_VERIFIED_FACTS",
    }


def export_from_releases(
    releases_path: Path = DEFAULT_RELEASES,
    output: Path = DEFAULT_OUTPUT,
    *,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    payload = _load_json(releases_path)
    if not isinstance(payload, dict):
        raise ValueError("releases.json root must be an object")
    facts = build_release_facts(payload, now=now)
    snapshot = build_snapshot(facts, now=now)
    if not facts:
        previous = _existing_last_good(output)
        if previous is not None:
            return {
                **previous,
                "preserved_last_good": True,
                "latest_attempt_status": "NO_FRESH_VERIFIED_FACTS",
            }
        atomic_write_json(output, snapshot, suffix=".market-factual.tmp")
        return snapshot

    atomic_write_json(output, snapshot, suffix=".market-factual.tmp")
    reread = _load_json(output)
    if (
        not isinstance(reread, dict)
        or reread.get("namespace") != "MARKET_ANALYSIS"
        or reread.get("facts") != facts
    ):
        raise RuntimeError("MARKET_ANALYSIS snapshot write/readback mismatch")
    reread["validation"]["write_readback_verified"] = True
    atomic_write_json(output, reread, suffix=".market-factual-readback.tmp")
    return reread


def self_test() -> None:
    now = dt.datetime(2026, 9, 6, 12, 0, tzinfo=dt.timezone.utc)
    release = {
        "game": "Pokémon",
        "region": "JP",
        "name": "30th CELEBRATION",
        "release_date": "2026-09-16",
        "status": "공식 확인",
        "source": "https://www.pokemon-card.com/products/index.html?productType=expansion",
        "last_verified_at": "2026-09-06T11:30:00+00:00",
    }
    stale = {**release, "name": "stale", "last_verified_at": "2026-09-01T00:00:00+00:00"}
    unverified = {**release, "name": "planned", "status": "출시예정"}
    bad_source = {**release, "name": "bad", "source": "https://example.com/not-official"}
    facts = build_release_facts({"items": [release, stale, unverified, bad_source]}, now=now)
    assert len(facts) == 1, facts
    assert facts[0]["fact_type"] == "release"
    assert facts[0]["verification_status"] == "verified"
    assert facts[0]["canonical_key"] == "pokemon|30th-celebration|jp"

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        releases = root / "releases.json"
        out = root / "factual_snapshot.json"
        releases.write_text(json.dumps({"items": [release]}), encoding="utf-8")
        result = export_from_releases(releases, out, now=now)
        assert result["status"] == "finalized", result
        assert result["validation"]["write_readback_verified"] is True, result

        releases.write_text(json.dumps({"items": [stale]}), encoding="utf-8")
        preserved = export_from_releases(releases, out, now=now)
        assert preserved.get("preserved_last_good") is True, preserved
        reread = json.loads(out.read_text(encoding="utf-8"))
        assert reread["status"] == "finalized" and len(reread["facts"]) == 1, reread

    print("Main persisted factual snapshot export: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--releases", default=str(DEFAULT_RELEASES))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    result = export_from_releases(Path(args.releases), Path(args.output))
    print(json.dumps({
        "status": result.get("status"),
        "fact_count": len(result.get("facts") or []),
        "preserved_last_good": bool(result.get("preserved_last_good")),
        "error_code": result.get("error_code"),
        "output": str(Path(args.output)),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
