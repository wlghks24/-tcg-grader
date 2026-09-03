#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Structural/quality audit for the local Graphify code map.

The audit is intentionally local and deterministic:
- no network access
- no LLM/API key
- no source-code writes
- no Git writes

It verifies graph structure, checks that files excluded by .graphifyignore/.gitignore
did not leak into the architecture map, and reports map size / hub concentration so
tablet-side bloat is visible before it becomes a problem.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent
DEFAULT_GRAPH = ROOT / "graphify-out" / "graph.json"
DEFAULT_REPORT = ROOT / "graphify-out" / "graph_audit.json"
IGNORE_FILES = (ROOT / ".graphifyignore", ROOT / ".gitignore")

# These are safety backstops even if an ignore file is accidentally edited.
ALWAYS_FORBIDDEN_PATTERNS = (
    "graphify-out/",
    ".git/",
    ".tcg_runtime_preserved/",
    "GRADE_TRAINING_INBOX/",
    "__pycache__/",
    ".pytest_cache/",
    "node_modules/",
)

NODE_PATH_KEYS = (
    "source_file",
    "file_path",
    "filepath",
    "filename",
    "path",
    "file",
    "module_path",
)


def _load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"graph file missing: {path}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"graph file unreadable: {type(exc).__name__}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("graph root must be a JSON object")
    return data


def _rows(data: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def _node_id(row: dict[str, Any], fallback: int) -> str:
    value = row.get("id")
    if value is None:
        value = row.get("key")
    if value is None:
        value = row.get("name")
    if value is None:
        return f"__index__:{fallback}"
    return str(value)


def _endpoint(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("id", "key", "name"):
            if value.get(key) is not None:
                return str(value[key])
        return None
    if value is None:
        return None
    return str(value)


def _normalize_path(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().replace("\\", "/")
    if not text:
        return None
    return text


def _node_paths(nodes: Iterable[dict[str, Any]]) -> list[str]:
    paths: list[str] = []
    for row in nodes:
        for key in NODE_PATH_KEYS:
            path = _normalize_path(row.get(key))
            if path:
                paths.append(path)
                break
    return paths


def _load_ignore_rules() -> tuple[list[tuple[bool, str, str]], list[str]]:
    """Return ordered (negated, pattern, source) rules plus read errors.

    Ordered evaluation gives basic gitignore-compatible negation behavior, e.g.
    `.env.*` followed by `!.env.example`.
    """
    rules: list[tuple[bool, str, str]] = []
    errors: list[str] = []
    for pattern in ALWAYS_FORBIDDEN_PATTERNS:
        rules.append((False, pattern, "built-in safety"))

    for ignore_path in IGNORE_FILES:
        try:
            text = ignore_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            errors.append(f"cannot read {ignore_path.name}: {type(exc).__name__}: {exc}")
            continue
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            negated = line.startswith("!")
            if negated:
                line = line[1:].strip()
            if not line:
                continue
            rules.append((negated, line.replace("\\", "/"), ignore_path.name))
    return rules, errors


def _path_candidates(path: str) -> list[str]:
    normalized = path.replace("\\", "/")
    candidates = [normalized, normalized.lstrip("./")]
    try:
        absolute = Path(normalized)
        if absolute.is_absolute():
            candidates.append(absolute.relative_to(ROOT).as_posix())
    except (OSError, ValueError):
        pass
    # Stable de-duplication.
    return list(dict.fromkeys(candidate for candidate in candidates if candidate))


def _rule_matches(path: str, pattern: str) -> bool:
    pattern = pattern.replace("\\", "/")
    anchored = pattern.startswith("/")
    if anchored:
        pattern = pattern[1:]
    if not pattern:
        return False

    candidates = _path_candidates(path)
    directory_rule = pattern.endswith("/")
    core = pattern.rstrip("/")

    for candidate in candidates:
        clean = candidate.lstrip("./")
        parts = [part for part in clean.split("/") if part]
        basename = parts[-1] if parts else clean

        if directory_rule:
            if anchored:
                if clean == core or clean.startswith(core + "/"):
                    return True
            elif clean == core or clean.startswith(core + "/") or f"/{core}/" in f"/{clean}/":
                return True
            continue

        if "/" in core:
            if fnmatch.fnmatch(clean, core) or (not anchored and fnmatch.fnmatch(clean, f"*/{core}")):
                return True
        else:
            if fnmatch.fnmatch(basename, core) or any(fnmatch.fnmatch(part, core) for part in parts):
                return True
    return False


def _ignored_reason(path: str, rules: list[tuple[bool, str, str]]) -> str | None:
    ignored = False
    reason: str | None = None
    for negated, pattern, source in rules:
        if _rule_matches(path, pattern):
            ignored = not negated
            reason = None if negated else f"{source}:{pattern}"
    return reason if ignored else None


def _path_leaks(
    paths: Iterable[str], rules: list[tuple[bool, str, str]],
) -> list[str]:
    leaks: list[str] = []
    for path in paths:
        reason = _ignored_reason(path, rules)
        if reason:
            leaks.append(f"{path} [{reason}]")
    # Stable de-duplication; cap report size in case a malformed graph repeats paths.
    return list(dict.fromkeys(leaks))[:100]


def audit(graph_path: Path) -> dict[str, Any]:
    data = _load(graph_path)
    nodes = _rows(data, "nodes")
    links = _rows(data, "links", "edges")

    errors: list[str] = []
    warnings: list[str] = []

    rules, ignore_errors = _load_ignore_rules()
    if ignore_errors:
        errors.extend(ignore_errors)

    if not nodes:
        errors.append("graph has no nodes")

    ids = [_node_id(row, index) for index, row in enumerate(nodes)]
    id_counts = Counter(ids)
    duplicate_ids = sorted(key for key, count in id_counts.items() if count > 1)
    if duplicate_ids:
        errors.append(f"duplicate node ids: {duplicate_ids[:10]}")

    known_ids = set(ids)
    degree: Counter[str] = Counter()
    malformed_links = 0
    dangling_links = 0
    dangling_samples: list[str] = []

    # Only enforce referential integrity when Graphify supplied explicit node IDs.
    explicit_id_count = sum(1 for row in nodes if row.get("id") is not None)
    can_verify_endpoints = bool(nodes) and explicit_id_count == len(nodes)

    for index, link in enumerate(links):
        source = _endpoint(link.get("source"))
        target = _endpoint(link.get("target"))
        if source is None or target is None:
            malformed_links += 1
            continue
        degree[source] += 1
        degree[target] += 1
        if can_verify_endpoints and (source not in known_ids or target not in known_ids):
            dangling_links += 1
            if len(dangling_samples) < 10:
                dangling_samples.append(f"#{index}:{source}->{target}")

    if malformed_links:
        errors.append(f"malformed links without source/target: {malformed_links}")
    if dangling_links:
        errors.append(f"dangling links: {dangling_links} samples={dangling_samples}")

    paths = _node_paths(nodes)
    leaks = _path_leaks(paths, rules)
    if leaks:
        errors.append(f"ignored/runtime/control-plane paths leaked into code map: {leaks[:20]}")

    unique_files = sorted(set(paths))
    graph_bytes = graph_path.stat().st_size
    edge_count = len(links)
    node_count = len(nodes)

    top_hubs = [
        {"node": node, "degree": count}
        for node, count in degree.most_common(10)
    ]
    hub_ratio = 0.0
    if edge_count and top_hubs:
        hub_ratio = top_hubs[0]["degree"] / max(1, edge_count)
        if node_count >= 25 and hub_ratio >= 0.50:
            warnings.append(
                "top hub touches at least 50% of graph edges; consider hub-suppressed reclustering "
                "(cluster-only --exclude-hubs 99) if navigation quality is poor"
            )

    if graph_bytes > 25 * 1024 * 1024:
        warnings.append("graph.json exceeds 25 MiB; review ignore scope for tablet efficiency")
    if node_count >= 100 and edge_count == 0:
        warnings.append("large graph has no links; call/dependency extraction may be incomplete")
    if nodes and not paths:
        warnings.append("no source-file metadata found on nodes; path-scope leak checks were limited")

    return {
        "ok": not errors,
        "graph": str(graph_path),
        "node_count": node_count,
        "edge_count": edge_count,
        "source_file_count": len(unique_files),
        "graph_bytes": graph_bytes,
        "top_hub_edge_ratio": round(hub_ratio, 4),
        "top_hubs": top_hubs,
        "ignore_rule_count": len(rules),
        "ignore_sources": [path.name for path in IGNORE_FILES],
        "path_leak_count": len(leaks),
        "path_leaks": leaks,
        "malformed_link_count": malformed_links,
        "dangling_link_count": dangling_links,
        "errors": errors,
        "warnings": warnings,
        "policy": {
            "network_used": False,
            "source_code_written": False,
            "git_written": False,
            "runtime_state_excluded": True,
            "ignore_policy_synced": not ignore_errors,
        },
    }


def _write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Graphify code-map structure and tablet-oriented scope")
    parser.add_argument("--graph", default=str(DEFAULT_GRAPH), help="path to graph.json")
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="path for local JSON audit report")
    parser.add_argument("--strict", action="store_true", help="return non-zero for structural/scope errors")
    parser.add_argument("--no-write", action="store_true", help="do not write graph_audit.json")
    args = parser.parse_args()

    try:
        result = audit(Path(args.graph))
    except ValueError as exc:
        result = {
            "ok": False,
            "graph": str(args.graph),
            "errors": [str(exc)],
            "warnings": [],
        }

    if not args.no_write:
        try:
            _write_report(Path(args.report), result)
        except OSError as exc:
            result.setdefault("errors", []).append(f"audit report write failed: {type(exc).__name__}: {exc}")
            result["ok"] = False

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.strict and not result.get("ok", False):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
