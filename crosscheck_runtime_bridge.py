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
from shared_self_learning.contracts import (
    CANONICAL_FACTUAL_TYPES,
    assert_canonical_factual_type,
    assert_passive_exchange_payload,
)
from shared_self_learning.engine import normalize_crosscheck_record

ROOT = Path(__file__).resolve().parent
EXCHANGE = ROOT / "crosscheck_exchange"
DEFAULT_MAIN_OUTPUT = EXCHANGE / "runtime-main.json"
DEFAULT_INSTAGRAM_OUTPUT = EXCHANGE / "runtime-instagram.json"
DEFAULT_REPORT = EXCHANGE / "runtime-crosscheck-report.json"

PERSISTED_ROOT = ROOT / "TCG_CROSSCHECK"
DEFAULT_MAIN_PERSISTED = PERSISTED_ROOT / "MARKET_ANALYSIS" / "factual_snapshot.json"
DEFAULT_INSTAGRAM_PERSISTED = PERSISTED_ROOT / "IG_CARDINFO" / "factual_snapshot.json"
DEFAULT_MAX_SNAPSHOT_AGE_HOURS = 36.0

PERSISTED_FACTUAL_FIELDS = {
    "canonical_key", "fact_type", "lineage_key", "identity", "value",
    "value_type", "currency", "region", "language", "condition",
    "grade_company", "grade", "effective_date", "observed_at",
    "source_role", "source_locator", "verification_status",
}
PERSISTED_VERIFICATION_STATES = {
    "verified", "conflict", "missing", "unverified", "quarantine",
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


def _export_domain(domain: str, records: list[dict[str, Any]], output: Path) -> None:
    normalized = [normalize_crosscheck_record(domain, row) for row in records]
    atomic_write_json(
        output,
        {"domain": domain, "records": normalized},
        suffix=f".{domain}-crosscheck.tmp",
    )


def _aware_utc(value: object, *, label: str) -> dt.datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label}: timezone-aware timestamp is required")
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label}: invalid ISO-8601 timestamp {text!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label}: timestamp must be timezone-aware")
    return parsed.astimezone(dt.timezone.utc)


def _utc_now(now: dt.datetime | None) -> dt.datetime:
    if now is None:
        return dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(dt.timezone.utc)


def _age_hours(timestamp: dt.datetime, now: dt.datetime) -> float:
    return (now - timestamp).total_seconds() / 3600.0


def _persistent_variant(row: dict[str, Any], factual_type: str) -> str:
    if factual_type == "completed_sale":
        return f"sale_lineage={str(row.get('lineage_key') or '').strip()}"[:120]
    parts = []
    for key in ("region", "condition", "grade_company", "grade", "value_type"):
        value = str(row.get(key) or "").strip().replace("|", "/")
        if value:
            parts.append(f"{key}={value}")
    return "|".join(parts)[:120]


def _persistent_value(row: dict[str, Any]) -> str:
    identity = row.get("identity")
    if identity is None:
        identity = {}
    return json.dumps(
        {
            "value": "" if row.get("value") is None else str(row.get("value")),
            "effective_date": str(row.get("effective_date") or ""),
            "identity": identity,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _load_persisted_snapshot(
    path: Path,
    *,
    expected_namespace: str,
    now: dt.datetime,
    max_age_hours: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not path.exists():
        return [], {"available": False, "reason": "missing", "path": str(path), "namespace": expected_namespace}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise ValueError(f"{path}: invalid persisted snapshot: {type(exc).__name__}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: persisted snapshot root must be an object")
    assert_passive_exchange_payload(payload)

    if str(payload.get("schema_version") or "") != "1.0":
        raise ValueError(f"{path}: schema_version must be '1.0'")
    if payload.get("namespace") != expected_namespace:
        raise ValueError(f"{path}: namespace mismatch; expected={expected_namespace!r} actual={payload.get('namespace')!r}")
    if payload.get("snapshot_kind") != "factual":
        raise ValueError(f"{path}: snapshot_kind must be 'factual'")

    status = str(payload.get("status") or "").strip()
    if status != "finalized":
        return [], {
            "available": False, "reason": "not_finalized", "status": status or "missing",
            "path": str(path), "namespace": expected_namespace,
        }

    finalized = _aware_utc(payload.get("finalized_at"), label=f"{path}:finalized_at")
    snapshot_age = _age_hours(finalized, now)
    if snapshot_age < -(5.0 / 60.0):
        raise ValueError(f"{path}: finalized_at is more than 5 minutes in the future")
    if snapshot_age > max_age_hours:
        return [], {
            "available": False, "reason": "stale_snapshot",
            "snapshot_age_hours": round(snapshot_age, 3),
            "path": str(path), "namespace": expected_namespace,
        }

    validation = payload.get("validation")
    if not isinstance(validation, dict):
        raise ValueError(f"{path}: validation object is required")
    required_true = ("manifest_validated", "allowed_fields_only", "exact_factual_types_enforced", "write_readback_verified")
    failed_validation = [key for key in required_true if validation.get(key) is not True]
    if failed_validation:
        raise ValueError(f"{path}: persisted validation flags are not PASS: {failed_validation}")
    if validation.get("isolation_breach") is True:
        raise ValueError(f"{path}: isolation_breach=true")

    facts = payload.get("facts")
    if not isinstance(facts, list) or not all(isinstance(row, dict) for row in facts):
        raise ValueError(f"{path}: facts must be a list of objects")
    if not facts:
        return [], {
            "available": False, "reason": "empty_facts", "path": str(path),
            "namespace": expected_namespace, "snapshot_age_hours": round(snapshot_age, 3),
        }

    unique: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    verified_total = 0
    stale_verified = 0

    for index, row in enumerate(facts):
        extra = sorted(set(row) - PERSISTED_FACTUAL_FIELDS)
        if extra:
            raise ValueError(f"{path}: facts[{index}] has forbidden/unknown fields: {extra}")
        factual_type = assert_canonical_factual_type(row.get("fact_type"), label=f"{path}:facts[{index}].fact_type")
        canonical_key = str(row.get("canonical_key") or "").strip()
        lineage_key = str(row.get("lineage_key") or "").strip()
        if not canonical_key or not lineage_key:
            raise ValueError(f"{path}: facts[{index}] requires canonical_key and lineage_key")

        verification_status = str(row.get("verification_status") or "").strip()
        if verification_status not in PERSISTED_VERIFICATION_STATES:
            raise ValueError(f"{path}: facts[{index}] invalid verification_status {verification_status!r}")
        if verification_status != "verified":
            continue

        verified_total += 1
        source_role = str(row.get("source_role") or "").strip()
        source_locator = str(row.get("source_locator") or "").strip()
        observed_text = str(row.get("observed_at") or "").strip()
        if not source_role or not source_locator or not observed_text:
            raise ValueError(f"{path}: verified facts[{index}] missing source_role/source_locator/observed_at")
        observed = _aware_utc(observed_text, label=f"{path}:facts[{index}].observed_at")
        observed_age = _age_hours(observed, now)
        if observed_age < -(5.0 / 60.0):
            raise ValueError(f"{path}: facts[{index}].observed_at is in the future")
        if observed_age > max_age_hours:
            stale_verified += 1
            continue

        mapped = {
            "information_family": factual_type,
            "canonical_key": canonical_key,
            "value": _persistent_value(row),
            "currency": str(row.get("currency") or "").strip(),
            "language": str(row.get("language") or "").strip(),
            "variant": _persistent_variant(row, factual_type),
            "source_code": source_role,
            "source_locator": source_locator,
            "checked_at_kst": observed_text,
            "verification": "verified",
            "confidence": 0.0,
            "lineage_key": lineage_key,
        }
        key = (
            mapped["information_family"], mapped["canonical_key"],
            mapped["currency"], mapped["language"], mapped["variant"],
        )
        prior = unique.get(key)
        if prior is not None and prior["value"] != mapped["value"]:
            raise ValueError(f"{path}: local canonical conflict for {key}; finalized snapshot contains divergent verified values")
        if prior is None:
            unique[key] = mapped

    records = list(unique.values())
    if not records:
        return [], {
            "available": False, "reason": "no_fresh_verified_facts",
            "verified_total": verified_total, "stale_verified": stale_verified,
            "path": str(path), "namespace": expected_namespace,
            "snapshot_age_hours": round(snapshot_age, 3),
        }
    return records, {
        "available": True, "reason": "ready", "records": len(records),
        "verified_total": verified_total, "stale_verified": stale_verified,
        "path": str(path), "namespace": expected_namespace,
        "snapshot_age_hours": round(snapshot_age, 3), "finalized_at": finalized.isoformat(),
    }


def _remove_runtime_outputs(*paths: Path) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


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
            "status": "snapshot_missing", "engine_available": True, "operational_ready": False,
            "missing_domains": missing, "main_records": len(main_records),
            "instagram_records": len(instagram_records), "agree": 0, "conflict": 0,
            "reverification_required": 0, "factual_type_contract": sorted(CANONICAL_FACTUAL_TYPES),
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


def run_persisted_bridge(
    main_snapshot: Path = DEFAULT_MAIN_PERSISTED,
    instagram_snapshot: Path = DEFAULT_INSTAGRAM_PERSISTED,
    *,
    main_output: Path = DEFAULT_MAIN_OUTPUT,
    instagram_output: Path = DEFAULT_INSTAGRAM_OUTPUT,
    report_output: Path | None = DEFAULT_REPORT,
    now: dt.datetime | None = None,
    max_age_hours: float = DEFAULT_MAX_SNAPSHOT_AGE_HOURS,
) -> dict[str, Any]:
    if max_age_hours <= 0:
        raise ValueError("max_age_hours must be positive")
    current = _utc_now(now)
    main_records, main_meta = _load_persisted_snapshot(
        main_snapshot, expected_namespace="MARKET_ANALYSIS", now=current, max_age_hours=max_age_hours,
    )
    instagram_records, instagram_meta = _load_persisted_snapshot(
        instagram_snapshot, expected_namespace="IG_CARDINFO", now=current, max_age_hours=max_age_hours,
    )
    if not main_meta.get("available") or not instagram_meta.get("available"):
        _remove_runtime_outputs(main_output, instagram_output)
        unavailable = {}
        if not main_meta.get("available"):
            unavailable["main"] = main_meta.get("reason")
        if not instagram_meta.get("available"):
            unavailable["instagram_content"] = instagram_meta.get("reason")
        result = {
            "status": "snapshot_unavailable", "engine_available": True, "operational_ready": False,
            "missing_domains": sorted(unavailable), "unavailable_reasons": unavailable,
            "main_records": len(main_records), "instagram_records": len(instagram_records),
            "agree": 0, "conflict": 0, "reverification_required": 0,
            "factual_type_contract": sorted(CANONICAL_FACTUAL_TYPES),
            "source_mode": "persisted_tcg_crosscheck",
            "persisted_snapshots": {"main": main_meta, "instagram_content": instagram_meta},
        }
        if report_output is not None:
            atomic_write_json(report_output, result, suffix=".crosscheck-persisted.tmp")
        return result

    result = run_bridge(
        main_records, instagram_records, main_output=main_output,
        instagram_output=instagram_output, report_output=None,
    )
    result["source_mode"] = "persisted_tcg_crosscheck"
    result["persisted_snapshots"] = {"main": main_meta, "instagram_content": instagram_meta}
    if report_output is not None:
        atomic_write_json(report_output, result, suffix=".crosscheck-persisted.tmp")
    return result


def _sample_persisted_snapshot(namespace: str, *, lineage: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0", "namespace": namespace, "snapshot_kind": "factual",
        "run_date_kst": "2026-09-06", "status": "finalized",
        "built_at": "2026-09-06T06:00:00+09:00", "finalized_at": "2026-09-06T06:10:00+09:00",
        "facts": [{
            "canonical_key": "pokemon|30th-celebration|jp", "fact_type": "release",
            "lineage_key": lineage, "identity": {"game": "pokemon", "product": "30th-celebration"},
            "value": "2026-09-16", "value_type": "date", "currency": "", "region": "JP",
            "language": "JP", "condition": "", "grade_company": "", "grade": "",
            "effective_date": "2026-09-16", "observed_at": "2026-09-06T06:00:00+09:00",
            "source_role": "official_primary", "source_locator": "https://example.invalid/fact",
            "verification_status": "verified",
        }],
        "validation": {
            "manifest_validated": True, "allowed_fields_only": True,
            "exact_factual_types_enforced": True, "write_readback_verified": True,
            "isolation_breach": False,
        },
        "error_code": None,
    }


def self_test() -> None:
    base = {
        "information_family": "release", "canonical_key": "pokemon|30th-celebration|jp",
        "value": "2026-09-16", "currency": "", "language": "JP", "variant": "",
        "source_code": "main-official", "source_locator": "https://example.invalid/main",
        "checked_at_kst": "2026-09-06T06:00:00+09:00", "verification": "verified",
        "confidence": 0.99, "lineage_key": "main-release-lineage",
    }
    same = {
        **base, "source_code": "instagram-official",
        "source_locator": "https://example.invalid/instagram",
        "checked_at_kst": "2026-09-06T06:30:00+09:00",
        "verification": "corroborated", "lineage_key": "instagram-release-lineage",
    }
    left_market = {
        **base, "information_family": "market_reference",
        "canonical_key": "onepiece|op17|box|jp", "value": "24500",
        "currency": "JPY", "variant": "BOX", "source_code": "main-market",
        "lineage_key": "main-market-lineage",
    }
    right_market = {
        **left_market, "value": "25000", "source_code": "instagram-market",
        "source_locator": "https://example.invalid/instagram-market",
        "verification": "candidate", "lineage_key": "instagram-market-lineage",
    }

    with tempfile.TemporaryDirectory(dir=EXCHANGE) as tmp:
        root = Path(tmp)
        result = run_bridge(
            [base, left_market], [same, right_market],
            main_output=root / "main.json", instagram_output=root / "instagram.json",
            report_output=root / "report.json",
        )
        assert result["operational_ready"] is True and result["agree"] == 1 and result["conflict"] == 1, result

        missing = run_bridge(
            [base], [], main_output=root / "missing-main.json",
            instagram_output=root / "missing-instagram.json", report_output=root / "missing-report.json",
        )
        assert missing["status"] == "snapshot_missing" and missing["operational_ready"] is False, missing

        try:
            run_bridge(
                [{**base, "information_family": "market_price"}], [same],
                main_output=root / "invalid-main.json", instagram_output=root / "invalid-instagram.json",
                report_output=None,
            )
        except ValueError:
            pass
        else:
            raise AssertionError("non-canonical factual type must fail closed")

        main_persisted = root / "persisted-main.json"
        instagram_persisted = root / "persisted-instagram.json"
        main_persisted.write_text(
            json.dumps(_sample_persisted_snapshot("MARKET_ANALYSIS", lineage="main-release"), ensure_ascii=False),
            encoding="utf-8",
        )
        instagram_persisted.write_text(
            json.dumps(_sample_persisted_snapshot("IG_CARDINFO", lineage="ig-release"), ensure_ascii=False),
            encoding="utf-8",
        )
        persisted = run_persisted_bridge(
            main_persisted, instagram_persisted,
            main_output=root / "persisted-runtime-main.json",
            instagram_output=root / "persisted-runtime-instagram.json",
            report_output=root / "persisted-report.json",
            now=dt.datetime(2026, 9, 6, 0, 0, tzinfo=dt.timezone.utc),
        )
        assert persisted["operational_ready"] is True and persisted["agree"] == 1, persisted
    print("Cross-domain factual runtime bridge: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--main-input")
    parser.add_argument("--instagram-input")
    parser.add_argument("--main-output", default=str(DEFAULT_MAIN_OUTPUT))
    parser.add_argument("--instagram-output", default=str(DEFAULT_INSTAGRAM_OUTPUT))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--persisted", action="store_true")
    parser.add_argument("--main-persisted", default=str(DEFAULT_MAIN_PERSISTED))
    parser.add_argument("--instagram-persisted", default=str(DEFAULT_INSTAGRAM_PERSISTED))
    parser.add_argument("--max-snapshot-age-hours", type=float, default=DEFAULT_MAX_SNAPSHOT_AGE_HOURS)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0
    if args.persisted:
        result = run_persisted_bridge(
            Path(args.main_persisted), Path(args.instagram_persisted),
            main_output=Path(args.main_output), instagram_output=Path(args.instagram_output),
            report_output=Path(args.report), max_age_hours=args.max_snapshot_age_hours,
        )
    else:
        if not args.main_input or not args.instagram_input:
            raise SystemExit("--main-input and --instagram-input are required unless --persisted is used")
        result = run_bridge(
            _load_records(Path(args.main_input)), _load_records(Path(args.instagram_input)),
            main_output=Path(args.main_output), instagram_output=Path(args.instagram_output),
            report_output=Path(args.report),
        )
    print(json.dumps({
        "status": result["status"], "engine_available": result["engine_available"],
        "operational_ready": result["operational_ready"], "source_mode": result.get("source_mode"),
        "main_records": result["main_records"], "instagram_records": result["instagram_records"],
        "agree": result["agree"], "conflict": result["conflict"],
        "reverification_required": result["reverification_required"],
        "unavailable_reasons": result.get("unavailable_reasons", {}),
    }, ensure_ascii=False))
    return 0 if result["operational_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
