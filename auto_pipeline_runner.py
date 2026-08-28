#!/usr/bin/env python3
"""Integrated discovery pipeline with adaptive multi-provider learning.

v113:
- Pokemon / ONE PIECE / NARUTO use adaptive KR/JP/US search plans.
- Broad search now uses independent no-key providers through MultiChannelCollector.
- HTTP-success + zero-result is recorded as empty/degraded, not a hard failure.
- Broad adaptive leads are merged into social_event_candidates.json as low-trust
  candidates so the event UI can surface them without promoting them to official.
- Verified/cross-checked candidates still teach future query vocabulary.
"""
from __future__ import annotations

import concurrent.futures
import os
import urllib.parse
from datetime import datetime
from pathlib import Path

from cross_platform_agent import CrossPlatformSelfHealingEngine
from multi_channel_agent import MultiChannelCollector
from safe_runtime import atomic_write_json
import supplementary_discovery
import social_event_discovery

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "web_discovery_candidates.json"
GAME_LABELS = {"포켓몬": "포켓몬 카드", "원피스": "원피스 카드", "나루토": "나루토 카드"}
SOCIAL_HOST_KIND = {
    "x.com": "x_public_search", "www.x.com": "x_public_search",
    "twitter.com": "x_public_search", "www.twitter.com": "x_public_search",
    "instagram.com": "instagram_public_search", "www.instagram.com": "instagram_public_search",
    "youtube.com": "youtube_public_search", "www.youtube.com": "youtube_public_search", "youtu.be": "youtube_public_search",
}


def _workers() -> int:
    is_android = "com.termux" in os.environ.get("PREFIX", "") or "ANDROID_ROOT" in os.environ
    return 2 if is_android else 3


def _host(url: str) -> str:
    try:
        return (urllib.parse.urlsplit(str(url or "")).hostname or "").lower()
    except ValueError:
        return ""


def _adaptive_event_rows(candidates: list[dict]) -> list[dict]:
    """Convert ranked broad-search hits to event candidates without trust escalation."""
    rows: list[dict] = []
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    for block in candidates:
        keyword = str(block.get("keyword") or "")
        game = GAME_LABELS.get(keyword, keyword + " 카드" if keyword else "")
        if not game:
            continue
        for item in block.get("results") or []:
            if not isinstance(item, dict):
                continue
            source = str(item.get("url") or "")
            title = str(item.get("title") or "").strip()
            if not source.startswith("https://") or not title:
                continue
            region = str(item.get("query_region") or "KR")
            if region not in {"KR", "JP", "US"}:
                region = "KR"
            host = _host(source)
            source_kind = SOCIAL_HOST_KIND.get(host, "adaptive_web_search")
            official_hint = bool(item.get("official_hint"))
            provider = str(item.get("search_provider") or "multi_provider")
            rows.append({
                "game": game,
                "region": region,
                "category": social_event_discovery._category(title),
                "title": title[:220],
                "source": source,
                "source_kind": source_kind,
                "source_tier": "A-search" if official_hint else "B-search",
                "source_label": f"자가학습 {provider} · 공식도메인 후보" if official_hint else f"자가학습 {provider} 공개검색 후보",
                "official_domain_match": official_hint,
                "official_account_verified": False,
                "dates": social_event_discovery._dates(title),
                "excerpt": title[:300],
                "status": "공식도메인 검색후보 · 내용 재확인 필요" if official_hint else "자가학습 검색후보 · 교차확인 필요",
                "verified": False,
                "confidence": 0.78 if official_hint else 0.56,
                "adaptive_search": True,
                "query_family": item.get("query_family"),
                "query_region": region,
                "search_provider": provider,
                "collected_at": now,
            })
    return rows


def _merge_adaptive_into_social(social: dict, candidates: list[dict]) -> tuple[dict, int]:
    adaptive_rows = _adaptive_event_rows(candidates)
    current = [x for x in (social.get("items") or []) if isinstance(x, dict)]
    merged = social_event_discovery.merge_candidates(current + adaptive_rows)
    out = dict(social)
    out["items"] = merged
    out["item_count"] = len(merged)
    out["official_social_candidate_count"] = sum(1 for x in merged if x.get("official_account_verified") is True)
    out["official_domain_search_count"] = sum(1 for x in merged if x.get("official_domain_match") is True)
    out["cross_checked_count"] = sum(1 for x in merged if x.get("cross_checked") is True)
    status = dict(out.get("channel_status") or {})
    status["adaptive_multi_provider"] = {
        "configured": True,
        "result_count": len(adaptive_rows),
        "merged_item_count": len(merged),
        "status": "DuckDuckGo/Bing RSS/Google News RSS + 완화 OR 검색 후보 병합",
    }
    out["channel_status"] = status
    out["adaptive_merge_count"] = len(adaptive_rows)
    out["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    atomic_write_json(social_event_discovery.OUT, out, suffix=".adaptive-social.tmp")
    return out, len(adaptive_rows)


def run_pipeline():
    agent = MultiChannelCollector()
    platform_agent = CrossPlatformSelfHealingEngine()
    keywords = ("포켓몬", "원피스", "나루토")

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

    adaptive_merge_count = 0
    try:
        social, adaptive_merge_count = _merge_adaptive_into_social(social, candidates)
    except Exception as exc:
        extra_errors.append(f"adaptive_social_merge: {type(exc).__name__}: {exc}")

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
            "adaptive_merged_rows": adaptive_merge_count,
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
    social_hard_failure = bool(
        not social.get("fresh_collection_ok")
        and not social.get("items")
        and (social_errors or social.get("error"))
    )
    errors = (
        [f"{x.get('keyword')}: {x.get('error', '수집 실패')}" for x in failures]
        + extra_errors
        + broad_errors[:20]
        + (social_errors[:20] if social_hard_failure else [])
    )

    payload = {
        "version": "v113-resilient-adaptive-discovery",
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "ok": len(failures) == 0 and not extra_errors and not social_hard_failure,
        "degraded": bool(broad_degraded or extra_errors or social_degraded),
        "failure_count": len(failures) + len(extra_errors) + (1 if social_hard_failure else 0),
        "empty_search_count": sum(1 for x in candidates if x.get("empty")),
        "errors": errors[:50],
        "notice": "검색/SNS/뉴스 후보 자료입니다. 반복 발견만으로 공식 승격하지 않으며 공식 웹사이트 또는 공식 연결 SNS/복수출처 확인이 필요합니다.",
        "learning_policy": "성공 검색어·유용 출처·검증 후보와 검색 제공자 결과를 학습하되, KR/JP/US 기본 탐색과 저사용 검색어 탐색을 항상 남겨 누락 과적합을 방지합니다.",
        "platform": platform_agent.diagnostics(),
        "queries": candidates,
        "supplementary": {
            "candidate_count": len(supplementary.get("items", [])),
            "updated_at": supplementary.get("updated_at"),
        },
        "social": {
            "candidate_count": len(social.get("items", [])),
            "adaptive_merge_count": adaptive_merge_count,
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
    total = sum(len(x.get("results", [])) for x in result["queries"])
    print(
        f"웹 후보 수집 완료: {total}건"
        f" · 실패 {result['failure_count']}건"
        f" · 빈검색 {result.get('empty_search_count', 0)}건"
        f" · 행사병합 {int((result.get('social') or {}).get('adaptive_merge_count') or 0)}건"
        f" · 학습검색어 {int((result.get('adaptive_learning') or {}).get('learned_queries') or 0)}개"
    )
