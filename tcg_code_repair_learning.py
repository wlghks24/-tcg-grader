#!/usr/bin/env python3
"""TCG-wide bounded learning for code-and-test repair candidates.

Recurring runtime/collector failures are converted into structured repair
candidates. Learned/error text is never executed, Python/JS/HTML source is never
rewritten here, git is never written here, and unverified collected data is never
promoted. Learning only ranks code-defined diagnostic playbooks and verification
checks.

v2 hardening keeps learning safe under repeated/concurrent observations:
- one signature can increase its occurrence count at most once per report run;
- an old signature is considered clean only when the whole file observation is
  successful and no different structural/code failure is active for that file;
- verified-fix regressions are remembered and reopened as high priority;
- a verified fix must satisfy the complete code-defined playbook, not an arbitrary
  subset supplied by a caller;
- load/modify/save transactions are serialized with the repository's cross-process
  learning lock so tablet/PC background jobs cannot overwrite each other's memory.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import tempfile
from pathlib import Path
from typing import Any

import auto_repair_engine
from safe_runtime import atomic_write_json, bounded_int, safe_read_text

ROOT = Path(__file__).resolve().parent
MEMORY = ROOT / "tcg_code_repair_learning.json"
CANDIDATES = ROOT / "tcg_code_repair_candidates.json"
REPORT = ROOT / "tcg_code_repair_report.json"
SCHEMA = 2
MAX_CANDIDATES = 200
MAX_HISTORY = 300
MAX_DETAILS_PER_RESULT = 40
MAX_RESULTS_PER_RUN = 100
CLEAN_RUNS_TO_OBSERVED_RESOLUTION = 2

PROCESS_SAFE_TRANSACTIONS = True
UNIQUE_SIGNATURE_OCCURRENCE_PER_RUN = True
WHOLE_FILE_CLEAN_REQUIRED = True
REQUIRED_VERIFICATION_CHECKS_ENFORCED = True

# These codes should not be handled by repeated network retries. They need a
# source/parser/config/code review plus regression verification.
CODE_REPAIR_CODES = {
    "INTERNAL_SYNTAX_ERROR",
    "INTERNAL_CODE_ERROR",
    "SOURCE_STRUCTURE_CHANGED",
    "DATA_SCHEMA_ERROR",
    "DATA_VALUE_ERROR",
    "FILE_MISSING",
    "FILE_PERMISSION_ERROR",
    "FILE_PATH_ERROR",
    "CONFIGURATION_ERROR",
    "DEPENDENCY_ERROR",
    "LINK_RUNTIME_ERROR",
    "VISION_MEASUREMENT_ERROR",
    "CAMERA_RUNTIME_ERROR",
    "SECURITY_POLICY_BLOCK",
}

# Data-output -> source files that are valid first places to inspect. Learning
# data can select among these labels but cannot add arbitrary paths or commands.
REPAIR_TARGETS: dict[str, list[str]] = {
    "releases.json": ["update_releases.py", "release_parser_learning.py"],
    "market_watch.json": ["update_market_watch.py"],
    "market_prices.json": ["update_market_prices.py"],
    "promo_events.json": ["update_promo_events.py", "event_gap_learning.py"],
    "purchase_sources.json": ["update_purchase_sources.py", "validate_external_links.py"],
    "exchange_rates.json": ["update_exchange_rates.py"],
    "graded_photo_candidates.json": ["graded_photo_multi_source.py", "grading_cert_verifier.py"],
    "__integration__": ["auto_pipeline_runner.py", "multi_channel_agent.py"],
    "__link_audit__": ["validate_external_links.py", "update_purchase_sources.py"],
}

# IDs only. No command line is ever loaded from learning JSON.
VERIFICATION_CHECKS: dict[str, str] = {
    "python_compile": "변경 Python 파일 py_compile 통과",
    "collector_smoke": "해당 수집기 단독 실행 후 출력 JSON 스키마 검증",
    "last_good_preserved": "실패 시 .tcg_last_good 정상본 보존 확인",
    "no_collection_errors": "수집 결과 collection_errors가 비어 있는지 확인",
    "runtime_bundle_guard": "런타임 번들/필수파일 호환성 검사 통과",
    "link_guard": "외부 링크 검사에서 미보정 영구 오류가 증가하지 않음",
    "security_guard": "SSRF/Origin/Host/경로 등 기존 보안 정책을 약화하지 않음",
    "vision_regression": "정상/불량 교차샘플에서 측정 회귀가 없는지 확인",
    "camera_fallback": "카메라 실패 시 파일 업로드/수동 등록 경로 유지",
    "graphify_map_review": "Graphify 코드 지도에서 호출/의존 영향범위 확인",
}

PLAYBOOKS: dict[str, dict[str, Any]] = {
    "INTERNAL_SYNTAX_ERROR": {
        "label": "문법 오류 격리 후 컴파일·회귀검사",
        "checks": ["graphify_map_review", "python_compile", "runtime_bundle_guard"],
    },
    "INTERNAL_CODE_ERROR": {
        "label": "예외 발생 심볼/호출경로 확인 후 최소 수정",
        "checks": ["graphify_map_review", "python_compile", "collector_smoke", "runtime_bundle_guard"],
    },
    "SOURCE_STRUCTURE_CHANGED": {
        "label": "원출처 구조변경 확인 후 검증된 파서 어댑터 수정",
        "checks": ["graphify_map_review", "collector_smoke", "no_collection_errors", "last_good_preserved"],
    },
    "DATA_SCHEMA_ERROR": {
        "label": "writer/reader 스키마 계약 교차검증 후 정상본 보존",
        "checks": ["graphify_map_review", "collector_smoke", "last_good_preserved", "runtime_bundle_guard"],
    },
    "DATA_VALUE_ERROR": {
        "label": "비정상 값 입력경로와 범위검증 수정",
        "checks": ["collector_smoke", "last_good_preserved", "runtime_bundle_guard"],
    },
    "FILE_MISSING": {
        "label": "필수파일 배포/번들 누락 원인 확인; 임의 파일 생성 금지",
        "checks": ["graphify_map_review", "runtime_bundle_guard"],
    },
    "FILE_PERMISSION_ERROR": {
        "label": "저장경로/잠금 상태 확인; 자동 chmod 확대 금지",
        "checks": ["last_good_preserved", "runtime_bundle_guard", "security_guard"],
    },
    "FILE_PATH_ERROR": {
        "label": "플랫폼 경로/원자교체 조건 확인",
        "checks": ["runtime_bundle_guard", "last_good_preserved", "security_guard"],
    },
    "CONFIGURATION_ERROR": {
        "label": "설정 계약과 안전 기본값 확인",
        "checks": ["runtime_bundle_guard", "security_guard"],
    },
    "DEPENDENCY_ERROR": {
        "label": "Python/패키지/Termux 호환 버전 확인",
        "checks": ["python_compile", "runtime_bundle_guard"],
    },
    "LINK_RUNTIME_ERROR": {
        "label": "UI 링크/정적자원/API 연결 계약 점검",
        "checks": ["graphify_map_review", "link_guard", "security_guard"],
    },
    "VISION_MEASUREMENT_ERROR": {
        "label": "측정 입력·보더·표면검출 경로 교차검증",
        "checks": ["graphify_map_review", "vision_regression", "runtime_bundle_guard"],
    },
    "CAMERA_RUNTIME_ERROR": {
        "label": "카메라 권한/스트림/앞뒤면 전환과 fallback 확인",
        "checks": ["graphify_map_review", "camera_fallback", "security_guard"],
    },
    "SECURITY_POLICY_BLOCK": {
        "label": "보안 차단 원인 확인; 우회 대신 안전 입력/출처 수정",
        "checks": ["security_guard", "runtime_bundle_guard"],
    },
}

DEFAULT_PLAYBOOK = {
    "label": "원인분류 후 코드·테스트 검토",
    "checks": ["graphify_map_review", "runtime_bundle_guard"],
}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _safe_int(value: Any, default: int = 0, maximum: int = 1_000_000) -> int:
    return bounded_int(value, default, 0, maximum)


def _default_memory() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "updated_at": None,
        "runs": 0,
        "signatures": {},
        "history": [],
        "safety": {
            "learned_text_executable": False,
            "source_rewrite": False,
            "git_write": False,
            "unverified_data_promotion": False,
            "allowlisted_playbooks_only": True,
            "process_safe_transactions": True,
            "verified_fix_requires_full_playbook": True,
            "whole_file_clean_resolution": True,
            "one_signature_occurrence_per_run": True,
        },
    }


def safety_contract_status() -> dict[str, bool]:
    return {
        "process_safe_transactions": PROCESS_SAFE_TRANSACTIONS,
        "unique_signature_occurrence_per_run": UNIQUE_SIGNATURE_OCCURRENCE_PER_RUN,
        "whole_file_clean_required": WHOLE_FILE_CLEAN_REQUIRED,
        "verified_fix_requires_full_playbook": REQUIRED_VERIFICATION_CHECKS_ENFORCED,
    }


def _load_json(path: Path, default: dict[str, Any], max_bytes: int = 3_000_000) -> dict[str, Any]:
    try:
        value = json.loads(safe_read_text(path, max_bytes=max_bytes))
    except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        return default
    return value if isinstance(value, dict) else default


def _safe_verified_fix(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    fix_id = value.get("fix_id")
    if not isinstance(fix_id, str) or not fix_id or len(fix_id) > 120 or re.search(r"[\x00-\x1f\x7f]", fix_id):
        return None
    check_ids = [
        str(x) for x in (value.get("verification_check_ids") or [])
        if isinstance(x, str) and x in VERIFICATION_CHECKS
    ]
    return {
        "fix_id": fix_id,
        "verified_at": value.get("verified_at") if isinstance(value.get("verified_at"), str) else None,
        "verification_check_ids": list(dict.fromkeys(check_ids)),
        "verification_checks": [VERIFICATION_CHECKS[x] for x in dict.fromkeys(check_ids)],
    }


def _load_memory(path: Path = MEMORY) -> dict[str, Any]:
    raw = _load_json(path, _default_memory())
    clean = _default_memory()
    clean["runs"] = _safe_int(raw.get("runs"))
    clean["updated_at"] = raw.get("updated_at") if isinstance(raw.get("updated_at"), str) else None
    signatures = raw.get("signatures") if isinstance(raw.get("signatures"), dict) else {}
    ranked = [
        (signature, row) for signature, row in signatures.items()
        if isinstance(signature, str) and len(signature) == 20 and isinstance(row, dict)
    ]
    ranked.sort(key=lambda item: (str(item[1].get("last_seen") or ""), item[0]))
    for signature, row in ranked[-MAX_CANDIDATES:]:
        clean["signatures"][signature] = {
            "file": str(row.get("file") or "unknown")[:160],
            "code": str(row.get("code") or "UNCLASSIFIED_ERROR")[:100],
            "subtype": str(row.get("subtype") or "general")[:120],
            "occurrences": _safe_int(row.get("occurrences")),
            "clean_runs": _safe_int(row.get("clean_runs"), 0, 1000),
            "first_seen": row.get("first_seen") if isinstance(row.get("first_seen"), str) else None,
            "last_seen": row.get("last_seen") if isinstance(row.get("last_seen"), str) else None,
            "last_outcome": row.get("last_outcome") if row.get("last_outcome") in {"error", "clean", "verified"} else "error",
            "verified_fix_count": _safe_int(row.get("verified_fix_count"), 0, 1000),
            "verified_regression_count": _safe_int(row.get("verified_regression_count"), 0, 1000),
            "last_verified_fix": _safe_verified_fix(row.get("last_verified_fix")),
        }
    clean["history"] = [x for x in (raw.get("history") or [])[-MAX_HISTORY:] if isinstance(x, dict)]
    return clean


def _safe_filename(value: Any) -> str:
    text = auto_repair_engine.redact_sensitive(value or "unknown", 180).replace("\\", "/")
    if text in {"__integration__", "__link_audit__"}:
        return text
    name = Path(text).name
    return name if name and name not in {".", ".."} else "unknown"


def _details(result: dict[str, Any]) -> list[str]:
    """Return only errors that are still active for this observation.

    A recovered collector may retain historical ``collection_errors`` for
    diagnostics while publishing an explicit empty ``remaining_collection_errors``.
    When the remaining-errors key exists it is authoritative. A stale top-level
    error on a successful result is ignored.
    """
    values: list[Any] = []
    keys = ("remaining_collection_errors",) if "remaining_collection_errors" in result else ("collection_errors",)
    for key in keys:
        raw = result.get(key)
        if isinstance(raw, (list, tuple)):
            values.extend(list(raw)[:MAX_DETAILS_PER_RESULT])
        elif raw:
            values.append(raw)
    if result.get("error") and not bool(result.get("ok")):
        values.append(result["error"])
    out: list[str] = []
    for value in values[:MAX_DETAILS_PER_RESULT]:
        text = auto_repair_engine.redact_sensitive(value, 1200).strip()
        if text and text not in out:
            out.append(text)
    return out


def _signature(filename: str, analysis: dict[str, Any]) -> str:
    raw = f"{filename}|{analysis.get('code')}|{analysis.get('error_subtype')}"
    return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:20]


def _required_check_ids(code: str) -> tuple[str, ...]:
    playbook = PLAYBOOKS.get(str(code), DEFAULT_PLAYBOOK)
    return tuple(x for x in playbook.get("checks", []) if x in VERIFICATION_CHECKS)


def _candidate_for(filename: str, signature: str, analysis: dict[str, Any], detail: str,
                   occurrence: int, first_seen: str | None, last_seen: str,
                   *, regression_after_verified_fix: bool = False) -> dict[str, Any]:
    code = str(analysis.get("code") or "UNCLASSIFIED_ERROR")
    playbook = PLAYBOOKS.get(code, DEFAULT_PLAYBOOK)
    targets = list(REPAIR_TARGETS.get(filename, []))
    checks = list(_required_check_ids(code))
    return {
        "signature": signature,
        "file": filename,
        "error_code": code,
        "error_subtype": analysis.get("error_subtype"),
        "category": analysis.get("category"),
        "http_status": analysis.get("http_status"),
        "occurrences": occurrence,
        "first_seen": first_seen or last_seen,
        "last_seen": last_seen,
        "status": "repeated_needs_code_and_test_repair" if occurrence >= 2 else "needs_code_and_test_repair",
        "priority": "high" if occurrence >= 2 or regression_after_verified_fix else "normal",
        "probable_cause": analysis.get("probable_cause"),
        "safe_action": analysis.get("safe_action"),
        "repair_playbook": playbook["label"],
        "repair_targets": targets,
        "verification_check_ids": checks,
        "verification_checks": [VERIFICATION_CHECKS[x] for x in checks],
        "sample_detail": auto_repair_engine.redact_sensitive(detail, 700),
        "graphify_first": bool(targets),
        "source_auto_rewrite_allowed": False,
        "requires_verified_tests_before_release": True,
        "regression_after_verified_fix": bool(regression_after_verified_fix),
    }


def _safe_candidate_item(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    signature = raw.get("signature")
    if not isinstance(signature, str) or len(signature) != 20:
        return None
    filename = _safe_filename(raw.get("file"))
    code = str(raw.get("error_code") or "UNCLASSIFIED_ERROR")[:100]
    allowed_status = {
        "needs_code_and_test_repair", "repeated_needs_code_and_test_repair",
        "observed_resolved", "verified_fixed",
    }
    checks = [x for x in (raw.get("verification_check_ids") or []) if isinstance(x, str) and x in VERIFICATION_CHECKS]
    safe = {
        "signature": signature,
        "file": filename,
        "error_code": code,
        "error_subtype": str(raw.get("error_subtype") or "general")[:120],
        "category": str(raw.get("category") or "")[:120],
        "http_status": raw.get("http_status") if isinstance(raw.get("http_status"), int) else None,
        "occurrences": _safe_int(raw.get("occurrences")),
        "first_seen": raw.get("first_seen") if isinstance(raw.get("first_seen"), str) else None,
        "last_seen": raw.get("last_seen") if isinstance(raw.get("last_seen"), str) else None,
        "status": raw.get("status") if raw.get("status") in allowed_status else "needs_code_and_test_repair",
        "priority": "high" if raw.get("priority") == "high" else "normal",
        "probable_cause": auto_repair_engine.redact_sensitive(raw.get("probable_cause") or "", 500),
        "safe_action": auto_repair_engine.redact_sensitive(raw.get("safe_action") or "", 500),
        "repair_playbook": str(raw.get("repair_playbook") or "")[:500],
        "repair_targets": [x for x in (raw.get("repair_targets") or []) if x in REPAIR_TARGETS.get(filename, [])],
        "verification_check_ids": list(dict.fromkeys(checks)),
        "verification_checks": [VERIFICATION_CHECKS[x] for x in dict.fromkeys(checks)],
        "sample_detail": auto_repair_engine.redact_sensitive(raw.get("sample_detail") or "", 700),
        "graphify_first": bool(raw.get("graphify_first")),
        "source_auto_rewrite_allowed": False,
        "requires_verified_tests_before_release": raw.get("requires_verified_tests_before_release") is not False,
        "regression_after_verified_fix": raw.get("regression_after_verified_fix") is True,
    }
    for field in ("resolved_at", "resolution_evidence"):
        if isinstance(raw.get(field), str):
            safe[field] = raw[field][:500]
    verified = _safe_verified_fix(raw.get("verified_fix"))
    previous = _safe_verified_fix(raw.get("previous_verified_fix"))
    if verified:
        safe["verified_fix"] = verified
    if previous:
        safe["previous_verified_fix"] = previous
    if isinstance(raw.get("verified_regression_count"), int):
        safe["verified_regression_count"] = _safe_int(raw.get("verified_regression_count"), 0, 1000)
    return safe


def _candidate_payload(path: Path = CANDIDATES) -> dict[str, Any]:
    raw = _load_json(path, {"schema": SCHEMA, "updated_at": None, "items": []})
    items = raw.get("items") if isinstance(raw.get("items"), list) else []
    clean_items = []
    for item in items[-MAX_CANDIDATES:]:
        safe = _safe_candidate_item(item)
        if safe is not None:
            clean_items.append(safe)
    return {"schema": SCHEMA, "updated_at": raw.get("updated_at"), "items": clean_items}


def _normalize_results(report: Any) -> list[dict[str, Any]]:
    if not isinstance(report, dict):
        return []
    raw_results = report.get("results")
    if not isinstance(raw_results, (list, tuple)):
        raw_results = []
    results = [x for x in list(raw_results)[:MAX_RESULTS_PER_RUN] if isinstance(x, dict)]
    for key, filename in (("integration", "__integration__"), ("link_audit", "__link_audit__")):
        aux = report.get(key)
        if isinstance(aux, dict) and (not aux.get("ok", False) or aux.get("degraded", False)):
            results.append({
                "file": filename,
                "ok": False,
                "error": aux.get("error") or aux.get("status") or aux.get("warning"),
            })
    return results[:MAX_RESULTS_PER_RUN + 2]


def observe(report: dict[str, Any], *, memory_path: Path = MEMORY,
            candidates_path: Path = CANDIDATES, report_path: Path = REPORT) -> dict[str, Any]:
    """Learn structural/code failures and build safe repair candidates.

    The memory file is the transaction lock key. Candidate/report files are written
    inside the same transaction, so concurrent tablet/PC jobs cannot lose updates.
    """
    try:
        with auto_repair_engine._memory_process_lock(Path(memory_path)):
            return _observe_locked(
                report,
                memory_path=Path(memory_path),
                candidates_path=Path(candidates_path),
                report_path=Path(report_path),
            )
    except (TimeoutError, OSError, ValueError) as exc:
        return {
            "ok": False,
            "error": auto_repair_engine.redact_sensitive(f"{type(exc).__name__}: code-repair learning transaction unavailable", 300),
            "safety": _default_memory()["safety"],
        }


def _observe_locked(report: Any, *, memory_path: Path, candidates_path: Path,
                    report_path: Path) -> dict[str, Any]:
    memory = _load_memory(memory_path)
    candidates = _candidate_payload(candidates_path)
    by_signature = {str(x.get("signature")): dict(x) for x in candidates["items"] if x.get("signature")}
    now = _now()
    memory["runs"] = min(1_000_000, _safe_int(memory.get("runs")) + 1)

    signatures_seen: set[str] = set()
    file_state: dict[str, dict[str, bool]] = {}
    new_count = repeated_count = resolved_count = regression_count = duplicate_suppressed = 0

    for result in _normalize_results(report):
        filename = _safe_filename(result.get("file"))
        state = file_state.setdefault(filename, {"all_ok": True, "has_relevant": False})
        if not bool(result.get("ok")):
            state["all_ok"] = False

        for detail in _details(result):
            analysis = auto_repair_engine.analyze_error(detail)
            code = str(analysis.get("code") or "")
            if code not in CODE_REPAIR_CODES:
                continue
            state["has_relevant"] = True
            signature = _signature(filename, analysis)
            if signature in signatures_seen:
                duplicate_suppressed += 1
                continue
            signatures_seen.add(signature)

            signatures = memory.setdefault("signatures", {})
            existed_before = signature in signatures
            stat = signatures.setdefault(signature, {
                "file": filename,
                "code": code,
                "subtype": str(analysis.get("error_subtype") or "general"),
                "occurrences": 0,
                "clean_runs": 0,
                "first_seen": now,
                "last_seen": now,
                "last_outcome": "error",
                "verified_fix_count": 0,
                "verified_regression_count": 0,
                "last_verified_fix": None,
            })

            previous_verified = _safe_verified_fix(stat.get("last_verified_fix"))
            old_candidate = by_signature.get(signature)
            if previous_verified is None and isinstance(old_candidate, dict):
                previous_verified = _safe_verified_fix(old_candidate.get("verified_fix"))
            # Count one verified-fix regression episode when the candidate
            # transitions out of verified_fixed. Repeated observations while that
            # regression remains unresolved keep high priority, but do not inflate
            # the regression counter as if multiple independent fixes had failed.
            regression_episode = bool(
                stat.get("last_outcome") == "verified"
                or (isinstance(old_candidate, dict) and old_candidate.get("status") == "verified_fixed")
            )
            regression_active = bool(
                regression_episode
                or (isinstance(old_candidate, dict) and old_candidate.get("regression_after_verified_fix") is True)
            )
            if regression_episode:
                stat["verified_regression_count"] = min(
                    1000, _safe_int(stat.get("verified_regression_count"), 0, 1000) + 1
                )
                regression_count += 1

            stat["occurrences"] = min(1_000_000, _safe_int(stat.get("occurrences")) + 1)
            stat["clean_runs"] = 0
            stat["last_seen"] = now
            stat["last_outcome"] = "error"
            candidate = _candidate_for(
                filename,
                signature,
                analysis,
                detail,
                stat["occurrences"],
                stat.get("first_seen"),
                now,
                regression_after_verified_fix=regression_active,
            )
            if previous_verified:
                candidate["previous_verified_fix"] = previous_verified
                candidate["verified_regression_count"] = stat["verified_regression_count"]
            if existed_before:
                repeated_count += 1
            else:
                new_count += 1
            by_signature[signature] = candidate
            memory.setdefault("history", []).append({
                "at": now,
                "signature": signature,
                "file": filename,
                "code": code,
                "outcome": "regression" if regression_episode else "error",
                "occurrences": stat["occurrences"],
            })

    # A clean run is evidence only when every observation for that file succeeded
    # and there was no different structural/code candidate in the same report.
    for filename, state in file_state.items():
        if not state.get("all_ok") or state.get("has_relevant"):
            continue
        for signature, stat in memory.get("signatures", {}).items():
            if stat.get("file") != filename or stat.get("last_outcome") == "verified":
                continue
            if signature in signatures_seen:
                continue
            stat["clean_runs"] = min(1000, _safe_int(stat.get("clean_runs")) + 1)
            stat["last_outcome"] = "clean"
            if stat["clean_runs"] >= CLEAN_RUNS_TO_OBSERVED_RESOLUTION and signature in by_signature:
                item = by_signature[signature]
                if item.get("status") not in {"verified_fixed", "observed_resolved"}:
                    item["status"] = "observed_resolved"
                    item["resolved_at"] = now
                    item["resolution_evidence"] = f"{stat['clean_runs']} consecutive whole-file clean observations"
                    item["requires_verified_tests_before_release"] = True
                    resolved_count += 1

    memory["history"] = memory.get("history", [])[-MAX_HISTORY:]
    if len(memory.get("signatures", {})) > MAX_CANDIDATES:
        ranked = sorted(
            memory["signatures"].items(),
            key=lambda kv: (str(kv[1].get("last_seen") or ""), kv[0]),
        )[-MAX_CANDIDATES:]
        memory["signatures"] = dict(ranked)
    memory["updated_at"] = now

    candidate_items = sorted(
        by_signature.values(),
        key=lambda x: (str(x.get("last_seen") or ""), str(x.get("signature") or "")),
    )[-MAX_CANDIDATES:]
    candidate_payload = {"schema": SCHEMA, "updated_at": now, "items": candidate_items}
    atomic_write_json(memory_path, memory, suffix=".code-repair-learning.tmp")
    atomic_write_json(candidates_path, candidate_payload, suffix=".code-repair-candidates.tmp")

    summary = {
        "ok": True,
        "runs": memory["runs"],
        "new_candidates": new_count,
        "repeated_candidates": repeated_count,
        "verified_fix_regressions": regression_count,
        "duplicate_signatures_suppressed": duplicate_suppressed,
        "observed_resolved": resolved_count,
        "open_candidates": sum(
            x.get("status") in {"needs_code_and_test_repair", "repeated_needs_code_and_test_repair"}
            for x in candidate_items
        ),
        "verified_fixed": sum(x.get("status") == "verified_fixed" for x in candidate_items),
        "safety": memory["safety"],
    }
    atomic_write_json(
        report_path,
        {"schema": SCHEMA, "updated_at": now, **summary},
        suffix=".code-repair-report.tmp",
    )
    return summary


def register_verified_fix(signature: str, fix_id: str, check_ids: list[str], *,
                          memory_path: Path = MEMORY, candidates_path: Path = CANDIDATES) -> dict[str, Any]:
    """Record a human/CI verified fix only after its full playbook passed."""
    with auto_repair_engine._memory_process_lock(Path(memory_path)):
        return _register_verified_fix_locked(
            signature,
            fix_id,
            check_ids,
            memory_path=Path(memory_path),
            candidates_path=Path(candidates_path),
        )


def _register_verified_fix_locked(signature: str, fix_id: str, check_ids: list[str], *,
                                  memory_path: Path, candidates_path: Path) -> dict[str, Any]:
    if not isinstance(signature, str) or len(signature) != 20:
        raise ValueError("invalid signature")
    if (
        not isinstance(fix_id, str)
        or not fix_id.strip()
        or len(fix_id) > 120
        or re.search(r"[\x00-\x1f\x7f]", fix_id)
    ):
        raise ValueError("invalid fix_id")
    if not isinstance(check_ids, list) or not check_ids:
        raise ValueError("verification check IDs are required")
    if any(not isinstance(check, str) or check not in VERIFICATION_CHECKS for check in check_ids):
        raise ValueError("only allow-listed verification check IDs are accepted")
    provided = list(dict.fromkeys(check_ids))

    memory = _load_memory(memory_path)
    candidates = _candidate_payload(candidates_path)
    item = next((x for x in candidates["items"] if x.get("signature") == signature), None)
    stat = memory.get("signatures", {}).get(signature)
    if not isinstance(item, dict) or not isinstance(stat, dict):
        raise KeyError("unknown repair signature")

    required = list(_required_check_ids(str(stat.get("code") or item.get("error_code") or "")))
    missing = [check for check in required if check not in provided]
    if missing:
        raise ValueError("missing required verification checks: " + ", ".join(missing))

    existing = _safe_verified_fix(item.get("verified_fix"))
    if existing and existing.get("fix_id") == fix_id and set(existing.get("verification_check_ids") or ()) == set(provided):
        return existing

    now = _now()
    verified = {
        "fix_id": fix_id.strip(),
        "verified_at": now,
        "verification_check_ids": provided,
        "verification_checks": [VERIFICATION_CHECKS[x] for x in provided],
    }
    item["status"] = "verified_fixed"
    item["verified_fix"] = verified
    item["resolved_at"] = now
    item["requires_verified_tests_before_release"] = False
    item["regression_after_verified_fix"] = False
    stat["last_outcome"] = "verified"
    stat["clean_runs"] = 0
    stat["verified_fix_count"] = min(1000, _safe_int(stat.get("verified_fix_count")) + 1)
    stat["last_verified_fix"] = verified
    memory.setdefault("history", []).append({
        "at": now, "signature": signature, "outcome": "verified", "fix_id": fix_id.strip()
    })
    memory["history"] = memory["history"][-MAX_HISTORY:]
    memory["updated_at"] = now
    candidates["updated_at"] = now
    atomic_write_json(memory_path, memory, suffix=".verified-fix.tmp")
    atomic_write_json(candidates_path, candidates, suffix=".verified-candidate.tmp")
    return verified


def public_status(*, memory_path: Path = MEMORY, candidates_path: Path = CANDIDATES) -> dict[str, Any]:
    memory = _load_memory(memory_path)
    candidates = _candidate_payload(candidates_path)
    open_items = [
        x for x in candidates["items"]
        if x.get("status") in {"needs_code_and_test_repair", "repeated_needs_code_and_test_repair"}
    ]
    return {
        "ok": True,
        "runs": memory.get("runs", 0),
        "open_count": len(open_items),
        "high_priority_count": sum(x.get("priority") == "high" for x in open_items),
        "verified_regression_count": sum(_safe_int(x.get("verified_regression_count"), 0, 1000) for x in open_items),
        "recent_open": open_items[-10:],
        "safety": memory.get("safety", {}),
    }


def self_test() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        memory = root / "memory.json"
        candidates = root / "candidates.json"
        report_path = root / "report.json"
        broken_row = {
            "file": "releases.json",
            "ok": False,
            "error": "NameError: name 'parse_release_card' is not defined",
            "collection_errors": ["NameError: name 'parse_release_card' is not defined"],
        }
        broken = {"results": [broken_row]}
        first = observe(broken, memory_path=memory, candidates_path=candidates, report_path=report_path)
        assert first["open_candidates"] == 1
        payload = json.loads(candidates.read_text(encoding="utf-8"))
        item = payload["items"][0]
        assert item["error_code"] == "INTERNAL_CODE_ERROR"
        assert item["source_auto_rewrite_allowed"] is False
        assert "graphify_map_review" in item["verification_check_ids"]
        signature = item["signature"]

        # A clean row earlier in the same report must not advance a different old
        # signature when this file later reports a structural/code error.
        memory_payload = json.loads(memory.read_text(encoding="utf-8"))
        synthetic_signature = "f" * 20
        memory_payload["signatures"][synthetic_signature] = {
            "file": "releases.json",
            "code": "DATA_SCHEMA_ERROR",
            "subtype": "synthetic",
            "occurrences": 1,
            "clean_runs": 0,
            "first_seen": _now(),
            "last_seen": _now(),
            "last_outcome": "error",
            "verified_fix_count": 0,
            "verified_regression_count": 0,
            "last_verified_fix": None,
        }
        memory.write_text(json.dumps(memory_payload), encoding="utf-8")
        mixed = {
            "results": [
                {"file": "releases.json", "ok": True, "remaining_collection_errors": []},
                broken_row,
            ]
        }
        observe(mixed, memory_path=memory, candidates_path=candidates, report_path=report_path)
        memory_payload = json.loads(memory.read_text(encoding="utf-8"))
        assert memory_payload["signatures"][synthetic_signature]["clean_runs"] == 0

        # Duplicate rows from one report are one observation, not artificial
        # recurrence. The occurrence count must rise by exactly one.
        before = memory_payload["signatures"][signature]["occurrences"]
        duplicate = {"results": [dict(broken_row), dict(broken_row)]}
        duplicate_result = observe(
            duplicate, memory_path=memory, candidates_path=candidates, report_path=report_path
        )
        memory_payload = json.loads(memory.read_text(encoding="utf-8"))
        assert memory_payload["signatures"][signature]["occurrences"] == before + 1
        assert duplicate_result["duplicate_signatures_suppressed"] >= 1

        # A successful recovery can retain historical diagnostics. The explicit
        # empty remaining list must win, otherwise candidates reopen forever.
        clean = {"results": [{
            "file": "releases.json", "ok": True,
            "collection_errors": ["NameError: name 'parse_release_card' is not defined"],
            "remaining_collection_errors": [],
            "error": "NameError: name 'parse_release_card' is not defined",
        }]}
        observe(clean, memory_path=memory, candidates_path=candidates, report_path=report_path)
        observe(clean, memory_path=memory, candidates_path=candidates, report_path=report_path)
        payload = json.loads(candidates.read_text(encoding="utf-8"))
        item = next(x for x in payload["items"] if x["signature"] == signature)
        assert item["status"] == "observed_resolved"
        assert item["requires_verified_tests_before_release"] is True

        # Partial verification must not close a candidate.
        try:
            register_verified_fix(
                signature,
                "partial-fix",
                ["python_compile", "runtime_bundle_guard"],
                memory_path=memory,
                candidates_path=candidates,
            )
        except ValueError as exc:
            assert "missing required verification checks" in str(exc)
        else:
            raise AssertionError("partial playbook verification must be rejected")

        required = list(_required_check_ids("INTERNAL_CODE_ERROR"))
        verified = register_verified_fix(
            signature,
            "test-fix-001",
            required,
            memory_path=memory,
            candidates_path=candidates,
        )
        assert verified["fix_id"] == "test-fix-001"
        # Re-registering the exact same proof is idempotent.
        verified_again = register_verified_fix(
            signature,
            "test-fix-001",
            required,
            memory_path=memory,
            candidates_path=candidates,
        )
        assert verified_again == verified
        payload = json.loads(candidates.read_text(encoding="utf-8"))
        item = next(x for x in payload["items"] if x["signature"] == signature)
        assert item["status"] == "verified_fixed"

        # If the same verified error returns, reopen it and remember the regression
        # instead of silently trusting the old fix forever.
        regressed = observe(broken, memory_path=memory, candidates_path=candidates, report_path=report_path)
        assert regressed["verified_fix_regressions"] == 1
        payload = json.loads(candidates.read_text(encoding="utf-8"))
        item = next(x for x in payload["items"] if x["signature"] == signature)
        assert item["status"] == "repeated_needs_code_and_test_repair"
        assert item["priority"] == "high"
        assert item["regression_after_verified_fix"] is True
        assert item.get("previous_verified_fix", {}).get("fix_id") == "test-fix-001"

        # More failures before a new verified fix are the same unresolved
        # regression episode, not additional verified-fix regressions.
        same_episode = observe(broken, memory_path=memory, candidates_path=candidates, report_path=report_path)
        assert same_episode["verified_fix_regressions"] == 0
        payload = json.loads(candidates.read_text(encoding="utf-8"))
        item = next(x for x in payload["items"] if x["signature"] == signature)
        assert item["verified_regression_count"] == 1
        assert item["regression_after_verified_fix"] is True
        assert item["priority"] == "high"

        try:
            register_verified_fix(
                signature, "bad", ["rm_everything"],
                memory_path=memory, candidates_path=candidates,
            )
        except ValueError:
            pass
        else:
            raise AssertionError("unapproved verification ID must be rejected")

        # Transaction lock must be cleaned up after successful operations.
        assert not memory.with_suffix(memory.suffix + ".lock").exists()
        assert safety_contract_status() == {
            "process_safe_transactions": True,
            "unique_signature_occurrence_per_run": True,
            "whole_file_clean_required": True,
            "verified_fix_requires_full_playbook": True,
        }
    print("TCG code-repair bounded-learning self-test: OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.status:
        print(json.dumps(public_status(), ensure_ascii=False, indent=2))
        return 0
    parser.error("use --self-test or --status")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())