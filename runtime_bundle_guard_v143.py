#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v143 semantic compatibility guard for the tablet/PC updater bundle.

The updater is intentionally split across many modules. Updating only the newest
wrapper can leave an older collector or recovery engine on a tablet, which makes
already-fixed bugs reappear (repeated DDG timeouts, generic ValueError diagnosis,
or graded-photo preflight rejection). This guard verifies *behavioral contracts*
rather than trusting filenames or a single version string.

No network request is made here and no learned JSON is modified.
"""
from __future__ import annotations

import importlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PATCH_ID = 143

REQUIRED_FILES = (
    "safe_runtime.py",
    "auto_repair_engine.py",
    "auto_update_all.py",
    "tcg_updater.py",
    "tcg_updater_v135.py",
    "update_releases.py",
    "release_history_backfill.py",
    "update_market_watch.py",
    "update_market_prices.py",
    "market_public_crosscheck.py",
    "update_promo_events.py",
    "update_purchase_sources.py",
    "update_exchange_rates.py",
    "graded_photo_multi_source.py",
    "graded_photo_evidence.py",
    "detailed_collection_intelligence.py",
    "grading_cert_verifier.py",
    "multi_channel_agent.py",
    "search_method_learning.py",
    "adaptive_collection_learner.py",
    "collection_learning_hardening_v142.py",
    "event_priority_watch.py",
    "event_quick_watch.py",
    # Manual graded-photo / official-site fallback must travel with the wrapper.
    "manual_graded_photo_registration.py",
    "manual_official_proof.py",
    "manual_official_verify_bridge.js",
    "graded_photo_dashboard.js",
    "vision_calibration.py",
    "library_slab_corpus.py",
    "IMPORT_GRADED_LEARNING_FILES.py",
    "START_GRADED_FILE_LEARNING.sh",
)

EXPECTED_JOB_FILES = {
    "releases.json",
    "market_watch.json",
    "market_prices.json",
    "promo_events.json",
    "purchase_sources.json",
    "exchange_rates.json",
    "graded_photo_candidates.json",
}

MANUAL_REQUIRED = {
    "manual_graded_photo_registration.py",
    "manual_official_proof.py",
    "manual_official_verify_bridge.js",
    "graded_photo_dashboard.js",
}


def _regular_file(name: str) -> bool:
    path = ROOT / name
    try:
        return path.is_file() and not path.is_symlink()
    except OSError:
        return False


def _load(name: str):
    return importlib.import_module(name)


def audit() -> dict:
    issues: list[str] = []
    missing = [name for name in REQUIRED_FILES if not _regular_file(name)]
    if missing:
        issues.append("필수 런타임 파일 누락: " + ", ".join(missing[:12]))

    modules = {}
    for name in (
        "safe_runtime",
        "auto_repair_engine",
        "auto_update_all",
        "update_promo_events",
        "graded_photo_multi_source",
        "multi_channel_agent",
        "search_method_learning",
        "collection_learning_hardening_v142",
        "manual_official_proof",
    ):
        try:
            modules[name] = _load(name)
        except Exception as exc:  # import compatibility is exactly what this audit checks
            issues.append(f"{name} 불러오기 실패: {type(exc).__name__}")

    safe = modules.get("safe_runtime")
    if safe is not None:
        try:
            detail = safe.diagnostic_exception(ValueError("v143-probe-detail"))
            if "v143-probe-detail" not in str(detail):
                issues.append("safe_runtime 진단 상세 보존 기능이 구버전입니다")
        except Exception:
            issues.append("safe_runtime 진단 예외 처리 계약이 맞지 않습니다")

    repair = modules.get("auto_repair_engine")
    if repair is not None:
        if "graded_photo_candidates.json" not in getattr(repair, "SAFE_JSON_FILES", set()):
            issues.append("등급사진 후보 JSON이 자동복구 안전목록에 없습니다")
        required = getattr(repair, "REQUIRED_JSON_FIELDS", {}).get("graded_photo_candidates.json", {})
        if required.get("records") is not list or required.get("summary") is not dict:
            issues.append("등급사진 후보 JSON 사전검증 계약이 구버전입니다")
        try:
            probe = repair.analyze_error("ValueError: 공식 페이지에서 검증 가능한 상품을 1건도 읽지 못함")
            if probe.get("code") != "SOURCE_STRUCTURE_CHANGED":
                issues.append("출처 구조변경이 DATA_VALUE_ERROR로 잘못 분류되는 구버전입니다")
        except Exception:
            issues.append("오류 원인 분류 엔진 계약 검사 실패")

    update_all = modules.get("auto_update_all")
    if update_all is not None:
        jobs = getattr(update_all, "JOBS", ())
        files = {row[2] for row in jobs if isinstance(row, tuple) and len(row) >= 3}
        if files != EXPECTED_JOB_FILES:
            issues.append("7개 정규 수집 작업 구성이 현재 번들과 맞지 않습니다")
        try:
            if update_all._should_retry({}, False, "ValueError: malformed data"):
                issues.append("결정적 ValueError가 네트워크 재시도로 잘못 처리됩니다")
        except Exception:
            issues.append("자동수집 재시도 정책 계약 검사 실패")

    promo = modules.get("update_promo_events")
    if promo is not None:
        try:
            keys = promo.social_topic_expected_keys()
            if len(keys) != 90:
                issues.append(f"행사 SNS 커버리지 셀이 {len(keys)}개로, 기대값 90과 다릅니다")
        except Exception:
            issues.append("행사 3게임×3국가×10주제 커버리지 계약이 구버전입니다")

    search = modules.get("multi_channel_agent")
    if search is not None and not callable(getattr(search.MultiChannelCollector, "search_exact", None)):
        issues.append("등급사진 공개검색용 학습형 search_exact/circuit-breaker 경로가 없습니다")

    method = modules.get("search_method_learning")
    if method is not None and int(getattr(method, "SCHEMA_VERSION", 0) or 0) < 2:
        issues.append("검색경로 timeout/403/429 cooldown 학습기가 구버전입니다")

    photo = modules.get("graded_photo_multi_source")
    if photo is not None:
        if getattr(photo, "SOURCE_ID_ALIASES", {}).get("ebay_public") != "ebay":
            issues.append("eBay 공개검색 학습 식별자 통합이 적용되지 않았습니다")
        if int(getattr(photo, "RUN_SOURCE_LIMIT", 999) or 999) > 6:
            issues.append("등급사진 1회 수집원 제한이 과도해 timeout 연쇄 위험이 있습니다")
        if not callable(getattr(photo, "_query_rows", None)):
            issues.append("등급사진 학습형 다중검색 경로가 없습니다")

    hardening = modules.get("collection_learning_hardening_v142")
    if hardening is not None:
        try:
            status = hardening.apply()
            if int(status.get("patch") or 0) < 142:
                issues.append("자료수집 자가학습 보안패치가 v142 미만입니다")
            if status.get("unique_evidence_host_counting") is not True:
                issues.append("고유 출처수 교차검증 보안이 비활성입니다")
            if float(status.get("unverified_payload_learning_weight", -1)) != 0.0:
                issues.append("미검증 후보의 지속학습 가중치가 0이 아닙니다")
        except Exception:
            issues.append("v142 자료수집 자가학습 보안 계약 검사 실패")

    manual = modules.get("manual_official_proof")
    if manual is not None:
        try:
            status = manual.public_status()
            policy = status.get("policy", {}) if isinstance(status, dict) else {}
            if policy.get("manual_screenshot_sets_official_result") is not False:
                issues.append("수동 공식확인 캡처가 공식검증 결과로 승격될 위험이 있습니다")
            if policy.get("manual_screenshot_trains_raw_grade_calibration") is not False:
                issues.append("수동 공식확인 캡처가 RAW 등급 보정학습에 섞일 위험이 있습니다")
            if policy.get("rejected_screenshot_bytes_retained") is not False:
                issues.append("수동 공식확인 불일치 캡처 원본이 불필요하게 보존됩니다")
            if policy.get("valid_proof_cannot_be_downgraded_by_later_bad_upload") is not True:
                issues.append("정상 수동 참고등록이 이후 불일치 업로드로 덮일 수 있습니다")
            if policy.get("proof_upload_rate_limited") is not True:
                issues.append("수동 공식확인 OCR 업로드 속도 제한이 없습니다")
        except Exception:
            issues.append("수동 공식확인 보안 계약 검사 실패")

    manual_missing = sorted(name for name in MANUAL_REQUIRED if name in missing)
    manual_issues = [
        item for item in issues
        if "수동 공식확인" in item or "manual_official_proof" in item
    ]

    return {
        "ok": not issues,
        "patch": PATCH_ID,
        "required_file_count": len(REQUIRED_FILES),
        "missing_file_count": len(missing),
        "missing_files": missing,
        "issue_count": len(issues),
        "issues": issues,
        "contracts": {
            "graded_photo_preflight_allowlisted": not any("등급사진 후보 JSON" in x for x in issues),
            "source_structure_classification": not any("출처 구조변경" in x for x in issues),
            "search_timeout_circuit_breaker": not any("search_exact" in x or "cooldown" in x for x in issues),
            "manual_official_fallback": not manual_missing and not manual_issues,
            "manual_proof_raw_calibration": False,
            "manual_proof_rejected_bytes_retained": False,
            "event_coverage_cells": 90,
            "unverified_learning_weight": 0.0,
        },
    }


def require_compatible() -> dict:
    result = audit()
    if not result["ok"]:
        raise RuntimeError("v143 런타임 번들 불일치: " + " / ".join(result["issues"][:6]))
    return result


if __name__ == "__main__":
    import json
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
