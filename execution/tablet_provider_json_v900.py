"""Budgeted JSON-only transport for the collector's existing raw GitHub files.

Raw JSON files may be served as text/plain. This does not authorize arbitrary
text, image URLs, new providers, redirect following, or country substitution.
"""
import json
import re
import time
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from urllib.parse import urlsplit

from safe_runtime import reject_nonstandard_json, unique_json_object

ONEPIECE = re.compile(r'https://raw\.githubusercontent\.com/Kuroro1990/OPTCG/main/(english|japanese|chinese-taiwan)/(packs\.json|data/[0-9]{4,8}\.json)')
RIFTBOUND = 'https://raw.githubusercontent.com/slimtreble/Riftbound-card-data/main/cards.json'
MIMES = {'application/json', 'application/octet-stream', 'text/plain'}


def provider_for(url):
    if not isinstance(url, str):
        return None
    if ONEPIECE.fullmatch(url):
        return 'PunkRecords'
    return 'RiftboundData' if url == RIFTBOUND else None


def read_json(auto, url, provider):
    if provider not in ('PunkRecords', 'RiftboundData') or provider_for(url) != provider or not auto._url_allowed(url):
        raise auto.ProviderError('기존 JSON 출처 주소 확인 필요')
    budget = getattr(auto._BUDGET_CONTEXT, 'current', None)
    if budget is None or budget.provider != provider:
        raise auto.ProviderError('동일 공급사 수집 예산이 필요합니다')
    allowance = min(auto.MAX_PROVIDER_BYTES, budget.byte_allowance())
    if allowance <= 0:
        raise auto.policy.Deferred('다운로드 용량 예산 도달')
    entry = budget.reserve_request(provider)
    received = 0
    deadline = time.monotonic() + min(12, budget.remaining_seconds())

    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise auto.ProviderError('JSON 출처 리다이렉트 차단')

    request = Request(url, headers={'User-Agent': 'TCGTabletPrivateImageCache/5 (+personal offline collection)',
                                    'Accept': 'application/json, text/plain'})
    try:
        opener = build_opener(ProxyHandler({}), NoRedirect())
        with opener.open(request, timeout=max(0.2, min(9, budget.remaining_seconds()))) as response:
            if response.status != 200 or response.geturl() != url:
                raise auto.ProviderError('JSON 출처 응답 오류')
            mime = response.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
            if mime not in MIMES:
                raise auto.ProviderError('JSON 출처 MIME 형식 오류')
            declared = response.headers.get('Content-Length', '')
            if declared and (not declared.isdecimal() or int(declared) > allowance):
                raise auto.ProviderError('JSON 응답 크기 제한 초과')
            chunks = []
            while True:
                if time.monotonic() >= deadline:
                    raise auto.policy.Deferred('출처 응답시간 예산 도달')
                chunk = response.read1(min(65536, allowance + 1 - received))
                received += len(chunk)
                if received > allowance:
                    raise auto.ProviderError('JSON 다운로드 크기 제한 초과')
                if time.monotonic() >= deadline:
                    raise auto.policy.Deferred('출처 응답시간 예산 도달')
                if not chunk:
                    break
                chunks.append(chunk)
            if declared and received != int(declared):
                raise auto.ProviderError('JSON 출처 응답 길이 불일치')
        value = json.loads(b''.join(chunks).decode('utf-8'), object_pairs_hook=unique_json_object,
                           parse_constant=reject_nonstandard_json)
        if not isinstance(value, (dict, list)):
            raise auto.ProviderError('JSON 목록/객체 형식 확인 필요')
        return value
    except HTTPError as error:
        if error.code in (403, 429):
            budget.block(provider, error.code, error.headers.get('Retry-After') if error.headers else None)
        code = error.code
        error.close()
        raise auto.ProviderError('JSON 출처 HTTP ' + str(code)) from None
    except (URLError, OSError, HTTPException):
        raise auto.ProviderError('JSON 출처 연결 실패') from None
    except (UnicodeError, ValueError, RecursionError) as error:
        # Preserve the existing policy's Deferred and fixed ProviderError messages.
        if isinstance(error, (auto.ProviderError, auto.policy.Deferred)):
            raise
        raise auto.ProviderError('출처 JSON 형식 오류') from None
    finally:
        budget.add_bytes(entry, min(received, allowance))


def onepiece_candidates(auto, region, page):
    """Keep stored 25-page cursors, including sets with more than 200 cards.

    The final page contains the bounded tail. The existing collector advances a
    page only after all candidates are processed; its download/time/day limits
    still apply and completed fingerprints are skipped on the next pass.
    """
    if type(page) is not int or not 1 <= page <= 100000:
        raise auto.ProviderError('OnePiece 페이지 식별값 오류')
    locale, host = auto.ONEPIECE_LOCALES[region]
    base = 'https://raw.githubusercontent.com/Kuroro1990/OPTCG/main/' + locale + '/'
    packs = auto.fetch_json(base + 'packs.json')
    if not isinstance(packs, dict) or len(packs) > 1000:
        raise auto.ProviderError('OnePiece 세트 목록 형식 오류')
    ids = sorted((key for key in packs if re.fullmatch(r'[0-9]{4,8}', key)), reverse=True)
    pack_index, part = divmod(page - 1, 25)
    if pack_index >= len(ids):
        return [], 1
    pack = ids[pack_index]
    url = base + 'data/' + pack + '.json'
    rows = auto.fetch_json(url)
    if not isinstance(rows, list) or len(rows) > 1500:
        raise auto.ProviderError('OnePiece 카드 목록 형식 오류')
    start = part * 8
    selected = rows[start:] if part == 24 else rows[start:start + 8]
    next_page = page + 1 if start + 8 < len(rows) and part < 24 else (pack_index + 1) * 25 + 1
    out = []
    for row in selected:
        if not isinstance(row, dict) or str(row.get('pack_id')) != pack:
            continue
        ident, image = row.get('id'), row.get('img_full_url')
        if not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z0-9-]{3,35}', ident):
            continue
        parsed = urlsplit(image) if isinstance(image, str) else None
        if (not parsed or parsed.scheme != 'https' or parsed.hostname != host or parsed.port not in (None, 443)
                or parsed.username is not None or parsed.password is not None or parsed.fragment
                or not re.fullmatch(r'/images/cardlist/card/[A-Za-z0-9_.-]{3,80}\.png', parsed.path)
                or parsed.query and not re.fullmatch(r'[0-9]{1,15}', parsed.query)):
            continue
        name = auto._safe_name(row.get('name'))
        if not name:
            continue
        info = packs.get(pack)
        title = info.get('raw_title', '') if isinstance(info, dict) else ''
        title = title if isinstance(title, str) else ''
        rarity = str(row.get('rarity') or '').lower()
        promo = 'promo' in rarity or 'promo' in title.lower() or '推廣' in title or 'プロモ' in title
        out.append({'provider': 'PunkRecords', 'key': 'onepiece/' + locale + '/' + pack + '/' + ident,
                    'game_id': 'onepiece', 'region': region, 'kind': 'PROMO' if promo else 'CARD',
                    'name': name + ' · ' + ident, 'url': image, 'source': url,
                    'card_metadata': auto._metadata(card_code=ident, set_name=title, rarity=row.get('rarity'))})
    return out, next_page


def install(auto):
    """Called once by the unified adapter before its existing scheduler starts."""
    original = auto.fetch_json
    if getattr(original, '_tcg_raw_json_v900', False):
        return
    if auto._THREAD is not None or auto._SCHEDULER is not None:
        raise RuntimeError('수집 시작 전 JSON 전송 경로를 연결해야 합니다')

    def fetch_json(url):
        provider = provider_for(url)
        return read_json(auto, url, provider) if provider else original(url)

    fetch_json._tcg_raw_json_v900 = True
    auto.fetch_json = fetch_json
    auto.candidates_onepiece = lambda region, page: onepiece_candidates(auto, region, page)
