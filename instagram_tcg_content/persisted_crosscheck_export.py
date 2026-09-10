#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from shared_self_learning.contracts import CANONICAL_FACTUAL_TYPES
from instagram_tcg_content.canonical_taxonomy import (
    lifecycle_anchor,
    lifecycle_bucket,
    normalize_content_type,
    snapshot_fact_type,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "TCG_CROSSCHECK" / "IG_CARDINFO" / "factual_snapshot.json"
KST = timezone(timedelta(hours=9))

DIRECT_FACT_TYPES = {"card_price", "completed_sale", "market_reference"}
CONTENT_FAMILY_TYPES = {
    "release", "official_release", "rerelease", "reprint", "official_reprint",
    "promo", "official_promo", "event", "official_event", "movie_bonus",
    "movie", "official_movie_bonus", "festival", "official_festival",
    "card_news", "official_card_news", "product_news", "official_product_news",
}
ALLOWED_FACTUAL_TYPES = set(CANONICAL_FACTUAL_TYPES)
VERIFICATION_MODE = "INSTAGRAM_LOCAL_EVIDENCE_ONLY"
VERIFICATION_ENGINE = "instagram_tcg_content.source_verification_engine.py::verify_fact"
ALLOWED_OUTPUT_FIELDS = {
    "canonical_key", "fact_type", "content_type", "lineage_key", "identity",
    "value", "value_type", "currency", "region", "language", "condition",
    "grade_company", "grade", "effective_date", "start_date", "end_date",
    "lifecycle_bucket", "observed_at", "source_role", "source_locator",
    "verification_status", "verification_mode", "verification_engine",
}


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            temp = Path(handle.name)
        os.replace(temp, path)
        try:
            dir_fd = os.open(path.parent, os.O_RDONLY)
        except OSError:
            dir_fd = None
        if dir_fd is not None:
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
    finally:
        if temp is not None and temp.exists():
            temp.unlink(missing_ok=True)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _load_records(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    records = value.get("records", value) if isinstance(value, dict) else value
    if not isinstance(records, list) or not all(isinstance(row, dict) for row in records):
        raise ValueError("input must be a JSON list or object with records list")
    return records


def _resolve_type(row: dict[str, Any]) -> tuple[str, str | None]:
    raw_type = _clean(row.get("information_family") or row.get("fact_type")).lower()
    explicit_content = _clean(row.get("content_type")).lower()
    if raw_type in DIRECT_FACT_TYPES:
        if explicit_content:
            raise ValueError("market/price fact cannot carry content_type")
        return raw_type, None
    candidate = explicit_content or raw_type
    if candidate not in CONTENT_FAMILY_TYPES and raw_type not in CONTENT_FAMILY_TYPES:
        raise ValueError(f"unsupported factual type: {raw_type!r}")
    content_type = normalize_content_type(candidate)
    fact_type = snapshot_fact_type(content_type)
    if fact_type not in ALLOWED_FACTUAL_TYPES:
        raise ValueError(f"unsupported canonical factual type: {fact_type!r}")
    return fact_type, content_type


def _normalize_fact(row: dict[str, Any], *, as_of: datetime) -> dict[str, Any] | None:
    verification = _clean(row.get("verification") or row.get("verification_status")).lower()
    if verification != "verified":
        return None
    verification_mode = _clean(row.get("verification_mode"))
    verification_engine = _clean(row.get("verification_engine"))
    if verification_mode != VERIFICATION_MODE:
        raise ValueError("verified factual row did not use Instagram-local verification mode")
    if verification_engine != VERIFICATION_ENGINE:
        raise ValueError("verified factual row did not use source_verification_engine.verify_fact")

    fact_type, content_type = _resolve_type(row)
    canonical_key = _clean(row.get("canonical_key"))
    lineage_key = _clean(row.get("lineage_key"))
    source_locator = _clean(row.get("source_locator"))
    source_role = _clean(row.get("source_role") or row.get("source_code"))
    observed_at = _clean(row.get("checked_at_kst") or row.get("observed_at"))
    try:
        parsed_observed_at = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("verified factual row has invalid observed_at") from exc
    if parsed_observed_at.tzinfo is None:
        raise ValueError("verified factual row observed_at must include timezone")
    if not all((canonical_key, lineage_key, source_locator, source_role, observed_at)):
        raise ValueError("verified factual row is missing canonical/provenance fields")

    start_date = _clean(row.get("start_date") or row.get("event_start_date"))
    effective_date = _clean(
        row.get("effective_date") or row.get("release_date") or
        row.get("announcement_date") or row.get("published_at")
    )
    explicit_end = _clean(row.get("end_date") or row.get("event_end_date"))
    anchor = None
    bucket = None
    if content_type is not None:
        anchor = lifecycle_anchor(row, content_type)
        bucket = lifecycle_bucket(end_date=anchor, as_of=as_of.astimezone(KST).date())

    fact = {
        "canonical_key": canonical_key,
        "fact_type": fact_type,
        "content_type": content_type,
        "lineage_key": lineage_key,
        "identity": row.get("identity") or canonical_key,
        "value": row.get("value"),
        "value_type": _clean(row.get("value_type") or "text"),
        "currency": _clean(row.get("currency")),
        "region": _clean(row.get("region")),
        "language": _clean(row.get("language")),
        "condition": _clean(row.get("condition")),
        "grade_company": _clean(row.get("grade_company")),
        "grade": _clean(row.get("grade")),
        "effective_date": effective_date,
        "start_date": start_date,
        "end_date": explicit_end or (anchor or ""),
        "lifecycle_bucket": bucket,
        "observed_at": observed_at,
        "source_role": source_role,
        "source_locator": source_locator,
        "verification_status": "verified",
        "verification_mode": verification_mode,
        "verification_engine": verification_engine,
    }
    return {key: value for key, value in fact.items() if key in ALLOWED_OUTPUT_FIELDS and value not in (None, "")}


def build_snapshot(records: list[dict[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    stamp = now or datetime.now(KST)
    if stamp.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    facts: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in records:
        fact = _normalize_fact(row, as_of=stamp)
        if fact is None:
            continue
        key = (fact["canonical_key"], fact["fact_type"], fact["lineage_key"])
        if key in seen:
            continue
        seen.add(key)
        facts.append(fact)

    finalized = bool(facts)
    current_count = sum(1 for f in facts if f.get("lifecycle_bucket") != "ARCHIVE")
    archive_count = sum(1 for f in facts if f.get("lifecycle_bucket") == "ARCHIVE")
    return {
        "schema_version": "1.1-lifecycle",
        "namespace": "IG_CARDINFO",
        "snapshot_kind": "factual",
        "run_date_kst": stamp.astimezone(KST).date().isoformat(),
        "status": "finalized" if finalized else "building",
        "built_at": stamp.astimezone(KST).isoformat(timespec="seconds"),
        "finalized_at": stamp.astimezone(KST).isoformat(timespec="seconds") if finalized else None,
        "facts": facts,
        "lifecycle_summary": {"current": current_count, "archive": archive_count},
        "validation": {
            "manifest_validated": True,
            "allowed_fields_only": True,
            "exact_factual_types_enforced": True,
            "lifecycle_routing_enforced": True,
            "write_readback_verified": False,
            "isolation_breach": False,
        },
        "error_code": None if finalized else "NO_VERIFIED_FACTS",
        "latest_attempt": {
            "status": "verified_facts_written" if finalized else "NO_VERIFIED_FACTS",
            "attempted_at": stamp.astimezone(KST).isoformat(timespec="seconds"),
            "verified_fact_count": len(facts),
        },
    }


def _existing_last_good(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, UnicodeError):
        return None
    if (
        isinstance(value, dict)
        and value.get("namespace") == "IG_CARDINFO"
        and value.get("status") == "finalized"
        and isinstance(value.get("facts"), list)
        and bool(value.get("facts"))
        and isinstance(value.get("validation"), dict)
        and value["validation"].get("write_readback_verified") is True
    ):
        return value
    return None


def export_snapshot(records: list[dict[str, Any]], output: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    payload = build_snapshot(records)
    if payload.get("status") != "finalized":
        previous = _existing_last_good(output)
        if previous is not None:
            preserved = {
                **previous,
                "preserved_last_good": True,
                "latest_attempt": {
                    "status": payload.get("error_code") or "NO_VERIFIED_FACTS",
                    "attempted_at": payload.get("built_at"),
                    "verified_fact_count": 0,
                },
            }
            _write_json_atomic(output, preserved)
            reread = json.loads(output.read_text(encoding="utf-8"))
            if reread.get("facts") != previous.get("facts") or reread.get("latest_attempt") != preserved.get("latest_attempt"):
                raise RuntimeError("IG_CARDINFO preserved snapshot write/readback mismatch")
            return reread
    _write_json_atomic(output, payload)
    reread = json.loads(output.read_text(encoding="utf-8"))
    if reread.get("namespace") != "IG_CARDINFO" or reread.get("facts") != payload.get("facts"):
        raise RuntimeError("IG_CARDINFO snapshot write/readback mismatch")
    reread["validation"]["write_readback_verified"] = True
    _write_json_atomic(output, reread)
    final = json.loads(output.read_text(encoding="utf-8"))
    if final.get("validation", {}).get("write_readback_verified") is not True:
        raise RuntimeError("IG_CARDINFO snapshot second readback mismatch")
    return final


def self_test() -> None:
    base = {
        "canonical_key": "pokemon|festival|kr",
        "value": "festival",
        "language": "KR",
        "source_code": "pokemon-official",
        "source_locator": "https://example.invalid/pokemon",
        "checked_at_kst": "2026-09-10T06:00:00+09:00",
        "verification": "verified",
        "verification_mode": VERIFICATION_MODE,
        "verification_engine": VERIFICATION_ENGINE,
        "lineage_key": "ig-festival-1",
        "identity": {"game": "pokemon", "language": "KR"},
    }
    current = build_snapshot([
        {**base, "information_family": "official_festival", "end_date": "2026-09-05"}
    ], now=datetime(2026, 9, 10, 12, 0, tzinfo=KST))
    assert current["facts"][0]["fact_type"] == "event", current
    assert current["facts"][0]["content_type"] == "festival", current
    assert current["facts"][0]["lifecycle_bucket"] == "CURRENT", current

    archived = build_snapshot([
        {**base, "information_family": "official_festival", "end_date": "2026-09-05"}
    ], now=datetime(2026, 9, 11, 12, 0, tzinfo=KST))
    assert archived["facts"][0]["lifecycle_bucket"] == "ARCHIVE", archived

    release = build_snapshot([
        {**base, "canonical_key": "pokemon|release|kr", "information_family": "official_release", "release_date": "2026-09-05", "lineage_key": "release-1"}
    ], now=datetime(2026, 9, 11, 12, 0, tzinfo=KST))
    assert release["facts"][0]["lifecycle_bucket"] == "ARCHIVE", release

    try:
        build_snapshot([{**base, "information_family": "unknown"}], now=datetime(2026, 9, 10, 12, 0, tzinfo=KST))
    except ValueError:
        pass
    else:
        raise AssertionError("unknown factual type must fail closed")
    print("Instagram persisted factual snapshot export lifecycle: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.input:
        raise SystemExit("--input is required unless --self-test is used")
    payload = export_snapshot(_load_records(Path(args.input)), Path(args.output))
    print(json.dumps({
        "status": payload["status"],
        "fact_count": len(payload["facts"]),
        "lifecycle_summary": payload.get("lifecycle_summary", {}),
        "error_code": payload["error_code"],
        "output": str(Path(args.output)),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
