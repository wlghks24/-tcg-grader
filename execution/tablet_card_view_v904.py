"""Render provider facts and collected prices without inventing a printing/sale."""
from datetime import datetime, timezone
import html

from execution.tablet_card_facts_v904 import (
    VARIANTS, SAFE_VIEW_LINK_STATES, displayable_price_reference,
    displayable_market_reference, text, stamp
)
from execution.tablet_catalog_bridge import safe_url
from execution.tablet_unified_ui_v890 import render_card


def freshness(updated, now=None):
    checked=stamp(updated)
    if not checked: return '갱신일 미확인'
    age=((now or datetime.now(timezone.utc))-datetime.fromisoformat(checked)).total_seconds()
    return '미래 시각 확인 필요' if age<0 else '최근 참고시세' if age<=7*86400 else '오래된 참고시세 · 재수집 필요'


def market_observed_state(value, now=None):
    """Saved price observations are references, not current sales."""
    if not isinstance(value,str) or not value or len(value)>64:
        return '가격 관측일 미확인 · 현재 거래가 아님'
    try:
        if len(value)==10 and value[4]=='-' and value[7]=='-':
            observed=datetime.strptime(value,'%Y-%m-%d').replace(tzinfo=timezone.utc)
        else:
            normalized=stamp(value)
            if not normalized:
                return '가격 관측일 확인 필요 · 현재 거래가 아님'
            observed=datetime.fromisoformat(normalized)
    except (ValueError,TypeError):
        return '가격 관측일 확인 필요 · 현재 거래가 아님'
    age=((now or datetime.now(timezone.utc))-observed).total_seconds()
    return ('미래 관측일 재확인 필요 · 현재 거래가 아님' if age<0 else
            '최근 공개 참고가 · 실시간 거래 아님' if age<=7*86400 else
            '오래된 공개 참고가 · 현재 거래 확인 필요')


def checked_release_date(value):
    if not isinstance(value,str) or len(value)!=10 or value[4]!='-' or value[7]!='-':
        return ''
    try: datetime.strptime(value,'%Y-%m-%d')
    except ValueError: return ''
    return value


def render(row, picture):
    esc=html.escape
    # The legacy renderer prints the catalog release string verbatim. Avoid
    # displaying a malformed calendar date before the newer evidence guard.
    display_row=(dict(row,observed_release_date='')
                 if row.get('observed_release_date') and not checked_release_date(row.get('observed_release_date'))
                 else row)
    page=render_card(display_row,picture)
    # The catalog and provider/photo identity are independent trust gates.
    # A conflicting or partial catalog must not expose preattached facts,
    # market quotes or exact-card grading links.
    catalog_blocked=(row.get('link_status') not in SAFE_VIEW_LINK_STATES
                     or row.get('display_only') is True)
    card_actions_blocked=(row.get('card_facts_conflict') is True or catalog_blocked)
    # A catalog-only listing can retain its proven market reference, but
    # without a real source photo it must not select a card for grading.
    grade_without_photo=(row.get('kind') in ('CARD','PROMO')
                         and not row.get('image_id'))
    if row.get('kind') not in ('CARD','PROMO'):
        # The frozen generic card renderer still emits individual-card grading
        # links for sealed BOX/packs. Correct only the current integrated view:
        # a product quote is not a card grade or a grade-based sale estimate.
        page=page.replace('<summary>등급·판매가·출처 보기</summary>',
                          '<summary>상품·BOX 가격·출처 보기</summary>',1)
        page=page.replace('<p>등급 측정 전 · 정확한 판본의 거래자료 확인 필요</p>',
                          '<p>BOX·팩·상품은 개별 카드 등급 측정 대상이 아닙니다. 판매조건과 판본은 출처에서 확인하세요.</p>',1)
        page=page.replace('<a href="/index.html?feature=auto-grade">등급 측정</a> · <a href="/index.html?feature=grading-economics">등급별 판매가 확인</a>',
                          '<span>상품·BOX 참고시세는 위의 가격 근거 영역에서 확인하세요.</span>',1)
    if card_actions_blocked:
        # Fail closed even if JavaScript is disabled, delayed or bypassed.
        # The shell click guard remains for previously rendered/legacy links.
        page=page.replace('<a href="/index.html?feature=auto-grade">등급 측정</a> · <a href="/index.html?feature=grading-economics">등급별 판매가 확인</a>',
                          '<span>카드 출처·식별정보 확인 전 등급·시세 자동 연결 보류</span>',1)
    elif grade_without_photo:
        # Keep catalog market browsing/quotes; only card-scoped grading
        # links are unavailable until a real photo is collected.
        page=page.replace('<a href="/index.html?feature=auto-grade">등급 측정</a> · <a href="/index.html?feature=grading-economics">등급별 판매가 확인</a>',
                          '<span>실물 카드 사진 확인 전 등급 측정·등급별 판매가 연결 보류</span>',1)
    facts={} if card_actions_blocked else (row.get('card_facts') or {})
    fact_release=checked_release_date(facts.get('release_date'))
    metadata=row.get('card_metadata',{})
    pokemon_card=row['game_id']=='pokemon' and row.get('kind') in ('CARD','PROMO')
    if pokemon_card:
        generation=facts.get('generation') or metadata.get('generation')
        if not generation and facts.get('category') in ('Trainer','Energy'):
            generation='해당 없음 · '+facts['category']
        lineage_label, lineage_value='포켓몬 세대', generation or '도감번호 수집 대기'
    else:
        # Other TCGs have explicit edition series/sets, not Pokemon species generations.
        lineage_label='등록된 발매 시리즈·세트'
        lineage_value=(text(facts.get('series_name'),130) or text(metadata.get('series'),130)
                       or text(metadata.get('set_name'),130) or text(metadata.get('set_code'),40)
                       or '시리즈·세트 근거 수집 대기')
    # Keep the historic renderer/export contract separate from the new live UI.
    page=page.replace('<dt>세대</dt><dd>'+esc(str(metadata.get('generation') or '확인 필요'))+'</dd>',
                      '<dt>'+lineage_label+'</dt><dd>'+esc(str(lineage_value))+'</dd>')
    if facts.get('card_number'):
        old=metadata.get('card_code') or metadata.get('card_number') or '확인 필요'
        page=page.replace('<dt>카드번호</dt><dd>'+esc(str(old))+'</dd>', '<dt>카드번호</dt><dd>'+esc(facts['card_number'])+'</dd>')
    available=[{'firstEdition':'초판'}.get(v,VARIANTS.get(v,v)) for v in facts.get('available_variants',[])]
    addition=''
    for label,value in [('발매 시리즈',facts.get('series_name')),('세트 발매일',fact_release)]:
        if value: addition+='<div><dt>'+label+'</dt><dd>'+esc(str(value))+'</dd></div>'
    observed_release=checked_release_date(row.get('observed_release_date'))
    if observed_release and not fact_release:
        addition+='<div><dt>공개 출처 출시일 참고</dt><dd>'+esc(observed_release)+'</dd></div>'
    page=page.replace('</dl>',addition+'</dl>',1)
    if not metadata.get('printing'):
        pending_printing='홀로·리버스 등 대조 대기' if pokemon_card else '언어·희귀도·인쇄판본 대조 대기'
        page=page.replace('<dt>판본</dt><dd>확인 필요</dd>',
                          '<dt>사진의 세부 판본</dt><dd>'+pending_printing+'</dd>')
    variants='<p class="tcg904-variants">이 카드의 발매 판본: '+esc(' · '.join(available))+' · 사진의 실제 판본과는 별도입니다.</p>' if available else ''
    quotes=[]
    for q in facts.get('prices',[]):
        # Do not surface zero, non-finite or malformed cached amounts. Only
        # bounded positive provider references are eligible for display.
        if not displayable_price_reference(q):
            continue
        amount=f"{q['amount']:,.2f}".rstrip('0').rstrip('.')
        state='이전 참고가 보존 · 최신 유효 가격 확인 필요' if facts.get('price_state')=='RETAINED_NO_NEW_PRICE' else freshness(q['updated_at'])
        scope=(' · 세부 발매판 참고('+q['variant_ref']+')' if q.get('price_scope')=='DETAILED_VARIANT' else '')
        quotes.append('<li><b>'+esc(q['currency']+' '+amount)+'</b><span>'+esc(VARIANTS[q['variant']]+' · '+q['provider']+' '+q['metric']+scope)+'</span><small>'+esc(state+' · '+(q['updated_at'] or '갱신일 없음'))+'</small></li>')
    # A conflicting source/photo identity cannot inherit a market quotation,
    # even if a caller supplied a cached candidate alongside the view row.
    catalog=None if card_actions_blocked else row.get('market_quote')
    if displayable_market_reference(catalog):
        quote_note=market_observed_state(catalog.get('observed_at'))
        source_state='출처 연결 확인 기록 있음' if row.get('source_health')=='HEALTHY' else '출처 연결 재확인 필요'
        quotes.append('<li><b>'+esc(catalog['display'])+'</b><span>'+esc(catalog.get('market') or '저장된 시장 자료')+'</span><small>'+esc((catalog.get('observed_at') or '가격 관측일 미확인')+' · '+quote_note+' · '+source_state+' · '+(catalog.get('basis') or '가격 성격 확인 필요'))+'</small></li>')
    market_title='판본별 시장 참고가' if row.get('kind') in ('CARD','PROMO') else '상품·BOX 시장 참고가'
    market='<section class="tcg904-market"><h3>'+market_title+'</h3>'
    if row.get('card_facts_conflict') is True:
        market+='<p role="alert">사진의 카드번호·언어·세트 정보와 카드 API 근거가 일치하지 않아 상세·시세 연결을 보류했습니다. 원본은 보존되며 판본 확인이 필요합니다.</p>'
    elif row.get('link_status')=='METADATA_CONFLICT':
        market+='<p role="alert">사진과 상품 출처의 카드번호·판본 정보가 충돌해 등급·시세 연결을 보류했습니다. 원본은 보존되며 출처 대조가 필요합니다.</p>'
    elif catalog_blocked:
        if row.get('link_status')=='SOURCE_COVERAGE_INCOMPLETE' or row.get('display_only') is True:
            market+='<p role="alert">카드 출처가 일부만 확인되어 등급·시세 자동 연결을 보류했습니다. 수집 완료 전에는 확인된 정보만 표시합니다.</p>'
        else:
            market+='<p role="alert">카드 연결 상태를 확인할 수 없어 등급·시세 자동 연결을 보류했습니다. 검증된 원본과 판본을 다시 확인하세요.</p>'
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
    if fact_release:
        page=page.replace('출시일 미확인','세트 발매일 '+esc(fact_release))
    if facts.get('checked_at'):
        page=page.replace('출처 확인 미확인','카드 API 확인 '+esc(facts['checked_at']))
    page=page.replace('<details>',variants+market+'<details>',1)
    # These remain same-document actions, carrying the selected exact card.
    # The selected market candidate must retain source-backed set and
    # printing evidence; a repeated card number alone is not a unique printing.
    # Use the verified facts set only if no explicit saved set code exists.
    set_code=text(metadata.get('set_code') or facts.get('set_id'),40)
    printing=text(metadata.get('printing'),80)
    conflict_attr=' data-source-identity-conflict="true"' if row.get('card_facts_conflict') is True else ''
    blocked_attr=' data-card-actions-blocked="true"' if card_actions_blocked else ''
    grade_attr=' data-card-grade-blocked="true"' if grade_without_photo else ''
    page=page.replace('<article ', '<article'+conflict_attr+blocked_attr+grade_attr+' data-card-code="'+esc(metadata.get('card_code') or '',quote=True)+'"'
                      +' data-set-code="'+esc(set_code,quote=True)+'"'
                      +' data-printing="'+esc(printing,quote=True)+'" ',1)
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
