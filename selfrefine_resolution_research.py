#!/usr/bin/env python3
"""Fail-closed research and verified-resolution learning for Main SELFREFINE.

New errors are handled in five separated stages:
1. scan the complete Main code/audit surface and build an impact map,
2. create a sanitized official-source-first research plan,
3. let only existing code-defined repair rules modify files,
4. keep the repair pending until the full regression workflow passes,
5. learn only the verified resolution method for future prioritization.

Research text, search results, error strings, and learned lesson text are advisory
data only. They are never evaluated, imported, or converted directly into code.
"""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from safe_runtime import atomic_write_json, exclusive_file_lock, safe_read_text

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "MAIN_SELFREFINE_RESOLUTION_LEARNING_STATE.json"
REPORT = ROOT / "MAIN_SELFREFINE_RESEARCH_REPORT.json"
SCHEMA = 1

MAX_SCAN_FILES = 4000
MAX_FILE_BYTES = 1_500_000
MAX_IMPACT_FILES = 64
MAX_ISSUES = 500
MAX_LESSONS = 500
MAX_HISTORY = 300

AUDIT_SUFFIXES = {
    ".py", ".js", ".mjs", ".cjs", ".html", ".css",
    ".json", ".jsonl", ".yml", ".yaml", ".sh", ".bat",
}
EXCLUDED_PREFIXES = (
    "instagram_tcg_content/",
    ".git/",
    ".venv/",
    "venv/",
    "__pycache__/",
    ".pytest_cache/",
)

OFFICIAL_RESEARCH = {
    "python": {
        "sources": [
            "https://docs.python.org/3/reference/index.html",
            "https://docs.python.org/3/library/ast.html",
        ],
        "query_prefix": "site:docs.python.org Python",
    },
    "javascript": {
        "sources": [
            "https://nodejs.org/api/",
            "https://developer.mozilla.org/en-US/docs/Web/JavaScript",
        ],
        "query_prefix": "site:nodejs.org JavaScript Node.js",
    },
    "shell": {
        "sources": [
            "https://www.gnu.org/software/bash/manual/",
        ],
        "query_prefix": "site:gnu.org/software/bash Bash",
    },
    "json": {
        "sources": [
            "https://docs.python.org/3/library/json.html",
            "https://datatracker.ietf.org/doc/html/rfc8259",
        ],
        "query_prefix": "JSON RFC 8259 Python",
    },
    "github_actions": {
        "sources": [
            "https://docs.github.com/en/actions/how-tos/secure-your-work",
            "https://docs.github.com/en/actions/concepts/security/script-injections",
        ],
        "query_prefix": "site:docs.github.com GitHub Actions",
    },
    "http": {
        "sources": [
            "https://docs.python.org/3/library/urllib.request.html",
            "https://datatracker.ietf.org/doc/html/rfc9110",
        ],
        "query_prefix": "HTTP RFC 9110 Python urllib",
    },
    "generic": {
        "sources": [
            "https://docs.python.org/3/",
            "https://docs.github.com/en/actions/how-tos/secure-your-work",
        ],
        "query_prefix": "software regression debugging official documentation",
    },
}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _clean(value: Any, limit: int = 500) -> str:
    text = str(value or "").replace("\x00", " ")
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _normalized(value: Any) -> str:
    return _clean(value, 400).replace("\\", "/").lstrip("./")


def _safe_signature(issue: dict[str, Any]) -> str:
    existing = _clean(issue.get("error_signature"), 80).lower()
    if re.fullmatch(r"[0-9a-f]{16,80}", existing):
        return existing[:80]
    raw = "|".join(
        _clean(issue.get(field), 500)
        for field in ("stage", "path", "root_cause", "evidence")
    )
    return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:20]


def _default_state() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "updated_at": None,
        "issues": {},
        "pending_verifications": {},
        "lessons": {},
        "history": [],
        "safety": {
            "full_repository_impact_analysis": True,
            "official_source_first_research": True,
            "research_text_executable": False,
            "search_result_patch_generation": False,
            "learned_text_executable": False,
            "unknown_error_direct_auto_patch": False,
            "code_defined_repairs_only": True,
            "full_regression_required_before_learning": True,
            "failed_verification_not_learned": True,
        },
    }


def _load_state(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(safe_read_text(path, max_bytes=3_000_000))
    except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        return _default_state()
    if not isinstance(value, dict):
        return _default_state()
    state = _default_state()
    state["issues"] = {
        str(key)[:80]: row for key, row in (value.get("issues") or {}).items()
        if isinstance(key, str) and isinstance(row, dict)
    }
    state["pending_verifications"] = {
        str(key)[:80]: row for key, row in (value.get("pending_verifications") or {}).items()
        if isinstance(key, str) and isinstance(row, dict)
    }
    state["lessons"] = {
        str(key)[:80]: row for key, row in (value.get("lessons") or {}).items()
        if isinstance(key, str) and isinstance(row, dict)
    }
    state["history"] = [
        row for row in (value.get("history") or [])[-MAX_HISTORY:]
        if isinstance(row, dict)
    ]
    return state


def _save_state(path: Path, state: dict[str, Any]) -> None:
    state["schema"] = SCHEMA
    state["updated_at"] = _now()
    state["issues"] = dict(list(state.get("issues", {}).items())[-MAX_ISSUES:])
    state["lessons"] = dict(list(state.get("lessons", {}).items())[-MAX_LESSONS:])
    state["history"] = state.get("history", [])[-MAX_HISTORY:]
    state["safety"] = _default_state()["safety"]
    atomic_write_json(path, state, suffix=".resolution-learning.tmp")


def _fallback_files(root: Path) -> list[str]:
    rows: list[str] = []
    for path in root.rglob("*"):
        if len(rows) >= MAX_SCAN_FILES + 1:
            break
        try:
            if path.is_symlink() or not path.is_file():
                continue
        except OSError:
            continue
        relative = path.relative_to(root).as_posix()
        if any(relative.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
            continue
        if path.suffix.lower() not in AUDIT_SUFFIXES:
            continue
        rows.append(relative)
    return rows


def _tracked_files(root: Path) -> tuple[list[str], bool]:
    names: list[str] = []
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            capture_output=True,
            timeout=20,
            check=False,
        )
        if proc.returncode == 0:
            names = [
                item.decode("utf-8", "replace")
                for item in proc.stdout.split(b"\x00") if item
            ]
    except (OSError, subprocess.SubprocessError):
        names = []
    if not names:
        names = _fallback_files(root)

    filtered: list[str] = []
    for raw in names:
        relative = _normalized(raw)
        if not relative or any(relative.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
            continue
        path = root / relative
        if path.suffix.lower() not in AUDIT_SUFFIXES:
            continue
        try:
            if path.is_symlink() or not path.is_file():
                continue
        except OSError:
            continue
        filtered.append(relative)
    filtered = sorted(dict.fromkeys(filtered))
    truncated = len(filtered) > MAX_SCAN_FILES
    return filtered[:MAX_SCAN_FILES], truncated


def _python_imports(text: str) -> set[str]:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        return set()
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names if alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def build_repository_index(root: Path = ROOT) -> dict[str, Any]:
    files, truncated = _tracked_files(root)
    records: list[dict[str, Any]] = []
    read_errors = 0
    for relative in files:
        path = root / relative
        try:
            text = safe_read_text(path, max_bytes=MAX_FILE_BYTES)
        except (OSError, ValueError, TypeError, UnicodeError):
            text = ""
            read_errors += 1
        records.append({
            "path": relative,
            "suffix": path.suffix.lower(),
            "text": text,
            "text_lower": text.lower(),
            "imports": _python_imports(text) if path.suffix.lower() == ".py" else set(),
        })
    return {
        "records": records,
        "files_scanned": len(records),
        "scan_truncated": truncated,
        "read_errors": read_errors,
        "full_repository_scan": not truncated,
    }


def _module_name(relative: str) -> str:
    value = relative[:-3] if relative.endswith(".py") else relative
    value = value.replace("/", ".")
    return value[:-9] if value.endswith(".__init__") else value


def analyze_repository_impact(
    issue: dict[str, Any],
    *,
    index: dict[str, Any] | None = None,
    root: Path = ROOT,
) -> dict[str, Any]:
    index = index or build_repository_index(root)
    target = _normalized(issue.get("path"))
    target_name = Path(target).name.lower() if target else ""
    target_stem = Path(target).stem.lower() if target else ""
    target_module = _module_name(target) if target.endswith(".py") else ""

    impacted: list[dict[str, Any]] = []
    for row in index["records"]:
        relative = row["path"]
        lower = row["text_lower"]
        score = 0
        reasons: list[str] = []
        if relative == target:
            score = 100
            reasons.append("direct_error_path")
        if target_module and row["suffix"] == ".py":
            for imported in row["imports"]:
                if imported == target_module or imported.startswith(target_module + "."):
                    score = max(score, 90)
                    reasons.append("python_import_dependency")
                    break
        if target_stem and Path(relative).name.lower().startswith("test_") and target_stem in lower:
            score = max(score, 82)
            reasons.append("targeted_test_reference")
        if target_name and target_name in lower and relative != target:
            score = max(score, 72)
            reasons.append("file_reference")
        elif target_stem and len(target_stem) >= 4 and target_stem in lower and relative != target:
            score = max(score, 58)
            reasons.append("module_or_symbol_reference")
        if relative.startswith(".github/workflows/") and target_name and target_name in lower:
            score = max(score, 75)
            reasons.append("workflow_reference")
        if score:
            impacted.append({
                "path": relative,
                "score": score,
                "reasons": sorted(set(reasons)),
            })

    impacted.sort(key=lambda row: (-int(row["score"]), str(row["path"])))
    return {
        "analysis_scope": "all_main_tracked_code_and_audit_files",
        "files_scanned": int(index["files_scanned"]),
        "scan_truncated": bool(index["scan_truncated"]),
        "full_repository_scan": bool(index["full_repository_scan"]),
        "read_errors": int(index["read_errors"]),
        "impacted_files": impacted[:MAX_IMPACT_FILES],
        "impacted_file_count": len(impacted),
    }


def _research_family(issue: dict[str, Any]) -> str:
    stage = _clean(issue.get("stage"), 100).upper()
    path = _normalized(issue.get("path")).lower()
    evidence = (
        _clean(issue.get("root_cause"), 240)
        + " "
        + _clean(issue.get("evidence"), 500)
    ).lower()
    if path.startswith(".github/workflows/") or "GITHUB" in stage or "ACTION" in stage:
        return "github_actions"
    if "PYTHON" in stage or path.endswith(".py") or "syntaxerror" in evidence:
        return "python"
    if "JS_" in stage or "JAVASCRIPT" in stage or path.endswith((".js", ".mjs", ".cjs")):
        return "javascript"
    if "SHELL" in stage or path.endswith((".sh", ".bat")):
        return "shell"
    if "JSON" in stage or path.endswith((".json", ".jsonl")):
        return "json"
    if any(token in stage for token in ("HTTP", "NETWORK", "TIMEOUT", "SOURCE_")):
        return "http"
    if any(token in evidence for token in ("http ", "urlerror", "timed out", "connection")):
        return "http"
    return "generic"


def research_plan(issue: dict[str, Any]) -> dict[str, Any]:
    family = _research_family(issue)
    catalog = OFFICIAL_RESEARCH[family]
    stage = _clean(issue.get("stage"), 80) or "UNKNOWN"
    cause = _clean(issue.get("root_cause"), 180) or "unknown root cause"
    path = _normalized(issue.get("path"))
    suffix = Path(path).suffix.lower().lstrip(".") or "source"
    compact = re.sub(r"[^A-Za-z0-9가-힣_. -]+", " ", f"{stage} {cause}")
    compact = re.sub(r"\s+", " ", compact).strip()[:180]
    queries = [
        f"{catalog['query_prefix']} {compact}".strip(),
        f"{catalog['query_prefix']} {suffix} regression fix verification {stage}".strip(),
    ]
    fingerprint_raw = json.dumps(
        {"family": family, "queries": queries, "sources": catalog["sources"]},
        sort_keys=True,
        ensure_ascii=False,
    )
    return {
        "research_family": family,
        "strategy": "official_or_primary_sources_first_then_cross_check",
        "search_required_for_new_error": True,
        "search_queries": queries,
        "preferred_sources": list(catalog["sources"]),
        "research_fingerprint": hashlib.sha256(
            fingerprint_raw.encode("utf-8", "replace")
        ).hexdigest()[:24],
        "research_text_executable": False,
        "patch_from_search_text_allowed": False,
        "minimum_evidence_rule": "root_cause_reproduced_plus_regression_verified",
    }


def observe_errors(
    errors: list[dict[str, Any]],
    *,
    root: Path = ROOT,
    state_path: Path = STATE,
    report_path: Path = REPORT,
) -> dict[str, Any]:
    open_errors = [
        row for row in errors[:MAX_ISSUES]
        if isinstance(row, dict) and row.get("state") == "open"
    ]
    index = build_repository_index(root)
    now = _now()
    observations: list[dict[str, Any]] = []

    with exclusive_file_lock(state_path):
        state = _load_state(state_path)
        issues = state.setdefault("issues", {})
        lessons = state.setdefault("lessons", {})
        for issue in open_errors:
            signature = _safe_signature(issue)
            previous = issues.get(signature) if isinstance(issues.get(signature), dict) else {}
            recurrence = max(0, int(previous.get("recurrence_count") or 0)) + 1
            impact = analyze_repository_impact(issue, index=index, root=root)
            research = research_plan(issue)
            lesson = lessons.get(signature) if isinstance(lessons.get(signature), dict) else None
            row = {
                "error_signature": signature,
                "error_code": _clean(issue.get("error_code"), 160),
                "stage": _clean(issue.get("stage"), 100),
                "path": _normalized(issue.get("path")),
                "root_cause": _clean(issue.get("root_cause"), 300),
                "evidence_summary": _clean(issue.get("evidence"), 500),
                "first_seen": previous.get("first_seen") or now,
                "last_seen": now,
                "recurrence_count": min(1_000_000, recurrence),
                "status": "open",
                "new_error": not bool(previous),
                "impact_analysis": impact,
                "research": research,
                "known_verified_resolution": bool(lesson and lesson.get("regression_pass") is True),
                "preferred_verified_fix_pattern": (
                    _clean(lesson.get("fix_pattern"), 300)
                    if lesson and lesson.get("regression_pass") is True else ""
                ),
            }
            issues[signature] = row
            observations.append(row)
            state.setdefault("history", []).append({
                "at": now,
                "error_signature": signature,
                "event": "new_error_researched" if row["new_error"] else "recurring_error_researched",
                "research_fingerprint": research["research_fingerprint"],
                "files_scanned": impact["files_scanned"],
            })

        _save_state(state_path, state)

    report = {
        "schema": SCHEMA,
        "generated_at": now,
        "error_count": len(observations),
        "new_error_count": sum(row["new_error"] for row in observations),
        "known_verified_resolution_count": sum(
            row["known_verified_resolution"] for row in observations
        ),
        "repository_files_scanned": int(index["files_scanned"]),
        "full_repository_scan": bool(index["full_repository_scan"]),
        "scan_truncated": bool(index["scan_truncated"]),
        "read_errors": int(index["read_errors"]),
        "errors": observations,
        "safety": _default_state()["safety"],
    }
    atomic_write_json(report_path, report, suffix=".resolution-research.tmp")
    return report


def stage_repairs(
    applied: list[dict[str, Any]],
    *,
    state_path: Path = STATE,
) -> dict[str, Any]:
    staged = 0
    now = _now()
    with exclusive_file_lock(state_path):
        state = _load_state(state_path)
        for item in applied:
            if not isinstance(item, dict):
                continue
            signature = _clean(item.get("error_signature"), 80).lower()
            if not signature:
                continue
            issue = state.get("issues", {}).get(signature)
            if not isinstance(issue, dict):
                continue
            rule_id = _clean(item.get("rule_id"), 160)
            if not rule_id:
                continue
            state.setdefault("pending_verifications", {})[signature] = {
                "error_signature": signature,
                "rule_id": rule_id,
                "rule_fingerprint": _clean(item.get("rule_fingerprint"), 80),
                "path": _normalized(item.get("path")),
                "stage": _clean(item.get("stage"), 100),
                "staged_at": now,
                "verification_status": "pending_full_regression",
                "research_fingerprint": _clean(
                    (issue.get("research") or {}).get("research_fingerprint"), 80
                ),
                "impact_files": [
                    row.get("path")
                    for row in (issue.get("impact_analysis") or {}).get("impacted_files", [])[:20]
                    if isinstance(row, dict)
                ],
            }
            staged += 1
            state.setdefault("history", []).append({
                "at": now,
                "error_signature": signature,
                "event": "repair_pending_full_regression",
                "rule_id": rule_id,
            })
        _save_state(state_path, state)
    return {
        "pending_full_regression": staged,
        "full_regression_required_before_learning": True,
        "learned_now": 0,
    }


def _lesson_id(signature: str, rule_id: str) -> str:
    raw = f"{signature}|{rule_id}"
    return "MAIN-" + hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:16].upper()


def finalize_pending(
    success: bool,
    *,
    state_path: Path = STATE,
) -> dict[str, Any]:
    verified = rejected = 0
    now = _now()
    with exclusive_file_lock(state_path):
        state = _load_state(state_path)
        pending = dict(state.get("pending_verifications", {}))
        for signature, pending_row in pending.items():
            if not isinstance(pending_row, dict):
                continue
            issue = state.get("issues", {}).get(signature)
            if not isinstance(issue, dict):
                state.get("pending_verifications", {}).pop(signature, None)
                continue
            rule_id = _clean(pending_row.get("rule_id"), 160)
            if success:
                old = state.get("lessons", {}).get(signature)
                old_successes = int(old.get("verified_successes") or 0) if isinstance(old, dict) else 0
                lesson = {
                    "lesson_id": _lesson_id(signature, rule_id),
                    "subsystem": Path(_normalized(issue.get("path"))).stem or "repository",
                    "issue_class": _clean(issue.get("stage"), 120) or "UNKNOWN",
                    "trigger_condition": _clean(
                        f"{issue.get('stage')} in {issue.get('path')}", 300
                    ),
                    "symptom_summary": _clean(
                        issue.get("evidence_summary") or issue.get("root_cause"), 500
                    ),
                    "root_cause_class": _clean(issue.get("root_cause"), 160) or "unknown",
                    "fix_pattern": f"verified_code_rule:{rule_id}",
                    "prevention_rule_id": rule_id,
                    "verification_result": "full_regression_passed",
                    "regression_pass": True,
                    "recurrence_count": min(
                        1_000_000, int(issue.get("recurrence_count") or 0)
                    ),
                    "applicable_scope": "main",
                    "confidence_level": "high" if old_successes >= 1 else "medium",
                    "verified_successes": min(10_000, old_successes + 1),
                    "verified_failures": int(old.get("verified_failures") or 0)
                    if isinstance(old, dict) else 0,
                    "research_fingerprint": _clean(
                        pending_row.get("research_fingerprint"), 80
                    ),
                    "resolution_method": (
                        "full_repository_impact_analysis -> official_source_research -> "
                        "code_defined_minimal_fix -> local_scan -> full_regression"
                    ),
                    "impacted_files": list(pending_row.get("impact_files") or [])[:20],
                    "verified_at": now,
                }
                state.setdefault("lessons", {})[signature] = lesson
                issue["status"] = "resolved_verified"
                issue["last_verified_resolution"] = lesson["fix_pattern"]
                verified += 1
                event = "verified_resolution_learned"
            else:
                old = state.get("lessons", {}).get(signature)
                if isinstance(old, dict):
                    old["verified_failures"] = min(
                        10_000, int(old.get("verified_failures") or 0) + 1
                    )
                    old["confidence_level"] = "low"
                issue["status"] = "verification_failed"
                rejected += 1
                event = "resolution_rejected_by_full_regression"
            state.setdefault("history", []).append({
                "at": now,
                "error_signature": signature,
                "event": event,
                "rule_id": rule_id,
            })
            state.setdefault("pending_verifications", {}).pop(signature, None)
        _save_state(state_path, state)
    return {
        "verified_resolution_lessons": verified,
        "rejected_unverified_resolutions": rejected,
        "regression_pass": bool(success),
        "research_text_executable": False,
        "unknown_error_direct_auto_patch": False,
    }


def public_summary(*, state_path: Path = STATE) -> dict[str, Any]:
    with exclusive_file_lock(state_path):
        state = _load_state(state_path)
    issues = list(state.get("issues", {}).values())
    lessons = list(state.get("lessons", {}).values())
    return {
        "ok": True,
        "researched_error_codes": len(issues),
        "verified_resolution_lessons": sum(
            row.get("regression_pass") is True for row in lessons
        ),
        "pending_full_regression": len(state.get("pending_verifications", {})),
        "known_verified_reuse_candidates": sum(
            row.get("status") == "open"
            and isinstance(state.get("lessons", {}).get(row.get("error_signature")), dict)
            for row in issues
            if isinstance(row, dict)
        ),
        "safety": state["safety"],
    }


def self_test() -> int:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "broken.py").write_text("x = (\n", encoding="utf-8")
        (root / "consumer.py").write_text("import broken\n", encoding="utf-8")
        (root / "test_broken.py").write_text(
            "import broken\n# broken.py regression\n", encoding="utf-8"
        )
        state = root / "state.json"
        report = root / "report.json"
        issue = {
            "error_signature": "a" * 20,
            "error_code": "SELFREFINE.PYTHON_SYNTAX",
            "stage": "PYTHON_SYNTAX",
            "path": "broken.py",
            "root_cause": "SyntaxError",
            "evidence": "line 1 syntax error",
            "state": "open",
        }
        observed = observe_errors(
            [issue], root=root, state_path=state, report_path=report
        )
        assert observed["new_error_count"] == 1, observed
        impacted = {row["path"] for row in observed["errors"][0]["impact_analysis"]["impacted_files"]}
        assert {"broken.py", "consumer.py", "test_broken.py"}.issubset(impacted), impacted
        assert observed["errors"][0]["research"]["preferred_sources"]
        assert observed["errors"][0]["research"]["patch_from_search_text_allowed"] is False

        staged = stage_repairs([{
            "error_signature": "a" * 20,
            "rule_id": "example-code-defined-rule",
            "rule_fingerprint": "f" * 24,
            "path": "broken.py",
            "stage": "PYTHON_SYNTAX",
        }], state_path=state)
        assert staged["pending_full_regression"] == 1, staged
        assert not _load_state(state)["lessons"], "must not learn before full regression"

        finalized = finalize_pending(True, state_path=state)
        assert finalized["verified_resolution_lessons"] == 1, finalized
        lesson = _load_state(state)["lessons"]["a" * 20]
        assert lesson["regression_pass"] is True
        assert lesson["verification_result"] == "full_regression_passed"
        assert lesson["fix_pattern"].startswith("verified_code_rule:")

        observed_again = observe_errors(
            [issue], root=root, state_path=state, report_path=report
        )
        assert observed_again["errors"][0]["known_verified_resolution"] is True

    print("Main SELFREFINE new-error research + verified resolution learning: PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--finalize", choices=("success", "failure"))
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.finalize:
        print(json.dumps(
            finalize_pending(args.finalize == "success"),
            ensure_ascii=False,
            sort_keys=True,
        ))
        return 0
    if args.summary:
        print(json.dumps(public_summary(), ensure_ascii=False, sort_keys=True))
        return 0
    raise SystemExit("Use through Main SELFREFINE; arbitrary research text cannot execute repairs.")


if __name__ == "__main__":
    raise SystemExit(main())
