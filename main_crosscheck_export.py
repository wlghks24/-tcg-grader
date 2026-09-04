#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from shared_self_learning.engine import normalize_crosscheck_record

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "crosscheck_exchange" / "runtime-main.json"


def export_records(records: list[dict], output: Path = DEFAULT_OUTPUT) -> list[dict]:
    normalized = [normalize_crosscheck_record("main", row) for row in records]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"domain": "main", "records": normalized}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return normalized


def self_test() -> None:
    sample = [{
        "information_family": "market_price",
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
