#!/usr/bin/env python3
from __future__ import annotations

import ast
from collections import Counter
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parent
SKIP_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "node_modules",
    ".precollect_stage", ".precollect_stage.tmp", ".tcg_runtime_preserved",
    ".tcg_last_good", ".tcg_reliability_state", "graphify-out",
}


def tracked_files() -> list[Path]:
    output = subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=ROOT
    )
    return [ROOT / item.decode("utf-8") for item in output.split(b"\0") if item]


def active(path: Path) -> bool:
    try:
        rel = path.relative_to(ROOT)
    except ValueError:
        return False
    return not any(part in SKIP_DIRS for part in rel.parts)


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def reject_constant(value: str):
    raise ValueError(f"non-finite JSON constant: {value}")


class FullRepoStructuralAuditV317(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = [p for p in tracked_files() if active(p)]

    def test_all_tracked_python_parses_and_active_modules_have_no_duplicate_top_level_definitions(self):
        failures = []
        for path in self.files:
            if path.suffix.lower() != ".py":
                continue
            rel = path.relative_to(ROOT).as_posix()
            try:
                tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=rel)
            except SyntaxError as exc:
                failures.append(f"syntax {rel}:{exc.lineno}: {exc.msg}")
                continue
            if path.name.startswith("test_") or "trusted_ai_tests" in path.parts:
                continue
            names = [
                node.name for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            ]
            duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
            if duplicates:
                failures.append(f"duplicate-top-level {rel}: {duplicates}")
        self.assertFalse(failures, "\n" + "\n".join(failures))

    def test_python_runtime_has_no_unsafe_deserialization_dynamic_execution_or_tls_disable(self):
        failures = []
        dangerous = {
            "eval", "exec", "os.system", "pickle.load", "pickle.loads",
            "marshal.load", "marshal.loads",
        }
        subprocess_calls = {
            "subprocess.run", "subprocess.Popen", "subprocess.call",
            "subprocess.check_call", "subprocess.check_output",
        }
        http_calls = {
            "requests.get", "requests.post", "requests.put", "requests.patch",
            "requests.delete", "requests.request", "httpx.get", "httpx.post",
            "httpx.request",
        }
        for path in self.files:
            if path.suffix.lower() != ".py" or path.name.startswith("test_"):
                continue
            rel = path.relative_to(ROOT).as_posix()
            try:
                tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=rel)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                try:
                    name = ast.unparse(node.func)
                except (AttributeError, ValueError):
                    name = ""
                line = getattr(node, "lineno", 1)
                if name in dangerous:
                    failures.append(f"dangerous-call {rel}:{line}: {name}")
                if name == "yaml.load":
                    loader = None
                    for kw in node.keywords:
                        if kw.arg == "Loader":
                            try:
                                loader = ast.unparse(kw.value)
                            except (AttributeError, ValueError):
                                loader = "?"
                    if loader not in {"yaml.SafeLoader", "SafeLoader"}:
                        failures.append(f"unsafe-yaml-load {rel}:{line}: loader={loader}")
                if name in subprocess_calls:
                    for kw in node.keywords:
                        if (
                            kw.arg == "shell"
                            and isinstance(kw.value, ast.Constant)
                            and kw.value.value is True
                        ):
                            failures.append(f"shell-true {rel}:{line}: {name}")
                if name in http_calls:
                    for kw in node.keywords:
                        if (
                            kw.arg == "verify"
                            and isinstance(kw.value, ast.Constant)
                            and kw.value.value is False
                        ):
                            failures.append(f"tls-verify-false {rel}:{line}: {name}")
        self.assertFalse(failures, "\n" + "\n".join(failures))

    def test_all_tracked_json_is_strict_no_duplicate_keys_or_nan_inf(self):
        failures = []
        for path in self.files:
            if path.suffix.lower() != ".json" or path.name.endswith(".bak"):
                continue
            rel = path.relative_to(ROOT).as_posix()
            try:
                json.loads(
                    path.read_text(encoding="utf-8-sig"),
                    object_pairs_hook=strict_object,
                    parse_constant=reject_constant,
                )
            except (OSError, UnicodeError, ValueError, TypeError) as exc:
                failures.append(f"strict-json {rel}: {type(exc).__name__}: {exc}")
        self.assertFalse(failures, "\n" + "\n".join(failures))

    def test_all_tracked_javascript_and_shell_files_parse(self):
        failures = []
        for path in self.files:
            rel = path.relative_to(ROOT).as_posix()
            if path.suffix.lower() == ".js":
                proc = subprocess.run(
                    ["node", "--check", str(path)], cwd=ROOT,
                    text=True, capture_output=True, check=False,
                )
                if proc.returncode:
                    failures.append(f"js-syntax {rel}: {proc.stderr.strip()[:300]}")
            elif path.suffix.lower() == ".sh":
                proc = subprocess.run(
                    ["bash", "-n", str(path)], cwd=ROOT,
                    text=True, capture_output=True, check=False,
                )
                if proc.returncode:
                    failures.append(f"sh-syntax {rel}: {proc.stderr.strip()[:300]}")
        self.assertFalse(failures, "\n" + "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
