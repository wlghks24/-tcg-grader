#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from shared_self_learning.contracts import assert_passive_exchange_payload

ROOT = Path(__file__).resolve().parent
CONTENT_PREFIX = "instagram_tcg_content/"
SHARED_LEARNING_PREFIX = "shared_self_learning/"
EXCHANGE_PREFIX = "crosscheck_exchange/"

SKIP = {".git", ".venv", "venv", "__pycache__", "node_modules", "dist", "build"}
CONTROL_PLANE_FILES = {
    "selfrefine_domain_boundary_guard.py",
    "main_selfrefine_gate.py",
    "selfrefine_crosscheck_gate.py",
    "main_crosscheck_export.py",
    "test_selfrefine_domain_isolation_v18.py",
    "test_main_selfrefine_state_isolation_v18.py",
}
MAIN_DOMAIN_MODULES = {path.stem for path in ROOT.glob("*.py")}
STATEFUL_SHARED_IMPORTS = {
    "pathlib", "os", "subprocess", "sqlite3", "requests", "urllib", "http",
    "socket", "tempfile", "shelve", "pickle", "dbm", "shutil",
}
FORBIDDEN_SHARED_CALLS = {"open", "exec", "eval", "compile", "__import__"}

ALLOWED_EXCHANGE_SUFFIXES = {".json", ".jsonl"}
FORBIDDEN_EXCHANGE_SUFFIXES = {
    ".py", ".pyc", ".pyo", ".js", ".mjs", ".cjs", ".sh", ".command", ".bat", ".cmd",
    ".exe", ".dll", ".so", ".dylib", ".jar", ".zip", ".whl", ".pkl", ".pickle", ".joblib",
}
FORBIDDEN_EXCHANGE_STATE_FIELDS = {
    "retry_count", "cool", "cooldown", "provider_score", "provider_health",
    "learning_state", "error_ledger", "render_state", "collector_state",
}
DANGEROUS_EXCHANGE_IMPORTS = {"importlib", "runpy", "pickle", "cloudpickle", "joblib", "marshal", "subprocess"}


def imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    return found


def dynamic_import_targets(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    targets = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        function_name = ""
        if isinstance(node.func, ast.Name):
            function_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            function_name = node.func.attr
        if function_name not in {"__import__", "import_module", "run_module"}:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            targets.add(first.value.split(".")[0])
    return targets


def called_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            names.add(node.func.id)
    return names


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="strict")


def _validate_exchange_file(path: Path) -> None:
    if path.name == "schema.json":
        json.loads(_text(path))
        return
    if path.suffix.lower() == ".jsonl":
        for line_no, line in enumerate(_text(path).splitlines(), start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"line {line_no}: JSONL row must be an object")
            assert_passive_exchange_payload(value)
        return
    value = json.loads(_text(path))
    assert_passive_exchange_payload(value)


def main() -> int:
    errors: list[str] = []
    policy = json.loads((ROOT / "selfrefine_domain_policy.json").read_text(encoding="utf-8"))
    main_state = set(policy["domains"]["main"]["state_files"].values())
    instagram_state = set(policy["domains"]["instagram_content"]["state_files"].values())
    if main_state & instagram_state:
        errors.append("domain policy: Main and Instagram state files overlap")

    exchange = ROOT / EXCHANGE_PREFIX
    if exchange.exists():
        for path in exchange.rglob("*"):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            rel = str(path.relative_to(ROOT)).replace("\\", "/")
            if suffix in FORBIDDEN_EXCHANGE_SUFFIXES or suffix not in ALLOWED_EXCHANGE_SUFFIXES | {".md"}:
                errors.append(f"{rel}: exchange area must contain passive JSON/JSONL data only")
                continue
            if suffix in ALLOWED_EXCHANGE_SUFFIXES:
                try:
                    _validate_exchange_file(path)
                except Exception as exc:
                    errors.append(f"{rel}: passive exchange validation failed: {exc}")
                    continue
                if path.name != "schema.json":
                    text = _text(path)
                    for field in FORBIDDEN_EXCHANGE_STATE_FIELDS:
                        if re.search(rf'["\']{re.escape(field)}["\']\s*:', text):
                            errors.append(f"{rel}: cross-domain exchange contains forbidden state field {field}")

    for path in ROOT.rglob("*.py"):
        if any(part in SKIP for part in path.parts):
            continue
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        try:
            imports = imports_of(path)
            dynamic_targets = dynamic_import_targets(path)
            calls = called_names(path)
            text = _text(path)
        except Exception as exc:
            errors.append(f"{rel}: parse/read failure: {exc!r}")
            continue

        if rel.startswith(SHARED_LEARNING_PREFIX):
            bad = sorted((imports | dynamic_targets) & (MAIN_DOMAIN_MODULES | {"instagram_tcg_content"}))
            if bad:
                errors.append(f"{rel}: shared learning imports domain runtime modules: {bad}")
            stateful = sorted(imports & STATEFUL_SHARED_IMPORTS)
            if stateful:
                errors.append(f"{rel}: shared learning must be stateless/pure; stateful imports: {stateful}")
            dangerous_calls = sorted(calls & FORBIDDEN_SHARED_CALLS)
            if dangerous_calls:
                errors.append(f"{rel}: shared learning must not perform IO/dynamic execution: {dangerous_calls}")
            if any(name in text for name in main_state | instagram_state):
                errors.append(f"{rel}: shared learning code must not own persisted domain state")

        elif rel.startswith(CONTENT_PREFIX):
            bad = sorted((imports | dynamic_targets) & MAIN_DOMAIN_MODULES)
            if bad:
                errors.append(f"{rel}: Instagram content imports/calls Main modules: {bad}")
            if any(name in text for name in main_state):
                errors.append(f"{rel}: Instagram content must not read/write Main SELFREFINE state")
            if re.search(r"(?:open|Path)\s*\([^\n]*\.\./[^\n]*\.py", text):
                errors.append(f"{rel}: Instagram content references Main source code by path")

        else:
            if "instagram_tcg_content" in (imports | dynamic_targets):
                errors.append(f"{rel}: Main imports/calls Instagram content domain")
            if rel not in CONTROL_PLANE_FILES and any(name in text for name in instagram_state):
                errors.append(f"{rel}: Main runtime must not read/write Instagram SELFREFINE state")

        if EXCHANGE_PREFIX in text:
            dangerous_calls = sorted(calls & {"exec", "eval", "compile", "__import__"})
            dangerous_imports = sorted(imports & DANGEROUS_EXCHANGE_IMPORTS)
            if dangerous_calls or dangerous_imports:
                errors.append(
                    f"{rel}: exchange-data execution capability forbidden: "
                    f"calls={dangerous_calls} imports={dangerous_imports}"
                )

    if errors:
        for error in errors:
            print(error)
        return 1
    print(
        "SELFREFINE domain boundary: PASS "
        "(isolated domain state + pure shared algorithms + passive fail-closed crosscheck)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
