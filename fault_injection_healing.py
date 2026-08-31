#!/usr/bin/env python3
"""격리 고장주입, 원인학습, 무결성 진단 및 제한적 자가복구.

코드 고장주입과 코드 복구 연습은 임시 복제본에서만 수행한다. 운영 폴더에서는
무결성 진단과 검증된 JSON 백업 복원만 자동 허용하며, 생성 코드를 자동 적용하지
않는다. 이 경계는 학습값 오염과 자가수정 폭주를 막기 위한 안전 계약이다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import py_compile
import re
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from safe_runtime import atomic_write_json, reject_nonstandard_json, unique_json_object


ROOT = Path(__file__).resolve().parent
ENGINE_VERSION = "v109-card-identity-ocr-learning"
MANIFEST_PATH = ROOT / "integrity_manifest.json"
LEARNING_PATH = ROOT / "fault_learning.json"
MUTABLE_JSON = {
    "adaptive_collection_stats.json", "auto_repair_memory.json", "auto_update_issues.json",
    "auto_update_report.json", "fault_learning.json", "FINAL_VERIFICATION_REPORT.json",
    "INTEGRATION_REPORT.json", "V107_CURRENT_VERIFICATION.json",
    "learning_store.json", "link_health_report.json",
    "scenario_learning_profiles.json", "source_collection_stats.json",
    "verification_cycles.json", "verification_history.json", "vision_calibration.json",
    "vision_self_learning_params.json", "vision_self_learning_report.json",
    "V103_MARKET_SOURCE_TEST_REPORT.json",
    "integrity_manifest.json", "web_discovery_candidates.json", "social_event_candidates.json", "social_source_registry.json",
    "event_gap_learning.json", "event_gap_learning.json.bak",
    "graded_photo_candidates.json", "graded_photo_source_learning.json", "graded_photo_official_cache.json",
    "graded_photo_reference_learning.json", "detailed_collection_learning.json",
    "collection_learning_memory.json", "search_method_learning.json", "search_engine_profile.json",
    "V108_FINAL_VERIFICATION_REPORT.json", "V109_FINAL_VERIFICATION_REPORT.json",
    "security_audit_report.json", "security_learning_memory.json",
}
STRUCTURED_MUTABLE_JSON = {
    "security_audit_report.json": {
        "schema_version": "int", "generated_at": "str", "scope": "str",
        "finding_counts": "dict", "findings": "list", "note": "str",
    },
    "security_learning_memory.json": {
        "schema_version": "int", "findings": "dict", "updated_at": "str",
    },
}
RECOVERABLE_DATA = {
    "releases.json", "market_watch.json", "market_prices.json",
    "promo_events.json", "purchase_sources.json", "exchange_rates.json",
}
TRACKED_SUFFIXES = {".py", ".js", ".html", ".json", ".sh", ".bat", ".cmd", ".command",
                    ".webmanifest", ".svg", ".yml", ".yaml"}
MAX_FILE_BYTES = 20 * 1024 * 1024


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _strict_json_bytes(payload: bytes) -> Any:
    return json.loads(
        payload.decode("utf-8"),
        parse_constant=reject_nonstandard_json,
        object_pairs_hook=unique_json_object,
    )


def _safe_file(root: Path, relative: str) -> Path:
    # Accept both NFC and NFD Korean filenames while retaining a strict
    # containment check. The old Hangul-syllable-only regex let the manifest
    # create entries that its own reader could not reopen on NFD filesystems.
    if (not isinstance(relative, str) or not 1 <= len(relative) <= 180
            or Path(relative).is_absolute() or ".." in Path(relative).parts
            or "\\" in relative or ":" in relative
            or any(ord(char) < 32 or ord(char) == 127 for char in relative)):
        raise ValueError("허용되지 않은 상대경로")
    candidate = (root / relative).resolve()
    if candidate.parent != root.resolve() and root.resolve() not in candidate.parents:
        raise ValueError("프로젝트 경로 밖 접근 차단")
    if candidate.is_symlink() or candidate.parent.is_symlink():
        raise ValueError("심볼릭 링크 경로 차단")
    return candidate


def tracked_files(root: Path = ROOT) -> list[Path]:
    result: list[Path] = []
    root = root.resolve()
    blocked = {"__pycache__", ".tcg_ai_proposals", "trusted_ai_tests"}
    for current, directories, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        relative_dir = current_path.relative_to(root)
        if not relative_dir.parts:
            directories[:] = [
                name for name in directories
                if name == ".github" or (not name.startswith(".") and name not in blocked)
            ]
        elif relative_dir.parts == (".github",):
            directories[:] = [name for name in directories if name == "workflows"]
        else:
            directories[:] = [
                name for name in directories
                if not name.startswith(".") and name not in blocked
            ]
        directories[:] = [
            name for name in directories if not (current_path / name).is_symlink()
        ]
        workflow_dir = relative_dir.parts[:2] == (".github", "workflows")
        if relative_dir.parts and not workflow_dir and any(part.startswith(".") for part in relative_dir.parts):
            continue
        for filename in filenames:
            path = current_path / filename
            if filename.startswith(".") or path.is_symlink():
                continue
            if path.suffix.lower() not in TRACKED_SUFFIXES or filename in MUTABLE_JSON:
                continue
            try:
                if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            result.append(path)
    return sorted(result, key=lambda item: item.as_posix())


def _mutable_json_manifest(root: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for relative, required in STRUCTURED_MUTABLE_JSON.items():
        try:
            path = _safe_file(root, relative)
            info = path.lstat()
            if stat.S_ISREG(info.st_mode) and not path.is_symlink() and info.st_size <= MAX_FILE_BYTES:
                result[relative] = {"required": dict(required), "max_bytes": MAX_FILE_BYTES}
        except (OSError, ValueError):
            continue
    return result


def _validate_mutable_json(path: Path, contract: Any) -> bool:
    if not isinstance(contract, dict) or not isinstance(contract.get("required"), dict):
        return False
    info = path.lstat()
    max_bytes = min(MAX_FILE_BYTES, max(1, int(contract.get("max_bytes", MAX_FILE_BYTES))))
    if not stat.S_ISREG(info.st_mode) or path.is_symlink() or info.st_size > max_bytes:
        return False
    payload = _strict_json_bytes(path.read_bytes())
    if not isinstance(payload, dict):
        return False
    type_map = {"int": int, "str": str, "dict": dict, "list": list, "bool": bool}
    for key, type_name in contract["required"].items():
        expected_type = type_map.get(str(type_name))
        if expected_type is None or key not in payload:
            return False
        value = payload[key]
        if expected_type in {int, bool}:
            if type(value) is not expected_type:
                return False
        elif not isinstance(value, expected_type):
            return False
    return True


def build_integrity_manifest(root: Path = ROOT, target: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    files = {
        path.relative_to(root).as_posix(): {"sha256": _sha256(path), "bytes": path.stat().st_size}
        for path in tracked_files(root)
    }
    mutable_json = _mutable_json_manifest(root)
    payload = {
        "version": 2,
        "engine": ENGINE_VERSION,
        "generated_at": _utc_now(),
        "files": files,
        "mutable_json": mutable_json,
        "policy": {
            "generated_code_auto_applied": False,
            "code_corruption_auto_repaired": False,
            "verified_json_backup_auto_repair_allowed": True,
            "fault_injection_production_allowed": False,
            "mutable_runtime_json_validation": "strict-schema-without-fixed-hash",
        },
    }
    if target is not None:
        atomic_write_json(target, payload, suffix=".integrity.tmp")
    return payload


def diagnose_integrity(root: Path = ROOT, manifest_path: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    manifest_path = manifest_path or root / MANIFEST_PATH.name
    try:
        manifest = _strict_json_bytes(manifest_path.read_bytes())
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        return {"ok": False, "engine": ENGINE_VERSION, "error": f"manifest:{type(exc).__name__}", "files": []}
    rows = []
    files = manifest.get("files") if isinstance(manifest, dict) else None
    if not isinstance(files, dict):
        return {"ok": False, "engine": ENGINE_VERSION, "error": "manifest:schema", "files": []}
    for relative, expected in files.items():
        try:
            path = _safe_file(root, relative)
            info = path.lstat()
            regular = stat.S_ISREG(info.st_mode) and not path.is_symlink()
            expected_bytes = int(expected["bytes"])
            size_matches = regular and info.st_size == expected_bytes and info.st_size <= MAX_FILE_BYTES
            actual_hash = _sha256(path) if size_matches else None
            ok = size_matches and actual_hash == expected["sha256"]
            rows.append({"file": relative, "ok": ok, "reason": "정상" if ok else "누락·변경·형식 이상"})
        except (OSError, ValueError, TypeError, KeyError, OverflowError):
            rows.append({"file": str(relative)[:180], "ok": False, "reason": "읽기 또는 무결성 검사 실패"})
    mutable_json = manifest.get("mutable_json", {}) if isinstance(manifest, dict) else {}
    if not isinstance(mutable_json, dict):
        return {"ok": False, "engine": ENGINE_VERSION, "error": "manifest:mutable-schema", "files": rows}
    for relative, contract in mutable_json.items():
        try:
            path = _safe_file(root, relative)
            ok = _validate_mutable_json(path, contract)
            rows.append({"file": relative, "ok": ok,
                         "reason": "정상(가변 JSON 구조검사)" if ok else "가변 JSON 구조 이상"})
        except (OSError, ValueError, TypeError, KeyError, OverflowError, UnicodeError):
            rows.append({"file": str(relative)[:180], "ok": False, "reason": "가변 JSON 검사 실패"})
    return {"ok": bool(rows) and all(row["ok"] for row in rows), "engine": ENGINE_VERSION,
            "checked": len(rows), "failed": sum(not row["ok"] for row in rows), "files": rows}


def restore_verified_data_backups(root: Path = ROOT) -> dict[str, Any]:
    """손상/누락 운영 JSON만 같은 폴더의 검증된 .bak에서 원자 복원한다."""
    root = root.resolve()
    rows = []
    for name in sorted(RECOVERABLE_DATA):
        current = _safe_file(root, name)
        backup = _safe_file(root, name + ".bak")
        try:
            current_valid = current.is_file() and not current.is_symlink()
            if current_valid:
                _strict_json_bytes(current.read_bytes())
                rows.append({"file": name, "status": "healthy", "repaired": False})
                continue
        except (OSError, ValueError, TypeError, UnicodeError):
            current_valid = False
        try:
            if not backup.is_file() or backup.is_symlink() or backup.stat().st_size > MAX_FILE_BYTES:
                raise ValueError("검증된 백업 없음")
            payload = backup.read_bytes()
            _strict_json_bytes(payload)
            temp = current.with_suffix(current.suffix + ".heal.tmp")
            if temp.exists() or temp.is_symlink():
                raise ValueError("복구 임시경로 충돌")
            try:
                with temp.open("xb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                _strict_json_bytes(temp.read_bytes())
                os.replace(temp, current)
            finally:
                if temp.exists():
                    temp.unlink()
            rows.append({"file": name, "status": "restored-from-verified-backup", "repaired": True})
        except (OSError, ValueError, TypeError, UnicodeError) as exc:
            rows.append({"file": name, "status": f"not-repaired:{type(exc).__name__}", "repaired": False})
    return {"ok": all(row["status"] == "healthy" or row["repaired"] for row in rows),
            "engine": ENGINE_VERSION, "repaired": sum(row["repaired"] for row in rows), "results": rows}


@dataclass(frozen=True)
class FaultScenario:
    scenario_id: str
    family: str
    target: str
    needle: bytes
    replacement: bytes
    probe: str
    description: str


_CACHE_SOURCE = (ROOT / "sw.js").read_bytes()
_CACHE_TOKEN_MATCH = re.search(rb"const CACHE='(tcg-v\d+(?:-[a-z0-9-]+)?)'", _CACHE_SOURCE, re.I)
CURRENT_CACHE_TOKEN = _CACHE_TOKEN_MATCH.group(1) if _CACHE_TOKEN_MATCH else b"tcg-cache-token-missing"


SCENARIOS = (
    FaultScenario("python-syntax-token", "syntax", "auto_repair_engine.py", b"from __future__ import annotations", b"from __future__ import (", "python", "Python 구문 손상"),
    FaultScenario("javascript-syntax-token", "syntax", "grading_vision_engine.js", b"'use strict';", b"'use strict';}", "javascript", "JavaScript 구문 손상"),
    FaultScenario("json-truncated", "data", "market_prices.json", b"{", b"", "json", "JSON 시작문자 유실"),
    FaultScenario("json-duplicate-key", "data", "exchange_rates.json", b"{", b'{"version":1,"version":2,', "json", "JSON 중복 키 주입"),
    FaultScenario("pwa-cache-version-skew", "version", "sw.js", CURRENT_CACHE_TOKEN, b"tcg-stale-cache", "required-current-cache", "PWA 캐시 버전 불일치"),
    FaultScenario("server-version-skew", "version", "tcg_updater.py", b"v109-card-identity-ocr-learning", b"v00-stale-runtime", "required-current-engine", "서버 통합버전 불일치"),
    FaultScenario("camera-policy-removed", "camera", "tcg_updater.py", b"camera=(self)", b"camera=()", "required-camera-policy", "카메라 권한 정책 차단"),
    FaultScenario("camera-duplicate-guard-removed", "camera", "index.html", b"sceneDistance(metric,frontMetric)>=12", b"sceneDistance(metric,frontMetric)>=-1", "required-camera-guard", "같은 면 중복촬영 보호 제거"),
    FaultScenario("camera-manual-duplicate-guard-removed", "camera", "index.html", b"manual&&stage===1&&frontMetric", b"manual&&false&&frontMetric", "required-camera-manual-guard", "수동 같은 면 중복촬영 보호 제거"),
    FaultScenario("camera-permission-timeout-removed", "camera", "index.html", b"const CAMERA_REQUEST_TIMEOUT_MS", b"const DISABLED_CAMERA_REQUEST_TIMEOUT_MS", "required-camera-request-timeout", "카메라 권한응답 제한 제거"),
    FaultScenario("camera-track-ended-handler-removed", "camera", "index.html", b"addEventListener?.('ended'", b"addEventListener?.('disabled-ended'", "required-camera-ended-handler", "카메라 트랙 종료 감지 제거"),
    FaultScenario("vision-mask-disabled", "vision", "grading_vision_engine.js", b"if((gx-cx)*(gx-cx)+(gy-cy)*(gy-cy)<=radius*radius)mask[position]=1;", b"mask[position]=1;", "required-vision-mask", "카드 외부 마스크 제거"),
    FaultScenario("vision-canny-inverted", "vision", "grading_vision_engine.js", b"cannyLow:35,cannyHigh:105", b"cannyLow:180,cannyHigh:20", "required-vision-threshold", "Canny 임계값 역전"),
    FaultScenario("vision-hough-removed", "vision", "grading_vision_engine.js", b"probabilisticHoughSegments", b"disabledHoughSegments", "required-hough", "Hough 선분 분석 연결 제거"),
    FaultScenario("vision-whitening-removed", "vision", "grading_vision_engine.js", b"function analyzeWhitening", b"function disabledWhitening", "required-whitening", "백화 전용 측정 제거"),
    FaultScenario("unsafe-blank-opener", "security", "index.html", b'rel="noopener noreferrer"', b'rel="opener"', "required-noopener", "새 창 opener 보호 제거"),
    FaultScenario("api-origin-guard-removed", "security", "tcg_updater.py", b"if not self._require_mutation_origin()", b"if False", "required-origin-guard", "변경 API 출처검사 제거"),
    FaultScenario("atomic-write-bypass", "storage", "safe_runtime.py", b"os.replace", b"shutil.move", "required-atomic-write", "원자 교체 우회"),
    FaultScenario("bounded-retry-disabled", "recovery", "ai_code_improver.py", b"MAX_RETRIES = 5", b"MAX_RETRIES = 5000", "required-retry-cap", "자가수정 재시도 폭주"),
    FaultScenario("generated-auto-apply-enabled", "security", "ai_code_improver.py", b'"automatic_application": False', b'"automatic_application": True', "required-human-review", "생성 코드 자동반영 우회"),
    FaultScenario("feature-contract-file-removed", "contract", "feature_contract.py", b'"verify_camera_runtime.js",', b'"missing_camera_runtime.js",', "required-feature-file", "필수 기능파일 계약 변조"),
)


def _run(command: list[str], cwd: Path, timeout: int = 30) -> bool:
    try:
        return subprocess.run(command, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=timeout, check=False).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _probe(root: Path, scenario: FaultScenario) -> bool:
    path = _safe_file(root, scenario.target)
    if scenario.probe == "python":
        try:
            py_compile.compile(str(path), doraise=True)
            return True
        except (OSError, py_compile.PyCompileError, SyntaxError):
            return False
    if scenario.probe == "javascript":
        return _run(["node", "--check", scenario.target], root)
    if scenario.probe == "json":
        try:
            _strict_json_bytes(path.read_bytes())
            return True
        except (OSError, ValueError, TypeError, UnicodeError):
            return False
    text = path.read_text(encoding="utf-8")
    cache_match = re.search(r"const CACHE='tcg-v(\d+)(?:-[a-z0-9-]+)?'", text, re.I)
    contracts = {
        "required-current-cache": bool(cache_match and int(cache_match.group(1)) >= 109
                                       and "./index.html" in text and "./manifest.webmanifest" in text),
        "required-current-engine": ENGINE_VERSION in text,
        "required-camera-policy": "camera=(self)" in text,
        "required-camera-guard": "sceneDistance(metric,frontMetric)>=12" in text,
        "required-camera-manual-guard": "manual&&stage===1&&frontMetric" in text,
        "required-camera-request-timeout": "const CAMERA_REQUEST_TIMEOUT_MS" in text and "requestCameraWithTimeout" in text,
        "required-camera-ended-handler": "addEventListener?.('ended'" in text,
        "required-vision-mask": "radius*radius)mask[position]=1" in text,
        "required-vision-threshold": "cannyLow:35,cannyHigh:105" in text and "cannyLow:180,cannyHigh:20" not in text,
        "required-hough": "function probabilisticHoughSegments" in text,
        "required-whitening": "function analyzeWhitening" in text,
        "required-noopener": 'rel="noopener noreferrer"' in text and 'rel="opener"' not in text,
        # The injected mutation targets the first guard, currently the manual
        # update handler. Counting every guard became blind once new protected
        # endpoints were added because one removal still left a high count.
        "required-origin-guard": re.search(
            r"def _manual_update\(self\):.{0,320}?if not self\._require_mutation_origin\(\)",
            text,
            re.S,
        ) is not None,
        "required-atomic-write": "os.replace" in text,
        "required-retry-cap": re.search(r"^MAX_RETRIES = 5$",text,re.M) is not None,
        "required-human-review": '"automatic_application": False' in text,
        "required-feature-file": '"verify_camera_runtime.js",' in text,
    }
    return bool(contracts.get(scenario.probe, False))


def _mutate(path: Path, scenario: FaultScenario) -> bytes:
    original = path.read_bytes()
    if scenario.needle not in original:
        raise ValueError(f"주입 기준문자열 누락:{scenario.scenario_id}")
    mutated = original.replace(scenario.needle, scenario.replacement, 1)
    if mutated == original:
        raise ValueError(f"고장주입 변화 없음:{scenario.scenario_id}")
    path.write_bytes(mutated)
    return original


def _save_fault_learning(report: dict[str, Any], target: Path) -> dict[str, Any]:
    profiles = {}
    for row in report["results"]:
        profile = profiles.setdefault(row["family"], {"attempts": 0, "detected": 0, "repaired": 0})
        profile["attempts"] += 1
        profile["detected"] += int(row["fault_detected"])
        profile["repaired"] += int(row["repair_verified"])
    payload = {
        "version": 1, "engine": ENGINE_VERSION, "updated_at": _utc_now(),
        "training_only": True, "scenario_count": len(report["results"]),
        "successful_scenarios": sum(row["ok"] for row in report["results"]),
        "profiles": profiles,
        "safety": {
            "production_files_modified": False,
            "scenario_text_executed": False,
            "network_accessed": False,
            "generated_code_auto_applied": False,
        },
    }
    atomic_write_json(target, payload, suffix=".fault-learning.tmp")
    return payload


def run_fault_lab(root: Path = ROOT, output: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    with tempfile.TemporaryDirectory(prefix="tcg-fault-lab-") as directory:
        lab = Path(directory) / "project"
        shutil.copytree(root, lab, ignore=shutil.ignore_patterns("__pycache__", ".tcg_ai_proposals", "*.pyc"))
        marker = lab / ".tcg_fault_lab"
        marker.write_text("isolated-only\n", encoding="utf-8")
        if not marker.is_file() or root == lab or root in lab.parents:
            raise RuntimeError("격리 고장주입 폴더 확인 실패")
        rows = []
        for scenario in SCENARIOS:
            path = _safe_file(lab, scenario.target)
            baseline_ok = _probe(lab, scenario)
            original = b""
            detected = repaired = False
            error = ""
            try:
                if not baseline_ok:
                    raise ValueError("기준 코드가 이미 계약을 통과하지 못함")
                original = _mutate(path, scenario)
                detected = not _probe(lab, scenario)
                path.write_bytes(original)
                repaired = _probe(lab, scenario) and path.read_bytes() == original
            except (OSError, ValueError, TypeError) as exc:
                error = f"{type(exc).__name__}:{str(exc)[:180]}"
            finally:
                if original and path.read_bytes() != original:
                    path.write_bytes(original)
            rows.append({
                "id": scenario.scenario_id, "family": scenario.family, "description": scenario.description,
                "baseline_ok": baseline_ok, "fault_detected": detected, "repair_verified": repaired,
                "ok": baseline_ok and detected and repaired, **({"error": error} if error else {}),
            })
        report = {
            "ok": all(row["ok"] for row in rows), "engine": ENGINE_VERSION,
            "scenario_count": len(rows), "successful_scenarios": sum(row["ok"] for row in rows),
            "results": rows, "production_files_modified": False,
        }
    if output is not None:
        _save_fault_learning(report, output)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TCG 격리 고장주입·무결성·제한적 자가복구")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--lab", action="store_true", help="임시 복제본에서 고장주입·복구학습")
    group.add_argument("--manifest", action="store_true", help="현재 검증본 무결성 기준 생성")
    group.add_argument("--diagnose", action="store_true", help="무결성 기준과 현재 파일 비교")
    group.add_argument("--heal-data", action="store_true", help="손상 JSON만 검증된 백업에서 복원")
    args = parser.parse_args(argv)
    if args.lab:
        result = run_fault_lab(ROOT, LEARNING_PATH)
    elif args.manifest:
        result = build_integrity_manifest(ROOT, MANIFEST_PATH)
        result = {"ok": True, "engine": ENGINE_VERSION, "tracked": len(result["files"])}
    elif args.diagnose:
        result = diagnose_integrity(ROOT, MANIFEST_PATH)
    else:
        result = restore_verified_data_backups(ROOT)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
