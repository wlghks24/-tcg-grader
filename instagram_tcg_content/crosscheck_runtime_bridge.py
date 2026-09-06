#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from main_crosscheck_export import export_records as export_main_records
from selfrefine_crosscheck_gate import run as run_crosscheck
from instagram_tcg_content.crosscheck_export import export_records as export_instagram_records
from safe_runtime import atomic_write_json

ROOT = Path(__file__).resolve().parents[1]
EXCHANGE = ROOT / "crosscheck_exchange"
DEFAULT_MAIN_OUTPUT = EXCHANGE / "runtime-main.json"
DEFAULT_INSTAGRAM_OUTPUT = EXCHANGE / "runtime-instagram.json"
DEFAULT_REPORT = EXCHANGE / "runtime-crosscheck-report.json"

CANONICAL_FACTUAL_TYPES = {
    "card_price",
    "release",
    "rerelease",
    "promo",
    "event",
    "movie_bonus",
    "completed_sale",
    "market_reference",
}


def _load_records(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    records = value.get("records", value) if isinstance(value, dict) else value
    if not isinstance(records, list) or not all(isinstance(row, dict) for row in records):
        raise ValueError(f"{path}: input must be a JSON list or object with records list")
    return records


def _validate_factual_types(records: list[dict[str, Any]], *, label: str) -> None:
    invalid = sorted({
        str(row.get("information_family") or "").strip()
        for row in records
        if str(row.get("information_family") or "").strip() not in CANONICAL_FACTUAL_TYPES
    })
    if invalid:
        raise ValueError(
            f"{label}: unsupported information_family values: {invalid}; "
            f"allowed={sorted(CANONICAL_FACTUAL_TYPES)}"
        )


def run_bridge(
    main_records: list[dict[str, Any]],
    instagram_records: list[dict[str, Any]],
    *,
    main_output: Path = DEFAULT_MAIN_OUTPUT,
    instagram_output: Path = DEFAULT_INSTAGRAM_OUTPUT,
    report_output: Path | None = DEFAULT_REPORT,
) -> dict[str, Any]:
    if not main_records or not instagram_records:
        missing = []
        if not main_records:
            missing.append("main")
        if not instagram_records:
            missing.append("instagram_content")
        result = {
            "status": "snapshot_missing",
            "operational_ready": False,
            "missing_domains": missing,
            "main_records": len(main_records),
            "instagram_records": len(instagram_records),
            "agree": 0,
            "conflict": 0,
            "reverification_required": 0,
            "factual_type_contract": sorted(CANONICAL_FACTUAL_TYPES),
        }
        if report_output is not None:
            atomic_write_json(report_output, result, suffix=".crosscheck-bridge.tmp")
        return result

    _validate_factual_types(main_records, label="main")
    _validate_factual_types(instagram_records, label="instagram_content")

    export_main_records(main_records, main_output)
    export_instagram_records(instagram_records, instagram_output)
    result = run_crosscheck(main_output, instagram_output)
    result["operational_ready"] = result.get("status") == "crosschecked"
    result["factual_type_contract"] = sorted(CANONICAL_FACTUAL_TYPES)

    if report_output is not None:
        atomic_write_json(report_output, result, suffix=".crosscheck-bridge.tmp")
    return result


def self_test() -> None:
    base = {
        "information_family": "release",
        "canonical_key": "pokemon|30th-celebration|jp",
        "value": "2026-09-16",
        "currency": "",
        "language": "JP",
        "variant": "",
        "source_code": "main-official",
        "source_locator": "https://example.invalid/main",
        "checked_at_kst": "2026-09-06T06:00:00+09:00",
        "verification": "verified",
        "confidence": 0.99,
        "lineage_key": "main-release-lineage",
    }
    same = {
        **base,
        "source_code": "instagram-official",
        "source_locator": "https://example.invalid/instagram",
        "checked_at_kst": "2026-09-06T06:30:00+09:00",
        "verification": "corroborated",
        "lineage_key": "instagram-release-lineage",
    }
    conflict_main = {
        **base,
        "information_family": "market_reference",
        "canonical_key": "onepiece|op17|box|jp",
        "value": "24500",
        "currency": "JPY",
        "language": "JP",
        "variant": "BOX",
        "source_code": "main-market",
        "lineage_key": "main-market-lineage",
    }
    conflict_instagram = {
        **conflict_main,
        "value": "25000",
        "source_code": "instagram-market",
        "source_locator": "https://example.invalid/instagram-market",
        "verification": "candidate",
        "lineage_key": "instagram-market-lineage",
    }

    with tempfile.TemporaryDirectory(dir=EXCHANGE) as tmp:
        root = Path(tmp)
        result = run_bridge(
            [base, conflict_main],
            [same, conflict_instagram],
            main_output=root / "main.json",
            instagram_output=root / "instagram.json",
            report_output=root / "report.json",
        )
        assert result["operational_ready"] is True, result
        assert result["agree"] == 1, result
        assert result["conflict"] == 1, result
        assert result["reverification_required"] == 1, result

        missing = run_bridge(
            [base],
            [],
            main_output=root / "missing-main.json",
            instagram_output=root / "missing-instagram.json",
            report_output=root / "missing-report.json",
        )
        assert missing["status"] == "snapshot_missing", missing
        assert missing["operational_ready"] is False, missing
        assert not (root / "missing-main.json").exists()
        assert not (root / "missing-instagram.json").exists()

        try:
            run_bridge(
                [{**base, "information_family": "market_price"}],
                [same],
                main_output=root / "invalid-main.json",
                instagram_output=root / "invalid-instagram.json",
                report_output=None,
            )
        except ValueError:
            pass
        else:
            raise AssertionError("non-canonical factual type must fail closed")

    print("Instagram crosscheck runtime bridge: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--main-input")
    parser.add_argument("--instagram-input")
    parser.add_argument("--main-output", default=str(DEFAULT_MAIN_OUTPUT))
    parser.add_argument("--instagram-output", default=str(DEFAULT_INSTAGRAM_OUTPUT))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0
    if not args.main_input or not args.instagram_input:
        raise SystemExit("--main-input and --instagram-input are required")

    result = run_bridge(
        _load_records(Path(args.main_input)),
        _load_records(Path(args.instagram_input)),
        main_output=Path(args.main_output),
        instagram_output=Path(args.instagram_output),
        report_output=Path(args.report),
    )
    print(json.dumps({
        "status": result["status"],
        "operational_ready": result["operational_ready"],
        "main_records": result["main_records"],
        "instagram_records": result["instagram_records"],
        "agree": result["agree"],
        "conflict": result["conflict"],
        "reverification_required": result["reverification_required"],
    }, ensure_ascii=False))
    return 0 if result["operational_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
