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
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from safe_runtime import (
    atomic_write_json,
    exclusive_file_lock,
    normalize_public_https_redirect,
    require_public_https,
    safe_read_text,
    validate_public_https_url,
)

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
MAX_PENDING_AGE_SECONDS = 6 * 60 * 60
MAX_NETWORK_RESEARCH_REQUESTS = 4
NETWORK_RESEARCH_TIMEOUT_SECONDS = 6
NETWORK_RESEARCH_MAX_BYTES = 250_000

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

RESEARCH_ALLOWED_HOSTS = {
    "docs.python.org",
    "docs.github.com",
    "nodejs.org",
    "developer.mozilla.org",
    "www.gnu.org",
    "datatracker.ietf.org",
}

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

OFFICIAL_SEARCH_TEMPLATES = {
    "python": "https://docs.python.org/3/search.html?q={query}",
    "javascript": "https://developer.mozilla.org/en-US/search?q={query}",
    "shell": "https://www.gnu.org/software/bash/manual/bash.html",
    "json": "https://docs.python.org/3/search.html?q={query}",
    "github_actions": "https://docs.github.com/en/search?query={query}",
    "http": "https://docs.python.org/3/search.html?q={query}",
    "generic": "https://docs.github.com/en/search?query={query}",
}


class OfficialResearchRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        absolute = normalize_public_https_redirect(
            req.full_url, newurl, RESEARCH_ALLOWED_HOSTS
        )
        validate_public_https_url(absolute, RESEARCH_ALLOWED_HOSTS)
        require_public_https(absolute, RESEARCH_ALLOWED_HOSTS)
        return super().redirect_request(req, fp, code, msg, headers, absolute)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _clean(value: Any, limit: int = 500) -> str:
    text = str(value or "").replace("\x00", " ")
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _normalized(value: Any) -> str:
    return _clean(value, 400).replace("\\", "/").lstrip("./")


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:20]


def _parse_timestamp(value: Any) -> dt.datetime | None:
    text = _clean(value, 80)
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


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
            "bounded_official_network_research": True,
            "research_network_allowlist_only": True,
            "research_network_failure_blocks_selfrefine": False,
            "research_text_executable": False,
            "search_result_patch_generation": False,
            "learned_text_executable": False,
            "unknown_error_direct_auto_patch": False,
            "code_defined_repairs_only": True,
            "full_regression_required_before_learning": True,
            "failed_verification_not_learned": True,
            "pending_resolution_rule_binding_required": True,
            "pending_resolution_after_hash_required": True,
            "stale_pending_resolution_not_promoted": True,
            "clean_run_skips_redundant_impact_scan": True,
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
            for alias in node.names:
                if alias.name and alias.name != "*":
                    imports.add(f"{node.module}.{alias.name}")
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

    # Build a reverse Python dependency graph once from the already-scanned
    # repository. This exposes second/third-order blast radius without importing
    # or executing project modules.
    module_to_path = {
        _module_name(row["path"]): row["path"]
        for row in index["records"]
        if row["suffix"] == ".py"
    }
    reverse_dependencies: dict[str, set[str]] = {}
    for row in index["records"]:
        if row["suffix"] != ".py":
            continue
        importer_path = row["path"]
        for imported in row["imports"]:
            dependency_path = module_to_path.get(imported)
            if dependency_path and dependency_path != importer_path:
                reverse_dependencies.setdefault(dependency_path, set()).add(
                    importer_path
                )

    dependency_depth: dict[str, int] = {}
    if target in module_to_path.values():
        frontier = [target]
        depth = 0
        visited = {target}
        while frontier and depth < 8:
            depth += 1
            next_frontier: list[str] = []
            for dependency in frontier:
                for importer in sorted(reverse_dependencies.get(dependency, set())):
                    if importer in visited:
                        continue
                    visited.add(importer)
                    dependency_depth[importer] = depth
                    next_frontier.append(importer)
            frontier = next_frontier

    impacted: list[dict[str, Any]] = []
    for row in index["records"]:
        relative = row["path"]
        lower = row["text_lower"]
        score = 0
        reasons: list[str] = []
        depth = dependency_depth.get(relative)
        if relative == target:
            score = 100
            reasons.append("direct_error_path")
        if depth == 1:
            score = max(score, 90)
            reasons.append("python_import_dependency")
        elif depth and depth > 1:
            score = max(score, max(60, 86 - depth * 6))
            reasons.append("transitive_python_dependency")
        elif target_module and row["suffix"] == ".py":
            # Keep conservative textual/import matching for unusual import
            # layouts that cannot be resolved to a tracked module exactly.
            for imported in row["imports"]:
                if imported == target_module or imported.startswith(target_module + "."):
                    score = max(score, 88)
                    reasons.append("python_import_dependency_unresolved_graph")
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
            item = {
                "path": relative,
                "score": score,
                "reasons": sorted(set(reasons)),
            }
            if depth:
                item["dependency_depth"] = depth
            impacted.append(item)

    impacted.sort(key=lambda row: (-int(row["score"]), str(row["path"])))
    return {
        "analysis_scope": "all_main_tracked_code_and_audit_files",
        "files_scanned": int(index["files_scanned"]),
        "scan_truncated": bool(index["scan_truncated"]),
        "full_repository_scan": bool(index["full_repository_scan"]),
        "read_errors": int(index["read_errors"]),
        "python_transitive_dependency_analysis": True,
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


def _search_url(plan: dict[str, Any]) -> str:
    family = str(plan.get("research_family") or "generic")
    template = OFFICIAL_SEARCH_TEMPLATES.get(
        family, OFFICIAL_SEARCH_TEMPLATES["generic"]
    )
    query = str((plan.get("search_queries") or [""])[0])[:300]
    encoded = urllib.parse.quote_plus(query)
    url = template.format(query=encoded)
    # URL construction is syntax/allowlist-only. DNS reachability is checked
    # inside the bounded request loop so an offline device cannot crash error
    # analysis before a deferred research result can be recorded.
    validate_public_https_url(url, RESEARCH_ALLOWED_HOSTS)
    return url


def _html_title(raw: str) -> str:
    match = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw)
    if not match:
        return ""
    title = re.sub(r"(?s)<[^>]+>", " ", match.group(1))
    title = re.sub(r"\s+", " ", title).strip()
    return _clean(title, 240)


def search_official_sources(
    plan: dict[str, Any],
    *,
    request_limit: int = 1,
) -> dict[str, Any]:
    """Perform a bounded lookup against a fixed official-document allowlist.

    The fetched page is reduced to non-executable metadata only. Body text,
    snippets, scripts and examples are never persisted or fed into patch logic.
    """
    limit = max(0, min(2, int(request_limit)))
    if limit <= 0:
        return {
            "attempted": 0,
            "successful": 0,
            "status": "budget_exhausted",
            "results": [],
            "content_used_for_patch": False,
        }
    urls = [_search_url(plan)]
    preferred = [
        value for value in plan.get("preferred_sources", [])
        if isinstance(value, str) and value.startswith("https://")
    ]
    for value in preferred:
        if len(urls) >= limit:
            break
        try:
            validate_public_https_url(value, RESEARCH_ALLOWED_HOSTS)
        except ValueError:
            continue
        if value not in urls:
            urls.append(value)

    opener = urllib.request.build_opener(OfficialResearchRedirect)
    results: list[dict[str, Any]] = []
    for url in urls[:limit]:
        parsed = urllib.parse.urlsplit(url)
        host = (parsed.hostname or "").lower()
        try:
            require_public_https(url, RESEARCH_ALLOWED_HOSTS)
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "TCG-Grader-SELFREFINE-Research/1.0"},
            )
            with opener.open(
                request, timeout=NETWORK_RESEARCH_TIMEOUT_SECONDS
            ) as response:
                final_url = response.geturl()
                validate_public_https_url(final_url, RESEARCH_ALLOWED_HOSTS)
                require_public_https(final_url, RESEARCH_ALLOWED_HOSTS)
                raw = response.read(NETWORK_RESEARCH_MAX_BYTES)
                content_type = str(response.headers.get("Content-Type") or "")[:120]
                decoded = raw.decode("utf-8", "replace")
                results.append({
                    "host": host,
                    "http_status": int(getattr(response, "status", 200) or 200),
                    "title": _html_title(decoded),
                    "content_type": _clean(content_type, 120),
                    "bytes_sampled": len(raw),
                    "status": "reachable",
                })
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            TimeoutError,
            OSError,
            ValueError,
        ) as exc:
            results.append({
                "host": host,
                "http_status": int(exc.code)
                if isinstance(exc, urllib.error.HTTPError) else None,
                "title": "",
                "content_type": "",
                "bytes_sampled": 0,
                "status": "unavailable",
                "error_type": type(exc).__name__,
            })

    successful = sum(row.get("status") == "reachable" for row in results)
    return {
        "attempted": len(results),
        "successful": successful,
        "status": "researched" if successful else "deferred",
        "results": results,
        "content_used_for_patch": False,
        "search_result_patch_generation": False,
        "raw_body_persisted": False,
    }


def observe_errors(
    errors: list[dict[str, Any]],
    *,
    root: Path = ROOT,
    state_path: Path = STATE,
    report_path: Path = REPORT,
    network_research: bool = True,
) -> dict[str, Any]:
    open_errors = [
        row for row in errors[:MAX_ISSUES]
        if isinstance(row, dict) and row.get("state") == "open"
    ]
    now = _now()

    # Main SELFREFINE already scanned the repository to determine that there are
    # no open errors. A second full impact index on a clean run adds I/O and
    # battery/CI cost without producing any diagnosis.
    if not open_errors:
        with exclusive_file_lock(state_path):
            state = _load_state(state_path)
            pending = set(state.get("pending_verifications", {}))
            for signature, issue in state.get("issues", {}).items():
                if (
                    isinstance(issue, dict)
                    and issue.get("status") == "open"
                    and signature not in pending
                ):
                    issue["status"] = "not_observed_unverified"
                    issue["last_clean_seen"] = now
                    state.setdefault("history", []).append({
                        "at": now,
                        "error_signature": signature,
                        "event": "error_not_observed_without_verified_repair",
                    })
            _save_state(state_path, state)
        report = {
            "schema": SCHEMA,
            "generated_at": now,
            "error_count": 0,
            "new_error_count": 0,
            "known_verified_resolution_count": 0,
            "repository_files_scanned": 0,
            "full_repository_scan": True,
            "impact_scan_required": False,
            "impact_scan_skipped_no_open_errors": True,
            "scan_truncated": False,
            "read_errors": 0,
            "network_research_attempted": 0,
            "network_research_successful": 0,
            "errors": [],
            "safety": _default_state()["safety"],
        }
        atomic_write_json(report_path, report, suffix=".resolution-research.tmp")
        return report

    index = build_repository_index(root)

    # Read only the small identity/lesson snapshot while holding the process-safe
    # state lock. Network research can take several seconds and must never block
    # another SELFREFINE process from reading/writing its local learning state.
    with exclusive_file_lock(state_path):
        snapshot = _load_state(state_path)
        previously_seen = set(snapshot.get("issues", {}))
        known_lessons = {
            key: dict(value)
            for key, value in snapshot.get("lessons", {}).items()
            if isinstance(value, dict)
        }

    prepared: list[dict[str, Any]] = []
    network_budget = MAX_NETWORK_RESEARCH_REQUESTS
    for issue in open_errors:
        signature = _safe_signature(issue)
        impact = analyze_repository_impact(issue, index=index, root=root)
        research = research_plan(issue)
        was_seen = signature in previously_seen
        if network_research and not was_seen and network_budget > 0:
            network_result = search_official_sources(
                research, request_limit=min(2, network_budget)
            )
            network_budget -= int(network_result.get("attempted") or 0)
        else:
            network_result = {
                "attempted": 0,
                "successful": 0,
                "status": "not_required" if was_seen else "disabled",
                "results": [],
                "content_used_for_patch": False,
                "search_result_patch_generation": False,
                "raw_body_persisted": False,
            }
        prepared.append({
            "issue": dict(issue),
            "signature": signature,
            "impact": impact,
            "research": research,
            "network_research": network_result,
            "snapshot_lesson": known_lessons.get(signature),
        })

    observations: list[dict[str, Any]] = []
    with exclusive_file_lock(state_path):
        # Reload before merge. Another process may have observed the same error
        # while this process performed bounded network research.
        state = _load_state(state_path)
        issues = state.setdefault("issues", {})
        lessons = state.setdefault("lessons", {})
        observed_signatures = {row["signature"] for row in prepared}
        pending_signatures = set(state.get("pending_verifications", {}))
        for signature, previous_issue in issues.items():
            if (
                isinstance(previous_issue, dict)
                and previous_issue.get("status") == "open"
                and signature not in observed_signatures
                and signature not in pending_signatures
            ):
                previous_issue["status"] = "not_observed_unverified"
                previous_issue["last_clean_seen"] = now
                state.setdefault("history", []).append({
                    "at": now,
                    "error_signature": signature,
                    "event": "error_not_observed_without_verified_repair",
                })
        for prepared_row in prepared:
            issue = prepared_row["issue"]
            signature = prepared_row["signature"]
            previous = (
                issues.get(signature)
                if isinstance(issues.get(signature), dict)
                else {}
            )
            recurrence = max(0, int(previous.get("recurrence_count") or 0)) + 1
            lesson = (
                lessons.get(signature)
                if isinstance(lessons.get(signature), dict)
                else prepared_row.get("snapshot_lesson")
            )
            is_new = not bool(previous)
            network_result = dict(prepared_row["network_research"])
            # If a concurrent process recorded the same signature first, retain
            # the bounded evidence we already collected but classify this merge
            # as a recurrence rather than a second new error.
            if not is_new and network_result.get("attempted"):
                network_result["status"] = (
                    "researched_concurrently"
                    if network_result.get("successful")
                    else "deferred_concurrently"
                )

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
                "new_error": is_new,
                "impact_analysis": prepared_row["impact"],
                "research": prepared_row["research"],
                "network_research": network_result,
                "known_verified_resolution": bool(
                    lesson and lesson.get("regression_pass") is True
                ),
                "preferred_verified_fix_pattern": (
                    _clean(lesson.get("fix_pattern"), 300)
                    if lesson and lesson.get("regression_pass") is True
                    else ""
                ),
            }
            issues[signature] = row
            observations.append(row)
            state.setdefault("history", []).append({
                "at": now,
                "error_signature": signature,
                "event": (
                    "new_error_researched"
                    if row["new_error"]
                    else "recurring_error_researched"
                ),
                "research_fingerprint": prepared_row["research"]["research_fingerprint"],
                "files_scanned": prepared_row["impact"]["files_scanned"],
                "network_research_status": network_result.get("status"),
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
        "network_research_attempted": sum(
            int((row.get("network_research") or {}).get("attempted") or 0)
            for row in observations
        ),
        "network_research_successful": sum(
            int((row.get("network_research") or {}).get("successful") or 0)
            for row in observations
        ),
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
    import verified_code_repair_rules as verified_repairs

    staged = 0
    skipped = 0
    skip_reasons: dict[str, int] = {}
    now = _now()

    def skip(reason: str) -> None:
        nonlocal skipped
        skipped += 1
        skip_reasons[reason] = skip_reasons.get(reason, 0) + 1

    with exclusive_file_lock(state_path):
        state = _load_state(state_path)
        for item in applied:
            if not isinstance(item, dict):
                skip("invalid_item")
                continue
            signature = _clean(item.get("error_signature"), 80).lower()
            issue = state.get("issues", {}).get(signature)
            if not signature or not isinstance(issue, dict):
                skip("missing_observed_issue")
                continue

            rule_id = _clean(item.get("rule_id"), 160)
            relative = _normalized(item.get("path"))
            fingerprint = _clean(item.get("rule_fingerprint"), 80)
            before_hash = _clean(item.get("before_hash"), 40).lower()
            after_hash = _clean(item.get("after_hash"), 40).lower()
            if (
                item.get("verification_forced_failed") is True
                or item.get("rollback_outcome") != "verified_kept"
            ):
                skip("repair_not_locally_verified")
                continue
            rule_probe = {"stage": _clean(item.get("stage"), 100), "path": relative}
            if (
                rule_id not in verified_repairs.ALL_RULE_IDS
                or relative not in verified_repairs.RULE_PATHS.get(rule_id, frozenset())
                or fingerprint != verified_repairs.rule_fingerprint(rule_id)
                or verified_repairs.rule_for_issue(rule_probe) != rule_id
            ):
                skip("repair_rule_binding_mismatch")
                continue
            if relative != _normalized(issue.get("path")):
                skip("issue_path_binding_mismatch")
                continue
            if not re.fullmatch(r"[0-9a-f]{20}", before_hash or ""):
                skip("before_hash_missing")
                continue
            if not re.fullmatch(r"[0-9a-f]{20}", after_hash or ""):
                skip("after_hash_missing")
                continue

            state.setdefault("pending_verifications", {})[signature] = {
                "error_signature": signature,
                "rule_id": rule_id,
                "rule_fingerprint": fingerprint,
                "path": relative,
                "stage": _clean(item.get("stage"), 100),
                "staged_at": now,
                "verification_status": "pending_full_regression",
                "before_hash": before_hash,
                "after_hash": after_hash,
                "research_fingerprint": _clean(
                    (issue.get("research") or {}).get("research_fingerprint"), 80
                ),
                "impact_files": [
                    row.get("path")
                    for row in (issue.get("impact_analysis") or {}).get("impacted_files", [])[:20]
                    if isinstance(row, dict)
                ],
            }
            issue["status"] = "pending_full_regression"
            staged += 1
            state.setdefault("history", []).append({
                "at": now,
                "error_signature": signature,
                "event": "repair_pending_full_regression",
                "rule_id": rule_id,
                "after_hash": after_hash,
            })
        _save_state(state_path, state)
    return {
        "pending_full_regression": staged,
        "skipped_unverified_repairs": skipped,
        "skip_reasons": skip_reasons,
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
    root: Path = ROOT,
) -> dict[str, Any]:
    import verified_code_repair_rules as verified_repairs

    verified = rejected = binding_rejected = 0
    now = _now()
    now_dt = _parse_timestamp(now) or dt.datetime.now(dt.timezone.utc)
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
            relative = _normalized(pending_row.get("path"))
            fingerprint = _clean(pending_row.get("rule_fingerprint"), 80)
            after_hash = _clean(pending_row.get("after_hash"), 40).lower()
            staged_at = _parse_timestamp(pending_row.get("staged_at"))

            binding_reason = ""
            if success:
                rule_probe = {
                    "stage": _clean(pending_row.get("stage"), 100),
                    "path": relative,
                }
                if (
                    rule_id not in verified_repairs.ALL_RULE_IDS
                    or relative not in verified_repairs.RULE_PATHS.get(rule_id, frozenset())
                    or verified_repairs.rule_for_issue(rule_probe) != rule_id
                ):
                    binding_reason = "repair_rule_not_allowlisted"
                elif fingerprint != verified_repairs.rule_fingerprint(rule_id):
                    binding_reason = "repair_rule_fingerprint_changed"
                elif relative != _normalized(issue.get("path")):
                    binding_reason = "issue_path_binding_changed"
                elif not re.fullmatch(r"[0-9a-f]{20}", after_hash or ""):
                    binding_reason = "after_hash_missing"
                elif staged_at is None:
                    binding_reason = "invalid_staged_at"
                elif (
                    (now_dt - staged_at).total_seconds() < 0
                    or (now_dt - staged_at).total_seconds() > MAX_PENDING_AGE_SECONDS
                ):
                    binding_reason = "pending_verification_expired"
                else:
                    target = root / relative
                    try:
                        if target.is_symlink() or not target.is_file():
                            raise OSError("repair target is not a regular file")
                        current_hash = _text_hash(
                            safe_read_text(target, max_bytes=MAX_FILE_BYTES)
                        )
                    except (OSError, ValueError, TypeError, UnicodeError):
                        binding_reason = "repair_target_unreadable"
                    else:
                        if current_hash != after_hash:
                            binding_reason = "repair_target_hash_changed"

                if binding_reason:
                    issue["status"] = "verification_binding_rejected"
                    issue["last_verification_rejection"] = binding_reason
                    binding_rejected += 1
                    rejected += 1
                    state.setdefault("history", []).append({
                        "at": now,
                        "error_signature": signature,
                        "event": "resolution_binding_rejected",
                        "rule_id": rule_id,
                        "reason": binding_reason,
                    })
                    state.setdefault("pending_verifications", {}).pop(signature, None)
                    continue

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
        "binding_rejected_resolutions": binding_rejected,
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
    import verified_code_repair_rules as verified_repairs

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
            [issue],
            root=root,
            state_path=state,
            report_path=report,
            network_research=False,
        )
        assert observed["new_error_count"] == 1, observed
        impacted = {
            row["path"]
            for row in observed["errors"][0]["impact_analysis"]["impacted_files"]
        }
        assert {"broken.py", "consumer.py", "test_broken.py"}.issubset(impacted), impacted
        assert observed["errors"][0]["research"]["preferred_sources"]
        assert observed["errors"][0]["research"]["patch_from_search_text_allowed"] is False

        repair_target = root / verified_repairs.RESOURCE_GUARD_PATH
        repair_target.write_text(
            "from pathlib import Path\n"
            "x = Path('a.js').read_text(encoding='utf-8')\n",
            encoding="utf-8",
        )
        repair_signature = "b" * 20
        repair_issue = {
            "error_signature": repair_signature,
            "error_code": "SELFREFINE.RESOURCE_HANDLE_LEAK_RISK",
            "stage": "RESOURCE_HANDLE_LEAK_RISK",
            "path": verified_repairs.RESOURCE_GUARD_PATH,
            "root_cause": "unclosed literal text read",
            "evidence": "open(...).read() can leave a file handle",
            "state": "open",
        }
        observe_errors(
            [repair_issue],
            root=root,
            state_path=state,
            report_path=report,
            network_research=False,
        )
        applied = {
            "error_signature": repair_signature,
            "rule_id": verified_repairs.RESOURCE_RULE_ID,
            "rule_fingerprint": verified_repairs.rule_fingerprint(
                verified_repairs.RESOURCE_RULE_ID
            ),
            "path": verified_repairs.RESOURCE_GUARD_PATH,
            "stage": "RESOURCE_HANDLE_LEAK_RISK",
            "before_hash": _text_hash("old content"),
            "after_hash": _text_hash(repair_target.read_text(encoding="utf-8")),
            "rollback_outcome": "verified_kept",
        }
        staged = stage_repairs([applied], state_path=state)
        assert staged["pending_full_regression"] == 1, staged
        assert not _load_state(state)["lessons"], "must not learn before full regression"

        finalized = finalize_pending(True, state_path=state, root=root)
        assert finalized["verified_resolution_lessons"] == 1, finalized
        lesson = _load_state(state)["lessons"][repair_signature]
        assert lesson["regression_pass"] is True
        assert lesson["verification_result"] == "full_regression_passed"
        assert lesson["fix_pattern"] == (
            f"verified_code_rule:{verified_repairs.RESOURCE_RULE_ID}"
        )

        clean = observe_errors(
            [],
            root=root,
            state_path=state,
            report_path=report,
            network_research=False,
        )
        assert clean["impact_scan_skipped_no_open_errors"] is True
        assert clean["repository_files_scanned"] == 0

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
