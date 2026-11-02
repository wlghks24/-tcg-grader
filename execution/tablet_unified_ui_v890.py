"""Accessible card/BOX presentation. Evidence values only; no price/grade inference."""
import html
from execution.tablet_catalog_bridge import safe_url

LABELS = {'KR': '한국판', 'JP': '일본판', 'US': '미국판', 'CN-S': '중국 간체판', 'CN-T': '중국 번체판'}
STATUS = {'VERIFIED_PAIR': '사진·정보 연결됨', 'NEEDS_IMAGE': '사진 보완 중',
          'NEEDS_EXACT_IDENTITY': '정확한 카드 확인 필요', 'METADATA_CONFLICT': '정보 충돌 확인 필요'}


def render_card(row, picture):
    esc = html.escape
    metadata = row['card_metadata']
    facts = [('카드번호', metadata.get('card_code') or metadata.get('card_number')),
             ('세트', metadata.get('set_name') or metadata.get('set_code')),
             ('세대', metadata.get('generation')), ('판본', metadata.get('printing')),
             ('언어', metadata.get('language')), ('희귀도', metadata.get('rarity'))]
    work_labels = {'COLLECT_EXACT_IMAGE':'사진 수집 필요', 'ENRICH_EXACT_METADATA':'카드정보 보완 필요', 'VERIFY_EXACT_IDENTITY':'동일 카드 확인 필요', 'RECONFIRM_RETAINED_FIELDS':'누적 정보 재확인 필요'}
    work_html = '<p>' + ' · '.join(work_labels.get(w.get('action'), '자료 확인 필요') for w in row.get('work_items', [])) + '</p>' if row.get('work_items') else ''
    facts_html = ''.join('<div><dt>' + label + '</dt><dd>' + esc(str(value or '확인 필요')) + '</dd></div>' for label, value in facts)
    source = safe_url(row.get('source_url'))
    link = '<a href="' + esc(source, quote=True) + '" target="_blank" rel="noopener noreferrer">근거 출처 ↗</a>' if source else '<span>출처 확인 필요</span>'
    original = '<a href="' + esc(row['image_url'], quote=True) + '" target="_blank" rel="noopener">원본 확대 ↗</a>' if row.get('image_id') else ''
    status = STATUS.get(row['link_status'], '확인 필요')
    if row.get('retained_fields'): status += ' · 누적 정보 재확인 필요'
    return '<article data-region="' + esc(row['region'], quote=True) + '" data-game="' + esc(row['game_id'], quote=True) + '" data-kind="' + esc(row['kind'], quote=True) + '"><div class="art">' + picture + '</div><div class="card-body"><div class="eyebrow">' + esc(LABELS.get(row['region'], row['region']) + ' · ' + row['game_id'] + ' · ' + row['kind']) + '</div><h2>' + esc(row['name']) + '</h2><span class="badge">' + status + '</span>' + work_html + '<dl>' + facts_html + '</dl><details><summary>등급·판매가·출처 보기</summary><p>등급 측정 전 · 정확한 판본의 거래자료 확인 필요</p><p>출시일 ' + esc(str(row.get('observed_release_date') or '미확인')) + ' · 출처 확인 ' + esc(str(row.get('source_checked_at') or '미확인')) + '</p><a href="/index.html?feature=auto-grade">등급 측정</a> · <a href="/index.html?feature=grading-economics">등급별 판매가 확인</a></details><footer>' + original + link + '</footer></div></article>'


def render_document(cards, rows, *, live=False, events=None):
    esc = html.escape
    connection = "'self'" if live else "'none'"
    games = sorted({r['game_id'] for r in rows})
    connected = sum(r['link_status'] == 'VERIFIED_PAIR' for r in rows)
    event_html = ''
    if isinstance(events, dict):
        if events.get('ok') is not True:
            event_html = '<section class="events"><h2>행사·콜라보</h2><p>행사 자료를 읽지 못했습니다. 0건으로 처리하지 않았습니다.</p><a href="/index.html?feature=promo-event-info">기존 행사 보기 →</a></section>'
        else:
            labels = {'CURRENT': '일정상 진행 기간', 'UPCOMING': '예정 일정', 'TRACKING': '발표 추적', 'RECENTLY_ENDED': '최근 종료', 'ARCHIVED': '지난 행사', 'UNKNOWN_DATE': '일정 미확인'}
            evidence = {'FRESH_OFFICIAL': '공식 출처 최근 확인', 'STALE_OFFICIAL': '출처 재확인 필요', 'UNVERIFIED': '검증 대기', 'INVALID_SOURCE': '출처 확인 필요', 'UNKNOWN_FRESHNESS': '갱신일 미확인'}
            candidates = [x for x in events.get('rows', []) if not x.get('archived')]
            candidates.sort(key=lambda x: ({'CURRENT': 0, 'UPCOMING': 1, 'TRACKING': 2}.get(x['lifecycle'], 3), x.get('start_date') or '9999'))
            tiles = []
            for event in candidates[:8]:
                source = safe_url(event.get('source'))
                source_link = '<a href="' + esc(source, quote=True) + '" target="_blank" rel="noopener noreferrer">공식·근거 출처 ↗</a>' if source else ''
                date = event.get('date_label') or ' ~ '.join(filter(None, (event.get('start_date'), event.get('end_date')))) or '일정 확인 필요'
                tiles.append('<div class="event-tile"><span class="eyebrow">' + esc(event['region'] + ' · ' + event['game'] + ' · ' + event['category']) + '</span><h3>' + esc(event['name']) + '</h3><p>' + esc(date) + '</p><span class="badge">' + labels.get(event['lifecycle'], '일정 확인 필요') + '</span><p>' + evidence.get(event['evidence_state'], '확인 필요') + ' · ' + esc(event.get('source_checked_at') or '확인일 없음') + '</p>' + source_link + '</div>')
            summary = events.get('summary') or {}
            event_html = '<section class="events"><h2>놓치지 말아야 할 행사·콜라보</h2><p>자료 ' + str(summary.get('loaded_rows', 0)) + '건 · 지난 행사 ' + str(summary.get('lifecycle_counts', {}).get('ARCHIVED', 0)) + '건 보존 · 일정과 출처 최신성은 별도 확인</p><div class="event-grid">' + ''.join(tiles) + '</div><a href="/index.html?feature=promo-event-info">지난 행사 포함 전체 보기 →</a></section>'
    return '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; connect-src ''' + connection + '''; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><title>TCG 카드·BOX 라이브러리</title><style>
:root{--ink:#172c35;--muted:#60757d;--line:#dce6e8;--green:#087f69;--paper:#f3f7f6}*{box-sizing:border-box}body{font:16px/1.6 system-ui,sans-serif;color:var(--ink);background:var(--paper);margin:0}header,main,.events,.filters{max-width:1180px;margin:auto}header{padding:30px 24px 20px}h1{font-size:clamp(26px,4vw,38px);line-height:1.25;margin:12px 0}h2{font-size:19px;line-height:1.45;word-break:keep-all;overflow-wrap:anywhere;margin:10px 0}p{color:var(--muted)}a{color:var(--green);font-weight:650;text-underline-offset:4px}button,select,input{font:inherit;border:1px solid var(--line);border-radius:12px;min-height:46px;padding:10px 14px;background:white;color:var(--ink)}button{cursor:pointer;background:var(--green);color:white}a:focus-visible,button:focus-visible,summary:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid #e9a92e;outline-offset:3px}summary{cursor:pointer;min-height:44px;padding:8px 0}header>details{background:white;border:1px solid var(--line);border-radius:14px;padding:8px 16px}header nav{display:flex;flex-wrap:wrap;gap:8px}.eyebrow{font-size:12px;letter-spacing:.035em;color:var(--muted)}.hero{display:flex;justify-content:space-between;align-items:center;gap:20px}.stats{display:flex;gap:12px;flex-wrap:wrap}.stat{background:white;border:1px solid var(--line);border-radius:14px;padding:12px 20px}.stat b{display:block;font-size:25px}.filters{padding:16px 24px;display:flex;flex-wrap:wrap;gap:10px}.filters label{display:grid;gap:3px;font-size:13px;color:var(--muted)}.filters input{min-width:230px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:20px;padding:10px 24px 36px}article{display:grid;grid-template-rows:auto 1fr;background:white;border:1px solid var(--line);border-radius:20px;overflow:hidden;box-shadow:0 5px 18px #173a2e05}article[hidden]{display:none}.art{background:#eaf0ee;min-height:200px;display:flex;align-items:center;justify-content:center;flex-direction:column;padding:18px}.art img{max-width:100%;width:auto;height:260px;object-fit:contain;filter:drop-shadow(0 7px 7px #0002)}.art p{font-size:12px;margin:8px 0 0;text-align:center}.card-body{padding:18px}.badge{display:inline-block;background:#ecf7f2;color:#136e54;font-size:12px;border-radius:999px;padding:4px 10px}dl{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:18px 0}dt{color:var(--muted);font-size:12px}dd{margin:0;font-size:14px;overflow-wrap:anywhere}footer{display:flex;justify-content:space-between;gap:12px;border-top:1px solid var(--line);padding-top:14px;margin-top:14px;font-size:13px}.events{padding:16px 24px}.event-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));gap:12px}.event-tile{padding:16px;background:white;border:1px solid var(--line);border-radius:16px}.event-tile h3{font-size:16px;line-height:1.5;margin:8px 0}.event-tile p{font-size:12px;margin:8px 0}.count{max-width:1180px;margin:auto;padding:0 24px;color:var(--muted);font-size:14px}@media(max-width:600px){header{padding:20px 16px}.hero{display:block}main{padding:10px 16px}.filters{padding:16px}.stat{padding:8px 14px}.art img{height:230px}}
</style><header><div class="eyebrow">MY TCG COLLECTION</div><div class="hero"><div><h1>사진으로 찾고,<br>정보를 함께 확인하세요.</h1><p>카드와 BOX를 한곳에서 · 원본 사진 보존</p></div><div class="stats"><div class="stat"><b>''' + str(len(rows)) + '''</b>등록 항목</div><div class="stat"><b>''' + str(connected) + '''</b>사진·정보 연결</div></div></div></header>''' + event_html + '''<section class="filters" aria-label="보관함 검색"><label>카드 검색<input id="query" type="search" placeholder="카드명·번호·세트 검색"></label><label>국가<select id="region"><option value="">전체 국가</option><option value="KR">한국판</option><option value="JP">일본판</option><option value="US">미국판</option><option value="CN">중국판</option></select></label><label>게임<select id="game"><option value="">전체 게임</option>''' + ''.join('<option>' + esc(g) + '</option>' for g in games) + '''</select></label><label>상품 종류<select id="kind"><option value="">카드·BOX 전체</option><option value="CARD">카드</option><option value="PRODUCT">BOX·팩·상품</option></select></label></section><p class="count" id="count" aria-live="polite"></p><main>''' + ''.join(cards) + '''</main><script>const region=document.getElementById('region'),game=document.getElementById('game'),kind=document.getElementById('kind'),query=document.getElementById('query');function filter(){let count=0;document.querySelectorAll('article').forEach(row=>{const country=region.value==='CN'?row.dataset.region.startsWith('CN-'):(!region.value||row.dataset.region===region.value);const card=['CARD','PROMO'].includes(row.dataset.kind);row.hidden=!(country&&(!game.value||row.dataset.game===game.value)&&(!kind.value||(kind.value==='CARD'?card:!card))&&(!query.value||row.textContent.toLowerCase().includes(query.value.trim().toLowerCase())));if(!row.hidden)count++;});document.getElementById('count').textContent=count+'개 항목';}[region,game,kind].forEach(x=>x.addEventListener('change',filter));query.addEventListener('input',filter);filter();</script></html>'''

