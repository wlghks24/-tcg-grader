#!/usr/bin/env python3
"""승인형 AI 코드개선 후보 생성·격리검증 파이프라인.

생성 코드는 운영 파일에 자동 적용하지 않는다. 정적검사와 사용자가 작성한
고정 회귀검사를 모두 통과한 후보만 별도 검토 폴더에 저장한다.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from safe_runtime import (
    atomic_write_json,
    atomic_write_text,
    reject_nonstandard_json,
    safe_read_text,
    unique_json_object,
)


ROOT = Path(__file__).resolve().parent
LEARNING_PATH = ROOT / "ai_code_learning.json"
LEARNING_BACKUP = ROOT / "ai_code_learning.json.bak"
TRUSTED_TEST_ROOT = ROOT / "trusted_ai_tests"
PROPOSAL_ROOT = ROOT / ".tcg_ai_proposals"
ENGINE_VERSION = "v98-camera-resilience-full-runtime"
DEFAULT_MODEL = "gpt-4o"
MAX_RETRIES = 5
MAX_REQUIREMENT_CHARS = 12_000
MAX_CODE_CHARS = 160_000
MAX_LOG_CHARS = 32_000
MAX_LEARNING_EVENTS = 100

BLOCKED_IMPORTS = {
    "builtins", "ctypes", "ftplib", "http", "importlib", "marshal", "multiprocessing",
    "os", "paramiko", "pickle", "requests", "shutil", "socket", "subprocess",
    "telnetlib", "urllib", "webbrowser",
}
BLOCKED_CALLS = {
    "eval", "exec", "compile", "__import__", "breakpoint", "getattr", "setattr",
    "delattr", "globals", "locals", "vars",
}
BLOCKED_ATTRIBUTES = {
    "load_module", "exec_module", "__subclasses__", "__globals__", "__code__",
    "__mro__", "__bases__",
}
LEARNING_THREAD_LOCK = threading.RLock()
SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|authorization|token|password)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
)
IMAGE_PATTERN = re.compile(r"[a-z0-9][a-z0-9._/-]*(?::[a-zA-Z0-9._-]+)?\Z")

CANDIDATE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "code": {"type": "string"},
        "test_code": {"type": "string"},
        "change_summary": {"type": "string"},
        "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
        "dependencies": {"type": "array", "items": {"type": "string"}, "maxItems": 20},
    },
    "required": ["code", "test_code", "change_summary", "risk_level", "dependencies"],
}


class CodeImproverError(RuntimeError):
    """사용자에게 안전하게 표시할 수 있는 파이프라인 오류."""


class Sandbox(Protocol):
    def preflight(self) -> tuple[bool, str]: ...
    def execute(self, code: str, generated_test: str, trusted_test: str) -> tuple[bool, str]: ...


@dataclass(frozen=True)
class StaticValidation:
    ok: bool
    clean_code: str
    issues: tuple[str, ...]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _redact(value: Any, limit: int = MAX_LOG_CHARS) -> str:
    text = str(value).replace("\x00", "")
    for pattern in SECRET_PATTERNS:
        text = pattern.sub(lambda m: f"{m.group(1)}=<redacted>" if m.lastindex else "<redacted>", text)
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/-]{8,}", "Bearer <redacted>", text)
    return text[:limit]


def _strict_json(text: str) -> Any:
    return json.loads(
        text,
        parse_constant=reject_nonstandard_json,
        object_pairs_hook=unique_json_object,
    )


def _strip_single_fence(value: str) -> str:
    text = value.strip()
    if "```" not in text:
        return text
    match = re.fullmatch(r"```(?:python)?\s*\n?(.*?)\n?```", text, flags=re.DOTALL | re.IGNORECASE)
    if not match:
        raise CodeImproverError("코드 이외의 Markdown 또는 여러 코드 블록이 섞였습니다.")
    return match.group(1).strip()


def validate_python_source(code: str, *, require_tests: bool = False) -> StaticValidation:
    if not isinstance(code, str) or not code.strip():
        return StaticValidation(False, "", ("빈 Python 코드",))
    if len(code) > MAX_CODE_CHARS:
        return StaticValidation(False, "", ("코드 크기 제한 초과",))
    try:
        clean = _strip_single_fence(code)
        tree = ast.parse(clean)
    except (SyntaxError, CodeImproverError) as exc:
        line = getattr(exc, "lineno", None)
        detail = f"{type(exc).__name__}: {exc}"
        if line:
            detail += f" (line {line})"
        return StaticValidation(False, "", (_redact(detail, 1000),))

    issues: set[str] = set()
    test_found = False
    assertion_found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in BLOCKED_IMPORTS:
                    issues.add(f"차단된 모듈 import: {root}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0]
            if root in BLOCKED_IMPORTS:
                issues.add(f"차단된 모듈 import: {root}")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in BLOCKED_CALLS:
                issues.add(f"차단된 호출: {node.func.id}")
            if isinstance(node.func, ast.Attribute) and node.func.attr in BLOCKED_ATTRIBUTES:
                issues.add(f"차단된 속성 호출: {node.func.attr}")
            if isinstance(node.func, ast.Attribute) and node.func.attr.startswith("assert"):
                assertion_found = True
        elif isinstance(node, ast.Attribute) and node.attr in BLOCKED_ATTRIBUTES:
            issues.add(f"차단된 속성 접근: {node.attr}")
        elif isinstance(node, ast.Assert):
            assertion_found = True
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            test_found = True

    if require_tests:
        if not test_found:
            issues.add("실행 가능한 test* 함수 또는 Test* 클래스 없음")
        if not assertion_found:
            issues.add("검증 assertion 없음")
    return StaticValidation(not issues, clean, tuple(sorted(issues)))


def parse_candidate_payload(raw_payload: str) -> dict[str, Any]:
    if not isinstance(raw_payload, str) or not raw_payload.strip():
        raise CodeImproverError("모델의 구조화 출력이 비어 있습니다.")
    if len(raw_payload) > MAX_CODE_CHARS * 3:
        raise CodeImproverError("모델 출력 크기 제한을 초과했습니다.")
    try:
        payload = _strict_json(raw_payload)
    except (json.JSONDecodeError, ValueError) as exc:
        raise CodeImproverError(f"구조화 JSON 오류: {_redact(exc, 500)}") from exc
    required = set(CANDIDATE_SCHEMA["required"])
    if not isinstance(payload, dict) or set(payload) != required:
        raise CodeImproverError("허용된 5개 구조화 필드가 정확히 필요합니다.")
    if payload.get("risk_level") not in {"low", "medium", "high"}:
        raise CodeImproverError("risk_level 값이 올바르지 않습니다.")
    dependencies = payload.get("dependencies")
    if not isinstance(dependencies, list) or len(dependencies) > 20 or not all(
        isinstance(item, str) and 0 < len(item) <= 120 for item in dependencies
    ):
        raise CodeImproverError("dependencies 구조가 올바르지 않습니다.")
    if dependencies:
        raise CodeImproverError("격리검사는 표준 라이브러리만 허용하며 외부 패키지를 자동 설치하지 않습니다.")
    if not isinstance(payload.get("change_summary"), str) or not payload["change_summary"].strip():
        raise CodeImproverError("변경 요약이 비어 있습니다.")
    if len(payload["change_summary"]) > 2000:
        raise CodeImproverError("변경 요약 크기 제한을 초과했습니다.")
    return payload


def _default_learning() -> dict[str, Any]:
    return {
        "version": 1,
        "engine": ENGINE_VERSION,
        "updated_at": None,
        "total_attempts": 0,
        "successful_proposals": 0,
        "failure_groups": {},
        "recent_events": [],
        "policy": {
            "model_training_claimed": False,
            "generated_code_auto_applied": False,
            "raw_code_persisted_in_learning_log": False,
        },
    }


def _validate_learning(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CodeImproverError("AI 코드개선 학습기록은 JSON 객체여야 합니다.")
    groups = value.get("failure_groups")
    events = value.get("recent_events")
    if not isinstance(groups, dict) or not isinstance(events, list):
        raise CodeImproverError("AI 코드개선 학습기록 구조가 손상되었습니다.")
    result = _default_learning()
    result["total_attempts"] = max(0, min(1_000_000, int(value.get("total_attempts", 0))))
    result["successful_proposals"] = max(0, min(1_000_000, int(value.get("successful_proposals", 0))))
    clean_groups: dict[str, dict[str, Any]] = {}
    for key, row in list(groups.items())[:1000]:
        if not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{16}", key) or not isinstance(row, dict):
            continue
        clean_groups[key] = {
            "phase": _redact(row.get("phase", "unknown"), 80),
            "signature": _redact(row.get("signature", "unknown"), 300),
            "occurrences": max(1, min(1_000_000, int(row.get("occurrences", 1)))),
            "last_seen": _redact(row.get("last_seen", ""), 50),
            "last_resolution": _redact(row.get("last_resolution", ""), 300),
        }
    result["failure_groups"] = clean_groups
    result["recent_events"] = [row for row in events[-MAX_LEARNING_EVENTS:] if isinstance(row, dict)]
    result["updated_at"] = value.get("updated_at") if isinstance(value.get("updated_at"), str) else None
    return result


class CodeLearningStore:
    def __init__(self, path: str | Path = LEARNING_PATH):
        self.path = Path(path).resolve()
        self.backup = self.path.with_suffix(self.path.suffix + ".bak")

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return _default_learning()
        if self.path.is_symlink():
            raise CodeImproverError("AI 코드개선 학습기록 심볼릭 링크가 차단되었습니다.")
        try:
            return _validate_learning(_strict_json(safe_read_text(self.path, max_bytes=2_000_000)))
        except Exception as primary_exc:
            if self.backup.is_file() and not self.backup.is_symlink():
                try:
                    return _validate_learning(_strict_json(safe_read_text(self.backup, max_bytes=2_000_000)))
                except Exception:
                    pass
            raise CodeImproverError(f"AI 코드개선 학습기록 복구 실패: {_redact(primary_exc, 500)}") from primary_exc

    def _save_unlocked(self, value: dict[str, Any]) -> None:
        clean = _validate_learning(value)
        clean["updated_at"] = _utc_now()
        if self.path.is_file() and not self.path.is_symlink():
            current = _validate_learning(_strict_json(safe_read_text(self.path, max_bytes=2_000_000)))
            atomic_write_json(self.backup, current, suffix=".ai-learning-backup.tmp")
        atomic_write_json(self.path, clean, suffix=".ai-learning.tmp")

    def record(self, *, phase: str, ok: bool, detail: str, resolution: str, attempt: int) -> dict[str, Any]:
        from auto_repair_engine import _memory_process_lock
        with LEARNING_THREAD_LOCK, _memory_process_lock(self.path):
            memory = self.load()
            memory["total_attempts"] += 1
            clean_detail = _redact(detail, 2000)
            normalized = re.sub(r"\b\d+(?:\.\d+)?\b", "<n>", clean_detail.lower())
            signature = normalized[:300] or "no-detail"
            group_id = hashlib.sha256(f"{phase}|{signature}".encode()).hexdigest()[:16]
            if not ok:
                group = memory["failure_groups"].setdefault(group_id, {
                    "phase": phase,
                    "signature": signature,
                    "occurrences": 0,
                    "last_seen": None,
                    "last_resolution": "",
                })
                group["occurrences"] = min(1_000_000, int(group.get("occurrences", 0)) + 1)
                group["last_seen"] = _utc_now()
                group["last_resolution"] = _redact(resolution, 300)
            else:
                memory["successful_proposals"] += 1
            memory["recent_events"].append({
                "timestamp": _utc_now(), "phase": phase, "ok": bool(ok),
                "group_id": None if ok else group_id, "attempt": max(1, min(MAX_RETRIES, int(attempt))),
                "detail": clean_detail[:600], "resolution": _redact(resolution, 300),
            })
            del memory["recent_events"][:-MAX_LEARNING_EVENTS]
            self._save_unlocked(memory)
            return {"group_id": None if ok else group_id, "memory": memory}


class DockerSandbox:
    """로컬에 이미 설치된 전용 이미지에서만 후보 코드를 실행한다."""

    def __init__(self, image: str = "python:3.11-slim", timeout_sec: int = 20):
        if not IMAGE_PATTERN.fullmatch(image) or len(image) > 160:
            raise CodeImproverError("Docker 이미지 이름이 올바르지 않습니다.")
        self.image = image
        self.timeout_sec = max(5, min(120, int(timeout_sec)))
        self._preflight_cache: tuple[bool, str] | None = None

    def _run(self, command: list[str], timeout: int = 10) -> subprocess.CompletedProcess[str]:
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)

    def preflight(self) -> tuple[bool, str]:
        if self._preflight_cache is not None:
            return self._preflight_cache
        docker = shutil.which("docker")
        if not docker:
            self._preflight_cache = (False, "Docker 실행파일이 없습니다. 생성 코드는 호스트에서 대신 실행하지 않습니다.")
            return self._preflight_cache
        try:
            server = self._run([docker, "version", "--format", "{{.Server.Version}}"], 8)
            if server.returncode != 0:
                self._preflight_cache = (False, "Docker 엔진에 연결할 수 없습니다.")
                return self._preflight_cache
            image = self._run([docker, "image", "inspect", self.image], 8)
            if image.returncode != 0:
                self._preflight_cache = (False, f"격리 이미지가 로컬에 없습니다: {self.image} (자동 다운로드 안 함)")
                return self._preflight_cache
            self._preflight_cache = (True, "Docker 격리 실행 준비 완료")
            return self._preflight_cache
        except (OSError, subprocess.TimeoutExpired) as exc:
            self._preflight_cache = (False, f"Docker 사전검사 실패: {_redact(exc, 500)}")
            return self._preflight_cache

    def build_command(self, workspace: str, container_name: str) -> list[str]:
        docker = shutil.which("docker") or "docker"
        return [
            docker, "run", "--name", container_name, "--rm", "--network", "none",
            "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
            "--pids-limit", "64", "--memory", "256m", "--memory-swap", "256m",
            "--cpus", "1.0", "--user", "65534:65534",
            "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=64m",
            "--mount", f"type=bind,src={workspace},dst=/workspace,readonly",
            "-w", "/workspace", self.image,
            "python", "-B", "-m", "unittest", "discover", "-s", "/workspace",
            "-p", "test_*.py", "-v",
        ]

    def execute(self, code: str, generated_test: str, trusted_test: str) -> tuple[bool, str]:
        ready, detail = self.preflight()
        if not ready:
            return False, detail
        container_name = f"tcg-code-check-{secrets.token_hex(6)}"
        docker = shutil.which("docker") or "docker"
        with tempfile.TemporaryDirectory(prefix="tcg-ai-code-") as temp_dir:
            workspace = Path(temp_dir)
            files = {
                "solution.py": code,
                "test_generated.py": generated_test,
                "test_regression.py": trusted_test,
            }
            for name, content in files.items():
                target = workspace / name
                target.write_text(content, encoding="utf-8")
                target.chmod(0o444)
            workspace.chmod(0o755)
            command = self.build_command(str(workspace), container_name)
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=(os.name != "nt"))
            try:
                stdout, stderr = process.communicate(timeout=self.timeout_sec)
            except subprocess.TimeoutExpired:
                if os.name != "nt":
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except OSError:
                        process.kill()
                else:
                    process.kill()
                process.communicate()
                subprocess.run([docker, "rm", "-f", container_name], capture_output=True, timeout=8, check=False)
                return False, f"TimeoutError: 격리검사가 {self.timeout_sec}초를 초과했습니다."
            output = _redact(f"{stdout}\n{stderr}")
            return process.returncode == 0, output


def load_trusted_test(path: str | Path, trusted_root: str | Path = TRUSTED_TEST_ROOT) -> str:
    root = Path(trusted_root).resolve()
    target = Path(path)
    if not target.is_absolute():
        target = root / target
    try:
        resolved = target.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise CodeImproverError("고정 회귀검사는 trusted_ai_tests 폴더 안의 실제 파일이어야 합니다.") from exc
    if resolved.is_symlink() or not resolved.is_file():
        raise CodeImproverError("고정 회귀검사 파일 형식이 안전하지 않습니다.")
    content = safe_read_text(resolved, max_bytes=MAX_CODE_CHARS)
    checked = validate_python_source(content, require_tests=True)
    if not checked.ok:
        raise CodeImproverError("고정 회귀검사 정적검사 실패: " + "; ".join(checked.issues))
    return checked.clean_code


class SecureAICodeImprover:
    def __init__(self, *, client: Any | None = None, model: str | None = None,
                 sandbox: Sandbox | None = None, learning_store: CodeLearningStore | None = None,
                 proposal_root: str | Path = PROPOSAL_ROOT):
        self.client = client
        self.model = (model or os.environ.get("TCG_OPENAI_MODEL") or DEFAULT_MODEL).strip()
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", self.model):
            raise CodeImproverError("모델 이름이 올바르지 않습니다.")
        self.sandbox = sandbox or DockerSandbox(os.environ.get("TCG_CODE_SANDBOX_IMAGE", "python:3.11-slim"))
        self.learning_store = learning_store or CodeLearningStore()
        self.proposal_root = Path(proposal_root).resolve()

    def _client(self) -> Any:
        if self.client is not None:
            return self.client
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise CodeImproverError("선택 기능에 필요한 openai 패키지가 설치되지 않았습니다.") from exc
        self.client = OpenAI()  # OPENAI_API_KEY 환경변수 사용, 키를 파일에 저장하지 않음
        return self.client

    def _request(self, requirement: str, feedback: str | None = None) -> dict[str, Any]:
        system = (
            "안전한 Python TDD 개발자입니다. 외부 네트워크·subprocess·동적 코드 실행·시스템 변경 없이 "
            "요구사항을 구현하십시오. test_code는 표준 unittest로 작성하고 solution을 import하십시오. "
            "JSON Schema에 맞는 값만 반환하십시오."
        )
        user = f"요구사항:\n{requirement}"
        if feedback:
            user += f"\n\n이전 후보 검증 결과:\n{_redact(feedback, 6000)}\n같은 오류를 반복하지 말고 수정하십시오."
        response = self._client().responses.create(
            model=self.model,
            input=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.1,
            max_output_tokens=12_000,
            text={"format": {"type": "json_schema", "name": "code_candidate", "strict": True,
                              "schema": CANDIDATE_SCHEMA}},
        )
        return parse_candidate_payload(getattr(response, "output_text", ""))

    def _save_proposal(self, requirement: str, candidate: dict[str, Any], attempt: int) -> Path:
        if self.proposal_root.exists() and self.proposal_root.is_symlink():
            raise CodeImproverError("코드 후보 저장 폴더 심볼릭 링크가 차단되었습니다.")
        self.proposal_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        proposal_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(5)}"
        directory = self.proposal_root / proposal_id
        directory.mkdir(mode=0o700)
        atomic_write_text(directory / "solution.py", candidate["code"] + "\n", suffix=".proposal.tmp")
        atomic_write_text(directory / "test_generated.py", candidate["test_code"] + "\n", suffix=".proposal.tmp")
        atomic_write_json(directory / "manifest.json", {
            "version": 1, "engine": ENGINE_VERSION, "proposal_id": proposal_id,
            "created_at": _utc_now(), "status": "READY_FOR_HUMAN_REVIEW",
            "attempt": attempt, "model": self.model,
            "requirement_sha256": hashlib.sha256(requirement.encode()).hexdigest(),
            "code_sha256": hashlib.sha256(candidate["code"].encode()).hexdigest(),
            "generated_test_sha256": hashlib.sha256(candidate["test_code"].encode()).hexdigest(),
            "change_summary": candidate["change_summary"], "risk_level": candidate["risk_level"],
            "dependencies": candidate["dependencies"],
            "security": {"production_files_modified": False, "automatic_application": False,
                         "trusted_regression_passed": True, "network_disabled_during_test": True},
        }, suffix=".proposal-manifest.tmp")
        return directory

    def run(self, requirement: str, trusted_test: str, *, max_retries: int = 3) -> dict[str, Any]:
        if not isinstance(requirement, str) or not requirement.strip():
            raise CodeImproverError("요구사항이 비어 있습니다.")
        requirement = requirement.strip()
        if len(requirement) > MAX_REQUIREMENT_CHARS:
            raise CodeImproverError("요구사항 크기 제한을 초과했습니다.")
        trusted = validate_python_source(trusted_test, require_tests=True)
        if not trusted.ok:
            raise CodeImproverError("고정 회귀검사 실패: " + "; ".join(trusted.issues))
        ready, preflight = self.sandbox.preflight()
        if not ready:
            return {"status": "SANDBOX_UNAVAILABLE", "attempts": 0, "detail": _redact(preflight, 1000),
                    "production_files_modified": False}

        retries = max(1, min(MAX_RETRIES, int(max_retries)))
        feedback: str | None = None
        seen_failures: set[str] = set()
        for attempt in range(1, retries + 1):
            try:
                candidate = self._request(requirement, feedback)
                code_check = validate_python_source(candidate["code"])
                test_check = validate_python_source(candidate["test_code"], require_tests=True)
                issues = [*code_check.issues, *test_check.issues]
                if issues:
                    phase, passed, log = "static_validation", False, "; ".join(issues)
                else:
                    candidate["code"] = code_check.clean_code
                    candidate["test_code"] = test_check.clean_code
                    passed, log = self.sandbox.execute(candidate["code"], candidate["test_code"], trusted.clean_code)
                    phase = "isolated_regression"
                if passed:
                    directory = self._save_proposal(requirement, candidate, attempt)
                    self.learning_store.record(phase="proposal_verified", ok=True,
                                               detail="정적검사·생성테스트·고정 회귀검사 통과",
                                               resolution="사람 검토 대기 후보로만 저장", attempt=attempt)
                    return {"status": "READY_FOR_HUMAN_REVIEW", "attempts": attempt,
                            "proposal_id": directory.name, "proposal_path": str(directory),
                            "change_summary": candidate["change_summary"], "risk_level": candidate["risk_level"],
                            "production_files_modified": False}
            except Exception as exc:
                phase, log = "model_or_schema", f"{type(exc).__name__}: {_redact(exc, 3000)}"

            normalized = re.sub(r"\b\d+(?:\.\d+)?\b", "<n>", _redact(log, 6000).lower())
            duplicate = normalized in seen_failures
            seen_failures.add(normalized)
            resolution = "동일 실패 반복으로 조기 중단" if duplicate else "오류 요약만 다음 생성 시도에 전달"
            self.learning_store.record(phase=phase, ok=False, detail=log, resolution=resolution, attempt=attempt)
            if duplicate:
                return {"status": "FAILED", "attempts": attempt, "last_phase": phase,
                        "last_log": _redact(log, 3000), "stopped_duplicate_failure": True,
                        "production_files_modified": False}
            feedback = f"단계={phase}\n{_redact(log, 6000)}"
        return {"status": "FAILED", "attempts": retries, "last_phase": phase,
                "last_log": _redact(log, 3000), "stopped_duplicate_failure": False,
                "production_files_modified": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="승인형 AI 코드개선 후보 생성·격리검증")
    parser.add_argument("--requirement", required=True, help="구현 요구사항")
    parser.add_argument("--trusted-test", required=True, help="trusted_ai_tests 안의 고정 회귀검사 파일")
    parser.add_argument("--max-retries", type=int, default=3)
    args = parser.parse_args(argv)
    try:
        trusted = load_trusted_test(args.trusted_test)
        result = SecureAICodeImprover().run(args.requirement, trusted, max_retries=args.max_retries)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "READY_FOR_HUMAN_REVIEW" else 2
    except CodeImproverError as exc:
        print(json.dumps({"status": "FAILED", "error": _redact(exc, 1000),
                          "production_files_modified": False}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
