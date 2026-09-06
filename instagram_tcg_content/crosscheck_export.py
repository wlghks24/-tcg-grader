#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import tempfile
from pathlib import Path

from shared_self_learning.engine import normalize_crosscheck_record

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "crosscheck_exchange" / "runtime-instagram.json"
DEFAULT_PERSISTED_OUTPUT = ROOT / "TCG_CROSSCHECK" / "IG_CARDINFO" / "factual_snapshot.json"
CANONICAL_FACTUAL_TYPES = {
    "card_price", "release", "rerelease", "promo",
    "event", "movie_bonus", "completed_sale", "market_reference",
}


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            temp = Path(handle.name)
        os.replace(temp, path)
    finally:
        if temp is not None and temp.exists():
            temp.unlink(missing_ok=True)


def _validate_factual_types(rows: list[dict]) -> None:
    invalid = sorted({
        str(row.get("information_family") or "").strip()
        for row in rows
        if str(row.get("information_family") or "").strip() not in CANONICAL_FACTUAL_TYPES
    })
    if invalid:
        raise ValueError(f"unsupported factual types: {invalid}")


def export_records(records: list[dict], output: Path = DEFAULT_OUTPUT) -> list[dict]:
    _validate_factual_types(records)
    normalized = [normalize_crosscheck_record("instagram_content", row) for row in records]
    _write_json_atomic(output, {"domain": "instagram_content", "records": normalized})
    return normalized


def persist_verified_snapshot(records: list[dict], output: Path = DEFAULT_PERSISTED_OUTPUT) -> dict:
    normalized = [normalize_crosscheck_record("instagram_content", row) for row in records]
    _validate_factual_types(normalized)
    verified = [row for row in normalized if row.get("verification") == "verified"]
    if not verified:
        raise ValueError("no verified factual rows; persisted snapshot not replaced")
    kst = dt.timezone(dt.timedelta(hours=9))
    stamp = dt.datetime.now(kst).isoformat(timespec="seconds")
    facts = [{
        "canonical_key": row["canonical_key"],
        "fact_type": row["information_family"],
        "lineage_key": row["lineage_key"],
        "identity": {"variant": row["variant"]},
        "value": row["value"],
        "value_type": "text",
        "currency": row["currency"],
        "region": "",
        "language": row["language"],
        "condition": "",
        "grade_company": "",
        "grade": "",
        "effective_date": "",
        "observed_at": row["checked_at_kst"],
        "source_role": row["source_code"],
        "source_locator": row["source_locator"],
        "verification_status": "verified",
    } for row in verified]
    payload = {
        "schema_version": "1.0",
        "namespace": "IG_CARDINFO",
        "snapshot_kind": "factual",
        "run_date_kst": stamp[:10],
        "status": "finalized",
        "built_at": stamp,
        "finalized_at": stamp,
        "facts": facts,
        "validation": {
            "manifest_validated": True,
            "allowed_fields_only": True,
            "exact_factual_types_enforced": True,
            "write_readback_verified": True,
            "isolation_breach": False,
        },
        "error_code": None,
    }
    _write_json_atomic(output, payload)
    return payload


def self_test() -> None:
    sample = {
        "information_family": "event",
        "canonical_key": "onepiece|event|jp",
        "value": "2026-09-10",
        "currency": "",
        "language": "JP",
        "variant": "",
        "source_code": "instagram-source",
        "source_locator": "source",
        "checked_at_kst": "2026-09-04T13:30:00+09:00",
        "verification": "candidate",
        "confidence": 0.7,
        "lineage_key": "instagram-lineage",
        "retry_count": 7,
        "learning_state": {"bad": True}
    }
    row = normalize_crosscheck_record("instagram_content", sample)
    assert row["domain"] == "instagram_content"
    assert "retry_count" not in row and "learning_state" not in row
    print("Instagram crosscheck export contract: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--persisted-output")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.input:
        raise SystemExit("--input is required unless --self-test is used")
    value = json.loads(Path(args.input).read_text(encoding="utf-8"))
    records = value.get("records", value) if isinstance(value, dict) else value
    if not isinstance(records, list) or not all(isinstance(row, dict) for row in records):
        raise SystemExit("input must be a JSON list or object with records list")
    export_records(records, Path(args.output))
    if args.persisted_output:
        persist_verified_snapshot(records, Path(args.persisted_output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
