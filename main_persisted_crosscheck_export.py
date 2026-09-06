#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from shared_self_learning.persisted_factual_snapshot import (
    export_snapshot as export_shared_snapshot,
    load_input_records,
)

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "TCG_CROSSCHECK" / "MARKET_ANALYSIS" / "factual_snapshot.json"


def export_snapshot(records: list[dict], output: Path = DEFAULT_OUTPUT):
    return export_shared_snapshot(
        records,
        output,
        namespace="MARKET_ANALYSIS",
        default_source_role="main_verified",
    )


def self_test() -> None:
    verified = {
        "information_family": "release",
        "canonical_key": "pokemon|30th-celebration|jp",
        "value": "2026-09-16",
        "language": "JP",
        "source_code": "pokemon-official",
        "source_locator": "https://example.invalid/pokemon",
        "checked_at_kst": "2026-09-06T06:00:00+09:00",
        "verification": "verified",
        "lineage_key": "main-release-1",
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
        assert empty["status"] == "building" and empty["facts"] == [], empty

        try:
            export_snapshot([{**verified, "information_family": "market_price"}], path)
        except ValueError:
            pass
        else:
            raise AssertionError("legacy/noncanonical factual type must fail closed")
    print("Main persisted factual snapshot export: PASS")


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
    payload = export_snapshot(load_input_records(Path(args.input)), Path(args.output))
    print(json.dumps({
        "status": payload["status"],
        "fact_count": len(payload["facts"]),
        "error_code": payload["error_code"],
        "output": str(Path(args.output)),
    }, ensure_ascii=False))
    return 0 if payload["status"] == "finalized" else 2


if __name__ == "__main__":
    raise SystemExit(main())
