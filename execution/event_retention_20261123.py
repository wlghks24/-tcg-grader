"""Pure two-week retention for event news; never touches photos or learning stores."""
from copy import deepcopy
import hashlib
import json
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from datetime import date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
DAYS = 14
MAX_UNDATED_KEYS = 3000
LEDGER = 'retention_undated_first_seen'
CATEGORIES = frozenset({'promo', 'collab', 'collaboration', 'movie', 'event', 'festival',
                        'tournament', 'popup', 'release', 'reprint', 'merch', 'anniversary',
                        'video', 'streaming'})
FACT_FIELDS = ('announcement_date', 'source_published_at', 'discovered_at', 'first_seen_at')
POLICY = ('14-day event-news retention: confirmed expiry=max(end_date,claim_deadline); '
          'start-only=start_date; undated=latest nonfuture factual announcement/discovery date '
          'or stable retention_first_seen_on; link checks and dataset updates never extend retention')


def _day(value):
    """Require an ISO day or an explicitly zoned instant; convert instants to KST."""
    if not isinstance(value, str) or not 0 < len(value) <= 64:
        return None
    try:
        if len(value) == 10:
            parsed = date.fromisoformat(value)
            return parsed if parsed.isoformat() == value else None
        instant = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return instant.astimezone(KST).date() if instant.tzinfo is not None else None
    except (ValueError, OverflowError):
        return None


def _today(value):
    if value is None:
        return datetime.now(KST).date()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError('timezone-aware retention clock required')
        return value.astimezone(KST).date()
    if isinstance(value, date):
        return value
    raise ValueError('retention clock must be a KST date or aware datetime')


def _anchor(row, today, first_discovery=None):
    precision = row.get('date_precision', 'day')
    start = _day(row.get('start_date'))
    if precision == 'start-only' and start is not None:
        return start
    dated = precision in ('month', 'season') or (
        precision == 'day' and (row.get('tracking_only') is not True or row.get('date_precision') == 'day'))
    if dated:
        end, claim = _day(row.get('end_date')), _day(row.get('claim_deadline'))
        # Conflicting ranges cannot provide a trustworthy expiry. A future
        # confirmed opening stays available even if its other fields are corrupt.
        if start is not None and start > today:
            return start
        if end is not None and (start is None or end >= start):
            return max(end, claim) if claim is not None else end
        if end is None and claim is not None and (start is None or claim >= start):
            return claim
    facts = []
    for field in FACT_FIELDS:
        value = _day(row.get(field))
        if value is not None and value <= today:
            if first_discovery is not None and field in ('discovered_at', 'first_seen_at'):
                value = min(value, first_discovery)
            facts.append(value)
    first = _day(row.get('retention_first_seen_on'))
    if first is not None and first > today:
        first = None
    if facts:
        return max(facts)
    if first is None:
        first = today
        row['retention_first_seen_on'] = first.isoformat()
    return first


def _identity(row):
    values = [row.get(key) for key in ('game', 'region', 'category', 'source')]
    values.append(row.get('name_ko') or row.get('name'))
    values = [value if isinstance(value, str) and len(value) <= 2048 else '' for value in values]
    try:
        source = urlsplit(values[3])
        query = [(key, value) for key, value in parse_qsl(source.query, keep_blank_values=True)
                 if not key.casefold().startswith('utm_') and key.casefold() not in ('fbclid', 'gclid')]
        values[3] = urlunsplit((source.scheme.lower(), source.netloc.lower(), source.path,
                               urlencode(sorted(query)), ''))
    except ValueError:
        pass
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def _ledger(payload, today):
    entries = payload.get(LEDGER, {})
    if not isinstance(entries, dict) or len(entries) > MAX_UNDATED_KEYS:
        raise ValueError('undated retention ledger bounds/schema')
    result = {}
    for identity, stamp in entries.items():
        day = _day(stamp)
        if (not isinstance(identity, str) or not re.fullmatch('[0-9a-f]{64}', identity)
                or day is None or day > today or not isinstance(stamp, str) or len(stamp) != 10):
            raise ValueError('invalid undated retention ledger')
        result[identity] = day.isoformat()
    return result


def _prepare(row, today, previous):
    local = _day(row.get('retention_first_seen_on'))
    # Never persist an invalid/future first-seen marker. A valid
    # factual date or confirmed schedule may bypass _anchor's fallback.
    if local is None or local > today:
        row.pop('retention_first_seen_on', None)
        local = None
    if previous is not None and (local is None or previous < local):
        row['retention_first_seen_on'] = previous.isoformat()
    anchor = _anchor(row, today, previous)
    first = _day(row.get('retention_first_seen_on'))
    if first is None and (row.get('date_precision') == 'unannounced' or
            (row.get('tracking_only') is True and row.get('date_precision') not in ('day', 'month', 'season', 'start-only'))):
        first = anchor
        row['retention_first_seen_on'] = first.isoformat()
    return anchor, first


def apply_retention(payload, *, today=None):
    """Return a deep copy with expired event rows removed from both lists.

    The fallback first-seen marker is retention metadata, not an event schedule.
    It must be persisted by the caller alongside the returned lists. Reapply this
    function after restoring last-good data or adding static seeds, before writes.
    """
    clock = _today(today)
    if not isinstance(payload, dict) or not isinstance(payload.get('items'), list):
        raise ValueError('event retention payload requires items list')
    if not isinstance(payload.get('archive_items', []), list):
        raise ValueError('event retention archive must be a list')
    result = deepcopy(payload)
    ledger = _ledger(result, clock)
    # Resolve all duplicate first-seen evidence before any expiry decision.
    baseline = dict(ledger)
    for field in ('items', 'archive_items'):
        for row in result.get(field, []):
            category = row.get('category', 'promo') if isinstance(row, dict) else None
            if not isinstance(category, str) or category not in CATEGORIES:
                continue
            identity = _identity(row)
            local = _day(row.get('retention_first_seen_on'))
            previous = _day(baseline.get(identity))
            if local is not None and local <= clock:
                previous = min(local, previous) if previous else local
            _, first = _prepare(dict(row), clock, previous)
            if first is not None:
                existing = _day(ledger.get(identity))
                if existing is None and len(ledger) >= MAX_UNDATED_KEYS:
                    raise ValueError('undated retention ledger capacity reached')
                ledger[identity] = min(first, existing).isoformat() if existing else first.isoformat()
    removed = 0
    for field in ('items', 'archive_items'):
        kept = []
        for row in result.get(field, []):
            category = row.get('category', 'promo') if isinstance(row, dict) else None
            if isinstance(category, str) and category in CATEGORIES:
                identity = _identity(row)
                previous = _day(ledger.get(identity))
                anchor, first = _prepare(row, clock, previous)
                if first is not None:
                    if identity not in ledger and len(ledger) >= MAX_UNDATED_KEYS:
                        raise ValueError('undated retention ledger capacity reached')
                    ledger[identity] = min(first, previous).isoformat() if previous else first.isoformat()
                if (clock - anchor).days >= DAYS:
                    removed += 1
                    continue
            kept.append(row)
        if field in result:
            result[field] = kept
    result[LEDGER] = ledger
    archive = result.get('archive_items', [])
    result['archive_event_count'] = len(archive)
    result['expired_event_count'] = len(archive)
    if 'expired_event_names' in result:
        result['expired_event_names'] = [row.get('name_ko', '이름 없음') for row in archive if isinstance(row, dict)][:50]
    result.update(retention_policy=POLICY, retention_days=DAYS,
                  retention_checked_on=clock.isoformat(), retention_removed_count=removed,
                  retention_remaining_count=len(result['items']) + len(archive))
    return result
