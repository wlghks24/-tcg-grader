"""Bounded reciprocal metadata repair and a single private card/photo feed.

No scheduler or deployment. The repair entrypoint requires the existing collector's
budget context; display compression never rewrites a stored/grade-analysis photo.
"""
from __future__ import annotations

import base64
import html
import io
import math
import time
from urllib.parse import quote

import tablet_image_library_v1 as library
from execution.tablet_catalog_bridge import REGIONS, KINDS, card_variant_gap, variant_fields

REQUIRED = ('card_code', 'card_number', 'language', 'set_code')
MAX_REPAIRS = 4
RETRY_SECONDS = 6 * 3600


def repair_existing(auto, root, state, records, budget, stop, *, clock=time.time):
    """Fill partial metadata using exact provider IDs under the *shared* quota.

    Unlike the historical repair, a set-only record remains eligible. No image
    download, guessed printing, cross-country substitution, or conflicting overwrite.
    Caller owns collector serialization and persists this same state/budget.
    """
    if (getattr(auto._BUDGET_CONTEXT, 'current', None) is not budget
            or getattr(budget, 'state', None) is not state
            or root != library.storage_root()):
        raise ValueError('기존 수집기 예산 문맥이 필요합니다')
    now = clock()
    if type(now) not in (int, float) or not math.isfinite(now):
        raise ValueError('잘못된 재확인 시각')
    if not isinstance(records, list) or len(records) > library.MAX_RECORDS:
        raise ValueError('이미지 목록 제한 초과')
    history = state.setdefault('metadata_repairs', {})
    if (not isinstance(history, dict) or len(history) > 4000 or any(
            not isinstance(k, str) or not isinstance(v, dict)
            or type(v.get('next_at')) not in (int, float)
            or not math.isfinite(v['next_at']) or not 0 <= v['next_at'] <= now + 86400
            for k, v in history.items())):
        raise ValueError('카드정보 재확인 이력 형식 오류')
    with library.LOCK:
        current = {r['id']: r for r in library._load(root)['items']}
    eligible = []
    seen = set()
    for r in records:
        if not isinstance(r, dict):
            continue
        ident = r.get('id')
        if not isinstance(ident, str) or not library.ID_PATTERN.fullmatch(ident) or ident in seen:
            continue
        seen.add(ident)
        if r != current.get(ident):
            continue
        if (r.get('origin') != 'auto' or r.get('provider') != 'TCGdex'
                or r.get('game_id') != 'pokemon' or r.get('kind') not in ('CARD', 'PROMO')):
            continue
        locale = auto.POKEMON_LOCALES.get(r.get('region'))
        metadata = r.get('card_metadata', {})
        source = r.get('source_id')
        prefix = 'pokemon/' + (locale or '') + '/'
        code = source[len(prefix):] if isinstance(source, str) and source.startswith(prefix) else ''
        if (not locale or not auto._valid_id(code) or not isinstance(metadata, dict)
                or metadata.get('card_code') not in (None, code)
                or metadata.get('language') not in (None, locale)
                or all(metadata.get(k) for k in REQUIRED)):
            continue
        eligible.append((r, code, locale))
    eligible.sort(key=lambda item: (history.get(item[0]['id'], {}).get('next_at', 0), item[0]['id']))
    result = {'attempted': 0, 'enriched': 0, 'pending': len(eligible), 'deferred': False, 'issues': []}
    for r, code, locale in eligible:
        if stop.is_set() or result['attempted'] >= MAX_REPAIRS:
            break
        if history.get(r['id'], {}).get('next_at', 0) > now:
            continue
        # Verify original bytes before linking new metadata to this image.
        try:
            library.get_image(r['id'])
        except (OSError, ValueError):
            result['issues'].append('사진 무결성 확인 필요')
            continue
        history[r['id']] = {'next_at': now + RETRY_SECONDS}
        budget.save()  # persisted BEFORE I/O, including failures
        budget.provider = 'TCGdex'
        result['attempted'] += 1
        try:
            detail = auto.fetch_json('https://api.tcgdex.net/v2/' + locale + '/cards/' + quote(code, safe=''))
            if not isinstance(detail, dict) or detail.get('id') != code:
                raise auto.ProviderError('카드 상세 식별값 불일치')
            card_set = detail.get('set')
            if not isinstance(card_set, dict):
                raise auto.ProviderError('카드 세트정보 미확인')
            fields = auto._metadata(card_code=code, language=locale, card_number=detail.get('localId'),
                                    set_code=card_set.get('id'), set_name=card_set.get('name'),
                                    rarity=detail.get('rarity'), card_type=detail.get('category'))
            old = r.get('card_metadata', {})
            if any(k in old and old[k] != v for k, v in fields.items()):
                raise auto.ProviderError('기존 카드정보와 출처정보 충돌')
            if library.enrich_auto_metadata(r['id'], 'TCGdex', r['source_id'], fields):
                result['enriched'] += 1
                if all(({**old, **fields}).get(k) for k in REQUIRED):
                    result['pending'] -= 1
                    history.pop(r['id'], None)
        except auto.policy.Deferred as exc:
            result['deferred'] = True
            result['issues'].append(str(exc)[:120])
            break
        except (auto.ProviderError, OSError, ValueError, TypeError) as exc:
            result['issues'].append(str(exc)[:120])
    budget.save()
    return result


def unified_feed(report):
    """One entity for a verified catalog/photo pair, with reciprocal field overlays.

    Unmatched objects remain in the same list. No fuzzy/name-only deduplication;
    original public evidence stays unchanged and field provenance stays explicit.
    """
    if not isinstance(report, dict) or report.get('ok') is not True or report.get('source_errors'):
        raise ValueError('출처 검증 보고서 필요')
    summary = report.get('summary', {})
    if not isinstance(summary, dict) or summary.get('source_limit_reached'):
        raise ValueError('출처 검증 보고서 필요')
    def indexed(key, idkey, limit):
        rows = report.get(key)
        if not isinstance(rows, list) or len(rows) > limit:
            raise ValueError('통합 목록 형식 오류')
        out = {}
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError('통합 목록 행 형식 오류')
            ident = row.get(idkey)
            if (not isinstance(ident, str) or not library.ID_PATTERN.fullmatch(ident)
                    or ident in out or row.get('region') not in REGIONS or row.get('kind') not in KINDS
                    or not isinstance(row.get('game_id'), str) or not library.GAME_PATTERN.fullmatch(row['game_id'])):
                raise ValueError('통합 목록 식별정보 오류')
            out[ident] = row
        return out
    images = indexed('local_catalog', 'id', library.MAX_RECORDS)
    sources = indexed('source_catalog', 'source_record_id', 1500)
    matches = report.get('catalog_matches')
    if not isinstance(matches, list) or len(matches) > 3000:
        raise ValueError('연결 목록 형식 오류')
    by_image, by_source = {}, {}
    for match in matches:
        if not isinstance(match, dict) or match.get('match') != 'CODE_MATCH':
            raise ValueError('정확한 이미지 연결 필요')
        i, s = match.get('id'), match.get('source_record_id')
        if i not in images or s not in sources or i in by_image or s in by_source:
            raise ValueError('중복 또는 누락된 이미지 연결')
        image, source = images[i], sources[s]
        if any(image[k] != source[k] or match.get(k) != image[k] for k in ('game_id', 'region', 'kind')):
            raise ValueError('국가·게임·상품종류 연결 충돌')
        codes = image.get('product_codes')
        if (not isinstance(codes, list) or not codes or not all(isinstance(c, str) for c in codes)
                or not isinstance(source.get('product_codes'), list)
                or codes != source['product_codes'] or source.get('source_health') != 'HEALTHY'
                or card_variant_gap(image, source)):
            raise ValueError('카드번호·판본 증거 부족')
        by_image[i], by_source[s] = s, i
    result = []
    for i, image in images.items():
        s = by_image.get(i)
        source = sources.get(s, {})
        left, right = image.get('card_metadata', {}), source.get('card_metadata', {})
        if isinstance(right, dict):
            right = {**{k: v for k, v in variant_fields(source).items() if v}, **right}
        if not isinstance(left, dict) or not isinstance(right, dict):
            raise ValueError('카드정보 형식 오류')
        conflicts = sorted(k for k in left.keys() & right.keys() if left[k] != right[k])
        metadata = dict(left)
        provenance = {k: 'photo_record' for k in left}
        if not conflicts:
            for key, value in right.items():
                if key not in metadata:
                    metadata[key], provenance[key] = value, 'verified_catalog'
        result.append({'entity_id': 'photo:' + i, 'image_id': i, 'source_record_id': s,
                       'game_id': image['game_id'], 'region': image['region'], 'kind': image['kind'],
                       'name': image.get('name') or source.get('name', ''),
                       'image_url': '/api/local-card-images/file/' + i,
                       'card_metadata': metadata, 'metadata_provenance': provenance,
                       'metadata_conflicts': conflicts,
                       'catalog_overlay': metadata if s and not conflicts else None,
                       'link_status': 'METADATA_CONFLICT' if conflicts else 'VERIFIED_PAIR' if s else 'NEEDS_EXACT_IDENTITY'})
    for s, source in sources.items():
        if s not in by_source:
            result.append({'entity_id': 'catalog:' + s, 'source_record_id': s,
                           'image_id': None, 'image_url': None,
                           **{k: source.get(k, '') for k in ('game_id', 'region', 'kind', 'name')},
                           'card_metadata': source.get('card_metadata', {}), 'metadata_provenance': {},
                           'metadata_conflicts': [], 'catalog_overlay': None, 'link_status': 'NEEDS_IMAGE'})
    return result


def display_compression(data):
    """Smallest tested WebP satisfying a conservative full-size pixel-error bound.

    No resizing. PSNR is a guard, not proof of OCR/human legibility. Original is
    always retained separately; small sources and transparent images stay lossless.
    """
    from PIL import Image, ImageChops, ImageOps, ImageStat, features
    if not isinstance(data, bytes) or not 0 < len(data) <= library.MAX_IMAGE_BYTES:
        raise ValueError('사진 크기 제한 초과')
    with Image.open(io.BytesIO(data)) as source:
        if source.width * source.height > 12_000_000 or getattr(source, 'n_frames', 1) != 1:
            raise ValueError('사진 픽셀/프레임 제한 초과')
        source.load()
        normalized = ImageOps.exif_transpose(source).convert('RGBA')
        profile = source.info.get('icc_profile')
    selected = data
    report = {'source_bytes': len(data), 'stored_bytes': len(data), 'width': normalized.width,
              'height': normalized.height, 'resized': False, 'encoding': 'source',
              'original_preserved': True, 'readability_review_required': True, 'psnr_db': None}
    if not features.check('webp'):
        return selected, report
    opaque = normalized.getextrema()[3] == (255, 255)
    for quality in ([60, 70, 80, 90, 95, 100] if opaque and min(normalized.size) >= 400 else [] ) + [None]:
        output = io.BytesIO()
        options = {'method': 6, 'exact': True, 'lossless': quality is None, 'quality': quality or 100}
        if profile:
            options['icc_profile'] = profile
        normalized.save(output, format='WEBP', **options)
        candidate = output.getvalue()
        with Image.open(io.BytesIO(candidate)) as decoded:
            decoded = decoded.convert('RGBA')
            if decoded.size != normalized.size:
                raise ValueError('압축 해상도 검증 실패')
            diff = ImageChops.difference(normalized, decoded)
            mse = sum(ImageStat.Stat(diff).sum2[:3]) / (normalized.width * normalized.height * 3)
            psnr = 99.0 if mse == 0 else 10 * math.log10(255 ** 2 / mse)
            # Bound individual channel error too: tiny text cannot hide in a large flat area.
            max_error = max(upper for _, upper in diff.getextrema())
            valid = (mse == 0 if quality is None else psnr >= 38 and max_error <= 32)
        if valid and len(candidate) < len(selected):
            selected = candidate
            report.update(stored_bytes=len(candidate), encoding='webp-lossless' if quality is None else 'webp',
                          quality=quality, psnr_db=round(psnr, 2))
    return selected, report


def cached_display(image_id):
    """Bounded private view cache, keyed by verified source bytes and codec policy.

    Export callers reuse compression; original library files are never changed.
    A damaged cache is rebuilt, not served. At most 60 entries / 20 MiB persist.
    """
    import hashlib
    import json
    from PIL import Image
    _, original = library.get_image(image_id)
    source_sha = hashlib.sha256(original).hexdigest()
    with library.LOCK:
        root = library.storage_root() / 'display_cache_v888'
        if root.is_symlink():
            raise ValueError('압축 보관함 경로 오류')
        root.mkdir(mode=0o700, exist_ok=True)
        key = hashlib.sha256(('v888-view-1:' + source_sha).encode()).hexdigest()
        image_path, meta_path = root / (key + '.view'), root / (key + '.json')
        try:
            if image_path.is_symlink() or meta_path.is_symlink():
                raise ValueError('압축 보관함 파일 오류')
            if meta_path.stat().st_size > 4096 or image_path.stat().st_size > library.MAX_IMAGE_BYTES:
                raise ValueError('압축 보관함 크기 오류')
            meta = json.loads(meta_path.read_text(encoding='utf-8'))
            view = image_path.read_bytes()
            if (not isinstance(meta, dict) or meta.get('source_sha256') != source_sha
                    or meta.get('view_sha256') != hashlib.sha256(view).hexdigest()
                    or not isinstance(meta.get('stats'), dict)):
                raise ValueError('압축 보관함 무결성 오류')
            with Image.open(io.BytesIO(view)) as checked:
                if checked.width * checked.height > 12_000_000 or getattr(checked, 'n_frames', 1) != 1:
                    raise ValueError('압축 사진 픽셀 제한')
                checked.load()
                stats = meta['stats']
                if (stats.get('source_bytes') != len(original) or stats.get('stored_bytes') != len(view)
                        or stats.get('width') != checked.width or stats.get('height') != checked.height
                        or stats.get('original_preserved') is not True or stats.get('resized') is not False):
                    raise ValueError('압축 보관함 측정정보 오류')
            return view, dict(meta['stats'], cache_hit=True)
        except (OSError, ValueError, TypeError):
            pass
        # Refuse symlink targets even when the read failed; don't replace them.
        if image_path.is_symlink() or meta_path.is_symlink():
            raise ValueError('압축 보관함 파일 오류')
        view, stats = display_compression(original)
        entries = sorted((p for p in root.glob('*.view') if p.is_file() and not p.is_symlink()),
                         key=lambda p: (p.stat().st_mtime_ns, p.name))
        size = sum(p.stat().st_size for p in entries)
        while entries and (len(entries) >= 60 or size + len(view) > 20 * 1024 * 1024):
            old = entries.pop(0)
            size -= old.stat().st_size
            old.unlink()
            old.with_suffix('.json').unlink(missing_ok=True)
        # No duplicate source when optimization cannot reduce bytes.
        if len(view) < len(original):
            meta = {'source_sha256': source_sha, 'view_sha256': hashlib.sha256(view).hexdigest(), 'stats': stats}
            library._atomic_write(image_path, view)
            library._atomic_write(meta_path, json.dumps(meta, ensure_ascii=False).encode('utf-8'))
        return view, dict(stats, cache_hit=False)


def export_html(report, *, max_images=60):
    """Self-contained private preview: country/game filters, metadata and photo together.

    One bounded export, no external image request or script; files are integrity
    checked by the existing library. This is an export, not the tablet's live UI.
    """
    if type(max_images) is not int or not 0 <= max_images <= 60:
        raise ValueError('내보내기 이미지 제한 오류')
    rows = unified_feed(report)
    cards, compressed, total = [], 0, 0
    for row in rows:
        picture = '<p>사진 보완 대기</p>'
        if row['image_id'] and compressed < max_images:
            try:
                view, stats = cached_display(row['image_id'])
                if total + len(view) <= 15_000_000:
                    from PIL import Image
                    with Image.open(io.BytesIO(view)) as checked:
                        mime = Image.MIME[checked.format]
                    picture = '<img loading="lazy" alt="카드 사진" src="data:' + mime + ';base64,' + base64.b64encode(view).decode('ascii') + '">'
                    total += len(view)
                    compressed += 1
                    picture += '<p>' + str(stats['source_bytes']) + ' → ' + str(stats['stored_bytes']) + ' bytes · 확대하여 글자 확인 필요</p>'
            except (OSError, ValueError):
                picture = '<p>사진 무결성 확인 필요</p>'
        elif row['image_id']:
            picture = '<p>내보내기 용량 한도 · 원본 보관함에서 확인</p>'
        metadata = ' · '.join(str(v) for v in row['card_metadata'].values())
        esc = html.escape
        cards.append('<article data-region="' + esc(row['region'], quote=True) + '" data-game="' + esc(row['game_id'], quote=True) + '"><h2>' + esc(row['name']) + '</h2><p>' + esc(row['region'] + ' · ' + row['game_id'] + ' · ' + row['kind']) + '</p>' + picture + '<p>' + esc(metadata) + '</p><p>' + esc(row['link_status']) + '</p></article>')
    games = sorted({r['game_id'] for r in rows})
    return '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><title>통합 카드 보관함</title><style>body{font:18px sans-serif;background:#f4f6fa;margin:16px}header{position:sticky;top:0;background:white;padding:12px}select{font:inherit;padding:12px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:16px}article{background:white;padding:16px;border-radius:16px;overflow-wrap:anywhere}img{width:100%;height:auto}article[hidden]{display:none}</style><header><h1>통합 카드 보관함</h1><p>상품정보·수집사진 함께 보기 · 원본 별도 보존 · 실기 검증 전</p><select id="region"><option value="">전체 국가</option>''' + ''.join('<option>' + r + '</option>' for r in sorted(REGIONS)) + '''</select><select id="game"><option value="">전체 게임</option>''' + ''.join('<option>' + html.escape(g) + '</option>' for g in games) + '''</select></header><main>''' + ''.join(cards) + '''</main><script>const region=document.getElementById('region'),game=document.getElementById('game');function filter(){document.querySelectorAll('article').forEach(row=>{row.hidden=!!((region.value&&row.dataset.region!==region.value)||(game.value&&row.dataset.game!==game.value));});}region.addEventListener('change',filter);game.addEventListener('change',filter);</script></html>'''


if __name__ == '__main__':
    import argparse
    from pathlib import Path
    from execution.tablet_catalog_bridge import build_report
    parser = argparse.ArgumentParser(description='기존 사진과 상품정보를 한 HTML로 내보내기 (수집/학습/설치 없음)')
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    # Exclusive create: never overwrite an original/photo/existing export.
    document = export_html(build_report(args.repo))
    with args.output.open('x', encoding='utf-8') as output:
        output.write(document)
    print('통합 보관함 내보내기 완료:', args.output)
