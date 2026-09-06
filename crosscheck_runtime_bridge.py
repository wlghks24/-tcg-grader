#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import tempfile
from pathlib import Path
from typing import Any

from safe_runtime import atomic_write_json
from selfrefine_crosscheck_gate import run as run_crosscheck
from shared_self_learning.contracts import CANONICAL_FACTUAL_TYPES, canonicalize_factual_type
from shared_self_learning.engine import normalize_crosscheck_record
from shared_self_learning.persisted_factual_snapshot import (
    DEFAULT_MAX_AGE_HOURS,
    load_finalized_snapshot,
)

ROOT = Path(__file__).resolve().parent
EXCHANGE = ROOT / "crosscheck_exchange"
DEFAULT_MAIN_OUTPUT = EXCHANGE / "runtime-main.json"
DEFAULT_INSTAGRAM_OUTPUT = EXCHANGE / "runtime-instagram.json"
DEFAULT_REPORT = EXCHANGE / "runtime-crosscheck-report.json"
PERSISTED_MAIN = ROOT / "TCG_CROSSCHECK" / "MARKET_ANALYSIS" / "factual_snapshot.json"
PERSISTED_INSTAGRAM = ROOT / "TCG_CROSSCHECK" / "IG_CARDINFO" / "factual_snapshot.json"


def _load_records(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    records = value.get("records", value) if isinstance(value, dict) else value
    if not isinstance(records, list) or not all(isinstance(row, dict) for row in records):
        raise ValueError(f"{path}: input must be a JSON list or object with records list")
    return records


def _validate_factual_types(records: list[dict[str, Any]], *, label: str) -> None:
    for index, row in enumerate(records):
        canonicalize_factual_type(
            row.get("information_family"),
            label=f"{label}[{index}].information_family",
        )


def _persisted_fact_to_runtime(row: dict[str, Any]) -> dict[str, Any]:
    fact_type = canonicalize_factual_type(row.get("fact_type"), label="fact_type")
    value = row.get("value")
    if value is None:
        value = row.get("effective_date")
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    variant_parts = []
    for key in ("region", "condition", "grade_company", "grade", "value_type"):
        item = str(row.get(key) or "").strip().replace("|", "/")
        if item:
            variant_parts.append(f"{key}={item}")

    return {
        "information_family": fact_type,
        "canonical_key": str(row.get("canonical_key") or "").strip(),
        "value": "" if value is None else str(value),
        "currency": str(row.get("currency") or "").strip(),
        "language": str(row.get("language") or "").strip(),
        "variant": "|".join(variant_parts)[:120],
        "source_code": str(row.get("source_role") or "persisted_verified").strip(),
        "source_locator": str(row.get("source_locator") or "").strip(),
        "checked_at_kst": str(row.get("observed_at") or "").strip(),
        "verification": "verified",
        # Persisted snapshots intentionally carry no numeric confidence score.
        "confidence": 0.0,
        "lineage_key": str(row.get("lineage_key") or "").strip(),
    }


def _remove_stale_runtime_outputs(main_output: Path, instagram_output: Path) -> None:
    for path in (main_output, instagram_output):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


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
            "source_mode": "runtime_records",
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
    result["source_mode"] = "runtime_records"
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
    now: dt.datetime | None = None,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
) -> dict[str, Any]:
    main_facts, main_meta = load_finalized_snapshot(
        main_snapshot,
        expected_namespace="MARKET_ANALYSIS",
        now=now,
        max_age_hours=max_age_hours,
    )
    instagram_facts, instagram_meta = load_finalized_snapshot(
        instagram_snapshot,
        expected_namespace="IG_CARDINFO",
        now=now,
        max_age_hours=max_age_hours,
    )

    if not main_meta.get("available") or not instagram_meta.get("available"):
        _remove_stale_runtime_outputs(main_output, instagram_output)
        unavailable = {}
        if not main_meta.get("available"):
            unavailable["main"] = main_meta.get("reason")
        if not instagram_meta.get("available"):
            unavailable["instagram_content"] = instagram_meta.get("reason")
        result = {
            "status": "snapshot_unavailable",
            "engine_available": True,
            "operational_ready": False,
            "missing_domains": sorted(unavailable),
            "unavailable_reasons": unavailable,
            "main_records": 0,
            "instagram_records": 0,
            "agree": 0,
            "conflict": 0,
            "reverification_required": 0,
            "factual_type_contract": sorted(CANONICAL_FACTUAL_TYPES),
            "source_mode": "persisted_tcg_crosscheck",
            "persisted_snapshots": {
                "main": main_meta,
                "instagram_content": instagram_meta,
            },
        }
        if report_output is not None:
            atomic_write_json(report_output, result, suffix=".crosscheck-persisted.tmp")
        return result

    result = run_bridge(
        [_persisted_fact_to_runtime(row) for row in main_facts],
        [_persisted_fact_to_runtime(row) for row in instagram_facts],
        main_output=main_output,
        instagram_output=instagram_output,
        report_output=None,
    )
    result["source_mode"] = "persisted_tcg_crosscheck"
    result["persisted_snapshots"] = {
        "main": main_meta,
        "instagram_content": instagram_meta,
    }
    if report_output is not None:
        atomic_write_json(report_output, result, suffix=".crosscheck-persisted.tmp")
    return result


def _snapshot(namespace: str, lineage: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "namespace": namespace,
        "snapshot_kind": "factual",
        "run_date_kst": "2026-09-06",
        "status": "finalized",
        "built_at": "2026-09-06T06:00:00+09:00",
        "finalized_at": "2026-09-06T06:10:00+09:00",
        "facts": [{
            "canonical_key": "pokemon|30th-celebration|jp",
            "fact_type": "release",
            "lineage_key": lineage,
            "identity": "pokemon|30th-celebration|jp",
            "value": "2026-09-16",
            "value_type": "date",
            "currency": "",
            "region": "JP",
            "language": "JP",
            "condition": "",
            "grade_company": "",
            "grade": "",
            "effective_date": "2026-09-16",
            "observed_at": "2026-09-06T06:00:00+09:00",
            "source_role": "official_primary",
            "source_locator": "https://example.invalid/fact",
            "verification_status": "verified",
        }],
        "validation": {
            "manifest_validated": True,
            "allowed_fields_only": True,
            "exact_factual_types_enforced": True,
            "write_readback_verified": True,
            "isolation_breach": False,
        },
        "error_code": None,
    }


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
        "verification": "corroborated",
        "lineage_key": "instagram-release-lineage",
    }
    with tempfile.TemporaryDirectory(dir=EXCHANGE) as tmp:
        root = Path(tmp)
        result = run_bridge(
            [base],
            [same],
            main_output=root / "main.json",
            instagram_output=root / "instagram.json",
            report_output=root / "report.json",
        )
        assert result["operational_ready"] is True and result["agree"] == 1, result

        main_snapshot = root / "persisted-main.json"
        instagram_snapshot = root / "persisted-instagram.json"
        main_snapshot.write_text(json.dumps(_snapshot("MARKET_ANALYSIS", "main-l")), encoding="utf-8")
        instagram_snapshot.write_text(json.dumps(_snapshot("IG_CARDINFO", "ig-l")), encoding="utf-8")
        persisted = run_from_persisted(
            main_snapshot=main_snapshot,
            instagram_snapshot=instagram_snapshot,
            main_output=root / "p-main.json",
            instagram_output=root / "p-instagram.json",
            report_output=root / "p-report.json",
            now=dt.datetime(2026, 9, 6, 0, 0, tzinfo=dt.timezone.utc),
        )
        assert persisted["operational_ready"] is True and persisted["agree"] == 1, persisted

        building = _snapshot("IG_CARDINFO", "ig-l")
        building.update({"status": "building", "finalized_at": None, "facts": []})
        instagram_snapshot.write_text(json.dumps(building), encoding="utf-8")
        stale_main = root / "stale-main.json"
        stale_instagram = root / "stale-instagram.json"
        stale_main.write_text("{}", encoding="utf-8")
        stale_instagram.write_text("{}", encoding="utf-8")
        unavailable = run_from_persisted(
            main_snapshot=main_snapshot,
            instagram_snapshot=instagram_snapshot,
            main_output=stale_main,
            instagram_output=stale_instagram,
            report_output=root / "unavailable-report.json",
            now=dt.datetime(2026, 9, 6, 0, 0, tzinfo=dt.timezone.utc),
        )
        assert unavailable["status"] == "snapshot_unavailable", unavailable
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
    parser.add_argument("--max-snapshot-age-hours", type=float, default=DEFAULT_MAX_AGE_HOURS)
    parser.add_argument("--allow-unready", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0
    if args.from_persisted:
        result = run_from_persisted(
            main_output=Path(args.main_output),
            instagram_output=Path(args.instagram_output),
            report_output=Path(args.report),
            max_age_hours=args.max_snapshot_age_hours,
        )
    else:
        if not args.main_input or not args.instagram_input:
            raise SystemExit("--main-input and --instagram-input are required unless --from-persisted is used")
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
        "source_mode": result.get("source_mode"),
        "main_records": result["main_records"],
        "instagram_records": result["instagram_records"],
        "agree": result["agree"],
        "conflict": result["conflict"],
        "reverification_required": result["reverification_required"],
        "unavailable_reasons": result.get("unavailable_reasons", {}),
    }, ensure_ascii=False))
    if result["operational_ready"] or args.allow_unready:
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
