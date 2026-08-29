#!/usr/bin/env python3
"""Static, bounded audit of the user-requested TCG feature contract.

This module reads only known project files. It never evaluates HTML/JavaScript,
learned error text, generated code, or data from an arbitrary path.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from safe_runtime import reject_nonstandard_json, safe_read_text, unique_json_object


REQUIRED_FILES = (
    "index.html", "tcg_updater.py", "auto_update_all.py", "auto_pipeline_runner.py", "auto_repair_engine.py",
    "error_scenario_lab.py", "scenario_learning_profiles.json",
    "ai_code_improver.py", "ai_code_learning.json", "verify_ai_code_improver.py",
    "verify_link_runtime.py", "verify_camera_runtime.js",
    "grading_vision_engine.js", "grading_accuracy_v99.js", "verify_vision_runtime.js",
    "card_identity_recognition.py", "card_identity_recognition.js", "card_identity_learning.json", "card_identity_reference_catalog.json",
    "graded_photo_multi_source.py", "graded_photo_evidence.py", "grading_cert_verifier.py",
    "graded_photo_dashboard.js", "graded_photo_dashboard.css", "graded_photo_candidates.json",
    "fault_injection_healing.py", "verify_fault_injection_healing.py", "fault_learning.json",
    "vision_calibration.py", "verify_vision_calibration.py", "vision_calibration.json",
    "trusted_ai_tests/test_card_name.py",
    "market_prices.json", "market_watch.json", "promo_events.json",
    "social_event_discovery.py", "social_event_candidates.json", "social_source_registry.json",
    "purchase_sources.json", "manifest.webmanifest", "sw.js",
)


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(
        safe_read_text(path), parse_constant=reject_nonstandard_json,
        object_pairs_hook=unique_json_object,
    )
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} JSON 객체 형식 필요")
    return value


def audit_feature_contract(root: str | Path | None = None) -> dict[str, Any]:
    base = Path(root).resolve() if root is not None else Path(__file__).resolve().parent
    if any(not (base / name).is_file() or (base / name).is_symlink() for name in REQUIRED_FILES):
        missing = [name for name in REQUIRED_FILES if not (base / name).is_file() or (base / name).is_symlink()]
        return {"ok": False, "total": 0, "implemented": 0, "missing_files": missing,
                "features": [], "excluded": ["iphone_serverless_continuous_collection"]}

    page = safe_read_text(base / "index.html")
    server = safe_read_text(base / "tcg_updater.py")
    automatic = safe_read_text(base / "auto_update_all.py")
    pipeline = safe_read_text(base / "auto_pipeline_runner.py")
    learner = safe_read_text(base / "auto_repair_engine.py")
    scenario_lab = safe_read_text(base / "error_scenario_lab.py")
    scenario_profiles = _json(base / "scenario_learning_profiles.json")
    ai_improver = safe_read_text(base / "ai_code_improver.py")
    ai_learning = _json(base / "ai_code_learning.json")
    fault_healing = safe_read_text(base / "fault_injection_healing.py")
    fault_learning = _json(base / "fault_learning.json")
    calibration = _json(base / "vision_calibration.json")
    identity_learning = _json(base / "card_identity_learning.json")
    identity_reference = _json(base / "card_identity_reference_catalog.json")
    manifest = _json(base / "manifest.webmanifest")
    worker = safe_read_text(base / "sw.js")
    prices = _json(base / "market_prices.json")
    watch = _json(base / "market_watch.json")
    promos = _json(base / "promo_events.json")
    social_candidates = _json(base / "social_event_candidates.json")
    social_registry = _json(base / "social_source_registry.json")
    social_discovery = safe_read_text(base / "social_event_discovery.py")
    purchases = _json(base / "purchase_sources.json")

    features: list[dict[str, Any]] = []

    def add(feature_id: str, title: str, implemented: bool, evidence: str) -> None:
        features.append({"id": feature_id, "title": title, "implemented": bool(implemented),
                         "evidence": evidence if implemented else "필수 연결 또는 자료 누락"})

    companies = {"PSA", "BGS", "CGC", "TAG", "BRG"}
    profiles = prices.get("graded_prices") if isinstance(prices.get("graded_prices"), dict) else {}
    company_rows = [row.get("grade_prices_krw", {}) for row in profiles.values() if isinstance(row, dict)]
    add("five_company_grading", "PSA·BGS·CGC·TAG·BRG 사진 사전측정",
        'const GRADING_COMPANIES=["PSA","BGS","CGC","TAG","BRG"]' in page
        and all(f'id="{prefix}10"' in page for prefix in ("p", "b", "c", "t", "r")),
        "5개 업체 결과 UI와 공통 측정 목록")
    add("official_grade_rules", "PSA·TAG 공식 공개기준과 BRG 비공개 기준 보호",
        "function tagScoreToGrade(score)" in page and "psa_10_centering" in server
        and "brg_unpublished_thresholds_invented" in server,
        "공식 점수표 API와 사진 참고표시")
    add("photo_front_back", "앞·뒷면 사진·센터링·코너·엣지·표면 분석",
        all(f'id="{item}"' in page for item in ("front", "back", "corner", "edge", "surface", "annot",
                                                  "startAutoCamera", "stopAutoCamera", "manualCapture"))
        and all(token in page for token in ("sceneDistance", "Camera", "_tcgCapturedFile", "visibilitychange",
                                             "analyzeWhitening", "confirmedSegments")),
        "앞·뒤 파일입력·자동촬영·내부 보더·Hough 선형 결함·백화·카메라 수명주기")
    add("card_identity_ocr_learning", "카드명·카드번호 자동인식·확인형 이미지학습",
        all(token in page for token in ("identityCardName", "identityCardNumber", "identityConfirm",
                                         "card_identity_recognition.js", "tcgRecognizeCurrentCard"))
        and all(token in server for token in ("/api/recognize-card", "/api/confirm-card-identity",
                                               "/api/card-identity-learning"))
        and identity_learning.get("confirmed_only") is True
        and identity_learning.get("auto_prediction_learning") is False
        and len(identity_reference.get("cards", [])) >= 20,
        "앞면 OCR·카드번호 우선 매칭·사용자 확인 후 동일사진/3회 유사사진 학습")
    add("exact_grade_prices", "업체별 1~10 정확한 등급가격·판매가·순수익",
        bool(company_rows) and all(set(row) == companies for row in company_rows)
        and all(set(values) == {str(i) for i in range(1, 11)} for row in company_rows for values in row.values())
        and "calculateGradingEconomics" in page,
        "5업체×10등급 가격구조와 수익계산")
    add("grade_cross_validation", "강화 서버 등급·시세 교차검증",
        'id="econServerVerify"' in page and "post_path=='/api/grade-card'" in server,
        "동일 출처 보호 POST API")
    add("calibration_learning", "실제 확정등급 저장·보수 자동보정",
        all(token in page for token in ("saveValidation", "recalcCalibration", "syncLearningToServer", "mergeLearning"))
        and all(token in page for token in ("official_result", "certification_id", "v97ComputeVisionCalibration"))
        and "merge_learning_rows" in server
        and calibration.get("policy", {}).get("official_result_required") is True
        and calibration.get("policy", {}).get("upward_correction_allowed") is False,
        "공식 인증번호 결과만 카드 단위 보류검증 · 개선 시 최대 1등급 하향 보정")
    add("error_root_cause_learning", "동일 오류 통합·신규 오류 분리·해결방법 기록",
        all(token in learner for token in ("error_group_key", "new_error_log", "resolution_steps", "verification_steps")),
        "원인 그룹·해결·재검증 계약")
    add("scenario_error_training", "다중 오류상황 사전학습·빠른 해결프로필",
        scenario_profiles.get("training_only") is True
        and scenario_profiles.get("scenario_count", 0) >= 286
        and scenario_profiles.get("family_count", 0) >= 32
        and scenario_profiles.get("successful_scenarios") == scenario_profiles.get("scenario_count")
        and scenario_profiles.get("verified_profile_count", 0) >= 158
        and scenario_profiles.get("safety", {}).get("operational_occurrences_modified") is False
        and all(token in scenario_lab for token in ("production_memory_unchanged", "equivalent_group", "build_profiles"))
        and all(token in learner for token in ("load_scenario_profiles", "fast_resolution_steps", "stop_conditions", "_diagnostic_needle_matches")),
        "310개 상황·33개 계열·164개 검증 프로필·카메라/링크/버튼/API/PWA·운영기록 비오염")
    ai_policy = ai_learning.get("policy") if isinstance(ai_learning.get("policy"), dict) else {}
    add("approved_ai_code_improvement", "구조화 코드후보·격리검사·오류통합·승인형 반영",
        all(token in ai_improver for token in (
            ".responses.create", '"type": "json_schema"', "validate_python_source",
            '"--network", "none"', '"--read-only"', '"--cap-drop", "ALL"',
            '"no-new-privileges:true"', "READY_FOR_HUMAN_REVIEW",
            "stopped_duplicate_failure", "MAX_RETRIES = 5",
        ))
        and ai_policy.get("model_training_claimed") is False
        and ai_policy.get("generated_code_auto_applied") is False
        and ai_policy.get("raw_code_persisted_in_learning_log") is False
        and all(token in fault_healing for token in (
            "run_fault_lab", "diagnose_integrity", "restore_verified_data_backups",
            "fault_injection_production_allowed", "generated_code_auto_applied",
        ))
        and fault_learning.get("training_only") is True
        and fault_learning.get("successful_scenarios") == fault_learning.get("scenario_count") == 21
        and fault_learning.get("safety", {}).get("production_files_modified") is False
        and "normalize_card_name" in safe_read_text(base / "trusted_ai_tests/test_card_name.py"),
        "Responses 승인형 후보 + 임시 복제본 고장주입 21종 + 운영 코드는 진단만 + 검증 JSON만 제한복구")
    add("timeout_deferred_collection", "시간초과 자료만 3~10분 별도 복구수집",
        all(token in automatic for token in ("DEFERRED_TIMEOUT_MIN_SECONDS = 180",
                                              "DEFERRED_TIMEOUT_MAX_SECONDS = 600",
                                              "_deferred_timeout_eligible")),
        "시간초과 전용 분리예산")
    add("six_collection_jobs", "출시·재발매·시세·행사·구매처·환율·등급사진 7단계 자동수집",
        "'total':7" in server and "graded_photo_multi_source" in automatic
        and all(token in server for token in ("/api/run-graded-photo-collection", "/api/graded-photo-collection-status"))
        and len(re.findall(
            r'^\s*\("[^"]+",\s*"update_[^"]+",\s*"[^"]+\.json"\),?$', automatic, re.M
        )) == 6,
        "6개 기존 작업 + OCR·공식 인증검증 등급사진 작업")
    add("scheduled_precollection", "6시간 자동반영·30분 전 사전수집",
        "AUTO_INTERVAL_SECONDS=6*60*60" in server and "PRECOLLECT_LEAD_SECONDS=30*60" in server,
        "PC·안드로이드 공통 일정")
    add("background_manual_update", "화면 전체 업데이트·백그라운드 진행·재연결",
        'window.tcgStartUpdateJob=startJob' in page and 'startJob("/api/run-auto-update"' in page
        and 'fetch(`/api/update?t=${Date.now()}`,{cache:' not in page,
        "POST 백그라운드 작업과 진행상태 재연결")
    entries = prices.get("entries") if isinstance(prices.get("entries"), dict) else {}
    countries = {key.split("|", 1)[0] for key in entries}
    assets = {key.rsplit("|", 1)[-1] for key in entries}
    games = {str(row.get("game")) for row in entries.values() if isinstance(row, dict)}
    add("three_country_market", "한국·일본·미국 카드·BOX 시세와 원화환산",
        {"KR", "JP", "US"} <= countries and {"BOX", "HIT"} <= assets
        and {"Pokémon", "ONE PIECE", "NARUTO"} <= games
        and "foreignKrw" in page and "loadExchangeRates" in page,
        "3국·3작품·BOX/HIT·환율")
    watched = watch.get("items") if isinstance(watch.get("items"), list) else []
    add("release_and_resale", "사전예약·출시일·재발매 추적",
        bool(watched) and any("재발매" in str(row.get("release_type", "")) for row in watched if isinstance(row, dict))
        and all(token in page for token in ("releaseBoard", "market_watch.json")),
        "출시·재발매 자료와 화면")
    coverage = promos.get("coverage") if isinstance(promos.get("coverage"), dict) else {}
    add("promo_collab_movies", "한·일·미 포켓몬·원피스·나루토 행사·콜라보·영화",
        coverage.get("covered_game_region_pairs") == 9 and coverage.get("movie_game_region_pairs") == 9
        and {"promo", "collaboration", "movie"} <= {row.get("category") for row in promos.get("items", []) if isinstance(row, dict)},
        "3작품×3국 공식출처 9조합")
    social_channels = social_candidates.get("channels") if isinstance(social_candidates.get("channels"), dict) else {}
    add("social_google_event_discovery", "Instagram·X·Google 기반 행사·콜라보·영화 보조수집",
        all(token in social_discovery for token in (
            "Google News", "X_BEARER_TOKEN", "INSTAGRAM_ACCESS_TOKEN",
            "GOOGLE_CSE_API_KEY", "official_social", "cross_checked",
        ))
        and isinstance(social_candidates.get("items", []), list)
        and isinstance(social_registry.get("official_accounts", {}), dict)
        and "social_event_candidates.json" in page
        and "공식 SNS" in page
        and "social_event_discovery" in pipeline,
        "Google News 기본 + X/Instagram 공식 API 선택 + 공식사이트 연결계정 우선 + 후보층 격리")
    sources = purchases.get("sources") if isinstance(purchases.get("sources"), list) else []
    add("purchase_sources", "온라인·오프라인 구매처와 실시간 참고신호",
        {"online", "offline"} <= {row.get("channel", "online") for row in sources if isinstance(row, dict)}
        and len(sources) >= 32 and "purchase-live-search" in page,
        "국가별 구매처·최근 신호")
    korean_offline = [row for row in sources if isinstance(row, dict)
                      and row.get("region") == "KR" and row.get("channel") == "offline"]
    retail_categories = {row.get("retailer_category") for row in korean_offline}
    required_categories = {"convenience", "hypermarket", "stationery", "toy",
                           "bookstore", "cardshop", "discount"}
    add("diverse_retail_channels", "편의점·이마트·대형마트·문구점·완구점·카드샵",
        required_categories <= retail_categories
        and all("미확인" in str(row.get("inventory_status", ""))
                and row.get("inventory_verified") is False for row in korean_offline)
        and all(any(token in str(row.get("name", "")) for row in korean_offline)
                for token in ("CU", "GS25", "세븐일레븐", "이마트24", "이마트 안산고잔점",
                              "트레이더스 홀세일 클럽 안산점", "알파문구", "동네 문구"))
        and 'id="purchaseRetailerType"' in page and 'x.retailer_category===category' in page,
        f"한국 오프라인 {len(korean_offline)}곳 · 매장 분류 {len(retail_categories)}종 · 점포 재고 미확인")
    gyeonggi = [row for row in sources if isinstance(row, dict) and str(row.get("address", "")).startswith("경기도")]
    add("ansan_distance", "경기도 매장·안산 기준 거리순",
        len(gyeonggi) >= 25 and "function useAnsanDistance()" in page,
        f"경기도 좌표 매장 {len(gyeonggi)}개")
    add("catalog_images_search", "국가·게임·BOX/HIT 이미지·검색·정렬",
        all(token in page for token in ("countryAnalysisList", "tradeCatalogList", 'id="box12"',
                                         "function renderBoxKnowledge", "analysisSort", "tradeSort"))
        and "safeExternalUrl" in page,
        "카탈로그·HTTPS 이미지·필터")
    add("pc_android_autostart", "Windows PC·Android 태블릿 서버·재부팅 자동시작",
        all((base / name).is_file() for name in ("START_TCG_UPDATER.bat", "PC_SERVER_AUTO_START_INSTALL.bat",
                                                  "START_TCG_UPDATER_ANDROID.sh", "ANDROID_AUTO_START_INSTALL.sh")),
        "Windows·Termux 실행기 4종")
    app_name = str(manifest.get("name", ""))
    cache_match = re.search(r"const CACHE='([^']+)'", worker)
    version_match = re.search(r"INTEGRATED_VERSION\s*=\s*['\"]([^'\"]+)['\"]", server)
    health_uses_version = "'integrated_version':INTEGRATED_VERSION" in server
    coherent = bool(app_name and app_name in page and cache_match and version_match and health_uses_version
                    and version_match.group(1) in automatic
                    and cache_match.group(1).replace("tcg-", "") == version_match.group(1))
    add("version_coherence", "로컬·PWA·서버·자동수집 버전 일치",
        coherent, "화면·manifest·서비스워커·서버 엔진 일치")
    add("safe_update_fallback", "통신 실패 시 마지막 정상자료 유지·허위정보 생성 금지",
        "기존 정상자료 유지" in automatic and "advisory_text_or_generated_code_executed" in safe_read_text(base / "FINAL_VERIFICATION_REPORT.json"),
        "원자저장·검증 실패 격리")

    implemented = sum(row["implemented"] for row in features)
    missing = [row["id"] for row in features if not row["implemented"]]
    return {
        "ok": not missing,
        "version": 3,
        "total": len(features),
        "implemented": implemented,
        "missing": missing,
        "features": features,
        "excluded": [{"id": "iphone_serverless_continuous_collection",
                      "reason": "사용자가 구현 제외를 요청한 기능"}],
        "learning_policy": "누락은 verify_all 실패로 기록되어 동일 원인 통합·신규 원인 분리 학습에 전달",
    }


if __name__ == "__main__":
    result = audit_feature_contract()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)
