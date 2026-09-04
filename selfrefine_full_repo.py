#!/usr/bin/env python3
"""Bounded whole-repository SELFREFINE audit with a non-executable error ledger.

This audit never edits source code. It reuses the repository's fail-closed tracked-file
scope and strict JSON policy, records only bounded diagnostic evidence, preserves
resolved history, and stops early when repeated cycles produce the same failure set.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import repository_integrity_guard as integrity
import security_self_audit
from safe_runtime import atomic_write_json

ROOT = Path(__file__).resolve().parent
KST = timezone(timedelta(hours=9))
LEDGER_PATH = ROOT / "SELFREFINE_ERROR_LEDGER.json"
MAX_ERRORS = 500
MAX_EVIDENCE = 1200
JS_SUFFIXES = {".js", ".mjs", ".cjs"}
SHELL_SUFFIXES = {".sh", ".command"}
JSON_SUFFIXES = set(integrity.JSON_TEXT_SUFFIXES)
AUDIT_SUFFIXES = set(integrity.TEXT_SUFFIXES) | JS_SUFFIXES


def now_kst() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def error_signature(stage: str, path: str, evidence: str) -> str:
    raw = f"{stage}|{path}|{evidence[:240]}"
    return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:20]


def tracked_code_files() -> Iterable[tuple[str, Path]]:
    """Use git's tracked set so local caches/generated files cannot affect the gate."""
    for relative, path, is_symlink in integrity.tracked_entries():
        if is_symlink or path.suffix.lower() not in AUDIT_SUFFIXES:
            continue
        yield relative, path


def make_issue(stage: str, relative: str, root_cause: str, evidence: str, fix_rule: str) -> dict:
    stamp = now_kst()
    clean = " ".join(str(evidence or "").replace("\x00", " ").split())[:MAX_EVIDENCE]
    return {
        "error_signature": error_signature(stage, relative, clean or root_cause),
        "stage": stage,
        "path": relative,
        "root_cause": str(root_cause)[:160],
        "evidence": clean,
        "fix_rule": str(fix_rule)[:300],
        "retry_count": 0,
        "regression_result": "failed",
        "state": "open",
        "first_seen_at_kst": stamp,
        "last_seen_at_kst": stamp,
    }


def scan_file(relative: str, path: Path) -> list[dict]:
    suffix = path.suffix.lower()
    try:
        text = path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError) as exc:
        return [make_issue(
            "TEXT_READ", relative, type(exc).__name__, repr(exc),
            "UTF-8 regular-file 상태를 복구한 뒤 전체 무결성 검사를 다시 실행",
        )]

    errors: list[dict] = []
    if suffix == ".py":
        try:
            ast.parse(text, filename=relative)
        except (SyntaxError, ValueError, MemoryError) as exc:
            errors.append(make_issue(
                "PYTHON_SYNTAX", relative, type(exc).__name__, repr(exc),
                "Python 문법을 수정하고 ast.parse 및 repository integrity 회귀검사를 재실행",
            ))
    elif suffix in JSON_SUFFIXES:
        try:
            json.loads(
                text,
                object_pairs_hook=integrity.unique_object,
                parse_constant=integrity.reject_constant,
            )
        except (ValueError, TypeError, RecursionError) as exc:
            errors.append(make_issue(
                "STRICT_JSON", relative, type(exc).__name__, repr(exc),
                "중복 키/NaN/Infinity를 제거하고 strict JSON 파서를 재실행",
            ))
    elif suffix in SHELL_SUFFIXES:
        bash = shutil.which("bash")
        if bash:
            proc = subprocess.run([bash, "-n", str(path)], capture_output=True, text=True, timeout=20)
            if proc.returncode:
                errors.append(make_issue(
                    "SHELL_SYNTAX", relative, "bash -n failure", proc.stderr or proc.stdout,
                    "shell 문법을 수정하고 bash -n을 재실행",
                ))
    elif suffix in JS_SUFFIXES:
        node = shutil.which("node")
        if node:
            proc = subprocess.run([node, "--check", str(path)], capture_output=True, text=True, timeout=20)
            if proc.returncode:
                errors.append(make_issue(
                    "JS_SYNTAX", relative, "node --check failure", proc.stderr or proc.stdout,
                    "JavaScript 문법을 수정하고 node --check를 재실행",
                ))
    return errors


def scan_security() -> list[dict]:
    errors: list[dict] = []
    for finding in security_self_audit.scan_repository(ROOT):
        if security_self_audit.SEVERITY_ORDER.get(str(finding.get("severity")), 0) < security_self_audit.SEVERITY_ORDER["high"]:
            continue
        relative = str(finding.get("path") or "repository")
        errors.append(make_issue(
            "SECURITY_HIGH", relative, str(finding.get("rule") or "security finding"),
            str(finding.get("evidence") or finding.get("message") or ""),
            "high/critical 보안 finding을 해결하고 security_self_audit --fail-on high를 재실행",
        ))
    return errors


def scan_once() -> tuple[list[dict], int]:
    errors: list[dict] = []
    files = list(tracked_code_files())
    for relative, path in files:
        errors.extend(scan_file(relative, path))
        if len(errors) >= MAX_ERRORS:
            break
    if len(errors) < MAX_ERRORS:
        errors.extend(scan_security())
    return errors[:MAX_ERRORS], len(files)


def load_previous(path: Path = LEDGER_PATH) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, UnicodeError, ValueError, TypeError):
        return {}


def merge_ledger(current: list[dict], files_scanned: int, cycle: int, *, path: Path = LEDGER_PATH) -> dict:
    previous = load_previous(path)
    old_rows = {
        str(row.get("error_signature")): row
        for row in (previous.get("errors") or [])
        if isinstance(row, dict) and row.get("error_signature")
    }
    stamp = now_kst()
    current_ids = {row["error_signature"] for row in current}
    merged: list[dict] = []

    for row in current:
        prior = old_rows.get(row["error_signature"])
        if isinstance(prior, dict):
            row["first_seen_at_kst"] = prior.get("first_seen_at_kst") or row["first_seen_at_kst"]
            row["retry_count"] = min(999, int(prior.get("retry_count") or 0) + 1)
        row["last_seen_at_kst"] = stamp
        merged.append(row)

    for signature, prior in old_rows.items():
        if signature in current_ids or not isinstance(prior, dict):
            continue
        resolved = dict(prior)
        resolved["state"] = "resolved"
        resolved["regression_result"] = "passed"
        resolved["resolved_at_kst"] = resolved.get("resolved_at_kst") or stamp
        merged.append(resolved)

    merged.sort(key=lambda row: (row.get("state") != "open", str(row.get("path")), str(row.get("stage"))))
    merged = merged[:MAX_ERRORS]
    open_count = sum(1 for row in merged if row.get("state") == "open")
    return {
        "version": 2,
        "updated_at_kst": stamp,
        "cycle": cycle,
        "summary": {
            "files_scanned": files_scanned,
            "open_errors": open_count,
            "resolved_errors_retained": sum(1 for row in merged if row.get("state") == "resolved"),
            "status": "pass" if open_count == 0 else "fail",
        },
        "safety": {
            "source_auto_rewrite": False,
            "git_write": False,
            "learned_text_executable": False,
            "tracked_files_only": True,
            "strict_json": True,
            "stable_failure_stops_early": True,
        },
        "errors": merged,
    }


def write_ledger(payload: dict, path: Path = LEDGER_PATH) -> None:
    atomic_write_json(path, payload, suffix=".selfrefine-ledger.tmp")


def run(cycles: int, *, path: Path = LEDGER_PATH) -> dict:
    limit = max(1, min(5, int(cycles)))
    previous_open: tuple[str, ...] | None = None
    result: dict = {}
    for cycle in range(1, limit + 1):
        errors, files_scanned = scan_once()
        result = merge_ledger(errors, files_scanned, cycle, path=path)
        open_ids = tuple(sorted(row["error_signature"] for row in result["errors"] if row.get("state") == "open"))
        if not open_ids:
            result["summary"]["stop_reason"] = "clean"
            write_ledger(result, path)
            break
        if open_ids == previous_open:
            result["summary"]["stop_reason"] = "stable_failure_no_source_rewrite"
            write_ledger(result, path)
            break
        previous_open = open_ids
        result["summary"]["stop_reason"] = "retry_after_changed_failure_set"
        write_ledger(result, path)
    return result


def self_test() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        bad_json = root / "bad.json"
        bad_json.write_text('{"a":1,"a":2}', encoding="utf-8")
        issues = scan_file("bad.json", bad_json)
        assert any(row["stage"] == "STRICT_JSON" for row in issues), issues

        good_python = root / "good.py"
        good_python.write_text("VALUE = 1\n", encoding="utf-8")
        assert scan_file("good.py", good_python) == []

        ledger = root / "ledger.json"
        first = merge_ledger([
            make_issue("PYTHON_SYNTAX", "x.py", "SyntaxError", "bad", "fix")
        ], 2, 1, path=ledger)
        write_ledger(first, ledger)
        second = merge_ledger([], 2, 2, path=ledger)
        assert second["summary"]["open_errors"] == 0
        assert second["summary"]["resolved_errors_retained"] == 1
        assert second["errors"][0]["regression_result"] == "passed"


def main() -> int:
    parser = argparse.ArgumentParser(description="Repository-wide bounded SELFREFINE audit")
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("SELFREFINE full-repository self-test: PASS")
        return 0
    result = run(args.cycles)
    print(json.dumps(result["summary"], ensure_ascii=False))
    return 0 if result["summary"]["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
