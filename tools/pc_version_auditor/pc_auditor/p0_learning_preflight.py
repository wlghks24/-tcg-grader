"""Read-only P0 grading evidence and verified-flag preflight.

This module proves only static code patterns against exact Git HEAD blobs.
It NEVER declares runtime safety, fixes protected files or approves a release.
"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path

from audit import AuditError, git

SCHEMA = "tcg-pc-p0-learning-evidence-preflight/v1"
MAX_SOURCE = 2_000_000
SOURCES = ("tcg_updater.py", "grading_self_learning.py")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _function(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _is_literal_true(value: ast.AST) -> bool:
    return isinstance(value, ast.Constant) and value.value is True


def _verified_is_explicit_true(node: ast.AST) -> bool:
    # Only an *exact* `is True` comparison supplies a recognizable static
    # guard. Other implementations require independent semantic review.
    return (isinstance(node, ast.Compare) and len(node.ops) == 1
            and isinstance(node.ops[0], ast.Is)
            and len(node.comparators) == 1 and _is_literal_true(node.comparators[0]))


def inspect_grading(raw: bytes) -> dict:
    tree = ast.parse(raw.decode("utf-8"), filename="grading_self_learning.py")
    fn = _function(tree, "sanitize_sample")
    if fn is None:
        return {"status": "HOLD_SOURCE_SHAPE_UNKNOWN", "risk": "인증자료 검사 함수를 확인하지 못함"}
    guards = []
    for node in ast.walk(fn):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) and target.id == "verified" for target in targets):
            continue
        guards.append(node.value)
    # Fail closed: bool('false') and bool(1) both return True.
    if any(isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
           and value.func.id == "bool" for value in guards):
        return {"status": "HOLD_TRUTHY_VERIFICATION", "risk": "문자열 false·숫자 1 등이 학습 인증으로 오판될 수 있음"}
    if not guards or not all(_verified_is_explicit_true(value) for value in guards):
        return {"status": "HOLD_VERIFICATION_SEMANTICS_UNKNOWN",
                "risk": "인증 플래그의 실제 타입·거부 조건을 별도로 검증해야 함"}
    return {"status": "STATIC_TRUE_GUARD_PRESENT_REQUIRES_REGRESSION",
            "risk": "정적 비교만 확인했으며 실제 모델·기능 회귀검사는 아직 미검증"}


def _is_endpoint_if(node: ast.If) -> bool:
    test = node.test
    if not isinstance(test, ast.Compare) or len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq):
        return False
    values = [test.left, *test.comparators]
    return (any(isinstance(v, ast.Name) and v.id == "post_path" for v in values)
            and any(isinstance(v, ast.Constant) and v.value == "/api/learning-store"
                    for v in values))


def inspect_updater(raw: bytes) -> dict:
    tree = ast.parse(raw.decode("utf-8"), filename="tcg_updater.py")
    branches = [n for n in ast.walk(tree) if isinstance(n, ast.If) and _is_endpoint_if(n)]
    if len(branches) != 1:
        return {"status": "HOLD_POST_ENDPOINT_UNKNOWN", "risk": "학습 저장 API 경로를 정확히 확인하지 못함"}
    branch = branches[0]
    writes = [n for n in ast.walk(branch) if isinstance(n, ast.Call)
              and isinstance(n.func, ast.Name) and n.func.id == "save_json_atomic"
              and len(n.args) >= 2 and isinstance(n.args[0], ast.Name)
              and n.args[0].id == "LEARNING_STORE"]
    if len(writes) != 1 or not isinstance(writes[0].args[1], ast.Name):
        return {"status": "HOLD_SAVE_OPERATION_UNKNOWN", "risk": "학습자료 저장 호출을 별도 검증해야 함"}
    data_name = writes[0].args[1].id
    assignments = [n for n in ast.walk(branch) if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == data_name for t in n.targets)]
    if len(assignments) != 1 or not isinstance(assignments[0].value, ast.Dict):
        return {"status": "HOLD_SAVED_PAYLOAD_UNKNOWN", "risk": "실제 저장 데이터 구성을 확인하지 못함"}
    keys = assignments[0].value.keys
    names = {k.value for k in keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    # A literal three-validation-only dict loses *other* persisted evidence.
    if all(k is not None for k in keys) and "confirmed_samples" not in names:
        return {"status": "HOLD_CONFIRMED_SAMPLES_DISCARDED",
                "risk": "학습 저장 POST에서 기존 confirmed_samples가 새 저장 딕셔너리에 포함되지 않음"}
    return {"status": "HOLD_PERSISTENCE_SEMANTICS_REVIEW",
            "risk": "저장 필드가 보이지만 원본 보존·동시성·백업·실제 회귀검증은 필요함"}


def evaluate(source_bytes: dict[str, bytes], *, head: str) -> dict:
    findings = []
    for path in SOURCES:
        raw = source_bytes.get(path)
        if not isinstance(raw, bytes):
            findings.append({"path": path, "source_sha256": None,
                             "status": "HOLD_SOURCE_ABSENT",
                             "risk": "이 HEAD에 검증 가능한 파일이 없음"})
            continue
        if len(raw) > MAX_SOURCE:
            raise AuditError("p0_source_too_large")
        try:
            item = inspect_updater(raw) if path == "tcg_updater.py" else inspect_grading(raw)
        except (UnicodeDecodeError, SyntaxError, ValueError) as exc:
            item = {"status": "HOLD_UNPARSEABLE_SOURCE", "risk": "원본 소스 구문·인코딩 오류: " + type(exc).__name__}
        findings.append({"path": path, "source_sha256": _sha(raw), **item})
    return {"schema": SCHEMA, "head_sha": head, "status": "HOLD_P0_RUNTIME_NOT_APPROVED",
            "findings": findings, "next_window_allowed": False,
            "functional_test": "NOT_RUN", "protected_successor": "NOT_VERIFIED",
            "physical_device_verified": False}


def inspect_git(repo: Path, *, head: str, tracked_paths: list[str]) -> dict:
    # Git HEAD blobs only: ignore possibly modified working-tree files.
    blobs = {}
    for path in SOURCES:
        if path in tracked_paths:
            blobs[path] = git(repo, "cat-file", "blob", "HEAD:" + path,
                              limit=MAX_SOURCE + 1)
    return evaluate(blobs, head=head)
