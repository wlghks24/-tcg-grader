#!/usr/bin/env python3
"""Read-only classifier for the scheduled Tablet GPT V400 fail-closed result.

No fabricated learning evidence, confidence adjustment, model or source writes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

MAX_LOG_BYTES = 8_000_000
BOOTSTRAP_FILES = (
    "tablet_autonomy_verified_outcomes.jsonl",
    "tablet_autonomy_skills_v374.json",
    "tablet_autonomy_verified_skill_outcomes_v374.jsonl",
    "crosscheck_exchange/tcg-grader-autonomy-summary.json",
)


def _absent_safe(path: Path) -> bool:
    return not path.is_symlink() and not path.exists()


def classify(root: Path, log: Path) -> str:
    """Conservative output: BOOTSTRAP_EVIDENCE_HOLD, VERIFIED_UPSTREAM_HOLD or FAILED."""
    try:
        if log.is_symlink() or not log.is_file() or log.stat().st_size > MAX_LOG_BYTES:
            return "FAILED"
        lines = log.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError, ValueError):
        return "FAILED"
    report = None
    for line in reversed(lines[-20:]):
        if not line.startswith("{"):
            continue
        try:
            value = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict) and "v400_status" in value:
            report = value
            break
    if not isinstance(report, dict):
        return "FAILED"
    execution = report.get("execution")
    v400 = report.get("v400_autonomous_gate")
    v387 = report.get("v387_autonomous_gate")
    if not isinstance(execution, dict) or not isinstance(v400, dict):
        return "FAILED"
    if (execution.get("executed") is not False
            or execution.get("git_write") is not False
            or execution.get("source_code_modified") is not False
            or v400.get("allow_execution") is not False):
        return "FAILED"
    if not str(report.get("v400_status") or "").endswith("_HOLD"):
        return "FAILED"
    if (report["v400_status"] == "V400_UPSTREAM_HOLD"
            and isinstance(v387, dict)
            and v387.get("status") == "V387_UNCERTAINTY_HOLD"
            and v387.get("allow_execution") is False
            and set(v387.get("reasons") or ()) == {
                "LOW_VERIFIED_CONFIDENCE", "HIGH_UNCERTAINTY"
            }
            and all(_absent_safe(root / item) for item in BOOTSTRAP_FILES)):
        return "BOOTSTRAP_EVIDENCE_HOLD"
    return "VERIFIED_UPSTREAM_HOLD"


def main() -> int:
    if len(sys.argv) != 3:
        return 2
    root = Path(sys.argv[1])
    log = Path(sys.argv[2])
    print(classify(root, log))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
