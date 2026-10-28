#!/usr/bin/env python3
"""Validate curated TCG findings and carry unresolved issues across 100-V windows.

A signed/hashed window inventory is NOT code verification; this ledger is also
not an approval, a grade, a successor or a physical tablet receipt.
No source writes, network, runtime imports, device access or workflow dispatch.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

SCHEMA = "tcg-version-finding-continuity/v1"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
IDS = re.compile(r"^W(?:001|101|201|301|401|501|601|701|801)-F[0-9]{3}$")
ALLOWED = {
    "HOLD_PROVENANCE", "HOLD_CANDIDATE", "HOLD_REPLAY_RESTRICTION",
    "HISTORICAL_REPAIR_PRESERVED",
}
TYPES = {
    "PROVENANCE_GAP", "CURRENT_CANDIDATE_BEHAVIOR_DEFECT",
    "HISTORICAL_BEHAVIOR_DEFECT", "HISTORICAL_REPLAY_SAFETY",
}


def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for k, v in pairs:
        if k in obj:
            raise ValueError("duplicate_json_key")
        obj[k] = v
    return obj


def load(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 100_000:
        raise ValueError("unsafe_findings_source")
    data = json.loads(path.read_text("utf-8"), object_pairs_hook=unique,
                      parse_constant=lambda _v: (_ for _ in ()).throw(
                          ValueError("non_finite_json")))
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise ValueError("wrong_findings_schema")
    return data


def validate(data: dict[str, Any], *, current_version: int) -> list[dict[str, Any]]:
    if type(current_version) is not int or not 1 <= current_version <= 9999:
        raise ValueError("invalid_version_limit")
    if (not isinstance(data, dict) or data.get("schema") != SCHEMA
            or data.get("latest_feature_candidate") != current_version
            or data.get("grading_policy") != "NOT_SCORED_WITHOUT_EXACT_SOURCE_TEST_AND_DEVICE_GATES"
            or data.get("device_verified") is not False):
        raise ValueError("unsupported_release_or_device_claim")
    root = data.get("base_main_sha")
    if not isinstance(root, str) or HEX40.fullmatch(root) is None:
        raise ValueError("unverified_base_format")
    records = data.get("findings")
    if not isinstance(records, list):
        raise ValueError("findings_not_array")
    ids: set[str] = set()
    for row in records:
        if not isinstance(row, dict):
            raise ValueError("malformed_finding")
        identity = row.get("id")
        if not isinstance(identity, str) or IDS.fullmatch(identity) is None or identity in ids:
            raise ValueError("invalid_or_duplicate_finding_id")
        ids.add(identity)
        opened, resolved = row.get("opened_at"), row.get("resolved_in")
        if type(opened) is not int or not 1 <= opened <= current_version:
            raise ValueError("invalid_opened_version")
        first = ((opened - 1) // 100) * 100 + 1
        if int(identity[1:4]) != first:
            raise ValueError("finding_id_wrong_window")
        if resolved is not None and (type(resolved) is not int
                                     or not opened <= resolved <= current_version):
            raise ValueError("invalid_resolution_version")
        state = row.get("state")
        if state not in ALLOWED or row.get("type") not in TYPES or row.get("severity") not in {"P0", "P1", "P2"}:
            raise ValueError("invalid_finding_state")
        if (state == "HISTORICAL_REPAIR_PRESERVED") != (resolved is not None):
            raise ValueError("resolution_state_contradiction")
        if row.get("score") is not None or row.get("device_verified") is not False:
            raise ValueError("finding_claims_unverified_quality_or_device")
        related = row.get("related_versions")
        if (not isinstance(related, list) or not related
                or any(type(v) is not int or not 1 <= v <= current_version for v in related)
                or related != sorted(set(related))):
            raise ValueError("invalid_related_versions")
        for field in ("source_paths", "source_commits"):
            if not isinstance(row.get(field), list):
                raise ValueError("missing_source_evidence_collection")
        for sha in row["source_commits"]:
            if not isinstance(sha, str) or HEX40.fullmatch(sha) is None:
                raise ValueError("invalid_evidence_sha")
        if not isinstance(row.get("explanation"), str) or len(row["explanation"]) < 30:
            raise ValueError("missing_finding_rationale")
        if (row.get("candidate_pr") is not None and
                (type(row["candidate_pr"]) is not int or row["candidate_pr"] < 1)):
            raise ValueError("invalid_candidate_pr")
    return sorted(records, key=lambda r: (r["opened_at"], r["id"]))


def build(data: dict[str, Any], *, current_version: int = 879) -> dict[str, Any]:
    findings = validate(data, current_version=current_version)
    results = []
    for first in range(1, current_version + 1, 100):
        last = min(first + 99, current_version)
        open_ids = sorted(row["id"] for row in findings
                          if row["opened_at"] <= last
                          and (row["resolved_in"] is None or row["resolved_in"] > last))
        closed_ids = sorted(row["id"] for row in findings
                            if row["resolved_in"] is not None
                            and first <= row["resolved_in"] <= last)
        results.append({
            "first": first, "last": last,
            "unresolved_carry_forward": open_ids,
            "historical_resolutions_in_window": closed_ids,
            "quality_score": None, "device_verified": False,
            "status": "REVIEW_FINDINGS_NOT_RELEASE_APPROVAL",
        })
    return {
        "schema": "tcg-version-finding-handoffs/v1",
        "source_main_sha": data["base_main_sha"],
        "current_version": current_version,
        "windows": results,
        "total_findings": len(findings),
        "open_at_latest": results[-1]["unresolved_carry_forward"],
        "quality_score": None,
        "physical_tablet_verified": False,
        "status": "UNRESOLVED_REVIEW_GAPS_HOLD",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path)
    parser.add_argument("--end-version", type=int, default=879)
    args = parser.parse_args()
    try:
        result = build(load(args.ledger), current_version=args.end_version)
    except (ValueError, OSError, UnicodeError) as exc:
        print(json.dumps({"status": "HOLD", "reason": str(exc)[:160]}))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
