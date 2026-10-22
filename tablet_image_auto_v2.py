#!/usr/bin/env python3
"""Bounded opt-in automatic PRIVATE image cache for TCG tablet.

Registry-wide coverage reporting; real downloads ONLY from explicitly wired APIs.
Never scrape search pages, invent regional printings, distribute media or bypass 403/429.
Runs on tablet Termux localhost, with no paid APIs/dependencies.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import tablet_image_library_v1 as library
from execution import tablet_image_collection_policy as policy

VERSION = 4
RUN_IMAGE_LIMIT = policy.RUN_IMAGES
MAX_PROVIDER_BYTES = 2_500_000
MAX_JOB_BYTES = policy.RUN_BYTES
FETCH_DELAY_SECONDS = 1.2
DEFAULT_PERIOD_SECONDS = policy.PERIOD_SECONDS
HOSTS = frozenset({'api.tcgdex.net', 'assets.tcgdex.net', 'db.ygoprodeck.com',
                   'images.ygoprodeck.com', 'api.gcgapi.com',
                   'api.scryfall.com', 'cards.scryfall.io', 'api.lorcana-api.com',
                   'lorcana-api.com', 'raw.githubusercontent.com',
                   'en.onepiece-cardgame.com', 'www.onepiece-cardgame.com',
                   'asia-tw.onepiece-cardgame.com', 'api.swu-db.com', 'cdn.swu-db.com',
                   'd3alac64utt23z.cloudfront.net', 'www.gundam-gcg.com',
                   'cdn.sanity.io'})
# One country edition = one language/printing. Never copy JP/EN image into Korean/Chinese bins.
# Official TCGdex locale codes; do not use zh for Chinese.
# TCGdex documentation lists Korean and Simplified Chinese as coming soon; no fake coverage.
POKEMON_LOCALES = {'JP': 'ja', 'US': 'en', 'CN-T': 'zh-tw'}
SUPPORTED = {('pokemon', k): 'TCGdex' for k in POKEMON_LOCALES}
MTG_LOCALES = {'KR':'ko','JP':'ja','US':'en','CN-S':'zhs','CN-T':'zht'}
SUPPORTED.update({('yugioh', 'US'): 'YGOPRODeck',
                  ('lorcana', 'US'): 'LorcanaAPI',
                  ('swu', 'US'): 'SWUDB',
                  ('gundam', 'US'): 'GCGAPI',
                  ('riftbound', 'US'): 'RiftboundData'})
ONEPIECE_LOCALES = {'US': ('english', 'en.onepiece-cardgame.com'),
                    'JP': ('japanese', 'www.onepiece-cardgame.com'),
                    'CN-T': ('chinese-taiwan', 'asia-tw.onepiece-cardgame.com')}
SUPPORTED.update({('onepiece', k): 'PunkRecords' for k in ONEPIECE_LOCALES})
SUPPORTED.update({('mtg', k): 'Scryfall' for k in MTG_LOCALES})
METADATA_ONLY = {}
_LOCK = threading.RLock()
_STOP = threading.Event()
_THREAD = None
_SCHEDULER = None
_BUDGET_CONTEXT = threading.local()
_LIVE = {'running': False, 'scanned': 0, 'saved': 0, 'skipped': 0, 'errors': 0,
         'message': '수집 대기', 'started_at': None, 'finished_at': None, 'error_class': None}


class ProviderError(ValueError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, hdrs, newurl):
        raise ProviderError('리다이렉트 차단')


def _url_allowed(url):
    try:
        parsed = urllib.parse.urlsplit(url)
        return (parsed.scheme == 'https' and parsed.hostname in HOSTS and
                parsed.username is None and parsed.password is None and
                parsed.port in (None, 443) and not parsed.fragment and
                0 < len(url) <= 1024)
    except (ValueError, TypeError):
        return False


def fetch_binary(url, limit=library.MAX_IMAGE_BYTES):
    if not _url_allowed(url):
        raise ProviderError('허용되지 않은 이미지 출처')
    budget = getattr(_BUDGET_CONTEXT, 'current', None)
    if budget is None:
        raise ProviderError('예산이 설정된 이미지 수집 작업에서만 연결합니다.')
    allowance = min(limit, budget.byte_allowance())
    if allowance <= 0:
        raise policy.Deferred('다운로드 용량 예산 도달')
    entry = budget.reserve_request(budget.provider)
    req = urllib.request.Request(url, headers={
        'User-Agent': 'TCGTabletPrivateImageCache/5 (+personal offline collection)',
        'Accept': 'application/json, image/webp, image/jpeg, image/png',
    })
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)
    received = 0
    deadline = time.monotonic() + min(12, budget.remaining_seconds())
    try:
        with opener.open(req, timeout=max(0.2, min(9, budget.remaining_seconds()))) as resp:
            if getattr(resp, 'status', 200) != 200 or resp.geturl() != url:
                raise ProviderError('출처 응답 오류')
            declared = resp.headers.get('Content-Length', '')
            if declared and (not declared.isdecimal() or int(declared) > allowance):
                raise ProviderError('응답 크기 제한 초과')
            mime = resp.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
            if mime and mime not in {'application/json', 'image/webp', 'image/jpeg', 'image/png', 'application/octet-stream'}:
                raise ProviderError('출처 MIME 형식 오류')
            chunks = []
            read = getattr(resp, 'read1', resp.read)
            while True:
                if time.monotonic() >= deadline:
                    raise policy.Deferred('출처 응답시간 예산 도달')
                chunk = read(min(65536, allowance + 1 - received))
                if not chunk:
                    break
                chunks.append(chunk)
                received += len(chunk)
                if received > allowance:
                    raise ProviderError('다운로드 크기 제한 초과')
            return b''.join(chunks)
    except urllib.error.HTTPError as ex:
        if ex.code in (403, 429):
            budget.block(budget.provider, ex.code, ex.headers.get('Retry-After') if ex.headers else None)
        ex.close()
        raise ProviderError(f'출처 HTTP {ex.code}') from ex
    except (urllib.error.URLError, TimeoutError, OSError) as ex:
        raise ProviderError('출처 연결 실패') from ex
    finally:
        budget.add_bytes(entry, min(received, allowance))


def fetch_json(url):
    data = fetch_binary(url, MAX_PROVIDER_BYTES)
    try:
        return json.loads(data.decode('utf-8'))
    except (UnicodeError, ValueError) as ex:
        raise ProviderError('출처 JSON 오류') from ex


def _state(root):
    p = root / 'auto_state_v2.json'
    if not p.exists():
        return {'version': VERSION, 'enabled': False, 'last_finished_epoch': 0,
                'pages': {}, 'completed': {}, 'last_result': {}}
    if p.is_symlink() or p.stat().st_size > 1_500_000:
        raise ValueError('자동수집 상태파일 손상')
    obj = json.loads(p.read_text(encoding='utf-8'))
    if (not isinstance(obj, dict) or obj.get('version') not in (2, 3, VERSION) or
            not isinstance(obj.get('pages'), dict) or not isinstance(obj.get('completed'), dict)
            or not isinstance(obj.get('enabled'), bool) or len(obj['completed']) > 4000):
        raise ValueError('자동수집 상태 스키마 오류')
    # Schema-compatible upgrade; keep progress and completed asset fingerprints.
    obj['version'] = VERSION
    return obj


def _save(root, obj):
    content = (json.dumps(obj, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')
    if len(content) > 1_500_000:
        raise ValueError('자동수집 상태 용량 제한 · 기존 상태 보존')
    library._atomic_write(root / 'auto_state_v2.json', content)


def _coverage(repo, state=None):
    games = library._registry_ids(repo)
    state = state or {}
    successes = state.get('source_stats') if isinstance(state.get('source_stats'), dict) else {}
    last = state.get('last_result') if isinstance(state.get('last_result'), dict) else {}
    per_source = last.get('per_source') if isinstance(last.get('per_source'), dict) else {}
    all_regions = ('KR', 'JP', 'US', 'CN-S', 'CN-T')
    return {
        'game_count': len(games),
        'edition_groups': ['KR', 'JP', 'US', 'CN'],
        'supported_sources': [{'game_id': game, 'region': region, 'source': source,
                               'confirmed_saved': bool((successes.get(game+'|'+region) or {}).get('saved_total',0) or
                                                    (per_source.get(game+'|'+region) or {}).get('saved',0))}
                              for (game, region), source in sorted(SUPPORTED.items()) if game in games],
        'metadata_only': [{'game_id':g,'region':r,'reason':reason} for (g,r),reason in METADATA_ONLY.items() if g in games],
        'pending_source_count': sum((game, region) not in SUPPORTED for game in games for region in all_regions),
        'note': '연결=코드 구성 (실기기 다운로드 검증과 별개). 포켓몬 한국어·중국 간체 미연결. BOX·PACK 실물 사진은 건담 등 확인된 제품 출처에서만 등록함. 영어판 표시가 북미 제조국 보증은 아님',
        'supported_kinds': ['CARD', 'PROMO', 'PACK', 'BOX', 'COLLECTION', 'DECK', 'ACCESSORY', 'BUNDLE'],
        'supported_product_sources': ['GCGAPI:gundam/US'],
        'unsupported_kinds': [],
        'pending_games': sorted(game for game in games if not any(g==game for g,_ in SUPPORTED)),
    }


def status(repo):
    with _LOCK:
        obj = _state(library.storage_root())
        return {'ok': True, 'version': VERSION, 'auto_enabled': obj['enabled'],
                'last_result': obj.get('last_result') or {}, 'job': dict(_LIVE),
                'coverage': _coverage(repo, obj), 'collection_policy': policy.Budget(obj, lambda: None).snapshot(),
                'compression_policy': 'PIXEL_PRESERVING_WEBP_OR_SMALLER_ORIGINAL',
                'local_folder': str(library.storage_root())}


def _safe_name(value):
    return re.sub(r'[\x00-\x1f\x7f]', ' ', str(value or '')).strip()[:90]


def _valid_id(value):
    # TCGdex set IDs can include dots and percent-encoded non-alphanumerics.
    return (isinstance(value, str) and bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._%\-]{0,89}', value))
            and '..' not in value and '%2f' not in value.lower() and '%2e' not in value.lower())


def candidates_pokemon(region, page):
    locale = POKEMON_LOCALES[region]
    url = f'https://api.tcgdex.net/v2/{locale}/cards?pagination%3Apage={page}&pagination%3AitemsPerPage=8'
    data = fetch_json(url)
    if not isinstance(data, list):
        raise ProviderError('TCGdex 목록 형식 오류')
    result = []
    for row in data[:8]:
        if not isinstance(row, dict) or not _valid_id(row.get('id')):
            continue
        image = row.get('image')
        if not isinstance(image, str) or not image.startswith('https://assets.tcgdex.net/' + locale + '/'):
            continue
        # TCGdex mixes Pokémon TCG Pocket (digital) and printed cards in the
        # same endpoint. Digital Pocket cards are NOT physical investment cards.
        if '/tcgp/' in image.lower():
            continue
        # Bound and validate every path segment, and reject URL escapes/traversal.
        parts = urllib.parse.urlsplit(image)
        if (parts.query or parts.fragment or parts.username or parts.password or
                not re.fullmatch(r'/[a-z-]{2,7}/[A-Za-z0-9_.%-]{1,60}/[A-Za-z0-9_.%-]{1,70}/[A-Za-z0-9_.%-]{1,65}', parts.path) or
                any(part in ('.', '..') or '%2e' in part.lower() or '%2f' in part.lower()
                    for part in parts.path.split('/'))):
            continue
        name = _safe_name(row.get('name'))
        if not name:
            continue
        result.append({'provider': 'TCGdex', 'key': 'pokemon/'+locale+'/'+row['id'],
                       'game_id': 'pokemon', 'region': region, 'kind': 'CARD',
                       'name': name + ' · ' + str(row['id']),
                       'url': image + '/high.webp', 'source': url})
    return result


def candidates_yugioh(page):
    offset = (page - 1) * 6
    url = f'https://db.ygoprodeck.com/api/v7/cardinfo.php?num=6&offset={offset}&sort=new'
    data = fetch_json(url)
    rows = data.get('data') if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ProviderError('YGOPRODeck 목록 형식 오류')
    out = []
    for row in rows[:6]:
        if not isinstance(row, dict):
            continue
        ident = str(row.get('id') or '')
        if not re.fullmatch(r'[0-9]{1,15}', ident):
            continue
        images = row.get('card_images')
        img = images[0] if isinstance(images, list) and images else {}
        if not isinstance(img, dict):
            continue
        url_image = img.get('image_url')
        if not isinstance(url_image, str) or not re.fullmatch(r'https://images\.ygoprodeck\.com/images/cards/[0-9]+\.jpg', url_image):
            continue
        name = _safe_name(row.get('name'))
        if name:
            out.append({'provider': 'YGOPRODeck', 'key': 'yugioh/en/' + ident,
                        'game_id': 'yugioh', 'region': 'US', 'kind': 'CARD',
                        'name': name + ' · ' + ident, 'url': url_image, 'source': url})
    return out


def _gundam_image_ok(value, *, kind):
    if not isinstance(value,str):return False
    try:
        parts=urllib.parse.urlsplit(value)
        if (parts.scheme!='https' or parts.hostname!='www.gundam-gcg.com'
            or parts.port not in (None,443) or parts.fragment):return False
        if parts.query and not re.fullmatch(r'[0-9]{1,15}',parts.query):return False
        if kind=='CARD':
            return bool(re.fullmatch(r'/en/images/cards/card/[A-Za-z0-9_-]{3,90}\.(?:webp|png|jpg)',parts.path))
        return bool(re.fullmatch(r'/gcg/bccard/en/[A-Za-z0-9_./-]{5,180}\.(?:webp|png|jpg)',parts.path)) and '..' not in parts.path
    except (TypeError,ValueError):return False


def candidates_gundam(page):
    """Official-product-derived imagery: alternate CARDS and PRODUCT photos.

    BOOSTERPACK photo=PACK unless item name explicitly states booster BOX.
    This prevents a pack thumbnail being mislabelled a sealed BOX.
    """
    is_product = (page % 2 == 1)
    offset=((page-1)//2)*6
    endpoint='products' if is_product else 'cards'
    url='https://api.gcgapi.com/v1/'+endpoint+'?limit=6&offset='+str(offset)
    data=fetch_json(url)
    rows=data.get('data') if isinstance(data,dict) else None
    if not isinstance(rows,list):raise ProviderError('GCGAPI '+endpoint+' 목록 형식 오류')
    out=[]
    for row in rows[:6]:
        if not isinstance(row,dict):continue
        ident=str(row.get('product_id') or '')
        if not re.fullmatch(r'[A-Za-z0-9_-]{2,72}',ident):continue
        name=_safe_name(row.get('name'))
        kind='CARD'
        if is_product:
            category=str(row.get('category_tag') or '').upper()
            if category=='BOOSTERPACK':
                kind='BOX' if re.search(r'\bbox\b', name, re.I) else 'PACK'
            elif category=='STARTERDECK':
                kind='DECK'
            elif category=='PREMIUMBANDAI':
                kind='COLLECTION'
            elif category=='ACCESSORIES':
                # A card/playmat bundle is not a single sealed booster pack.
                low=name.lower()
                kind='BUNDLE' if 'playmat' in low and 'card set' in low else 'ACCESSORY'
            else:kind='OTHER'
        elif str(row.get('where_to_get') or '').lower().find('promo')>=0:
            kind='PROMO'
        image=row.get('image_url')
        if not name or not _gundam_image_ok(image,kind='CARD' if not is_product else 'PRODUCT'):
            continue
        out.append({'provider':'GCGAPI','key':'gundam/en/'+endpoint+'/'+ident,
                    'game_id':'gundam','region':'US','kind':kind,'name':name+' · '+ident,
                    'url':image,'source':url})
    return out


def candidates_mtg(region, page):
    """Scryfall published English physical prints; full card image (not art crop)."""
    locale=MTG_LOCALES[region]
    q = urllib.parse.urlencode({'q': 'game:paper lang:'+locale, 'unique': 'prints',
                                'order': 'released', 'dir': 'desc',
                                'page': (page - 1) // 22 + 1})
    url = 'https://api.scryfall.com/cards/search?' + q
    data = fetch_json(url)
    rows = data.get('data') if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ProviderError('Scryfall 목록 형식 오류')
    start = ((page - 1) % 22) * 8
    out = []
    for row in rows[start:start+8]:
        if not isinstance(row, dict) or row.get('lang') != locale or 'paper' not in row.get('games', []) or row.get('image_status') == 'placeholder':
            continue
        ident = row.get('id')
        if not isinstance(ident, str) or not re.fullmatch(r'[a-f0-9\-]{36}', ident):
            continue
        images = row.get('image_uris')
        if not isinstance(images, dict):
            faces = row.get('card_faces')
            images = faces[0].get('image_uris') if isinstance(faces, list) and faces and isinstance(faces[0], dict) else None
        img = (images.get('large') or images.get('normal')) if isinstance(images, dict) else None
        if not isinstance(img, str) or not re.fullmatch(r'https://cards\.scryfall\.io/(?:large|normal)/(?:front|back)/[A-Za-z0-9/._-]+\.jpg(?:\?[A-Za-z0-9=&_-]+)?', img):
            continue
        name = _safe_name(row.get('name'))
        if name:
            out.append({'provider':'Scryfall', 'key':'mtg/'+locale+'/'+ident,
                        'game_id':'mtg', 'region':region, 'kind':'CARD',
                        'name':name, 'url':img,'source':url})
    return out


def candidates_lorcana(page):
    url = 'https://api.lorcana-api.com/cards/all?pagesize=8&page=' + str(page)
    data = fetch_json(url)
    if not isinstance(data, list):
        raise ProviderError('LorcanaAPI 목록 형식 오류')
    out = []
    for row in data[:8]:
        if not isinstance(row, dict):
            continue
        image = row.get('Image')
        ident = row.get('Set_ID')
        number = row.get('Card_Num')
        if (not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,18}',ident)
                or not isinstance(number, (int,str)) or not re.fullmatch(r'[0-9]{1,5}',str(number))):
            continue
        if not isinstance(image, str) or not re.fullmatch(r'https://lorcana-api\.com/images/[A-Za-z0-9_./-]+\.(?:png|jpg|webp)',image):
            continue
        name = _safe_name(row.get('Name'))
        if name:
            out.append({'provider':'LorcanaAPI','key':'lorcana/en/'+ident+'/'+str(number),
                        'game_id':'lorcana','region':'US','kind':'CARD',
                        'name':name+' · '+ident+'-'+str(number),'url':image,'source':url})
    return out


def candidates_swu(page):
    """SWU-DB release /sets list and real English card art, not invented sets."""
    sets_url='https://api.swu-db.com/sets'
    sets=fetch_json(sets_url)
    if not isinstance(sets,list) or len(sets)>250:
        raise ProviderError('SWUDB 세트 목록 형식 오류')
    set_ids=sorted({str(row.get('setId')).upper() for row in sets
                    if isinstance(row,dict) and re.fullmatch(r'[A-Za-z0-9]{2,8}',str(row.get('setId') or ''))}, reverse=True)
    set_index,part=divmod(page-1,64)
    if set_index>=len(set_ids):
        return [],1
    set_id=set_ids[set_index]
    url='https://api.swu-db.com/cards/'+set_id.lower()
    cards=fetch_json(url)
    if not isinstance(cards,list) or len(cards)>1000:
        raise ProviderError('SWUDB 카드 목록 형식 오류')
    start=part*8
    next_page=page+1 if start+8<len(cards) and part<63 else (set_index+1)*64+1
    out=[]
    for card in cards[start:start+8]:
        if not isinstance(card,dict) or str(card.get('Set','')).upper()!=set_id:
            continue
        number=str(card.get('Number') or '')
        name=_safe_name(card.get('Name'))
        img=card.get('FrontArt')
        if not re.fullmatch(r'[0-9]{1,5}[A-Z]?',number) or not name or not isinstance(img,str):
            continue
        parsed=urllib.parse.urlsplit(img)
        if (parsed.scheme!='https' or parsed.hostname not in ('cdn.swu-db.com','d3alac64utt23z.cloudfront.net')
            or parsed.query or parsed.fragment or parsed.port not in (None,443)
            or not re.fullmatch(r'/images/cards/'+set_id+r'/[0-9]{1,5}[A-Z]?(?:-b)?\.png',parsed.path,re.IGNORECASE)):
            continue
        rarity=str(card.get('Rarity','')).lower()
        kind='PROMO' if 'promo' in rarity else 'CARD'
        out.append({'provider':'SWUDB','key':'swu/en/'+set_id+'/'+number,
                    'game_id':'swu','region':'US','kind':kind,
                    'name':name+' · '+set_id+'-'+number,'url':img,'source':url})
    return out,next_page


def candidates_riftbound(page):
    """Riot official gallery-derived static dataset. Personal small-size cache only."""
    url='https://raw.githubusercontent.com/slimtreble/Riftbound-card-data/main/cards.json'
    rows=fetch_json(url)
    if not isinstance(rows,list) or len(rows)>4000:
        raise ProviderError('Riftbound 카드 목록 형식 오류')
    start=(page-1)*8
    out=[]
    for row in rows[start:start+8]:
        if not isinstance(row,dict):continue
        code=str(row.get('publicCode') or '')
        name=_safe_name(row.get('name'))
        img=row.get('imageUrl')
        if not re.fullmatch(r'[A-Za-z0-9*/_-]{3,45}',code) or not name or not isinstance(img,str):
            continue
        parts=urllib.parse.urlsplit(img)
        if (parts.scheme!='https' or parts.hostname!='cdn.sanity.io' or parts.port not in (None,443)
            or not re.fullmatch(r'/images/dsfx7636/game_data_live/[A-Za-z0-9_.-]{10,150}\.(?:png|jpg|webp)',parts.path)
            or (parts.query and not re.fullmatch(r'[A-Za-z0-9_=&%.-]{1,120}',parts.query))):
            continue
        kind='PROMO' if 'PROMO' in str(row.get('setName','')).upper() else 'CARD'
        out.append({'provider':'RiftboundData','key':'riftbound/en/'+code,
                    'game_id':'riftbound','region':'US','kind':kind,
                    'name':name+' · '+code,'url':img,'source':url})
    return out


def candidates_onepiece(region, page):
    """Publisher-derived locale-specific static pack/card metadata; no page scraping.

    25 chunks per pack; next-page skips exhausted chunks. Card art remains
    publisher copyright: private cache only; never uploaded to public repo.
    """
    locale, host = ONEPIECE_LOCALES[region]
    base = 'https://raw.githubusercontent.com/Kuroro1990/OPTCG/main/'+locale+'/'
    packs = fetch_json(base+'packs.json')
    if not isinstance(packs, dict) or len(packs)>1000:
        raise ProviderError('OnePiece 세트 목록 형식 오류')
    # Stable order; newest code first, keep cards and locale together.
    pack_ids = sorted((k for k in packs if re.fullmatch(r'[0-9]{4,8}',k)),reverse=True)
    pack_index, part_index = divmod(page-1,25)
    if pack_index >= len(pack_ids):
        return [],1
    pack = pack_ids[pack_index]
    url = base+'data/'+pack+'.json'
    rows = fetch_json(url)
    if not isinstance(rows,list) or len(rows)>1500:
        raise ProviderError('OnePiece 카드 목록 형식 오류')
    start = part_index*8
    next_page = page+1 if start+8<len(rows) and part_index<24 else (pack_index+1)*25+1
    out=[]
    for row in rows[start:start+8]:
        if not isinstance(row,dict) or str(row.get('pack_id'))!=pack:
            continue
        ident=row.get('id')
        img=row.get('img_full_url')
        if not isinstance(ident,str) or not re.fullmatch(r'[A-Za-z0-9-]{3,35}',ident):
            continue
        parsed=urllib.parse.urlsplit(img) if isinstance(img,str) else None
        if not parsed or parsed.scheme!='https' or parsed.hostname != host or parsed.port not in (None,443):
            continue
        if not re.fullmatch(r'/images/cardlist/card/[A-Za-z0-9_.-]{3,80}\.png',parsed.path):
            continue
        if parsed.query and not re.fullmatch(r'[0-9]{1,15}',parsed.query):
            continue
        name=_safe_name(row.get('name'))
        if not name:
            continue
        rarity=str(row.get('rarity') or '').lower()
        pack_data=packs.get(pack)
        pack_title=(pack_data.get('raw_title','') if isinstance(pack_data,dict) else '')
        if not isinstance(pack_title,str):pack_title=''
        promo=('promo' in rarity or 'promo' in pack_title.lower() or '推廣' in pack_title or 'プロモ' in pack_title)
        out.append({'provider':'PunkRecords','key':'onepiece/'+locale+'/'+pack+'/'+ident,
                    'game_id':'onepiece','region':region,'kind':'PROMO' if promo else 'CARD',
                    'name':name+' · '+ident,'url':img,'source':url})
    return out,next_page


def _candidate_batches(state, bridge_priority=None):
    """Round-robin sources; every third cycle gives one evidence-backed gap priority.

    A gap means 'revisit this provider', NEVER proof of a matching printing.
    Provider endpoints, image host allowlists and 18-image budget stay unchanged.
    """
    available=sorted(SUPPORTED)
    first = int(state.get('next_source_index',0)) % len(available)
    ordered=[(first+i)%len(available) for i in range(len(available))]
    cycle=state.get('cross_cycle',0)
    if not isinstance(cycle,int) or cycle<0:cycle=0
    if bridge_priority and cycle%3==2:
        best=max(ordered,key=lambda i:bridge_priority.get(available[i],0))
        if bridge_priority.get(available[best],0)>0:
            ordered=[best]+[i for i in ordered if i!=best]
    for pos in ordered:
        game,region=available[pos]
        key=game+'|'+region
        page=min(max(int(state['pages'].get(key,1)),1),100000)
        yield pos,key,page,game,region


def _collect_once(repo, stop=None, sleeper=time.sleep):
    """Synchronous bounded run for unit tests/CLI; thread wrapper below uses this."""
    repo = Path(repo)
    stop = stop or threading.Event()
    root = library.storage_root()
    budget = _BUDGET_CONTEXT.current
    state = budget.state
    counts = {'scanned': 0, 'saved': 0, 'skipped': 0, 'errors': 0,
              'per_source': {}, 'issues': [], 'deferred': False, 'stored_bytes':0, 'compression_bytes_saved':0, 'run_at': datetime.now(timezone.utc).isoformat()}
    known_games = library._registry_ids(repo)
    used_bytes = 0
    try:
        import tablet_catalog_auto_reflect_v43 as bridge
        priority=bridge.safe_priority(repo)
    except (ImportError,OSError,ValueError):
        priority={}
    for pos, key, page, game, region in _candidate_batches(state, priority):
        if stop.is_set() or counts['saved'] >= RUN_IMAGE_LIMIT:
            break
        if game not in known_games:
            continue
        # Save scheduling cursor before attempting: every source gets a turn.
        state['next_source_index']=(pos+1)%len(SUPPORTED)
        source = SUPPORTED[(game,region)]
        budget.provider = source
        stats = counts['per_source'][key] = {'source':source, 'saved':0, 'skipped':0,'errors':0}
        try:
            budget.can_save(source)
            if game == 'pokemon':
                rows = candidates_pokemon(region, page)
            elif game == 'yugioh':
                rows = candidates_yugioh(page)
            elif game == 'gundam':
                rows = candidates_gundam(page)
            elif game == 'riftbound':
                rows = candidates_riftbound(page)
            elif game == 'mtg':
                rows = candidates_mtg(region,page)
            elif game == 'lorcana':
                rows = candidates_lorcana(page)
            elif game == 'onepiece':
                rows, next_page = candidates_onepiece(region,page)
            elif game == 'swu':
                rows, next_page = candidates_swu(page)
            else:
                raise ProviderError('미연결 출처')
            # Persist source-specific cursor; no other region is silently substituted.
            pending_page = next_page if game in ('onepiece','swu') else (1 if not rows else page+1)
        except policy.Deferred as ex:
            counts['deferred'] = True
            counts['issues'].append(key + ': ' + str(ex))
            continue
        except (ProviderError, ValueError, TypeError, OSError) as ex:
            counts['errors'] += 1
            stats['errors'] += 1
            counts['issues'].append(key + ': ' + str(ex)[:100])
            continue
        completed_page = True
        for row in rows:
            if stop.is_set() or counts['saved'] >= RUN_IMAGE_LIMIT or used_bytes >= MAX_JOB_BYTES:
                completed_page = False
                break
            counts['scanned'] += 1
            fingerprint = hashlib.sha256(row['key'].encode('utf-8')).hexdigest()
            if fingerprint in state['completed']:
                # Treat a manual deletion as an opt-out, not a request to re-download.
                counts['skipped'] += 1; stats['skipped'] += 1
                continue
            try:
                budget.can_save(source)
                if not _url_allowed(row['url']):
                    raise ProviderError('외부 이미지 호스트 차단')
                sleeper(FETCH_DELAY_SECONDS)
                if stop.is_set():
                    completed_page = False
                    break
                data = fetch_binary(row['url'])
                mime, _ = library.sniff(data)
                used_bytes += len(data)
                if used_bytes > MAX_JOB_BYTES:
                    raise ProviderError('1회 데이터 사용량 제한 초과')
                added = library.save_image(repo, {
                    'game_id': row['game_id'], 'region': row['region'],
                    'kind': row['kind'], 'name': row['name'],
                    'provider': row['provider'], 'source_url': row['source'], 'source_id': row['key'],
                    'image_base64': 'data:' + mime + ';base64,' + base64.b64encode(data).decode('ascii'),
                }, trusted_auto=True)
                # Only committed image IDs get persisted as completed.
                state['completed'][fingerprint] = {'id': added['id'], 'provider': row['provider'],
                                                   'key': row['key'], 'source': row['source']}
                counts['saved'] += 1; stats['saved'] += 1
                budget.record_image(source, added.get('stored_bytes',0))
                counts['stored_bytes'] += added.get('stored_bytes',0)
                counts['compression_bytes_saved'] += max(0, added.get('source_bytes',0)-added.get('stored_bytes',0))
                src_info = state.setdefault('source_stats', {}).setdefault(key, {'saved_total':0})
                src_info['saved_total'] = int(src_info.get('saved_total',0)) + 1
                with _LOCK:
                    _LIVE.update({k:counts[k] for k in ('scanned','saved','skipped','errors')})
                if len(state['completed']) > 3800:
                    # Memory bounded; content-addressed library files stay untouched.
                    first = next(iter(state['completed']))
                    del state['completed'][first]
                with _LOCK:
                    state['enabled'] = _state(root)['enabled']
                    _save(root, state)
            except policy.Deferred as ex:
                completed_page = False
                counts['deferred'] = True
                counts['issues'].append(row['provider'] + ': ' + str(ex))
                break
            except (ProviderError, ValueError, OSError, UnicodeError, TypeError) as ex:
                counts['errors'] += 1; stats['errors'] += 1
                counts['issues'].append(row['provider'] + ': ' + str(ex)[:100])
                # Throttle errors rather than retrying 403/429.
                if ('HTTP 429' in str(ex) or 'HTTP 403' in str(ex) or
                        '최대 2500' in str(ex) or '500MB' in str(ex)):
                    completed_page = False
                    break
        if completed_page:
            state['pages'][key] = pending_page
        with _LOCK:
            state['enabled'] = _state(root)['enabled']
            _save(root, state)
        if stop.is_set():
            break
    cycle=state.get('cross_cycle',0)
    state['cross_cycle']=(cycle if isinstance(cycle,int) and cycle>=0 else 0)%1_000_000+1
    counts['issues'] = counts['issues'][:12]
    counts['stopped'] = bool(stop.is_set())
    counts['budget'] = budget.snapshot()
    with _LOCK:
        state['last_finished_epoch'] = time.time()
        state['last_result'] = counts
        state['enabled'] = _state(root)['enabled']
        _save(root, state)
    return counts


def collect_once(repo, stop=None, sleeper=time.sleep):
    root = library.storage_root()
    with _LOCK:
        state = _state(root)
    def save_budget():
        with _LOCK:
            state['enabled'] = _state(root)['enabled']
            _save(root, state)
    _BUDGET_CONTEXT.current = policy.Budget(state, save_budget)
    try:
        return _collect_once(repo, stop=stop, sleeper=sleeper)
    finally:
        del _BUDGET_CONTEXT.current


def _worker(repo):
    global _THREAD
    try:
        result = collect_once(repo, _STOP)
        # Derived read-only evidence audit; never fail the actual image job.
        try:
            import tablet_catalog_auto_reflect_v43 as bridge
            bridge.safe_cycle(repo)
        except (OSError,ValueError,TypeError,UnicodeError,ImportError):
            pass
        with _LOCK:
            _LIVE.update({k: result[k] for k in ('scanned','saved','skipped','errors')})
            _LIVE['message'] = '중지됨' if result['stopped'] else '예산/출처 대기 · 기존 사진 보존' if result['deferred'] else '수집 종료'
    except Exception as ex:
        with _LOCK:
            _LIVE['errors'] += 1
            _LIVE['error_class'] = type(ex).__name__
            _LIVE['message'] = '수집 실패(기존 사진 보존)'
    finally:
        with _LOCK:
            _LIVE['finished_at'] = datetime.now(timezone.utc).isoformat()
            _LIVE['running'] = False
            _THREAD = None


def start_job(repo):
    global _THREAD
    with _LOCK:
        if _THREAD is not None and _THREAD.is_alive():
            return {'ok':True,'already_running':True}
        _STOP.clear()
        _LIVE.update({'running':True,'scanned':0,'saved':0,'skipped':0,'errors':0,
                      'message':'자동 이미지 수집 중','started_at':datetime.now(timezone.utc).isoformat(),
                      'finished_at':None,'error_class':None})
        _THREAD = threading.Thread(target=_worker,args=(Path(repo),),daemon=True,name='tcg-private-image-collector')
        _THREAD.start()
    return {'ok':True,'accepted':True}


def set_enabled(enabled):
    if type(enabled) is not bool:
        raise ValueError('자동 실행 설정 오류')
    with _LOCK:
        root=library.storage_root()
        data=_state(root)
        data['enabled']=enabled
        _save(root,data)
    return {'ok':True, 'auto_enabled':enabled}


def stop_job():
    _STOP.set()
    return {'ok': True, 'stop_requested': True}


def start_scheduler(repo):
    """Call once at server startup. No background work when server process is stopped."""
    global _SCHEDULER
    with _LOCK:
        if _SCHEDULER is not None:
            return
        def loop():
            while True:
                try:
                    with _LOCK:
                        current = _state(library.storage_root())
                        due = (current['enabled'] and not _LIVE['running'] and
                               time.time() - float(current.get('last_finished_epoch',0)) >= DEFAULT_PERIOD_SECONDS)
                    if due:
                        start_job(repo)
                except (OSError, ValueError, TypeError):
                    pass
                time.sleep(60)
        _SCHEDULER = threading.Thread(target=loop,daemon=True,name='tcg-image-scheduler')
        _SCHEDULER.start()


def handle_get(h, path):
    if path != '/api/local-card-images/auto-status':
        return h.json({'ok':False,'error':'없는 요청'},404)
    try:
        return h.json(status(Path(h.directory)))
    except (ValueError,OSError,TypeError,UnicodeError):
        return h.json({'ok':False,'error':'자동수집 상태 확인 실패'},503)


def handle_post(h, path):
    try:
        if path == '/api/local-card-images/auto-start':
            h._read_json_body(128)  # JSON {} with same-origin checks in caller
            return h.json(start_job(Path(h.directory)),202)
        if path == '/api/local-card-images/auto-stop':
            h._read_json_body(128)
            return h.json(stop_job())
        if path == '/api/local-card-images/auto-enable':
            obj = h._read_json_body(128)
            if set(obj) != {'enabled'}:
                raise ValueError('설정 입력 오류')
            return h.json(set_enabled(obj['enabled']))
        return h.json({'ok':False,'error':'없는 요청'},404)
    except (ValueError,OSError,TypeError,UnicodeError):
        return h.json({'ok':False,'error':'자동수집 요청 오류/저장소 권한 부족'},400)
