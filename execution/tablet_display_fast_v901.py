"""Read an existing smaller view or return the verified original without encoding.

HTTP requests never build/write caches, start workers or contact providers.
Cache failures cannot revive a deleted, changed or integrity-invalid original.
"""
import hashlib
import io
import json
import threading

from PIL import Image

import tablet_image_library_v1 as library
from safe_runtime import safe_read_bytes, reject_nonstandard_json, unique_json_object

MAX_PIXELS = 12_000_000
MAX_META_BYTES = 4096
FORMATS = {'JPEG', 'PNG', 'WEBP'}
_DECODE_SLOTS = threading.BoundedSemaphore(2)


def _shape(data, *, normalized=False):
    """Decode bounded bytes without converting, resizing or encoding them."""
    if not isinstance(data, bytes) or not 0 < len(data) <= library.MAX_IMAGE_BYTES:
        raise ValueError('사진 크기 제한 초과')
    # Bound decoded pixel buffers across ThreadingHTTPServer request threads.
    # No library lock is held while waiting for a decode slot or loading pixels.
    with _DECODE_SLOTS:
        try:
            with Image.open(io.BytesIO(data)) as checked:
                if (checked.format not in FORMATS or checked.width * checked.height > MAX_PIXELS
                        or getattr(checked, 'n_frames', 1) != 1):
                    raise ValueError('사진 픽셀/프레임 제한 초과')
                width, height = checked.size
                if normalized and checked.getexif().get(274) in (5, 6, 7, 8):
                    width, height = height, width
                checked.load()
                return width, height, Image.MIME[checked.format]
        except (OSError, Image.DecompressionBombError) as error:
            raise ValueError('사진 해독/픽셀 검증 실패') from error


def _read_cache(root, source_sha):
    # safe_read_bytes rejects symlink components and non-regular/oversized files.
    # No directory creation, repair, cache eviction or codec work occurs here.
    key = hashlib.sha256(('v888-view-1:' + source_sha).encode()).hexdigest()
    cache = root / 'display_cache_v888'
    meta = safe_read_bytes(cache / (key + '.json'), max_bytes=MAX_META_BYTES)
    view = safe_read_bytes(cache / (key + '.view'), max_bytes=library.MAX_IMAGE_BYTES)
    return json.loads(meta.decode('utf-8'), object_pairs_hook=unique_json_object,
                      parse_constant=reject_nonstandard_json), view


def _validated_cache(meta, view, original, source_sha, dimensions):
    if (not isinstance(meta, dict) or meta.get('source_sha256') != source_sha
            or meta.get('view_sha256') != hashlib.sha256(view).hexdigest()
            or not isinstance(meta.get('stats'), dict) or not 0 < len(view) < len(original)):
        raise ValueError('압축 보관함 무결성 오류')
    stats = meta['stats']
    width, height, _ = _shape(view)
    numbers = {'source_bytes': len(original), 'stored_bytes': len(view),
               'width': width, 'height': height}
    if (any(type(stats.get(key)) is not int or stats[key] != value for key, value in numbers.items())
            or dimensions != (width, height)
            or stats.get('original_preserved') is not True or stats.get('resized') is not False):
        raise ValueError('압축 보관함 측정정보 오류')
    return dict(stats, cache_hit=True, compression_deferred=False)


def read_display(image_id):
    """Return ``(bytes, stats)`` with a second original read before any return."""
    if not isinstance(image_id, str) or not library.ID_PATTERN.fullmatch(image_id):
        raise ValueError('이미지 식별번호 오류')
    cached = None
    with library.LOCK:
        mime, original = library.get_image(image_id)
        if not isinstance(original, bytes):
            raise ValueError('원본 사진 형식 오류')
        source_sha = hashlib.sha256(original).hexdigest()
        try:
            cached = _read_cache(library.storage_root(), source_sha)
        except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
            # Invalid/missing cache is optional; the original remains authoritative.
            pass
    width, height, decoded_mime = _shape(original, normalized=True)
    if mime != decoded_mime:
        raise ValueError('원본 사진 종류 불일치')
    selected = original
    stats = {'source_bytes': len(original), 'stored_bytes': len(original),
             'width': width, 'height': height, 'resized': False, 'encoding': 'source',
             'original_preserved': True, 'readability_review_required': True,
             'psnr_db': None, 'cache_hit': False, 'compression_deferred': True}
    if cached is not None:
        try:
            stats = _validated_cache(*cached, original, source_sha, (width, height))
            selected = cached[1]
        except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
            pass
    with library.LOCK:
        current_mime, current = library.get_image(image_id)
        if (current_mime != mime or not isinstance(current, bytes)
                or hashlib.sha256(current).hexdigest() != source_sha):
            raise ValueError('원본 사진이 변경되었습니다')
    return selected, stats
