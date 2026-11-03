"""Read-only, redacted local collection snapshot. No POST, repair or training.

A readable snapshot is not proof of a completed/current-build collection cycle.
Issue-message hints are counts of messages, not the collector's error count.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from http.client import HTTPException
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from safe_runtime import reject_nonstandard_json, unique_json_object
from tcg_game_registry import load_registry

ROOT = Path(__file__).resolve().parents[1]
ROUTES = {'auto': '/api/local-card-images/auto-status',
          'inventory': '/api/local-card-images',
          'projection': '/api/local-card-images/catalog-links'}
MAX_RESPONSE_BYTES = 8_000_000
PROVIDERS = {'TCGdex', 'YGOPRODeck', 'LorcanaAPI', 'SWUDB', 'GCGAPI', 'RiftboundData', 'PunkRecords', 'Scryfall'}
METADATA_FIELDS = ('card_code', 'card_number', 'set_code', 'set_name', 'language', 'printing',
                   'variant', 'rarity', 'card_type', 'condition', 'generation')
WORK_ACTIONS = {'COLLECT_EXACT_IMAGE', 'ENRICH_EXACT_METADATA', 'VERIFY_EXACT_IDENTITY', 'RECONFIRM_RETAINED_FIELDS'}
LINK_STATES = {'VERIFIED_PAIR', 'NEEDS_IMAGE', 'NEEDS_EXACT_IDENTITY', 'METADATA_CONFLICT', 'SOURCE_COVERAGE_INCOMPLETE'}
REASONS = {'HTTP_403', 'HTTP_429', 'HTTP_404', 'HTTP_5XX', 'TIMEOUT', 'METADATA', 'STORAGE', 'BUDGET', 'SCHEMA', 'OTHER'}


class SnapshotError(ValueError):
    def __init__(self, reason):
        self.reason = reason if reason in REASONS else 'OTHER'
        super().__init__(self.reason)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SnapshotError('OTHER')


def _http_reason(code):
    return 'HTTP_' + str(code) if code in (403, 429, 404) else 'HTTP_5XX' if type(code) is int and 500 <= code <= 599 else 'OTHER'


def _reason(exc):
    if isinstance(exc, SnapshotError):
        return exc.reason
    if isinstance(exc, HTTPError):
        return _http_reason(exc.code)
    if isinstance(exc, TimeoutError) or isinstance(getattr(exc, 'reason', None), TimeoutError):
        return 'TIMEOUT'
    return 'SCHEMA' if isinstance(exc, (ValueError, TypeError, KeyError)) else 'OTHER'


def read_snapshot(path):
    """Fixed loopback GET only; proxy/redirect disabled, bounded bytes/deadline."""
    if path not in ROUTES.values():
        raise SnapshotError('SCHEMA')
    opener = build_opener(ProxyHandler({}), NoRedirect())
    request = Request('http://127.0.0.1:8765' + path, headers={'Accept': 'application/json'})
    deadline = time.monotonic() + 6
    try:
        response = opener.open(request, timeout=3)
    except HTTPError as exc:
        reason = _http_reason(exc.code)
        exc.close()
        raise SnapshotError(reason) from None
    with response:
        if response.status != 200:
            raise SnapshotError(_http_reason(response.status))
        if response.headers.get_content_type() != 'application/json':
            raise SnapshotError('SCHEMA')
        chunks, size = [], 0
        while size <= MAX_RESPONSE_BYTES:
            if time.monotonic() >= deadline:
                raise SnapshotError('TIMEOUT')
            chunk = response.read1(min(65_536, MAX_RESPONSE_BYTES + 1 - size))
            if time.monotonic() >= deadline:
                raise SnapshotError('TIMEOUT')
            if not chunk:
                break
            chunks.append(chunk); size += len(chunk)
        if size > MAX_RESPONSE_BYTES:
            raise SnapshotError('SCHEMA')
    payload = json.loads(b''.join(chunks).decode('utf-8'), object_pairs_hook=unique_json_object,
                         parse_constant=reject_nonstandard_json)
    if not isinstance(payload, dict):
        raise SnapshotError('SCHEMA')
    return payload


def _count(value):
    if type(value) is not int or not 0 <= value <= 100_000_000:
        raise SnapshotError('SCHEMA')
    return value


def _counts(data, keys):
    if not isinstance(data, dict):
        raise SnapshotError('SCHEMA')
    return {key: _count(data[key]) for key in keys if key in data}


def _timestamp(value):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 64:
        raise SnapshotError('SCHEMA')
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            raise ValueError('naive timestamp')
        return stamp.isoformat()
    except ValueError as exc:
        raise SnapshotError('SCHEMA') from exc


def issue_hints(messages):
    if not isinstance(messages, list) or len(messages) > 100:
        raise SnapshotError('SCHEMA')
    counts = Counter()
    for message in messages:
        if not isinstance(message, str) or len(message) > 4000:
            counts['SCHEMA'] += 1
            continue
        value = message.casefold()
        found = set()
        for code in (403, 429, 404):
            if re.search(r'(?<!\d)' + str(code) + r'(?!\d)', value):
                found.add('HTTP_' + str(code))
        if re.search(r'(?<!\d)5\d\d(?!\d)', value):
            found.add('HTTP_5XX')
        for label, terms in {'TIMEOUT': ('timeout', 'timed out', '시간 초과', '시간초과', '네트워크 지연'),
                'METADATA': ('metadata', '메타데이터', '카드정보', '카드 정보', '카드 상세'),
                'STORAGE': ('storage', 'permission', 'no space', '저장소', '권한', '파일', '무결성'),
                'BUDGET': ('budget', 'quota', '예산', '한도', '대기기간'),
                'SCHEMA': ('schema', '형식', '식별값', '스키마')}.items():
            if any(term in value for term in terms):
                found.add(label)
        counts.update(found or {'OTHER'})
    return {'message_count': len(messages), 'hint_counts': dict(sorted(counts.items())),
            'counts_are_error_count': False, 'multiple_hints_per_message_possible': True}


def _auto(data, known_pairs):
    job = data.get('job', {})
    if not isinstance(job, dict):
        raise SnapshotError('SCHEMA')
    last = data.get('last_result')
    result = {'job': _counts(job, ('scanned', 'saved', 'skipped', 'errors')),
              'job_started_at': _timestamp(job.get('started_at')), 'job_finished_at': _timestamp(job.get('finished_at')),
              'run_generation_recorded': False, 'current_build_cycle_verified': False}
    if 'running' in job:
        if type(job['running']) is not bool:
            raise SnapshotError('SCHEMA')
        result['job']['running'] = job['running']
    if last is None:
        return dict(result, last_result_status='NOT_RUN_OR_NOT_RECORDED')
    result['last_result_status'] = 'READABLE_UNVERSIONED_RECEIPT'
    result['last_result'] = _counts(last, ('scanned', 'saved', 'skipped', 'errors', 'metadata_enriched',
                                              'metadata_repair_attempted', 'metadata_repair_pending', 'stored_bytes', 'compression_bytes_saved'))
    result['run_at'] = _timestamp(last.get('run_at'))
    for key in ('deferred', 'stopped'):
        if key in last:
            if type(last[key]) is not bool:
                raise SnapshotError('SCHEMA')
            result['last_result'][key] = last[key]
    result['issue_hints'] = issue_hints(last.get('issues', []))
    result['metadata_counter_semantics'] = 'metadata_enriched counts updates to existing photos; zero does not establish missing metadata on new photos'
    for key in ('unified_metadata_repair', 'target_image_repair'):
        if key in last:
            repair = last[key]
            safe = _counts(repair, ('attempted', 'enriched', 'pending', 'saved', 'stored_bytes', 'compression_bytes_saved'))
            if 'deferred' in repair:
                if type(repair['deferred']) is not bool:
                    raise SnapshotError('SCHEMA')
                safe['deferred'] = repair['deferred']
            safe['issue_hints'] = issue_hints(repair.get('issues', []))
            result[key] = safe
    if 'canonical_store' in last:
        store = last['canonical_store']
        if not isinstance(store, dict) or type(store.get('ok')) is not bool:
            raise SnapshotError('SCHEMA')
        result['canonical_store'] = dict(_counts(store, ('records', 'current', 'pending_work')), ok=store['ok'])
    sources = last.get('per_source', {})
    if not isinstance(sources, dict) or len(sources) > 256:
        raise SnapshotError('SCHEMA')
    safe_sources, other = [], 0
    for key, value in sources.items():
        parts = re.split(r'[|/]', key) if isinstance(key, str) else []
        if len(parts) != 2 or tuple(parts) not in known_pairs or not isinstance(value, dict) or value.get('source') not in PROVIDERS:
            other += 1
            continue
        safe_sources.append(dict(_counts(value, ('saved', 'skipped', 'errors')),
                                 game_id=parts[0], region=parts[1], provider=value['source']))
    result['per_source'] = sorted(safe_sources, key=lambda row: (row['game_id'], row['region']))
    result['other_source_count'] = other
    return result


def _inventory(data):
    items = data.get('items')
    if not isinstance(items, list) or len(items) > 2500:
        raise SnapshotError('SCHEMA')
    present, nonempty, invalid = Counter(), 0, 0
    for row in items:
        if not isinstance(row, dict):
            raise SnapshotError('SCHEMA')
        metadata = row.get('card_metadata', {})
        if not isinstance(metadata, dict):
            invalid += 1
            continue
        fields = {key for key in METADATA_FIELDS if isinstance(metadata.get(key), str) and metadata[key].strip()}
        nonempty += bool(fields)
        present.update(fields)
    return {'inventory_rows': len(items), 'rows_with_known_metadata_fields': nonempty,
            'rows_with_invalid_metadata_schema': invalid,
            'metadata_field_presence': {key: present[key] for key in METADATA_FIELDS},
            'reported_count': _count(data['count']) if 'count' in data else None,
            'identity_and_image_pixels_verified': False}


def _projection(data):
    rows = data.get('unified_catalog')
    if not isinstance(rows, list) or len(rows) > 4000:
        raise SnapshotError('SCHEMA')
    actions, links, tasks = Counter(), Counter(), 0
    for row in rows:
        if not isinstance(row, dict):
            raise SnapshotError('SCHEMA')
        state = row.get('link_status')
        links[state if isinstance(state, str) and state in LINK_STATES else 'OTHER'] += 1
        work = row.get('work_items', [])
        if not isinstance(work, list) or len(work) > 20:
            raise SnapshotError('SCHEMA')
        for item in work:
            action = item.get('action') if isinstance(item, dict) else None
            actions[action if isinstance(action, str) and action in WORK_ACTIONS else 'OTHER'] += 1
            tasks += 1
    return {'projection_rows': len(rows), 'work_item_count': tasks,
            'work_action_counts': dict(sorted(actions.items())), 'link_status_counts': dict(sorted(links.items())),
            'projection_is_completed_collection_proof': False}


def _events(repo, now):
    from execution import tablet_event_coverage_v896 as coverage
    path = Path(repo) / coverage.STATE
    if path.is_symlink():
        return {'status': 'HOLD_EVENT_STORE_SCHEMA', 'discovery_only': True}
    if not path.exists():
        return {'status': 'NOT_RUN_OR_NOT_RECORDED', 'discovery_only': True}
    try:
        configured = coverage.cells(load_registry(Path(repo)))
        snapshot = coverage.report(configured, coverage._load(repo), now=now)
        states = Counter(row['status'] for row in snapshot['cells'])
        return {'status': 'READABLE_DISCOVERY_SNAPSHOT', 'discovery_only': True,
                'configured_games': snapshot['game_count'], 'configured_cells': snapshot['configured_cells'],
                'attempted_cells': snapshot['configured_cells'] - states['NOT_SEARCHED'],
                'fresh_success_cells': states['SEARCHED_UNCONFIRMED'], 'partial_cells': states['PARTIAL_SEARCH'],
                'failed_cells': states['SEARCH_FAILED'], 'not_searched_cells': states['NOT_SEARCHED'],
                'stale_cells': states['STALE_SEARCH'], 'candidate_count': len(snapshot['items']),
                'confirmed_events_or_rewards': 'NOT_VERIFIED', 'snapshot_is_collection_success_proof': False}
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        return {'status': 'HOLD_EVENT_STORE_SCHEMA', 'discovery_only': True}


def collection_report(repo=ROOT, *, reader=read_snapshot, now=None):
    now = datetime.now(timezone.utc) if now is None else now
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise SnapshotError('SCHEMA')
    try:
        registry = load_registry(Path(repo))
        known_pairs = {(game['id'], region) for game in registry['games'] for region in game['regions']}
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        known_pairs = set()
    report = {'schema_version': 899, 'snapshot_readable': {}, 'routes': {},
              'collector_verified': False, 'run_generation_recorded': False,
              'current_build_cycle_verified': False, 'touch_camera_verification': 'NOT_RUN',
              'model_training_verification': 'NOT_RUN'}
    for name, path in ROUTES.items():
        try:
            payload = reader(path)
            if not isinstance(payload, dict) or payload.get('ok') is not True:
                raise SnapshotError('SCHEMA')
            summary = _auto(payload, known_pairs) if name == 'auto' else _inventory(payload) if name == 'inventory' else _projection(payload)
            report['routes'][name] = {'status': 'READABLE_SNAPSHOT', 'summary': summary}
            report['snapshot_readable'][name] = True
        except (OSError, ValueError, TypeError, KeyError, AttributeError, HTTPException, RecursionError) as exc:
            report['routes'][name] = {'status': 'UNAVAILABLE', 'reason': _reason(exc)}
            report['snapshot_readable'][name] = False
    report['events'] = _events(repo, now)
    report['status'] = 'SNAPSHOTS_READABLE_NOT_CYCLE_PROOF' if all(report['snapshot_readable'].values()) else 'PARTIAL_SNAPSHOT_READBACK'
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        result = collection_report(args.repo)
    except (OSError, ValueError, TypeError, HTTPException, RecursionError):
        result = {'schema_version': 899, 'status': 'HOLD_REPORT_UNAVAILABLE', 'collector_verified': False}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'SNAPSHOTS_READABLE_NOT_CYCLE_PROOF' else 1


if __name__ == '__main__':
    raise SystemExit(main())
