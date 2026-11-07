"""Read-only event/promo UI projection. No collection, promotion or source writes."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone, date
import hashlib
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from execution.tablet_catalog_bridge import read_json

MAX_BYTES = 8_000_000
MAX_ROWS = 3000
MAX_DISPLAY = 500
FRESH_SECONDS = 7 * 86400
KST = timezone(timedelta(hours=9))
REGIONS = {'KR', 'JP', 'US', 'CN', 'CN-S', 'CN-T', 'TW', 'HK', 'ASIA', 'GLOBAL'}


def _text(value, limit=250):
    return value.strip() if isinstance(value, str) and 0 < len(value.strip()) <= limit and not any(ord(c) < 32 for c in value) else ''


def _date(value):
    # fromisoformat also accepts ISO week dates (2026-W45-3). Saved events
    # require an explicit calendar day, never an inferred event announcement.
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _time(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00')) if isinstance(value, str) and len(value) <= 64 else None
        return parsed if parsed is not None and parsed.tzinfo is not None else None
    except ValueError:
        return None


def _source(value):
    """Use the same exact host/post approval as the existing collector, no fetch."""
    from update_promo_events import approved_url
    try:
        return approved_url(_text(value, 2048))
    except (ValueError, TypeError):
        return ''


def _lineage(source):
    parsed = urlsplit(source)
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
             if not k.lower().startswith('utm_') and k.lower() not in {'fbclid', 'gclid'}]
    normalized = urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path, urlencode(sorted(query)), ''))
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:24]


def project_events(payload, *, now=None):
    """Separate real dates from internal tracking horizons and stale verification.

    Link availability is evidence of a reachable source, never confirmation of an
    announced event/date. Retain archives; missing dates stay UNKNOWN_DATE.
    """
    now = datetime.now(timezone.utc) if now is None else now
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError('timezone-aware event clock required')
    if not isinstance(payload, dict):
        raise ValueError('event payload must be an object')
    active, archive = payload.get('items'), payload.get('archive_items', [])
    if (not isinstance(active, list) or not isinstance(archive, list)
            or len(active) + len(archive) > MAX_ROWS):
        raise ValueError('event row bounds/schema')
    today = now.astimezone(KST).date()
    rows, rejected, seen = [], 0, {}
    for raw, archived in [(r, False) for r in active] + [(r, True) for r in archive]:
        if not isinstance(raw, dict):
            rejected += 1
            continue
        name, game = _text(raw.get('name_ko') or raw.get('name')), _text(raw.get('game'), 130)
        region = raw.get('region')
        if not name or not game or not isinstance(region, str) or region not in REGIONS:
            rejected += 1
            continue
        source = _source(raw.get('source'))
        original = _source(raw.get('original_source')) or source
        lineage = _lineage(original) if original else ''
        checked = _time(raw.get('link_checked_at'))
        age = (now - checked).total_seconds() if checked else None
        if not source:
            evidence = 'INVALID_SOURCE'
        elif raw.get('source_grade') != 'official' or raw.get('link_status') != '정상':
            evidence = 'UNVERIFIED'
        elif age is None or age < -300:
            evidence = 'UNKNOWN_FRESHNESS'
        else:
            evidence = 'FRESH_OFFICIAL' if age <= FRESH_SECONDS else 'STALE_OFFICIAL'
        precision = raw.get('date_precision')
        # External saved JSON may contain a list/object here. Reject only
        # that untrusted event rather than crashing and hiding every valid
        # neighboring event through the read-only display fallback.
        if precision is not None and not isinstance(precision, str):
            rejected += 1
            continue
        tracking = raw.get('tracking_only') is True or precision in {'unannounced', 'start-only'}
        start, end, claim = (_date(raw.get(k)) for k in ('start_date', 'end_date', 'claim_deadline'))
        invalid_range = bool(start and end and end < start)
        if tracking:
            # start-only retains only its explicit start; end/claim are review horizons.
            start = start if precision == 'start-only' else None
            end = claim = None
            lifecycle = 'TRACKING'
        elif invalid_range or not start or not end:
            start = end = claim = None
            lifecycle = 'UNKNOWN_DATE'
        else:
            expiry = max(end, claim) if claim else end
            # Adding five days overflows at 9999-12-27..31 and previously
            # made one malformed/far-future event blank the entire read-only
            # event view. Subtract only after expiry has passed.
            expired_days = (today - expiry).days if today > expiry else 0
            lifecycle = ('ARCHIVED' if archived or expired_days > 5
                         else 'RECENTLY_ENDED' if today > expiry
                         else 'UPCOMING' if today < start else 'RECENTLY_ENDED' if today > end else 'CURRENT')
        if archived:
            lifecycle = 'ARCHIVED'
        category = _text(raw.get('category'), 40) or 'event'
        row = {'name': name, 'game': game, 'region': region, 'category': category,
               'source': source or None, 'source_checked_at': checked.isoformat() if checked else None,
               'evidence_state': evidence, 'lifecycle': lifecycle,
               'start_date': start.isoformat() if start else None,
               'end_date': end.isoformat() if end else None,
               'claim_deadline': claim.isoformat() if claim else None,
               'date_label': (_text(raw.get('date_label')) or '공식 일정 확인 중') if tracking else
                             '날짜 확인 필요' if lifecycle == 'UNKNOWN_DATE' else '',
               'lineage_id': lineage or None, 'tracking_only': tracking,
               'reward': _text(raw.get('reward'), 700), 'condition': _text(raw.get('condition'), 1000),
               'archived': archived or lifecycle == 'ARCHIVED'}
        # Mirrors/repeated snapshots of the same announcement are one row/lineage.
        key = (game, region, category, name.casefold(), lineage)
        if key in seen:
            index = seen[key]
            prior = _time(rows[index].get('source_checked_at'))
            if checked and (not prior or checked > prior):
                rows[index] = row
            continue
        seen[key] = len(rows)
        rows.append(row)
    counts = Counter(r['lifecycle'] for r in rows)
    evidence_counts = Counter(r['evidence_state'] for r in rows)
    rows.sort(key=lambda r: (r['archived'], r['start_date'] or '9999-99-99', r['region'], r['name']))
    return {'ok': True, 'status': 'READ_ONLY_EVENT_SUMMARY', 'rows': rows[:MAX_DISPLAY],
            'summary': {'loaded_rows': len(rows), 'rejected_rows': rejected,
                        'rows_truncated': len(rows) > MAX_DISPLAY,
                        'unique_lineages': len({r['lineage_id'] for r in rows if r['lineage_id']}),
                        'lifecycle_counts': dict(counts), 'evidence_counts': dict(evidence_counts)},
            'source_updated_at': _text(payload.get('updated_at'), 64) or None,
            'model_training_performed': False, 'physical_tablet_verified': False}


def read_event_summary(repo, *, now=None):
    """An unreadable dataset is not zero events; retain an explicit error state."""
    try:
        return project_events(read_json(Path(repo) / 'promo_events.json', MAX_BYTES), now=now)
    except (OSError, ValueError, TypeError, UnicodeError, ImportError):
        return {'ok': False, 'status': 'EVENT_DATA_UNAVAILABLE', 'rows': [], 'summary': None,
                'model_training_performed': False, 'physical_tablet_verified': False}
