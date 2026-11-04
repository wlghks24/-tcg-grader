"""A single tablet workspace: gallery on home, existing tools in a side menu.

Read-only presentation. Original IDs, controls and script bytes are retained.
No collection, photo encoding, storage writes, training or grade changes on GET.
"""
import base64
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urlencode

from execution.tablet_feature_inventory_v894 import annotate, inventory, read_source


class Boundaries(HTMLParser):
    """Actual markup offsets; ignore closing-tag strings inside old scripts."""
    def __init__(self, source):
        super().__init__(convert_charrefs=False)
        self.lines = [0] + [i + 1 for i, c in enumerate(source) if c == '\n']
        self.points = {}
        self.feed(source)

    def pos(self):
        line, col = self.getpos()
        return self.lines[line - 1] + col

    def handle_starttag(self, tag, attrs):
        if tag in ('html', 'body'):
            self.points.setdefault(tag, (self.pos(), self.get_starttag_text()))

    def handle_endtag(self, tag):
        if tag in ('head', 'body'):
            self.points.setdefault('/' + tag, (self.pos(), '</' + tag + '>'))


class Shortcuts(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.rows, self.row, self.small = [], None, 0
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and 'feature-shortcut' in attrs.get('class', '').split():
            key, href = attrs.get('data-feature-key', ''), attrs.get('href', '')
            if key and href.startswith('#'):
                self.row = {'key':key, 'target':href[1:], 'label':''}
        if tag == 'small':
            self.small += 1

    def handle_data(self, data):
        if self.row is not None and not self.small:
            self.row['label'] += data

    def handle_endtag(self, tag):
        if tag == 'small':
            self.small = max(0, self.small - 1)
        if tag == 'a' and self.row is not None:
            self.row['label'] = ' '.join(self.row['label'].split())
            self.rows.append(self.row)
            self.row = None


GROUPS = (
    ('카드', ('auto-grade', 'manual-photo', 'precision-grade', 'card-ocr', 'verified-grade')),
    ('시세 · BOX', ('market-search', 'grading-economics', 'trading-catalog', 'box-knowledge', 'box-hit-analysis')),
    ('소식 · 구매처', ('promo-event-info', 'release-info', 'purchase-finder', 'purchase-distance')),
    ('학습 · 관리', ('learning-status', 'tablet-manager', 'code-audit', 'code-validation')),
)


def link(label, **query):
    return '<a data-tcg903-link href="/index.html?' + html.escape(urlencode(query), quote=True) + '">' + html.escape(label) + '</a>'


def navigation(source):
    rows = Shortcuts(source).rows
    report = inventory(source)
    by_key = {r['key']:r for r in rows}
    groups, seen = [], set()
    for title, keys in GROUPS:
        links = []
        for key in keys:
            if key in by_key:
                links.append(link(by_key[key]['label'], feature=key))
                seen.add(key)
        groups.append('<div class="tcg903-group"><h2>' + title + '</h2>' + ''.join(links) + '</div>')
    extra = ''.join(link(r['label'], feature=r['key']) for r in rows if r['key'] not in seen)
    advanced = ''.join(link(r['label'], target=r['id']) for r in report['items'])
    menu = ''.join(groups) + extra + '<details id="tcg903-advanced"><summary>전체 세부 기능 · ' + str(len(report['items'])) + '개</summary>' + advanced + '<a href="/tablet_market_hub_v881.html">이전 통합 도구 · 로컬 보관함</a></details>'
    return menu, {'features':{r['key']:r['target'] for r in rows}, 'targets':[r['id'] for r in report['items']], 'controls':report['controls']}


def gallery(repo):
    try:
        from execution.tablet_live_view_v898 import read_view, render_live
        from execution.tablet_catalog_bridge import safe_url
        view = read_view(Path(repo))
        document = render_live(view)
        cards = document.split('<main>', 1)[1].split('</main>', 1)[0]
        games = sorted({r['game_id'] for r in view['rows']})
        options = ''.join('<option>' + html.escape(g) + '</option>' for g in games)
        preview = []
        events = view.get('events', {})
        if events.get('ok') is True:
            for event in [r for r in events.get('rows', []) if not r.get('archived')][:3]:
                source = safe_url(event.get('source'))
                label = html.escape(event['name'])
                if source:
                    label = '<a href="' + html.escape(source, quote=True) + '" target="_blank" rel="noopener noreferrer">' + label + '</a>'
                preview.append('<li>' + label + ' <small>' + html.escape(event.get('date_label') or event.get('start_date') or '일정 확인 필요') + ' · ' + html.escape(event.get('evidence_state', 'UNVERIFIED')) + '</small></li>')
        return {'state':view['view_state'], 'cards':cards, 'options':options, 'count':len(view['rows']), 'events':''.join(preview)}
    except (OSError, ValueError, TypeError, UnicodeError):
        return {'state':'UNAVAILABLE', 'cards':'', 'options':'', 'count':None, 'events':''}


def event_fragment(repo, options):
    try:
        from execution.tablet_event_coverage_v896 import render
        page = render(repo, game_id=options.get('game', [''])[0], region=options.get('region', [''])[0])
        return page.split('</style>', 1)[1].rsplit('</html>', 1)[0]
    except (OSError, ValueError, TypeError, UnicodeError):
        return '<p role="alert">행사 수집 현황 읽기 보류 · 기존 행사·프로모 정보는 메뉴에서 확인하세요.</p>'


def home(data):
    state = data['state']
    warning = '<p role="status">일부 자료만 표시 중 · 이 부분 목록으로 자동 연결·저장·학습하지 않습니다.</p>' if state == 'PARTIAL_READ_ONLY' else '<p role="alert">카드 자료 읽기 보류 · 원본 보존. 촬영·관리 등 다른 메뉴는 계속 사용할 수 있습니다.</p>' if state == 'UNAVAILABLE' else ''
    quick = link('촬영 · 카드 등록', feature='auto-grade') + link('시세 확인', feature='market-search') + link('BOX · HIT', feature='box-knowledge') + link('행사 · 프로모', feature='promo-event-info')
    countries = ''.join('<button type="button" data-tcg903-country="' + code + '" aria-pressed="' + ('false' if code else 'true') + '">' + label + '</button>' for code,label in [('', '전체'),('KR','한판'),('JP','일판'),('US','미판'),('CN','중판')])
    events = '<details class="tcg903-events-preview"><summary>행사 · 콜라보 · 영화 · 프로모</summary><ul>' + data['events'] + '</ul>' + link('전체 행사 정보', feature='promo-event-info') + link('전체 게임 수집 현황', pane='events') + '</details>'
    return '''<section id="tcg903-home" class="tcg903-panel"><div class="tcg903-heading"><div><p class="tcg903-kicker">MY TCG WORKSPACE</p><h1>카드 라이브러리</h1><p>사진과 카드정보 · BOX · 국가별 시세</p></div><span class="tcg903-total">''' + (str(data['count']) + '개 자료' if data['count'] is not None else '자료 확인 보류') + '''</span></div><div class="tcg903-quick">''' + quick + '''</div>''' + warning + '''<div class="tcg903-filters"><label>카드명·번호·세트<input id="tcg903-query" type="search" placeholder="카드명이나 번호 검색"></label><label>게임<select id="tcg903-game"><option value="">전체 게임</option>''' + data['options'] + '''</select></label><label>상품<select id="tcg903-kind"><option value="">카드·BOX 전체</option><option value="CARD">카드·프로모</option><option value="PRODUCT">BOX·팩·상품</option></select></label></div><div id="tcg903-countries" role="group" aria-label="판본 선택">''' + countries + '''</div><p id="tcg903-count" role="status">공개 수집 도감 · 사진 수는 보유 수량이 아닙니다.</p><div id="tcg903-grid"></div><div class="tcg903-pagination"><button id="tcg903-prev" type="button">이전</button><span id="tcg903-page"></span><button id="tcg903-next" type="button">다음</button></div>''' + events + '''<details class="tcg903-maintenance"><summary>수집 · 자료 갱신</summary><button id="tcg903-collect" type="button">사진·카드정보 보완 수집</button><button id="tcg903-refresh" type="button">출시·행사·시세 갱신</button><p id="tcg903-job" role="status"></p></details><template id="tcg903-cards">''' + data['cards'] + '</template></section>'


def compose(repo, *, options=None, initial='home', document=None, compatibility=False):
    options = options or {}
    source = read_source(repo)
    document = annotate(source) if document is None else document
    if 'id="tcg903-' in document:
        raise ValueError('duplicate menu shell')
    menu, config = navigation(source)
    data = gallery(repo)
    config.update(initial=initial, compatibility=compatibility, viewState=data['state'])
    primary = link('홈 · 카드와 이미지', pane='home') + link('카드 도감', pane='home', kind='CARD') + link('BOX·팩 도감', pane='home', kind='PRODUCT') + link('전체 TCG · 행사·콜라보·영화·프로모', pane='events')
    chrome = '''<header id="tcg903-top"><button id="tcg903-toggle" type="button" aria-controls="tcg903-drawer" aria-expanded="false" aria-label="전체 메뉴 열기">☰ <span>메뉴</span></button><a href="/index.html?pane=home" data-tcg903-link>TCG 카드·BOX 라이브러리</a><span id="tcg903-title">홈</span></header><button id="tcg903-backdrop" type="button" aria-label="메뉴 닫기" hidden></button><aside id="tcg903-drawer" aria-label="전체 메뉴" tabindex="-1"><div class="tcg903-brand"><span aria-hidden="true">✦</span><div><b>TCG 카드</b><small>태블릿 로컬 라이브러리</small></div><button id="tcg903-close" type="button" aria-label="메뉴 닫기">✕</button></div><nav aria-label="기능 메뉴">''' + primary + menu + '''</nav></aside><p id="tcg903-status" role="status" aria-live="polite"></p><div id="tcg903-panels">''' + home(data) + '<section id="tcg903-events" class="tcg903-panel" hidden>' + link('기존 행사·프로모 정보', feature='promo-event-info') + event_fragment(repo, options) + '</section></div>'
    root = Path(__file__).parent
    css = '<style id="tcg903-style">' + (root/'tablet_menu_shell_v903.css').read_text(encoding='utf-8') + '</style>'
    script = (root/'tablet_menu_shell_v903.js').read_text(encoding='utf-8')
    config_text = json.dumps(config, ensure_ascii=False).replace('<','\\u003c').replace('&','\\u0026')
    boot = '<script id="tcg903-config" type="application/json">' + config_text + '</script><script>' + script + '</script>'
    digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode('ascii')
    def allow_boot(match):
        policy = match.group(1)
        if "'unsafe-inline'" in policy and "'sha256-" not in policy and "'nonce-" not in policy:
            return policy  # One hash would disable the existing unsafe-inline policy.
        return policy + " 'sha256-" + digest + "'"
    document = re.sub(r'(script-src\s+[^;\"]+)', allow_boot, document, count=1)
    points = Boundaries(document).points
    if 'body' not in points:
        raise ValueError('legacy body unavailable')
    offset, opening = points['body']
    edits = [(offset, len(opening), opening[:-1] + ' data-tcg903-shell="true" data-tcg903-view="home">' + chrome)]
    if 'html' in points:
        offset, opening = points['html']
        edits.append((offset, len(opening), opening[:-1] + ' data-tcg-view-state="' + html.escape(data['state'], quote=True) + '">'))
    edits.append((points.get('/head', points['body'])[0], 0, css))
    edits.append((points.get('/body', (len(document),''))[0], 0, boot))
    for offset, size, replacement in sorted(edits, reverse=True):
        document = document[:offset] + replacement + document[offset+size:]
    return document
