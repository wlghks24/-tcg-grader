#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from shared_self_learning.engine import normalize_crosscheck_record
from safe_runtime import atomic_write_json

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "crosscheck_exchange" / "runtime-main.json"
CANONICAL_FACTUAL_TYPES = {
    "card_price", "release", "rerelease", "promo",
    "event", "movie_bonus", "completed_sale", "market_reference",
}


def export_records(records: list[dict], output: Path = DEFAULT_OUTPUT) -> list[dict]:
    invalid = sorted({
        str(row.get("information_family") or "").strip()
        for row in records
        if str(row.get("information_family") or "").strip() not in CANONICAL_FACTUAL_TYPES
    })
    if invalid:
        raise ValueError(f"unsupported factual types: {invalid}")
    normalized = [normalize_crosscheck_record("main", row) for row in records]
    atomic_write_json(
        output,
        {"domain": "main", "records": normalized},
        suffix=".main-crosscheck.tmp",
    )
    return normalized


def self_test() -> None:
    sample = [{
        "information_family": "market_reference",
        "canonical_key": "pokemon|001|jp",
        "value": "1000",
        "currency": "JPY",
        "language": "JP",
        "variant": "",
        "source_code": "main-source",
        "source_locator": "source",
        "checked_at_kst": "2026-09-04T13:30:00+09:00",
        "verification": "verified",
        "confidence": 0.9,
        "lineage_key": "main-lineage",
        "retry_count": 99,
        "provider_score": 1,
    }]
    row = normalize_crosscheck_record("main", sample[0])
    assert row["domain"] == "main"
    assert "retry_count" not in row and "provider_score" not in row
    print("Main crosscheck export contract: PASS")


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
    value = json.loads(Path(args.input).read_text(encoding="utf-8"))
    records = value.get("records", value) if isinstance(value, dict) else value
    if not isinstance(records, list) or not all(isinstance(row, dict) for row in records):
        raise SystemExit("input must be a JSON list or object with records list")
    export_records(records, Path(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
