"""Read-only restoration of saved country/game event cards in the tablet shell.

V896 discovery coverage and the historical promo_events.json event feed are
independent evidence. This view never declares discovery leads confirmed and
never writes collection or training files.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import html
from pathlib import Path

from execution.tablet_catalog_bridge import norm, registry, safe_url, read_json
from execution.tablet_event_summary_v890 import REGIONS, read_event_summary

EVENT_CARD_STYLES = (
    '<style>'
    '.tcg930-saved-events{--event-ink:#18243b;--event-muted:#52617b;'
    'color:var(--event-ink);margin:16px 0 28px}'
    '.tcg930-saved-events>h2{font-size:clamp(1.2rem,2.5vw,1.65rem);'
    'letter-spacing:-.025em;margin:0 0 10px}'
    '.tcg930-saved-events>p{line-height:1.6;color:var(--event-muted)}'
    '.tcg930-saved-events [role="alert"]{background:#fff6e8;color:#6b420d;'
    'border:1px solid #efce8b;padding:12px 14px;border-radius:12px}'
    '.tcg930-group{margin:20px 0;padding:16px;border:1px solid #dce5f2;'
    'border-radius:20px;background:#f8faff}'
    '.tcg930-group>h3{margin:0 0 14px;font-size:1.05rem;letter-spacing:-.015em}'
    '.tcg930-event{background:#fff;border:1px solid #dce4ef;'
    'border-radius:15px;padding:16px;margin:12px 0;'
    'box-shadow:0 3px 12px rgba(24,36,59,.05);overflow-wrap:anywhere}'
    '.tcg930-event .tcg944-status{display:inline-block;font-size:.78rem;'
    'font-weight:700;border-radius:999px;padding:5px 10px;margin:0 0 9px;'
    'background:#eaf2ff;color:#244d86}'
    '.tcg930-event[data-tcg930-lifecycle="ARCHIVED"] .tcg944-status,'
    '.tcg930-event[data-tcg930-lifecycle="RECENTLY_ENDED"] .tcg944-status'
    '{background:#edf0f5;color:#4c596e}'
    '.tcg930-event[data-tcg930-lifecycle="TRACKING"] .tcg944-status,'
    '.tcg930-event[data-tcg930-lifecycle="UNKNOWN_DATE"] .tcg944-status'
    '{background:#fff2d8;color:#704e12}'
    '.tcg930-event h4{font-size:1.06rem;margin:0 0 9px;line-height:1.45}'
    '.tcg930-event p{margin:6px 0;line-height:1.55;color:#46566d}'
    '.tcg930-event a{display:inline-block;margin-top:9px;'
    'color:#1d4ed8;font-weight:650;text-underline-offset:3px}'
    '.tcg930-group details{border:1px solid #dce4ef;border-radius:12px;'
    'padding:12px;background:#fff;margin-top:12px}'
    '.tcg930-group summary{cursor:pointer;font-weight:650}'
    '.tcg936-visible-archive{display:grid;gap:4px}'
    '@media(min-width:760px){.tcg936-visible-archive{grid-template-columns:'
    'repeat(2,minmax(0,1fr));gap:12px}.tcg936-visible-archive '
    '.tcg930-event{margin:0}}'
    '@media(prefers-reduced-motion:no-preference){.tcg930-event{'
    'transition:box-shadow .18s ease}.tcg930-event:hover{'
    'box-shadow:0 8px 22px rgba(24,36,59,.1)}}'
    '</style>'
)

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


def _collector_run_note(root):
    """Read-only status of the last persisted updater report, not live execution."""
    path = root / 'auto_update_report.json'
    if not path.is_file():
        return '<p role="note">행사 수집기 실행 기록을 확인할 수 없습니다.</p>'
    try:
        report = read_json(path, 2_000_000)
        if not isinstance(report, dict):
            raise ValueError('invalid updater report')
        finished = report.get('finished_at')
        if not isinstance(finished, str) or len(finished) > 64:
            raise ValueError('missing updater timestamp')
        parsed = datetime.fromisoformat(finished.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError('timezone missing')
        age = (datetime.now(timezone.utc) - parsed).total_seconds()
        if age < -300:
            raise ValueError('future updater timestamp')
        results = report.get('results')
        if not isinstance(results, list):
            raise ValueError('missing job results')
        matches = [item for item in results if isinstance(item, dict)
                   and item.get('file') == 'promo_events.json']
        if len(matches) != 1 or type(matches[0].get('ok')) is not bool:
            raise ValueError('missing event collector result')
        job = matches[0]
        state = ('마지막 행사 수집 작업 성공' if job['ok'] else
                 '마지막 행사 수집 작업 실패')
        if age > 7 * 86400:
            state += ' · 마지막 기록이 7일 넘게 오래됐습니다'
        return ('<p role="status">수집기 실행 기록: ' + _safe(finished, 64) +
                ' · ' + state +
                ' · 현재 자동 실행 여부는 별도 확인 필요.</p>')
    except (OSError, ValueError, TypeError, UnicodeError):
        return '<p role="alert">행사 수집기 실행 기록을 검증할 수 없습니다.</p>'


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
            # A saved event may have an ended participation period but a later
            # reward-claim deadline. Show both; never imply the event continues.
            start, end = row.get('start_date'), row.get('end_date')
            date_label = row.get('date_label') or (
                ('행사 일정: ' + start + ' ~ ' + end) if start and end else
                ('행사 시작: ' + start) if start else '일정 확인 필요')
            claim = row.get('claim_deadline')
            if claim and start and end and claim > end:
                date_label += ' · 수령 마감: ' + claim
            item = (
                '<article class="tcg930-event" data-tcg930-region="' + _safe(country) +
                '" data-tcg930-game="' + _safe(name) +
                '" data-tcg930-lifecycle="' + _safe(row['lifecycle']) +
                '"><span class="tcg944-status">' + _safe(lifecycle) +
                '</span><h4>' + _safe(row['name']) +
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
    # This is the dataset snapshot time, not an event date or source verification.
    source_stamp = result.get('source_updated_at')
    try:
        parsed = datetime.fromisoformat(source_stamp.replace('Z', '+00:00')) if (
            isinstance(source_stamp, str) and len(source_stamp) <= 64) else None
        age_seconds = (datetime.now(timezone.utc) - parsed).total_seconds() if (
            parsed is not None and parsed.tzinfo is not None) else None
    except ValueError:
        age_seconds = None
    freshness_note = (
        '<p role="alert">저장 행사 자료의 갱신 시각을 확인할 수 없습니다. '
        '현재 행사 목록으로 단정하지 마세요.</p>' if age_seconds is None or age_seconds < -300 else
        '<p role="alert">저장 행사 자료가 7일 넘게 갱신되지 않았습니다. '
        '최신 행사 누락 가능 · 공식 출처 재확인 필요.</p>' if age_seconds > 7 * 86400 else
        '<p role="note">저장 행사 자료 최근 갱신 기록 있음 · 행사 자체의 확인과는 별개입니다.</p>'
    )
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
        EVENT_CARD_STYLES +
        '<section class="tcg930-saved-events" aria-label="이전 행사 기록">'
        '<h2>기존 저장 행사 · 콜라보 · 영화 · 프로모</h2>'
        '<p>기존 자료 ' + str(summary.get('loaded_rows', len(rows))) +
        '건 중 현재 조건 ' + str(len(filtered)) +
        '건 · 국가별·TCG별로 표시 · 지난 행사 기록도 보존</p>'
        '<p role="note">표시되는 국가 정보는 저장된 행사 분류입니다. '
        '출처 링크 점검은 행사 일정·증정카드·개최 확정을 의미하지 않습니다.</p>' +
        freshness_note + _collector_run_note(root) + warning + ''.join(rendered) + empty + '</section>'
    )
