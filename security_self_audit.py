#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Defensive repository vulnerability audit with persistent learning memory.

The "learning" here is intentionally conservative: the tool remembers each finding,
how often it has appeared, and when it was resolved.  It never learns executable
code from untrusted input and never auto-applies approximate fixes.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any

ROOT = Path(__file__).resolve().parent
REPORT = ROOT / "security_audit_report.json"
MEMORY = ROOT / "security_learning_memory.json"
TEXT_EXTENSIONS = {".py", ".js", ".html", ".yml", ".yaml", ".sh", ".bat", ".ps1"}
MAX_SCAN_BYTES = 2_000_000
SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def write_json(path: Path, payload: Any) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def finding_id(rule: str, path: str, line: int, evidence: str) -> str:
    digest = hashlib.sha256(f"{rule}|{path}|{line}|{evidence[:160]}".encode("utf-8")).hexdigest()[:12]
    return f"{rule}:{digest}"


def add(findings: list[dict[str, Any]], rule: str, severity: str, path: str, line: int, message: str, evidence: str = "") -> None:
    findings.append({
        "id": finding_id(rule, path, line, evidence or message),
        "rule": rule,
        "severity": severity,
        "path": path,
        "line": int(line),
        "message": message,
        "evidence": evidence[:240],
    })


def iter_text_files(root: Path):
    excluded_dirs = {".git", "__pycache__", ".pytest_cache", "node_modules", "GRADE_TRAINING_INBOX"}
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        if any(part in excluded_dirs for part in path.parts):
            continue
        try:
            if path.stat().st_size > MAX_SCAN_BYTES:
                continue
            yield path, path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue


def scan_python(path: Path, text: str, findings: list[dict[str, Any]], rel: str) -> None:
    try:
        tree = ast.parse(text, filename=rel)
    except SyntaxError as exc:
        add(findings, "PY_SYNTAX", "high", rel, exc.lineno or 1, "Python syntax error prevents reliable security analysis.", str(exc))
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = ""
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                owner = node.func.value.id if isinstance(node.func.value, ast.Name) else ""
                name = f"{owner}.{node.func.attr}" if owner else node.func.attr
            if name in {"eval", "exec", "os.system"}:
                add(findings, "PY_DANGEROUS_EXEC", "critical", rel, getattr(node, "lineno", 1), "Dynamic code/shell execution requires manual review.", name)
            if name in {"subprocess.run", "subprocess.Popen", "subprocess.call", "subprocess.check_output"}:
                for keyword in node.keywords:
                    if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                        add(findings, "PY_SHELL_TRUE", "critical", rel, getattr(node, "lineno", 1), "subprocess shell=True can enable command injection.", name)


def scan_workflow(text: str, findings: list[dict[str, Any]], rel: str) -> None:
    if re.search(r"(?m)^\s*pull_request_target\s*:", text):
        add(findings, "GHA_PR_TARGET", "critical", rel, 1, "pull_request_target has a high trust boundary and requires strict review.", "pull_request_target")
    if re.search(r"(?m)^\s*permissions\s*:\s*write-all\s*$", text):
        add(findings, "GHA_WRITE_ALL", "high", rel, 1, "GitHub Actions write-all permission is broader than necessary.", "permissions: write-all")
    if re.search(r"(?ms)^permissions\s*:\s*.*?^\s*contents\s*:\s*write\s*$", text):
        untrusted_trigger=bool(re.search(r"(?m)^\s*(?:pull_request|pull_request_target)\s*:",text))
        severity="high" if untrusted_trigger else "low"
        message=("Write permission is reachable from a pull-request trigger."
                 if untrusted_trigger else
                 "Write permission is limited to trusted push/manual/scheduled automation; keep the trigger narrow.")
        add(findings, "GHA_CONTENTS_WRITE", severity, rel, 1, message, "contents: write")
    for lineno, line in enumerate(text.splitlines(), 1):
        match = re.search(r"\buses:\s*([^\s#]+)", line)
        if match:
            value = match.group(1)
            if value.startswith("./"):
                continue
            ref = value.rsplit("@", 1)[-1] if "@" in value else ""
            if not re.fullmatch(r"[0-9a-fA-F]{40}", ref):
                add(findings, "GHA_UNPINNED_ACTION", "medium", rel, lineno, "Third-party/action reference is mutable; pin to a full commit SHA.", value)
        if re.search(r"(?:curl|wget).*(?:\||\|\s*)(?:ba)?sh\b", line, re.I):
            add(findings, "GHA_REMOTE_PIPE_SHELL", "critical", rel, lineno, "Remote content is piped directly to a shell.", line.strip())


def scan_js_html(text: str, findings: list[dict[str, Any]], rel: str) -> None:
    for lineno, line in enumerate(text.splitlines(), 1):
        if re.search(r"\beval\s*\(|\bnew\s+Function\s*\(", line):
            add(findings, "JS_DYNAMIC_CODE", "critical", rel, lineno, "Dynamic JavaScript execution requires manual review.", line.strip())
        if "document.write(" in line:
            add(findings, "JS_DOCUMENT_WRITE", "medium", rel, lineno, "document.write can create DOM injection risk.", line.strip())
    if rel == "index.html" and "'unsafe-inline'" in text:
        add(findings, "CSP_UNSAFE_INLINE", "medium", rel, 1, "CSP still permits inline script/style; migrate to hashes/nonces when the UI is refactored.", "'unsafe-inline'")


def scan_repository(root: Path = ROOT) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    updater = (root / "tcg_updater.py").read_text(encoding="utf-8", errors="replace") if (root / "tcg_updater.py").exists() else ""
    runtime = (root / "safe_runtime.py").read_text(encoding="utf-8", errors="replace") if (root / "safe_runtime.py").exists() else ""
    gitignore = (root / ".gitignore").read_text(encoding="utf-8", errors="replace") if (root / ".gitignore").exists() else ""

    if "client_network_allowed(self.client_address[0])" not in updater:
        add(findings, "SERVER_PUBLIC_SOURCE_GUARD", "high", "tcg_updater.py", 1, "0.0.0.0 LAN server lacks a public-source client IP rejection guard.")
    if "OFFICIAL_LOOKUP_GUARD.claim(company)" not in updater:
        add(findings, "CERT_API_RATE_GUARD", "high", "tcg_updater.py", 1, "Web cert endpoint can bypass the batch 60s/max-2/cooldown policy.")
    if "def assert_no_symlink_components(" not in runtime:
        add(findings, "ANCESTOR_SYMLINK_GUARD", "high", "safe_runtime.py", 1, "Safe file helpers check too few path components for ancestor symlinks.")
    for required in (".env", "*.pem", "*.key", "credentials*.json", "security_learning_memory.json"):
        if required not in gitignore.splitlines():
            add(findings, "SECRET_GITIGNORE", "medium", ".gitignore", 1, f"Sensitive local pattern is not ignored: {required}", required)

    for path, text in iter_text_files(root):
        rel = path.relative_to(root).as_posix()
        suffix = path.suffix.lower()
        if suffix == ".py":
            scan_python(path, text, findings, rel)
        if suffix in {".yml", ".yaml"} and "/workflows/" in f"/{rel}":
            scan_workflow(text, findings, rel)
        if suffix in {".js", ".html"}:
            scan_js_html(text, findings, rel)

    findings.sort(key=lambda x: (-SEVERITY_ORDER.get(x["severity"], 0), x["path"], x["line"], x["rule"]))
    return findings


def update_memory(findings: list[dict[str, Any]], memory_path: Path = MEMORY) -> dict[str, Any]:
    now = utc_now()
    memory = load_json(memory_path, {"schema_version": 1, "findings": {}})
    if not isinstance(memory, dict):
        memory = {"schema_version": 1, "findings": {}}
    records = memory.setdefault("findings", {})
    if not isinstance(records, dict):
        records = {}; memory["findings"] = records
    current = {item["id"] for item in findings}
    for item in findings:
        previous = records.get(item["id"]) if isinstance(records.get(item["id"]), dict) else {}
        records[item["id"]] = {
            "rule": item["rule"], "severity": item["severity"], "path": item["path"],
            "first_seen": previous.get("first_seen") or now,
            "last_seen": now,
            "times_seen": int(previous.get("times_seen", 0)) + 1,
            "state": "open",
            "message": item["message"],
        }
    for fid, record in list(records.items()):
        if fid not in current and isinstance(record, dict) and record.get("state") == "open":
            record["state"] = "resolved"
            record["resolved_at"] = now
    memory["updated_at"] = now
    write_json(memory_path, memory)
    return memory


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fail-on", choices=list(SEVERITY_ORDER), default=None)
    parser.add_argument("--no-memory", action="store_true")
    args = parser.parse_args()
    findings = scan_repository()
    counts = {severity: sum(1 for item in findings if item["severity"] == severity) for severity in SEVERITY_ORDER}
    report = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "scope": "defensive-static-audit",
        "finding_counts": counts,
        "findings": findings,
        "note": "Findings are defensive review signals; medium/low items may be accepted design tradeoffs.",
    }
    write_json(REPORT, report)
    if not args.no_memory:
        update_memory(findings)
    print(json.dumps({"finding_counts": counts, "report": REPORT.name, "memory": None if args.no_memory else MEMORY.name}, ensure_ascii=False))
    if args.fail_on:
        threshold = SEVERITY_ORDER[args.fail_on]
        if any(SEVERITY_ORDER.get(item["severity"], 0) >= threshold for item in findings):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
