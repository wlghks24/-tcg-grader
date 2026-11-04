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
    cards = []
    for row in view['rows']:
        picture = '<p>사진 보완 대기</p>'
        if row.get('image_id'):
            image_id = row['image_id']
            if not isinstance(image_id, str) or not library.ID_PATTERN.fullmatch(image_id):
                raise ValueError('사진 식별정보 확인 필요')
            picture = '<img loading="lazy" decoding="async" alt="카드 사진" src="/api/local-card-images/display/' + image_id + '" data-original="/api/local-card-images/file/' + image_id + '"><p>표시용 사진 · 원본 확대 가능</p>'
        cards.append(render_card(row, picture))
    page = render_document(cards, view['rows'], live=True, events=view.get('events'))
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
