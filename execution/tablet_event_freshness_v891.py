"""Fresh coverage adapter for the existing event watcher; no fetch/scheduler.

Old rows remain in the original snapshot. Only the priority-gap calculation uses
freshly collected evidence; publication or whole-file update time is not a receipt.
"""
from datetime import datetime, timezone, timedelta
from functools import wraps

MAX_ROWS = 3000
MAX_AGE_SECONDS = 7 * 86400


def fresh_rows(items, *, now=None):
    now = datetime.now(timezone.utc) if now is None else now
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError('timezone-aware freshness clock required')
    if not isinstance(items, list) or len(items) > MAX_ROWS:
        return []
    result = []
    for row in items:
        if not isinstance(row, dict):
            continue
        raw = row.get('collected_at')
        if not isinstance(raw, str) or len(raw) > 64:
            continue
        try:
            checked = datetime.fromisoformat(raw.replace('Z', '+00:00'))
            if checked.tzinfo is None:
                continue
            age = (now - checked).total_seconds()
            if not 0 <= age <= MAX_AGE_SECONDS:
                continue
            dates = row.get('dates', [])
            if not isinstance(dates, list) or len(dates) > 32:
                continue
            parsed = []
            for value in dates:
                if not isinstance(value, str) or len(value) != 10:
                    raise ValueError('invalid event date')
                parsed.append(datetime.strptime(value, '%Y-%m-%d').date())
            # A freshly re-read historical event cannot fill current coverage.
            if parsed and max(parsed) < now.astimezone(timezone(timedelta(hours=9))).date():
                continue
        except (ValueError, OverflowError):
            continue
        result.append(row)
    return result


def install(watcher):
    """Compose with original game/region/topic/trust checks; idempotent startup."""
    original = watcher._priority_gaps
    if getattr(original, '_tcg_freshness_v891', False):
        return
    if not callable(original):
        raise ValueError('event priority callback required')
    @wraps(original)
    def wrapped(items, registry):
        return original(fresh_rows(items), registry)
    wrapped._tcg_freshness_v891 = True
    watcher._priority_gaps = wrapped
