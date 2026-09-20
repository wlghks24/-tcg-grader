#!/usr/bin/env python3
"""Tablet collection publisher with transaction-aware freshness verification."""
from __future__ import annotations

import json
import subprocess
import sys

import tablet_collection_publish as core


def gates(root):
    core.run([
        sys.executable, "static_data_publish_gate.py",
        "--max-social-age-hours", "12",
        "--max-report-age-hours", "2",
        "--report", "STATIC_DATA_PUBLISH_REPORT.json",
    ], root)
    core.run([
        sys.executable, "collection_verification_gate_contextual.py",
        "--max-health-age-seconds", "900",
        "--fail-on-degraded",
        "--report", "COLLECTION_VERIFICATION_REPORT.json",
    ], root)
    core.run([
        sys.executable, "-c",
        "import json,auto_update_all; auto_update_all.validate_json('grading_company_updates.json',json.load(open('grading_company_updates.json',encoding='utf-8')))"
    ], root)


def main() -> int:
    core.gates = gates
    return core.main()


if __name__ == "__main__":
    raise SystemExit(main())
