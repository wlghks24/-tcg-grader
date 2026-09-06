#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import tempfile
from pathlib import Path
from typing import Any

from crosscheck_runtime_bridge import run_bridge
from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "TCG_CROSSCHECK" / "exchange_manifest.json"
DEFAULT_MAIN_SNAPSHOT = ROOT / "TCG_CROSSCHECK" / "MARKET_ANALYSIS" / "factual_snapshot.json"
DEFAULT_INSTAGRAM_SNAPSHOT = ROOT / "TCG_CROSSCHECK" / "IG_CARDINFO" / "factual_snapshot.json"
DEFAULT_MAIN_RUNTIME = ROOT / "crosscheck_exchange" / "runtime-main.json"
DEFAULT_INSTAGRAM_RUNTIME = ROOT / "crosscheck_exchange" / "runtime-instagram.json"
DEFAULT_REPORT = ROOT / "crosscheck_exchange" / "runtime-crosscheck-report.json"

REQUIRED_VALIDATION = {
    "manifest_validated": True,
    "allowed_fields_only": True,
    "exact_factual_types_enforced": True,
    "write_readback_verified": True,
    "isolation_breach": False,
}


class SnapshotUnavailable(RuntimeError):
    pass


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(safe_read_text(path))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: snapshot root must be an object")
    return value


def _parse_time(value: Any) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _stable_value(value: Any) -> str:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(value if value is not None else "")


def _variant_from_fact(fact: dict[str, Any]) -> str:
    identity = fact.get("identity")
    if isinstance(identity, dict):
        explicit_variant = identity.get("variant")
        if explicit_variant not in (None, ""):
            return str(explicit_variant)
    payload = {
        "region": fact.get("region") or "",
        "condition": fact.get("condition") or "",
        "grade_company": fact.get("grade_company") or "",
        "grade": fact.get("grade") or "",
        "value_type": fact.get("value_type") or "",
    }
    if all(value == "" for value in payload.values()):
        return ""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load_manifest() -> dict[str, Any]:
    manifest = _read_json(MANIFEST)
    factual_types = manifest.get("factual_types")
    if not isinstance(factual_types, list) or not factual_types:
        raise ValueError("crosscheck manifest factual_types missing")
    return manifest


def snapshot_to_verified_records(
    path: Path,
    *,
    expected_namespace: str,
    manifest: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    manifest = manifest or _load_manifest()
    if not path.is_file():
        raise SnapshotUnavailable(f"{expected_namespace}: factual snapshot missing")

    snap = _read_json(path)
    if snap.get("namespace") != expected_namespace:
        raise ValueError(f"{path}: namespace mismatch")
    if snap.get("snapshot_kind") != "factual":
        raise ValueError(f"{path}: snapshot_kind must be factual")
    if snap.get("status") != "finalized":
        raise SnapshotUnavailable(f"{expected_namespace}: factual snapshot not finalized")
    if _parse_time(snap.get("finalized_at")) is None:
        raise ValueError(f"{path}: finalized_at must be timezone-aware")

    validation = snap.get("validation")
    if not isinstance(validation, dict):
        raise ValueError(f"{path}: validation block missing")
    mismatches = {
        key: {"expected": expected, "actual": validation.get(key)}
        for key, expected in REQUIRED_VALIDATION.items()
        if validation.get(key) is not expected
    }
    if mismatches:
        raise ValueError(f"{path}: validation contract mismatch: {mismatches}")

    facts = snap.get("facts")
    if not isinstance(facts, list):
        raise ValueError(f"{path}: facts must be a list")
    if not facts:
        raise SnapshotUnavailable(f"{expected_namespace}: factual snapshot empty")

    allowed = set(str(x) for x in manifest["factual_types"])
    required = set(str(x) for x in manifest.get("required_factual_keys") or [])
    verification_values = set(str(x) for x in manifest.get("verification_status_values") or [])

    rows: list[dict[str, Any]] = []
    for idx, fact in enumerate(facts):
        if not isinstance(fact, dict):
            raise ValueError(f"{path}: fact #{idx} must be an object")
        missing = sorted(key for key in required if not str(fact.get(key) or "").strip())
        if missing:
            raise ValueError(f"{path}: fact #{idx} missing required keys {missing}")
        fact_type = str(fact.get("fact_type") or "").strip()
        if fact_type not in allowed:
            raise ValueError(f"{path}: unsupported fact_type {fact_type!r}")
        verification = str(fact.get("verification_status") or "").strip().lower()
        if verification not in verification_values:
            raise ValueError(f"{path}: unsupported verification_status {verification!r}")
        if verification != "verified":
            continue

        observed_at = str(fact.get("observed_at") or "").strip()
        if _parse_time(observed_at) is None:
            raise ValueError(f"{path}: verified fact #{idx} requires timezone-aware observed_at")
        source_role = str(fact.get("source_role") or "").strip()
        source_locator = str(fact.get("source_locator") or "").strip()
        if not source_role or not source_locator:
            raise ValueError(f"{path}: verified fact #{idx} missing source provenance")

        rows.append(
            {
                "information_family": fact_type,
                "canonical_key": str(fact.get("canonical_key") or "").strip(),
                "value": _stable_value(fact.get("value")),
                "currency": str(fact.get("currency") or "").strip(),
                "language": str(fact.get("language") or "").strip(),
                "variant": _variant_from_fact(fact),
                "source_code": source_role,
                "source_locator": source_locator,
                "checked_at_kst": observed_at,
                "verification": "verified",
                "confidence": 1.0,
                "lineage_key": str(fact.get("lineage_key") or "").strip(),
            }
        )
    if not rows:
        raise SnapshotUnavailable(f"{expected_namespace}: no verified factual rows")
    return rows


def _clear_stale_runtime(paths: list[Path]) -> None:
    for path in paths:
        path.unlink(missing_ok=True)


def run_persisted_crosscheck(
    *,
    main_snapshot: Path = DEFAULT_MAIN_SNAPSHOT,
    instagram_snapshot: Path = DEFAULT_INSTAGRAM_SNAPSHOT,
    main_runtime: Path = DEFAULT_MAIN_RUNTIME,
    instagram_runtime: Path = DEFAULT_INSTAGRAM_RUNTIME,
    report: Path = DEFAULT_REPORT,
) -> dict[str, Any]:
    manifest = _load_manifest()
    runtime_paths = [main_runtime, instagram_runtime]
    try:
        main_rows = snapshot_to_verified_records(
            main_snapshot, expected_namespace="MARKET_ANALYSIS", manifest=manifest
        )
        instagram_rows = snapshot_to_verified_records(
            instagram_snapshot, expected_namespace="IG_CARDINFO", manifest=manifest
        )
    except SnapshotUnavailable as exc:
        _clear_stale_runtime(runtime_paths)
        result = {
            "status": "snapshot_missing",
            "engine_available": True,
            "operational_ready": False,
            "reason": str(exc),
            "main_records": 0,
            "instagram_records": 0,
            "agree": 0,
            "conflict": 0,
            "reverification_required": 0,
        }
        atomic_write_json(report, result, suffix=".persisted-crosscheck.tmp")
        return result
    except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
        _clear_stale_runtime(runtime_paths)
        result = {
            "status": "validation_error",
            "engine_available": True,
            "operational_ready": False,
            "reason": str(exc)[:1200],
            "main_records": 0,
            "instagram_records": 0,
            "agree": 0,
            "conflict": 0,
            "reverification_required": 0,
        }
        atomic_write_json(report, result, suffix=".persisted-crosscheck.tmp")
        return result

    result = run_bridge(
        main_rows,
        instagram_rows,
        main_output=main_runtime,
        instagram_output=instagram_runtime,
        report_output=report,
    )
    result["persisted_snapshot_validation"] = "pass"
    return result


def _sample_snapshot(namespace: str, facts: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "namespace": namespace,
        "snapshot_kind": "factual",
        "run_date_kst": "2026-09-06",
        "status": "finalized",
        "built_at": "2026-09-06T06:30:00+09:00",
        "finalized_at": "2026-09-06T06:31:00+09:00",
        "facts": facts,
        "validation": dict(REQUIRED_VALIDATION),
        "error_code": None,
    }


def self_test() -> None:
    base_fact = {
        "canonical_key": "pokemon|release|jp|sample",
        "fact_type": "release",
        "lineage_key": "lineage-main",
        "identity": {"variant": "sample"},
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
        "source_locator": "https://example.invalid/main",
        "verification_status": "verified",
    }
    ig_fact = dict(base_fact)
    ig_fact.update(
        {
            "lineage_key": "lineage-instagram",
            "source_role": "instagram_official_primary",
            "source_locator": "https://example.invalid/instagram",
        }
    )

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        main = root / "main.json"
        instagram = root / "instagram.json"
        runtime_main = root / "runtime-main.json"
        runtime_instagram = root / "runtime-instagram.json"
        report = root / "report.json"
        atomic_write_json(main, _sample_snapshot("MARKET_ANALYSIS", [base_fact]))
        atomic_write_json(instagram, _sample_snapshot("IG_CARDINFO", [ig_fact]))
        result = run_persisted_crosscheck(
            main_snapshot=main,
            instagram_snapshot=instagram,
            main_runtime=runtime_main,
            instagram_runtime=runtime_instagram,
            report=report,
        )
        assert result["operational_ready"] is True, result
        assert result["agree"] == 1 and result["conflict"] == 0, result

        conflict_fact = dict(ig_fact)
        conflict_fact["value"] = "2026-09-17"
        atomic_write_json(instagram, _sample_snapshot("IG_CARDINFO", [conflict_fact]))
        conflict = run_persisted_crosscheck(
            main_snapshot=main,
            instagram_snapshot=instagram,
            main_runtime=runtime_main,
            instagram_runtime=runtime_instagram,
            report=report,
        )
        assert conflict["conflict"] == 1, conflict
        assert conflict["reverification_required"] == 1, conflict

        runtime_main.write_text("stale", encoding="utf-8")
        runtime_instagram.write_text("stale", encoding="utf-8")
        instagram.unlink()
        missing = run_persisted_crosscheck(
            main_snapshot=main,
            instagram_snapshot=instagram,
            main_runtime=runtime_main,
            instagram_runtime=runtime_instagram,
            report=report,
        )
        assert missing["operational_ready"] is False, missing
        assert not runtime_main.exists() and not runtime_instagram.exists(), missing

    print("Persisted factual crosscheck runtime: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--main-snapshot", default=str(DEFAULT_MAIN_SNAPSHOT))
    parser.add_argument("--instagram-snapshot", default=str(DEFAULT_INSTAGRAM_SNAPSHOT))
    parser.add_argument("--main-runtime", default=str(DEFAULT_MAIN_RUNTIME))
    parser.add_argument("--instagram-runtime", default=str(DEFAULT_INSTAGRAM_RUNTIME))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--require-operational", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0

    result = run_persisted_crosscheck(
        main_snapshot=Path(args.main_snapshot),
        instagram_snapshot=Path(args.instagram_snapshot),
        main_runtime=Path(args.main_runtime),
        instagram_runtime=Path(args.instagram_runtime),
        report=Path(args.report),
    )
    print(json.dumps(result, ensure_ascii=False))
    if args.require_operational and not result.get("operational_ready"):
        return 2
    if result.get("status") == "validation_error":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
