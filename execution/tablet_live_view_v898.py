"""Read-only bounded card view; partial evidence never becomes a stored match.

Collectors keep the original strict read_live/unified_feed defaults. Page GETs
do not run photo compression, persist canonical entities or perform collection.
"""
import html

import tablet_image_library_v1 as library
from execution.tablet_catalog_bridge import build_report
from execution.tablet_entity_store_v892 import project
from execution.tablet_event_summary_v890 import read_event_summary
from execution.tablet_image_unified_v888 import unified_feed
from execution.tablet_unified_ui_v890 import render_card, render_document

VIEW_STATES = {'COMPLETE', 'PARTIAL_READ_ONLY'}


class ViewUnavailable(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def read_view(repo):
    report = build_report(repo)
    if not isinstance(report, dict) or report.get('ok') is not True:
        raise ViewUnavailable('CATALOG_READ_FAILED')
    try:
        rows = unified_feed(report, allow_partial_display=True)
    except (OSError, ValueError, TypeError) as exc:
        raise ViewUnavailable('FEED_INVALID') from exc
    partial = bool(report.get('source_errors') or report['summary'].get('source_limit_reached'))
    # Never reconcile a truncated subset or project old fields into that subset.
    if not partial:
        try:
            rows = project(rows, library.storage_root())
        except (OSError, ValueError, TypeError) as exc:
            raise ViewUnavailable('ENTITY_STATE_INVALID') from exc
    return {'view_state': 'PARTIAL_READ_ONLY' if partial else 'COMPLETE',
            'rows': rows, 'events': read_event_summary(repo),
            'source_limit_reached': bool(report['summary'].get('source_limit_reached')),
            'source_error_count': len(report.get('source_errors', []))}


def render_live(view):
    if not isinstance(view, dict) or view.get('view_state') not in VIEW_STATES or not isinstance(view.get('rows'), list) or len(view['rows']) > library.MAX_RECORDS + 1500:
        raise ValueError('통합 화면 자료 검증 필요')
    cards, display_rows = [], []
    partial = view['view_state'] == 'PARTIAL_READ_ONLY'
    for row in view['rows']:
        picture = '<p>사진 보완 대기</p>'
        display_row = dict(row)
        if partial:
            # A partial collection can never supply a verified photo/facts
            # pair, even if a stale caller passes a VERIFIED_PAIR status.
            display_row['link_status'] = 'SOURCE_COVERAGE_INCOMPLETE'
            display_row['display_only'] = True
        if row.get('image_id'):
            image_id = row['image_id']
            if not isinstance(image_id, str) or not library.ID_PATTERN.fullmatch(image_id):
                raise ValueError('사진 식별정보 확인 필요')
            # A verified local ID, never the cached URL, controls the photo
            # link. Retain the original row and photo bytes untouched.
            original_url = '/api/local-card-images/file/' + image_id
            display_row['image_url'] = original_url
            picture = '<img loading="lazy" decoding="async" alt="카드 사진" src="/api/local-card-images/display/' + image_id + '" data-original="' + original_url + '"><p>표시용 사진 · 원본 확대 가능</p>'
        card_html = render_card(display_row, picture)
        photo_id = row.get('image_id')
        grade_allowed = (
            not partial and row.get('kind') in ('CARD', 'PROMO')
            and row.get('link_status') == 'VERIFIED_PAIR'
            and (row.get('display_only') is None or row.get('display_only') is False)
            and isinstance(photo_id, str)
            and library.ID_PATTERN.fullmatch(photo_id) is not None
        )
        if not grade_allowed:
            # The historical renderer always emits grading links. Remove
            # them server-side; a banner or JavaScript click guard alone is
            # insufficient when the saved source/identity is untrusted.
            links = ('<a href="/index.html?feature=auto-grade">등급 측정</a>'
                     ' · <a href="/index.html?feature=grading-economics">등급별 판매가 확인</a>')
            if card_html.count(links) != 1:
                raise ValueError('카드 등급 링크 화면 계약 불일치')
            card_html = card_html.replace(
                links, '<span>카드 원본·출처·판본 확인 전 등급·시세 연결 보류</span>', 1)
            card_html = card_html.replace('<article ', '<article data-card-actions-blocked="true" ', 1)
        cards.append(card_html)
        display_rows.append(display_row)
    page = render_document(cards, display_rows, live=True, events=view.get('events'))
    fallback = '''<script>document.addEventListener('error',event=>{const img=event.target;if(!(img instanceof HTMLImageElement)||!img.dataset.original)return;if(!img.dataset.originalTried){img.dataset.originalTried='1';img.src=img.dataset.original;}else{img.hidden=true;const caption=img.nextElementSibling;if(caption)caption.textContent='사진 표시 확인 필요 · 원본 확대에서 확인하세요';}},true);</script>'''
    page = page.replace('<main>', fallback + '<main>', 1)
    state = view['view_state']
    page = page.replace('<html lang="ko">', '<html lang="ko" data-tcg-view-state="' + state + '">', 1)
    if state == 'PARTIAL_READ_ONLY':
        message = ('일부 자료만 표시 중입니다. 출처 읽기 오류 ' + str(view.get('source_error_count', 0))
                   + '건 · 목록 한도 ' + ('도달' if view.get('source_limit_reached') else '미도달')
                   + '. 누적 자료는 보존했으며 이 부분 목록으로 자동 연결·저장·학습하지 않습니다.')
        page = page.replace('</header>', '</header><section class="events" role="status"><h2>자료 확인 보류</h2><p>' + html.escape(message) + '</p></section>', 1)
    return page
