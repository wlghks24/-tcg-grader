"""Read-only restoration of saved country/game event cards in the tablet shell.

V896 discovery coverage and the historical promo_events.json event feed are
independent evidence. This view never declares discovery leads confirmed and
never writes collection or training files.
"""
from __future__ import annotations

from collections import defaultdict
import html
from pathlib import Path

from execution.tablet_catalog_bridge import norm, registry, safe_url
from execution.tablet_event_summary_v890 import REGIONS, read_event_summary

REGION_LABELS = {
    'KR': '한국', 'JP': '일본', 'US': '미국', 'CN': '중국',
    'CN-S': '중국 간체', 'CN-T': '중국 번체', 'TW': '대만',
    'HK': '홍콩', 'ASIA': '아시아', 'GLOBAL': '글로벌',
}
EVIDENCE_LABELS = {
    'FRESH_OFFICIAL': '공식 출처 링크 최근 점검 · 내용 확인 별도',
    'STALE_OFFICIAL': '공식 출처 링크 재확인 필요',
    'UNVERIFIED': '근거 출처 검증 대기',
    'INVALID_SOURCE': '유효한 출처 링크 없음',
    'UNKNOWN_FRESHNESS': '출처 확인 시각 미확인',
}
LIFECYCLE_LABELS = {
    'CURRENT': '기록된 일정상 진행 기간',
    'UPCOMING': '기록된 예정 일정', 'RECENTLY_ENDED': '최근 종료 기록',
    'TRACKING': '발표 추적 중 · 확정 행사 아님',
    'UNKNOWN_DATE': '일정 미확인',
    'ARCHIVED': '지난 행사 기록',
}
REGION_ORDER = {value: i for i, value in enumerate(REGION_LABELS)}


def _safe(value, limit=350):
    if not isinstance(value, str):
        return ''
    return html.escape(value[:limit], quote=True)


def render_saved_events(repo, *, game_id='', region=''):
    """Return bounded, independent HTML for saved and archived promo events.

    The user-selected game is a registry ID. Historical promo data stores
    Korean/display names, so map only *unambiguous* official registry aliases.
    Unmapped games remain visible in the all-games view rather than silently
    being attributed to an unrelated game.
    """
    root = Path(repo)
    games, aliases = registry(root)
    if game_id and game_id not in games:
        raise ValueError('unknown event game filter')
    if region and region not in REGIONS:
        raise ValueError('unknown event region filter')
    result = read_event_summary(root)
    if result.get('ok') is not True:
        return ('<section class="tcg930-saved-events" role="status">'
                '<h2>이전에 저장된 행사·콜라보</h2>'
                '<p role="alert">기존 행사 자료를 읽지 못했습니다. '
                '저장 기록을 0건으로 판정하거나 원본을 변경하지 않았습니다.</p></section>')

    rows = result['rows']
    filtered = []
    unmatched = 0
    for row in rows:
        stored_name = row['game']
        mapped = aliases.get(norm(stored_name)) or (
            stored_name if stored_name in games else '')
        if not mapped:
            unmatched += 1
        if game_id and mapped != game_id:
            continue
        if region and row['region'] != region:
            continue
        filtered.append((row, mapped))
    groups = defaultdict(list)
    for row, mapped in filtered:
        groups[(row['region'], mapped or row['game'])].append(row)
    rendered = []
    for (country, name), entries in sorted(
        groups.items(), key=lambda g: (
            REGION_ORDER.get(g[0][0], 99),
            games[g[0][1]].get('label_ko', g[0][1])
            if g[0][1] in games else g[0][1]
        )
    ):
        label = games[name].get('label_ko') or name if name in games else name
        current, archived = [], []
        for row in entries:
            lifecycle = LIFECYCLE_LABELS.get(row['lifecycle'], '상태 확인 필요')
            evidence = EVIDENCE_LABELS.get(row['evidence_state'], '출처 상태 확인 필요')
            source = safe_url(row.get('source'))
            link = ('<a href="' + html.escape(source, quote=True) +
                    '" target="_blank" rel="noopener noreferrer">근거 출처 확인</a>'
                    if source else '<span>출처 확인 필요 · 링크 없음</span>')
            date_label = row.get('date_label') or row.get('start_date') or '일정 확인 필요'
            item = (
                '<article class="tcg930-event" data-tcg930-region="' + _safe(country) +
                '" data-tcg930-game="' + _safe(name) +
                '"><h4>' + _safe(row['name']) +
                '</h4><p>구분: ' + _safe(row['category']) +
                ' · ' + lifecycle + '</p><p>' + _safe(date_label) +
                ' · ' + evidence + '</p>' + link + '</article>'
            )
            (archived if row['archived'] else current).append(item)
        rendered.append(
            '<section class="tcg930-group" aria-label="' +
            _safe(REGION_LABELS.get(country, country) + ' · ' + label) +
            '"><h3>' + _safe(REGION_LABELS.get(country, country)) + ' · ' +
            _safe(label) + ' (' + str(len(entries)) + '건)</h3>' +
            ''.join(current) +
            (('<details><summary>지난 행사·종료 기록 ' + str(len(archived)) +
              '건 · 현재 표시할 행사 없음, 기록 아래 표시</summary>' +
              '<p>지난 행사 기록은 아래에 바로 표시됩니다.</p></details>' +
              '<div class="tcg936-visible-archive" aria-label="지난 행사 기록">' +
              ''.join(archived) + '</div>' if not current else
              '<details><summary>지난 행사·종료 기록 ' + str(len(archived)) +
              '건</summary>' + ''.join(archived) + '</details>')
             if archived else '') +
            '</section>'
        )
    summary = result.get('summary') or {}
    trunc = bool(summary.get('rows_truncated'))
    rejected = summary.get('rejected_rows', 0)
    warning = ('<p role="note">저장자료 표시 상한 500건으로 일부 기록이 '
               '목록에서 제외됐습니다.</p>' if trunc else '')
    if rejected:
        warning += ('<p role="alert">형식·출처 확인이 필요한 기존 기록 ' +
                    str(rejected) + '건은 이 목록에서 제외됐습니다. '
                    '원본 파일은 그대로입니다.</p>')
    if unmatched:
        warning += ('<p role="note">게임명이 현재 등록정보와 연결되지 않은 '
                    '기존 기록 ' + str(unmatched) +
                    '건이 있습니다. 전체 게임에서 확인할 수 있습니다.</p>')
    empty = ('' if rendered else
             '<p role="status">선택한 게임·국가 조건에 표시할 저장 행사 기록이 '
             '없습니다. 다른 국가·게임 기록이나 신규 검색 후보가 '
             '없다는 뜻은 아닙니다.</p>')
    return (
        '<section class="tcg930-saved-events" aria-label="이전 행사 기록">'
        '<h2>기존 저장 행사 · 콜라보 · 영화 · 프로모</h2>'
        '<p>기존 자료 ' + str(summary.get('loaded_rows', len(rows))) +
        '건 중 현재 조건 ' + str(len(filtered)) +
        '건 · 국가별·TCG별로 표시 · 지난 행사 기록도 보존</p>'
        '<p role="note">표시되는 국가 정보는 저장된 행사 분류입니다. '
        '출처 링크 점검은 행사 일정·증정카드·개최 확정을 의미하지 않습니다.</p>' +
        warning + ''.join(rendered) + empty + '</section>'
    )
