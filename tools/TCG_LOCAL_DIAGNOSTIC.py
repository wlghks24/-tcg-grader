#!/usr/bin/env python3
"""Read-only tablet diagnostics: no network, update, restart, or candidate edits."""
import argparse
import ast
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

FILES = ("social_event_discovery.py", "multi_route_event_discovery.py", "event_collection_hardening_v140.py")

def command(argv, root, timeout=12):
    try:
        p = subprocess.run(argv, cwd=root, text=True, capture_output=True, timeout=timeout, check=False)
        return {"returncode": p.returncode, "stdout": p.stdout[-3000:], "stderr": p.stderr[-2000:]}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": type(exc).__name__, "detail": str(exc)[:200]}

def diagnose(root, tests=False):
    report = {"schema_version": 1, "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "mode": "read_only", "files": {}}
    for name in FILES:
        path = root / name
        result = {"exists": path.is_file()}
        if path.is_file():
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=name)
                result["syntax"] = "PASS"
            except (OSError, UnicodeError, SyntaxError) as exc:
                result.update(syntax="FAIL", error=f"{type(exc).__name__}: {str(exc)[:160]}")
        report["files"][name] = result
    report["git_head"] = command(["git", "rev-parse", "HEAD"], root)
    report["git_status"] = command(["git", "status", "--short"], root)
    report["git_diff_check"] = command(["git", "diff", "--check"], root)
    path = root / "social_event_candidates.json"
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            report["candidates"] = {"item_count": data.get("item_count"), "updated_at": data.get("updated_at")}
            report["channels"] = {
                name: {key: status.get(key) for key in ("attempted_query_count", "success_query_count", "error_count", "result_count")}
                for name, status in (data.get("channel_status") or {}).items() if isinstance(status, dict)
            }
        except (OSError, UnicodeError, ValueError) as exc:
            report["candidates"] = {"error": type(exc).__name__}
    if tests:
        report["tests"] = command([sys.executable, "-m", "unittest", "test_multi_route_event_discovery", "-q"], root, timeout=90)
    return report

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, help="Optional local JSON report file")
    parser.add_argument("--tests", action="store_true", help="Run offline regression tests")
    args = parser.parse_args()
    root = args.root.resolve()
    if not (root / FILES[0]).is_file():
        parser.error("Not a TCG Grader source directory")
    report = diagnose(root, args.tests)
    report["run_id"] = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + str(os.getpid())
    payload = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.output:
        target = args.output.expanduser().resolve()
        if target == Path(__file__).resolve() or target == (root / "social_event_candidates.json") or target == (root / "integrity_manifest.json") or target.name in FILES:
            parser.error("Refusing to overwrite protected source or candidate data")
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(target.name + ".tmp-" + str(os.getpid()))
        try:
            temp.write_text(payload, encoding="utf-8")
            os.replace(temp, target)
            readback = target.read_bytes()
            if hashlib.sha256(readback).hexdigest() != hashlib.sha256(payload.encode("utf-8")).hexdigest():
                raise OSError("JSON report readback SHA256 mismatch")
            parsed = json.loads(readback)
            if parsed.get("schema_version") != 1 or parsed.get("run_id") != report["run_id"] or parsed.get("mode") != "read_only":
                raise ValueError("JSON report schema/readback mismatch")
        finally:
            temp.unlink(missing_ok=True)
    print(payload, end="")

if __name__ == "__main__":
    main()
