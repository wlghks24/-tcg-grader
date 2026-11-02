"""Two-way image/catalog repair plan; no image, grade, or market-evidence mutations.

Turns the existing exact-identity audit into bounded actionable follow-ups.
Only the collector's already allowlisted provider/edition pairs gain priority.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import re

MAX_ACTIONS = 3000
MAX_PLAN_BYTES = 2_000_000
_IMAGE_ID = re.compile(r'^[0-9a-f]{32}$')
_SOURCE_ID = re.compile(r'^[0-9a-f]{32}$')
REGIONS = frozenset({'KR', 'JP', 'US', 'CN-S', 'CN-T'})
KINDS = frozenset({'CARD', 'PROMO', 'BOX', 'PACK', 'DECK', 'COLLECTION',
                   'BUNDLE', 'ACCESSORY', 'OTHER'})
VALID_REASONS = frozenset({'NO_EXACT_IDENTIFIER_MATCH', 'CARD_METADATA_INCOMPLETE',
    'AMBIGUOUS_CODE', 'SOURCE_RECHECK_REQUIRED', 'DATASET_INCOMPLETE',
    'CARD_VARIANT_EVIDENCE_INCOMPLETE', 'CARD_VARIANT_CONFLICT',
    'CARD_SET_EVIDENCE_INCOMPLETE', 'CARD_SET_CONFLICT', 'NO_UNIQUE_LOCAL_IMAGE'})


def _code_set(value):
    if not isinstance(value, list) or len(value) > 12 or any(
        not isinstance(code, str) or not re.fullmatch(r'[A-Z0-9]{2,90}', code)
        for code in value):
        return None
    return frozenset(value)


def plan(report, supported):
    """Fail closed: no download, file modification or implicit matching."""
    empty = {'ok': False, 'status': 'HOLD', 'version': 887, 'actions': [],
             'collection_priorities': [], 'summary': {},
             'automatic_image_replacement': False, 'physical_tablet_verified': False}
    if (not isinstance(report, dict) or report.get('ok') is not True or
        not isinstance(report.get('summary'), dict) or report.get('source_errors') or
        report['summary'].get('source_limit_reached') or report['summary'].get('queue_truncated') or
        not isinstance(report.get('gap_queue'), list) or len(report['gap_queue']) > MAX_ACTIONS or
        not isinstance(report.get('local_catalog'), list) or
        not isinstance(report.get('source_catalog'), list) or not isinstance(supported, dict)):
        return dict(empty, reason='SOURCE_OR_QUEUE_INCOMPLETE')
    images, sources = {}, {}
    try:
        for row in report['local_catalog']:
            if not isinstance(row, dict) or not _IMAGE_ID.fullmatch(row.get('id', '')):
                raise ValueError('IMAGE_ID')
            if row['id'] in images:
                raise ValueError('DUPLICATE_IMAGE_ID')
            images[row['id']] = row
        for row in report['source_catalog']:
            if not isinstance(row, dict) or not _SOURCE_ID.fullmatch(row.get('source_record_id', '')):
                raise ValueError('SOURCE_ID')
            if row['source_record_id'] in sources:
                raise ValueError('DUPLICATE_SOURCE_ID')
            sources[row['source_record_id']] = row
        index = defaultdict(set)
        for sid, row in sources.items():
            codes = _code_set(row.get('product_codes'))
            if (row.get('region') not in REGIONS or not isinstance(row.get('game_id'), str)
                or row.get('kind') not in KINDS or codes is None):
                raise ValueError('SOURCE_IDENTITY')
            for code in codes:
                index[(row['game_id'], row['region'], row['kind'], code)].add(sid)
        local_code_index = defaultdict(set)
        for image_id, row in images.items():
            codes = _code_set(row.get('product_codes'))
            if (codes is None or row.get('region') not in REGIONS or
                not isinstance(row.get('game_id'), str) or row.get('kind') not in KINDS):
                raise ValueError('IMAGE_IDENTITY')
            for code in codes:
                local_code_index[(row['game_id'], row['region'], row['kind'], code)].add(image_id)
        actions, priorities, ids = [], Counter(), set()
        for task in report['gap_queue']:
            if not isinstance(task, dict):
                raise ValueError('GAP_SCHEMA')
            direction = task.get('direction')
            game, region, kind = task.get('game_id'), task.get('region'), task.get('kind')
            reason = task.get('reason')
            if (not isinstance(game, str) or not re.fullmatch(r'[a-z0-9-]{2,64}', game)
                or region not in REGIONS or kind not in KINDS or reason not in VALID_REASONS):
                raise ValueError('GAP_IDENTITY')
            if direction == 'IMAGE_NEEDS_METADATA':
                image_id = task.get('image_id')
                if (not isinstance(image_id, str) or not _IMAGE_ID.fullmatch(image_id)
                    or image_id not in images):
                    raise ValueError('IMAGE_GAP_NOT_IN_REPORT')
                row = images[image_id]
                if (row.get('game_id'), row.get('region'), row.get('kind')) != (game, region, kind):
                    raise ValueError('IMAGE_GAP_IDENTITY')
                key = (direction, image_id)
                if key in ids:
                    raise ValueError('DUPLICATE_GAP')
                ids.add(key)
                codes = _code_set(row.get('product_codes'))
                if codes is None:
                    raise ValueError('IMAGE_CODES')
                related = set().union(*(index[(game, region, kind, c)] for c in codes)) if codes else set()
                # Source IDs are hints only. They are never auto-promoted to links.
                source_id = next(iter(related)) if len(related) == 1 else None
                origin, source_key = row.get('provider'), row.get('source_id')
                metadata = row.get('card_metadata', {})
                eligible_tcgdex = (origin == 'TCGdex' and game == 'pokemon'
                    and kind in ('CARD', 'PROMO') and isinstance(source_key, str)
                    and isinstance(metadata, dict) and region in {'JP', 'US', 'CN-T'}
                    and source_key.startswith('pokemon/' +
                        {'JP':'ja', 'US':'en', 'CN-T':'zh-tw'}[region] + '/')
                    and bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._%-]{0,89}',
                                           source_key.rsplit('/', 1)[-1]))
                    and not metadata.get('set_code') and not metadata.get('set_name'))
                if reason in ('AMBIGUOUS_CODE', 'CARD_VARIANT_CONFLICT', 'CARD_SET_CONFLICT') or len(related) > 1:
                    action = 'REVIEW_CONFLICTING_IDENTITY'
                elif reason in ('DATASET_INCOMPLETE', 'SOURCE_RECHECK_REQUIRED'):
                    action = 'REVERIFY_CATALOG_SOURCE'
                elif eligible_tcgdex:
                    action = 'RECHECK_ORIGIN_METADATA'
                else:
                    action = 'MANUAL_IDENTITY_REVIEW'
                actions.append({'direction': direction, 'image_id': image_id, 'game_id': game,
                    'region': region, 'kind': kind, 'reason': reason, 'next_action': action,
                    'source_record_id_hint': source_id, 'auto_link': False, 'auto_download': False,
                    'source_code_hint_only': True})
            elif direction == 'CATALOG_NEEDS_IMAGE':
                source_id = task.get('source_record_id')
                if (not isinstance(source_id, str) or not _SOURCE_ID.fullmatch(source_id)
                    or source_id not in sources):
                    raise ValueError('SOURCE_GAP_NOT_IN_REPORT')
                source = sources[source_id]
                if (source.get('game_id'), source.get('region'), source.get('kind')) != (game, region, kind):
                    raise ValueError('SOURCE_GAP_IDENTITY')
                key = (direction, source_id)
                if key in ids:
                    raise ValueError('DUPLICATE_GAP')
                ids.add(key)
                codes = _code_set(source.get('product_codes'))
                if codes is None:
                    raise ValueError('SOURCE_CODES')
                provider = supported.get((game, region))
                if not isinstance(provider, str) or not provider or len(provider) > 40:
                    action = 'FIND_SUPPORTED_OFFICIAL_SOURCE'
                elif source.get('source_health') != 'HEALTHY':
                    action = 'REVERIFY_CATALOG_SOURCE'
                elif not codes:
                    action = 'REVIEW_MISSING_EXACT_CODE'
                elif any(local_code_index[(game, region, kind, code)] for code in codes):
                    # Existing evidence is in conflict; new images worsen ambiguity.
                    action = 'REVIEW_EXISTING_IMAGE_MATCH'
                else:
                    action = 'REQUERY_CONFIGURED_PROVIDER'
                    priorities[(game, region)] += 1
                actions.append({'direction': direction, 'source_record_id': source_id,
                    'game_id': game, 'region': region, 'kind': kind, 'reason': reason,
                    'next_action': action, 'provider': provider if isinstance(provider, str) else '',
                    'auto_link': False, 'auto_download': False})
            else:
                raise ValueError('GAP_DIRECTION')
        counts = Counter(x['next_action'] for x in actions)
        return {'ok': True, 'status': 'REPAIR_QUEUE_PREPARED', 'version': 887,
            'actions': actions, 'collection_priorities': [
                {'game_id': k[0], 'region': k[1], 'missing_images': n}
                for k, n in sorted(priorities.items())],
            'summary': {'total_actions': len(actions), 'image_to_catalog': sum(
                a['direction'] == 'IMAGE_NEEDS_METADATA' for a in actions),
                'catalog_to_image': sum(a['direction'] == 'CATALOG_NEEDS_IMAGE' for a in actions),
                'by_next_action': dict(sorted(counts.items()))},
            'automatic_image_replacement': False, 'physical_tablet_verified': False,
            'price_inferred': False, 'grade_inferred': False}
    except (ValueError, KeyError, TypeError, AttributeError):
        return dict(empty, reason='INVALID_OR_CONFLICTING_REPAIR_EVIDENCE')


def write_private_plan(report, supported, root, library, *, clock=None):
    """Only atomic private action sidecar; never modifies original images/index."""
    result = plan(report, supported)
    if not result['ok']:
        return {'ok': False, 'status': 'HOLD_PREVIOUS_REPAIR_PLAN_PRESERVED',
                'reason': result.get('reason', 'INVALID_REPORT')}
    if clock is None:
        clock = lambda: datetime.now(timezone.utc)
    destination = root / 'collection_repair_plan_v887.json'
    if destination.is_symlink():
        raise ValueError('unsafe_repair_plan_symlink')
    stamped = {**result, 'generated_at': clock().isoformat(),
               'source_and_image_files_unchanged': True}
    encoded = (json.dumps(stamped, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')
    if len(encoded) > MAX_PLAN_BYTES:
        raise ValueError('repair_plan_bytes_limit')
    with library.LOCK:
        library._atomic_write(destination, encoded)
    return {'ok': True, 'status': result['status'], 'summary': result['summary'],
            'collection_priorities': result['collection_priorities']}
