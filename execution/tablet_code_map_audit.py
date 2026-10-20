#!/usr/bin/env python3
"""Read-only, bounded map of tracked TCG source files and local Python imports."""
from __future__ import annotations
import sys
sys.dont_write_bytecode = True  # Feature routing must not create __pycache__ on Lenovo.
import argparse
import ast
import json
import posixpath
import re
import shutil
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
    def count_tracked_changes(*arguments: str) -> int | None:
        # Git evidence only; never stage, restore, clean or rewrite the worktree.
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "-z", *arguments, "--"],
                cwd=root, capture_output=True, timeout=20, check=True,
            )
            return sum(bool(item) for item in result.stdout.split(b"\0"))
        except (OSError, subprocess.SubprocessError):
            return None
    staged_changes = count_tracked_changes("--cached")
    unstaged_changes = count_tracked_changes()
    # Enumerate *names* of untracked entries only; --directory collapses local
    # backup trees. Never read, upload, delete, or treat them as verified code.
    untracked_entry_count: int | None = None
    untracked_code_sample: list[str] = []
    untracked_inventory_status = "unavailable"
    try:
        result = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "--directory", "-z"],
            cwd=root, capture_output=True, timeout=12, check=True,
        )
        # Fail closed for unexpectedly large inventories rather than retaining
        # sensitive path listings or publishing false zero counts.
        if len(result.stdout) <= 256_000:
            entries = [x.decode("utf-8", "replace") for x in result.stdout.split(b"\0") if x]
            untracked_entry_count = len(entries)
            untracked_code_sample = sorted(
                p for p in entries
                if p.endswith((".py", ".sh", ".js", ".mjs", ".html", ".css"))
            )[:20]
            untracked_inventory_status = "names_only"
        else:
            untracked_inventory_status = "over_limit"
    except (OSError, subprocess.SubprocessError):
        untracked_inventory_status = "unavailable"

    def safe_file(path: Path) -> bool:
        # A tracked file can be reached through a locally replaced symlinked
        # parent; a disappearing/permission-denied file is a reported issue.
        try:
            return (not path.is_symlink() and path.is_file() and
                    path.resolve().is_relative_to(root) and path.stat().st_size <= MAX_BYTES)
        except (OSError, RuntimeError):
            return False
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
    ambiguous_asset_reference_count = 0
    unresolved_asset_references: list[dict] = []
    unresolved_asset_reference_count = 0
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
            # Record unresolved references even when no file of that basename
            # exists anywhere in the tracked tree. These are candidates, not
            # proof that a runtime dependency is broken.
            if not name.endswith(asset_suffixes):
                continue
            # Resolve relative to the referring file first, then root paths.
            local = posixpath.normpath(posixpath.join(posixpath.dirname(p), token.lstrip("/")))
            rooted = posixpath.normpath(token.lstrip("/"))
            # HTML/CSS paths are relative to the referring file unless they
            # start with '/'. A matching basename in another folder does NOT
            # prove the reference: record it as unresolved instead.
            if token.startswith("/"):
                matched = rooted if rooted in asset_paths else None
            elif p.endswith((".sh", ".bash")):
                # Shell relative paths depend on the process working directory,
                # not necessarily the script's directory. If two distinct
                # tracked paths fit, never select a falsely precise edge.
                shell_matches = {x for x in (rooted, local) if x in asset_paths}
                matched = next(iter(shell_matches)) if len(shell_matches) == 1 else None
            else:
                matched = local if local in asset_paths else None
            if matched and matched != p:
                candidates.add(matched)
            elif matched is None:
                unresolved_asset_reference_count += 1
                if len(unresolved_asset_references) < 100:
                    unresolved_asset_references.append({
                        "source": p, "reference": token[:160],
                        "candidate_count": len(asset_names.get(name, ())),
                    })
                if len(asset_names.get(name, ())) > 1:
                    ambiguous_asset_reference_count += 1
                    if len(ambiguous_asset_references) < 100:
                        ambiguous_asset_references.append({"source": p, "basename": name})
        asset_edges[p] = sorted(candidates)
    # Presence-only Graphify diagnostics. We never execute Graphify or read its
    # potentially large output here; missing data leaves the static fallback usable.
    # Read-only capability probe: never execute Graphify or install packages.
    # Binary presence alone is not evidence of a working graph or compatible CLI.
    graphify_executable = shutil.which("graphify")
    if not graphify_executable:
        fallback = Path.home() / ".local" / "bin" / "graphify"
        try:
            if fallback.is_file() and not fallback.is_symlink() and fallback.stat().st_mode & 0o111:
                graphify_executable = str(fallback)
        except (OSError, RuntimeError):
            pass  # A missing/racing CLI is a diagnostic, not a scan failure.
    graphify_cli_status = "present_unverified" if graphify_executable else "not_found"
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
            "ambiguous_asset_reference_count": ambiguous_asset_reference_count,
            "unresolved_asset_references": unresolved_asset_references,
            "unresolved_asset_reference_count": unresolved_asset_reference_count,
            "staged_tracked_changes": staged_changes,
            "unstaged_tracked_changes": unstaged_changes,
            "untracked_inventory_status": untracked_inventory_status,
            "untracked_entry_count": untracked_entry_count,
            "untracked_code_sample": untracked_code_sample,
            "graphify_cli_status": graphify_cli_status,
            "graphify_artifacts": graphify_artifacts,
            "python_count": len(imports), "category_counts": dict(sorted(Counter(
                p.split("/")[0] if "/" in p else "(root)" for p in paths).items())),
            "local_import_edges": imports, "static_asset_candidates": asset_edges, "incoming_reference_counts": dict(sorted(reverse.items())),
            "parse_issues": errors, "physical_device_verified": False,
            "notes": ["Static imports and literal asset candidates only; runtime calls are not proven.",
                      "Untracked names are inventoried but their contents are NOT analyzed.",
                      "No files are relocated, deleted, executed or written."]}

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--feature", default="", help="optional query routed through existing code map")
    args = parser.parse_args()
    report = build(args.root)
    if args.feature:
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
