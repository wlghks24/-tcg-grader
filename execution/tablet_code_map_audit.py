#!/usr/bin/env python3
"""Read-only, bounded map of tracked TCG source files and local Python imports."""
from __future__ import annotations
import argparse
import ast
import json
import subprocess
from collections import Counter
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
SKIP = {".tmp", ".git", "__pycache__", ".venv", "venv", "node_modules"}
MAX_BYTES = 1_000_000

def build(root: Path = ROOT) -> dict:
    root = root.resolve()
    proc = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, timeout=20, check=True)
    paths = sorted(x.decode("utf-8", "replace") for x in proc.stdout.split(b"\0") if x)
    paths = [p for p in paths if not (set(PurePosixPath(p).parts) & SKIP)]
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
        if file.is_symlink() or not file.is_file() or file.stat().st_size > MAX_BYTES:
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
    tracked = set(paths)
    for p in paths:
        if not p.endswith(asset_suffixes):
            continue
        file = root / p
        if file.is_symlink() or not file.is_file() or file.stat().st_size > MAX_BYTES:
            errors.append({"path": p, "issue": "unsafe_or_oversize_asset"})
            continue
        try:
            content = file.read_text(encoding="utf-8")
        except (UnicodeError, OSError) as exc:
            errors.append({"path": p, "issue": type(exc).__name__})
            continue
        candidates = set()
        for target in tracked:
            if target == p or not target.endswith(asset_suffixes):
                continue
            name = PurePosixPath(target).name
            if len(name) >= 5 and (("\"" + name + "\"") in content or ("\'" + name + "\'") in content):
                candidates.add(target)
        asset_edges[p] = sorted(candidates)
    reverse = Counter(target for targets in imports.values() for target in targets)
    return {"schema_version": 1, "mode": "read_only", "tracked_count": len(paths),
            "python_count": len(imports), "category_counts": dict(sorted(Counter(
                p.split("/")[0] if "/" in p else "(root)" for p in paths).items())),
            "local_import_edges": imports, "static_asset_candidates": asset_edges, "incoming_reference_counts": dict(sorted(reverse.items())),
            "parse_issues": errors, "physical_device_verified": False,
            "notes": ["Static imports and literal asset candidates only; runtime calls are not proven.",
                      "No files are relocated, deleted, executed or written."]}

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps(build(args.root), ensure_ascii=False, sort_keys=True, indent=2))

if __name__ == "__main__":
    main()
