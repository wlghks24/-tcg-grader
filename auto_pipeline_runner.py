#!/usr/bin/env python3
"""Integrated adaptive discovery pipeline.

v117:
- Pokemon / ONE PIECE / NARUTO keep adaptive KR/JP/US public search.
- Adds three independent official paths: direct page crawl, YouTube Atom feeds,
  and official sitemap discovery.
- Final selection preserves provider diversity so one engine/channel cannot occupy
  every slot merely because it returns more rows.
- Provider operational health is persisted separately from source trust.
- All broad/direct/feed leads remain candidates until existing verification rules
  confirm the event/content. Repeated discovery never grants official status.
"""
from __future__ import annotations

import concurrent.futures
import os
import urllib.parse
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from cross_platform_agent import CrossPlatformSelfHealingEngine
from multi_channel_agent import MultiChannelCollector
from safe_runtime import atomic_write_json
import official_channel_feed_discovery
import official_direct_discovery
import official_sitemap_discovery
import provider_health_learning
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
DIRECT_PROVIDER_ORDER = ("official_youtube_feed", "official_sitemap", "official_direct")
PROVIDER_ORDER = DIRECT_PROVIDER_ORDER + ("google_news", "bing_rss", "duckduckgo")


def _workers() -> int:
    is_android = "com.termux" in os.environ.get("PREFIX", "") or "ANDROID_ROOT" in os.environ
    return 2 if is_android else 3


def _host(url: str) -> str:
    try:
        return (urllib.parse.urlsplit(str(url or "")).hostname or "").lower()
    except ValueError:
        return ""


def _diverse_ranked(rows: list[dict], limit: int = 8) -> list[dict]:
    """Interleave providers while preserving relevance order within each bucket."""
    buckets: dict[str, list[dict]] = defaultdict(list)
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "").strip()
        if not url.startswith("https://") or url in seen:
            continue
        seen.add(url)
        provider = str(row.get("search_provider") or "unknown")
        buckets[provider].append(row)
    order = [name for name in PROVIDER_ORDER if buckets.get(name)]
    order += [name for name in buckets if name not in order]
    result: list[dict] = []
    index = 0
    while len(result) < max(1, limit) and order:
        progressed = False
        for provider in order:
            rows_for_provider = buckets.get(provider, [])
            if index < len(rows_for_provider):
                result.append(rows_for_provider[index])
                progressed = True
                if len(result) >= max(1, limit):
                    break
        if not progressed:
            break
        index += 1
    return result[: max(1, limit)]


def _collect_provider_for_games(provider: str, fn, keywords: tuple[str, ...]) -> dict[str, dict]:
    by_key: dict[str, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=_workers(), thread_name_prefix=f"tcg-{provider}") as ex:
        futs = {ex.submit(fn, k): k for k in keywords}
        for fut in concurrent.futures.as_completed(futs):
            key = futs[fut]
            try:
                by_key[key] = fut.result()
            except Exception as exc:
                by_key[key] = {
                    "keyword": key,
                    "ok": False,
                    "degraded": True,
                    "results": [],
                    "errors": [f"{type(exc).__name__}: {exc}"],
                    "provider": provider,
                }
    return by_key


def _collect_official_sources(keywords: tuple[str, ...]) -> dict[str, dict[str, dict]]:
    collectors = (
        ("official_direct", official_direct_discovery.collect_game),
        ("official_youtube_feed", official_channel_feed_discovery.collect_game),
        ("official_sitemap", official_sitemap_discovery.collect_game),
    )
    out: dict[str, dict[str, dict]] = {}
    # Provider groups run sequentially to keep Termux traffic/memory bounded; games run in parallel.
    for provider, fn in collectors:
        out[provider] = _collect_provider_for_games(provider, fn, keywords)
    return out


def _merge_official_sources(
    agent: MultiChannelCollector,
    candidates: list[dict],
    official_sources: dict[str, dict[str, dict]],
) -> tuple[list[dict], dict[str, int]]:
    selected_totals = {provider: 0 for provider in DIRECT_PROVIDER_ORDER}
    merged_blocks: list[dict] = []
    for block in candidates:
        keyword = str(block.get("keyword") or "")
        direct_rows: list[dict] = []
        discovered_counts: dict[str, int] = {}
        source_errors: dict[str, list[str]] = {}
        source_status: dict[str, object] = {}
        for provider in DIRECT_PROVIDER_ORDER:
            result = (official_sources.get(provider) or {}).get(keyword) or {}
            rows = [dict(x) for x in (result.get("results") or []) if isinstance(x, dict)]
            discovered_counts[provider] = len(rows)
            source_errors[provider] = [str(x) for x in (result.get("errors") or [])][:20]
            source_status[provider] = {
                "ok": bool(result.get("ok")),
                "degraded": bool(result.get("degraded")),
                "result_count": len(rows),
                "pages": result.get("pages") or result.get("accounts") or result.get("sitemaps") or [],
            }
            for row in rows:
                row["official_hint"] = True
                row["search_provider"] = provider
                row.setdefault("query_family", provider.replace("_", "-"))
                row.setdefault("query_region", "KR")
                direct_rows.append(row)
        combined = list(block.get("results") or []) + direct_rows
        ranked = agent.learner.rank_results(keyword, combined, limit=max(30, len(combined) or 1))
        selected = _diverse_ranked(ranked, limit=8)
        selected_counts = dict(Counter(str(x.get("search_provider") or "unknown") for x in selected))
        for provider in DIRECT_PROVIDER_ORDER:
            selected_totals[provider] += int(selected_counts.get(provider) or 0)
        out = dict(block)
        out["results"] = selected
        out["provider_counts"] = selected_counts
        out["provider_diversity"] = len(selected_counts)
        out["provider_pool_counts"] = dict(Counter(str(x.get("search_provider") or "unknown") for x in combined))
        out["official_source_discovered"] = discovered_counts
        out["official_source_selected"] = {p: int(selected_counts.get(p) or 0) for p in DIRECT_PROVIDER_ORDER}
        out["official_source_status"] = source_status
        out["official_source_errors"] = source_errors
        if direct_rows:
            out["empty"] = False
            out["ok"] = True
        merged_blocks.append(out)
    return merged_blocks, selected_totals


def _provider_label(provider: str) -> tuple[str, str, str, float]:
    if provider == "official_youtube_feed":
        return "official_youtube_feed", "공식 YouTube 피드 직접수집 후보", "공식 YouTube 피드 · 내용 재확인 필요", 0.90
    if provider == "official_sitemap":
        return "official_sitemap", "공식 사이트맵 직접수집 후보", "공식 사이트맵 · 내용 재확인 필요", 0.88
    if provider == "official_direct":
        return "official_direct", "공식사이트 직접수집 후보", "공식사이트 직접수집 · 내용 재확인 필요", 0.86
    return "", "", "", 0.0


def _adaptive_event_rows(candidates: list[dict]) -> list[dict]:
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
            provider = str(item.get("search_provider") or "multi_provider")
            direct_kind, direct_label, direct_status, direct_confidence = _provider_label(provider)
            is_youtube_official = provider == "official_youtube_feed"
            official_hint = bool(item.get("official_hint"))
            if direct_kind:
                source_kind = direct_kind
                source_label = direct_label
                status = direct_status
                confidence = direct_confidence
            else:
                source_kind = SOCIAL_HOST_KIND.get(host, "adaptive_web_search")
                source_label = f"자가학습 {provider} · 공식도메인 후보" if official_hint else f"자가학습 {provider} 공개검색 후보"
                status = "공식도메인 검색후보 · 내용 재확인 필요" if official_hint else "자가학습 검색후보 · 교차확인 필요"
                confidence = 0.78 if official_hint else 0.56
            rows.append({
                "game": game,
                "region": region,
                "category": social_event_discovery._category(title),
                "title": title[:220],
                "source": source,
                "source_kind": source_kind,
                "source_tier": "A-social" if is_youtube_official else ("A-search" if official_hint else "B-search"),
                "source_label": source_label,
                "official_domain_match": bool(official_hint and not is_youtube_official),
                "official_account_verified": bool(is_youtube_official),
                "dates": social_event_discovery._dates(title),
                "excerpt": title[:300],
                "status": status,
                "verified": False,
                "confidence": confidence,
                "adaptive_search": True,
                "query_family": item.get("query_family"),
                "query_region": region,
                "search_provider": provider,
                "published_at": item.get("published_at"),
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
        "status": "공식사이트/YouTube/사이트맵 직접수집 + DuckDuckGo/Bing RSS/Google News RSS 후보 병합",
    }
    out["channel_status"] = status
    out["adaptive_merge_count"] = len(adaptive_rows)
    out["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    atomic_write_json(social_event_discovery.OUT, out, suffix=".adaptive-social.tmp")
    return out, len(adaptive_rows)


def _official_source_summary(
    keywords: tuple[str, ...],
    candidates: list[dict],
    official_sources: dict[str, dict[str, dict]],
    selected_totals: dict[str, int],
) -> dict:
    summary = {}
    for provider in DIRECT_PROVIDER_ORDER:
        games = {}
        for key in keywords:
            raw = (official_sources.get(provider) or {}).get(key) or {}
            block = next((x for x in candidates if x.get("keyword") == key), {})
            games[key] = {
                "result_count": len(raw.get("results") or []),
                "selected_count": int((block.get("official_source_selected") or {}).get(provider) or 0),
                "degraded": bool(raw.get("degraded")),
                "status": raw.get("pages") or raw.get("accounts") or raw.get("sitemaps") or [],
            }
        summary[provider] = {"selected_total": int(selected_totals.get(provider) or 0), "games": games}
    return summary


def _health_rows(candidates: list[dict], official_sources: dict[str, dict[str, dict]]) -> list[dict]:
    rows = []
    selected = Counter()
    pool = Counter()
    for block in candidates:
        selected.update(block.get("provider_counts") or {})
        pool.update(block.get("provider_pool_counts") or {})
    for provider in ("duckduckgo", "bing_rss", "google_news"):
        error_count = 0
        for block in candidates:
            for err in block.get("collection_errors") or []:
                if provider in str(err):
                    error_count += 1
        rows.append({
            "provider": provider,
            "responded": bool(pool.get(provider) or not error_count),
            "results": int(pool.get(provider) or 0),
            "selected": int(selected.get(provider) or 0),
            "errors": error_count,
        })
    for provider in DIRECT_PROVIDER_ORDER:
        results = 0
        errors = 0
        responded = False
        for raw in (official_sources.get(provider) or {}).values():
            results += len(raw.get("results") or [])
            errors += len(raw.get("errors") or [])
            responded = responded or bool(raw.get("ok"))
        rows.append({
            "provider": provider,
            "responded": responded,
            "results": results,
            "selected": int(selected.get(provider) or 0),
            "errors": errors,
        })
    return rows


def run_pipeline():
    agent = MultiChannelCollector()
    platform_agent = CrossPlatformSelfHealingEngine()
    keywords = ("포켓몬", "원피스", "나루토")

    with concurrent.futures.ThreadPoolExecutor(max_workers=_workers(), thread_name_prefix="tcg-web-candidate") as ex:
        futs = {ex.submit(agent.search_web, k): k for k in keywords}
        by_key = {}
        for fut in concurrent.futures.as_completed(futs):
            key = futs[fut]
            try:
                by_key[key] = fut.result()
            except Exception as exc:
                by_key[key] = {
                    "ok": False,
                    "degraded": True,
                    "keyword": key,
                    "results": [],
                    "error": f"{type(exc).__name__}: {exc}",
                    "collection_errors": [f"{type(exc).__name__}: {exc}"],
                }
    candidates = [by_key[k] for k in keywords]

    official_sources = _collect_official_sources(keywords)
    candidates, selected_totals = _merge_official_sources(agent, candidates, official_sources)
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
            "official_selected": dict(selected_totals),
        }
    except Exception as exc:
        adaptive_learning = {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "safety": "학습기 오류만 격리하고 수집 후보/공식 검증자료는 유지",
        }
        extra_errors.append(f"adaptive_learning: {type(exc).__name__}: {exc}")

    provider_health = {}
    try:
        provider_health = provider_health_learning.observe(_health_rows(candidates, official_sources))
    except Exception as exc:
        provider_health = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        extra_errors.append(f"provider_health: {type(exc).__name__}: {exc}")

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

    official_summary = _official_source_summary(keywords, candidates, official_sources, selected_totals)
    payload = {
        "version": "v117-official-channel-sitemap-health-learning",
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "ok": len(failures) == 0 and not extra_errors and not social_hard_failure,
        "degraded": bool(broad_degraded or extra_errors or social_degraded),
        "failure_count": len(failures) + len(extra_errors) + (1 if social_hard_failure else 0),
        "empty_search_count": sum(1 for x in candidates if x.get("empty")),
        "errors": errors[:50],
        "notice": "검색/SNS/뉴스/공식사이트/공식 YouTube/사이트맵 후보 자료입니다. 발견 경로가 공식이어도 내용 검증 전에는 자동 확정하지 않습니다.",
        "learning_policy": "검색어·출처·검증 후보와 수집경로 건강도를 별도 누적 학습하되, 반복 발견만으로 공식 신뢰를 승격하지 않습니다.",
        "platform": platform_agent.diagnostics(),
        "queries": candidates,
        "official_direct": official_summary.get("official_direct", {}),
        "official_youtube_feed": official_summary.get("official_youtube_feed", {}),
        "official_sitemap": official_summary.get("official_sitemap", {}),
        "provider_health": provider_health,
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
        f" · 공식직접 {int((result.get('official_direct') or {}).get('selected_total') or 0)}건"
        f" · YouTube {int((result.get('official_youtube_feed') or {}).get('selected_total') or 0)}건"
        f" · 사이트맵 {int((result.get('official_sitemap') or {}).get('selected_total') or 0)}건"
        f" · 행사병합 {int((result.get('social') or {}).get('adaptive_merge_count') or 0)}건"
        f" · 학습검색어 {int((result.get('adaptive_learning') or {}).get('learned_queries') or 0)}개"
    )
