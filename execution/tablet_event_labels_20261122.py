"""Korean labels for stored event projections; no new evidence or date claims."""
LIFECYCLE = {'CURRENT':'진행 중', 'UPCOMING':'진행 예정', 'RECENTLY_ENDED':'최근 종료',
             'ARCHIVED':'종료·보관', 'TRACKING':'일정 확인 중', 'UNKNOWN_DATE':'날짜 확인 필요'}
EVIDENCE = {'FRESH_OFFICIAL':'공식 출처 최근 확인', 'STALE_OFFICIAL':'공식 출처 재확인 필요',
            'UNVERIFIED':'근거 검증 필요', 'UNKNOWN_FRESHNESS':'출처 확인 시각 미상',
            'INVALID_SOURCE':'출처 확인 필요'}
CATEGORIES = {'event':'행사', 'promo':'프로모', 'collab':'콜라보', 'collaboration':'콜라보',
              'movie':'영화·영상 소식', 'merch':'상품 소식', 'release':'출시 소식', 'tournament':'대회'}


def lookup(table, value, fallback):
    return table.get(value, fallback) if isinstance(value, str) else fallback


def labels(event):
    if not isinstance(event, dict):
        raise ValueError('event projection required')
    lifecycle = event.get('lifecycle')
    # A tracking horizon never becomes a confirmed event or theatrical film.
    tracking = event.get('tracking_only') is True or lifecycle == 'TRACKING'
    category = lookup(CATEGORIES, event.get('category'), '기타 소식')
    if event.get('media_type') == 'streaming_series':
        category = '스트리밍·시리즈'
    elif event.get('media_type') == 'theatrical_film':
        category = '극장 영화 소식'
    if tracking:
        category += ' · 일정 추적'
    return {'category':category,
            'schedule':'일정: ' + ('일정 확인 중' if tracking else lookup(LIFECYCLE, lifecycle, '상태 확인 필요')),
            'evidence':'출처: ' + lookup(EVIDENCE, event.get('evidence_state'), '근거 검증 필요')}
