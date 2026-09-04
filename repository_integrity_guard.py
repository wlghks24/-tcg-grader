#!/usr/bin/env python3
"""Fail-closed integrity checks for tracked source and configuration files.

This guard is intentionally read-only. It catches syntax damage and audit blind spots
that targeted runtime tests can miss: unresolved merge markers, Trojan Source bidi
controls, oversized executable text that the security scanner would otherwise skip,
malformed/duplicate-key JSON, Python syntax errors, unsafe tracked symlinks, and
cross-platform filename collisions that can break the Windows/Android deployment path.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parent
EXECUTABLE_TEXT_SUFFIXES = {
    ".py", ".js", ".html", ".yml", ".yaml",
    ".sh", ".command", ".bat", ".cmd", ".ps1",
}
JSON_TEXT_SUFFIXES = {".json", ".webmanifest"}
TEXT_SUFFIXES = EXECUTABLE_TEXT_SUFFIXES | JSON_TEXT_SUFFIXES | {".md", ".txt", ".css", ".svg"}
SECURITY_SCAN_LIMIT = 2_000_000
MAX_JSON_BYTES = 20_000_000
BIDI_CONTROLS = {chr(code) for code in (*range(0x202A, 0x202F), *range(0x2066, 0x206A))}
# Match actual Git conflict marker lines, not decorative separators such as
# "========================================" in shell output banners.
MERGE_MARKER_RE = re.compile(r"^(?:<{7}(?: .*)?|\|{7}(?: .*)?|={7}|>{7}(?: .*)?)\s*$")
WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
WINDOWS_FORBIDDEN = set('<>:"\\|?*')


def tracked_entries() -> list[tuple[str, Path, bool]]:
    """Return every tracked path without silently following or omitting symlinks."""
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    entries: list[tuple[str, Path, bool]] = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        relative = raw.decode("utf-8", "strict")
        path = ROOT / relative
        entries.append((relative, path, path.is_symlink()))
    return entries


def unsafe_windows_component(component: str) -> str | None:
    if component in {"", ".", ".."}:
        return "invalid path component"
    if component.endswith((" ", ".")):
        return "trailing space/dot is not portable to Windows"
    if any(char in WINDOWS_FORBIDDEN or ord(char) < 32 for char in component):
        return "Windows-forbidden filename character"
    stem = component.split(".", 1)[0].upper()
    if stem in WINDOWS_RESERVED:
        return "Windows reserved device name"
    return None


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def legacy_runtime_reference(relative: str, text: str) -> str | None:
    """Reject accidental execution/import of archived one-shot patch sources.

    Historical apply_* and gemini-code-* files remain tracked for reproducibility,
    but current runtime code must never depend on them. Tests and the archived
    patch files themselves may mention those names while proving migration safety.
    """
    name = Path(relative).name
    if (
        name.startswith("apply_")
        or name.startswith("gemini-code-")
        or name.startswith(("test_", "verify_"))
        or relative.startswith(".github/workflows/apply-")
    ):
        return None
    if "gemini-code-" in text:
        return "current runtime references archived gemini-code source"
    if re.search(r"(?m)^\s*(?:from|import)\s+apply_[A-Za-z0-9_]+", text):
        return "current runtime imports one-shot apply_* patch module"
    if re.search(r"\bpython(?:3(?:\.\d+)?)?\s+apply_[A-Za-z0-9_]+\.py\b", text):
        return "current runtime executes one-shot apply_* patch script"
    return None


def main() -> int:
    findings: list[str] = []
    checked = 0
    suffix_counts: dict[str, int] = {}
    entries = tracked_entries()

    # A case-insensitive checkout (the user's Windows PC) cannot safely represent
    # two different tracked paths that case-fold to the same value.
    folded: dict[str, str] = {}
    for relative, _path, _is_symlink in entries:
        key = relative.casefold()
        previous = folded.get(key)
        if previous is not None and previous != relative:
            findings.append(f"case-insensitive path collision: {previous} <-> {relative}")
        else:
            folded[key] = relative
        if any(char in BIDI_CONTROLS or ord(char) < 32 or ord(char) == 127 for char in relative):
            findings.append(f"{relative!r}: control/bidi character in tracked filename")
        for component in Path(relative).parts:
            reason = unsafe_windows_component(component)
            if reason:
                findings.append(f"{relative}: {reason}: {component!r}")
                break

    for relative, path, is_symlink in entries:
        suffix = path.suffix.lower()
        if suffix not in TEXT_SUFFIXES:
            continue
        checked += 1
        suffix_counts[suffix] = suffix_counts.get(suffix, 0) + 1
        if is_symlink:
            findings.append(f"{relative}: tracked text/config symlink is not allowed")
            continue
        try:
            if not path.is_file():
                findings.append(f"{relative}: tracked text path is not a regular file")
                continue
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
        if suffix in JSON_TEXT_SUFFIXES and size > MAX_JSON_BYTES:
            findings.append(f"{relative}: JSON-like file exceeds {MAX_JSON_BYTES} bytes")
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
                if MERGE_MARKER_RE.fullmatch(line.lstrip()):
                    findings.append(f"{relative}:{lineno}: unresolved merge marker")
            legacy_reason = legacy_runtime_reference(relative, text)
            if legacy_reason:
                findings.append(f"{relative}: {legacy_reason}")

        if suffix == ".py":
            try:
                compile(text, relative, "exec", dont_inherit=True)
            except (SyntaxError, ValueError, OverflowError) as exc:
                lineno = getattr(exc, "lineno", None) or 1
                findings.append(f"{relative}:{lineno}: Python compile failed: {exc}")
        elif suffix in JSON_TEXT_SUFFIXES:
            try:
                json.loads(text, object_pairs_hook=unique_object, parse_constant=reject_constant)
            except (ValueError, TypeError, RecursionError) as exc:
                findings.append(f"{relative}: strict JSON parse failed: {exc}")

    if findings:
        print("Repository integrity guard: FAILED", file=sys.stderr)
        for item in findings:
            print(f" - {item}", file=sys.stderr)
        return 1
    summary = ", ".join(f"{suffix or '(none)'}={count}" for suffix, count in sorted(suffix_counts.items()))
    print(
        f"Repository integrity guard: OK ({checked} tracked text files checked; "
        f"{len(entries)} tracked paths checked; {summary})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
