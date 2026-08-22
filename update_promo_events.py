#!/usr/bin/env python3
"""Discover and recheck dated events from approved public official pages."""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import html
import json
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "promo_events.json"
ALLOWED = {
    "www.pokemon-card.com", "www.30th.pokemon-card.com",
    "pokemoncard.co.kr", "www.pokemoncard.co.kr",
    "onepiece-cardgame.kr", "www.onepiece-cardgame.kr",
    "www.onepiece-cardgame.com", "en.onepiece-cardgame.com",
    "shop.bandainamco-am.com", "www.pokemon.com",
}
INDEXES = (
    ("KR", "원피스 카드", "https://onepiece-cardgame.kr/events.do"),
    ("KR", "포켓몬 카드", "https://pokemoncard.co.kr/card/category/event"),
    ("JP", "포켓몬 카드", "https://www.pokemon-card.com/info/"),
    ("JP", "원피스 카드", "https://www.onepiece-cardgame.com/events/"),
    ("US", "원피스 카드", "https://en.onepiece-cardgame.com/events/"),
    ("US", "포켓몬 카드", "https://www.pokemon.com/us/play-pokemon"),
)
TIMEOUT_SECONDS = 12
MAX_DISCOVERED_PER_INDEX = 3
EVENT_WORDS = re.compile(
    r"이벤트|행사|배틀|교류회|챔피언|토너먼트|프로모|"
    r"イベント|バトル|キャンペーン|チャンピオン|"
    r"event|battle|championship|tournament|promo|league|cup",
    re.I,
)


def approved_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED:
        raise ValueError("허용되지 않은 공식 출처")
    if parsed.username or parsed.password:
        raise ValueError("인증정보가 포함된 주소 차단")
    return url


class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        approved_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url: str) -> str:
    approved_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 TCG-Grader-Promo-Checker/2.0"})
    opener = urllib.request.build_opener(OfficialRedirect)
    with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
        approved_url(response.geturl())
        return response.read(1_500_000).decode("utf-8", "replace")


def plain(value: str) -> str:
    value = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"(?s)<[^>]+>", " ", value))).strip()


class AnchorParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.href = None
        self.parts = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.href = dict(attrs).get("href")
            self.parts = []

    def handle_data(self, value):
        if self.href is not None:
            self.parts.append(value)

    def handle_endtag(self, tag):
        if tag == "a" and self.href is not None:
            text = re.sub(r"\s+", " ", " ".join(self.parts)).strip()
            if text:
                self.links.append((self.href, text))
            self.href = None
            self.parts = []


def date_range(text: str) -> tuple[str, str] | None:
    dates = []
    patterns = (
        r"(20\d{2})[.년/\-]\s*(\d{1,2})[.월/\-]\s*(\d{1,2})",
        r"([A-Za-z]+)\s+(\d{1,2})(?:\s*[-–~]\s*(\d{1,2}))?,?\s+(20\d{2})",
    )
    for year, month, day in re.findall(patterns[0], text):
        try:
            dates.append(dt.date(int(year), int(month), int(day)))
        except ValueError:
            continue
    for month, start, end, year in re.findall(patterns[1], text):
        try:
            first = dt.datetime.strptime(f"{month} {start} {year}", "%B %d %Y").date()
            dates.append(first)
            if end:
                dates.append(first.replace(day=int(end)))
        except ValueError:
            continue
    if not dates:
        month_day = re.findall(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일", text)
        if len(month_day) >= 2:
            year = dt.date.today().year
            for month, day in month_day[:2]:
                try:
                    dates.append(dt.date(year, int(month), int(day)))
                except ValueError:
                    continue
    if not dates:
        return None
    start, end = min(dates), max(dates)
    today = dt.date.today()
    if end < today or start > today + dt.timedelta(days=550):
        return None
    if (end - start).days > 370:
        return None
    return start.isoformat(), end.isoformat()


def valid(item: dict) -> bool:
    required = ("game", "region", "name_ko", "start_date", "end_date", "reward", "condition", "source")
    if not isinstance(item, dict) or not all(item.get(key) for key in required):
        return False
    if item.get("region") not in {"KR", "JP", "US"}:
        return False
    try:
        approved_url(item["source"])
        start = dt.date.fromisoformat(item["start_date"])
        end = dt.date.fromisoformat(item["end_date"])
    except (ValueError, TypeError):
        return False
    return start <= end


def discover(index: tuple[str, str, str]) -> tuple[list[dict], list[str]]:
    region, game, root_url = index
    rows = []
    errors = []
    try:
        raw = fetch(root_url)
        parser = AnchorParser()
        parser.feed(raw)
        for href, label in parser.links:
            if len(rows) >= MAX_DISCOVERED_PER_INDEX:
                break
            if not EVENT_WORDS.search(label) or len(label) < 8:
                continue
            target = urllib.parse.urljoin(root_url, href).split("#", 1)[0]
            try:
                approved_url(target)
            except ValueError:
                continue
            dates = date_range(label)
            if dates is None:
                continue
            start, end = dates
            native = re.sub(r"\s+", " ", label).strip()[:140]
            rows.append({
                "game": game,
                "region": region,
                "category": "collaboration" if EVENT_WORDS.search(native) and re.search(r"교류|collab|champion|チャンピオン", native, re.I) else "promo",
                "name_ko": native if region == "KR" else f"{'일본' if region == 'JP' else '미국'} 공식 행사 · {native}",
                "name_native": native,
                "start_date": start,
                "end_date": end,
                "claim_deadline": end,
                "reward": "공식 행사 안내에서 참가·입상 보상 확인",
                "condition": "공식 안내의 참가 자격·접수 일정·현장 조건을 확인하세요.",
                "location": {"KR": "한국 공식 개최점", "JP": "일본 공식 개최점", "US": "미국 공식 개최점"}[region],
                "status": "진행 중" if dt.date.fromisoformat(start) <= dt.date.today() else "예정",
                "source": target,
                "discovered_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            })
    except Exception as exc:
        errors.append(f"{region} {game} 신규행사 탐색: {type(exc).__name__}")
    return rows, errors


def check_existing(item: dict) -> tuple[dict, str | None]:
    try:
        page = fetch(item["source"])
        native_tokens = re.findall(r"[가-힣ァ-ヶ一-龠]{4,}|[A-Za-z]{5,}", item.get("name_native", ""))[:4]
        korean_tokens = re.findall(r"[가-힣]{4,}", item.get("name_ko", ""))[:3]
        if native_tokens or korean_tokens:
            lowered = page.lower()
            if not any(token.lower() in lowered for token in native_tokens + korean_tokens):
                raise ValueError("행사명 확인 실패")
        return item, None
    except Exception as exc:
        return item, f"{item['name_ko']}: {type(exc).__name__}"


def main() -> dict:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    original = data.get("items", [])
    if not isinstance(original, list):
        raise ValueError("행사 목록 형식 오류")
    errors = []
    existing = []
    for item in original:
        if valid(item):
            existing.append(item)
        else:
            errors.append(f"구조 오류: {item.get('name_ko', '이름 없음')}")
    if original and not existing:
        raise ValueError("기존 행사 대량 삭제 방지")

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        checked_results = list(pool.map(check_existing, existing))
        discovery_results = list(pool.map(discover, INDEXES))

    checked = []
    known_urls = set()
    for item, error in checked_results:
        checked.append(item)
        known_urls.add(item["source"])
        if error:
            errors.append(error)

    added = 0
    for discovered, discovery_errors in discovery_results:
        errors.extend(discovery_errors)
        for item in discovered:
            if item["source"] not in known_urls and valid(item):
                checked.append(item)
                known_urls.add(item["source"])
                added += 1

    data["items"] = checked
    data["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    data["new_event_count"] = added
    data["discovery_sources"] = len(INDEXES)
    data["collection_status"] = "정상" if not errors else "기존 확인자료 유지 · 일부 출처 재확인 필요"
    data["collection_errors"] = errors
    temp = DATA.with_suffix(".json.tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(DATA)
    return data


if __name__ == "__main__":
    main()
