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
from collections import Counter, deque
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
    python_tracked_count = sum(p.endswith(".py") for p in paths)
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
    asset_tracked_count = len(asset_paths)
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
    # Inventory coverage is not unit-test coverage or proof of executed paths.
    # Track skipped/unsafe source explicitly instead of inflating python_count.
    component_buckets: dict[str, dict[str, int]] = {}
    for path in paths:
        area = path.split("/", 1)[0] if "/" in path else "(root)"
        bucket = component_buckets.setdefault(
            area, {"tracked": 0, "python_tracked": 0, "python_parsed": 0,
                   "test_files": 0, "static_assets": 0})
        bucket["tracked"] += 1
        bucket["python_tracked"] += int(path.endswith(".py"))
        bucket["python_parsed"] += int(path in imports)
        bucket["test_files"] += int(_test_path(path))
        bucket["static_assets"] += int(path in asset_paths)
    component_overview = sorted(
        [{"component": name, **counts} for name, counts in component_buckets.items()],
        key=lambda record: (-record["tracked"], record["component"]),
    )[:32]
    components_truncated = len(component_buckets) > 32
    reverse = Counter(target for targets in imports.values() for target in targets)
    report = {"schema_version": 1, "mode": "read_only", "tracked_count": len(paths),
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
            "python_count": len(imports),
            "python_tracked_count": python_tracked_count,
            "python_parsed_count": len(imports),
            "python_unscanned_count": python_tracked_count - len(imports),
            "asset_tracked_count": asset_tracked_count,
            "asset_unscanned_count": asset_tracked_count - asset_files_scanned,
            "component_overview": component_overview,
            "component_overview_truncated": components_truncated,
            "inventory_coverage_not_runtime_coverage": True,
            "category_counts": dict(sorted(Counter(
                p.split("/")[0] if "/" in p else "(root)" for p in paths).items())),
            "local_import_edges": imports, "static_asset_candidates": asset_edges, "incoming_reference_counts": dict(sorted(reverse.items())),
            "parse_issues": errors, "physical_device_verified": False,
            "notes": ["Static imports and literal asset candidates only; runtime calls are not proven.",
                      "Untracked names are inventoried but their contents are NOT analyzed.",
                      "No files are relocated, deleted, executed or written."]}
    report["maintenance_queue"] = summarize_maintenance(report)
    return report


def summarize_maintenance(report: dict) -> dict:
    """Bounded issue queue, never a quality score or repair instruction."""
    issues = []
    dirty = (report.get("staged_tracked_changes"), report.get("unstaged_tracked_changes"))
    if any(x is None or x > 0 for x in dirty):
        issues.append({"priority": "P0", "category": "local_worktree_protection",
                       "evidence": "dirty_or_unknown", "action": "hold_code_install"})
    parsed = len(report.get("parse_issues") or [])
    if parsed:
        issues.append({"priority": "P1", "category": "static_parse_or_read_issues",
                       "count": parsed, "action": "inspect_without_running"})
    if report.get("untracked_inventory_status") != "names_only" or report.get("untracked_entry_count"):
        issues.append({"priority": "P1", "category": "untracked_coverage_gap",
                       "count": report.get("untracked_entry_count"),
                       "action": "do_not_delete_or_overwrite"})
    unresolved = int(report.get("unresolved_asset_reference_count") or 0)
    if unresolved:
        issues.append({"priority": "P2", "category": "unresolved_static_asset_candidates",
                       "count": unresolved, "action": "verify_at_runtime"})
    artifacts = report.get("graphify_artifacts") or {}
    if any(artifacts.get(name) != "present_unverified"
           for name in ("graph.json", "graph_audit.json")):
        issues.append({"priority": "P2", "category": "graphify_evidence_incomplete",
                       "action": "check_capability_and_graph_receipt"})
    hubs = sorted(({"path": k, "incoming_import_count": v}
                   for k, v in (report.get("incoming_reference_counts") or {}).items()),
                  key=lambda x: (-x["incoming_import_count"], x["path"]))[:10]
    return {
        "assessment": "static_evidence_only",
        "quality_score": None,
        "physical_device_verified": False,
        "issues": issues,
        "import_hubs_for_review": hubs,
        "required_workflow": "scope -> reproduce -> minimal fix -> targeted tests -> full regression -> receipt",
        "auto_source_change_authorized": False,
    }


def _test_path(path: str) -> bool:
    name = PurePosixPath(path).name
    return path.endswith(".py") and name.startswith("test_")


def plan_change_impact(report: dict, changed_files: list[str], *, max_files: int = 24,
                       max_tests: int = 12, max_depth: int = 2) -> dict:
    """Conservative read-only first-touch plan; never authorizes a patch or test skip.

    Reverse static imports/literal links provide *candidate* dependents, not
    runtime evidence. Unknown paths, security boundaries and truncation escalate.
    """
    max_files = max(1, min(48, int(max_files)))
    max_tests = max(1, min(24, int(max_tests)))
    max_depth = max(0, min(3, int(max_depth)))
    edges: dict[str, set[str]] = {}
    for key in ("local_import_edges", "static_asset_candidates"):
        for source, targets in report.get(key, {}).items():
            edges.setdefault(source, set()).update(targets)
    known = set(edges) | {v for vals in edges.values() for v in vals}
    known.update(e.get("path") for e in report.get("parse_issues", ()) if e.get("path"))
    cleaned: set[str] = set()
    invalid: list[str] = []
    for value in changed_files[:256]:
        path = str(value).strip()
        if (not path or len(path) > 260 or "\\" in path or path.startswith("/")
                or any(part in (".", "..") for part in path.split("/"))):
            invalid.append(path[:160])
        else:
            cleaned.add(path)
    changed = sorted(cleaned)
    unknown = [path for path in changed if path not in known]
    reverse: dict[str, set[str]] = {}
    for src, deps in edges.items():
        for dep in deps:
            reverse.setdefault(dep, set()).add(src)
    distance = {path: 0 for path in changed if path in known}
    queue = deque(sorted(distance))
    while queue and len(distance) < 512:
        current = queue.popleft()
        if distance[current] >= max_depth:
            continue
        for parent in sorted(reverse.get(current, ())):
            if parent not in distance:
                distance[parent] = distance[current] + 1
                queue.append(parent)
    ranked = sorted(distance, key=lambda p: (distance[p], p))
    candidates = [p for p in ranked if p not in cleaned and not _test_path(p)]
    tests = [p for p in ranked if _test_path(p)]
    parse_paths = {e.get("path") for e in report.get("parse_issues", ())}
    critical_paths = [p for p in changed if (
        p.startswith(".github/workflows/")
        or p.startswith(("crosscheck_control_plane/", ("crosscheck_" + "exchange/")))
        or PurePosixPath(p).name in {
            "ANDROID_UPDATE_AND_START.sh", "TABLET_SCHEDULED_UPDATE.sh",
            "START_TCG_UPDATER_ANDROID.sh", "repository_integrity_guard.py",
            "integrity_manifest.json", "main_selfrefine_gate.py",
            "collection_job_contract.py", "safe_runtime.py",
        } or any(token in p.lower() for token in ("security", "selfrefine", "autonomy"))
    )]
    truncated = (len(candidates) > max_files or len(tests) > max_tests
                 or len(distance) >= 512 or len(changed_files) > 256)
    reasons = []
    if invalid:
        reasons.append("invalid_change_path")
    if unknown:
        reasons.append("unmapped_change_requires_repository_review")
    if critical_paths:
        reasons.append("critical_or_security_boundary")
    if truncated:
        reasons.append("bounded_impact_truncated")
    if any(path in parse_paths for path in distance):
        reasons.append("parse_issue_in_impact")
    # No conservative static graph can replace full final regression or CodeQL.
    initial = "full_chain" if reasons else ("targeted_plus_repository_verify"
                if tests else "repository_verify")
    return {
        "mode": "read_only", "changed_files": changed[:48],
        "unmapped_files": unknown[:24], "invalid_paths": invalid[:10],
        "impact_candidates": [{"path": p, "distance": distance[p]} for p in candidates[:max_files]],
        "test_candidates": tests[:max_tests],
        "bounded_impact_truncated": truncated,
        "initial_validation_scope": initial,
        "full_regression_required_before_release": True,
        "reasons": reasons,
        "limitations": "Static candidates only; dynamic/runtime paths require human and CI review.",
    }



def collect_tracked_changes(root: Path, *, max_output_bytes: int = 256_000) -> dict:
    """Read staged/unstaged names from Git, never touching source or index."""
    names: set[str] = set()
    for args in (("--cached",), ()):
        try:
            result = subprocess.run(
                ["git", "-c", "diff.renames=false", "diff", "--name-only", "-z",
                 *args, "--"],
                cwd=root, capture_output=True, check=True, timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            return {"status": "unavailable", "files": []}
        if len(result.stdout) > max_output_bytes:
            return {"status": "over_limit", "files": []}
        names.update(s.decode("utf-8", "replace")
                     for s in result.stdout.split(b"\0") if s)
        if len(names) > 256:
            return {"status": "over_limit", "files": []}
    return {"status": "changes" if names else "clean", "files": sorted(names)}



def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--feature", default="", help="optional query routed through existing code map")
    parser.add_argument("--changed-file", action="append", default=[], help="tracked source change for bounded read-only impact planning")
    parser.add_argument("--auto-changes", action="store_true", help="plan changes from staged and unstaged tracked paths without manual input")
    args = parser.parse_args()
    report = build(args.root)
    changed = list(args.changed_file)
    if args.auto_changes:
        detected = collect_tracked_changes(args.root.resolve())
        report["auto_change_inventory_status"] = detected["status"]
        report["auto_changed_tracked_count"] = len(detected["files"])
        changed.extend(detected["files"])
    if changed:
        report["change_impact_plan"] = plan_change_impact(report, changed)
    if args.auto_changes and report["auto_change_inventory_status"] in ("unavailable", "over_limit"):
        plan = report.setdefault("change_impact_plan", plan_change_impact(report, changed))
        plan["initial_validation_scope"] = "full_chain"
        plan["reasons"] = sorted(set(plan["reasons"]) | {"auto_change_inventory_unavailable"})
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
