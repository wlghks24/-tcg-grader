#!/usr/bin/env python3
"""Read-only Graphify code-map intelligence for AI automatic tracking.

The code map is advisory:
- reads graphify-out/graph.json when available;
- never turns learned text into commands or patches;
- reports bounded dependency/impact neighborhoods;
- learns only from repairs that are explicitly verified and full-regression-passed.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, deque
from pathlib import Path
from typing import Any, Iterable

GRAPH_RELATIVE = Path("graphify-out/graph.json")
AUDIT_RELATIVE = Path("graphify-out/graph_audit.json")
MAX_GRAPH_BYTES = 40 * 1024 * 1024
MAX_IMPACT_FILES = 24
MAX_MATCHED_NODES = 12
MAX_LEARNING_PATTERNS = 200
PATH_KEYS = (
    "source_file", "file_path", "filepath", "filename", "path", "file", "module_path",
)


def _norm(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def _rows(data: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def _node_id(row: dict[str, Any], index: int) -> str:
    for key in ("id", "key", "name"):
        if row.get(key) is not None:
            return str(row[key])
    return f"__index__:{index}"


def _endpoint(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("id", "key", "name"):
            if value.get(key) is not None:
                return str(value[key])
        return ""
    return "" if value is None else str(value)


def _node_path(row: dict[str, Any]) -> str:
    for key in PATH_KEYS:
        value = _norm(row.get(key))
        if value:
            return value
    return ""


def _safe_json(path: Path) -> dict[str, Any] | None:
    try:
        if not path.is_file() or path.stat().st_size <= 0 or path.stat().st_size > MAX_GRAPH_BYTES:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError):
        return None


def _matches(origin: str, candidate: str) -> bool:
    a = _norm(origin).lower()
    b = _norm(candidate).lower()
    if not a or not b:
        return False
    if a == b or a.endswith("/" + b) or b.endswith("/" + a):
        return True
    return Path(a).name == Path(b).name


def impact_context(
    root: Path,
    origin_path: str,
    *,
    depth: int = 2,
    limit: int = MAX_IMPACT_FILES,
) -> dict[str, Any]:
    root = Path(root)
    graph_path = root / GRAPH_RELATIVE
    graph = _safe_json(graph_path)
    origin = _norm(origin_path)
    if graph is None:
        return {
            "available": False,
            "status": "missing_or_invalid",
            "origin_path": origin,
            "graph_path": str(GRAPH_RELATIVE),
            "matched_nodes": [],
            "impacted_files": [],
            "depth": max(0, min(4, int(depth))),
        }

    nodes = _rows(graph, "nodes")
    links = _rows(graph, "links", "edges")
    ids: list[str] = []
    path_by_id: dict[str, str] = {}
    for index, row in enumerate(nodes):
        nid = _node_id(row, index)
        ids.append(nid)
        path = _node_path(row)
        if path:
            path_by_id[nid] = path

    adjacency: dict[str, set[str]] = {nid: set() for nid in ids}
    degree: Counter[str] = Counter()
    for link in links:
        source = _endpoint(link.get("source"))
        target = _endpoint(link.get("target"))
        if not source or not target:
            continue
        adjacency.setdefault(source, set()).add(target)
        adjacency.setdefault(target, set()).add(source)
        degree[source] += 1
        degree[target] += 1

    matched = [nid for nid, path in path_by_id.items() if _matches(origin, path)]
    matched = matched[:MAX_MATCHED_NODES]
    max_depth = max(0, min(4, int(depth)))
    visited = set(matched)
    queue = deque((nid, 0) for nid in matched)
    while queue:
        current, level = queue.popleft()
        if level >= max_depth:
            continue
        for neighbor in sorted(adjacency.get(current, ())):
            if neighbor in visited:
                continue
            visited.add(neighbor)
            queue.append((neighbor, level + 1))

    impacted_files: list[str] = []
    for nid in visited:
        path = path_by_id.get(nid)
        if path and path not in impacted_files:
            impacted_files.append(path)
    impacted_files.sort(key=lambda value: (0 if _matches(origin, value) else 1, value))
    impacted_files = impacted_files[: max(1, min(MAX_IMPACT_FILES, int(limit)))]

    audit = _safe_json(root / AUDIT_RELATIVE) or {}
    top_hubs = audit.get("top_hubs") if isinstance(audit.get("top_hubs"), list) else [
        {"node": node, "degree": count} for node, count in degree.most_common(8)
    ]

    return {
        "available": True,
        "status": "ok" if matched else "origin_not_mapped",
        "origin_path": origin,
        "graph_path": str(GRAPH_RELATIVE),
        "node_count": len(nodes),
        "edge_count": len(links),
        "matched_nodes": matched,
        "impacted_files": impacted_files,
        "depth": max_depth,
        "top_hubs": [row for row in top_hubs[:8] if isinstance(row, dict)],
        "read_only": True,
    }


def verified_learning_candidate(
    *,
    origin_path: str,
    changed_files: Iterable[str],
    impact: dict[str, Any],
    verified: bool,
    regression_pass: bool,
) -> dict[str, Any] | None:
    changed = sorted({_norm(value) for value in changed_files if _norm(value)})[:32]
    origin = _norm(origin_path)
    if not verified or not regression_pass or not origin or not changed:
        return None
    predicted = sorted({_norm(value) for value in (impact.get("impacted_files") or []) if _norm(value)})
    predicted_set = set(predicted)
    hits = [path for path in changed if path in predicted_set]
    misses = [path for path in changed if path not in predicted_set]
    key = hashlib.sha256(origin.lower().encode("utf-8", "replace")).hexdigest()[:20]
    return {
        "pattern_key": key,
        "origin_path": origin,
        "changed_files": changed,
        "predicted_hits": hits,
        "predicted_misses": misses,
        "map_available": bool(impact.get("available")),
        "verification": "full_regression_verified",
    }


def default_learning_state() -> dict[str, Any]:
    return {
        "schema": 1,
        "verified_patterns": {},
        "verified_learning_only": True,
        "learned_text_executable": False,
    }


def merge_verified_learning(state: dict[str, Any], rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    raw = state.get("code_map_learning")
    learning = raw if isinstance(raw, dict) else default_learning_state()
    patterns = learning.get("verified_patterns")
    if not isinstance(patterns, dict):
        patterns = {}

    for row in rows:
        if not isinstance(row, dict) or row.get("verification") != "full_regression_verified":
            continue
        key = str(row.get("pattern_key") or "")[:40]
        origin = _norm(row.get("origin_path"))
        if not key or not origin:
            continue
        current = patterns.get(key) if isinstance(patterns.get(key), dict) else {}
        current["origin_path"] = origin
        current["verified_count"] = min(1_000_000, int(current.get("verified_count") or 0) + 1)
        current["map_available"] = bool(row.get("map_available"))
        counts = current.get("changed_file_counts")
        if not isinstance(counts, dict):
            counts = {}
        for path in row.get("changed_files") or []:
            clean = _norm(path)
            if clean:
                counts[clean] = min(1_000_000, int(counts.get(clean) or 0) + 1)
        current["changed_file_counts"] = dict(sorted(
            counts.items(), key=lambda item: (-int(item[1]), item[0])
        )[:32])
        current["last_predicted_hits"] = list(row.get("predicted_hits") or [])[:32]
        current["last_predicted_misses"] = list(row.get("predicted_misses") or [])[:32]
        patterns[key] = current

    if len(patterns) > MAX_LEARNING_PATTERNS:
        ranked = sorted(
            patterns.items(),
            key=lambda item: (int(item[1].get("verified_count") or 0), item[0]),
            reverse=True,
        )[:MAX_LEARNING_PATTERNS]
        patterns = dict(ranked)

    learning["schema"] = 1
    learning["verified_patterns"] = patterns
    learning["verified_learning_only"] = True
    learning["learned_text_executable"] = False
    state["code_map_learning"] = learning
    return learning


def compact_context(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "available": bool(value.get("available")),
        "status": str(value.get("status") or "")[:40],
        "origin_path": _norm(value.get("origin_path")),
        "matched_nodes": list(value.get("matched_nodes") or [])[:8],
        "impacted_files": [_norm(x) for x in (value.get("impacted_files") or []) if _norm(x)][:16],
        "depth": int(value.get("depth") or 0),
        "read_only": True,
    }
