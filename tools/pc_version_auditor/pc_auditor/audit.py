"""TCG PC history auditor: offline, read-only, evidence-led, no release certification.

Python 3.10+ and locally installed Git. Does not import project source, execute
project tests, modify Git, contact remote services, or touch the Lenovo device.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

SCHEMA = "tcg-pc-historical-audit/v1"
VERSION_HINT = re.compile(r"(?<![A-Za-z0-9])V0*(\d{1,4})(?![A-Za-z0-9])", re.IGNORECASE)
LEDGER_NAME = re.compile(r"version_review_findings_v001_v(\d{3,4})\.json$")
MAX_SOURCE_BYTES = 1_000_000
MAX_GIT_PATHS = 30000
MAX_COMMITS = 15000
MAX_CODEMAP_FILES = 2500
MAX_FINDINGS_BYTES = 1_000_000


class AuditError(Exception):
    """Fail-closed, recoverable PC-audit problem."""


def git(repo: Path, *args: str, limit: int = 40_000_000) -> bytes:
    try:
        done = subprocess.run(["git", *args], cwd=repo, capture_output=True,
                              timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AuditError("git_unavailable_or_timeout: " + str(exc)) from exc
    if done.returncode:
        raise AuditError("git_failed: " + " ".join(args[:2]) + " " +
                         done.stderr[:300].decode("utf-8", "replace"))
    if len(done.stdout) > limit:
        raise AuditError("git_response_exceeds_limit")
    return done.stdout


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tcg-audit-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(canonical(value))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def atomic_text(path: Path, content: str) -> None:
    """Avoid following a malicious pre-existing report symlink."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".tcg-report-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def read_checkpoint(path: Path, max_bytes: int = 2_000_000) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > max_bytes:
        raise AuditError("unsafe_checkpoint: " + path.name)
    def unique(pairs):
        d = {}
        for k, v in pairs:
            if k in d:
                raise AuditError("duplicate_checkpoint_key")
            d[k] = v
        return d
    try:
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(AuditError("nonfinite_json")))
    except (OSError, ValueError) as exc:
        raise AuditError("invalid_checkpoint: " + str(exc)) from exc
    if not isinstance(data, dict):
        raise AuditError("invalid_checkpoint_object")
    return data


def version_tokens(text: str, ceiling: int) -> list[int]:
    return sorted({int(x) for x in VERSION_HINT.findall(text)
                   if 1 <= int(x) <= ceiling})


def validate_repo(path: Path) -> tuple[Path, str, bool]:
    path = path.resolve(strict=True)
    root = Path(git(path, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    if root != path:
        raise AuditError("choose_git_checkout_root_not_subfolder")
    sha = git(path, "rev-parse", "--verify", "HEAD^{commit}").decode().strip()
    if re.fullmatch(r"[a-f0-9]{40}", sha) is None:
        raise AuditError("invalid_git_head")
    shallow = git(path, "rev-parse", "--is-shallow-repository").strip() == b"true"
    return root, sha, shallow


def git_inventory(root: Path) -> list[str]:
    paths = git(root, "ls-tree", "-r", "--name-only", "-z", "HEAD").split(b"\0")
    paths = [p.decode("utf-8", "strict") for p in paths if p]
    if len(paths) > MAX_GIT_PATHS:
        raise AuditError("too_many_tracked_paths")
    # Reject malformed Git path inventory; no worktree access or symlink follow.
    if any(p.startswith("/") or ".." in p.split("/") or "\\" in p or "\x00" in p
           for p in paths):
        raise AuditError("unsafe_git_path")
    return paths


def git_history(root: Path, ceiling: int) -> tuple[dict[int, list[dict]], bool, int]:
    raw = git(root, "log", "--format=%H%x09%s", "--no-show-signature",
              "-n", str(MAX_COMMITS + 1), limit=15_000_000)
    lines = raw.decode("utf-8", "replace").splitlines()
    limited = len(lines) > MAX_COMMITS
    found: dict[int, list[dict]] = {}
    for line in lines[:MAX_COMMITS]:
        sha, sep, subject = line.partition("\t")
        if not sep or not re.fullmatch(r"[a-f0-9]{40}", sha):
            raise AuditError("invalid_git_history")
        for n in version_tokens(subject, ceiling):
            found.setdefault(n, []).append({"commit": sha, "subject_hint": subject[:180]})
    return found, limited, min(len(lines), MAX_COMMITS)


def code_map(root: Path, paths: list[str], stop=None) -> dict:
    files = []
    risk_hints = []
    parse_issues = []
    scanned = 0
    skipped = []
    for path in paths:
        if stop is not None and stop.is_set():
            raise AuditError("stopped_before_code_map_completed")
        if not path.endswith(".py"):
            continue
        if scanned >= MAX_CODEMAP_FILES:
            skipped.append({"path": path, "reason": "file_count_limit"})
            continue
        blob = git(root, "cat-file", "blob", f"HEAD:{path}", limit=MAX_SOURCE_BYTES+100)
        if len(blob) > MAX_SOURCE_BYTES:
            skipped.append({"path": path, "reason": "file_size_limit"})
            continue
        scanned += 1
        try:
            code = blob.decode("utf-8")
            tree = ast.parse(code, filename=path)
        except (UnicodeDecodeError, SyntaxError, ValueError) as exc:
            parse_issues.append({"path": path, "problem": type(exc).__name__,
                                 "line": getattr(exc, "lineno", None)})
            continue
        functions, imports, calls = [], set(), set()
        # Specific source-only review hint: the old learning-store POST may
        # rebuild a fresh dictionary without historical V40 evidence.
        # Do NOT generate a blind patch for this protected endpoint.
        if path.rsplit("/", 1)[-1] == "tcg_updater.py":
            has_learning_sink = any(
                isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "save_json_atomic" and len(n.args) >= 2
                and isinstance(n.args[0], ast.Name) and n.args[0].id == "LEARNING_STORE"
                and isinstance(n.args[1], ast.Name) and n.args[1].id == "data"
                for n in ast.walk(tree))
            if has_learning_sink:
                for n in ast.walk(tree):
                    if not isinstance(n, ast.Assign) or not isinstance(n.value, ast.Dict):
                        continue
                    if not any(isinstance(t, ast.Name) and t.id == "data"
                               for t in n.targets):
                        continue
                    keys = {v.value for v in n.value.keys if isinstance(v, ast.Constant)
                            and isinstance(v.value, str)}
                    if {"v99_validation", "v30_validation", "v11_validation"} <= keys and "confirmed_samples" not in keys:
                        risk_hints.append({"path": path, "line": n.lineno,
                            "rule": "LEARNING_STORE_PRESERVATION_REVIEW",
                            "status": "REVIEW_REQUIRED"})
        # Static-only WARNING hints. Never assert confirmed bugs from these.
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
                risk_hints.append({"path": path, "line": node.lineno,
                                   "rule": "DYNAMIC_CODE_EXECUTION_REVIEW", "status": "REVIEW_REQUIRED"})
            if (isinstance(node.func, ast.Name) and node.func.id == "bool"
                    and len(node.args) == 1 and isinstance(node.args[0], ast.Call)):
                call = node.args[0]
                if (isinstance(call.func, ast.Attribute) and call.func.attr == "get"
                        and call.args and isinstance(call.args[0], ast.Constant)
                        and call.args[0].value in {"verified", "resolution_confirmed"}):
                    risk_hints.append({"path": path, "line": node.lineno,
                                       "rule": "TRUTHY_VERIFICATION_FLAG_REVIEW", "status": "REVIEW_REQUIRED"})
            if (isinstance(node.func, ast.Attribute) and node.func.attr in {"run", "Popen", "call"}
                    and any(k.arg == "shell" and isinstance(k.value, ast.Constant)
                            and k.value.value is True for k in node.keywords)):
                risk_hints.append({"path": path, "line": node.lineno,
                                   "rule": "SHELL_EXECUTION_REVIEW", "status": "REVIEW_REQUIRED"})
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append({"name": node.name, "line": node.lineno,
                                  "async": isinstance(node, ast.AsyncFunctionDef)})
            elif isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module)
            elif isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Name):
                    calls.add(fn.id)
                elif isinstance(fn, ast.Attribute):
                    calls.add(fn.attr)
        files.append({"path": path, "sha256": hashlib.sha256(blob).hexdigest(),
                      "functions": sorted(functions, key=lambda v: (v["line"], v["name"])),
                      "imports": sorted(imports), "called_names": sorted(calls)[:300]})
    return {"schema": SCHEMA, "scope": "CURRENT_HEAD_STATIC_SOURCE_ONLY",
            "files": files, "python_files_parsed": len(files),
            "syntax_or_encoding_issues": parse_issues,
            "risk_hints": risk_hints, "skipped": skipped}


def load_findings(root: Path, paths: list[str]) -> tuple[list[dict], str | None, int | None]:
    choices = []
    for path in paths:
        if path.startswith("execution/evidence/"):
            match = LEDGER_NAME.fullmatch(path.rsplit("/", 1)[-1])
            if match:
                choices.append((int(match.group(1)), path))
    if not choices:
        return [], None, None
    declared_max, name = max(choices)
    raw = git(root, "cat-file", "blob", "HEAD:"+name, limit=MAX_FINDINGS_BYTES+1)
    if len(raw) > MAX_FINDINGS_BYTES:
        raise AuditError("findings_ledger_too_large")
    try:
        ledger = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        raise AuditError("invalid_findings_ledger") from exc
    if not isinstance(ledger, dict) or not isinstance(ledger.get("findings"), list):
        raise AuditError("wrong_findings_ledger_schema")
    records = []
    seen = set()
    for row in ledger["findings"]:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or row["id"] in seen:
            raise AuditError("bad_findings_entries")
        seen.add(row["id"])
        if type(row.get("first_observed_version")) is not int:
            raise AuditError("bad_findings_version")
        records.append({"id": row["id"], "start": row["first_observed_version"],
                        "state": row.get("state"), "severity": row.get("severity"),
                        "summary": row.get("summary")})
    return sorted(records, key=lambda x: (x["start"], x["id"])), name, declared_max


def determine_latest(root: Path, paths: list[str]) -> int:
    # This is only the highest documented evidence-matrix range, not proof of
    # the latest released software version. The GUI must label it as such.
    _, _, number = load_findings(root, paths)
    if number is None:
        raise AuditError("no_documented_max_version; supply --latest")
    return number


def group_window(start: int, latest: int, paths: list[str], history: dict,
                 findings: list[dict], head: str, prior: str | None,
                 history_complete: bool, code_map_sha: str) -> dict:
    end = min(start + 99, latest)
    path_hints = {}
    for path in paths:
        for n in version_tokens(path, latest):
            if start <= n <= end:
                path_hints.setdefault(n, []).append(path)
    slots = []
    for n in range(start, end+1):
        hint = path_hints.get(n, [])
        history_hint = history.get(n, [])
        slots.append({"version": n,
                      "path_hints": sorted(set(hint))[:120],
                      "commit_subject_hints": history_hint[:50],
                      "status": "LEADS_ONLY_NOT_REVIEWED" if hint or history_hint
                                else "NO_EVIDENCE_LEAD_NOT_REVIEWED",
                      "source_review": "NOT_PERFORMED", "tests": "NOT_RUN",
                      "device": "UNVERIFIED", "quality_score": None})
    out = {"schema": SCHEMA, "head_sha": head, "first": start, "last": end,
           "checkpoint_parent_sha256": prior, "code_map_sha256": code_map_sha,
           "history_complete": history_complete, "source": "LOCAL_GIT_READ_ONLY",
           "quality_score": None, "device_verified": False,
           "open_findings_carry_forward": [f for f in findings if f["start"] <= end
                                            and f["state"] != "HISTORICAL_REPAIR_EVIDENCED"],
           "slots": slots}
    out["checkpoint_sha256"] = digest(out)
    return out


def markdown_report(summary: dict) -> str:
    lines = ["# TCG PC V1~V현재 구간별 점검 결과", "",
             "**읽기 전용 Git 증거·정적 코드 검사. 릴리스 전수검사 또는 실기기 인증이 아닙니다.**", "",
             f"- Git HEAD: `{summary['head_sha']}`",
             f"- 요청 숫자 범위: V1~V{summary['latest']} (증빙 없는 번호도 포함)",
             f"- 점검 구간: {summary['completed_windows']} / {summary['total_windows']}",
             f"- Git 이력: {'부분/불완전' if not summary['git_history_complete'] else '로컬 이력 조회 완료'}",
             f"- Python AST 구문·인코딩 문제: {summary['syntax_issue_count']}",
             f"- 정적 보안·검증 위험 힌트(미확정): {summary['risk_hint_count']}",
             f"- 기존 결함 장부 항목: {summary['ledger_finding_count']}",
             f"- 매 구간 1차 재구성/2차 Git 독립검증/3차 의심 재검토: {'PASS' if summary['all_completed_windows_rereviewed'] else 'HOLD'}",
             "- 다음 100개 구간은 위 3가지 검증을 모두 통과한 경우에만 조사합니다.",
             "- 소스 전체 승인/실제 성능/디바이스 인증: 별도 검증 필요 (자동 승인 안 함)",
             f"- 배포/태블릿: HOLD, 물리 검증 없음", "",
             "| 번호 범위 | 힌트 존재 | 증거 부족 | 승계 결함 | 판정 |", "|---|---:|---:|---:|---|"]
    for w in summary["windows"]:
        lines.append(f"| V{w['first']}~V{w['last']} | {w['hint_slots']} | "
                     f"{w['no_hint_slots']} | {w['open_findings']} | NOT_REVIEWED |")
    if summary.get("candidate_validation"):
        gate = summary["candidate_validation"]
        lines += ["", "## 격리된 수정 후보 검증 / 이중 교차확인 (v0.4)", "",
                  f"- 정적 검증 통과 후보: {gate['validated_static_candidates']}",
                  f"- 보류된 후보: {gate['held_candidates']}",
                  f"- Docker 격리 회귀검사: {gate['docker']}",
                  f"- 검토 준비도(코드 품질점수 아님): {gate['readiness_score_not_quality']}/100",
                  "- 보고서: candidate_validation.json, independent_patch_review.json, approval_packet.json",
                  "- 사용자 검토와 V426 successor/CI 승인 전에는 절대 적용·병합하지 않습니다."]
    if summary.get("automatic_review"):
        v = summary["automatic_review"]
        lines += ["", "## 자동 보완 후보 (원본 미수정)", "",
                  f"- 자동 분류한 검토 항목: {v['priority_items']}",
                  f"- 격리된 수정 검토 후보: {v['ast_pass_proposals']}",
                  "- 상세: remediation_plan.json / repair_candidates/",
                  f"- 적용된 저장소 등록 스킬 라우팅(읽기 전용): {summary['registered_skills_read_only']}",
                  "- 수정 후보는 AST 통과만 확인. 실제 프로젝트 실행/회귀/승인 아님."]
    lines += ["", "## 의미와 다음 조치", "",
              "힌트는 파일명·커밋 제목에서 발견한 숫자일 뿐, 실제 V버전 스냅샷이 아닙니다.",
              "모든 구간은 차례대로 저장하며 미해결 결함을 다음 구간으로 승계합니다.",
              "코드 지도는 선택된 HEAD의 정적 AST이며, 해당 V번호의 개별 소스 검수나 테스트가 아닙니다.",
              "사람이 소스와 부정 테스트를 재검토하고 정식 successor/CI를 통과하기 전에는 병합하지 마세요.",
              "PC 프로그램은 GitHub 업로드, AI 자동수정, 태블릿 설치·학습을 수행하지 않습니다.", ""]
    return "\n".join(lines)


def run_audit(repo: Path, output: Path, latest: int | None = None,
              resume: bool = False, stop_after: int | None = None,
              callback: Callable[[str], None] | None = None,
              stop_event=None, auto_review: bool = False,
              validate_candidates: bool = True, docker_tests: bool = False,
              docker_image: str = 'python:3.11-slim') -> dict:
    callback = callback or (lambda _: None)
    root, head, shallow = validate_repo(repo)
    output = output.expanduser().resolve()
    if output == root or root in output.parents:
        raise AuditError("output_must_be_outside_git_checkout")
    paths = git_inventory(root)
    findings, ledger_path, documented_max = load_findings(root, paths)
    if latest is None:
        if documented_max is None:
            raise AuditError("supply_latest_version")
        latest = documented_max
    if type(latest) is not int or not 1 <= latest <= 9999:
        raise AuditError("invalid_latest_version")
    if stop_after is not None and (type(stop_after) is not int or stop_after < 1):
        raise AuditError("invalid_stop_after")
    target = output / (f"HEAD_{head[:12]}_V1-V{latest}")
    if target.exists() and not resume:
        raise AuditError("report_folder_exists_use_resume_or_other_output")
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise AuditError("unsafe_report_folder")
    if not target.exists():
        target.mkdir(parents=True)
    callback("Git 커밋·파일 증거 읽기")
    history, history_limited, commits_read = git_history(root, latest)
    complete = not (shallow or history_limited)
    code_path = target / "code_map.json"
    if not code_path.exists():
        callback("정적 코드 지도 분석 (실행하지 않음)")
        map_data = code_map(root, paths, stop_event)
        map_data.update({"head_sha": head, "history_complete": complete})
        atomic_json(code_path, map_data)
        atomic_json(target / "code_map_hash.json", {
            "head_sha": head, "sha256": digest(map_data),
            "scope": "STATIC_CURRENT_HEAD_ONLY"})
    map_data = read_checkpoint(code_path, max_bytes=40_000_000)
    if map_data.get("head_sha") != head:
        raise AuditError("code_map_head_conflict")
    map_hash = digest(map_data)
    seal_path = target / "code_map_hash.json"
    if not seal_path.is_file():
        raise AuditError("unsealed_old_code_map; use_new_report_output_folder")
    seal = read_checkpoint(seal_path)
    if seal.get("head_sha") != head or seal.get("sha256") != map_hash:
        raise AuditError("code_map_tampered_or_wrong_head")
    # Always re-read immutable HEAD evidence and source map independently.
    # A refreshed JSON checksum alone is not independent verification.
    from crosscheck import independent_sources, verify_window
    callback("의심 우선: 별도 Git 증거/정적 코드지도 독립 재검사")
    separate = independent_sources(root, head, latest, paths, history, findings,
                                   map_data, stop_event)
    windows = []
    prior = None
    performed = 0
    for first in range(1, latest + 1, 100):
        if stop_event is not None and stop_event.is_set():
            callback("중단 요청: 마지막 완료 구간까지 보존")
            break
        end = min(first+99, latest)
        filename = target / f"V{first:04d}_V{end:04d}.json"
        if filename.exists():
            if not resume:
                raise AuditError("existing_checkpoint_without_resume")
            checkpoint = read_checkpoint(filename)
            copy = dict(checkpoint)
            recorded = copy.pop("checkpoint_sha256", None)
            if (recorded != digest(copy) or checkpoint.get("head_sha") != head
                    or checkpoint.get("first") != first or checkpoint.get("last") != end
                    or checkpoint.get("checkpoint_parent_sha256") != prior
                    or checkpoint.get("code_map_sha256") != map_hash):
                raise AuditError("checkpoint_chain_or_digest_mismatch")
        else:
            checkpoint = group_window(first, latest, paths, history, findings, head,
                                      prior, complete, map_hash)
            atomic_json(filename, checkpoint)
            performed += 1
        # Mandatory first-pass rebuild, independent second evidence pass and
        # negative/adversarial re-review *before* proceeding to next 100 slots.
        expected = group_window(first, latest, paths, history, findings, head,
                                prior, complete, map_hash)
        callback(f"V{first}~V{end}: 1차 재구성→2차 독립 교차검증→3차 의심 재검토")
        verified = verify_window(root, target, checkpoint, expected, separate,
                                 latest=latest, previous=prior)
        if not verified["next_window_audit_allowed"]:
            raise AuditError("window_3_pass_review_not_approved_to_continue")
        prior = checkpoint["checkpoint_sha256"]
        slots = checkpoint["slots"]
        windows.append({"first": first, "last": end,
                        "hint_slots": sum(v["status"] == "LEADS_ONLY_NOT_REVIEWED" for v in slots),
                        "no_hint_slots": sum(v["status"] == "NO_EVIDENCE_LEAD_NOT_REVIEWED"
                                             for v in slots),
                        "open_findings": len(checkpoint["open_findings_carry_forward"]),
                        "checkpoint_sha256": prior,
                        "three_pass_audit_gate": "PASS",
                        "release_approved": False,
                        "crosscheck_receipt_sha256": verified["review_receipt_sha256"]})
        callback(f"V{first}~V{end} 기록/3단계 교차검증 완료 ({len(windows)}/{(latest+99)//100})")
        if stop_after is not None and performed >= stop_after:
            callback("설정된 구간 수만 처리하고 안전하게 멈춤")
            break
    automated = None
    skill_routes = None
    validation = None
    if docker_tests and not auto_review:
        raise AuditError('docker_tests_require_auto_review')
    if auto_review and (stop_event is None or not stop_event.is_set()) and len(windows) == (latest+99)//100:
        from skills_registry import registered_skills
        from repair import stage_repair_candidates
        callback("저장소에 등록된 관련 스킬 확인(지침 읽기만)")
        skill_routes = registered_skills(root, paths, git, map_data.get("risk_hints"))
        selected_skills = {
            "head_sha": head, "scope": "REGISTERED_REPO_SKILLS_READ_ONLY_NO_EXECUTION",
            "skills": skill_routes,
            "external_skill_installation": False,
            "skill_instructions_execute_as_code": False,
        }
        skill_record = target / "skills_applied.json"
        if skill_record.exists() or skill_record.is_symlink():
            if read_checkpoint(skill_record, max_bytes=10_000_000) != selected_skills:
                raise AuditError("registered_skills_report_disagrees_with_git")
        else:
            atomic_json(skill_record, selected_skills)
        callback("부족한 부분 분류 및 격리된 안전 수정 후보 만들기")
        automated = stage_repair_candidates(root, target, map_data, findings)
        if validate_candidates:
            from validation import validate_and_handoff
            callback('격리 후보 검증: 패치/원본 해시, Python 컴파일, 승인용 보고서')
            validation = validate_and_handoff(root, target, head=head,
                docker_tests=docker_tests, docker_image=docker_image)
    if auto_review and len(windows) < (latest+99)//100:
        callback("HOLD: 모든 번호구간 3단계 재검토 전에는 패치 승인용 단계로 진행하지 않음")
    summary = {"schema": SCHEMA, "head_sha": head, "latest": latest,
               "documented_evidence_max": documented_max, "ledger_source": ledger_path,
               "git_history_complete": complete, "commits_read": commits_read,
               "total_windows": (latest+99)//100, "completed_windows": len(windows),
               "complete": len(windows) == (latest+99)//100,
               "quality_score": None, "physical_tablet_verified": False,
               "source_review_complete": False, "CI": "NOT_RUN_BY_PC_TOOL",
               "mandatory_crosscheck_policy": "THREE_PASS_FAIL_CLOSED_V4",
               "all_completed_windows_rereviewed": all(
                   w["three_pass_audit_gate"] == "PASS" for w in windows),
               "next_stage_gate": "HOLD_MANUAL_SEMANTIC_REVIEW_AND_CURRENT_HEAD_CI",
               "auto_release_or_merge_allowed": False,
               "candidate_stage_deferred_until_all_windows_pass": (
                   auto_review and len(windows) < (latest+99)//100),
               "syntax_issue_count": len(map_data.get("syntax_or_encoding_issues", [])),
               "risk_hint_count": len(map_data.get("risk_hints", [])),
               "ledger_finding_count": len(findings), "windows": windows,
               "automatic_review": automated,
               "candidate_validation": validation,
               "registered_skills_read_only": len([x for x in skill_routes or []
                     if x["state"] == "ROUTED_READ_ONLY"]),
               "auto_fixed_original_files": 0,
               "original_repository_modified": False}
    atomic_json(target / "summary.json", summary)
    atomic_text(target / "summary.md", markdown_report(summary))
    callback("보고서: " + str(target / "summary.md"))
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Offline TCG mandatory twice-run review (read-only)")
    parser.add_argument("--repo", type=Path, required=True, help="Local git checkout root")
    parser.add_argument("--output", type=Path, default=Path.home()/"Documents"/"TCG_PC_AUDIT")
    parser.add_argument("--latest", type=int, help="Last V number; default: highest local ledger label")
    parser.add_argument("--resume", action="store_true", help="Resume verified checkpoints")
    parser.add_argument("--stop-after", type=int, help="Deprecated: strict mode never advances until current window is fully resolved")
    parser.add_argument("--auto", action="store_true", help="Mandatory strict per-window auto remediation gate (default)")
    parser.add_argument("--docker-tests", action="store_true", help="Explicitly opt in to offline Docker-isolated repository tests; never native host execution")
    parser.add_argument("--docker-image", default="python:3.11-slim", help="An already locally present Docker image; no pulling")
    ns = parser.parse_args(argv)
    try:
        from double_review import run_double_review
        result = run_double_review(ns.repo, ns.output, ns.latest,
                                  callback=lambda x: print(x, flush=True),
                                  docker_tests=ns.docker_tests,
                                  docker_image=ns.docker_image)
    except (AuditError, OSError, UnicodeError) as exc:
        print("[HOLD] " + str(exc), file=sys.stderr)
        return 2
    print("[HOLD] " + result["status"] + "; both full audit passes matched, next 100 blocked")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
