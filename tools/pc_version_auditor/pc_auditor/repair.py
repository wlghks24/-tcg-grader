"""Generate narrowly bounded staging-only code candidates and a prioritized plan.

Never imports or runs repository Python, writes back to Git, trains a model,
changes a protected runtime, or declares a patch approved. Syntax parse only.
"""
from __future__ import annotations

import ast
import difflib
import hashlib
import json
import re
from pathlib import Path

from audit import AuditError, atomic_json, atomic_text, git, read_checkpoint

RULE = "STRICT_TRUE_VERIFIED_CANDIDATE"
MAX_PATCH_FILES = 40
MAX_PATCH_BYTES = 350_000
MAX_PY_SOURCE = 1_000_000
FLAGS = {"verified", "resolution_confirmed"}
SAFE_FILENAME = re.compile(r"[^a-zA-Z0-9_.-]+")


def _offset(lines: list[bytes], lineno: int, column: int) -> int:
    return sum(len(x) for x in lines[:lineno-1]) + column


def guarded_candidates(original: bytes) -> tuple[bytes, int]:
    """Only bool(record.get('verified'|'resolution_confirmed'[, default])).

    AST byte offsets accommodate UTF-8 content. Every replacement is validated
    as Python syntax; no runtime evaluation is attempted.
    """
    if len(original) > MAX_PY_SOURCE:
        raise AuditError("patch_source_too_large")
    try:
        source = original.decode("utf-8")
        tree = ast.parse(source)
    except (UnicodeDecodeError, SyntaxError, ValueError) as exc:
        raise AuditError("patch_requires_valid_python_source") from exc
    lines = original.splitlines(keepends=True)
    spans = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id != "bool" or len(node.args) != 1 or node.keywords:
            continue
        inner = node.args[0]
        if not isinstance(inner, ast.Call) or not isinstance(inner.func, ast.Attribute):
            continue
        if inner.func.attr != "get" or not inner.args or not isinstance(inner.args[0], ast.Constant):
            continue
        if inner.args[0].value not in FLAGS or len(inner.args) > 2 or inner.keywords:
            continue
        # This proposed semantic change is held for human review even when AST-valid.
        start = _offset(lines, node.lineno, node.col_offset)
        end = _offset(lines, node.end_lineno, node.end_col_offset)
        expr = original[_offset(lines, inner.lineno, inner.col_offset):
                        _offset(lines, inner.end_lineno, inner.end_col_offset)]
        spans.append((start, end, b"(" + expr + b" is True)"))
    if not spans:
        return original, 0
    for left, right in zip(sorted(spans), sorted(spans)[1:]):
        if left[1] > right[0]:
            raise AuditError("overlapping_static_patch_candidates")
    patched = original
    for start, end, replacement in sorted(spans, reverse=True):
        patched = patched[:start] + replacement + patched[end:]
    try:
        ast.parse(patched.decode("utf-8"))
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise AuditError("generated_patch_invalid_ast") from exc
    return patched, len(spans)


def improvement_items(code: dict, findings: list[dict]) -> list[dict]:
    items: list[dict] = []
    for issue in code.get("syntax_or_encoding_issues", []):
        items.append({"priority": "P0", "kind": "SYNTAX_OR_ENCODING",
                      "path": issue.get("path"), "line": issue.get("line"),
                      "state": "MANUAL_REPRO_REQUIRED"})
    for hint in code.get("risk_hints", []):
        items.append({"priority": "P0" if hint["rule"] in {"TRUTHY_VERIFICATION_FLAG_REVIEW",
                                 "LEARNING_STORE_PRESERVATION_REVIEW"} else "P1",
                      "kind": hint["rule"], "path": hint["path"],
                      "line": hint["line"], "state": "REVIEW_REQUIRED"})
    for row in findings:
        if row.get("state") != "HISTORICAL_REPAIR_EVIDENCED":
            items.append({"priority": row.get("severity") or "P1", "kind": "CARRIED_OPEN_FINDING",
                          "finding_id": row.get("id"), "summary": row.get("summary"),
                          "state": "OPEN_NOT_AUTOCLOSED"})
    for skipped in code.get("skipped", []):
        items.append({"priority": "P2", "kind": "SKIPPED_SOURCE", "path": skipped.get("path"),
                      "state": "COVERAGE_GAP"})
    order = {"P0": 0, "P1": 1, "P2": 2}
    return sorted(items, key=lambda item: (order.get(item["priority"], 3),
                                             item.get("path", ""), item.get("kind", "")))


def stage_repair_candidates(root: Path, target: Path, code_map: dict,
                            findings: list[dict]) -> dict:
    """Generate review proposals ONLY outside the Git checkout.

    A static AST pass does not establish correctness, calibration stability,
    safety, review approval, CI success, or on-device behavior.
    """
    proposals = []
    by_path = sorted({x["path"] for x in code_map.get("risk_hints", [])
                      if x.get("rule") == "TRUTHY_VERIFICATION_FLAG_REVIEW"})
    candidate_dir = target / "repair_candidates"
    if candidate_dir.is_symlink():
        raise AuditError("unsafe_patch_directory_symlink")
    for rel in by_path[:MAX_PATCH_FILES]:
        if (not isinstance(rel, str) or rel.startswith("/") or ".." in rel.split("/")
                or "\\" in rel or "\x00" in rel or not rel.endswith(".py")):
            raise AuditError("unsafe_patch_candidate_path")
        blob = git(root, "cat-file", "blob", "HEAD:" + rel, limit=MAX_PY_SOURCE + 1)
        if len(blob) > MAX_PY_SOURCE:
            proposals.append({"path": rel, "state": "SOURCE_TOO_LARGE_NOT_PATCHED"})
            continue
        try:
            patched, count = guarded_candidates(blob)
        except AuditError as exc:
            proposals.append({"path": rel, "state": "PATCH_BLOCKED_REQUIRES_REVIEW",
                              "reason": str(exc)})
            continue
        if not count or patched == blob:
            continue
        old_text, new_text = blob.decode("utf-8"), patched.decode("utf-8")
        diff = "".join(difflib.unified_diff(old_text.splitlines(keepends=True),
                    new_text.splitlines(keepends=True), fromfile="a/" + rel,
                    tofile="b/" + rel))
        if len(diff.encode("utf-8")) > MAX_PATCH_BYTES:
            proposals.append({"path": rel, "state": "PATCH_EXCEEDS_SIZE_LIMIT"})
            continue
        # SHA suffix avoids filename collisions and path traversal.
        file_name = SAFE_FILENAME.sub("_", rel)[:85] + "_" + hashlib.sha256(rel.encode()).hexdigest()[:12] + ".patch"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        path = candidate_dir / file_name
        if path.is_symlink():
            raise AuditError("unsafe_patch_output_symlink")
        if path.exists():
            # On resume, never silently overwrite a modified proposal.
            if not path.is_file() or path.read_bytes() != diff.encode('utf-8'):
                raise AuditError('existing_patch_tampered')
        else:
            atomic_text(path, diff)
        proposals.append({"path": rel, "rule": RULE, "state": "PROPOSAL_AST_PASS_HUMAN_REVIEW_REQUIRED",
                          "patch_file": str(path.relative_to(target)), "replacements": count,
                          "source_sha256": hashlib.sha256(blob).hexdigest(),
                          "candidate_sha256": hashlib.sha256(patched).hexdigest(),
                          "candidate_executed": False, "tests_run": False,
                          "main_or_tablet_modified": False})
    plan = {"schema": "tcg-pc-safe-remediation/v2", "head_sha": code_map["head_sha"],
            "status": "PATCH_PROPOSALS_ONLY_NOT_APPROVED",
            "rules": {"tcg-code-review": "read-only guidance", "tcg-test-gap-audit": "gaps identified",
                      "tcg-regression-recovery": "successor/integrity gate required"},
            "priority_items": improvement_items(code_map, findings),
            "proposals": proposals,
            "unscanned_candidate_files_due_to_limit": max(0, len(by_path) - MAX_PATCH_FILES),
            "limitations": ["Never apply patches automatically to original repository or protected main",
                            "Only strict-True static AST proposals; no execution or behavioral proof",
                            "All other missing logic needs a reviewed implementation and regression tests",
                            "Do not claim model training, GitHub merge, Lenovo installation, or release certification"]}
    plan_path = target / "remediation_plan.json"
    if plan_path.exists() or plan_path.is_symlink():
        if read_checkpoint(plan_path, max_bytes=10_000_000) != plan:
            raise AuditError("existing_remediation_plan_disagrees_with_git")
    else:
        atomic_json(plan_path, plan)
    return {"priority_items": len(plan["priority_items"]), "candidate_files": len(proposals),
            "ast_pass_proposals": sum(p.get("state") == "PROPOSAL_AST_PASS_HUMAN_REVIEW_REQUIRED"
                                      for p in proposals), "report": "remediation_plan.json"}
