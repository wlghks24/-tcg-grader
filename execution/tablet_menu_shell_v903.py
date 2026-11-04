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

# CSS is part of this integrity-pinned Python module, rather than an
# unregistered asset type in the protected repository manifest.
STYLE = r"""
body[data-tcg903-shell]{--tcg903-line:#e1e8ed;--tcg903-muted:#72808c;margin:0!important;padding:72px 0 20px!important;background:#f4f7f8!important;color:#21323d}
body[data-tcg903-shell] #featureCategories,body[data-tcg903-shell] #featureCategoryFab,body[data-tcg903-shell] #tcgAppBottomDock,body[data-tcg903-shell] .feature-category-fab,body[data-tcg903-shell] main.app>.app-title{display:none!important}
body[data-tcg903-shell]:not([data-tcg903-view="legacy"])>:not(#tcg903-top):not(#tcg903-drawer):not(#tcg903-backdrop):not(#tcg903-panels):not(#tcg903-status):not(script):not(style):not(link){display:none!important}
body[data-tcg903-shell][data-tcg903-view="legacy"]>main.app{max-width:1180px;margin:auto;padding:16px!important}
body[data-tcg903-shell] [data-tcg-migration-target]{scroll-margin-top:92px}
#tcg903-top,#tcg903-drawer,#tcg903-panels,#tcg903-status{font:16px/1.6 system-ui,sans-serif;box-sizing:border-box;color:#21323d}
#tcg903-top *,#tcg903-drawer *,#tcg903-panels *{box-sizing:border-box}
#tcg903-top{position:fixed;inset:0 0 auto;z-index:1200;height:68px;display:flex;align-items:center;gap:14px;padding:10px 20px;background:#fffffff2;border-bottom:1px solid var(--tcg903-line);backdrop-filter:blur(12px)}
#tcg903-top>a{font-weight:800;color:#20352f;text-decoration:none;font-size:18px;overflow-wrap:anywhere}
#tcg903-top>span{margin-left:auto;font-size:12px;color:var(--tcg903-muted)}
#tcg903-toggle,#tcg903-close{font:inherit;min-width:46px;min-height:46px;width:auto;margin:0;border:0;border-radius:12px;background:#eff4f2;color:#263f38;cursor:pointer;flex-shrink:0}
#tcg903-drawer{position:fixed;inset:0 auto 0 0;width:min(86vw,320px);z-index:1400;overflow:auto;overscroll-behavior:contain;padding:0 16px 26px;background:white;border-right:1px solid var(--tcg903-line);box-shadow:12px 0 40px #122d4914;transform:translateX(-105%);visibility:hidden;transition:transform .18s ease,visibility .18s}
body[data-tcg903-menu="open"] #tcg903-drawer{transform:none;visibility:visible}
#tcg903-backdrop{position:fixed;inset:0;z-index:1300;background:#12213966;border:0;border-radius:0;width:100%;height:100%;padding:0;margin:0}
#tcg903-backdrop[hidden],#tcg903-panels [hidden]{display:none!important}
#tcg903-drawer .tcg903-brand{display:flex;align-items:center;gap:12px;padding:24px 0 20px;border-bottom:1px solid var(--tcg903-line);margin-bottom:12px}
#tcg903-drawer .tcg903-brand>span{display:grid;place-items:center;width:46px;height:46px;border-radius:15px;color:white;background:linear-gradient(140deg,#358d7e,#19584d);font-size:26px}
#tcg903-drawer small{display:block;font-size:11px;color:var(--tcg903-muted)}
#tcg903-close{margin-left:auto}
#tcg903-drawer nav>a,#tcg903-drawer .tcg903-group>a,#tcg903-advanced>a{display:flex;align-items:center;min-height:48px;padding:10px 12px;margin:2px 0;border-radius:10px;color:#293b41;text-decoration:none;font-size:15px;font-weight:550;overflow-wrap:anywhere;word-break:keep-all}
#tcg903-drawer a:hover,#tcg903-drawer a[aria-current="page"]{background:#eaf5f0;color:#086b58}
#tcg903-drawer .tcg903-group{margin-top:16px;border-top:1px solid #edf1ef;padding-top:10px}
#tcg903-drawer h2{font-size:12px;font-weight:600;letter-spacing:.04em;color:#85918d;margin:6px 12px}
#tcg903-advanced{border-top:1px solid var(--tcg903-line);margin-top:16px;padding-top:12px}
#tcg903-advanced summary{cursor:pointer;min-height:48px;padding:10px;font-size:14px}
#tcg903-status{max-width:1180px;margin:0 auto;padding:0 18px;font-size:14px;color:#9b471c}
#tcg903-status:empty{display:none}
#tcg903-panels{max-width:1180px;margin:auto;padding:22px}
#tcg903-panels h1{font-size:clamp(24px,3.2vw,32px);line-height:1.3;letter-spacing:-.035em;margin:3px 0 8px;color:#20352f;word-break:keep-all}
#tcg903-panels p{color:var(--tcg903-muted);overflow-wrap:anywhere}
#tcg903-panels a{color:#126f60;text-underline-offset:4px}
#tcg903-panels .tcg903-heading{display:flex;justify-content:space-between;align-items:center;gap:16px}
#tcg903-panels .tcg903-heading p{margin:4px 0;font-size:13px}
#tcg903-panels .tcg903-kicker{font-size:10px;font-weight:750;letter-spacing:.16em;color:#41826d}
#tcg903-panels .tcg903-total{font-size:12px;padding:8px 12px;border-radius:10px;background:#e9f1ec;color:#386a56;white-space:nowrap}
#tcg903-panels .tcg903-quick{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:20px 0}
#tcg903-panels .tcg903-quick a{display:flex;align-items:center;justify-content:center;min-height:54px;padding:10px;background:#fff;border:1px solid #dce7e2;border-radius:13px;font-size:14px;font-weight:700;text-decoration:none;text-align:center;color:#2b4d40;word-break:keep-all}
#tcg903-panels .tcg903-quick a:first-child{background:#1b705a;border-color:#1b705a;color:white}
#tcg903-panels input,#tcg903-panels select,#tcg903-panels button{font:inherit;min-height:46px;max-width:100%;border:1px solid #d7e1df;border-radius:10px;padding:9px 12px;background:white;color:#2d423c}
#tcg903-panels button{width:auto;margin:0;cursor:pointer}
#tcg903-panels button:disabled{opacity:.45;cursor:default}
#tcg903-panels .tcg903-filters{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:12px}
#tcg903-panels .tcg903-filters label{display:grid;gap:4px;font-size:11px;color:var(--tcg903-muted);flex:1;min-width:140px}
#tcg903-panels .tcg903-filters label:first-child{flex:2}
#tcg903-panels input{width:100%;margin:0}
#tcg903-countries{display:flex;flex-wrap:wrap;gap:8px}
#tcg903-countries button[aria-pressed="true"]{background:#1b705a;color:white;border-color:#1b705a}
#tcg903-count{font-size:12px;margin:12px 0}
#tcg903-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,245px),1fr));gap:16px}
#tcg903-grid article{display:grid;grid-template-rows:auto 1fr;min-width:0;overflow:hidden;border:1px solid var(--tcg903-line);border-radius:18px;background:white;box-shadow:0 4px 16px #152d4a04}
#tcg903-grid .art{background:#ebf0ed;padding:18px;min-height:224px;display:flex;flex-direction:column;align-items:center;justify-content:center}
#tcg903-grid img{width:auto;height:190px;max-width:100%;object-fit:contain;filter:drop-shadow(0 7px 8px #152d491c)}
#tcg903-grid .art p{font-size:10px;margin:8px 0 0}
#tcg903-grid .card-body{padding:16px}
#tcg903-grid h2{font-size:17px;line-height:1.45;margin:8px 0;overflow-wrap:anywhere;word-break:keep-all}
#tcg903-grid .eyebrow{font-size:10px;color:#72867b}
#tcg903-grid .badge{display:inline-block;font-size:11px;padding:4px 8px;border-radius:8px;background:#eef6f1;color:#356c53}
#tcg903-grid dl{display:grid;grid-template-columns:1fr 1fr;gap:10px}
#tcg903-grid dt{font-size:10px;color:#7d8a83}
#tcg903-grid dd{font-size:12px;margin:0;overflow-wrap:anywhere}
#tcg903-grid p,#tcg903-grid details,#tcg903-grid footer{font-size:12px}
#tcg903-grid summary{min-height:44px;padding:10px 0;cursor:pointer}
#tcg903-grid footer{display:flex;justify-content:space-between;gap:8px;border-top:1px solid #e7edef;padding-top:12px}
#tcg903-panels .tcg903-pagination{display:flex;align-items:center;justify-content:center;gap:16px;margin:20px 0}
#tcg903-panels .tcg903-events-preview,#tcg903-panels .tcg903-maintenance,#tcg903-events article,#tcg903-events details{background:white;border:1px solid var(--tcg903-line);border-radius:14px;padding:16px;margin:14px 0}
#tcg903-panels .tcg903-events-preview summary,#tcg903-panels .tcg903-maintenance summary{min-height:44px;cursor:pointer;font-weight:650}
#tcg903-panels .tcg903-events-preview li{font-size:14px;margin:12px 0}
#tcg903-panels .tcg903-events-preview small{display:block;font-size:11px;color:var(--tcg903-muted)}
#tcg903-events h2{font-size:19px}
#tcg903-events table{width:100%;table-layout:fixed;font-size:12px;overflow-wrap:anywhere}
#tcg903-events td,#tcg903-events th{padding:7px 3px;border-bottom:1px solid #edf0f2;text-align:left}
#tcg903-events form{display:flex;flex-wrap:wrap;gap:8px}
#tcg903-events form select{flex:1;min-width:100px}
#tcg903-top :focus-visible,#tcg903-drawer :focus-visible,#tcg903-panels :focus-visible{outline:3px solid #d3932b;outline-offset:3px}
@media(min-width:1100px){body[data-tcg903-shell]{padding-left:280px!important}#tcg903-top{left:280px}#tcg903-drawer{width:280px;transform:none;visibility:visible;box-shadow:none}#tcg903-toggle,#tcg903-close,#tcg903-backdrop{display:none!important}}
@media(max-width:600px){#tcg903-top{padding:10px 12px;gap:10px}#tcg903-top>a{font-size:14px}#tcg903-top>span{display:none}#tcg903-panels{padding:16px}#tcg903-panels .tcg903-quick{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}#tcg903-panels .tcg903-quick a{font-size:13px;min-height:48px}}
@media(prefers-reduced-motion:reduce){#tcg903-drawer{transition:none}}
"""


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
    css = '<style id="tcg903-style">' + STYLE + '</style>'
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
