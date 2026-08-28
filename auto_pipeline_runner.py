#!/usr/bin/env python3
"""Integrated discovery pipeline with adaptive collection learning.

v112:
- Pokemon / ONE PIECE / NARUTO use rotating KR/JP/US + official-domain +
  X/Instagram/YouTube discovery plans.
- Verified and cross-checked candidates teach useful search terms/source hosts.
- A small exploration budget remains active so the learner cannot overfit only
  to historically successful event types.
- Optional collection_feedback.json corrections are consumed once and become
  future search hints.
- Learning failure is isolated from collection data; official verification rules
  remain owned by the existing official collectors.
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
    is_android = "com.termux" in os.environ.get("PREFIX", "") or "ANDROID_ROOT" in os.environ
    return 2 if is_android else 3


def run_pipeline():
    agent = MultiChannelCollector()
    platform_agent = CrossPlatformSelfHealingEngine()
    keywords = ("포켓몬", "원피스", "나루토")

    # Broad adaptive searches run in parallel, while mutation of the shared learner
    # is internally serialized by MultiChannelCollector.
    with concurrent.futures.ThreadPoolExecutor(max_workers=_workers(), thread_name_prefix="tcg-web-candidate") as ex:
        futs = {ex.submit(agent.search_web, k): k for k in keywords}
        by_key = {}
        for fut in concurrent.futures.as_completed(futs):
            k = futs[fut]
            try:
                by_key[k] = fut.result()
            except Exception as exc:
                by_key[k] = {
                    "ok": False,
                    "degraded": True,
                    "keyword": k,
                    "results": [],
                    "error": f"{type(exc).__name__}: {exc}",
                    "collection_errors": [f"{type(exc).__name__}: {exc}"],
                }
    candidates = [by_key[k] for k in keywords]
    failures = [x for x in candidates if not x.get("ok")]
    broad_degraded = [x for x in candidates if x.get("degraded")]

    extra_errors: list[str] = []
    try:
        supplementary = supplementary_discovery.main()
    except Exception as exc:
        supplementary = {"items": [], "error": f"{type(exc).__name__}: {exc}"}
        extra_errors.append(f"supplementary: {type(exc).__name__}: {exc}")
    try:
        social = social_event_discovery.main()
    except Exception as exc:
        social = {"items": [], "fresh_collection_ok": False, "degraded": True, "error": f"{type(exc).__name__}: {exc}"}
        extra_errors.append(f"social: {type(exc).__name__}: {exc}")

    # Teach the next run from facts that survived the existing verification/cross-check
    # layers. Discovery-only community rows receive very small weight and never become
    # official through this learner.
    adaptive_learning = {}
    try:
        learned_supplementary = agent.learner.learn_from_payload(supplementary, origin="supplementary")
        learned_social = agent.learner.learn_from_payload(social, origin="social")
        learned_feedback = agent.learner.learn_feedback_file()
        agent.learner.save()
        adaptive_learning = agent.learner.report()
        adaptive_learning["learned_this_run"] = {
            "supplementary_rows": learned_supplementary,
            "social_rows": learned_social,
            "feedback_rows": learned_feedback,
        }
    except Exception as exc:
        adaptive_learning = {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "safety": "학습기 오류만 격리하고 수집 후보/공식 검증자료는 유지",
        }
        extra_errors.append(f"adaptive_learning: {type(exc).__name__}: {exc}")

    social_errors = [str(x) for x in (social.get("collection_errors") or []) if str(x).strip()]
    broad_errors: list[str] = []
    for row in candidates:
        for err in row.get("collection_errors") or []:
            text = str(err).strip()
            if text and text not in broad_errors:
                broad_errors.append(f"{row.get('keyword')}: {text}")
    social_degraded = bool(social.get("degraded"))
    errors = (
        [f"{x.get('keyword')}: {x.get('error', '수집 실패')}" for x in failures]
        + extra_errors
        + broad_errors[:20]
        + social_errors[:20]
    )

    payload = {
        "version": "v112-adaptive-self-learning-discovery",
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "ok": len(failures) == 0 and not extra_errors,
        "degraded": bool(failures or broad_degraded or extra_errors or social_degraded),
        "failure_count": len(failures) + len(extra_errors) + (1 if social_degraded else 0),
        "errors": errors[:50],
        "notice": "검색/SNS/뉴스 후보 자료입니다. 반복 발견만으로 공식 승격하지 않으며 공식 웹사이트 또는 공식 연결 SNS/복수출처 확인이 필요합니다.",
        "learning_policy": "성공 검색어·유용 출처·검증 후보에서 수집전략을 학습하되, KR/JP/US 기본 탐색과 저사용 검색어 탐색을 항상 남겨 누락 과적합을 방지합니다.",
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
        "adaptive_learning": adaptive_learning,
    }
    atomic_write_json(OUT, payload, suffix=".candidates.tmp")
    return payload


if __name__ == "__main__":
    result = run_pipeline()
    print(
        f"웹 후보 수집 완료: {sum(len(x.get('results', [])) for x in result['queries'])}건"
        f" · 실패 {result['failure_count']}건"
        f" · 학습검색어 {int((result.get('adaptive_learning') or {}).get('learned_queries') or 0)}개"
    )
