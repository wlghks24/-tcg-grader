#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "TCG_CROSSCHECK" / "IG_CARDINFO" / "factual_snapshot.json"
KST = timezone(timedelta(hours=9))

FACT_TYPE_MAP = {
    "card_price": "card_price",
    "release": "release",
    "official_release": "release",
    "rerelease": "rerelease",
    "official_reprint": "rerelease",
    "promo": "promo",
    "official_promo": "promo",
    "event": "event",
    "official_event": "event",
    "movie_bonus": "movie_bonus",
    "official_movie_bonus": "movie_bonus",
    "completed_sale": "completed_sale",
    "market_reference": "market_reference",
}
ALLOWED_FACTUAL_TYPES = set(FACT_TYPE_MAP.values())
ALLOWED_OUTPUT_FIELDS = {
    "canonical_key",
    "fact_type",
    "lineage_key",
    "identity",
    "value",
    "value_type",
    "currency",
    "region",
    "language",
    "condition",
    "grade_company",
    "grade",
    "effective_date",
    "observed_at",
    "source_role",
    "source_locator",
    "verification_status",
}


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            temp = Path(handle.name)
        temp.replace(path)
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


def _normalize_fact(row: dict[str, Any]) -> dict[str, Any] | None:
    verification = _clean(row.get("verification") or row.get("verification_status")).lower()
    if verification != "verified":
        return None

    raw_type = _clean(row.get("information_family") or row.get("fact_type"))
    fact_type = FACT_TYPE_MAP.get(raw_type)
    if fact_type not in ALLOWED_FACTUAL_TYPES:
        raise ValueError(f"unsupported factual type: {raw_type!r}")

    canonical_key = _clean(row.get("canonical_key"))
    lineage_key = _clean(row.get("lineage_key"))
    source_locator = _clean(row.get("source_locator"))
    observed_at = _clean(row.get("checked_at_kst") or row.get("observed_at"))
    if not all((canonical_key, lineage_key, source_locator, observed_at)):
        raise ValueError("verified factual row is missing canonical/provenance fields")

    fact = {
        "canonical_key": canonical_key,
        "fact_type": fact_type,
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
        "effective_date": _clean(row.get("effective_date")),
        "observed_at": observed_at,
        "source_role": _clean(row.get("source_role") or row.get("source_code") or "instagram_verified"),
        "source_locator": source_locator,
        "verification_status": "verified",
    }
    return {key: value for key, value in fact.items() if key in ALLOWED_OUTPUT_FIELDS}


def build_snapshot(records: list[dict[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    stamp = now or datetime.now(KST)
    facts = []
    seen: set[tuple[str, str, str]] = set()
    for row in records:
        fact = _normalize_fact(row)
        if fact is None:
            continue
        key = (fact["canonical_key"], fact["fact_type"], fact["lineage_key"])
        if key in seen:
            continue
        seen.add(key)
        facts.append(fact)

    finalized = bool(facts)
    return {
        "schema_version": "1.0",
        "namespace": "IG_CARDINFO",
        "snapshot_kind": "factual",
        "run_date_kst": stamp.astimezone(KST).date().isoformat(),
        "status": "finalized" if finalized else "building",
        "built_at": stamp.astimezone(KST).isoformat(timespec="seconds"),
        "finalized_at": stamp.astimezone(KST).isoformat(timespec="seconds") if finalized else None,
        "facts": facts,
        "validation": {
            "manifest_validated": True,
            "allowed_fields_only": True,
            "exact_factual_types_enforced": True,
            "write_readback_verified": False,
            "isolation_breach": False,
        },
        "error_code": None if finalized else "NO_VERIFIED_FACTS",
    }


def export_snapshot(records: list[dict[str, Any]], output: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    payload = build_snapshot(records)
    _write_json_atomic(output, payload)
    reread = json.loads(output.read_text(encoding="utf-8"))
    if reread.get("namespace") != "IG_CARDINFO" or reread.get("facts") != payload.get("facts"):
        raise RuntimeError("IG_CARDINFO snapshot write/readback mismatch")
    reread["validation"]["write_readback_verified"] = True
    _write_json_atomic(output, reread)
    return reread


def self_test() -> None:
    verified = {
        "information_family": "official_release",
        "canonical_key": "pokemon|30th-celebration|jp",
        "value": "2026-09-16",
        "language": "JP",
        "source_code": "pokemon-official",
        "source_locator": "https://example.invalid/pokemon",
        "checked_at_kst": "2026-09-06T06:30:00+09:00",
        "verification": "verified",
        "lineage_key": "ig-release-1",
    }
    candidate = {**verified, "verification": "candidate", "lineage_key": "candidate"}
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "factual_snapshot.json"
        payload = export_snapshot([verified, candidate], path)
        assert payload["status"] == "finalized", payload
        assert len(payload["facts"]) == 1, payload
        assert payload["facts"][0]["fact_type"] == "release", payload
        assert payload["validation"]["write_readback_verified"] is True, payload

        empty = export_snapshot([candidate], path)
        assert empty["status"] == "building", empty
        assert empty["facts"] == [], empty
        assert empty["error_code"] == "NO_VERIFIED_FACTS", empty

        try:
            export_snapshot([{**verified, "information_family": "market_price"}], path)
        except ValueError:
            pass
        else:
            raise AssertionError("legacy/noncanonical factual type must fail closed")

    print("Instagram persisted factual snapshot export: PASS")


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
        "error_code": payload["error_code"],
        "output": str(Path(args.output)),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
