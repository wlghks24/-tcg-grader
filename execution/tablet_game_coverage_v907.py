"""Read-only source-coverage and evidence counts for every registered TCG.

Catalog evidence is not an image, sale, grade or a successful data-provider fetch.
No network, collection, training or persistent data is touched by this module.
"""
from collections import defaultdict
import html
import re

from execution.tablet_catalog_bridge import REGIONS
from execution.tablet_card_facts_v904 import (
    SAFE_FACT_LINK_STATES, SAFE_MARKET_LINK_STATES,
    displayable_market_reference, displayable_price_reference
)
from execution.tablet_card_view_v904 import checked_release_date

ORDER = ('KR', 'JP', 'US', 'CN-S', 'CN-T')
STATES = {'core': 0, 'promoted': 1, 'watch': 2}


def snapshot(games, rows, *, providers, view_state):
    """Use the verified live feed and the currently approved collector configuration."""
    if not isinstance(games, dict) or len(games) > 200 or not isinstance(rows, list) or len(rows) > 10000:
        raise ValueError('TCG 전체 조회 범위 확인 필요')
    if view_state not in ('COMPLETE', 'PARTIAL_READ_ONLY') or not isinstance(providers, dict):
        raise ValueError('TCG 출처 상태 확인 필요')
    if any((not isinstance(k, tuple) or len(k) != 2 or k[1] not in REGIONS or
            not isinstance(k[0], str) or not re.fullmatch(r'[a-z0-9-]{2,64}', k[0])
            or not isinstance(v, str) or not v)
           for k, v in providers.items()):
        raise ValueError('TCG 공급사 설정 확인 필요')
    counters = defaultdict(lambda: dict(rows=0, images=0, catalog=0, exact_pairs=0,
                                        price_refs=0, release_refs=0, conflicts=0,
                                        cards=0, products=0))
    for row in rows:
        if (not isinstance(row, dict) or row.get('game_id') not in games
                or row.get('region') not in REGIONS):
            raise ValueError('TCG 목록의 게임·국가 출처 확인 필요')
        key = (row['game_id'], row['region'])
        count = counters[key]
        count['rows'] += 1
        count['images'] += bool(row.get('image_id'))
        count['catalog'] += bool(row.get('source_record_id'))
        status = row.get('link_status')
        facts = row.get('card_facts')
        facts = facts if isinstance(facts, dict) else {}
        trusted = not row.get('display_only') and row.get('card_facts_conflict') is not True
        photo_proof = bool(trusted and row.get('image_id') and status in SAFE_FACT_LINK_STATES)
        catalog_proof = bool(trusted and row.get('source_record_id') and status in SAFE_MARKET_LINK_STATES)
        # The matrix must not claim a price or exact pair which the card
        # renderer would refuse. Count evidence only within its approved
        # photo or catalog scope; these are not actual sales or graded cards.
        count['exact_pairs'] += bool(trusted and status == 'VERIFIED_PAIR'
                                     and row.get('image_id') and row.get('source_record_id'))
        count['conflicts'] += status in ('METADATA_CONFLICT', 'SOURCE_COVERAGE_INCOMPLETE')
        catalog_quote = row.get('market_quote')
        catalog_visible = displayable_market_reference(catalog_quote)
        provider_prices = facts.get('prices')
        provider_visible = isinstance(provider_prices, list) and any(
            displayable_price_reference(q) for q in provider_prices)
        # Raw quote presence is not a visible price. Preserve exactly the
        # same zero/finite-price and display-label boundaries as the card UI.
        count['price_refs'] += bool((catalog_proof and catalog_visible) or
                                    (photo_proof and provider_visible))
        count['release_refs'] += bool((catalog_proof and checked_release_date(row.get('observed_release_date'))) or
                                      (photo_proof and checked_release_date(facts.get('release_date'))))
        count['cards' if row.get('kind') in ('CARD', 'PROMO') else 'products'] += 1
    games_out = []
    for game_id, record in sorted(games.items(), key=lambda pair: (
            STATES.get(pair[1].get('state'), 3), pair[1].get('label_ko') or pair[0], pair[0])):
        if not isinstance(record, dict):
            raise ValueError('TCG 등록 게임 형식 확인 필요')
        label = record.get('label_ko') or game_id
        if not isinstance(label, str) or not label or len(label) > 160:
            raise ValueError('TCG 게임 이름 확인 필요')
        cells = []
        for region in ORDER:
            evidence = dict(counters[(game_id, region)])
            cells.append({'region': region, 'provider': providers.get((game_id, region), ''),
                          'observed': evidence})
        games_out.append({'game_id': game_id, 'label': label,
                          'state': record.get('state') or 'watch', 'cells': cells})
    return {'view_state': view_state, 'game_count': len(games_out),
            'configured_pairs': sum(bool(providers.get((g, r))) for g in games for r in ORDER),
            'country_count': len(ORDER), 'games': games_out}


def render(coverage):
    """Compact collapsible 30-game × five-country matrix; never a fake success count."""
    esc = html.escape
    state = coverage['view_state']
    rows = []
    for game in coverage['games']:
        cells = []
        for cell in game['cells']:
            evidence = cell['observed']
            source = cell['provider']
            if source:
                connection = '수집기 연결: ' + source
            else:
                connection = '자동수집기 미연결'
            if evidence['rows']:
                observed = ('자료 ' + str(evidence['rows']) + ' · 사진 ' + str(evidence['images']) +
                            ' · 카드 ' + str(evidence['cards']) + ' · 상품 ' + str(evidence['products']) +
                            ' · 가격근거 ' + str(evidence['price_refs']))
            else:
                observed = '조회된 자료 없음' if state == 'COMPLETE' else '부분 조회 · 미확인'
            cells.append('<td><small>' + esc(connection) + '</small><div>' + esc(observed) + '</div></td>')
        rows.append('<tr><th scope="row">' + esc(game['label']) + '<small> · ' +
                    esc(game['state']) + '</small></th>' + ''.join(cells) + '</tr>')
    partial = ('현재 자료는 부분 조회이므로 비어 있는 칸을 카드 부재로 판단하지 않습니다. ' if state != 'COMPLETE' else '')
    return ('<details id="tcg907-coverage" class="tcg903-maintenance"><summary>TCG 전체 ' +
            str(coverage['game_count']) + '종 · 국가판별 수집·정보 현황</summary><p>' +
            partial + '한판·일판·미판·중국 간체·대만 번체를 각각 구분합니다. ' +
            '수집기 연결은 카드정보·사진·시세 확보 완료를 의미하지 않습니다. ' +
            '미연결 게임도 기존 자료 검색과 수동 등록은 가능합니다.</p>' +
            '<div class="tcg907-scroll"><table><thead><tr><th>게임</th><th>한국판</th><th>일본판</th>' +
            '<th>미국판</th><th>중국 간체</th><th>대만 번체</th></tr></thead><tbody>' +
            ''.join(rows) + '</tbody></table></div><p>현재 설정: 전체 ' +
            str(coverage['game_count'] * coverage['country_count']) + '개 게임·국가 구분 중 ' +
            str(coverage['configured_pairs']) +
            '개 조합에 자동 이미지 공급사 설정 있음 · 실제 성공·시세 정확성·카드 진위·등급 미검증</p></details>')
