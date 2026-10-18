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
            if not isinstance(data, dict):
                raise ValueError("Candidates JSON root must be an object")
            report["candidates"] = {"item_count": data.get("item_count"), "updated_at": data.get("updated_at")}
            channels = data.get("channel_status", {})
            if channels is None:
                channels = {}
            if not isinstance(channels, dict):
                raise ValueError("channel_status must be an object")
            if any(not isinstance(name, str) or not isinstance(status, dict) for name, status in channels.items()):
                raise ValueError("channel_status entries must be named objects")
            report["channels"] = {
                name: {key: status.get(key) for key in ("attempted_query_count", "success_query_count", "error_count", "result_count")}
                for name, status in channels.items()
            }
        except (OSError, UnicodeError, ValueError) as exc:
            report["candidates"] = {"error": type(exc).__name__}
    if tests:
        report["tests"] = command([sys.executable, "-m", "unittest", "test_multi_route_event_discovery", "-q"], root, timeout=90)
        report["tests"]["passed"] = report["tests"].get("returncode") == 0
    return report

def atomic_bytes(target, data):
    import tempfile
    fd, temporary = tempfile.mkstemp(prefix=target.name + ".tmp-", dir=str(target.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, help="Optional local JSON report file")
    parser.add_argument("--tests", action="store_true", help="Run offline regression tests")
    parser.add_argument("--self-test", action="store_true", help="Run isolated diagnostic safety regression tests")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.self_test:
        import tempfile
        with tempfile.TemporaryDirectory(prefix="tcg-diag-test-") as folder:
            sandbox = Path(folder)
            for name in FILES:
                (sandbox / name).write_text("x = 1\n", encoding="utf-8")
            first = diagnose(sandbox)
            if not all(x.get("syntax") == "PASS" for x in first["files"].values()):
                raise RuntimeError("Expected valid syntax")
            (sandbox / FILES[0]).write_text("def broken(:\n", encoding="utf-8")
            second = diagnose(sandbox)
            if second["files"][FILES[0]]["syntax"] != "FAIL":
                raise RuntimeError("Expected syntax failure")
            target = sandbox / "receipt.json"
            atomic_bytes(target, json.dumps({"schema_version": 1}).encode("utf-8"))
            if json.loads(target.read_bytes())["schema_version"] != 1:
                raise RuntimeError("Atomic write readback failed")
            if list(sandbox.glob("receipt.json.tmp-*")):
                raise RuntimeError("Temporary files leaked")
            (sandbox / "social_event_candidates.json").write_text("[]", encoding="utf-8")
            malformed = diagnose(sandbox)
            if malformed["candidates"].get("error") != "ValueError":
                raise RuntimeError("Malformed candidates root was not rejected")
            (sandbox / "social_event_candidates.json").write_text(json.dumps({"channel_status": []}), encoding="utf-8")
            malformed_channels = diagnose(sandbox)
            if malformed_channels["candidates"].get("error") != "ValueError":
                raise RuntimeError("Malformed channel status was not rejected")
            (sandbox / "social_event_candidates.json").write_text(json.dumps({"channel_status": {"broken": []}}), encoding="utf-8")
            malformed_entry = diagnose(sandbox)
            if malformed_entry["candidates"].get("error") != "ValueError":
                raise RuntimeError("Malformed channel entry was not rejected")
        print("DIAGNOSTIC_SELF_TEST_PASS")
        return
    if not (root / FILES[0]).is_file():
        parser.error("Not a TCG Grader source directory")
    report = diagnose(root, args.tests)
    report["run_id"] = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + str(os.getpid())
    payload = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.output:
        requested = args.output.expanduser().absolute()
        if requested.is_symlink() or requested.with_name(requested.name + ".last-good").is_symlink():
            parser.error("Refusing diagnostic symlink output")
        target = requested.resolve()
        if requested != target:
            parser.error("Refusing diagnostic output through symlinked parent")
        if target.is_dir():
            parser.error("Diagnostic output must be a file")
        if target.is_relative_to(root) and (target.suffix.lower() != ".json" or target.name != "TCG_LOCAL_DIAGNOSTIC_REPORT.json"):
            parser.error("Repository output restricted to TCG_LOCAL_DIAGNOSTIC_REPORT.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        lock = target.with_name(target.name + ".lock")
        if lock.is_symlink():
            parser.error("Refusing symlink lock")
        try:
            lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            parser.error("DIAGNOSTIC_ALREADY_RUNNING: inspect existing lock manually")
        lock_owner = os.fstat(lock_fd).st_ino
        try:
            with os.fdopen(lock_fd, "w") as stream:
                stream.write(str(os.getpid()) + "\n")
            if target.is_symlink() or target.with_name(target.name + ".last-good").is_symlink():
                raise ValueError("Diagnostic output changed to symlink")
            if target.exists():
                previous = target.read_bytes()
                prior = json.loads(previous)
                if not isinstance(prior, dict) or prior.get("schema_version") != 1 or prior.get("mode") != "read_only" or not isinstance(prior.get("run_id"), str):
                    raise ValueError("Previous diagnostic invalid: refusing overwrite")
                if prior["run_id"] == report["run_id"]:
                    raise ValueError("Duplicate run_id: refusing overwrite")
                atomic_bytes(target.with_name(target.name + ".last-good"), previous)
            atomic_bytes(target, payload.encode("utf-8"))
            readback = target.read_bytes()
            if hashlib.sha256(readback).hexdigest() != hashlib.sha256(payload.encode("utf-8")).hexdigest():
                raise OSError("JSON report readback SHA256 mismatch")
            parsed = json.loads(readback)
            if not isinstance(parsed, dict) or parsed.get("schema_version") != 1 or parsed.get("run_id") != report["run_id"] or parsed.get("mode") != "read_only":
                raise ValueError("JSON report schema/readback mismatch")
        finally:
            try:
                if lock.stat().st_ino == lock_owner:
                    lock.unlink()
            except FileNotFoundError:
                pass
    print(payload, end="")

if __name__ == "__main__":
    main()
