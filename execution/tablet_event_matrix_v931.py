"""All registered TCG events: honest read-only collection/evidence matrix.

Three independent layers have intentionally different meanings:
1. A registered game/country is only a collection target.
2. V896 search successes/leads are unverified discovery, not country of event.
3. V890 saved items/archive are local records, not automatically official facts.

This module does not request network access, schedule work, mutate JSON,
promote WATCH games, or endorse unknown event dates/rewards.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import html
from pathlib import Path

from execution.tablet_catalog_bridge import norm
from execution.tablet_event_summary_v890 import read_event_summary
from execution import tablet_event_coverage_v896 as coverage
from tcg_game_registry import load_registry

COUNTRIES = {'KR': '한국', 'JP': '일본', 'US': '미국',
             'GLOBAL': '글로벌', 'ASIA': '아시아'}
STATES = {'NOT_CONFIGURED': '검색 대상 외 기존 저장 지역', 'NOT_SEARCHED': '검색 기록 없음',
          'STALE_SEARCH': '재검색 필요', 'SEARCH_FAILED': '검색 실패',
          'PARTIAL_SEARCH': '일부 검색 성공', 'SEARCHED_UNCONFIRMED': '검색 완료 · 행사 미검증'}
GAME_STATES = {'core': '핵심', 'promoted': '확장 승인', 'watch': '발견·검토 전용'}
MAX_VISIBLE_CELLS = 100


def summarize(root, *, now=None):
    """Project current files without assuming discovery == verified events."""
    root = Path(root)
    now = datetime.now(timezone.utc) if now is None else now
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError('aware clock required')
    reg = load_registry(root)
    games = {g['id']: g for g in reg['games']}
    aliases = {}
    ambiguous = set()
    for g in reg['games']:
        for name in [g['id'], g.get('label_ko'), g.get('promo_value'),
                     g.get('canonical'), *(g.get('aliases') or [])]:
            if not isinstance(name, str):
                continue
            key = norm(name)
            if key and key in aliases and aliases[key] != g['id']:
                ambiguous.add(key)
            elif key:
                aliases[key] = g['id']
    for key in ambiguous:
        aliases.pop(key, None)

    cells = coverage.cells(reg)
    if not 0 < len(cells) <= MAX_VISIBLE_CELLS:
        raise ValueError('unexpected registry search scope')

    path = root / coverage.STATE
    discovery_status = 'RECORDED'
    try:
        if not path.exists():
            discovery_status = 'NOT_RECORDED'
        data = coverage._load(root)
        snapshot = coverage.report(cells, data, now=now)
        attempts = {r['key']: r for r in snapshot['cells']}
        unconfirmed = Counter()
        for row in snapshot['items']:
            for country in row['search_regions']:
                unconfirmed[(row['game_id'], country)] += 1
    except (OSError, ValueError, TypeError, KeyError, UnicodeError):
        discovery_status = 'READ_ERROR'
        attempts = {}
        unconfirmed = Counter()

    saved_result = read_event_summary(root, now=now)
    saved_status = 'READABLE' if saved_result.get('ok') is True else 'READ_ERROR'
    stored = Counter()
    archive = Counter()
    unmapped = 0
    if saved_status == 'READABLE':
        for row in saved_result['rows']:
            key = aliases.get(norm(row['game']))
            if not key:
                unmapped += 1
                continue
            (archive if row['archived'] else stored)[(key, row['region'])] += 1
    game_rows = []
    for g in reg['games']:
        g_cells = []
        configured_regions = {c['region']: c for c in cells if c['game_id'] == g['id']}
        # Preserve old GLOBAL/ASIA records even when no registry search cell
        # exists for the location. A saved-event region is not a search target.
        saved_regions = {
            country for (game, country) in set(stored) | set(archive)
            if game == g['id']
        }
        regions = sorted(set(configured_regions) | saved_regions,
                         key=lambda r: (list(COUNTRIES).index(r)
                                        if r in COUNTRIES else 99, r))
        for region in regions:
            cell = configured_regions.get(region)
            key = (g['id'], region)
            stat = attempts.get(cell['key']) if cell else None
            status = (stat['status'] if stat else
                      'NOT_CONFIGURED' if cell is None else
                      'UNKNOWN_READ_ERROR' if discovery_status == 'READ_ERROR'
                      else 'NOT_SEARCHED')
            g_cells.append({
                'region': region,
                'configured': cell is not None,
                'search_status': status,
                'attempted_at': stat.get('attempted_at') if stat else None,
                'candidate_leads': (unconfirmed[key]
                                    if discovery_status != 'READ_ERROR' else None),
                'saved_active': stored[key] if saved_status == 'READABLE' else None,
                'saved_archive': archive[key] if saved_status == 'READABLE' else None,
            })
        game_rows.append({'id': g['id'], 'label': g.get('label_ko') or g['id'],
                          'state': g['state'], 'cells': g_cells,
                          'official_auto_eligible': g['state'] in {'core', 'promoted'}})
    return {
        'registered_games': len(reg['games']),
        'search_cells': len(cells),
        'game_rows': game_rows,
        'discovery_status': discovery_status,
        'saved_status': saved_status,
        'saved_total': saved_result['summary']['loaded_rows']
             if saved_status == 'READABLE' else None,
        'saved_unmapped': unmapped if saved_status == 'READABLE' else None,
        'candidate_total': len(data['items']) if discovery_status != 'READ_ERROR' else None,
        'training_performed': False,
    }


def render(root, *, now=None):
    value = summarize(root, now=now)
    esc = lambda x: html.escape(str(x), quote=True)
    status_parts = [
        '전체 TCG 등록·검색 대상과 실제 결과는 다릅니다.',
        '검색국가와 행사 개최국은 다르며 후보는 행사·특전·일정 미확인입니다.',
        'WATCH 대상은 공식 행사 자동승격 제외 · 출처/일정 검증 후 별도 심사 필요.',
    ]
    messages = []
    if value['saved_status'] != 'READABLE':
        messages.append('기존 행사 저장소 읽기 오류 · 0건으로 판단하지 않습니다.')
    if value['discovery_status'] == 'READ_ERROR':
        messages.append('신규 행사 검색 기록 읽기 오류 · 이전 자료 보존.')
    elif value['discovery_status'] == 'NOT_RECORDED':
        messages.append('신규 검색 기록 파일 없음 · 30종 수집 성공으로 판정할 수 없습니다.')
    if value['saved_unmapped']:
        messages.append('등록 게임명에 정확히 연결되지 않은 저장 기록 '
                        + str(value['saved_unmapped']) + '건 · 원본 유지')
    rows = []
    for game in value['game_rows']:
        per_country = []
        for cell in game['cells']:
            label = STATES.get(cell['search_status'], '상태 확인 필요')
            leads = ('확인 보류' if cell['candidate_leads'] is None
                     else str(cell['candidate_leads']) + '건 (미확인 후보)')
            saved = ('확인 보류' if cell['saved_active'] is None
                     else str(cell['saved_active']) + '건 / 지난 기록 '
                     + str(cell['saved_archive']) + '건')
            stamp = esc(cell['attempted_at'] or '검색 시각 없음')
            per_country.append(
                '<tr><td>' + esc(COUNTRIES.get(cell['region'], cell['region'])) +
                ' (' + esc(cell['region']) + ')</td><td>' + esc(saved) +
                '</td><td>' + esc(leads) + '</td><td>' + esc(label) +
                '<small> · ' + stamp + '</small></td></tr>'
            )
        # Games with no V896 search cell remain registered but not measured.
        if not per_country:
            per_country.append('<tr><td colspan="4">현재 자동 검색 대상 국가 없음'
                               ' · 등록된 게임이 없어졌다는 뜻은 아닙니다.</td></tr>')
        rows.append(
            '<details class="tcg931-game" data-tcg931-game="' + esc(game['id']) + '">'
            '<summary>' + esc(game['label']) + ' · ' +
            esc(GAME_STATES.get(game['state'], '상태 확인 필요')) +
            ' · 검색국가 ' + str(len(game['cells'])) + '개</summary>'
            '<p>' + ('공식 출처 검사 결과와 일정 확인 시 행사 저장 대상'
                       if game['official_auto_eligible']
                       else '공식 승격 전 · 검색 후보만 표시') + '</p>'
            '<div style="overflow-x:auto"><table><thead><tr>'
            '<th>검색 대상</th><th>기존 저장 기록 / 지난 기록</th>'
            '<th>발견 후보</th><th>최근 검색 상태</th>'
            '</tr></thead><tbody>' + ''.join(per_country) +
            '</tbody></table></div></details>'
        )
    return (
        '<section class="tcg931-matrix" aria-label="전체 TCG 수집 결과">'
        '<h2>전체 TCG · 국가별 실제 수집·반영 점검</h2>'
        '<p>등록 ' + str(value['registered_games']) + '종 · 검색 대상 ' +
        str(value['search_cells']) + '개 국가 조합 · 기존 저장 ' +
        (str(value['saved_total']) + '건' if value['saved_total'] is not None
         else '확인 보류') + '</p>'
        '<p role="note">' + esc(' '.join(status_parts)) + '</p>' +
        ''.join('<p role="alert">' + esc(x) + '</p>' for x in messages) +
        ''.join(rows) + '</section>'
    )
