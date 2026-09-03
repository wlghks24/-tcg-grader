#!/usr/bin/env python3
"""Fail-closed integrity checks for tracked source and configuration files.

This guard is intentionally read-only. It catches syntax damage and audit blind spots
that targeted runtime tests can miss: unresolved merge markers, Trojan Source bidi
controls, oversized executable text that the security scanner would otherwise skip,
malformed/duplicate-key JSON, and Python syntax errors across the whole tracked tree.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parent
EXECUTABLE_TEXT_SUFFIXES = {".py", ".js", ".html", ".yml", ".yaml", ".sh", ".bat", ".ps1"}
TEXT_SUFFIXES = EXECUTABLE_TEXT_SUFFIXES | {".json", ".md", ".txt", ".css"}
SECURITY_SCAN_LIMIT = 2_000_000
MAX_JSON_BYTES = 20_000_000
BIDI_CONTROLS = {chr(code) for code in (*range(0x202A, 0x202F), *range(0x2066, 0x206A))}
MERGE_MARKERS = ("<<<<<<< ", "=======", ">>>>>>> ")


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    paths: list[Path] = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        relative = raw.decode("utf-8", "strict")
        path = ROOT / relative
        if path.is_symlink() or not path.is_file():
            continue
        paths.append(path)
    return paths


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def main() -> int:
    findings: list[str] = []
    checked = 0
    for path in tracked_files():
        relative = path.relative_to(ROOT).as_posix()
        suffix = path.suffix.lower()
        if suffix not in TEXT_SUFFIXES:
            continue
        checked += 1
        try:
            size = path.stat().st_size
        except OSError as exc:
            findings.append(f"{relative}: stat failed: {exc.__class__.__name__}")
            continue

        if suffix in EXECUTABLE_TEXT_SUFFIXES and size > SECURITY_SCAN_LIMIT:
            findings.append(
                f"{relative}: executable text is {size} bytes, above the "
                f"{SECURITY_SCAN_LIMIT}-byte security-audit limit"
            )
            continue
        if suffix == ".json" and size > MAX_JSON_BYTES:
            findings.append(f"{relative}: JSON exceeds {MAX_JSON_BYTES} bytes")
            continue

        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeError) as exc:
            findings.append(f"{relative}: UTF-8 read failed: {exc.__class__.__name__}")
            continue

        if "\x00" in text:
            findings.append(f"{relative}: NUL byte in tracked text")
        if suffix in EXECUTABLE_TEXT_SUFFIXES and any(char in text for char in BIDI_CONTROLS):
            findings.append(f"{relative}: bidi control character in executable text")
        if suffix in EXECUTABLE_TEXT_SUFFIXES:
            for lineno, line in enumerate(text.splitlines(), 1):
                stripped = line.lstrip()
                if any(stripped.startswith(marker) for marker in MERGE_MARKERS):
                    findings.append(f"{relative}:{lineno}: unresolved merge marker")

        if suffix == ".py":
            try:
                compile(text, relative, "exec", dont_inherit=True)
            except (SyntaxError, ValueError, OverflowError) as exc:
                lineno = getattr(exc, "lineno", None) or 1
                findings.append(f"{relative}:{lineno}: Python compile failed: {exc}")
        elif suffix == ".json":
            try:
                json.loads(text, object_pairs_hook=unique_object, parse_constant=reject_constant)
            except (ValueError, TypeError, RecursionError) as exc:
                findings.append(f"{relative}: strict JSON parse failed: {exc}")

    if findings:
        print("Repository integrity guard: FAILED", file=sys.stderr)
        for item in findings:
            print(f" - {item}", file=sys.stderr)
        return 1
    print(f"Repository integrity guard: OK ({checked} tracked text files checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
