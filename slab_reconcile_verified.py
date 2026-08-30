#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reconcile an existing slab OCR manifest against the official registry.

No image OCR is performed. This lets large tablet scans be reused after the
verification registry grows. A slab row becomes verified only when company,
certification number and OCR label grade all match an official registry row.
Rows with missing/conflicting OCR grades stay quarantined.
"""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def registry_map(payload: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in payload.get("certifications", []):
        if not isinstance(row, dict) or row.get("officially_verified") is not True:
            continue
        company = str(row.get("company") or "").upper()
        cert = str(row.get("certification_id") or "")
        if company and cert and row.get("grade") is not None:
            out[(company, cert)] = row
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--registry", type=Path, default=Path("library_official_cert_registry.json"))
    parser.add_argument("--output", type=Path, default=Path("slab_full_reconciled.json"))
    parser.add_argument("--verified", type=Path, default=Path("slab_full_reconciled_verified.json"))
    args = parser.parse_args()

    manifest = load_json(args.manifest)
    registry_payload = load_json(args.registry)
    registry = registry_map(registry_payload)
    records = manifest.get("records", []) if isinstance(manifest, dict) else []
    if not isinstance(records, list):
        raise SystemExit("manifest records must be a list")

    verified_refs: list[dict[str, Any]] = []
    emitted: set[tuple[str, str]] = set()
    outcomes: Counter[str] = Counter()

    for row in records:
        if not isinstance(row, dict):
            continue
        company = str(row.get("company") or "").upper()
        cert = str(row.get("certification_id") or "")
        grade = row.get("label_grade")
        reg = registry.get((company, cert)) if company and cert else None

        reasons = set(row.get("quarantine_reasons") or [])
        reasons.discard("official_lookup_not_confirmed")
        reasons.discard("official_grade_conflict")

        if reg is None:
            row["official_result"] = False
            row["status"] = "quarantine"
            if company and cert:
                reasons.add("official_lookup_not_confirmed")
                outcomes["official_lookup_not_confirmed"] += 1
            else:
                outcomes["missing_company_or_cert"] += 1
        elif grade is None:
            row["official_result"] = False
            row["status"] = "quarantine"
            reasons.add("grade_unresolved")
            outcomes["official_found_grade_unresolved"] += 1
        elif abs(float(reg.get("grade")) - float(grade)) > 1e-9:
            row["official_result"] = False
            row["status"] = "quarantine"
            reasons.add("official_grade_conflict")
            outcomes["official_grade_conflict"] += 1
        else:
            row["official_result"] = True
            row["status"] = "verified"
            row["official_reference_url"] = reg.get("official_reference_url")
            row["learning_eligibility"] = "reference_only_missing_raw_prediction"
            row["training_eligible"] = False
            outcomes["verified_match"] += 1
            key = (company, cert)
            if key not in emitted:
                verified_refs.append({
                    "company": company,
                    "certification_id": cert,
                    "official_grade": float(reg["grade"]),
                    "card_name": reg.get("card_name"),
                    "game": reg.get("game", "unknown"),
                    "mode": "slab",
                    "official_result": True,
                    "official_reference_url": reg.get("official_reference_url"),
                    "source_sha256": row.get("sha256"),
                    "source_name": row.get("source_name"),
                    "learning_eligibility": "reference_only_missing_raw_prediction",
                })
                emitted.add(key)

        row["quarantine_reasons"] = sorted(reasons)

    manifest["reconciled_at"] = utc_now()
    manifest["reconciled_registry_entries"] = len(registry)
    summary = manifest.setdefault("summary", {})
    summary["officially_verified_certifications"] = len(verified_refs)
    summary["verified_files"] = sum(
        1 for row in records if isinstance(row, dict) and row.get("status") == "verified"
    )
    summary["quarantined_files"] = sum(
        1 for row in records if isinstance(row, dict) and row.get("status") == "quarantine"
    )
    summary["reconcile_outcomes"] = dict(sorted(outcomes.items()))

    verified_payload = {
        "schema_version": 3,
        "created_at": utc_now(),
        "certifications": verified_refs,
        "training_rows_written": 0,
        "reason": (
            "Officially verified slab references are kept separate from raw-camera "
            "calibration to prevent target leakage."
        ),
    }
    atomic_write_json(args.output, manifest)
    atomic_write_json(args.verified, verified_payload)
    print(json.dumps({
        "registry_entries": len(registry),
        "verified_certifications": len(verified_refs),
        "verified_files": summary["verified_files"],
        "quarantined_files": summary["quarantined_files"],
        "outcomes": dict(sorted(outcomes.items())),
    }, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
