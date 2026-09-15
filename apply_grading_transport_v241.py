from pathlib import Path

p = Path('grading_company_watch.py')
text = p.read_text(encoding='utf-8')
if 'def _transient_retry_delay(' in text:
    raise SystemExit('transport recovery already present')
text = text.replace(
    'from datetime import datetime, timezone\n',
    'from datetime import datetime, timezone\nfrom email.utils import parsedate_to_datetime\n',
    1,
)
text = text.replace(
    'import re\nimport urllib.request\n',
    'import re\nimport time\nimport urllib.error\nimport urllib.request\n',
    1,
)
old = '''def _fetch_raw(url: str) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Language": "ko-KR,ja-JP;q=0.9,en-US;q=0.8,en;q=0.7",
    })
    with safe_urlopen(req, timeout=20, allowed_hosts=ALLOWED_HOSTS, max_redirects=3) as response:
        return response.read(MAX_PAGE_BYTES).decode("utf-8", "ignore")
'''
new = '''def _transient_retry_delay(exc: Exception) -> float | None:
    """One short retry for transport failures; never retry access/policy denial."""
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code not in {502, 503, 504}:
            return None
        value = exc.headers.get("Retry-After") if exc.headers else None
        if value is not None:
            try:
                delay = float(int(value.strip())) if value.strip().isdigit() else (
                    parsedate_to_datetime(value) - datetime.now(timezone.utc)
                ).total_seconds()
            except (ValueError, TypeError, OverflowError, AttributeError):
                return None
            return max(0.0, delay) if math.isfinite(delay) and delay <= 2 else None
        return 1.0
    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    return 1.0 if isinstance(reason, (TimeoutError, ConnectionResetError)) else None


def _fetch_raw(url: str) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Language": "ko-KR,ja-JP;q=0.9,en-US;q=0.8,en;q=0.7",
    })
    for attempt in range(2):
        try:
            with safe_urlopen(req, timeout=20, allowed_hosts=ALLOWED_HOSTS, max_redirects=3) as response:
                return response.read(MAX_PAGE_BYTES).decode("utf-8", "ignore")
        except (OSError, ValueError) as exc:
            delay = _transient_retry_delay(exc) if attempt == 0 else None
            if delay is None:
                raise
            if isinstance(exc, urllib.error.HTTPError):
                exc.close()
            time.sleep(delay)
'''
if old not in text:
    raise SystemExit('_fetch_raw anchor missing')
text = text.replace(old, new, 1)
old_return = '''        "schema_version": 1,
        "checked_at": checked_at,
        "policy": {
'''
new_return = '''        "schema_version": 1,
        "checked_at": checked_at,
        "updated_at": checked_at,
        "collection_status": ("정상" if ok_sources == len(health_rows) else "감정업체 일부 출처 확인 실패 · 검증된 기존자료 보존"),
        "collection_errors": [f"{row['source_id']}: {row.get('error', 'source degraded')}"
                              for row in health_rows if row["status"] != "ok"],
        "policy": {
'''
if old_return not in text:
    raise SystemExit('return status anchor missing')
text = text.replace(old_return, new_return, 1)
p.write_text(text, encoding='utf-8')
