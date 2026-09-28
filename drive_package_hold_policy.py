#!/usr/bin/env python3
"""Classify collection verification failures that are safe to hold without upload.

This helper does not make degraded data publishable.  It is intentionally narrow:
only externally attributable provider/network degradation may convert a Drive package
job from hard failure to an explicit HOLD.  All stale, invalid, unknown, or critical
findings remain hard failures and the package upload step stays disabled.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

_EXTERNAL_ERROR_RE = re.compile(
    r"(?:"
    r"HTTPError:\s*status\s*(?:403|408|425|429|451|500|502|503|504)\b|"
    r"URLError|TimeoutError|IncompleteRead|RemoteDisconnected|HTTPException|"
    r"timed out|connection reset|name resolution|\bDNS\b|MaintenanceRedirect"
    r")",
    re.IGNORECASE,
)
_ALLOWED_FAILURE_CLASSES = {"planned_maintenance"}
_ALLOWED_HIGH_CODES = {
    "GRADING_COMPANY_NO_HEALTHY_SOURCE",
    "DEGRADED_COLLECTION_OUTPUT",
}


def _external_error(value: Any) -> bool:
    return bool(_EXTERNAL_ERROR_RE.search(str(value or "")))


def _grading_company_hold(finding: dict[str, Any]) -> bool:
    companies = finding.get("companies")
    samples_by_company = finding.get("degraded_samples_by_company")
    if not isinstance(companies, list) or not companies or not isinstance(samples_by_company, dict):
        return False
    for company in companies:
        rows = samples_by_company.get(company)
        if not isinstance(rows, list) or not rows:
            return False
        for row in rows:
            if not isinstance(row, dict):
                return False
            failure_class = str(row.get("failure_class") or "")
            if failure_class in _ALLOWED_FAILURE_CLASSES:
                continue
            if not _external_error(row.get("error")):
                return False
    return True


def _degraded_output_hold(finding: dict[str, Any]) -> bool:
    errors = finding.get("errors")
    if not isinstance(errors, list) or not errors:
        return False
    return all(_external_error(error) for error in errors)


def is_external_provider_hold(report: Any) -> bool:
    """Return True only for a fully evidenced external-degradation HOLD."""
    if not isinstance(report, dict) or report.get("status") != "degraded":
        return False
    counts = report.get("counts")
    findings = report.get("findings")
    if not isinstance(counts, dict) or not isinstance(findings, list):
        return False
    try:
        critical = int(counts.get("critical", 0))
        high_count = int(counts.get("high", 0))
    except (TypeError, ValueError, OverflowError):
        return False
    if critical != 0 or high_count <= 0:
        return False

    high_findings = [
        row for row in findings
        if isinstance(row, dict) and row.get("severity") == "high"
    ]
    if len(high_findings) != high_count:
        return False

    for finding in high_findings:
        code = finding.get("code")
        if code not in _ALLOWED_HIGH_CODES:
            return False
        if code == "GRADING_COMPANY_NO_HEALTHY_SOURCE":
            if not _grading_company_hold(finding):
                return False
        elif code == "DEGRADED_COLLECTION_OUTPUT":
            if not _degraded_output_hold(finding):
                return False
        else:  # pragma: no cover - defensive against future refactors
            return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", nargs="?", default="COLLECTION_VERIFICATION_REPORT.json")
    args = parser.parse_args()
    try:
        report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return 2
    if not is_external_provider_hold(report):
        return 1
    print(json.dumps({
        "status": "HOLD",
        "reason": "EXTERNAL_PROVIDER_DEGRADED_HOLD",
        "package_ready": False,
        "upload_allowed": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
