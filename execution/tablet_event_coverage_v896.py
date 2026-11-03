"""Registry-wide discovery lane. Search leads never assert an event or card reward.

Runs inside the existing local collection call, with a durable fair cursor and
fixed request/time/storage limits. Historical collectors and WATCH gates stay intact.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request
from urllib.error import HTTPError
import xml.etree.ElementTree as ET

from safe_runtime import (atomic_write_json, exclusive_file_lock, safe_read_text,
                          safe_urlopen, validate_public_https_url)
from tcg_game_registry import load_registry

STATE = 'event_coverage_v896.json'
MAX_BYTES = 2_000_000
MAX_ITEMS = 600
MAX_REQUESTS = 12
MAX_SECONDS = 45
FRESH_SECONDS = 7 * 86400
TOPICS = {
    'movie': ('영화', '극장판', '재개봉', '재상영', '관람특전', '映画', '劇場版', '再上映', 'リバイバル', '入場者特典', 'movie', 'film', 'cinema', 'rerelease', 're-release', 'encore'),
    'collab': ('콜라보', '협업', '제휴', 'コラボ', 'コラボレーション', 'collaboration', 'collab', 'partnership', 'Secret Lair', 'Universes Beyond'),
    'promo': ('프로모', '특전', '증정', '배포', 'プロモ', '配布', '特典', 'キャンペーン', 'promo', 'giveaway', 'campaign', 'reward'),
    'popup': ('팝업', '전시', '카페', 'ポップアップ', '展示', 'カフェ', 'pop-up', 'popup', 'exhibition', 'cafe'),
    'event': ('행사', '이벤트', '대회', 'イベント', '大会', 'event', 'tournament', 'festival', 'convention'),
    'release': ('출시', '발매', '재판', '発売', '再販', 'release', 'launch', 'reprint'),
}
QUERY_TERMS = {
    'KR': ('영화', '재개봉', '콜라보', '프로모', '특전', '팝업', '행사', '발매'),
    'JP': ('映画', '再上映', 'リバイバル', 'コラボ', '配布', '特典', 'ポップアップ', 'イベント', '発売'),
    'US': ('movie', 're-release', 'encore', 'collaboration', 'promo', 'giveaway', 'pop-up', 'event', 'release', 'Secret Lair'),
    'GLOBAL': ('movie', 're-release', 'collaboration', 'promo', 'event', 'release'),
}


def _text(value, limit=250):
    return value.strip() if isinstance(value, str) and 0 < len(value.strip()) <= limit and not any(ord(c) < 32 for c in value) else ''


def cells(registry):
    """Include WATCH discovery without enabling market, grading or promo promotion."""
    result = []
    for game in registry['games']:
        if game['state'] not in {'core', 'promoted', 'watch'} or game['capabilities'].get('promo') is not True:
            continue
        for region in game['regions']:
            if region in QUERY_TERMS:
                result.append({'key': game['id'] + '/' + region, 'game_id': game['id'],
                               'game': game['promo_value'], 'region': region, 'state': game['state'],
                               'canonical': game['canonical'], 'label': game['label_ko'],
                               'aliases': game['aliases'], 'official_source': game['official_source']})
    return sorted(result, key=lambda row: row['key'])


def _stamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00')) if isinstance(value, str) and len(value) <= 64 else None
        return parsed if parsed is not None and parsed.tzinfo is not None else None
    except ValueError:
        return None


def _lineage(url):
    validate_public_https_url(url)
    p = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith('utm_') and k.lower() not in {'fbclid', 'gclid'}]
    return urlunsplit((p.scheme, p.netloc.lower(), p.path, urlencode(sorted(query)), ''))


def _load(root):
    path = Path(root) / STATE
    if not path.exists():
        return {'version': 896, 'cursor': '', 'cells': {}, 'items': []}
    data = json.loads(safe_read_text(path, max_bytes=MAX_BYTES))
    if (not isinstance(data, dict) or data.get('version') != 896
            or not isinstance(data.get('cursor'), str) or len(data['cursor']) > 150
            or not isinstance(data.get('cells'), dict) or len(data['cells']) > 256
            or not isinstance(data.get('items'), list) or len(data['items']) > MAX_ITEMS):
        raise ValueError('event coverage state invalid; previous file preserved')
    if any(not isinstance(v, dict) for v in data['cells'].values()) or any(not isinstance(v, dict) for v in data['items']):
        raise ValueError('event coverage rows invalid; previous file preserved')
    for key, stat in data['cells'].items():
        if not isinstance(key, str) or len(key) > 150 or _stamp(stat.get('attempted_at')) is None:
            raise ValueError('event coverage cell invalid')
        for field, bound in [('requests', 2), ('successes', 2), ('results', 24)]:
            value = stat.get(field)
            if type(value) is not int or not 0 <= value <= bound:
                raise ValueError('event coverage count invalid')
        if stat['successes'] > stat['requests']:
            raise ValueError('event coverage success count invalid')
        if not isinstance(stat.get('errors'), list) or len(stat['errors']) > 3 or any(not _text(e, 80) for e in stat['errors']):
            raise ValueError('event coverage errors invalid')
    for row in data['items']:
        if (not isinstance(row.get('id'), str) or not re.fullmatch('[0-9a-f]{24}', row['id'])
                or not _text(row.get('game_id'), 64) or not _text(row.get('game'), 150)
                or not _text(row.get('title'), 220) or _stamp(row.get('collected_at')) is None
                or row.get('verified') is not False or row.get('card_reward_confirmed') is not False
                or row.get('region') != 'UNKNOWN'):
            raise ValueError('event coverage item invalid')
        for field, allowed in [('search_regions', QUERY_TERMS), ('topics', TOPICS)]:
            values = row.get(field)
            if not isinstance(values, list) or not 1 <= len(values) <= len(allowed) or any(not isinstance(v, str) or v not in allowed for v in values):
                raise ValueError('event coverage item scope invalid')
        _lineage(row.get('source'))
    return data


def query_url(cell, scoped):
    names = tuple(dict.fromkeys((cell['canonical'], cell['label'])))
    def quoted(value):
        return '"' + value.replace('"', '').replace('\\', '') + '"'
    query = '(' + ' OR '.join(quoted(n) for n in names) + ') (' + ' OR '.join(quoted(t) for t in QUERY_TERMS[cell['region']]) + ')'
    if scoped:
        validate_public_https_url(cell['official_source'])
        query += ' site:' + urlsplit(cell['official_source']).hostname
    url = 'https://www.bing.com/search?' + urlencode({'format': 'rss', 'q': query})
    if len(url) > 2048:
        raise ValueError('event search URL budget')
    return url


def _matches(text, term):
    if re.fullmatch(r'[A-Za-z0-9 !:&.\-]+', term):
        return re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', text, re.I) is not None
    return term.casefold() in text.casefold()


def parse_rss(raw, cell, now):
    """No dates, country, reward, freshness or official trust inferred from snippets."""
    if len(raw) > 400_000 or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('unsafe/oversized event RSS')
    root = ET.fromstring(raw)
    if root.tag != 'rss':
        raise ValueError('event RSS schema')
    result = []
    official_host = urlsplit(cell['official_source']).hostname
    names = [cell['canonical'], cell['label'], *cell['aliases']]
    for item in root.findall('./channel/item')[:12]:
        title, excerpt = _text(item.findtext('title'), 220), _text(item.findtext('description'), 500)
        if not title:
            continue
        text = title + ' ' + excerpt
        if not any(_matches(text, n) for n in names if len(n) >= 3):
            continue
        topics = [topic for topic, terms in TOPICS.items() if any(_matches(text, term) for term in terms)]
        if not topics:
            continue
        try:
            source = _lineage(_text(item.findtext('link'), 2048))
        except ValueError:
            continue
        result.append({'id': hashlib.sha256((cell['game_id'] + '|' + source).encode()).hexdigest()[:24],
                       'game_id': cell['game_id'], 'game': cell['game'], 'registry_state': cell['state'],
                       'search_regions': [cell['region']], 'region': 'UNKNOWN', 'title': title,
                       'source': source, 'excerpt': excerpt, 'topics': topics, 'collected_at': now.isoformat(),
                       'source_kind': 'registry_bing_search_v896', 'official_domain_match': urlsplit(source).hostname == official_host,
                       'verified': False, 'card_reward_confirmed': False, 'date_status': 'UNCONFIRMED',
                       'status': '발견 후보 · 개최국·날짜·카드 특전 공식 확인 필요'})
    return result


def fetch(cell, scoped, now, *, deadline=None, clock=time.monotonic):
    deadline = clock() + 6 if deadline is None else deadline
    remaining = deadline - clock()
    if remaining <= 0:
        raise TimeoutError('event request deadline')
    req = Request(query_url(cell, scoped), headers={'User-Agent': 'TCG-Grader-Registry-Discovery/896', 'Accept': 'application/rss+xml'})
    with safe_urlopen(req, timeout=min(3, remaining), allowed_hosts={'www.bing.com'}, max_redirects=1) as response:
        chunks, size = [], 0
        while size <= 400_000:
            if clock() >= deadline:
                raise TimeoutError('event body deadline')
            chunk = response.read1(min(8192, 400_001 - size))
            if clock() >= deadline:
                raise TimeoutError('event body deadline')
            if not chunk:
                break
            chunks.append(chunk); size += len(chunk)
        raw = b''.join(chunks)
    return parse_rss(raw, cell, now)


def collect(root, *, fetcher=None, now=None, clock=time.monotonic):
    now = datetime.now(timezone.utc) if now is None else now
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError('aware event collection clock required')
    configured = cells(load_registry(Path(root)))
    with exclusive_file_lock(Path(root) / STATE, timeout_seconds=0):
        data = _load(root)
        cooldown = _stamp(data.get('cooldown_until'))
        last_run = _stamp(data.get('last_run_at'))
        if last_run is not None and (now - last_run).total_seconds() < 1800:
            summary = report(configured, data, now=now)
            summary.pop('items')
            return summary | {'requests_this_run': 0, 'errors_this_run': ['RUN_INTERVAL_DEFERRED']}
        if cooldown is not None and now < cooldown:
            summary = report(configured, data, now=now)
            summary.pop('items')
            return summary | {'requests_this_run': 0, 'errors_this_run': ['PROVIDER_COOLDOWN']}
        keys = {c['key'] for c in configured}
        history = {key: value for key, value in data['cells'].items() if key in keys}
        # Key cursor survives registry additions/removals without starving later games.
        ordered = [c for c in configured if c['key'] > data['cursor']] + [c for c in configured if c['key'] <= data['cursor']]
        items = {r.get('id'): r for r in data['items'] if isinstance(r.get('id'), str)}
        started, requests, errors, blocked = clock(), 0, [], False
        for cell in ordered:
            if blocked or requests + 2 > MAX_REQUESTS or clock() - started >= MAX_SECONDS - 6:
                break
            old_time = _stamp(history.get(cell['key'], {}).get('attempted_at'))
            if old_time is not None and 0 <= (now - old_time).total_seconds() < 6 * 3600:
                continue
            stat = {'attempted_at': now.isoformat(), 'requests': 0, 'successes': 0, 'results': 0, 'errors': []}
            for scoped in (True, False):
                if clock() - started >= MAX_SECONDS - 3:
                    stat['errors'].append('DEFERRED_DEADLINE')
                    errors.append(cell['key'] + ':DEFERRED_DEADLINE')
                    break
                requests += 1; stat['requests'] += 1
                try:
                    rows = fetch(cell, scoped, now, deadline=started + MAX_SECONDS, clock=clock) if fetcher is None else fetcher(cell, scoped, now)
                    if not isinstance(rows, list) or len(rows) > 12:
                        raise ValueError('event result bounds')
                    stat['successes'] += 1
                    for row in rows:
                        previous = items.get(row['id'], {})
                        row['search_regions'] = sorted(set(previous.get('search_regions', []) + row['search_regions']))
                        row['topics'] = sorted(set(previous.get('topics', []) + row['topics']))
                        items[row['id']] = row
                    stat['results'] += len(rows)
                except HTTPError as exc:
                    stat['errors'].append('HTTP_' + str(exc.code))
                    errors.append(cell['key'] + ':HTTP_' + str(exc.code))
                    if exc.code in (403, 429):
                        from datetime import timedelta
                        data['cooldown_until'] = (now + timedelta(hours=24)).isoformat()
                        blocked = True
                        break
                except (OSError, ValueError, TypeError, KeyError, ET.ParseError):
                    stat['errors'].append('SEARCH_FAILED')
                    errors.append(cell['key'] + ':SEARCH_FAILED')
            if stat['requests'] == 0:
                break
            history[cell['key']] = stat
            data['cursor'] = cell['key']
        data.update({'updated_at': now.isoformat(), 'cells': history,
                     'items': sorted(items.values(), key=lambda r: str(r.get('collected_at', '')), reverse=True)[:MAX_ITEMS]})
        if requests:
            data['last_run_at'] = now.isoformat()
        encoded = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
        if len(encoded.encode('utf-8')) > MAX_BYTES:
            raise ValueError('event state size limit; previous file preserved')
        summary = report(configured, data, now=now)
        summary.pop('items')
        atomic_write_json(Path(root) / STATE, data, suffix='.v896.tmp')
        return summary | {'candidate_count': len(data['items']), 'requests_this_run': requests, 'errors_this_run': errors}


def report(configured, data, *, now):
    result = []
    for cell in configured:
        stat = data['cells'].get(cell['key'], {})
        stamp = _stamp(stat.get('attempted_at'))
        fresh = stamp is not None and 0 <= (now - stamp).total_seconds() <= FRESH_SECONDS
        status = 'NOT_SEARCHED' if not stamp else 'STALE_SEARCH' if not fresh else 'SEARCH_FAILED' if stat.get('successes', 0) == 0 else 'PARTIAL_SEARCH' if stat.get('successes', 0) < 2 else 'SEARCHED_UNCONFIRMED'
        result.append({k: cell[k] for k in ('key', 'game_id', 'game', 'region', 'state')} | {'status': status, 'attempted_at': stat.get('attempted_at'), 'results': stat.get('results', 0)})
    return {'game_count': len({c['game_id'] for c in configured}), 'configured_cells': len(configured),
            'cells': result, 'items': data['items'], 'policy': '검색 성공은 행사·특전 확인이나 누락 없음의 증거가 아닙니다.'}


def install(route_module, root):
    """Compose once with original collector; never expand its fixed legacy fanout."""
    original = route_module.collect_all
    if getattr(original, '_registry_v896', False):
        return
    def wrapped():
        rows, errors, status = original()
        status = dict(status)
        try:
            status['registry_coverage_v896'] = collect(root)
        except (OSError, ValueError, TypeError, TimeoutError):
            status['registry_coverage_v896'] = {'status': 'HOLD_PREVIOUS_COVERAGE'}
            errors = list(errors) + ['전체 TCG 이벤트 수집 보류 · 이전 자료 보존']
        # Expanded-game leads live in their own bounded store/view. They must not
        # pass legacy core-only merging or imply WATCH activation.
        return rows, errors, status
    wrapped._registry_v896 = True
    route_module.collect_all = wrapped


def install_update(core, root):
    """The existing manual/regular updater uses subprocesses: hook its parent too.

    Reuse its existing worker and POST origin gate; no second scheduler/worker.
    """
    original = core.update_cycle
    if getattr(original, '_registry_v896', False):
        return
    def wrapped(*args, **kwargs):
        try:
            coverage = collect(root)
        except (OSError, ValueError, TypeError, TimeoutError):
            coverage = {'status': 'HOLD_PREVIOUS_COVERAGE'}
        result = original(*args, **kwargs)
        if isinstance(result, dict):
            result['registry_event_coverage_v896'] = coverage
        return result
    wrapped._registry_v896 = True
    core.update_cycle = wrapped


def render(root, *, game_id='', region=''):
    configured = cells(load_registry(Path(root)))
    data = _load(root)
    snapshot = report(configured, data, now=datetime.now(timezone.utc))
    def esc(v):
        return html.escape(str(v), quote=True)
    games = {c['game_id']: c['game'] for c in configured}
    if game_id and game_id not in games or region and region not in QUERY_TERMS:
        raise ValueError('unknown event filter')
    options = '<option value="">전체 게임</option>' + ''.join('<option value="' + esc(key) + '"' + (' selected' if key == game_id else '') + '>' + esc(value) + '</option>' for key, value in sorted(games.items()))
    regions = '<option value="">전체 검색국가</option>' + ''.join('<option' + (' selected' if key == region else '') + '>' + key + '</option>' for key in QUERY_TERMS)
    filters = '<form action="/tablet-events-all" method="get"><select name="game">' + options + '</select><select name="region">' + regions + '</select><button>보기</button></form>'
    table = ''.join('<tr><td>' + esc(c['game']) + '</td><td>' + esc(c['region']) + '</td><td>' + esc(c['state']) + '</td><td>' + esc(c['status']) + '</td></tr>' for c in snapshot['cells'] if (not game_id or c['game_id'] == game_id) and (not region or c['region'] == region))
    cards = []
    for row in snapshot['items']:
        if game_id and row.get('game_id') != game_id or region and region not in row.get('search_regions', []):
            continue
        try:
            source = _lineage(row.get('source', ''))
        except (ValueError, TypeError):
            continue
        cards.append('<article><small>' + esc(row.get('game')) + ' · 검색국가 ' + esc(', '.join(row.get('search_regions', []))) + '</small><h2>' + esc(row.get('title')) + '</h2><p>' + esc(' · '.join(row.get('topics', []))) + '</p><p>개최국·일정·카드 특전 미확인 · 검색 수집 ' + esc(row.get('collected_at')) + '</p><a rel="noopener noreferrer" target="_blank" href="' + esc(source) + '">출처 확인 ↗</a></article>')
    return '<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src &#39;none&#39;; style-src &#39;unsafe-inline&#39;; base-uri &#39;none&#39;; form-action &#39;self&#39;"><title>전체 TCG 이벤트 수집</title><style>body{font:17px system-ui;background:#f3f6fb;color:#18223b;max-width:1100px;margin:auto;padding:20px}a{color:#1749c9}article,details{background:white;border:1px solid #dae1ec;border-radius:16px;padding:18px;margin:14px 0}h2{font-size:20px}table{width:100%;font-size:14px}td{padding:8px;border-bottom:1px solid #eee}small{color:#52617b}select,button{font:inherit;padding:12px;max-width:100%;margin:4px;border:1px solid #ccd5e6;border-radius:10px}button{background:#1749c9;color:white}</style><a href="/tablet-unified">← 카드·사진 보관함</a><h1>전체 TCG · 행사·콜라보·영화·프로모</h1><p>' + esc(snapshot['game_count']) + '종 · ' + esc(snapshot['configured_cells']) + '개 게임·국가 검색 경로. 기존 행사 목록은 기존 홈에서 계속 볼 수 있습니다.</p><p>한 번에 최대 12회, 6개 경로를 순환 검색합니다. WATCH는 발견 후보로 유지합니다. 검색국가는 실제 개최국이나 카드 판본이 아닙니다.</p>' + filters + '<p>NOT_SEARCHED 미검색 · STALE_SEARCH 재검색 필요 · SEARCH_FAILED 오류 · PARTIAL_SEARCH 일부 오류 · SEARCHED_UNCONFIRMED 검색 완료/내용 미확인</p><details><summary>전체 게임·국가 수집 상태</summary><table><tr><th>게임</th><th>검색국가</th><th>등록상태</th><th>수집상태</th></tr>' + table + '</table></details>' + ''.join(cards) + '<p>후보가 없어도 행사가 없다는 뜻은 아닙니다. 자료 갱신 후 이 화면을 새로고침하세요.</p></html>'
