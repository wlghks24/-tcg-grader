#!/usr/bin/env python3
"""Read-only forensic checks for the original V101–V109 *report claims*.

An historical report's ok=true is not a current source or physical-tablet PASS.
Pinned protected-main Git blobs are parsed without running legacy verify scripts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

BASE = "6c78831bbb6e188717f86ef90243a836d2e0b67a"
REPORT_BLOBS = {
    101: "9b0059f1c32b322fb821e97dd73d27252c93cda1",
    102: "db0c6abf670153294ff2ace62c2923139daddcab",
    103: "276c658c465a9c5ae0c5d29239a59a70ad0f10e8",
    104: "975248a440cddb3e4c28500aadf03c1a1b910337",
    105: "02f25155d0671ede2cc852fc7e50f517eae63c18",
    106: "84db3640e8229da0d1894b59586aba4709538f7a",
    107: "707c9da06238ac5b58e283bec5b089ebb442db07",
    108: "681d27628f108704618e097bcc31fdf439421fef",
    109: "71b07e9bc8fed76890f54f0a78047c4cfe3cb2f",
}


def git(root: Path, *args: str) -> bytes:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True,
                            check=False, timeout=40)
    if result.returncode:
        raise ValueError("git_forensic_evidence_unavailable")
    return result.stdout


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate_historical_report_key")
        out[key] = value
    return out


def _parse(raw: bytes) -> dict[str, Any]:
    if len(raw) > 100_000:
        raise ValueError("historical_report_oversized")
    obj = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=_unique,
                     parse_constant=lambda _: (_ for _ in ()).throw(
                         ValueError("historical_report_nonfinite")))
    if not isinstance(obj, dict):
        raise ValueError("historical_report_not_object")
    return obj


def _blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def _check(name: str, condition: bool) -> None:
    if not condition:
        raise ValueError("historical_report_inconsistent:" + name)


def analyze(data: dict[int, dict[str, Any]]) -> dict[str, Any]:
    _check("missing_versions", set(data) == set(REPORT_BLOBS))
    for version in sorted(data):
        record = data[version]
        _check(f"v{version}_object", isinstance(record, dict))
        build = str(record.get("build") or record.get("version") or "")
        _check(f"v{version}_marker", re.search(
            rf"(?<![a-z0-9])v{version}(?![0-9])", build, re.I) is not None)
        _check(f"v{version}_historical_ok", record.get("ok") is True)
    v101 = data[101]
    checks = v101.get("checks")
    _check("v101_checks", isinstance(checks, list))
    vision = next((row for row in checks
                   if isinstance(row, dict)
                   and row.get("name") == "v101_vision_self_learning"), None)
    _check("v101_vision_report", isinstance(vision, dict))
    metrics = _parse(str(vision["detail"]).encode("utf-8"))
    _check("v101_small_counts", metrics.get("metrics", {}).get("counts", {}).get("tp") == 12
           and metrics["metrics"]["counts"].get("tn") == 24)
    _check("v101_calibration_adopted", metrics.get("calibration_adopted") is False)

    v104 = data[104]
    _check("v104_not_digital_deblur", "not digital deblurring" in
           str(v104.get("note", "")).lower())

    for version in (105, 106, 107):
        note = str(data[version].get("live_credential_note", ""))
        _check(f"v{version}_live_not_executed",
               ("not executed" in note.lower()
                and ("mock" in note.lower() or "deterministic tests" in note.lower())))
    for version in (106, 107):
        _check(f"v{version}_not_published",
               "not been pushed" in str(data[version].get("deployment_note", "")).lower())

    v108 = data[108]
    checks108 = v108.get("checks")
    _check("v108_check_array", isinstance(checks108, list))
    evidence_rows = []
    for row in checks108:
        if not isinstance(row, dict):
            continue
        detail = row.get("detail")
        if isinstance(detail, str) and '"officially_verified_certifications"' in detail:
            evidence_rows.append(_parse(detail.encode("utf-8")))
    _check("v108_unique_summary", len(evidence_rows) == 1)
    scanned = evidence_rows[0].get("summary")
    _check("v108_summary_object", isinstance(scanned, dict))
    count = {
        "files_scanned": scanned.get("files_scanned"),
        "officially_verified_certifications": scanned.get("officially_verified_certifications"),
        "quarantined_files": scanned.get("quarantined_files"),
        "training_rows_written": evidence_rows[0].get("training_rows_written"),
    }
    _check("v108_count_exact_types", all(type(value) is int for value in count.values()))
    _check("v108_count_invariants", count["files_scanned"] == 200
           and count["officially_verified_certifications"] == 1
           and count["quarantined_files"] == 199
           and count["training_rows_written"] == 0)

    v109policy = data[109].get("policy")
    _check("v109_policy", isinstance(v109policy, dict)
           and v109policy.get("automatic_ocr_predictions_train") is False
           and v109policy.get("user_confirmation_required") is True
           and v109policy.get("raw_slab_grade_learning_isolated") is True)
    return {
        "schema": "tcg-historical-v101-v109-forensics/v1",
        "protected_base": BASE,
        "reviewed_historical_report_count": 9,
        "v101": {"synthetic_positive": 12, "synthetic_negative": 24,
                 "calibration_adopted": False, "real_photo_accuracy_verified": False},
        "v104": {"hardware_camera_verified": False,
                 "claim": "CAPTURE_GATING_NOT_DIGITAL_DEBLURRING"},
        "v105_v107": {"real_social_credentials_exercised": False,
                      "deterministic_mock_evidence_only": True,
                      "v106_v107_published": False},
        "v108": {**count, "verified_is_not_training": True},
        "v109": {"automatic_ocr_predictions_train": False,
                 "user_confirmation_required": True},
        "current_head_tests_per_version": "NOT_EXECUTED_BY_FORENSIC_TOOL",
        "complete_code_reviews": 0,
        "quality_score": None,
        "device": "DEVICE_UNVERIFIED",
        "status": "HISTORICAL_REPORT_EVIDENCE_ONLY_NOT_RELEASE_VERIFIED",
    }


def inspect(root: Path) -> dict[str, Any]:
    root = root.resolve()
    git(root, "merge-base", "--is-ancestor", BASE, "HEAD")
    evidence: dict[int, dict[str, Any]] = {}
    for version, expected in REPORT_BLOBS.items():
        path = f"V{version}_FINAL_VERIFICATION_REPORT.json"
        raw = git(root, "show", f"{BASE}:{path}")
        if _blob(raw) != expected:
            raise ValueError("pinned_historical_report_blob_changed:" + path)
        evidence[version] = _parse(raw)
    return analyze(evidence)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = ap.parse_args()
    try:
        obj = inspect(args.root)
    except (OSError, UnicodeError, ValueError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "HOLD", "reason": str(exc)[:160]}))
        return 2
    print(json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
