"""Read-only timing diagnostics for historical sync-shard GitHub Actions logs.

Never runs git, rewrites a legacy test, alters timeouts or infers CI success
from a unittest "OK" marker. Use a downloaded job log and the independently
observed GitHub Actions conclusion to keep evidence layers separate.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re

MAX_LOG_BYTES = 4 * 1024 * 1024
DEFAULT_BUDGET_SECONDS = 600
DEFAULT_WARNING_SECONDS = 540
_EVENT = re.compile(
    r"^(?P<at>\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+Z) "
    r"(?P<test>test_[^\r\n]{1,350}?) \.\.\. "
    r"(?P<result>ok|FAIL|ERROR|skipped ['\"].*['\"])\s*$"
)
_SUITE = re.compile(r"\bRan (\d+) tests? in (\d+(?:\.\d+)?)s\b")
_OK = re.compile(r"^\d{4}-\d\d-\d\dT\S+ OK\s*$", re.MULTILINE)
_FAIL = re.compile(r"^\d{4}-\d\d-\d\dT\S+ FAILED(?:\s*\(.*\))?\s*$", re.MULTILINE)
_CANCEL = re.compile(r"\b(?:The operation was cancel(?:ed|led)|Job was cancel(?:ed|led))\b", re.IGNORECASE)
_RESULTS = frozenset(("success", "failure", "cancelled", "unknown"))


def _stamp(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def analyze(log: str, *, job_conclusion: str = "unknown",
            expected_tests: int = 191, warning_seconds: int = DEFAULT_WARNING_SECONDS,
            budget_seconds: int = DEFAULT_BUDGET_SECONDS) -> dict:
    """Report completion gaps, suite status and separately proven CI outcome.

    A completion gap is NOT a profiler-measured function duration: it includes
    overhead since the previous visible completed test.
    """
    if (not isinstance(log, str) or not isinstance(job_conclusion, str)
            or job_conclusion not in _RESULTS
            or type(expected_tests) is not int or expected_tests <= 0
            or type(warning_seconds) is not int or not 0 < warning_seconds < budget_seconds
            or type(budget_seconds) is not int or budget_seconds <= 0):
        raise ValueError("sync timing analysis arguments invalid")
    if len(log.encode("utf-8")) > MAX_LOG_BYTES:
        raise ValueError("sync log exceeds read-only size limit")
    gaps, previous = [], None
    completed, failed_cases = 0, 0
    for line in log.splitlines():
        m = _EVENT.match(line)
        if not m:
            continue
        at = _stamp(m["at"])
        if previous is not None:
            gap = (at - previous).total_seconds()
            if gap < 0:
                raise ValueError("sync timestamps out of order")
            gaps.append({"test": m["test"][:240], "completion_gap_seconds": round(gap, 3)})
        previous = at
        completed += 1
        failed_cases += m["result"] in ("FAIL", "ERROR")
    suites = _SUITE.findall(log)
    count, elapsed = (int(suites[-1][0]), float(suites[-1][1])) if suites else (None, None)
    cancelled = bool(_CANCEL.search(log)) or job_conclusion == "cancelled"
    python_status = ("FAILED" if failed_cases or _FAIL.search(log)
                     else "PASSED" if count == expected_tests and _OK.search(log)
                     else "INCOMPLETE")
    # A finished Python suite may still have a cancelled GitHub job.
    verified = bool(job_conclusion == "success" and python_status == "PASSED"
                    and not cancelled)
    largest = sorted(gaps, key=lambda g: (-g["completion_gap_seconds"], g["test"]))[:10]
    return {
        "schema_version": 928,
        "job_conclusion": job_conclusion,
        "workflow_success_verified": verified,
        "runner_cancelled": cancelled,
        "python_suite": python_status,
        "reported_test_count": count,
        "observed_completed_tests": completed,
        "expected_tests": expected_tests,
        "reported_suite_seconds": elapsed,
        "budget_seconds": budget_seconds,
        "headroom_seconds": round(budget_seconds - elapsed, 3) if elapsed is not None else None,
        "near_timeout": bool(elapsed is not None and elapsed >= warning_seconds),
        "longest_completion_gaps": largest,
        "top_four_gap_seconds": round(sum(x["completion_gap_seconds"] for x in largest[:4]), 3),
        "limitations": "Completion gaps include inter-test overhead; no function-level profiling or runtime speedup is implied.",
    }


def compare(reports: list[dict]) -> dict:
    if not 1 <= len(reports) <= 8:
        raise ValueError("expected one to eight sync job reports")
    samples = [r["reported_suite_seconds"] for r in reports
               if r["reported_suite_seconds"] is not None]
    return {
        "observed_runs": len(reports),
        "measured_suites": len(samples),
        "fastest_seconds": min(samples) if samples else None,
        "slowest_seconds": max(samples) if samples else None,
        "spread_seconds": round(max(samples) - min(samples), 3) if samples else None,
        "verified_successes": sum(r["workflow_success_verified"] for r in reports),
        "cancelled_jobs": sum(r["runner_cancelled"] for r in reports),
    }


def read_log(path: Path) -> str:
    """Do not follow a symlink or accept a directory / giant job log."""
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_LOG_BYTES:
        raise ValueError("sync log file must be regular, bounded and not a symlink")
    return path.read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only historical Sync job timing audit")
    parser.add_argument("logs", type=Path, nargs="+", help="up to eight downloaded job logs")
    parser.add_argument("--conclusion", choices=sorted(_RESULTS), default="unknown",
                        help="verified GitHub job conclusion; never inferred from unittest OK")
    parser.add_argument("--expected-tests", type=int, default=191)
    args = parser.parse_args(argv)
    if len(args.logs) > 8:
        parser.error("at most eight logs may be analyzed")
    reports = [analyze(read_log(path), job_conclusion=args.conclusion,
                       expected_tests=args.expected_tests) for path in args.logs]
    print(json.dumps({"runs": reports, "comparison": compare(reports)},
                     ensure_ascii=False, indent=2, sort_keys=True))
    return 0  # Diagnostic-only tool, never an automatic CI safety bypass.


if __name__ == "__main__":
    raise SystemExit(main())
