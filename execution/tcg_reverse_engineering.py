#!/usr/bin/env python3
"""Reverse-map owned TCG Python source without executing it.

Reuses the tracked-only module atlas. AST results are hypotheses, never proof
of runtime calls, authorization, grading behavior, or device verification.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path, PurePosixPath

try:
    from execution.tablet_code_map_audit import ROOT, build, MAX_BYTES
except ModuleNotFoundError:
    from tablet_code_map_audit import ROOT, build, MAX_BYTES

MAX_SYMBOLS = 100
MAX_CALLS = 40


class ReverseBlocked(ValueError):
    """Unsafe path, incomplete or unparseable static source."""


def _tracked_source(root: Path, relative: str) -> Path:
    if (not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative
            or "\x00" in relative or not relative.endswith(".py")):
        raise ReverseBlocked("invalid_python_path")
    bits = relative.split("/")
    if PurePosixPath(relative).is_absolute() or any(x in ("..", ".", "") for x in bits):
        raise ReverseBlocked("unsafe_relative_path")
    candidate = root
    for bit in bits:
        candidate = candidate / bit
        if candidate.is_symlink():
            raise ReverseBlocked("symlink_path_not_allowed")
    if not candidate.is_file() or candidate.stat().st_size > MAX_BYTES:
        raise ReverseBlocked("unsafe_missing_or_oversize_source")
    return candidate


def _main_guard(node: ast.AST) -> bool:
    if not isinstance(node, ast.If):
        return False
    cmp = node.test
    if not isinstance(cmp, ast.Compare) or len(cmp.ops) != 1 or not isinstance(cmp.ops[0], ast.Eq):
        return False
    if len(cmp.comparators) != 1:
        return False
    pairs = ((cmp.left, cmp.comparators[0]), (cmp.comparators[0], cmp.left))
    return any(isinstance(a, ast.Name) and a.id == "__name__" and
               isinstance(b, ast.Constant) and b.value == "__main__" for a,b in pairs)


class CallSurvey(ast.NodeVisitor):
    def __init__(self):
        self.calls = set()
        self.count = 0

    def visit_Call(self, node: ast.Call):
        self.count += 1
        called = node.func
        if isinstance(called, ast.Name):
            self.calls.add(called.id)
        elif isinstance(called, ast.Attribute):
            # Member lookup does not establish actual dispatch.
            self.calls.add("*." + called.attr)
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        return

    def visit_AsyncFunctionDef(self, node):
        return

    def visit_ClassDef(self, node):
        return

    def visit_Lambda(self, node):
        return


def inspect(root: Path, relative: str) -> dict:
    graph = build(root)
    if relative not in graph["local_import_edges"]:
        raise ReverseBlocked("source_not_tracked_or_unparseable")
    path = _tracked_source(root, relative)
    raw = path.read_bytes()
    try:
        tree = ast.parse(raw.decode("utf-8"), filename=relative)
    except (SyntaxError, UnicodeError) as exc:
        raise ReverseBlocked("cannot_parse_source") from exc

    functions = []
    count = 0
    clipped = False
    for node in tree.body:
        definitions = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            definitions = [(node.name, node)]
        elif isinstance(node, ast.ClassDef):
            definitions = [(node.name + "." + item.name, item)
                           for item in node.body
                           if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))]
        for name, func in definitions:
            count += 1
            if count > MAX_SYMBOLS:
                clipped = True
                break
            visitor = CallSurvey()
            for statement in func.body:
                visitor.visit(statement)
            if len(visitor.calls) > MAX_CALLS or visitor.count > MAX_CALLS:
                clipped = True
            functions.append({
                "symbol": name,
                "kind": "async" if isinstance(func, ast.AsyncFunctionDef) else "function",
                "line": func.lineno,
                "observed_call_syntax": sorted(visitor.calls)[:MAX_CALLS],
                "call_count_syntax": visitor.count,
            })
        if count > MAX_SYMBOLS:
            break

    entrypoints = [node.lineno for node in tree.body if _main_guard(node)]
    all_importers = sorted(source for source, imports in graph["local_import_edges"].items()
                           if relative in imports)
    importers = all_importers[:100]
    return {
        "schema": "tcg-python-reverse-ast-v1",
        "mode": "tracked_source_static_no_execution",
        "file": relative,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "defined_functions": functions,
        "symbols_seen": count,
        "imported_by": importers,
        "importers_total": len(all_importers),
        "importers_truncated": len(all_importers) > 100,
        "possible_main_guard_lines": entrypoints[:20],
        "review_state": ("HOLD_TRUNCATED" if clipped or len(entrypoints) > 20
                         or len(all_importers) > 100 else "CANDIDATE_ONLY"),
        "limitations": [
            "AST call syntax, not dynamic call graph or successful execution",
            "Methods can resolve dynamically; *.method does not identify receiver",
            "No JS/PWA, JNI, SDK or Android runtime inspection",
            "No learned improvements or automatic code modification",
            "A candidate requires current-head CI and independent device verification",
        ],
        "physical_tablet_verified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, help="tracked .py path only")
    args = parser.parse_args()
    try:
        report = inspect(ROOT, args.file)
    except (ReverseBlocked, OSError, RuntimeError, ValueError) as exc:
        parser.exit(2, "BLOCKED: " + str(exc) + "\n")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
