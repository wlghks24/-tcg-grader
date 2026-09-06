#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from safe_runtime import atomic_write_json
from selfrefine_crosscheck_gate import run as run_crosscheck
from shared_self_learning.engine import normalize_crosscheck_record

ROOT = Path(__file__).resolve().parent
EXCHANGE = ROOT / "crosscheck_exchange"
DEFAULT_MAIN_OUTPUT = EXCHANGE / "runtime-main.json"
DEFAULT_INSTAGRAM_OUTPUT = EXCHANGE / "runtime-instagram.json"
DEFAULT_REPORT = EXCHANGE / "runtime-crosscheck-report.json"
PERSISTED_MAIN = ROOT / "TCG_CROSSCHECK" / "MARKET_ANALYSIS" / "factual_snapshot.json"
PERSISTED_INSTAGRAM = ROOT / "TCG_CROSSCHECK" / "IG_CARDINFO" / "factual_snapshot.json"

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


def _manifest_fact_to_record(row: dict[str, Any]) -> dict[str, Any]:
    verification_status = str(row.get("verification_status") or "").strip().lower()
    verification = "verified" if verification_status == "verified" else "candidate"
    variant_parts = [
        str(row.get("condition") or "").strip(),
        str(row.get("grade_company") or "").strip(),
        str(row.get("grade") or "").strip(),
    ]
    variant = "|".join(part for part in variant_parts if part)
    value = row.get("value")
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "information_family": str(row.get("fact_type") or "").strip(),
        "canonical_key": str(row.get("canonical_key") or "").strip(),
        "value": "" if value is None else str(value),
        "currency": str(row.get("currency") or "").strip(),
        "language": str(row.get("language") or row.get("region") or "").strip(),
        "variant": variant,
        "source_code": str(row.get("source_role") or "persisted-snapshot").strip(),
        "source_locator": str(row.get("source_locator") or "").strip(),
        "checked_at_kst": str(row.get("observed_at") or "").strip(),
        "verification": verification,
        "confidence": 1.0 if verification == "verified" else 0.5,
        "lineage_key": str(row.get("lineage_key") or "").strip(),
    }


def _load_records(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, dict) and "facts" in value:
        if value.get("status") != "finalized":
            return []
        facts = value.get("facts")
        if not isinstance(facts, list) or not all(isinstance(row, dict) for row in facts):
            raise ValueError(f"{path}: persisted snapshot facts must be a list")
        return [_manifest_fact_to_record(row) for row in facts]
    records = value.get("records", value) if isinstance(value, dict) else value
    if not isinstance(records, list) or not all(isinstance(row, dict) for row in records):
        raise ValueError(f"{path}: input must be a JSON list, records list, or finalized facts snapshot")
    return records


def _load_persisted_records(path: Path, expected_namespace: str) -> tuple[list[dict[str, Any]], str]:
    if not path.exists():
        return ([], "missing")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: persisted snapshot root must be an object")
    if value.get("namespace") != expected_namespace:
        raise ValueError(
            f"{path}: namespace mismatch: expected {expected_namespace!r}, got {value.get('namespace')!r}"
        )
    if value.get("snapshot_kind") not in {None, "factual"}:
        raise ValueError(f"{path}: snapshot_kind must be factual")
    status = str(value.get("status") or "").strip()
    if status != "finalized":
        return ([], status or "unknown")
    facts = value.get("facts")
    if not isinstance(facts, list) or not all(isinstance(row, dict) for row in facts):
        raise ValueError(f"{path}: finalized persisted snapshot facts must be a list")
    if not facts:
        return ([], "finalized_empty")
    return ([_manifest_fact_to_record(row) for row in facts], status)


def _remove_stale_runtime_outputs(
    main_output: Path,
    instagram_output: Path,
) -> None:
    for path in (main_output, instagram_output):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


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


def _export_domain(domain: str, records: list[dict[str, Any]], output: Path) -> None:
    normalized = [normalize_crosscheck_record(domain, row) for row in records]
    atomic_write_json(
        output,
        {"domain": domain, "records": normalized},
        suffix=f".{domain}-crosscheck.tmp",
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
        _remove_stale_runtime_outputs(main_output, instagram_output)
        missing = []
        if not main_records:
            missing.append("main")
        if not instagram_records:
            missing.append("instagram_content")
        result = {
            "status": "snapshot_missing",
            "engine_available": True,
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

    _export_domain("main", main_records, main_output)
    _export_domain("instagram_content", instagram_records, instagram_output)
    result = run_crosscheck(main_output, instagram_output)
    result["engine_available"] = True
    result["operational_ready"] = result.get("status") == "crosschecked"
    result["factual_type_contract"] = sorted(CANONICAL_FACTUAL_TYPES)

    if report_output is not None:
        atomic_write_json(report_output, result, suffix=".crosscheck-bridge.tmp")
    return result


def run_from_persisted(
    *,
    main_snapshot: Path = PERSISTED_MAIN,
    instagram_snapshot: Path = PERSISTED_INSTAGRAM,
    main_output: Path = DEFAULT_MAIN_OUTPUT,
    instagram_output: Path = DEFAULT_INSTAGRAM_OUTPUT,
    report_output: Path | None = DEFAULT_REPORT,
) -> dict[str, Any]:
    main_records, main_status = _load_persisted_records(main_snapshot, "MARKET_ANALYSIS")
    instagram_records, instagram_status = _load_persisted_records(
        instagram_snapshot, "IG_CARDINFO"
    )
    result = run_bridge(
        main_records,
        instagram_records,
        main_output=main_output,
        instagram_output=instagram_output,
        report_output=report_output,
    )
    result["persisted_main_status"] = main_status
    result["persisted_instagram_status"] = instagram_status
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

        persisted_main = root / "persisted-main.json"
        persisted_instagram = root / "persisted-instagram.json"
        persisted_main.write_text(json.dumps({
            "namespace": "MARKET_ANALYSIS",
            "status": "finalized",
            "facts": [{
                "fact_type": "release",
                "canonical_key": "pokemon|30th-celebration|jp",
                "lineage_key": "pmain",
                "value": "2026-09-16",
                "language": "JP",
                "source_role": "official_primary",
                "source_locator": "https://example.invalid/p-main",
                "observed_at": "2026-09-06T06:00:00+09:00",
                "verification_status": "verified",
            }],
        }), encoding="utf-8")
        persisted_instagram.write_text(json.dumps({
            "namespace": "IG_CARDINFO",
            "status": "finalized",
            "facts": [{
                "fact_type": "release",
                "canonical_key": "pokemon|30th-celebration|jp",
                "lineage_key": "pinstagram",
                "value": "2026-09-16",
                "language": "JP",
                "source_role": "official_primary",
                "source_locator": "https://example.invalid/p-instagram",
                "observed_at": "2026-09-06T06:30:00+09:00",
                "verification_status": "verified",
            }],
        }), encoding="utf-8")
        persisted = run_from_persisted(
            main_snapshot=persisted_main,
            instagram_snapshot=persisted_instagram,
            main_output=root / "persisted-runtime-main.json",
            instagram_output=root / "persisted-runtime-instagram.json",
            report_output=root / "persisted-report.json",
        )
        assert persisted["operational_ready"] is True, persisted
        assert persisted["agree"] == 1, persisted

        persisted_instagram.write_text(json.dumps({
            "namespace": "IG_CARDINFO",
            "status": "building",
            "facts": [],
        }), encoding="utf-8")
        stale_main = root / "stale-main.json"
        stale_instagram = root / "stale-instagram.json"
        stale_main.write_text("{}", encoding="utf-8")
        stale_instagram.write_text("{}", encoding="utf-8")
        unavailable = run_from_persisted(
            main_snapshot=persisted_main,
            instagram_snapshot=persisted_instagram,
            main_output=stale_main,
            instagram_output=stale_instagram,
            report_output=root / "unavailable-report.json",
        )
        assert unavailable["operational_ready"] is False, unavailable
        assert not stale_main.exists() and not stale_instagram.exists(), unavailable

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

    print("Cross-domain factual runtime bridge: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--main-input")
    parser.add_argument("--instagram-input")
    parser.add_argument("--main-output", default=str(DEFAULT_MAIN_OUTPUT))
    parser.add_argument("--instagram-output", default=str(DEFAULT_INSTAGRAM_OUTPUT))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--from-persisted", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0
    if args.from_persisted:
        result = run_from_persisted(
            main_output=Path(args.main_output),
            instagram_output=Path(args.instagram_output),
            report_output=Path(args.report),
        )
        print(json.dumps({
            "status": result["status"],
            "engine_available": result["engine_available"],
            "operational_ready": result["operational_ready"],
            "persisted_main_status": result["persisted_main_status"],
            "persisted_instagram_status": result["persisted_instagram_status"],
            "main_records": result["main_records"],
            "instagram_records": result["instagram_records"],
            "agree": result["agree"],
            "conflict": result["conflict"],
            "reverification_required": result["reverification_required"],
        }, ensure_ascii=False))
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
        "engine_available": result["engine_available"],
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
