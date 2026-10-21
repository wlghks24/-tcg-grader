#!/usr/bin/env python3
"""Read-only impact/review adapter on TCG's existing tracked Python atlas.

Never installs/runs external agents, scrapes the web, or modifies a source file.
"""
from __future__ import annotations

import argparse
from collections import defaultdict, deque
import json
from pathlib import Path, PurePosixPath

try:
    from execution.tablet_code_map_audit import ROOT, build
except ModuleNotFoundError:
    from tablet_code_map_audit import ROOT, build

MAX_CHANGED = 12
MAX_IMPACT = 40
MAX_DEPTH = 3
MAX_TESTS = 12
UPSTREAM = {
    "REA": ("https://github.com/morluto/rea", "HOLD_AUTHORIZED_BINARY"),
    "Agent Reach": ("https://github.com/Panniantong/agent-reach", "REVIEW_PUBLIC_EVIDENCE_ONLY"),
    "Graft": ("https://github.com/trailhq/Graft", "LOCAL_MAP_ADAPTER_ONLY"),
    "Agency Agents": ("https://github.com/msitarzewski/agency-agents", "REVIEW_ROLES_ONLY"),
    "Codebase Memory MCP": ("https://github.com/DeusData/codebase-memory-mcp", "LOCAL_MAP_ADAPTER_ONLY"),
}
REVIEW_ROLES = (
    "architecture_impact", "grading_calibration",
    "market_source_provenance", "security_and_privacy",
    "regression_and_ci", "independent_evidence",
)


class ReviewBlocked(ValueError):
    """Fail-closed validation of changes and map inputs."""


def _validate_changed(root: Path, paths: list[str], known: set[str]) -> list[str]:
    if not (1 <= len(paths) <= MAX_CHANGED) or len(paths) != len(set(paths)):
        raise ReviewBlocked("invalid_changed_count")
    for item in paths:
        if not isinstance(item, str) or not item or item not in known:
            raise ReviewBlocked("unknown_or_untracked_python_file")
        if "\\" in item or ":" in item or "\x00" in item or not item.endswith(".py"):
            raise ReviewBlocked("invalid_python_path")
        parsed = PurePosixPath(item)
        if parsed.is_absolute() or any(p in (".", "..", "") for p in item.split("/")):
            raise ReviewBlocked("unsafe_relative_path")
        current = root
        for part in parsed.parts:
            current = current / part
            if current.is_symlink():
                raise ReviewBlocked("symlink_path")
        if not current.is_file():
            raise ReviewBlocked("missing_regular_file")
    return sorted(paths)


def review(root: Path, changed: list[str], *, depth: int = 2, limit: int = 24) -> dict:
    if type(depth) is not int or not 0 <= depth <= MAX_DEPTH:
        raise ReviewBlocked("invalid_depth")
    if type(limit) is not int or not 1 <= limit <= MAX_IMPACT:
        raise ReviewBlocked("invalid_limit")
    atlas = build(root)
    edges = atlas["local_import_edges"]
    changed = _validate_changed(root, changed, set(edges) | {issue["path"] for issue in atlas["parse_issues"]})
    reverse = defaultdict(set)
    for source, targets in edges.items():
        for target in targets:
            reverse[target].add(source)
    distance = {p: 0 for p in changed}
    queue = deque(changed)
    while queue:
        current = queue.popleft()
        if distance[current] >= depth:
            continue
        for user in sorted(reverse.get(current, ())):
            if user not in distance:
                distance[user] = distance[current] + 1
                queue.append(user)
    impacted = sorted((p for p in distance if p not in changed),
                      key=lambda p: (distance[p], p))
    candidates = sorted((p for p in distance if PurePosixPath(p).name.startswith("test_")),
                        key=lambda p: (distance[p], p))[:MAX_TESTS]
    parse_issues = sorted(issue["path"] for issue in atlas["parse_issues"]
                          if issue.get("path") in distance)
    incomplete = len(impacted) > limit or bool(parse_issues)
    return {
        "schema_version": 1,
        "project": "TCG_Grader_only",
        "mode": "offline_read_only",
        "source": "execution.tablet_code_map_audit.build",
        "changed": changed,
        "tracked_count": atlas["tracked_count"],
        "affected": [{"path": p, "import_hops": distance[p]} for p in impacted[:limit]],
        "affected_total": len(impacted),
        "truncated": len(impacted) > limit,
        "suggested_tests": candidates,
        "affected_parse_issues": parse_issues,
        "review_state": "HOLD_INCOMPLETE_MAP" if incomplete else "CANDIDATE_ONLY",
        "review_roles": list(REVIEW_ROLES),
        "tools": {name: {"upstream": url, "state": state}
                  for name, (url, state) in UPSTREAM.items()},
        "restrictions": [
            "External tools are NOT installed or executed by this audit.",
            "Static Python imports only; dynamic calls and JS/UI paths not covered.",
            "No proof of CodeQL/required CI, real TCG data, or physical Lenovo test.",
            "Existing Graphify/skill/rollback/approval gates remain authoritative.",
        ],
        "physical_device_verified": False,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--changed", action="append", required=True)
    ap.add_argument("--depth", type=int, default=2)
    ap.add_argument("--limit", type=int, default=24)
    args = ap.parse_args()
    try:
        report = review(ROOT, args.changed, depth=args.depth, limit=args.limit)
    except (ReviewBlocked, OSError, RuntimeError, ValueError) as exc:
        ap.exit(2, "BLOCKED: " + str(exc) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
