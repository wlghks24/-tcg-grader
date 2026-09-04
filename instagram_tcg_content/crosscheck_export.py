#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from shared_self_learning.engine import normalize_crosscheck_record

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "crosscheck_exchange" / "runtime-instagram.json"


def export_records(records: list[dict], output: Path = DEFAULT_OUTPUT) -> list[dict]:
    normalized = [normalize_crosscheck_record("instagram_content", row) for row in records]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"domain": "instagram_content", "records": normalized}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return normalized


def self_test() -> None:
    sample = {
        "information_family": "promo_event",
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
        "learning_state": {"bad": true}
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
