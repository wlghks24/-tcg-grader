from __future__ import annotations

import html
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

from instagram_tcg_content.collector_runtime import FetchResult, SourceSpec, ValidationError, canonicalize_url, utc_now
from instagram_tcg_content.canonical_taxonomy import normalize_content_type
from instagram_tcg_content.collection_normalizer import normalize_collector_record

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.I | re.S)
_WS_RE = re.compile(r"\s+")


def html_to_text(body: bytes) -> str:
    raw = body.decode("utf-8", errors="replace")
    raw = _SCRIPT_STYLE_RE.sub(" ", raw)
    raw = _TAG_RE.sub(" ", raw)
    return _WS_RE.sub(" ", html.unescape(raw)).strip()


def require_any(text: str, tokens: Sequence[str], code: str = "PARSER_SCHEMA_DRIFT") -> None:
    if not any(t.lower() in text.lower() for t in tokens):
        raise ValidationError(f"{code}: none of expected markers found: {tokens}")


def require_all(text: str, tokens: Sequence[str], code: str = "PARSER_SCHEMA_DRIFT") -> None:
    missing = [t for t in tokens if t.lower() not in text.lower()]
    if missing:
        raise ValidationError(f"{code}: missing expected markers: {missing}")


def _iso_date(year: str, month: str, day: str) -> str:
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def _usd(raw: str) -> Optional[float]:
    try:
        return float(raw.replace(",", ""))
    except Exception:
        return None


def _fact_type_from_text(text: str, default: str = "card_news") -> str:
    t = text.casefold()
    if any(k in t for k in ("재발매", "reprint", "재판")):
        return "rerelease"
    if any(k in t for k in ("재입고", "restock", "back in stock")):
        return "product_news"
    if any(k in t for k in ("프로모", "promotion", "campaign", "증정", "giveaway", "giving away", "distributed")):
        return "promo"
    if any(k in t for k in ("축제", "festival", "フェス")):
        return "festival"
    if any(k in t for k in ("이벤트", "대회", "토너먼트", "tournament", "event", "league", "battle", "demo session")):
        return "event"
    if any(k in t for k in ("영화", "movie", "theater", "극장", "cinema")):
        return "movie_bonus"
    if any(k in t for k in ("발매", "출시", "release", "available ")):
        return "release"
    if any(k in t for k in ("products", "product", "상품", "제품")):
        return "product_news"
    return normalize_content_type(default)


@dataclass(frozen=True)
class OfficialFact:
    canonical_identity: str
    game: str
    region: str
    language: str
    fact_type: str
    value: str
    effective_date_or_period: Optional[str]
    source_code: str
    source_locator: str
    source_tier: str = "official_primary"
    verification_status: str = "verified_official"
    checked_at: str = ""
    published_at_if_available: Optional[str] = None
    native_currency: Optional[str] = None
    native_value: Optional[float] = None
    product_code: Optional[str] = None
    market_status: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        d = asdict(self)
        if not d["checked_at"]:
            d["checked_at"] = utc_now()
        return {k: v for k, v in d.items() if v is not None}


def _bundle(source_code: str, locator: str, game: str, region: str, language: str, facts: Iterable[OfficialFact], parser_version: str) -> Mapping:
    rows = [normalize_collector_record(f.to_dict()) for f in facts]
    if not rows:
        raise ValidationError("PARSER_SCHEMA_DRIFT: parser produced zero official facts")
    return {
        "source_code": source_code,
        "canonical_locator": canonicalize_url(locator),
        "source_tier": "official_primary",
        "game": game,
        "region": region,
        "language": language,
        "parser_version": parser_version,
        "checked_at": utc_now(),
        "record_count": len(rows),
        "records": rows,
    }


def pokemon_jp_products_validator(result: FetchResult) -> Mapping:
    text = html_to_text(result.body)
    require_all(text, ("ポケモンカードゲーム", "商品", "販売日"))
    pat = re.compile(
        r"(?P<title>[^。]{2,100}?)\s+販売日\s*(?P<y>20\d{2})年\s*(?P<m>\d{1,2})月\s*(?P<d>\d{1,2})日(?:（[^）]+）)?(?:\s+希望小売価格\s*(?P<price>[\d,]+)円)?",
        re.I,
    )
    facts: List[OfficialFact] = []
    for m in pat.finditer(text):
        title = _WS_RE.sub(" ", m.group("title")).strip(" -|｜")[-100:]
        if not title or title in {"商品情報", "新着商品"}:
            continue
        date = _iso_date(m.group("y"), m.group("m"), m.group("d"))
        price = m.group("price")
        facts.append(OfficialFact(
            canonical_identity=title,
            game="POKEMON",
            region="JP",
            language="JA",
            fact_type="release",
            value=title,
            effective_date_or_period=date,
            source_code="POKEMON_JP_PRODUCTS",
            source_locator=result.url,
            native_currency="JPY" if price else None,
            native_value=float(price.replace(",", "")) if price else None,
        ))
    return _bundle("POKEMON_JP_PRODUCTS", result.url, "POKEMON", "JP", "JA", facts, "pokemon_jp_products_v2")


def pokemon_jp_info_validator(result: FetchResult) -> Mapping:
    text = html_to_text(result.body)
    require_all(text, ("ポケモンカードゲーム", "ニュース"))
    pat = re.compile(
        r"(?P<category>商品|イベント|キャンペーン|その他)\s+(?P<headline>[^。]{4,180}?)\s+(?P<y>20\d{2})\.(?P<m>\d{1,2})\.(?P<d>\d{1,2})"
    )
    facts: List[OfficialFact] = []
    for m in pat.finditer(text):
        headline = _WS_RE.sub(" ", m.group("headline")).strip()
        pub = _iso_date(m.group("y"), m.group("m"), m.group("d"))
        category = m.group("category")
        if category == "商品":
            ftype = _fact_type_from_text(headline, "product_news")
        elif category == "イベント":
            ftype = "event"
        elif category == "キャンペーン":
            ftype = "promo"
        else:
            ftype = _fact_type_from_text(headline)
        facts.append(OfficialFact(headline, "POKEMON", "JP", "JA", ftype, headline, None,
                                  "POKEMON_JP_INFO", result.url, published_at_if_available=pub))
    return _bundle("POKEMON_JP_INFO", result.url, "POKEMON", "JP", "JA", facts, "pokemon_jp_info_v1")


def pokemon_kr_news_validator(result: FetchResult) -> Mapping:
    text = html_to_text(result.body)
    require_any(text, ("포켓몬 카드 게임", "카드 게임"))
    pat = re.compile(
        r"(?P<headline>[^\n]{4,180}?)\s+(?:카드 게임\s+)?(?P<y>20\d{2})년\s*(?P<m>\d{1,2})월\s*(?P<d>\d{1,2})일"
    )
    facts: List[OfficialFact] = []
    seen = set()
    for m in pat.finditer(text):
        headline = _WS_RE.sub(" ", m.group("headline")).strip(" -|｜")[-180:]
        if not any(k in headline.lower() for k in ("카드", "mega", "확장팩", "배틀", "토너먼트", "리그", "card")):
            continue
        pub = _iso_date(m.group("y"), m.group("m"), m.group("d"))
        key = (headline, pub)
        if key in seen:
            continue
        seen.add(key)
        facts.append(OfficialFact(
            headline, "POKEMON", "KR", "KO", _fact_type_from_text(headline), headline, None,
            "POKEMON_KR_NEWS", result.url, published_at_if_available=pub
        ))
    return _bundle("POKEMON_KR_NEWS", result.url, "POKEMON", "KR", "KO", facts, "pokemon_kr_news_v1")


def pokemon_en_news_validator(result: FetchResult) -> Mapping:
    text = html_to_text(result.body)
    require_all(text, ("Pokémon", "Trading Card Game"))
    pat = re.compile(r"(?P<title>Pokémon\s+TCG:[^.!?]{3,140}?)\s+Available\s+(?P<month>[A-Za-z]+)\s+(?P<d>\d{1,2}),\s*(?P<y>20\d{2})", re.I)
    facts: List[OfficialFact] = []
    for m in pat.finditer(text):
        try:
            dt = datetime.strptime(f"{m.group('month')} {m.group('d')} {m.group('y')}", "%B %d %Y")
        except ValueError:
            continue
        title = _WS_RE.sub(" ", m.group("title")).strip()
        facts.append(OfficialFact(title, "POKEMON", "GLOBAL_EN", "EN", "release", title, dt.date().isoformat(), "POKEMON_EN_NEWS", result.url))
    if not facts:
        rel = re.search(r"releas(?:e|ing)[^.!?]{0,80}?\b(?P<month>January|February|March|April|May|June|July|August|September|October|November|December)\s+(?P<d>\d{1,2}),\s*(?P<y>20\d{2})", text, re.I)
        title = re.search(r"Pokémon\s+TCG:\s*([^|]{3,100})", text, re.I)
        if rel and title:
            dt = datetime.strptime(f"{rel.group('month')} {rel.group('d')} {rel.group('y')}", "%B %d %Y")
            name = "Pokémon TCG: " + _WS_RE.sub(" ", title.group(1)).strip()
            facts.append(OfficialFact(name, "POKEMON", "GLOBAL_EN", "EN", "release", name, dt.date().isoformat(), "POKEMON_EN_NEWS", result.url))
    if not facts:
        listing = re.compile(
            r"(?P<title>[^.!?]{4,180}?(?:Pokémon\s+TCG|Trading Card Game)[^.!?]{0,180}?)\s+"
            r"(?P<month>January|February|March|April|May|June|July|August|September|October|November|December)\s+"
            r"(?P<d>\d{1,2}),\s*(?P<y>20\d{2})", re.I
        )
        for m in listing.finditer(text):
            dt = datetime.strptime(f"{m.group('month')} {m.group('d')} {m.group('y')}", "%B %d %Y")
            title = _WS_RE.sub(" ", m.group("title")).strip()[-180:]
            facts.append(OfficialFact(title, "POKEMON", "GLOBAL_EN", "EN", "card_news", title, None,
                                      "POKEMON_EN_NEWS", result.url, published_at_if_available=dt.date().isoformat()))
    return _bundle("POKEMON_EN_NEWS", result.url, "POKEMON", "GLOBAL_EN", "EN", facts, "pokemon_en_news_v1")


def onepiece_products_validator(result: FetchResult) -> Mapping:
    text = html_to_text(result.body)
    require_all(text, ("ONE PIECE CARD GAME", "PRODUCTS"))
    pat = re.compile(
        r"(?P<title>[^|]{3,150}?)\s*\[(?P<code>(?:OP|EB|ST|PRB|DP)-?\d{1,3})\]\s*(?:Release Date\s*(?P<date>[A-Za-z]+\s+\d{1,2},\s*20\d{2})|Delivery Month\s*(?P<month>[A-Za-z]+\s+20\d{2}))?\s*(?:MSRPUSD\s*\$(?P<price>[\d.]+))?",
        re.I,
    )
    facts: List[OfficialFact] = []
    for m in pat.finditer(text):
        title = _WS_RE.sub(" ", m.group("title")).strip(" -|｜")[-150:]
        code = m.group("code").upper()
        effective: Optional[str] = None
        if m.group("date"):
            try:
                effective = datetime.strptime(_WS_RE.sub(" ", m.group("date")), "%B %d, %Y").date().isoformat()
            except ValueError:
                pass
        elif m.group("month"):
            try:
                dt = datetime.strptime(_WS_RE.sub(" ", m.group("month")), "%B %Y")
                effective = dt.strftime("%Y-%m")
            except ValueError:
                pass
        facts.append(OfficialFact(
            canonical_identity=f"{title} [{code}]", game="ONE_PIECE", region="GLOBAL_EN", language="EN",
            fact_type="release" if effective else "product_news", value=title,
            effective_date_or_period=effective, source_code="ONEPIECE_EN_PRODUCTS", source_locator=result.url,
            native_currency="USD" if m.group("price") else None,
            native_value=_usd(m.group("price")) if m.group("price") else None, product_code=code,
        ))
    return _bundle("ONEPIECE_EN_PRODUCTS", result.url, "ONE_PIECE", "GLOBAL_EN", "EN", facts, "onepiece_products_v1")


def onepiece_topics_validator(result: FetchResult) -> Mapping:
    text = html_to_text(result.body)
    require_all(text, ("ONE PIECE CARD GAME", "TOPICS"))
    pat = re.compile(r"(?P<headline>[^.]{5,180}?(?:has been announced|has been updated|we[’']ll be giving away)[^.]{0,80})\.?\s*(?P<month>January|February|March|April|May|June|July|August|September|October|November|December)\s+(?P<d>\d{1,2}),\s*(?P<y>20\d{2})", re.I)
    facts: List[OfficialFact] = []
    for m in pat.finditer(text):
        dt = datetime.strptime(f"{m.group('month')} {m.group('d')} {m.group('y')}", "%B %d %Y")
        headline = _WS_RE.sub(" ", m.group("headline")).strip()
        facts.append(OfficialFact(headline, "ONE_PIECE", "GLOBAL_EN", "EN", _fact_type_from_text(headline), headline, None, "ONEPIECE_EN_TOPICS", result.url, published_at_if_available=dt.date().isoformat()))
    return _bundle("ONEPIECE_EN_TOPICS", result.url, "ONE_PIECE", "GLOBAL_EN", "EN", facts, "onepiece_topics_v2")


def onepiece_kr_topics_validator(result: FetchResult) -> Mapping:
    text = html_to_text(result.body)
    require_all(text, ("원피스 카드게임", "공지사항"))
    pat = re.compile(r"(?P<category>PRODUCTS|EVENTS|CAMPAIGN|OTHER|ORGANIZED PLAY)\s+(?P<headline>[^\n]{4,180}?)\s+(?P<date>20\d{2}-\d{2}-\d{2})", re.I)
    facts: List[OfficialFact] = []
    for m in pat.finditer(text):
        headline = _WS_RE.sub(" ", m.group("headline")).strip(" -|｜")[-180:]
        category = m.group("category").upper()
        if category in {"EVENTS", "ORGANIZED PLAY"}:
            ftype = "event"
        elif category == "CAMPAIGN":
            ftype = "promo"
        elif category == "PRODUCTS":
            ftype = _fact_type_from_text(headline, "product_news")
        else:
            ftype = _fact_type_from_text(headline)
        facts.append(OfficialFact(headline, "ONE_PIECE", "KR", "KO", ftype, headline, None, "ONEPIECE_KR_TOPICS", result.url, published_at_if_available=m.group("date")))
    return _bundle("ONEPIECE_KR_TOPICS", result.url, "ONE_PIECE", "KR", "KO", facts, "onepiece_kr_topics_v1")


def naruto_official_news_validator(result: FetchResult) -> Mapping:
    text = html_to_text(result.body)
    require_any(text, ("NARUTO CARD GAME", "NARUTOカードゲーム"))
    facts: List[OfficialFact] = []
    pub = None
    mdy = re.search(r"\b(?P<m>\d{1,2})/(?P<d>\d{1,2})/(?P<y>20\d{2})\b", text)
    ymd = re.search(r"\b(?P<y>20\d{2})/(?P<m>\d{1,2})/(?P<d>\d{1,2})\b", text)
    m = mdy or ymd
    if m:
        pub = _iso_date(m.group("y"), m.group("m"), m.group("d"))
    launch = re.search(r"(?:release|launch|発売)[^.!。]{0,120}?(?P<year>20\d{2})(?:\s*(?P<season>summer|spring|fall|autumn|winter)|年(?P<jpseason>夏|春|秋|冬))?", text, re.I)
    if launch:
        year = launch.group("year")
        season = (launch.group("season") or launch.group("jpseason") or "").lower()
        period = year + (f"-{season}" if season else "")
        facts.append(OfficialFact(
            "NARUTO CARD GAME", "NARUTO", "GLOBAL", "EN" if "NARUTO CARD GAME" in text else "JA", "release",
            "NARUTO CARD GAME global release", period, "NARUTO_OFFICIAL_NEWS", result.url,
            published_at_if_available=pub, market_status="pre_retail" if int(year) > datetime.now(timezone.utc).year else None,
        ))
    for code in sorted(set(re.findall(r"\b(?:CP|PR|P)-\d{3}\b", text, re.I))):
        facts.append(OfficialFact(
            f"NARUTO CARD GAME {code.upper()}", "NARUTO", "GLOBAL", "EN" if "NARUTO CARD GAME" in text else "JA", "promo",
            code.upper(), None, "NARUTO_OFFICIAL_NEWS", result.url, published_at_if_available=pub,
            product_code=code.upper(), market_status="pre_retail",
        ))
    if not facts and pub:
        headline = re.search(r"(?:#\s*)?([^.!。]{5,180}NARUTO CARD GAME[^.!。]{0,120})", text, re.I)
        if headline:
            h = _WS_RE.sub(" ", headline.group(1)).strip()
            facts.append(OfficialFact(h, "NARUTO", "GLOBAL", "EN", "card_news", h, None, "NARUTO_OFFICIAL_NEWS", result.url, published_at_if_available=pub, market_status="pre_retail"))
    return _bundle("NARUTO_OFFICIAL_NEWS", result.url, "NARUTO", "GLOBAL", "EN", facts, "naruto_official_news_v2")


def naruto_cardgame_site_validator(result: FetchResult) -> Mapping:
    text = html_to_text(result.body)
    require_any(text, ("NARUTO CARD GAME", "NARUTOカードゲーム"))
    if len(text) < 150:
        raise ValidationError("PARSER_SCHEMA_DRIFT: NARUTO official game site returned shell/interstitial-like content")
    facts: List[OfficialFact] = []
    for y in sorted(set(re.findall(r"\b(20\d{2})\b", text))):
        if "release" in text.lower() or "発売" in text:
            facts.append(OfficialFact("NARUTO CARD GAME", "NARUTO", "GLOBAL", "EN", "release", "NARUTO CARD GAME", y, "NARUTO_CARDGAME_OFFICIAL", result.url, market_status="pre_retail"))
            break
    return _bundle("NARUTO_CARDGAME_OFFICIAL", result.url, "NARUTO", "GLOBAL", "EN", facts, "naruto_cardgame_site_v1")


def official_source_specs() -> List[SourceSpec]:
    return [
        SourceSpec("POKEMON_KR_NEWS", ["https://pokemoncard.co.kr/main"], validator=pokemon_kr_news_validator,
                   fallback_urls=["https://www.pokemonkorea.co.kr/"], provider_id="pokemon-official-kr"),
        SourceSpec("POKEMON_JP_PRODUCTS", ["https://www.pokemon-card.com/products/index.html"], validator=pokemon_jp_products_validator, provider_id="pokemon-official-jp-news"),
        SourceSpec("POKEMON_JP_INFO", ["https://www.pokemon-card.com/info/index.html"], validator=pokemon_jp_info_validator, provider_id="pokemon-official-jp-news"),
        SourceSpec("POKEMON_EN_NEWS", ["https://www.pokemon.com/us/news/all"], validator=pokemon_en_news_validator,
                   fallback_urls=["https://www.pokemon.com/us/pokemon-news/", "https://www.pokemon.com/uk/pokemon-news/"], provider_id="pokemon-official-us-news"),
        SourceSpec("ONEPIECE_KR_TOPICS", ["https://onepiece-cardgame.kr/topics.do"], validator=onepiece_kr_topics_validator,
                   fallback_urls=["https://onepiece-cardgame.kr/"], provider_id="onepiece-cardgame-regional"),
        SourceSpec("ONEPIECE_EN_PRODUCTS", ["https://en.onepiece-cardgame.com/products/"], validator=onepiece_products_validator, provider_id="onepiece-cardgame-global"),
        SourceSpec("ONEPIECE_EN_TOPICS", ["https://en.onepiece-cardgame.com/topics/"], validator=onepiece_topics_validator, provider_id="onepiece-cardgame-global"),
        SourceSpec("NARUTO_OFFICIAL_NEWS", ["https://naruto-official.com/en/news/"], validator=naruto_official_news_validator, provider_id="naruto-official-news"),
        SourceSpec("NARUTO_CARDGAME_OFFICIAL", ["https://www.naruto-cardgame.com/en/"], validator=naruto_cardgame_site_validator,
                   fallback_urls=["https://www.naruto-cardgame.com/jp/"], provider_id="naruto-cardgame-official"),
    ]
