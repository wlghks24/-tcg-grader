#!/usr/bin/env python3
"""Read-only, bounded map of tracked TCG source files and local Python imports."""
from __future__ import annotations
import argparse
import ast
import json
import posixpath
import re
import subprocess
import time
from collections import Counter
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
SKIP = {".tmp", ".git", "__pycache__", ".venv", "venv", "node_modules"}
MAX_BYTES = 1_000_000

def build(root: Path = ROOT) -> dict:
    root = root.resolve()
    scan_started = time.perf_counter()
    proc = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, timeout=20, check=True)
    paths = sorted(x.decode("utf-8", "replace") for x in proc.stdout.split(b"\0") if x)
    paths = [p for p in paths if not (set(PurePosixPath(p).parts) & SKIP)]
    def safe_file(path: Path) -> bool:
        # A tracked file can be reached through a locally replaced symlinked parent.
        return (not path.is_symlink() and path.is_file() and
                path.resolve().is_relative_to(root) and path.stat().st_size <= MAX_BYTES)
    modules = {p[:-3].replace("/", "."): p for p in paths if p.endswith(".py")}
    modules.update({p[:-12].replace("/", "."): p for p in paths if p.endswith("/__init__.py")})
    def resolve(name: str) -> str | None:
        parts = name.split(".")
        for end in range(len(parts), 0, -1):
            target = modules.get(".".join(parts[:end]))
            if target:
                return target
        return None
    imports: dict[str, list[str]] = {}
    errors: list[dict] = []
    for p in paths:
        if not p.endswith(".py"):
            continue
        file = root / p
        if not safe_file(file):
            errors.append({"path": p, "issue": "unsafe_or_oversize"})
            continue
        try:
            tree = ast.parse(file.read_text(encoding="utf-8"), filename=p)
        except (SyntaxError, UnicodeError, OSError) as exc:
            errors.append({"path": p, "issue": type(exc).__name__})
            continue
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    found.add(node.module)
                    for alias in node.names:
                        if alias.name != "*":
                            found.add(node.module + "." + alias.name)
                elif node.level:
                    package = p[:-3].replace("/", ".").split(".")[:-1]
                    if p.endswith("/__init__.py"):
                        package = p[:-12].replace("/", ".").split(".")
                    if node.level <= len(package) + 1:
                        prefix = package[:len(package) - node.level + 1]
                        base = ".".join(prefix + ([node.module] if node.module else []))
                        if base:
                            found.add(base)
                        for alias in node.names:
                            if alias.name != "*":
                                found.add(".".join(x for x in (base, alias.name) if x))
        imports[p] = sorted({target for name in found if (target := resolve(name)) is not None})
    # Literal asset references are candidates, not verified runtime calls.
    asset_edges: dict[str, list[str]] = {}
    asset_suffixes = (".sh", ".bash", ".js", ".mjs", ".css", ".html", ".htm")
    asset_names = {}
    for target in paths:
        if target.endswith(asset_suffixes):
            asset_names.setdefault(PurePosixPath(target).name, []).append(target)
    # Tokenize quoted asset references once per file. Full path evidence is
    # preferred over basename inference, and ambiguous basenames are not edges.
    asset_paths = {p for p in paths if p.endswith(asset_suffixes)}
    ambiguous_asset_references: list[dict] = []
    asset_files_scanned = 0
    quoted_references_examined = 0
    quoted_literal = re.compile(r"""(?:"([^"\r\n]{1,256})"|'([^'\r\n]{1,256})')""")
    for p in paths:
        if not p.endswith(asset_suffixes):
            continue
        file = root / p
        if not safe_file(file):
            errors.append({"path": p, "issue": "unsafe_or_oversize_asset"})
            continue
        try:
            content = file.read_text(encoding="utf-8")
        except (UnicodeError, OSError) as exc:
            errors.append({"path": p, "issue": type(exc).__name__})
            continue
        asset_files_scanned += 1
        candidates = set()
        for double, single in quoted_literal.findall(content):
            quoted_references_examined += 1
            token = (double or single).split("?", 1)[0].split("#", 1)[0]
            if "://" in token or token.startswith("//"):
                continue  # remote URLs cannot establish local dependencies
            name = PurePosixPath(token).name
            if len(name) < 5 or name not in asset_names:
                continue
            # Resolve relative to the referring file first, then root paths.
            local = posixpath.normpath(posixpath.join(posixpath.dirname(p), token.lstrip("/")))
            rooted = posixpath.normpath(token.lstrip("/"))
            if token.startswith("/"):
                matched = rooted if rooted in asset_paths else None
            else:
                matched = next((candidate for candidate in (local, rooted) if candidate in asset_paths), None)
            if matched and matched != p:
                candidates.add(matched)
            elif "/" not in token and len(asset_names[name]) == 1:
                target = asset_names[name][0]
                if target != p:
                    candidates.add(target)
            elif "/" not in token and len(asset_names[name]) > 1:
                if len(ambiguous_asset_references) < 100:
                    ambiguous_asset_references.append({"source": p, "basename": name})
        asset_edges[p] = sorted(candidates)
    # Presence-only Graphify diagnostics. We never execute Graphify or read its
    # potentially large output here; missing data leaves the static fallback usable.
    graphify_artifacts: dict[str, str] = {}
    for artifact in ("graph.json", "graph_audit.json"):
        target = root / "graphify-out" / artifact
        try:
            if not target.resolve().is_relative_to(root) or target.is_symlink():
                graphify_artifacts[artifact] = "unsafe_external_path"
            elif target.is_file() and target.stat().st_size > 0:
                graphify_artifacts[artifact] = "present_unverified"
            else:
                graphify_artifacts[artifact] = "missing"
        except OSError:
            graphify_artifacts[artifact] = "unreadable"
    reverse = Counter(target for targets in imports.values() for target in targets)
    return {"schema_version": 1, "mode": "read_only", "tracked_count": len(paths),
            "scan_ms": round((time.perf_counter() - scan_started) * 1000, 3),
            "asset_files_scanned": asset_files_scanned,
            "quoted_references_examined": quoted_references_examined,
            "ambiguous_asset_references": ambiguous_asset_references,
            "graphify_artifacts": graphify_artifacts,
            "python_count": len(imports), "category_counts": dict(sorted(Counter(
                p.split("/")[0] if "/" in p else "(root)" for p in paths).items())),
            "local_import_edges": imports, "static_asset_candidates": asset_edges, "incoming_reference_counts": dict(sorted(reverse.items())),
            "parse_issues": errors, "physical_device_verified": False,
            "notes": ["Static imports and literal asset candidates only; runtime calls are not proven.",
                      "No files are relocated, deleted, executed or written."]}

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--feature", default="", help="optional query routed through existing code map")
    args = parser.parse_args()
    report = build(args.root)
    if args.feature:
        import sys
        root = args.root.resolve()
        if root != ROOT:
            report["existing_code_map_integration"] = "unavailable_custom_root"
            print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
            return
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        try:
            from code_map_intelligence import resolve_feature_query
            route = resolve_feature_query(args.feature)
            report["existing_code_map_route"] = route
            report["existing_code_map_integration"] = "read_only_feature_route"
        except (ImportError, ValueError, OSError) as exc:
            report["existing_code_map_integration"] = "unavailable"
            report["existing_code_map_error"] = type(exc).__name__
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))

if __name__ == "__main__":
    main()
