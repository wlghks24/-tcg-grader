#!/usr/bin/env python3
"""Bounded official-only Chinese Pokemon sealed-product discovery.

Official catalog candidates only: no real sales, automatic holdings, prices or
grade inference. HK/TW locality remains visible inside CN-T edition records.
"""
from __future__ import annotations
import re
import datetime as dt
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.request import Request
from safe_runtime import safe_urlopen

SOURCES = (
    ('CN-S', 'CN', 'https://www.pokemon.cn/tcg/product'),
    ('CN-T', 'HK', 'https://asia.pokemon-card.com/hk/products/'),
    ('CN-T', 'TW', 'https://asia.pokemon-card.com/tw/products/'),
)
HOSTS = {'www.pokemon.cn', 'pokemon.cn', 'asia.pokemon-card.com'}
MAX_BYTES = 1_200_000
MAX_LINKS = 100
MAX_ROWS_PER_SOURCE = 20
MAX_ROWS_TOTAL = 50
BOX_HINT = re.compile(r'(?:盒|禮盒|礼盒|箱|套裝|套装|組合|组合|BOX|禮包|礼包|收藏盒|珍藏)', re.I)
NOT_PRODUCT = re.compile(r'(?:活動規則|活動規定|比賽報名|道館|排行榜|活动细则|赛事报名)', re.I)

def safe_link(index_url: str, href: str, region: str) -> str | None:
    if not isinstance(href, str) or not href or len(href) > 450 or any(ord(c) < 33 for c in href):
        return None
    url = urljoin(index_url, href)
    p = urlsplit(url)
    if p.scheme != 'https' or p.netloc not in HOSTS or p.query or p.fragment:
        return None
    if region == 'CN-S':
        if p.netloc not in {'www.pokemon.cn', 'pokemon.cn'} or not re.fullmatch(r'/tcg/product/[0-9]{2,9}\.html', p.path):
            return None
    elif region == 'CN-T':
        if p.netloc != 'asia.pokemon-card.com' or not re.fullmatch(r'/(?:hk|tw)/archives/[0-9]{2,9}/', p.path):
            return None
    else:
        return None
    return url

class _Anchors(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.recent, self.current = [], [], None
    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'a' and self.current is None:
            self.current = {'href': dict(attrs).get('href'), 'text': [], 'context': self.recent[-3:]}
    def handle_data(self, text):
        part = ' '.join(text.split())
        if not part or len(part) > 320:
            return
        if self.current is not None:
            self.current['text'].append(part)
        else:
            self.recent.append(part)
            if len(self.recent) > 10: self.recent = self.recent[-10:]
    def handle_endtag(self, tag):
        if tag.lower() == 'a' and self.current is not None:
            if len(self.links) < MAX_LINKS: self.links.append(self.current)
            self.current = None

def parse_official_html(body: str, region: str, locale: str, url: str, checked_at: str) -> list[dict]:
    if not isinstance(body, str) or len(body) > MAX_BYTES:
        return []
    parser = _Anchors()
    parser.feed(body)
    rows, seen = [], set()
    for entry in parser.links:
        source = safe_link(url, entry['href'], region)
        if not source or source in seen:
            continue
        label = ' '.join(entry['text']).strip()
        if region == 'CN-S':
            match = re.search(r'\bProduct\s+(20\d{2}-\d{2}-\d{2})\b', label)
            if not match: continue
            published = match.group(1)
            title = re.sub(r'\s*Product\s+20\d{2}-\d{2}-\d{2}\s*$', '', label).strip()
        else:
            published = None
            if label in ('商品資訊', '商品信息', ''):
                title = next((x for x in reversed(entry['context']) if x not in ('商品資訊', '商品信息') and len(x) >= 6), '')
            else:
                title = label
        if not title or len(title) > 150 or NOT_PRODUCT.search(title) or not BOX_HINT.search(title):
            continue
        if region == 'CN-S' and not re.search(r'[\u3400-\u9fff]', title):
            continue
        # Score means evidence-completeness only, NOT price, grade or profitability.
        # 20 each: official link, exact edition locale, product title,
        # valid publication date, verified completed-sale evidence (always 0).
        valid_published=False
        if published:
            try:
                day=dt.date.fromisoformat(published)
                valid_published=day<=dt.datetime.now(dt.timezone.utc).date()
            except ValueError:
                valid_published=False
        completeness_score=60+(20 if valid_published else 0)
        seen.add(source)
        rows.append({
            'region': region, 'market_locale': locale, 'game': 'Pokémon',
            'asset': 'BOX', 'name': title, 'native': title, 'product_code': '',
            'package_type': '공식 미개봉 상품 · BOX 구성 확인 필요',
            'release_date': '확인 중', 'catalog_published_at': published,
            'sale_status': '공식 상품 발견 · 거래가 미확인',
            'release_type': '공식 상품 목록', 'official_price': '확인 중',
            'source': source, 'source_grade': 'official_catalog',
            'source_checked_at': checked_at, 'market_eligible': False,
            'price_evidence': 'NONE', 'autodiscovered': True,
            'evidence_completeness_score': completeness_score,
            'evidence_score_kind': 'CATALOG_ONLY_NOT_PRICE',
            'investment_score': None, 'market_decision': 'HOLD',
        })
        if len(rows) >= MAX_ROWS_PER_SOURCE: break
    return rows

def fetch_official_products(*, fetcher=None, now: dt.datetime | None = None) -> dict:
    checked_at = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc).isoformat(timespec='seconds')
    def network(url):
        req = Request(url, headers={'User-Agent':'TCG-Grader-OfficialCatalog/1.0',
                                   'Accept':'text/html','Accept-Language':'zh-CN,zh;q=0.8'})
        with safe_urlopen(req, timeout=6, allowed_hosts=HOSTS, max_redirects=1) as response:
            data = response.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES: raise ValueError('official index too large')
            return data.decode('utf-8', 'replace')
    load = fetcher or network
    all_rows, errors, coverage = [], [], []
    for region, locale, url in SOURCES:
        try:
            rows = parse_official_html(load(url), region, locale, url, checked_at)
            if not rows: raise ValueError('official product index parser found no qualified BOX candidates')
            all_rows.extend(rows)
            coverage.append({'region':region,'locale':locale,'count':len(rows),'checked_at':checked_at})
        except (OSError, ValueError, TimeoutError, UnicodeError) as exc:
            errors.append({'region':region,'locale':locale,'error':type(exc).__name__})
    return {'items':all_rows[:MAX_ROWS_TOTAL], 'coverage':coverage, 'errors':errors,
            'checked_at':checked_at, 'automatic':True, 'prices_verified':False, 'holdings_created':False}
