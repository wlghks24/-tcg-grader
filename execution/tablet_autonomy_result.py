"""Classify an actual scheduled controller result; never authorize execution."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

MAX_FINAL_LINE_BYTES = 8 * 1024 * 1024


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError("non-finite JSON constant")


def read_final_result(path: Path) -> dict:
    """Read only a bounded tail and require the last nonempty line to be JSON."""
    if path.is_symlink() or not path.is_file():
        raise ValueError("not a regular local log")
    with path.open("rb") as stream:
        stream.seek(0, 2)
        size = stream.tell()
        start = max(0, size - MAX_FINAL_LINE_BYTES - 1)
        stream.seek(start)
        data = stream.read(MAX_FINAL_LINE_BYTES + 1)
    if start:
        _, separator, data = data.partition(b"\n")
        if not separator:
            raise ValueError("final result exceeds limit")
    lines = data.splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines or len(lines[-1]) > MAX_FINAL_LINE_BYTES:
        raise ValueError("missing or oversized final result")
    result = json.loads(lines[-1].decode("utf-8"), object_pairs_hook=_unique_object,
                        parse_constant=_invalid_constant)
    if not isinstance(result, dict):
        raise ValueError("final result is not an object")
    return result


def is_policy_hold(exit_code: int, result: dict, hold_statuses: set[str]) -> bool:
    if exit_code != 2 or result.get("controller_version") != "v400":
        return False
    status = result.get("v400_status")
    if not isinstance(status, str) or status not in hold_statuses:
        return False
    execution = result.get("execution")
    if not isinstance(execution, dict) or execution.get("status") != status:
        return False
    if execution.get("executed") is not False:
        return False
    if execution.get("git_write") is not False or execution.get("source_code_modified") is not False:
        return False
    if execution.get("proposals_executed", False) is not False:
        return False
    gate = result.get("v400_autonomous_gate")
    # The lock-contention return is intentionally earlier than gate construction.
    if status == "V400_CONCURRENT_AUTONOMY_HOLD" and gate is None:
        return True
    return (isinstance(gate, dict) and gate.get("status") == status
            and gate.get("allow_execution") is False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--exit-code", type=int, required=True)
    args = parser.parse_args()
    if args.exit_code != 2:
        return 1
    try:
        result = read_final_result(args.log)
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        import tablet_autonomous_evolution_v400 as controller
        return 0 if is_policy_hold(args.exit_code, result, controller._HOLD_STATUSES) else 1
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError, ImportError):
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
