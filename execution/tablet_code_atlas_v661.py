#!/usr/bin/env python3
"""Read-only V661 tablet code atlas: tracked paths, AST edges and test routing.

Graphify / code_map_fast_route.py remains the feature-query entrypoint.
No external data, source execution, automated edits, model learning or Git writes.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict, deque
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
MAX_PATHS = 3000
MAX_SCAN_BYTES = 750_000
MAX_FOCUS = 650
MAX_DISPLAY = 35
EVOLVE = re.compile(r"^tablet_autonomous_evolution_v(\d+)\.py$")
SHELL_REF = re.compile(r"(?<![\w/])(?:[\w-]+/)*[\w.-]+\.(?:py|sh|js|css)\b")
CRITICAL = {"main", "TABLET_SCHEDULED_UPDATE.sh", "ANDROID_UPDATE_AND_START.sh",
            "tablet_runtime_manifest.py", "tablet_autonomous_evolution_v400.py",
            "tablet_autonomous_evolution_v387.py", "integrity_manifest.json"}


def safe_name(s: str) -> bool:
    if not isinstance(s, str) or not s or "\x00" in s or "\\" in s:
        return False
    p = PurePosixPath(s)
    return not p.is_absolute() and all(x not in (".", "..") for x in p.parts)


def tracked(root: Path) -> list[str]:
    try:
        r = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached"],
                           capture_output=True, check=True, timeout=20)
        if len(r.stdout) > 1_500_000:
            raise ValueError("GIT_INDEX_OVERSIZE")
        names = [x.decode("utf-8") for x in r.stdout.split(b"\x00") if x]
    except (OSError, UnicodeError, subprocess.SubprocessError) as exc:
        raise ValueError("GIT_INDEX_UNAVAILABLE") from exc
    if len(names) > MAX_PATHS or len(names) != len(set(names)) or any(not safe_name(n) for n in names):
        raise ValueError("GIT_INDEX_INVALID_OR_TOO_LARGE")
    return sorted(names)


def role(s: str) -> str:
    name = PurePosixPath(s).name
    if s.startswith("TCG_CROSSCHECK/"):
        return "preserved_crosscheck_contract_or_snapshot"
    if s.startswith(".github/workflows/"):
        return "ci_workflow"
    if name.startswith("test_") and name.endswith(".py"):
        return "test"
    if EVOLVE.fullmatch(s):
        return "autonomy_version"
    if s == "main" or (name.startswith(("ANDROID_", "TABLET_", "VERIFY_TABLET"))
                       and name.endswith((".sh", ".py")) and "/" not in s):
        return "tablet_control_plane"
    if name.startswith(("GRAPHIFY_", "code_map_")):
        return "existing_code_map"
    if "/" not in s and name.startswith(("tablet_", "screen_policy_", "verified_collection_",
                                          "tcg_updater", "tcg_game_registry")):
        return "tablet_or_shared_runtime"
    if s.endswith((".json", ".jsonl", ".csv")):
        return "data_contract_or_snapshot"
    return "other_tracked"


def focus(s: str, active: set[str]) -> bool:
    name = PurePosixPath(s).name
    return s in active or role(s) in {
        "autonomy_version", "tablet_control_plane", "tablet_or_shared_runtime",
        "existing_code_map",
    } or name.startswith(("test_tablet", "test_verified_collection", "test_code_map")) \
        or s.startswith("execution/tablet_") or s in {"safe_runtime.py", "main"}


def import_edges(raw: bytes, names: set[str]) -> set[str]:
    tree = ast.parse(raw, filename="<static-atlas>")
    edges = set()
    for node in ast.walk(tree):
        values = []
        if isinstance(node, ast.Import):
            values = [n.name for n in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            values = [node.module or ""]
            values += [(node.module + "." + n.name) if node.module else n.name
                       for n in node.names]
        for module in values:
            p = module.replace(".", "/")
            for candidate in (p + ".py", p + "/__init__.py"):
                if candidate in names:
                    edges.add(candidate)
    return edges


def atlas(root: Path, paths: list[str], *, active: tuple[str, ...] = (),
          changed: tuple[str, ...] = (), detailed: bool = False) -> dict:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("UNSAFE_ROOT")
    if len(paths) > MAX_PATHS or len(paths) != len(set(paths)) or any(not safe_name(p) for p in paths):
        raise ValueError("UNSAFE_TRACKED_LIST")
    if any(not safe_name(p) for p in changed):
        raise ValueError("UNSAFE_CHANGED_PATH")
    names = set(paths)
    missing_active = sorted(set(active) - names)
    errors = ["MISSING_ACTIVE_RUNTIME:" + p for p in missing_active]
    warnings = []
    focused = [p for p in paths if focus(p, set(active))]
    if len(focused) > MAX_FOCUS:
        errors.append("ATLAS_FOCUS_LIMIT")
        focused = focused[:MAX_FOCUS]
    edges: dict[str, set[str]] = {}
    hashes = {}
    for p in focused:
        disk = root / p
        if disk.is_symlink() or not disk.is_file():
            errors.append("UNSAFE_OR_MISSING_SOURCE:" + p)
            continue
        if not (p.endswith((".py", ".sh", ".js", ".css")) or p == "main"):
            continue
        try:
            if disk.stat().st_size > MAX_SCAN_BYTES:
                warnings.append("SKIPPED_LARGE_FILE:" + p)
                continue
            raw = disk.read_bytes()
            if len(raw) > MAX_SCAN_BYTES:
                raise ValueError("SOURCE_RACE")
            hashes[p] = hashlib.sha256(raw).hexdigest()
            if p.endswith(".py"):
                edges[p] = import_edges(raw, names)
            elif p == "main" or p.endswith(".sh"):
                edges[p] = set(SHELL_REF.findall(raw.decode("utf-8", errors="replace"))) & names
        except (OSError, UnicodeError, ValueError, SyntaxError) as exc:
            errors.append("SOURCE_SYNTAX_OR_READ:" + p + ":" + type(exc).__name__)
    incoming = defaultdict(set)
    for p, deps in edges.items():
        for dep in deps:
            if dep != p:
                incoming[dep].add(p)
    dependents, candidate_tests = set(), set()
    queue = deque((p, 0) for p in changed if p in names)
    checked = set()
    while queue and len(checked) < 500:
        node, depth = queue.popleft()
        if node in checked:
            continue
        checked.add(node)
        if node not in changed:
            dependents.add(node)
        for dependent in sorted(incoming[node]):
            if role(dependent) == "test":
                candidate_tests.add(dependent)
            elif depth < 2:
                queue.append((dependent, depth + 1))
    for p in changed:
        stem = PurePosixPath(p).stem
        if p in names and role(p) == "test":
            candidate_tests.add(p)
        if len(stem) >= 10:
            candidate_tests.update(x for x in paths if role(x) == "test"
                                   and stem in PurePosixPath(x).stem)
    unknown = [p for p in changed if p not in names]
    if unknown:
        warnings.append("UNTRACKED_CHANGED_PATHS:" + str(len(unknown)))
    versions = sorted(int(EVOLVE.fullmatch(p).group(1)) for p in paths if EVOLVE.fullmatch(p))
    high = any(p in CRITICAL or role(p) in {"tablet_control_plane", "ci_workflow"}
               for p in changed)
    result = {
        "schema_version": 1, "ok": not errors, "mode": "READ_ONLY_TRACKED",
        "tracked_count": len(paths), "role_counts": dict(sorted(Counter(role(p) for p in paths).items())),
        "active_runtime_count": len(active), "missing_active": missing_active[:MAX_DISPLAY],
        "autonomy_versions": versions, "focused_count": len(focused),
        "parsed_or_hashed_source_count": len(hashes),
        "static_dependency_edges": sum(len(v) for v in edges.values()),
        "changed": list(changed)[:MAX_DISPLAY],
        "impacted_files": sorted(dependents)[:MAX_DISPLAY],
        "existing_test_candidates": sorted(candidate_tests)[:MAX_DISPLAY],
        "recommended_review": "FULL_CI_AND_SUCCESSOR_CONTRACT" if high else "FOCUSED_TESTS_AND_INTEGRITY",
        "warnings": sorted(set(warnings))[:MAX_DISPLAY], "errors": sorted(set(errors))[:MAX_DISPLAY],
        "physical_device_verified": False, "learning_records_created": 0,
        "self_modification": False, "auto_deletion": False,
        "graphify_replaced": False, "public_feature_router": "code_map_fast_route.py",
    }
    if detailed:
        result["tracked_paths_by_role"] = {
            k: [p for p in paths if role(p) == k] for k in sorted(set(role(p) for p in paths))
        }
        result["dependencies"] = {k: sorted(v) for k, v in sorted(edges.items()) if v}
        result["read_only_source_hashes"] = dict(sorted(hashes.items()))
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--changed", nargs="*", default=[])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    try:
        active = ()
        if args.root.resolve() == ROOT.resolve():
            from tablet_runtime_manifest import ACTIVE_RUNTIME_FILES
            active = ACTIVE_RUNTIME_FILES
        result = atlas(args.root, tracked(args.root), active=tuple(active),
                       changed=tuple(args.changed), detailed=args.all)
    except (ValueError, OSError) as exc:
        result = {"ok": False, "errors": [str(exc)], "physical_device_verified": False}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
