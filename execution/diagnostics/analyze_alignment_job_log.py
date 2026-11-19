"""Offline, read-only evidence parser for timed-out Main Alignment jobs.

Usage: python -m execution.diagnostics.analyze_alignment_job_log JOB.log
Completion gaps are *upper bounds on elapsed time since the preceding
reported test*, not measurements made at test entry/exit.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re

MAX_LOG_BYTES = 8 * 1024 * 1024
STAMP = re.compile(r'^\ufeff?(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z)\s+(.*)$')
TEST = re.compile(r'(test_[A-Za-z0-9_]+) \(([\w.]+)\) \.\.\. (ok|FAIL|ERROR|skipped(?: [^\r\n]*)?)\s*$')


def analyze_log(contents: str, *, top: int = 5) -> dict:
    """Summarize GitHub runner log evidence, without running any test or Git command."""
    if not isinstance(contents, str) or not 1 <= top <= 50:
        raise ValueError('invalid log or top limit')
    previous = None
    start = None
    end = None
    cancelled = False
    failures = 0
    completed = 0
    gaps = []
    for line in contents.splitlines():
        match = STAMP.match(line)
        if not match:
            continue
        try:
            stamp = datetime.fromisoformat(match.group(1).replace('Z', '+00:00'))
        except ValueError:
            continue
        payload = match.group(2)
        if '##[group]Run set -euo pipefail' in payload:
            start = stamp
        if '##[error]The operation was canceled.' in payload:
            cancelled = True
            end = stamp
        result = TEST.search(payload)
        if result is None:
            continue
        method, module, outcome = result.groups()
        completed += 1
        if outcome in ('FAIL', 'ERROR'):
            failures += 1
        if previous is not None:
            seconds = (stamp - previous).total_seconds()
            if seconds >= 1:
                gaps.append({'test': module + '.' + method,
                             'completion_gap_seconds': round(seconds, 3),
                             'outcome': outcome})
        previous = stamp
    gaps.sort(key=lambda row: row['completion_gap_seconds'], reverse=True)
    elapsed = (end - start).total_seconds() if start is not None and end is not None else None
    return {
        'status': 'cancelled' if cancelled else ('test_failure' if failures else 'incomplete_or_unknown'),
        'cancelled': cancelled,
        'completed_test_results': completed,
        'failed_test_results': failures,
        'step_to_cancellation_seconds': round(elapsed, 3) if elapsed is not None else None,
        'largest_completion_gaps': gaps[:top],
        'interpretation': 'Gaps between test result timestamps; not direct method runtime measurements',
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', type=Path, help='Existing local GitHub Actions text log')
    parser.add_argument('--top', type=int, default=5)
    args = parser.parse_args(argv)
    if not 1 <= args.top <= 50:
        parser.error('--top must be between 1 and 50')
    try:
        if not args.file.is_file() or args.file.stat().st_size > MAX_LOG_BYTES:
            raise ValueError('missing or oversized log')
        contents = args.file.read_text(encoding='utf-8-sig')
        result = analyze_log(contents, top=args.top)
    except (OSError, UnicodeError, ValueError) as error:
        parser.error(f'invalid log input: {error}')
    print(json.dumps(result, sort_keys=True, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
