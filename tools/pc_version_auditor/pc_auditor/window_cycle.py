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
from p0_learning_preflight import inspect_git as inspect_p0_learning_git
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
    return stored, map_data, {"findings": findings, "receipt": receipt,
                              "ledger_present": _ledger is not None}


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
    p0_learning = inspect_p0_learning_git(repo, head=head, tracked_paths=paths)
    _write_or_check(window_dir / "p0_learning_preflight.json", p0_learning)
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
    # Korean human-review plan: a numbered historical gap is NOT a missing release.
    backlog = read_checkpoint(window_dir / "implementation_backlog.json", max_bytes=12_000_000)
    if (backlog.get("head_sha") != head or
            backlog.get("status") != "OPEN_TASKS_NOT_AUTOMATICALLY_IMPLEMENTED"
            or not isinstance(backlog.get("items"), list)):
        raise AuditError("korean_design_invalid_backlog")
    labels = {
        "TRUTHY_VERIFICATION_FLAG_REVIEW": "인증 플래그의 문자열 true/false 오판 위험",
        "LEARNING_STORE_PRESERVATION_REVIEW": "confirmed_samples 등 저장 증거 유실 위험",
        "CARRIED_OPEN_FINDING": "과거 결함을 원본과 교차대조하고 재현 테스트 설계",
        "SYNTAX_OR_ENCODING": "문법·인코딩 오류를 원본으로 재현",
        "SKIPPED_SOURCE": "검사에서 제외된 파일을 별도 조사",
        "PLACEHOLDER_FUNCTION_REVIEW": "pass/생략형 함수의 의도 확인 후 동작 테스트와 구현 설계",
        "UNIMPLEMENTED_RAISE_REVIEW": "NotImplementedError가 의도된 추상 계약인지 확인하고 필요한 구현 보완",
    }
    tasks = []
    for index, item in enumerate(backlog["items"]):
        if not isinstance(item, dict) or item.get("item_index") != index:
            raise AuditError("korean_design_invalid_backlog_item")
        kind = item.get("kind")
        summary = labels.get(kind, "원본 재확인과 기능·보안·성능 영향 설계")
        fid = item.get("finding_id")
        if kind == "CARRIED_OPEN_FINDING" and fid == "W001-F014":
            summary = "학습자료 confirmed_samples 저장 전후 보존·회귀검사·V426 후속 보호계약"
        elif kind == "CARRIED_OPEN_FINDING" and fid == "W001-F015":
            summary = "verified 값이 문자열 false/true·숫자 1이면 학습 차단하는 회귀검사"
        tasks.append({"priority": item.get("priority"), "kind": kind,
                      "path": item.get("path"), "finding_id": fid,
                      "design_ko": summary, "state": "HOLD_REPRO_AND_TESTS_REQUIRED",
                      "implementation_verified": False})
    slot_states = []
    for i, slot in enumerate(checkpoint["slots"], start=start):
        if (slot.get("version") != i or slot.get("source_review") != "NOT_PERFORMED"
                or slot.get("quality_score") is not None):
            raise AuditError("korean_design_false_version_verification")
        slot_states.append({"version": i, "evidence_state": slot["status"],
                            "original_source_verified": False,
                            "missing_release_confirmed": False})
    design = {"schema": "tcg-pc-korean-review-plan/v1", "head_sha": head,
              "window": {"first": start, "last": end},
              "checkpoint_sha256": checkpoint["checkpoint_sha256"],
              "status": "HOLD_UNIMPLEMENTED_AND_HISTORICAL_EVIDENCE_UNVERIFIED",
              "next_window_allowed": False, "quality_score": None,
              "slots": slot_states, "tasks": tasks}
    design["design_sha256"] = digest(design)
    _write_or_check(window_dir / "구간별_한글_기획설계.json", design)
    lines = ["# TCG PC V1~V100: 한글 누락 조사·기획·설계", "",
             "상태: HOLD (실제 원본/기능/회귀/보안/사람 재검토 미완료)",
             "단서가 없다는 사실은 버전이나 기능이 없다는 증거가 아닙니다.",
             "품질 채점: 미채점. Git main·Lenovo 변경: 없음.", "",
             "## 버전별 증거 상태"]
    lines += ["V%d: %s (원본 미검증)" % (x["version"],
                 "번호 단서 없음" if x["evidence_state"] == "NO_EVIDENCE_LEAD_NOT_REVIEWED"
                 else "파일명/커밋 단서만 있음") for x in slot_states]
    lines += ["", "## 개선 기획·설계 및 필수 교차검증"]
    for task in tasks:
        source = task["finding_id"] or task["path"] or "원본 대조 필요"
        source = " ".join(str(source).split())[:150]
        lines.append("- %s %s: %s. 필수: 재현→설계→격리 패치→기능/보안/성능/회귀→재검토" % (
            task["priority"], source, task["design_ko"]))
    lines += ["", "다음 100개 조사: 필수 검증 증거가 부족하므로 HOLD", ""]
    markdown = "\n".join(lines)
    report_path = window_dir / "구간별_한글_기획설계.md"
    if report_path.exists() or report_path.is_symlink():
        if (report_path.is_symlink() or not report_path.is_file()
                or report_path.read_text("utf-8") != markdown):
            raise AuditError("korean_design_report_tampered")
    else:
        atomic_text(report_path, markdown)
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
    after_p0 = inspect_p0_learning_git(repo, head=head, tracked_paths=git_inventory(repo))
    if (again != checkpoint or digest(again_map) != digest(source_map)
            or again_ev["receipt"] != evidence["receipt"]
            or after_p0 != p0_learning):
        raise AuditError("window_remediation_after_recheck_mismatch")
    no_leads = [slot["version"] for slot in checkpoint["slots"]
                if slot["status"] == "NO_EVIDENCE_LEAD_NOT_REVIEWED"]
    hints_only = [slot["version"] for slot in checkpoint["slots"]
                  if slot["status"] == "LEADS_ONLY_NOT_REVIEWED"]
    open_ids = [x["id"] for x in checkpoint["open_findings_carry_forward"]]
    gates = {
        "window_original_source_inventory": "PASS_HINT_INVENTORY_NOT_RELEASE_REVIEW",
        "historical_findings_ledger": ("PRESENT_UNVERIFIED_RECORDS" if evidence["ledger_present"]
                                       else "MISSING_HOLD_UNRESOLVED_UNKNOWN"),
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
        "findings_ledger_present": evidence["ledger_present"],
        "source_map_risks_not_version_specific": len(source_map.get("risk_hints", [])),
        "unparsed_files": len(source_map.get("syntax_or_encoding_issues", [])),
        "skipped_files": len(source_map.get("skipped", [])),
        "remediation": remediation,
        "p0_learning_preflight_sha256": digest(p0_learning),
        "p0_learning_status": p0_learning["status"],
        "korean_design_sha256": design["design_sha256"],
        "korean_design_tasks": len(tasks),
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
        "unresolved_findings": (len(result["open_findings_carry_forward"])
                                if result["findings_ledger_present"] else None),
        "findings_ledger_present": result["findings_ledger_present"],
    }
    _write_or_check(summary_path, summary)
    hold_text = "\n".join([
        "# TCG V1~V현재: 100개 구간별 보완·재검증 상태", "",
        f"- HEAD: `{head}`", f"- 현재 조사 구간: V1~V{end}",
        f"- 목표 구간: V1~V{latest} / {(latest+99)//100}개 단위",
        "- 다음 구간 이동: **HOLD (금지)**",
        f"- 버전 번호의 원본 근거 부족: {len(result['missing_hint_slots_not_proven_absent_releases'])}개",
        f"- 파일명·커밋 힌트만 존재: {len(result['hint_only_slots_not_verified_releases'])}개 (릴리스 증명 아님)",
        (f"- 미해결 이전 결함: {len(result['open_findings_carry_forward'])}개 (장부가 확인된 경우만)"
         if result["findings_ledger_present"] else
         "- 이전 결함 장부: 없음 · 결함 개수 미확정 · 별도 소스 확보 후 재검토 필수"),
        f"- 격리 수정 후보: {len(result['before_after_candidates'])}개",
        f"- P0 학습 증거/인증 검증: {result['p0_learning_status']} (상세: p0_learning_preflight.json)",
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
