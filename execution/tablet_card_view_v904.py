"""Render provider facts and collected prices without inventing a printing/sale."""
from datetime import datetime, timezone
import html

from execution.tablet_card_facts_v904 import VARIANTS, text, stamp
from execution.tablet_catalog_bridge import safe_url
from execution.tablet_unified_ui_v890 import render_card


def freshness(updated, now=None):
    checked=stamp(updated)
    if not checked: return '갱신일 미확인'
    age=((now or datetime.now(timezone.utc))-datetime.fromisoformat(checked)).total_seconds()
    return '미래 시각 확인 필요' if age<0 else '최근 참고시세' if age<=7*86400 else '오래된 참고시세 · 재수집 필요'


def render(row, picture):
    esc=html.escape
    page=render_card(row,picture)
    facts=row.get('card_facts') or {}
    metadata=row.get('card_metadata',{})
    pokemon_card=row['game_id']=='pokemon' and row.get('kind') in ('CARD','PROMO')
    generation=facts.get('generation') or metadata.get('generation')
    if not generation and facts.get('category') in ('Trainer','Energy'):
        generation='해당 없음 · '+facts['category']
    # Keep the historic renderer/export contract separate from the new live UI.
    page=page.replace('<dt>세대</dt><dd>'+esc(str(metadata.get('generation') or '확인 필요'))+'</dd>',
                      '<dt>'+('포켓몬 세대' if pokemon_card else '발매 세대·시리즈')+'</dt><dd>'+esc(str(generation or ('도감번호 수집 대기' if pokemon_card else '출시 시리즈 수집 대기')))+'</dd>')
    if facts.get('card_number'):
        old=metadata.get('card_code') or metadata.get('card_number') or '확인 필요'
        page=page.replace('<dt>카드번호</dt><dd>'+esc(str(old))+'</dd>', '<dt>카드번호</dt><dd>'+esc(facts['card_number'])+'</dd>')
    available=[{'firstEdition':'초판'}.get(v,VARIANTS.get(v,v)) for v in facts.get('available_variants',[])]
    addition=''
    for label,value in [('발매 시리즈',facts.get('series_name')),('세트 발매일',facts.get('release_date'))]:
        if value: addition+='<div><dt>'+label+'</dt><dd>'+esc(str(value))+'</dd></div>'
    page=page.replace('</dl>',addition+'</dl>',1)
    if not metadata.get('printing'):
        page=page.replace('<dt>판본</dt><dd>확인 필요</dd>','<dt>사진의 세부 판본</dt><dd>홀로·리버스 등 대조 대기</dd>')
    variants='<p class="tcg904-variants">이 카드의 발매 판본: '+esc(' · '.join(available))+' · 사진의 실제 판본과는 별도입니다.</p>' if available else ''
    quotes=[]
    for q in facts.get('prices',[]):
        if q['amount'] <= 0:  # Preserve old cache bytes, but never display a zero placeholder as a market price.
            continue
        amount=f"{q['amount']:,.2f}".rstrip('0').rstrip('.')
        state='이전 참고가 보존 · 최신 유효 가격 확인 필요' if facts.get('price_state')=='RETAINED_NO_NEW_PRICE' else freshness(q['updated_at'])
        scope=(' · 세부 발매판 참고('+q['variant_ref']+')' if q.get('price_scope')=='DETAILED_VARIANT' else '')
        quotes.append('<li><b>'+esc(q['currency']+' '+amount)+'</b><span>'+esc(VARIANTS[q['variant']]+' · '+q['provider']+' '+q['metric']+scope)+'</span><small>'+esc(state+' · '+(q['updated_at'] or '갱신일 없음'))+'</small></li>')
    catalog=row.get('market_quote')
    if isinstance(catalog,dict) and text(catalog.get('display'),200):
        quotes.append('<li><b>'+esc(catalog['display'])+'</b><span>'+esc(catalog.get('market') or '저장된 시장 자료')+'</span><small>'+esc((catalog.get('observed_at') or '가격 관측일 미확인')+' · '+(catalog.get('basis') or '가격 성격 확인 필요'))+'</small></li>')
    market='<section class="tcg904-market"><h3>판본별 시장 참고가</h3>'
    if quotes:
        market+='<ul>'+''.join(quotes)+'</ul><p>공급사 제공 가격입니다. 실제 체결가·사진의 정확한 판본·등급별 판매가를 확정하지 않습니다.</p>'
    else:
        status=facts.get('price_state')
        missing=('가격 자료의 언어·판본 범위 확인이 필요합니다. 영문 시장 가격을 다른 언어 카드에 대입하지 않았습니다.' if status=='LANGUAGE_SCOPE_UNVERIFIED'
                 else '공급사 가격 필드·통화·가격 성격 확인이 필요합니다. 확인되지 않은 숫자는 표시하지 않았습니다.' if status=='UNSUPPORTED_OR_UNQUALIFIED'
                 else '공급사에 가격 자료가 없습니다. 다른 판본·카드의 가격을 대신 표시하지 않았습니다.' if facts
                 else '카드 상세·가격 수집 대기 · 수집·자료 갱신에서 보완 수집을 실행할 수 있습니다.')
        market+='<p>'+missing+'</p>'
    source=safe_url(facts.get('source'))
    if source:
        market+='<small>상세 확인 '+esc(facts.get('checked_at') or '미확인')+'</small> <a href="'+esc(source,quote=True)+'" target="_blank" rel="noopener noreferrer">카드 상세 근거 ↗</a>'
    if facts.get('retained_fields') or facts.get('set_facts_retained'):
        market+='<p>누적 상세값 보존 · 일부 항목은 최신 응답에서 빠져 재확인이 필요합니다.</p>'
    market+='</section>'
    if facts.get('release_date'):
        page=page.replace('출시일 미확인','세트 발매일 '+esc(facts['release_date']))
    if facts.get('checked_at'):
        page=page.replace('출처 확인 미확인','카드 API 확인 '+esc(facts['checked_at']))
    page=page.replace('<details>',variants+market+'<details>',1)
    # These remain same-document actions, carrying the selected exact card.
    page=page.replace('<article ', '<article data-card-code="'+esc(metadata.get('card_code') or '',quote=True)+'" ',1)
    return page


def render_cards(rows):
    import tablet_image_library_v1 as library
    cards=[]
    for row in rows:
        picture='<p>사진 보완 대기</p>'
        ident=row.get('image_id')
        if ident:
            if not isinstance(ident,str) or not library.ID_PATTERN.fullmatch(ident): raise ValueError('card display ID')
            picture='<img loading="lazy" decoding="async" alt="카드 사진" src="/api/local-card-images/display/'+ident+'" data-original="/api/local-card-images/file/'+ident+'"><p>표시용 사진 · 원본 확대 가능</p>'
        cards.append(render(row,picture))
    return ''.join(cards)
