"""Mandatory independent second execution of the complete strict PC audit.

Run two full instances into *separate* output roots, using the same immutable
local Git HEAD and same version bounds. Match every output file by raw SHA-256
and length, then re-read both trees and record a sealed reconciliation receipt.

Important: two matching review records are NOT historical version certification
or proof that fixes pass production tests. Original Git files are never patched.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Callable

from audit import AuditError, atomic_json, digest, git_inventory, load_findings, read_checkpoint, validate_repo
from window_cycle import run_strict_cycle

SCHEMA = "tcg-pc-mandatory-independent-double-review/v6"
MAX_REPORT_FILES = 10000
MAX_SINGLE_REPORT_BYTES = 50_000_000
MAX_REPORT_TOTAL_BYTES = 200_000_000


def _inventory(folder: Path) -> dict[str, dict]:
    """Reopen actual files; a forged JSON check-sum never replaces raw checks."""
    if folder.is_symlink() or not folder.is_dir():
        raise AuditError("double_review_missing_or_symlinked_pass_folder")
    result: dict[str, dict] = {}
    total = 0
    for path in sorted(folder.rglob("*")):
        if path.is_symlink():
            raise AuditError("double_review_symlinked_output")
        if path.is_dir():
            continue
        if not path.is_file():
            raise AuditError("double_review_nonregular_output")
        rel = path.relative_to(folder).as_posix()
        if len(result) >= MAX_REPORT_FILES:
            raise AuditError("double_review_excessive_output_files")
        size = path.stat().st_size
        total += size
        if size > MAX_SINGLE_REPORT_BYTES or total > MAX_REPORT_TOTAL_BYTES:
            raise AuditError("double_review_excessive_output_bytes")
        h = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                h.update(block)
        if path.stat().st_size != size:
            raise AuditError("double_review_report_changed_while_reading")
        result[rel] = {"sha256": h.hexdigest(), "size": size}
    required = ("code_map.json", "code_map_hash.json", "V0001_V0100.json")
    # The last numeric slot may be less than 100 for short runs.
    for name in required[:2]:
        if name not in result:
            raise AuditError("double_review_expected_report_missing:" + name)
    if not any(p.startswith("V0001_V") and p.endswith(".json") for p in result):
        raise AuditError("double_review_first_window_checkpoint_missing")
    if not any(p.endswith("/window_gate.json") for p in result):
        raise AuditError("double_review_window_gate_missing")
    if "strict_window_status.json" not in result:
        raise AuditError("double_review_strict_status_missing")
    return result


def _check_original(repo: Path, head: str) -> None:
    _root, actual, _ = validate_repo(repo)
    if actual != head:
        raise AuditError("double_review_git_head_changed_between_passes")


def run_double_review(repo: Path, output: Path, latest: int | None = None, *,
                      docker_tests: bool = False,
                      docker_image: str = "python:3.11-slim",
                      callback: Callable[[str], None] | None = None,
                      stop_event=None) -> dict:
    """Full 1st pass + full independent 2nd pass, and fail-closed comparison."""
    callback = callback or (lambda _: None)
    repo, head, _ = validate_repo(repo)
    raw_output = output.expanduser()
    if raw_output.is_symlink():
        raise AuditError("double_review_output_symlink")
    root = raw_output.resolve()
    if root == repo or repo in root.parents or root in repo.parents:
        raise AuditError("double_review_output_must_not_overlap_git_checkout")
    paths = git_inventory(repo)
    _findings, _ledger, declared = load_findings(repo, paths)
    if latest is None:
        if declared is None:
            raise AuditError("supply_latest_version")
        latest = declared
    if type(latest) is not int or not 1 <= latest <= 9999:
        raise AuditError("double_review_invalid_latest")
    # Keep output roots physically separate so a reused/resumed first-pass
    # checkpoint cannot substitute for independent second-pass computation.
    if root.exists() and not root.is_dir():
        raise AuditError("double_review_output_not_directory")
    if root.is_symlink():
        raise AuditError("double_review_output_symlink")
    root.mkdir(parents=True, exist_ok=True)
    report_name = f"HEAD_{head[:12]}_V1-V{latest}"
    summaries = []
    inventories = []
    for i, part in enumerate(("first_pass", "second_pass"), start=1):
        if stop_event is not None and stop_event.is_set():
            raise AuditError("double_review_stopped_before_second_pass")
        _check_original(repo, head)
        callback(f"[전체 검수 {i}/2] 독립 증거 조사→격리 패치→전후 재검증")
        one = root / part
        if one.is_symlink():
            raise AuditError("double_review_pass_root_symlink")
        summary = run_strict_cycle(repo, one, latest=latest, resume=True,
                                   docker_tests=docker_tests,
                                   docker_image=docker_image,
                                   callback=callback, stop_event=stop_event)
        _check_original(repo, head)
        if summary.get("head_sha") != head or summary.get("latest") != latest:
            raise AuditError("double_review_wrong_source_or_version_scope")
        if (summary.get("next_window_allowed") is not False or
                summary.get("completed_remediated_windows") != 0 or
                summary.get("original_repository_modified") is not False or
                not str(summary.get("status", "")).startswith("HOLD_")):
            raise AuditError("double_review_invalid_advancement_claim")
        dest = one / report_name
        if dest.is_symlink() or not dest.is_dir():
            raise AuditError("double_review_pass_path_missing")
        summaries.append(summary)
        inventories.append(_inventory(dest))
    callback("[이중 교차검증] 전체 보고서 원시 SHA-256·파일크기·경로 비교")
    if summaries[0] != summaries[1]:
        raise AuditError("double_review_independent_status_disagrees")
    if inventories[0] != inventories[1]:
        divergent = sorted(set(inventories[0]) ^ set(inventories[1]) |
                           {p for p in inventories[0].keys() & inventories[1].keys()
                            if inventories[0][p] != inventories[1][p]})
        raise AuditError("double_review_independent_report_mismatch:" +
                         ",".join(divergent[:5]))
    _check_original(repo, head)
    row = {
        "schema": SCHEMA, "head_sha": head, "latest": latest,
        "pass_count": 2,
        "first_pass_status": summaries[0]["status"],
        "second_pass_status": summaries[1]["status"],
        "independent_report_bytes_and_sha256_equal": True,
        "compared_files": len(inventories[0]),
        "report_manifest_sha256": digest(inventories[0]),
        "windows_remediated_and_certified": 0,
        "next_window_allowed": False,
        "release_or_patch_approved": False,
        "physical_tablet_verified": False,
        "actual_tcg_functional_regressions_verified": False,
        "status": "HOLD_DOUBLE_REVIEW_MATCHED_BUT_HISTORICAL_AND_FUNCTIONAL_EVIDENCE_UNVERIFIED",
    }
    row["receipt_sha256"] = digest(row)
    receipt_path = root / "double_review_receipt.json"
    if receipt_path.exists() or receipt_path.is_symlink():
        if read_checkpoint(receipt_path) != row:
            raise AuditError("double_review_existing_receipt_disagrees")
    else:
        atomic_json(receipt_path, row)
    callback("[이중 검수 결과] 보고서 일치 PASS / 실제 버전·기능 승인 HOLD")
    return row
