#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parent
PATH=ROOT/'social_event_discovery.py'

APPLIED_MARKERS = {
    'multi route import': 'import multi_route_event_discovery',
    'collector registration': '"route_diversity":',
    'independent-source counting': 'existing_evidence_host =',
    'balanced game-region merge': 'per_group_floor = 4',
    'resilient baseline': 'route_status = channel_status.get("route_diversity"',
}


def replace_once(text,old,new,label):
    if new in text:
        return text
    marker = APPLIED_MARKERS.get(label)
    if marker and marker in text:
        print(label, 'already applied by newer integration')
        return text
    if old not in text:
        raise RuntimeError(f'patch anchor not found: {label}')
    return text.replace(old,new,1)


def main():
    text=PATH.read_text(encoding='utf-8')

    text=replace_once(
        text,
        'import xml.etree.ElementTree as ET\nfrom html.parser import HTMLParser',
        'import xml.etree.ElementTree as ET\nimport multi_route_event_discovery\nfrom html.parser import HTMLParser',
        'multi route import',
    )

    text=replace_once(
        text,
        '        "google_news": lambda: collect_google_news(),\n        "public_social_search": lambda: collect_public_social_search(registry),',
        '        "google_news": lambda: collect_google_news(),\n        "route_diversity": lambda: multi_route_event_discovery.collect_all(),\n        "public_social_search": lambda: collect_public_social_search(registry),',
        'collector registration',
    )

    old='''        sources = max(1, int(existing.get("independent_source_count") or 1))\n        if _host(str(existing.get("source") or "")) != _host(source) or raw.get("source_kind") != existing.get("source_kind"): sources += 1'''
    new='''        sources = max(1, int(existing.get("independent_source_count") or 1))\n        # Different search routes/providers pointing at the same publisher are not\n        # independent corroboration. Prefer publisher_url when Google News exposes it.\n        existing_evidence_host = _host(str(existing.get("publisher_url") or existing.get("source") or ""))\n        new_evidence_host = _host(str(raw.get("publisher_url") or source or ""))\n        if existing_evidence_host and new_evidence_host and existing_evidence_host != new_evidence_host:\n            sources += 1'''
    text=replace_once(text,old,new,'independent-source counting')

    old='''    result = list(merged.values()); result.sort(key=lambda x: (-float(x.get("confidence") or 0.0), str(x.get("game")), str(x.get("region")), str(x.get("title"))))\n    return result[:MAX_ITEMS]'''
    new='''    result = list(merged.values()); result.sort(key=lambda x: (-float(x.get("confidence") or 0.0), str(x.get("game")), str(x.get("region")), str(x.get("title"))))\n    # Preserve coverage across all 3 games x 3 regions so a high-volume franchise\n    # cannot crowd every JP/KR/US lead from another game out of the global cap.\n    selected = []; used = set(); per_group_floor = 4\n    for game_name in GAMES:\n        for region_name in REGION_LANG:\n            group = [row for row in result if row.get("game") == game_name and row.get("region") == region_name]\n            for row in group[:per_group_floor]:\n                marker = id(row)\n                if marker not in used:\n                    selected.append(row); used.add(marker)\n    for row in result:\n        marker = id(row)\n        if marker not in used:\n            selected.append(row); used.add(marker)\n        if len(selected) >= MAX_ITEMS: break\n    return selected[:MAX_ITEMS]'''
    text=replace_once(text,old,new,'balanced game-region merge')

    old='''    google_status = channel_status.get("google_news", {}) if isinstance(channel_status.get("google_news"), dict) else {}\n    public_status = channel_status.get("public_social_search", {}) if isinstance(channel_status.get("public_social_search"), dict) else {}\n    baseline_ok = int(google_status.get("success_query_count") or 0) > 0 or int(public_status.get("success_query_count") or 0) > 0'''
    new='''    google_status = channel_status.get("google_news", {}) if isinstance(channel_status.get("google_news"), dict) else {}\n    route_status = channel_status.get("route_diversity", {}) if isinstance(channel_status.get("route_diversity"), dict) else {}\n    public_status = channel_status.get("public_social_search", {}) if isinstance(channel_status.get("public_social_search"), dict) else {}\n    baseline_ok = (int(google_status.get("success_query_count") or 0) > 0\n                   or int(route_status.get("success_query_count") or 0) > 0\n                   or int(public_status.get("success_query_count") or 0) > 0)'''
    text=replace_once(text,old,new,'resilient baseline')

    text=text.replace('"version": "v110-no-key-social-youtube-fallback"','"version": "v113-multi-route-resilient-discovery"',1)
    text=text.replace(
        '"policy": "공식 웹사이트 우선. X/Instagram/YouTube는 API가 없어도 공개검색 후보를 수집하고 공식계정은 레지스트리로 검증. 이전 공식/교차확인 후보는 새 수집 때도 보존. 공식확정 promo_events 승격은 별도 검증.",',
        '"policy": "공식 웹사이트 우선. Google News, Bing RSS 일반/공식/파트너 검색, 공식사이트 직접 링크 스캔, DuckDuckGo 비상 폴백, X/Instagram/YouTube 공개검색을 독립 경로로 운영. 이전 공식/교차확인 후보는 보존하며 공식확정 promo_events 승격은 별도 검증.",',
        1,
    )
    text=text.replace(
        '"google_policy": "Google News 무키 RSS + 선택적 Google CSE + 공개검색 폴백.",',
        '"google_policy": "Google News 무키 RSS + 선택적 Google CSE. Google 장애 시 Bing RSS/공식링크/DDG 경로가 독립적으로 수집을 계속함.",',
        1,
    )

    PATH.write_text(text,encoding='utf-8')
    print('multi-route event discovery integration applied')


if __name__=='__main__':
    main()
