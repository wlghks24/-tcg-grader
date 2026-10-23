"""Tablet-local private card image library for the TCG Grader localhost server.

Files are kept in the Android shared internal Pictures directory, *not GitHub*.
Requires `termux-setup-storage` and explicit Android storage permission.
Manual photos use user action; optional auto module fetches rate-limited public APIs.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import ipaddress
import json
import os
import re
import tempfile
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_RECORDS = 2500
MAX_TOTAL_BYTES = 500 * 1024 * 1024
MAX_JSON_BYTES = 7_500_000
MAX_INDEX_BYTES = 1_200_000
ROOT_NAME = 'TCG_Card_Images'
ID_PATTERN = re.compile(r'^[0-9a-f]{32}$')
SHA_PATTERN = re.compile(r'^[0-9a-f]{64}$')
GAME_PATTERN = re.compile(r'^[a-z0-9][a-z0-9-]{0,63}$')
REGIONS = frozenset({'KR', 'JP', 'US', 'CN-S', 'CN-T', 'OTHER'})
CARD_METADATA_LIMITS = {'card_code':90,'set_code':40,'card_number':30,'set_name':130,
                        'language':12,'rarity':60,'card_type':60}
KINDS = frozenset({'CARD', 'BOX', 'PACK', 'COLLECTION', 'PROMO', 'OTHER', 'ACCESSORY', 'BUNDLE', 'DECK'})
LOCK = threading.RLock()


def storage_root():
    """No silent private fallback: owner must grant Android shared storage."""
    shared = Path.home() / 'storage' / 'shared'
    if not shared.exists() or not shared.is_dir():
        raise ValueError('Termux 공유 저장소 권한이 없습니다. termux-setup-storage 후 사진/파일 접근을 허용하세요.')
    # Android storage symlink is expected and explicitly allowed here.
    parent = (shared / 'Pictures').resolve()
    if not parent.is_dir():
        raise ValueError('태블릿 내부 저장소 Pictures 폴더를 열 수 없습니다.')
    target = parent / ROOT_NAME
    if target.is_symlink():
        raise ValueError('이미지 보관함 심볼릭 링크는 사용할 수 없습니다.')
    target.mkdir(mode=0o700, exist_ok=True)
    image_dir = target / 'images'
    if image_dir.is_symlink():
        raise ValueError('이미지 폴더 심볼릭 링크는 사용할 수 없습니다.')
    image_dir.mkdir(mode=0o700, exist_ok=True)
    return target


def _atomic_write(path, content):
    fd, tmp = tempfile.mkstemp(prefix='.tcg-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as h:
            h.write(content)
            h.flush()
            os.fsync(h.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _registry_ids(repo_root):
    target = Path(repo_root) / 'tcg_game_registry.json'
    if target.is_symlink() or target.stat().st_size > 1_000_000:
        raise ValueError('게임 목록 파일이 안전하지 않습니다.')
    payload = json.loads(target.read_text(encoding='utf-8'))
    if payload.get('schema_version') != 1 or not isinstance(payload.get('games'), list):
        raise ValueError('게임 목록 형식을 확인할 수 없습니다.')
    return {row['id'] for row in payload['games'] if isinstance(row, dict) and isinstance(row.get('id'), str) and GAME_PATTERN.fullmatch(row['id'])}


def _load(root):
    p = root / 'index.json'
    if not p.exists():
        return {'version': 1, 'items': []}
    if p.is_symlink() or p.stat().st_size > MAX_INDEX_BYTES:
        raise ValueError('보관함 목록이 손상되었거나 너무 큽니다.')
    payload = json.loads(p.read_text(encoding='utf-8'))
    if payload.get('version') != 1 or not isinstance(payload.get('items'), list) or len(payload['items']) > MAX_RECORDS:
        raise ValueError('보관함 목록 형식 오류')
    return payload


def _save_index(root, payload):
    content = (json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')
    if len(content) > MAX_INDEX_BYTES:
        raise ValueError('보관함 목록 용량 제한 초과 · 기존 자료 보존')
    _atomic_write(root / 'index.json', content)


def sniff(data):
    if data.startswith(b'\xff\xd8\xff') and data[-2:] == b'\xff\xd9':
        return 'image/jpeg', 'jpg'
    if data.startswith(b'\x89PNG\r\n\x1a\n') and len(data) >= 45 and data[12:16] == b'IHDR' and b'IEND' in data[-20:]:
        return 'image/png', 'png'
    if len(data) >= 30 and data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image/webp', 'webp'
    raise ValueError('JPG/PNG/WebP 사진만 저장할 수 있습니다.')


def _text(value, limit):
    if not isinstance(value, str):
        raise ValueError('문자 입력 형식 오류')
    value = value.strip()
    if not value or len(value) > limit or any(ord(ch) < 32 for ch in value):
        raise ValueError('필수 텍스트 입력 오류')
    return value


def _image_filename(record):
    sha = record.get('sha256', '')
    ext = record.get('ext', '')
    if not isinstance(sha, str) or not SHA_PATTERN.fullmatch(sha) or ext not in ('jpg', 'png', 'webp'):
        raise ValueError('저장 파일 식별값 오류')
    return sha + '.' + ext


def list_images():
    with LOCK:
        root = storage_root()
        payload = _load(root)
        result = [{k: v for k, v in row.items() if k not in ('sha256', 'ext')} for row in payload['items']]
        return {'ok': True, 'count': len(result), 'items': list(reversed(result)), 'folder': str(root)}


def save_image(repo_root, incoming, *, trusted_auto=False):
    required = {'game_id', 'region', 'kind', 'name', 'image_base64'}
    extra = {'provider', 'source_url', 'source_id'}
    metadata_field = {'card_metadata'}
    if not isinstance(incoming, dict) or not required.issubset(incoming) or set(incoming) - required - extra - metadata_field:
        raise ValueError('사진 등록 입력항목 오류')
    if set(incoming) & extra and (set(incoming) & extra != extra or not trusted_auto):
        raise ValueError('출처 정보는 검증된 자동수집만 기록할 수 있습니다.')
    card_metadata = {}
    if 'card_metadata' in incoming:
        raw_metadata = incoming['card_metadata']
        if not trusted_auto or not extra.issubset(incoming) or not isinstance(raw_metadata,dict) or set(raw_metadata)-set(CARD_METADATA_LIMITS):
            raise ValueError('카드 메타데이터는 검증된 자동수집만 기록할 수 있습니다.')
        card_metadata = {key:_text(value,CARD_METADATA_LIMITS[key]) for key,value in raw_metadata.items()}
    game = _text(incoming['game_id'], 64)
    if not GAME_PATTERN.fullmatch(game) or game not in _registry_ids(repo_root):
        raise ValueError('30개 게임 목록에 없는 게임입니다.')
    region = _text(incoming['region'], 8)
    kind = _text(incoming['kind'], 20)
    name = _text(incoming['name'], 130)
    if region not in REGIONS or kind not in KINDS:
        raise ValueError('국가 또는 이미지 종류 오류')
    b64 = incoming['image_base64']
    if not isinstance(b64, str) or len(b64) > (MAX_IMAGE_BYTES * 4 // 3 + 100):
        raise ValueError('사진 크기가 5MB를 넘습니다.')
    # Explicit data URI is convenient for browser FileReader, but data is stored as binary.
    if not re.match(r'^data:image/(jpeg|png|webp);base64,', b64):
        raise ValueError('사진 인코딩 형식 오류')
    try:
        data = base64.b64decode(b64.partition(',')[2], validate=True)
    except (ValueError, binascii.Error):
        raise ValueError('사진 데이터 오류')
    if len(data) < 24 or len(data) > MAX_IMAGE_BYTES:
        raise ValueError('사진 크기 오류(최대 5MB)')
    mime, ext = sniff(data)
    if not b64.startswith('data:' + mime + ';base64,'):
        raise ValueError('파일 종류와 사진 내용이 다릅니다.')
    # Validate provenance BEFORE touching disk so invalid metadata cannot leave
    # untracked orphan image blobs behind.
    provenance = {'origin': 'manual'}
    if extra.issubset(incoming):
        provider = _text(incoming['provider'], 35)
        source_id = _text(incoming['source_id'], 140)
        source_url = _text(incoming['source_url'], 600)
        url = urlparse(source_url)
        if (provider not in ('TCGdex', 'YGOPRODeck', 'Scryfall', 'LorcanaAPI', 'PunkRecords', 'SWUDB', 'GCGAPI', 'RiftboundData') or url.scheme != 'https' or
                url.username or url.password or url.port not in (None, 443) or
                url.hostname not in ('api.tcgdex.net', 'db.ygoprodeck.com',
                                     'api.scryfall.com', 'api.lorcana-api.com',
                                     'raw.githubusercontent.com', 'api.swu-db.com', 'api.gcgapi.com')):
            raise ValueError('자동 이미지 출처가 허용되지 않습니다.')
        if provider == 'RiftboundData' and source_url != 'https://raw.githubusercontent.com/slimtreble/Riftbound-card-data/main/cards.json':
            raise ValueError('Riftbound 데이터 출처 불일치')
        if provider == 'PunkRecords' and not source_url.startswith('https://raw.githubusercontent.com/Kuroro1990/OPTCG/main/'):
            raise ValueError('OnePiece 데이터 출처 불일치')
        provenance = {'origin': 'auto', 'provider': provider,
                      'source_url': source_url, 'source_id': source_id}
    source_digest = hashlib.sha256(data).hexdigest()
    storage_policy = None
    if trusted_auto:
        from execution.tablet_image_collection_policy import lossless_storage
        data, storage_policy = lossless_storage(data)
        mime, ext = sniff(data)
    digest = hashlib.sha256(data).hexdigest()
    with LOCK:
        root = storage_root()
        payload = _load(root)
        rows = payload['items']
        if len(rows) >= MAX_RECORDS:
            raise ValueError('등록 이미지가 최대 2500장입니다.')
        current_files = {(_image_filename(row)) for row in rows}
        file_sizes = {}
        for row in rows:
            filename = _image_filename(row)
            size = int(row.get('bytes', 0))
            if size < 0 or size > MAX_IMAGE_BYTES:
                raise ValueError('보관함 용량정보 오류')
            file_sizes[filename] = size
        total_bytes = sum(file_sizes.values())
        target = root / 'images' / (digest + '.' + ext)
        if target.is_symlink():
            raise ValueError('파일 경로가 안전하지 않습니다.')
        if not target.exists() and total_bytes + len(data) > MAX_TOTAL_BYTES:
            raise ValueError('보관함 용량 제한 500MB 초과')
        wrote_file = False
        if not target.exists():
            _atomic_write(target, data)
            wrote_file = True
        entry = {
            'id': uuid.uuid4().hex, 'game_id': game, 'region': region,
            'kind': kind, 'name': name, 'sha256': digest, 'ext': ext,
            'mime': mime, 'bytes': len(data),
            'added_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        }
        entry.update(provenance)
        if card_metadata:
            entry['card_metadata'] = card_metadata
        if storage_policy is not None:
            entry['image_storage'] = storage_policy
            entry['source_sha256'] = source_digest
        rows.append(entry)
        try:
            _save_index(root, payload)
        except Exception:
            rows.pop()
            if wrote_file:
                try: target.unlink()
                except OSError: pass
            raise
        return {'ok': True, 'id': entry['id'], 'count': len(rows), 'folder': str(root),
                'stored_bytes':len(data), 'source_bytes':storage_policy['source_bytes'] if storage_policy else len(data)}



def enrich_auto_metadata(image_id, provider, source_id, metadata):
    """Fill missing explicit fields only; no image writes/downloads or identity change.

    A completed image deleted by its owner remains deleted. Conflicting provider
    values never replace previously stored metadata or create catalog facts.
    """
    if not isinstance(image_id,str) or not ID_PATTERN.fullmatch(image_id):return False
    if not isinstance(metadata,dict) or set(metadata)-set(CARD_METADATA_LIMITS):return False
    checked={key:_text(value,CARD_METADATA_LIMITS[key]) for key,value in metadata.items()}
    if not checked:return False
    with LOCK:
        root=storage_root();payload=_load(root)
        record=next((r for r in payload['items'] if r.get('id')==image_id),None)
        if (not record or record.get('origin')!='auto' or record.get('provider')!=provider
                or record.get('source_id')!=source_id):return False
        previous=record.get('card_metadata',{})
        if not isinstance(previous,dict):raise ValueError('카드 메타데이터 저장형식 오류')
        if any(key in previous and previous[key]!=value for key,value in checked.items()):return False
        combined={**checked,**previous}
        if combined==previous:return False
        record['card_metadata']=combined
        _save_index(root,payload)
        return True


def get_image(image_id):
    if not ID_PATTERN.fullmatch(image_id):
        raise ValueError('이미지 식별번호 오류')
    with LOCK:
        root = storage_root()
        record = next((x for x in _load(root)['items'] if x.get('id') == image_id), None)
        if not record:
            raise FileNotFoundError('이미지 없음')
        target = root / 'images' / _image_filename(record)
        if target.is_symlink() or not target.is_file() or target.stat().st_size > MAX_IMAGE_BYTES:
            raise FileNotFoundError('안전한 사진 파일 없음')
        content = target.read_bytes()
        mime, ext = sniff(content)
        if mime != record.get('mime') or ext != record.get('ext') or hashlib.sha256(content).hexdigest() != record.get('sha256'):
            raise ValueError('이미지 무결성 검사 실패')
        return mime, content


def delete_image(image_id):
    if not ID_PATTERN.fullmatch(image_id):
        raise ValueError('이미지 식별번호 오류')
    with LOCK:
        root = storage_root()
        payload = _load(root)
        row = next((x for x in payload['items'] if x.get('id') == image_id), None)
        if row is None:
            raise FileNotFoundError('이미지 없음')
        filename = _image_filename(row)
        payload['items'] = [x for x in payload['items'] if x.get('id') != image_id]
        _save_index(root, payload)
        if not any(_image_filename(x) == filename for x in payload['items']):
            target = root / 'images' / filename
            if target.is_file() and not target.is_symlink():
                target.unlink()
        return {'ok': True, 'count': len(payload['items'])}


def _local_request(h):
    try:
        return ipaddress.ip_address(h.client_address[0]).is_loopback
    except (TypeError, ValueError):
        return False


def handle_get(h, path):
    if not _local_request(h):
        return h.json({'ok': False, 'error': '태블릿 내부 접속 전용'}, 403)
    try:
        if path == '/api/local-card-images/catalog-links':
            import tablet_catalog_auto_reflect_v43 as sync
            return h.json(sync.read_live(Path(h.directory)))
        if path == '/api/local-card-images/opportunities':
            from urllib.parse import urlsplit,parse_qs
            import tcg_profit_radar_v47 as radar
            args=parse_qs(urlsplit(h.path).query)
            game=args.get('game',[''])[0][:64]
            kind=args.get('kind',[''])[0][:24]
            limit=args.get('limit',['100'])[0]
            try:
                return h.json(radar.read(Path(h.directory),game=game,kind=kind,limit=limit))
            except (radar.RadarError, ValueError, TypeError):
                return h.json({'ok':False,'error':'수익후보 수집 결과 확인 보류'},503)
        if path == '/api/local-card-images/cross-status':
            import tablet_collection_image_bridge_v42 as bridge
            return h.json(bridge.analyze(Path(h.directory)))
        if path == '/api/local-card-images/auto-status':
            import tablet_image_auto_v2
            return tablet_image_auto_v2.handle_get(h, path)
        if path == '/api/local-card-images':
            return h.json(list_images())
        image_id = path.removeprefix('/api/local-card-images/file/')
        if not path.startswith('/api/local-card-images/file/'):
            return h.json({'ok': False, 'error': '잘못된 요청'}, 404)
        mime, content = get_image(image_id)
        h.send_response(200)
        h.send_header('Content-Type', mime)
        h.send_header('Content-Length', str(len(content)))
        h.send_header('Cache-Control', 'private, no-store')
        h.send_header('X-Content-Type-Options', 'nosniff')
        h.send_header('Content-Security-Policy', "default-src 'none'; sandbox")
        h.end_headers()
        return h.wfile.write(content)
    except FileNotFoundError:
        return h.json({'ok': False, 'error': '사진을 찾을 수 없습니다.'}, 404)
    except (ValueError, OSError, UnicodeError, TypeError, ImportError):
        return h.json({'ok': False, 'error': '저장소/파일 검증 실패'}, 503)


def handle_post(h, path):
    if not _local_request(h):
        return h.json({'ok': False, 'error': '태블릿 내부 접속 전용'}, 403)
    try:
        if path in ('/api/local-card-images/auto-start', '/api/local-card-images/auto-stop', '/api/local-card-images/auto-enable'):
            import tablet_image_auto_v2
            return tablet_image_auto_v2.handle_post(h,path)
        if path == '/api/local-card-images/save':
            return h.json(save_image(Path(h.directory), h._read_json_body(MAX_JSON_BYTES)), 201)
        if path == '/api/local-card-images/delete':
            obj = h._read_json_body(1024)
            if set(obj) != {'id'} or not isinstance(obj['id'], str):
                raise ValueError('삭제 입력 오류')
            return h.json(delete_image(obj['id']))
        return h.json({'ok': False, 'error': '없는 요청'}, 404)
    except FileNotFoundError:
        return h.json({'ok': False, 'error': '사진을 찾을 수 없습니다.'}, 404)
    except (ValueError, OSError, UnicodeError, TypeError, ImportError):
        return h.json({'ok': False, 'error': '사진 등록·삭제 오류 또는 저장소 권한 부족'}, 400)
