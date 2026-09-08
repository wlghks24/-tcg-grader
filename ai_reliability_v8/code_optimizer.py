"""Bounded source candidate analysis, validation, promotion and exact rollback.

This module does not generate code, run shell commands, deploy, or alter schedules.
A host may supply an AI-generated candidate, but only an allowlisted file can be
replaced after syntax, regression, holdout and post-apply checks.
"""
import ast
import difflib
import hashlib
import os
import sqlite3
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


FORBIDDEN_IMPORTS = {"subprocess", "ctypes"}
FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__"}


@dataclass(frozen=True)
class CodeObservation:
    passed: bool
    evidence: str

    def success(self):
        return self.passed is True and isinstance(self.evidence, str) and bool(self.evidence)


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def analyze_source(text):
    if not isinstance(text, str) or not text or len(text.encode()) > 250_000:
        raise ValueError("SOURCE_SIZE_INVALID")
    tree = ast.parse(text)
    hazards = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [x.name.split(".")[0] for x in node.names] if isinstance(node, ast.Import) else [(node.module or "").split(".")[0]]
            hazards.extend("FORBIDDEN_IMPORT:" + name for name in names if name in FORBIDDEN_IMPORTS)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
            hazards.append("FORBIDDEN_CALL:" + node.func.id)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"system", "popen"}:
            hazards.append("FORBIDDEN_PROCESS_CALL:" + node.func.attr)
    return {"syntax_valid": True, "hazards": sorted(set(hazards)),
            "functions": sorted({n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}),
            "classes": sorted({n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)})}


class SafeCodeOptimizer:
    def __init__(self, project_root, state_root, *, allowlist):
        self.project_root = Path(project_root).resolve()
        self.state_root = Path(state_root).resolve()
        if not self.project_root.is_dir() or not isinstance(allowlist, (list, tuple)) or not allowlist:
            raise ValueError("ROOT_AND_ALLOWLIST_REQUIRED")
        self.allowlist = {str(Path(x)) for x in allowlist if Path(x).suffix == ".py" and not Path(x).is_absolute() and ".." not in Path(x).parts}
        if len(self.allowlist) != len(allowlist):
            raise ValueError("INVALID_ALLOWLIST")
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.db = self.state_root / "code_trials.sqlite"
        with sqlite3.connect(self.db) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS trials (path TEXT, before_hash TEXT, candidate_hash TEXT, passed INTEGER, evidence TEXT, at REAL, PRIMARY KEY(path,before_hash,candidate_hash))")

    def evaluate_and_apply(self, relative_path, candidate_text, *, validate, max_changed_lines=120):
        relative = str(Path(relative_path))
        if relative not in self.allowlist or type(max_changed_lines) is not int or not 1 <= max_changed_lines <= 300:
            return {"status": "PATH_OR_LIMIT_NOT_ALLOWED"}
        path = (self.project_root / relative).resolve()
        if not path.is_relative_to(self.project_root) or path.is_symlink() or not path.is_file():
            return {"status": "INVALID_SOURCE_PATH"}
        original = path.read_bytes()
        try:
            old_text = original.decode("utf-8")
            report = analyze_source(candidate_text)
        except (UnicodeError, SyntaxError, ValueError) as exc:
            return {"status": "CANDIDATE_REJECTED", "reason": type(exc).__name__}
        if report["hazards"]:
            return {"status": "CANDIDATE_REJECTED", "reason": "STATIC_HAZARD", "hazards": report["hazards"]}
        changed = sum(1 for line in difflib.ndiff(old_text.splitlines(), candidate_text.splitlines()) if line[:1] in ("+", "-"))
        if changed == 0:
            return {"status": "NO_CHANGE"}
        if changed > max_changed_lines:
            return {"status": "CANDIDATE_REJECTED", "reason": "CHANGE_BUDGET_EXCEEDED", "changed_lines": changed}
        candidate = candidate_text.encode("utf-8")
        before_hash, candidate_hash = _digest(original), _digest(candidate)
        with sqlite3.connect(self.db) as conn:
            prior = conn.execute("SELECT passed FROM trials WHERE path=? AND before_hash=? AND candidate_hash=?", (relative, before_hash, candidate_hash)).fetchone()
        if prior:
            return {"status": "ALREADY_EVALUATED", "passed": bool(prior[0])}
        fd, temp_name = tempfile.mkstemp(prefix=path.name + ".candidate.", suffix=".py", dir=path.parent)
        backup = self.state_root / (hashlib.sha256(relative.encode()).hexdigest() + ".rollback")
        applied = False
        evidence = ""
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(candidate); stream.flush(); os.fsync(stream.fileno())
            for suite in ("syntax", "targeted_regression", "holdout"):
                observed = validate(Path(temp_name), suite)
                if not isinstance(observed, CodeObservation) or not observed.success():
                    evidence = "VALIDATION_FAILED:" + suite
                    return self._finish(relative, before_hash, candidate_hash, False, evidence,
                                        {"status": "NO_VERIFIED_CODE_FIX", "failed_suite": suite})
            if path.read_bytes() != original or backup.exists():
                return {"status": "SOURCE_CHANGED_OR_ROLLBACK_PENDING"}
            with backup.open("xb") as stream:
                stream.write(original); stream.flush(); os.fsync(stream.fileno())
            os.replace(temp_name, path); applied = True
            post = validate(path, "post_apply")
            if not isinstance(post, CodeObservation) or not post.success() or path.read_bytes() != candidate:
                os.replace(backup, path); applied = False
                return self._finish(relative, before_hash, candidate_hash, False, "POST_APPLY_FAILED",
                                    {"status": "ROLLED_BACK"})
            backup.unlink(); applied = False
            return self._finish(relative, before_hash, candidate_hash, True, "ALL_GATES_PASSED",
                                {"status": "CODE_FIX_APPLIED", "changed_lines": changed,
                                 "revision": candidate_hash, "scheduler_mutated": False})
        except Exception as exc:
            if applied and backup.exists() and path.read_bytes() == candidate:
                os.replace(backup, path); applied = False
            return {"status": "OPTIMIZER_ERROR", "error_type": type(exc).__name__}
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def _finish(self, path, before_hash, candidate_hash, passed, evidence, result):
        with sqlite3.connect(self.db) as conn:
            conn.execute("INSERT OR IGNORE INTO trials VALUES (?,?,?,?,?,?)",
                         (path, before_hash, candidate_hash, int(passed), evidence, time.time()))
        return result

