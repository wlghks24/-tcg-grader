"""Pure two-week retention for event news; never touches photos or learning stores."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
DAYS = 14
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


def _anchor(row, today):
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
    facts = [_day(row.get(field)) for field in FACT_FIELDS]
    facts = [value for value in facts if value is not None and value <= today]
    first = _day(row.get('retention_first_seen_on'))
    if first is not None and first > today:
        first = None
    if facts:
        return max(facts)
    if first is None:
        first = today
        row['retention_first_seen_on'] = first.isoformat()
    return first


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
    removed = 0
    for field in ('items', 'archive_items'):
        kept = []
        for row in result.get(field, []):
            category = row.get('category', 'promo') if isinstance(row, dict) else None
            if isinstance(category, str) and category in CATEGORIES:
                anchor = _anchor(row, clock)
                if (clock - anchor).days >= DAYS:
                    removed += 1
                    continue
            kept.append(row)
        if field in result:
            result[field] = kept
    archive = result.get('archive_items', [])
    result['archive_event_count'] = len(archive)
    result['expired_event_count'] = len(archive)
    if 'expired_event_names' in result:
        result['expired_event_names'] = [row.get('name_ko', '이름 없음') for row in archive if isinstance(row, dict)][:50]
    result.update(retention_policy=POLICY, retention_days=DAYS,
                  retention_checked_on=clock.isoformat(), retention_removed_count=removed,
                  retention_remaining_count=len(result['items']) + len(archive))
    return result
