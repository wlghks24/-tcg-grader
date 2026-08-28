#!/usr/bin/env python3
"""추가 업로드 기능을 기존 업데이트와 연결하는 통합 보조 실행기.

v62: 포켓몬/원피스/나루토 후보검색을 제한 병렬화하고, 일부/전체 실패를
상위 업데이트 엔진에 명시하여 오류학습이 clean success로 오판하지 않게 한다.
"""
from __future__ import annotations
import concurrent.futures
import os
from datetime import datetime
from pathlib import Path
from cross_platform_agent import CrossPlatformSelfHealingEngine
from multi_channel_agent import MultiChannelCollector
from safe_runtime import atomic_write_json
import supplementary_discovery
import social_event_discovery

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "web_discovery_candidates.json"


def _workers() -> int:
    is_android = 'com.termux' in os.environ.get('PREFIX','') or 'ANDROID_ROOT' in os.environ
    return 2 if is_android else 3


def run_pipeline():
    agent = MultiChannelCollector()
    platform_agent = CrossPlatformSelfHealingEngine()
    keywords = ("포켓몬", "원피스", "나루토")
    with concurrent.futures.ThreadPoolExecutor(max_workers=_workers(), thread_name_prefix='tcg-web-candidate') as ex:
        futs = {ex.submit(agent.search_web, k): k for k in keywords}
        by_key = {}
        for fut in concurrent.futures.as_completed(futs):
            k = futs[fut]
            try:
                by_key[k] = fut.result()
            except Exception as exc:
                by_key[k] = {"ok": False, "keyword": k, "results": [], "error": f"{type(exc).__name__}: {exc}"}
    candidates = [by_key[k] for k in keywords]
    failures = [x for x in candidates if not x.get('ok')]

    # v105: broad web search, supplementary wiki/news discovery, and social/Google discovery
    # are executed exactly once in the integration stage. Optional API credentials being
    # absent is not a failure; the social collector records each channel's configuration.
    extra_errors = []
    try:
        supplementary = supplementary_discovery.main()
    except Exception as exc:
        supplementary = {"items": [], "error": f"{type(exc).__name__}: {exc}"}
        extra_errors.append(f"supplementary: {type(exc).__name__}")
    try:
        social = social_event_discovery.main()
    except Exception as exc:
        social = {"items": [], "fresh_collection_ok": False, "degraded": True, "error": f"{type(exc).__name__}: {exc}"}
        extra_errors.append(f"social: {type(exc).__name__}")

    social_errors = [str(x) for x in (social.get("collection_errors") or []) if str(x).strip()]
    # Social discovery is additive. Temporary source/API failures are reported as degraded
    # but never erase the previous social_event_candidates.json dataset.
    social_degraded = bool(social.get("degraded"))
    errors = [f"{x.get('keyword')}: {x.get('error','수집 실패')}" for x in failures] + extra_errors + social_errors[:20]
    payload = {
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "ok": len(failures) == 0 and not extra_errors,
        "degraded": bool(failures or extra_errors or social_degraded),
        "failure_count": len(failures) + len(extra_errors) + (1 if social_degraded else 0),
        "errors": errors,
        "notice": "검색/SNS/뉴스 후보 자료입니다. 공식 웹사이트 또는 공식 연결 SNS 확인 전에는 확정 행사 데이터로 승격하지 않습니다.",
        "platform": platform_agent.diagnostics(),
        "queries": candidates,
        "supplementary": {
            "candidate_count": len(supplementary.get("items", [])),
            "updated_at": supplementary.get("updated_at"),
        },
        "social": {
            "candidate_count": len(social.get("items", [])),
            "official_social_candidate_count": int(social.get("official_social_candidate_count") or 0),
            "official_domain_search_count": int(social.get("official_domain_search_count") or 0),
            "cross_checked_count": int(social.get("cross_checked_count") or 0),
            "updated_at": social.get("updated_at"),
            "channel_status": social.get("channel_status", {}),
            "preserved_previous_items": bool(social.get("preserved_previous_items")),
        },
    }
    atomic_write_json(OUT,payload,suffix='.candidates.tmp')
    return payload


if __name__ == "__main__":
    result = run_pipeline()
    print(f"웹 후보 수집 완료: {sum(len(x.get('results',[])) for x in result['queries'])}건 · 실패 {result['failure_count']}건")
