"""Mandatory per-100-window inspect -> isolate remediation -> compare -> recheck -> HOLD.

The next window is *never* visited solely because a version-number inventory
passed its three static consistency checks. Historical release/feature source,
negative functional tests, independent CI and reviewed protected successors
cannot be manufactured from a filename hint. Work stays outside the Git tree.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable

from audit import (AuditError, atomic_json, atomic_text, digest, git_history,
                   git_inventory, group_window, load_findings,
                   read_checkpoint, run_audit, validate_repo)
from crosscheck import independent_sources, verify_window
from repair import stage_repair_candidates
from skills_registry import registered_skills
from validation import _write_or_check, validate_and_handoff

GATE_SCHEMA = "tcg-pc-window-remediation-gate/v5"


def _checked_window(repo: Path, target: Path, *, head: str, latest: int,
                    start: int, stop=None) -> tuple[dict, dict, dict]:
    """Re-read the evidence independently, including on every resume."""
    _root, actual, shallow = validate_repo(repo)
    if actual != head:
        raise AuditError("window_remediation_git_head_changed")
    paths = git_inventory(repo)
    history, limited, _ = git_history(repo, latest)
    findings, _ledger, _max = load_findings(repo, paths)
    map_data = read_checkpoint(target / "code_map.json", max_bytes=40_000_000)
    seal = read_checkpoint(target / "code_map_hash.json")
    if (map_data.get("head_sha") != head or
            seal.get("head_sha") != head or seal.get("sha256") != digest(map_data)):
        raise AuditError("window_remediation_code_map_seal_invalid")
    independent = independent_sources(repo, head, latest, paths, history,
                                     findings, map_data, stop)
    end = min(start + 99, latest)
    expected = group_window(start, latest, paths, history, findings, head,
                            None, not (shallow or limited), digest(map_data))
    stored = read_checkpoint(target / f"V{start:04d}_V{end:04d}.json")
    receipt = verify_window(repo, target, stored, expected, independent,
                            latest=latest, previous=None)
    return stored, map_data, {"findings": findings, "receipt": receipt}


def _one_window(repo: Path, target: Path, *, head: str, latest: int,
                docker_tests: bool, docker_image: str, callback: Callable[[str], None],
                stop_event=None) -> dict:
    start = 1
    end = min(100, latest)
    checkpoint, source_map, evidence = _checked_window(repo, target, head=head,
                                                       latest=latest, start=start,
                                                       stop=stop_event)
    if stop_event is not None and stop_event.is_set():
        raise AuditError("window_remediation_stopped_before_review")
    window_dir = target / f"window_remediation_V{start:04d}_V{end:04d}"
    if window_dir.is_symlink() or (window_dir.exists() and not window_dir.is_dir()):
        raise AuditError("window_remediation_unsafe_output_directory")
    window_dir.mkdir(exist_ok=True)
    paths = git_inventory(repo)
    callback(f"V{start}~V{end}: 미검증 항목 분류·전후 비교·격리 보완 후보 생성")
    routes = registered_skills(repo, paths, __import__('audit').git,
                               source_map.get("risk_hints"))
    _write_or_check(window_dir / "skills_applied.json", {
        "head_sha": head, "scope": "REGISTERED_REPO_SKILLS_READ_ONLY_NO_EXECUTION",
        "skills": routes, "external_skill_installation": False,
        "skill_instructions_execute_as_code": False})
    within = [row for row in evidence["findings"] if row["start"] <= end]
    remediation = stage_repair_candidates(repo, window_dir, source_map, within)
    validation = validate_and_handoff(repo, window_dir, head=head,
                                      docker_tests=docker_tests,
                                      docker_image=docker_image)
    proposal = read_checkpoint(window_dir / "remediation_plan.json", max_bytes=12_000_000)
    evaluated = read_checkpoint(window_dir / "candidate_validation.json", max_bytes=12_000_000)
    approval = read_checkpoint(window_dir / "approval_packet.json", max_bytes=12_000_000)
    before_after = []
    staged = {x["path"]: x for x in evaluated["staged"]}
    for item in proposal["proposals"]:
        path = item.get("path")
        result = staged.get(path, {})
        before_after.append({
            "path": path,
            "before_git_blob_sha256": item.get("source_sha256"),
            "after_isolated_candidate_sha256": item.get("candidate_sha256"),
            "independent_static_recheck": result.get("gates", {}).get(
                "second_independent_ast_recheck", "NOT_RUN_OR_BLOCKED"),
            "negative_input_recheck": result.get("gates", {}).get(
                "third_negative_test_re_review", "NOT_RUN_OR_BLOCKED"),
            "actual_functional_regression": validation["docker"],
            "patch_applied_to_original": False,
            "meaning_and_security_review": "NOT_APPROVED",
        })
    if approval.get("status") != "NOT_APPROVED_HANDOFF_ONLY":
        raise AuditError("window_remediation_unexpected_approval_state")
    callback(f"V{start}~V{end}: 수정 전후 재검증 후 원본 Git 재확인")
    again, again_map, again_ev = _checked_window(repo, target, head=head,
                                                   latest=latest, start=start,
                                                   stop=stop_event)
    if (again != checkpoint or digest(again_map) != digest(source_map)
            or again_ev["receipt"] != evidence["receipt"]):
        raise AuditError("window_remediation_after_recheck_mismatch")
    no_leads = [slot["version"] for slot in checkpoint["slots"]
                if slot["status"] == "NO_EVIDENCE_LEAD_NOT_REVIEWED"]
    hints_only = [slot["version"] for slot in checkpoint["slots"]
                  if slot["status"] == "LEADS_ONLY_NOT_REVIEWED"]
    open_ids = [x["id"] for x in checkpoint["open_findings_carry_forward"]]
    gates = {
        "window_original_source_inventory": "PASS_HINT_INVENTORY_NOT_RELEASE_REVIEW",
        "independent_before_and_after_git_recheck": "PASS",
        "isolated_patch_ast_and_negative_checks": "STATIC_ONLY_NOT_FUNCTIONAL",
        "version_by_version_historical_originals": "NOT_VERIFIED",
        "missing_version_evidence_resolved": "NOT_VERIFIED",
        "open_p0_p1_p2_remediation_proven": "NOT_VERIFIED",
        "before_after_behavioral_equivalence": "NOT_VERIFIED",
        "full_regression_security_and_performance": "NOT_VERIFIED",
        "independent_human_rereview": "NOT_PERFORMED",
        "current_head_ci_and_protected_successor": "NOT_VERIFIED_BY_PC_TOOL",
    }
    result = {
        "schema": GATE_SCHEMA, "head_sha": head,
        "window": {"first": start, "last": end},
        "checkpoint_sha256": checkpoint["checkpoint_sha256"],
        "three_pass_audit_receipt_sha256": evidence["receipt"]["review_receipt_sha256"],
        "status": "HOLD_REMEDIATION_AND_HISTORICAL_EVIDENCE_UNVERIFIED",
        "next_window_allowed": False,
        "advance_blocked_until": "MISSING_SOURCE_REVIEW_FIX_BEFORE_AFTER_FUNCTIONAL_CROSSCHECK_REREVIEW",
        "missing_hint_slots_not_proven_absent_releases": no_leads,
        "hint_only_slots_not_verified_releases": hints_only,
        "open_findings_carry_forward": open_ids,
        "source_map_risks_not_version_specific": len(source_map.get("risk_hints", [])),
        "unparsed_files": len(source_map.get("syntax_or_encoding_issues", [])),
        "skipped_files": len(source_map.get("skipped", [])),
        "remediation": remediation,
        "before_after_candidates": before_after,
        "actual_functional_test_result": validation["docker"],
        "independent_recheck_gates": gates,
        "patch_approval": "NOT_APPROVED",
        "original_repository_modified": False,
        "next_window_checkpoint_may_be_created": False,
    }
    result["gate_sha256"] = digest(result)
    _write_or_check(window_dir / "window_gate.json", result)
    if (target / f"V{end+1:04d}_V{min(end+100, latest):04d}.json").exists():
        raise AuditError("later_window_exists_without_remediation_gate_pass")
    return result


def run_strict_cycle(repo: Path, output: Path, latest: int | None = None,
                     *, resume: bool = True, docker_tests: bool = False,
                     docker_image: str = "python:3.11-slim",
                     callback: Callable[[str], None] | None = None,
                     stop_event=None) -> dict:
    """User-facing strict workflow. No bypass to inventory-only progression."""
    callback = callback or (lambda _s: None)
    root, head, _shallow = validate_repo(repo)
    output = output.expanduser().resolve()
    if output == root or root in output.parents:
        raise AuditError("output_must_be_outside_git_checkout")
    paths = git_inventory(root)
    _f, _ledger, declared = load_findings(root, paths)
    if latest is None:
        if declared is None:
            raise AuditError("supply_latest_version")
        latest = declared
    if type(latest) is not int or not 1 <= latest <= 9999:
        raise AuditError("invalid_latest")
    target = output / f"HEAD_{head[:12]}_V1-V{latest}"
    if target.is_symlink():
        raise AuditError("unsafe_strict_report_symlink")
    end = min(100, latest)
    if not (target / f"V0001_V{end:04d}.json").exists():
        # Collector runs ONE new window only. Audit receipt PASS does NOT mean
        # remediation or per-version source review is complete.
        run_audit(root, output, latest=latest, resume=True, stop_after=1,
                  auto_review=False, callback=callback, stop_event=stop_event)
    if not (target / f"V0001_V{end:04d}.json").is_file():
        raise AuditError("strict_first_window_not_completed")
    if any(target.glob("V????_V????.json")) and any(
            p.name != f"V0001_V{end:04d}.json"
            for p in target.glob("V????_V????.json")):
        raise AuditError("legacy_multiwindow_inventory_not_remediation_certified_use_new_output")
    result = _one_window(root, target, head=head, latest=latest,
                         docker_tests=docker_tests, docker_image=docker_image,
                         callback=callback, stop_event=stop_event)
    summary_path = target / "strict_window_status.json"
    summary = {
        "schema": "tcg-pc-strict-window-status/v5",
        "head_sha": head, "latest": latest, "window": result["window"],
        "window_gate_sha256": result["gate_sha256"],
        "status": result["status"], "next_window_allowed": False,
        "completed_remediated_windows": 0,
        "investigated_windows": 1,
        "total_windows": (latest+99)//100,
        "original_repository_modified": False,
        "actual_device_verified": False,
        "unresolved_number_slots": len(result["missing_hint_slots_not_proven_absent_releases"]) + len(result["hint_only_slots_not_verified_releases"]),
        "unresolved_findings": len(result["open_findings_carry_forward"]),
    }
    _write_or_check(summary_path, summary)
    hold_text = "\n".join([
        "# TCG V1~V현재: 100개 구간별 보완·재검증 상태", "",
        f"- HEAD: `{head}`", f"- 현재 조사 구간: V1~V{end}",
        f"- 목표 구간: V1~V{latest} / {(latest+99)//100}개 단위",
        "- 다음 구간 이동: **HOLD (금지)**",
        f"- 버전 번호의 원본 근거 부족: {len(result['missing_hint_slots_not_proven_absent_releases'])}개",
        f"- 파일명·커밋 힌트만 존재: {len(result['hint_only_slots_not_verified_releases'])}개 (릴리스 증명 아님)",
        f"- 미해결 이전 결함: {len(result['open_findings_carry_forward'])}개",
        f"- 격리 수정 후보: {len(result['before_after_candidates'])}개",
        f"- 실제 기능·보안·회귀 재검사: {result['actual_functional_test_result']}",
        "- 보호된 코드 수정/현재 HEAD CI/사람 재검토: 미승인", "",
        "## 다음 단계로 넘어가기 전 필요한 검증", "",
        "1. 실제 과거 버전 원본과 누락 항목을 확인하고 출처·버전·영향 기능별로 연결", 
        "2. 누락·오류의 실제 재현 테스트와 예상 동작을 먼저 확정", 
        "3. 격리된 후보를 전후 비교하고 기능/통합/회귀/보안/성능 테스트로 검증", 
        "4. 독립 교차확인 및 검토자 재검토 후 보호된 successor와 현 HEAD CI 확인", 
        "5. 단 하나라도 증거 불충분하면 보류, 임의로 100개 버전 통과나 릴리스 인증하지 않음", "",
        f"상세: `window_remediation_V0001_V{end:04d}/window_gate.json`,",
        "`implementation_backlog.json`, `candidate_validation.json`, `approval_packet.json`", "",
        "**이 시험판은 자동으로 증거를 만들어 결함을 해결할 수 없습니다. "
        "명시된 필수 증거가 부족하면 같은 구간을 재검사하며 다음 구간을 생성하지 않습니다.**", "",
    ])
    readable = target / "현재구간_보완검증_상태.md"
    if readable.exists() or readable.is_symlink():
        if (readable.is_symlink() or not readable.is_file()
                or readable.read_text(encoding="utf-8") != hold_text):
            raise AuditError("window_hold_report_tampered_or_mismatched")
    else:
        atomic_text(readable, hold_text)
    callback(f"V1~V{end}: HOLD — 누락증거·보완 전후 기능검증/재검토 미충족; 다음 100개 차단")
    return summary
