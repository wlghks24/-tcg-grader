"""Bounded CJ cinema announcements, with injected local safe HTTP transport.

``fetch(url)`` must validate redirects as well as the initial URL and return text
or bytes. This module checks the exact initial host; it never creates transport,
executes HTML, infers card rewards, or treats a publication date as a show date.
"""
from __future__ import annotations

import datetime as dt
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
import re
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import xml.etree.ElementTree as ET

HOST = 'cjnews.cj.net'
MAX_BYTES = 1_500_000
MAX_ITEMS = 30
MAX_ARTICLES = 4
MAX_AGE_DAYS = 90
MAX_SECONDS = 60
CONTENT = '{http://purl.org/rss/1.0/modules/content/}encoded'
GAMES = (('원피스 카드', '원피스', r'원피스|one\s*piece'),
         ('포켓몬 카드', '포켓몬', r'포켓몬(?:스터)?|pok[eé]mon'),
         ('나루토 카드', '나루토', r'나루토|naruto'))
QUOTED = re.compile(r'[‘’「『“\"《]([^‘’「」『』“”\"《》\n]{2,100})[’」』”\"》]')
DATE = re.compile(r'(?:(\d{4})년\s*)?(?:(\d{1,2})월\s*)?(\d{1,2})일(?:부터|에|[은는, ]|$)')
SCREENING = re.compile(r'재상영|특별상영|상영|재개봉|개봉')
UNCONFIRMED = re.compile(r'(?:상영|개봉).{0,30}(?:취소|미정|검토|협의|않|없)|(?:취소|미정).{0,20}(?:상영|개봉)')
WEEKDAYS = {'월': 0, '화': 1, '수': 2, '목': 3, '금': 4, '토': 5, '일': 6}


def _error_kind(exc):
    # Reveal useful transport categories without echoing untrusted URLs, query
    # credentials or a provider's arbitrary response in diagnostics.
    reason = str(getattr(exc, 'reason', '')).casefold()
    for marker in ('dns lookup failed', 'name or service not known',
                   'temporary failure in name resolution', 'timed out'):
        if marker in reason:
            return type(exc).__name__+': '+marker
    return type(exc).__name__


def _body(value):
    if not isinstance(value, (str, bytes)):
        raise ValueError('response_type')
    raw = value.encode('utf-8') if isinstance(value, str) else value
    if len(raw) > MAX_BYTES:
        raise ValueError('response_size')
    if b'<!doctype' in raw.lower() or b'<!entity' in raw.lower():
        # Normal HTML doctypes are harmless, but neither RSS nor confirmation
        # needs document declarations. Reject entity-capable XML before parsing.
        if b'<!entity' in raw.lower() or b'<rss' in raw.lower():
            raise ValueError('xml_declaration_forbidden')
    return raw.decode('utf-8', errors='strict')


def _url(value, *, article=False):
    if not isinstance(value, str) or len(value) > 4096 or any(ord(c) <= 32 for c in value) or '\\' in value:
        raise ValueError('url_shape')
    parts = urlsplit(value)
    if (parts.scheme != 'https' or parts.hostname != HOST or
            parts.username is not None or parts.password is not None or
            parts.port not in (None, 443)):
        raise ValueError('url_host')
    if article and parts.path.rstrip('/') in ('', '/feed'):
        raise ValueError('article_url_required')
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.casefold().startswith('utm_')]
    return urlunsplit(('https', HOST, parts.path, urlencode(query), ''))


class _Paragraphs(HTMLParser):
    """Read paragraph text only; ignore navigation, related cards and code."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.parts = None
        self.rows = []

    def handle_starttag(self, tag, attrs):
        if tag in ('br', 'img', 'meta', 'link', 'hr', 'input', 'source', 'wbr'):
            if self.parts is not None and tag == 'br':
                self.parts.append(' ')
            return
        values = dict(attrs)
        marker = ' '.join(str(values.get(k) or '') for k in ('class', 'id')).casefold()
        blocked = (tag in ('script', 'style', 'nav', 'footer', 'aside') or
                   any(s in marker for s in ('related', 'recommend', 'faq', 'sidebar')) or
                   'hidden' in values or values.get('aria-hidden') == 'true')
        self.stack.append((tag, blocked))
        if tag == 'p':
            self.parts = [] if not any(x[1] for x in self.stack) else None
        elif self.parts is not None:
            self.parts.append(' ')

    def handle_endtag(self, tag):
        if tag == 'p' and self.parts is not None:
            text = re.sub(r'\s+', ' ', ''.join(self.parts)).strip()
            if text and len(text) <= 4000 and len(self.rows) < 600:
                self.rows.append(text)
            self.parts = None
        for i in range(len(self.stack)-1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self.parts is not None and not any(x[1] for x in self.stack):
            self.parts.append(data)


def _paragraphs(value):
    parser = _Paragraphs()
    parser.feed(_body(value))
    return parser.rows


def _month(article_title):
    months = {int(m) for m in re.findall(r'(?<!\d)(\d{1,2})월', article_title)}
    return next(iter(months)) if len(months) == 1 else None


def _schedule(sentence, title_span, article_title, published):
    nearby = []
    for match in DATE.finditer(sentence):
        distance = max(title_span[0]-match.end(), match.start()-title_span[1], 0)
        if distance <= 90:
            nearby.append((distance, match))
    if not nearby:
        return None
    nearby.sort(key=lambda x: x[0])
    if len(nearby) > 1:
        # Multiple dates can describe releases, presales or rewards. Do not pick
        # one merely because it happens to be first or nearest in prose.
        return None
    match = nearby[0][1]
    year = int(match[1]) if match[1] else published.year
    month = int(match[2]) if match[2] else _month(article_title)
    if month is None:
        return None
    try:
        start = dt.date(year, month, int(match[3]))
    except ValueError:
        return None
    if abs((start-published.date()).days) > 90:
        return None
    weeks = re.search(r'(?<!\d)([1-8])\s*주간', sentence)
    weekly = re.search(r'매주\s*([월화수목금토일\s·ㆍ,]+)요일', sentence)
    if weeks or weekly or re.search(r'매일|매주|주간|[~～]|부터.{0,25}까지', sentence):
        if not (weeks and weekly and '부터' in match[0]):
            return None
        days = {WEEKDAYS[c] for c in weekly[1] if c in WEEKDAYS}
        if not days or start.weekday() not in days:
            return None
        dates = [start+dt.timedelta(days=i) for i in range(int(weeks[1])*7)
                 if (start+dt.timedelta(days=i)).weekday() in days]
        return {'start': start, 'end': dates[-1], 'dates': [d.isoformat() for d in dates],
                'basis': '공식 본문의 시작일·주간 수·매주 지정 요일로 계산',
                'precision': 'day', 'weekly_phrase': weeks[0]+' '+weekly[0]}
    # A lone opening date does not reveal when a cinema will stop screening.
    return {'start': start, 'end': start+dt.timedelta(days=90), 'dates': [start.isoformat()],
            'basis': '공식 본문의 개봉·상영 시작일만 확인; 종료일은 미발표',
            'precision': 'start-only', 'weekly_phrase': ''}


def _announcements(paragraphs, game_pattern, article_title, published):
    results = []
    for paragraph in paragraphs:
        if re.match(r'(?:[QA][.：:]|질문|답변)', paragraph, re.I):
            continue
        for sentence in re.split(r'(?<=[.!?。])\s+', paragraph):
            if not SCREENING.search(sentence) or UNCONFIRMED.search(sentence):
                continue
            titles = [m for m in QUOTED.finditer(sentence) if re.search(game_pattern, m[1], re.I)]
            if len(titles) != 1:
                continue
            match = titles[0]
            title = match[1].strip()
            # A quoted franchise alone is not an identified film title.
            remainder = re.sub(game_pattern, '', title, flags=re.I)
            if len(re.sub(r'[\W_]', '', remainder)) < 2:
                continue
            schedule = _schedule(sentence, match.span(), article_title, published)
            if schedule:
                results.append((title, schedule))
    return results


def _key(title, schedule):
    return (re.sub(r'\s+', '', title).casefold(), schedule['start'].isoformat(),
            schedule['end'].isoformat(), tuple(schedule['dates']), schedule['precision'])


def collect(fetch, now=None):
    """Return ``(rows, errors)`` from three feeds and <=4 article checks total.

    Missing evidence remains an explicit collection gap. ``end_date`` on a
    start-only row is solely the existing schema's internal review deadline.
    """
    current = now or dt.datetime.now(dt.timezone.utc)
    if not isinstance(current, dt.datetime) or current.tzinfo is None:
        raise ValueError('aware_now_required')
    current = current.astimezone(dt.timezone.utc)
    checked_at = current.isoformat(timespec='seconds')
    rows, errors, seen = [], [], set()
    deadline = time.monotonic()+MAX_SECONDS
    article_attempts = 0
    for game, query, pattern in GAMES:
        feed = 'https://'+HOST+'/feed/?'+urlencode({'s': query})
        if time.monotonic() >= deadline:
            errors.append(f'CJ_OFFICIAL_BUDGET_EXHAUSTED {query}')
            continue
        try:
            body = _body(fetch(_url(feed)))
            if '<!doctype' in body.casefold() or '<!entity' in body.casefold():
                raise ValueError('xml_declaration_forbidden')
            root = ET.fromstring(body)
            if root.tag != 'rss':
                raise ValueError('rss_required')
        except Exception as exc:
            errors.append(f'CJ_OFFICIAL_FEED {query}: {_error_kind(exc)}')
            continue
        article_urls = set()
        found = 0
        feed_items = root.findall('./channel/item')
        if len(feed_items) > MAX_ITEMS:
            errors.append(f'CJ_OFFICIAL_ITEM_LIMIT {query}')
        for item in feed_items[:MAX_ITEMS]:
            article_title = item.findtext('title', '')
            content = item.findtext(CONTENT, '')
            if not re.search(pattern, article_title+' '+content, re.I):
                continue
            try:
                published = parsedate_to_datetime(item.findtext('pubDate', ''))
                if published.tzinfo is None:
                    raise ValueError('publication_timezone')
                published = published.astimezone(dt.timezone.utc)
                age = current-published
                if not dt.timedelta(0) <= age <= dt.timedelta(days=MAX_AGE_DAYS):
                    continue
                source = _url(item.findtext('link', ''), article=True)
                candidates = _announcements(_paragraphs(content), pattern, article_title, published)
                if not candidates:
                    continue
                if source in article_urls:
                    continue
                if article_attempts >= MAX_ARTICLES:
                    errors.append(f'CJ_OFFICIAL_ARTICLE_LIMIT {query}')
                    break
                if time.monotonic() >= deadline:
                    errors.append(f'CJ_OFFICIAL_BUDGET_EXHAUSTED {query}')
                    break
                article_urls.add(source)
                article_attempts += 1
                article_body = _body(fetch(source))
                confirmations = _announcements(_paragraphs(article_body), pattern, article_title, published)
                if 'CGV' not in article_title.upper()+' '+article_body.upper():
                    raise ValueError('cinema_operator_missing')
                confirmed = {_key(title, schedule) for title, schedule in confirmations}
                for title, schedule in candidates:
                    if _key(title, schedule) not in confirmed:
                        errors.append(f'CJ_OFFICIAL_CONTENT_MISMATCH {query}')
                        continue
                    identity = (source, game, re.sub(r'\s+', '', title).casefold())
                    if identity in seen:
                        continue
                    seen.add(identity)
                    single = schedule['precision'] == 'start-only'
                    row = {
                        'game': game, 'region': 'KR', 'category': 'movie',
                        'name_ko': title+' · CGV 공식 상영 일정', 'name_native': title,
                        'start_date': schedule['start'].isoformat(),
                        'end_date': schedule['end'].isoformat(), 'claim_deadline': None,
                        'reward': '카드 특전 확인 안 됨',
                        'condition': ('상영 시작일만 확정 · 종료일 미발표 · 내부 검토 기한은 상영 종료일이 아님 · 극장별 시간 확인'
                                      if single else '매일 상영 아님 · '+schedule['weekly_phrase']+' · 극장별 시간 확인'),
                        'location': '대한민국 CGV · 극장별 상영관 확인',
                        'source': source, 'collection_source': source,
                        'discovery_source': feed, 'discovered_at': checked_at,
                        'source_grade': 'official', 'media_type': 'theatrical_film',
                        'date_precision': schedule['precision'],
                        'date_label': (schedule['start'].isoformat()+' 개봉·상영 시작 확정 · 종료일 미발표'
                                       if single else '공식 반복 상영 일정 '+', '.join(schedule['dates'])),
                        'schedule_dates': schedule['dates'], 'schedule_basis': schedule['basis'],
                        'source_published_at': published.isoformat(timespec='seconds'),
                        'link_status': '정상', 'link_checked_at': checked_at,
                        'content_checked_at': checked_at, 'tracking_only': single,
                    }
                    if single:
                        row['internal_review_until'] = schedule['end'].isoformat()
                    rows.append(row)
                    found += 1
            except Exception as exc:
                errors.append(f'CJ_OFFICIAL_ARTICLE {query}: {_error_kind(exc)}')
        if not found:
            errors.append(f'CJ_OFFICIAL_NO_CONFIRMED_SCHEDULE {query}')
    return rows, errors
