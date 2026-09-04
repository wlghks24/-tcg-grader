#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from shared_self_learning.engine import compare_record_sets

ROOT = Path(__file__).resolve().parent
EXCHANGE = ROOT / "crosscheck_exchange"
REPORT = ROOT / "SELFREFINE_CROSSCHECK_REPORT.json"


def _load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.suffix.lower() == ".jsonl":
        rows = []
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_no}: JSONL row must be an object")
            rows.append(value)
        return rows
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, dict):
        value = value.get("records", [])
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise ValueError(f"{path}: expected JSON list or records list")
    return value


def run(main_path: Path | None, instagram_path: Path | None) -> dict[str, Any]:
    main_rows = _load_records(main_path) if main_path else []
    instagram_rows = _load_records(instagram_path) if instagram_path else []
    result = compare_record_sets(main_rows, instagram_rows)
    result["status"] = (
        "crosschecked"
        if main_rows and instagram_rows
        else "no_exchange_data"
    )
    result["safety"] = {
        "passive_json_only": True,
        "verification_promotion": False,
        "provider_state_merged": False,
        "retry_state_merged": False,
        "learning_state_merged": False,
        "lineage_preserved": True,
    }
    return result


def self_test() -> None:
    base = {
        "information_family": "market_price",
        "canonical_key": "pokemon|pikachu|001|jp",
        "value": "10000",
        "currency": "JPY",
        "language": "JP",
        "variant": "normal",
        "source_code": "official-a",
        "source_locator": "https://example.invalid/a",
        "checked_at_kst": "2026-09-04T13:30:00+09:00",
        "verification": "verified",
        "confidence": 0.95,
        "lineage_key": "main-lineage",
    }
    same = dict(base)
    same.update({
        "source_code": "official-b",
        "source_locator": "https://example.invalid/b",
        "verification": "candidate",
        "lineage_key": "instagram-lineage",
    })
    agreed = compare_record_sets([base], [same])
    assert agreed["agree"] == 1 and agreed["conflict"] == 0, agreed
    row = agreed["comparisons"][0]
    assert row["verification_promotion"] is False
    assert row["main"]["verification"] == "verified"
    assert row["instagram_content"]["verification"] == "candidate"
    assert row["main"]["lineage_key"] != row["instagram_content"]["lineage_key"]

    conflict = dict(same)
    conflict["value"] = "15000"
    result = compare_record_sets([base], [conflict])
    assert result["conflict"] == 1 and result["agree"] == 0, result

    other = dict(same)
    other["canonical_key"] = "pokemon|pikachu|002|jp"
    result = compare_record_sets([base], [other])
    assert result["comparisons"] == [], result
    print("SELFREFINE cross-domain factual crosscheck: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--main", dest="main_path")
    parser.add_argument("--instagram", dest="instagram_path")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    result = run(
        Path(args.main_path) if args.main_path else None,
        Path(args.instagram_path) if args.instagram_path else None,
    )
    if args.write_report:
        REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "main_records": result["main_records"],
        "instagram_records": result["instagram_records"],
        "agree": result["agree"],
        "conflict": result["conflict"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
