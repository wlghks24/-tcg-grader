"""Skeptical independent source recheck and mandatory adversarial rereview.

These gates certify *audit records*, never V-releases or functional patch safety.
They only read immutable local Git objects and locally generated reports. Project
source code and SKILL.md files are never imported/executed here.
"""
from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path

from audit import (AuditError, atomic_json, canonical, code_map, digest, git,
                   git_history, git_inventory, load_findings, read_checkpoint,
                   validate_repo)

WINDOW_SCHEMA = "tcg-pc-skeptical-window-review/v4"
PATCH_SCHEMA = "tcg-pc-independent-patch-review/v4"
# Independent parser, not delegated to the first-pass version_tokens function.
V_PATTERN = re.compile(r"(?<![A-Za-z0-9])V0*(\d{1,4})(?![A-Za-z0-9])", re.I)


def independent_sources(root: Path, head: str, latest: int,
                        first_paths: list[str], first_history: dict,
                        first_findings: list[dict], code_data: dict, stop=None) -> dict:
    """Read same pinned tree/history afresh and cross-examine the saved map."""
    _root, actual, shallow = validate_repo(root)
    if actual != head:
        raise AuditError("crosscheck_source_head_changed")
    paths = git_inventory(root)
    history, limited, _n = git_history(root, latest)
    findings, _ledger, _max = load_findings(root, paths)
    if paths != first_paths or history != first_history or findings != first_findings:
        raise AuditError("crosscheck_independent_git_evidence_differs")
    fresh_map = code_map(root, paths, stop)
    original = {k: v for k, v in code_data.items()
                if k not in ("head_sha", "history_complete")}
    if digest(fresh_map) != digest(original):
        raise AuditError("crosscheck_code_map_disagrees_with_git")
    if code_data.get("history_complete") is not (not (limited or shallow)):
        raise AuditError("crosscheck_history_completeness_disagrees")
    return {"paths": paths, "history": history, "findings": findings,
            "evidence_sha256": digest({"paths": paths,"history": history,
                                       "findings": findings}),
            "head": head, "code_map_sha256": digest(code_data)}


def verify_window(root: Path, report: Path, checkpoint: dict, expected: dict,
                  independent: dict, *, latest: int, previous: str | None) -> dict:
    """Three distinct strict gates before recording/entering the next window."""
    first, last = expected["first"], expected["last"]
    if checkpoint != expected:
        raise AuditError("window_first_pass_reconstruction_disagrees")
    if checkpoint.get("checkpoint_parent_sha256") != previous:
        raise AuditError("window_parent_does_not_match_previous_review")
    if checkpoint.get("checkpoint_sha256") != digest(
            {k: v for k, v in checkpoint.items() if k != "checkpoint_sha256"}):
        raise AuditError("window_digest_does_not_match_content")
    _r, actual, _s = validate_repo(root)
    if actual != independent["head"]:
        raise AuditError("window_source_head_changed")
    # Independent per-number reproduction from a second Git read. The legacy
    # generator/first-pass group_window is NOT used to build this expectation.
    separate_paths = {}
    for rel in independent["paths"]:
        for match in V_PATTERN.finditer(rel):
            n = int(match.group(1))
            if first <= n <= last and n <= latest:
                separate_paths.setdefault(n, set()).add(rel)
    for i, slot in enumerate(checkpoint.get("slots", [])):
        number = first + i
        if (not isinstance(slot, dict) or slot.get("version") != number
                or slot.get("window_start") is not None):
            raise AuditError("window_independent_slot_number_mismatch")
        expect_paths = sorted(separate_paths.get(number, set()))[:120]
        expect_commits = independent["history"].get(number, [])[:50]
        if slot.get("path_hints") != expect_paths or slot.get("commit_subject_hints") != expect_commits:
            raise AuditError("window_independent_source_hints_disagree")
        state = "LEADS_ONLY_NOT_REVIEWED" if expect_paths or expect_commits else "NO_EVIDENCE_LEAD_NOT_REVIEWED"
        if slot.get("status") != state:
            raise AuditError("window_independent_hint_classification_disagree")
        # Explicit adversarial review: no missing evidence is a negative test,
        # no version token is a valid release, no device/full review has run.
        if (slot.get("source_review") != "NOT_PERFORMED" or
                slot.get("tests") != "NOT_RUN" or
                slot.get("device") != "UNVERIFIED" or
                slot.get("quality_score") is not None):
            raise AuditError("window_adversarial_re_review_detects_false_certification")
    if len(checkpoint.get("slots", [])) != last - first + 1:
        raise AuditError("window_independent_slot_count_disagrees")
    expected_open = [f for f in independent["findings"] if f["start"] <= last
                     and f["state"] != "HISTORICAL_REPAIR_EVIDENCED"]
    if checkpoint.get("open_findings_carry_forward") != expected_open:
        raise AuditError("window_carry_forward_evidence_disagrees")
    if (checkpoint.get("source") != "LOCAL_GIT_READ_ONLY"
            or checkpoint.get("head_sha") != independent["head"]
            or checkpoint.get("code_map_sha256") != independent["code_map_sha256"]
            or checkpoint.get("device_verified") is not False
            or checkpoint.get("quality_score") is not None):
        raise AuditError("window_adversarial_metadata_mismatch")
    row = {"schema": WINDOW_SCHEMA,"head_sha": independent["head"],
           "window": {"first": first, "last": last},
           "checkpoint_sha256": checkpoint["checkpoint_sha256"],
           "previous_window_sha256": previous,
           "independent_evidence_sha256": independent["evidence_sha256"],
           "gates": {
               "first_pass_original_reconstruction": "PASS",
               "second_pass_independent_git_evidence": "PASS",
               "third_pass_adversarial_noncertification_review": "PASS",
           },
           "next_window_audit_allowed": True,
           "release_or_patch_approved": False,
           "state": "AUDIT_RECORD_CROSSCHECKED_NOT_VERSION_CERTIFIED"}
    row["review_receipt_sha256"] = digest(row)
    name = report / f"crosscheck_V{first:04d}_V{last:04d}.json"
    if name.exists():
        old = read_checkpoint(name)
        if old != row:
            raise AuditError("window_crosscheck_receipt_changed_or_forged")
    else:
        atomic_json(name, row)
    return row


class _SafeTrueTransformer(ast.NodeTransformer):
    """Independent AST structural reconstruction of only the guarded rule."""
    def __init__(self):
        self.count = 0

    def visit_Call(self, node: ast.Call):
        self.generic_visit(node)
        if not (isinstance(node.func, ast.Name) and node.func.id == "bool"
                and len(node.args) == 1 and not node.keywords):
            return node
        call = node.args[0]
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                and call.func.attr == "get" and 1 <= len(call.args) <= 2
                and not call.keywords and isinstance(call.args[0], ast.Constant)
                and call.args[0].value in ("verified", "resolution_confirmed")):
            return node
        self.count += 1
        return ast.copy_location(ast.Compare(left=call, ops=[ast.Is()],
                                             comparators=[ast.Constant(value=True)]), node)


def re_review_candidate(source: bytes, candidate: bytes, *, number: int) -> dict:
    """A *separate* AST transformer checks no unrelated executable AST changed."""
    try:
        before = ast.parse(source.decode("utf-8"))
        after = ast.parse(candidate.decode("utf-8"))
    except (UnicodeDecodeError, SyntaxError, ValueError) as exc:
        raise AuditError("candidate_second_pass_ast_not_parseable") from exc
    transformer = _SafeTrueTransformer()
    expected = transformer.visit(before)
    if number <= 0 or transformer.count != number:
        raise AuditError("candidate_second_pass_rule_count_disagrees")
    if ast.dump(expected, include_attributes=False) != ast.dump(after, include_attributes=False):
        raise AuditError("candidate_second_pass_unrelated_code_changed")
    # Deliberately compare unsafe truthy input values with strict booleans;
    # this is a reference truth-table, not execution of project code.
    truth_values = (True, False, None, 0, 1, "false", "true", "0", "1", [], {})
    expected_values = (True, False, False, False, False, False, False, False, False, False, False)
    if tuple(value is True for value in truth_values) != expected_values:
        raise AuditError("candidate_negative_truth_table_disagrees")
    return {"structural_ast_recheck":"PASS",
            "negative_truthiness_matrix":"PASS",
            "negative_input_count":len(truth_values),
            "human_semantic_review":"NOT_PERFORMED",
            "production_regression":"NOT_RUN",
            "promote_allowed":False}
