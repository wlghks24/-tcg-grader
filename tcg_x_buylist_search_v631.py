#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V631 — Free, zero-API X search planner for ALL 30 registered card games.
Generates manual search queries/links; NEVER scrapes X or treats a post as a sold price.
Country is a market/search scope, NOT proof of an officially issued local edition.
Requires the existing tcg_game_registry.json from the same folder.
Python 3.9+ standard library only.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent
REGISTRY_PATH = ROOT / "tcg_game_registry.json"
LOCALES = ("JP", "KR", "US")

# These six Japanese shorthand names are high-signal SEARCH TERMS; not promised
# canonical manufacturer/official hashtags. An actual hashtag must begin with #.
JP_SHORT_NAMES = {
    "pokemon": "ポケカ",
    "onepiece": "ワンピカード",
    "yugioh": "遊戯王",
    "weiss-schwarz": "ヴァイス",
    "unionarena": "ユニアリ",
    "digimon": "デジカ",
}
# Optional rarity tokens, not an objective "six most valuable" ranking.
# All remaining games deliberately use broad discovery until terminology is verified.
JP_RARITY_HINTS = {
    "pokemon": ("SAR", "UR", "プロモ"),
    "onepiece": ("コミパラ", "スーパーパラレル", "SEC", "シリアル"),
    "yugioh": ("クオシク", "プリシク", "20thシク", "レリーフ"),
    "weiss-schwarz": ("SSP", "SP", "SEC", "サイン"),
    "unionarena": ("AP", "パラレル", "SR"),
    "digimon": ("SEC", "SP", "パラレル"),
}
# Region-specific rarity hints avoid assuming Japanese names apply in US/KR.
REGIONAL_RARITY_HINTS = {
    "KR": {
        "pokemon": ("SAR", "UR", "프로모"),
        "onepiece": ("코믹패러렐", "SEC", "시리얼"),
        "yugioh": ("쿼터센츄리 시크릿", "프리즈마틱 시크릿"),
        "weiss-schwarz": ("SSP", "SP", "SEC"),
        "unionarena": ("AP", "SR", "패러렐"),
        "digimon": ("SEC", "SP", "패러렐"),
    },
    "US": {
        "pokemon": ("SIR", "Hyper Rare", "Promo"),
        "onepiece": ("Manga Rare", "SEC", "Serial"),
        "yugioh": ("Quarter Century Secret Rare", "Starlight Rare", "Ultimate Rare"),
        "weiss-schwarz": ("SSP", "SP", "SEC"),
        "unionarena": ("AP", "SR", "Parallel"),
        "digimon": ("SEC", "Alt Art", "SP"),
    },
}
# Cross-game aliases ONLY to improve noisy discovery; not manufacturer claims.
JP_EXTRA_SEARCH_NAMES = {
    "naruto":"NARUTO", "gundam":"ガンダムカード", "dbsfw":"ドラゴンボール",
    "lorcana":"ロルカナ", "swu":"スターウォーズ アンリミテッド",
    "riftbound":"リフトバウンド", "mtg":"MTG", "flesh-and-blood":"Flesh and Blood",
    "cardfight-vanguard":"ヴァンガード", "hololive-ocg":"ホロカ",
    "shadowverse-evolve":"シャドウバース エボルヴ", "grand-archive":"Grand Archive",
    "final-fantasy-tcg":"FFTCG", "sorcery-contested-realm":"Sorcery Contested Realm",
    "godzilla-card-game":"ゴジラ カード", "palworld-ocg":"パルワールド カード",
    "cyberpunk-tcg":"Cyberpunk TCG", "elestrals":"Elestrals",
    "rush-of-ikorr":"Rush of Ikorr", "cookierun-braverse":"クッキーラン ブレイバーズ",
    "universus":"UniVersus", "alpha-clash":"Alpha Clash", "metazoo":"MetaZoo",
    "wixoss":"WIXOSS",
}
MARKET = {
    "JP": {
        "buy": ("買取", "買取表"),
        "exclude": ("販売", "オリパ", "トレード", "プレゼント", "交換希望"),
        "box": ("BOX", "ボックス", "未開封"),
        "edition": ("日本版", "日本語版"),
        "lang": "ja",
        "currency": "JPY",
    },
    "KR": {
        "buy": ("매입", "매입가", "삽니다"),
        "exclude": ("판매", "오리파", "교환", "나눔", "이벤트"),
        "box": ("BOX", "박스", "미개봉"),
        "edition": ("한국판", "국내판"),
        "lang": "ko",
        "currency": "KRW",
    },
    "US": {
        "buy": ("buylist", "we buy", "buying cards"),
        "exclude": ("giveaway", "raffle", "trade only", "for sale", "mystery box"),
        "box": ("booster box", "sealed box", "sealed"),
        "edition": ("English edition", "English"),
        "lang": "en",
        "currency": "USD",
    },
}


def _registry(path=REGISTRY_PATH):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = data.get("games")
    if data.get("schema_version") != 1 or not isinstance(rows, list) or len(rows) != 30:
        raise ValueError("INVALID_30_GAME_REGISTRY")
    if len({g["id"] for g in rows}) != 30 or not all(
        isinstance(g.get("canonical"), str) and isinstance(g.get("label_ko"), str)
        and isinstance(g.get("regions"), list) for g in rows
    ):
        raise ValueError("INVALID_GAME_REGISTRY_ROWS")
    return rows


def build_search_config(registry_path=REGISTRY_PATH):
    """30 games * JP/KR/US; all markets searchable; declared regions tagged."""
    rows = _registry(registry_path)
    result = {}
    for g in rows:
        key = g["id"]
        market_configs = {}
        for region in LOCALES:
            market = MARKET[region]
            if region == "JP":
                name = JP_SHORT_NAMES.get(key) or JP_EXTRA_SEARCH_NAMES.get(key) or g["canonical"]
                rarities = JP_RARITY_HINTS.get(key, ())
                curated = key in JP_SHORT_NAMES
            elif region == "KR":
                name = g["label_ko"]
                rarities = REGIONAL_RARITY_HINTS["KR"].get(key, ())
                curated = False
            else:
                # English canonical name is not necessarily the US product imprint.
                name = g["canonical"]
                rarities = REGIONAL_RARITY_HINTS["US"].get(key, ())
                curated = False
            market_configs[region] = {
                "hashtag": name,  # Search text; no leading # unless confirmed.
                "hashtag_verified": False,
                "name_source": "JP_COMMON_SEARCH_ALIAS" if curated else "REGISTRY_OR_SEARCH_ALIAS",
                "top_rarities": list(rarities),  # Hints, no value/rank guarantee.
                "rarity_scope": "SEARCH_HINTS_NOT_VALUE_RANKING",
                "buy_keyword": market["buy"][0],
                "buy_keywords": list(market["buy"]),
                "exclude_keywords": ["-" + x for x in market["exclude"]],
                "box_keywords": list(market["box"]),
                "edition_keywords": list(market["edition"]),
                "lang": market["lang"],
                "currency": market["currency"],
                "declared_region": region in g["regions"] or "GLOBAL" in g["regions"],
                "source_evidence": "UNVERIFIED_SEARCH_DISCOVERY",
                "price_evidence": "NONE",
            }
        result[key] = market_configs
    return result


tcg_search_config = build_search_config()


def _term(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 100:
        raise ValueError("INVALID_SEARCH_TERM")
    token = value.strip()
    # Never allow an unreviewed input to inject X operators or search modifiers.
    if any(char in token for char in ("\n", "\r", "\t", '"', "(", ")", "#")) or ":" in token:
        raise ValueError("INVALID_SEARCH_OPERATOR")
    return f'"{token}"' if " " in token else token


def _or(values):
    if not values:
        raise ValueError("EMPTY_SEARCH_ALTERNATIVES")
    return "(" + " OR ".join(_term(x) for x in values) + ")" if len(values) > 1 else _term(values[0])


def generate_twitter_query(game_key, rarity=None, region="JP", *,
                           kind="card", images=True, restrict_language=False,
                           require_edition=False):
    """Return a safe manual X search query. No network, paid API or scraping.

    rarity=None: broad scan so games WITHOUT known rarity abbreviations are NOT omitted.
    rarity='ALL_HINTS': OR all available hint tokens; if none, falls back to broad scan.
    rarity='<one of game/region known hints>': require that known term.
    kind='box': sealed/BOX discovery, no card-only rarity filter.
    require_edition: require explicit edition text, can LOWER recall significantly.
    """
    if region not in LOCALES: raise ValueError("UNKNOWN_MARKET")
    if kind not in ("card", "box"): raise ValueError("UNKNOWN_KIND")
    if game_key not in tcg_search_config: raise KeyError(game_key)
    c = tcg_search_config[game_key][region]
    terms = [_term(c["hashtag"])]
    if kind == "box":
        if rarity is not None: raise ValueError("RARITY_NOT_APPLICABLE_TO_BOX_SEARCH")
        terms.append(_or(c["box_keywords"]))
    elif rarity == "ALL_HINTS":
        if c["top_rarities"]: terms.append(_or(c["top_rarities"]))
    elif rarity is not None:
        if rarity not in c["top_rarities"]: raise ValueError("UNVERIFIED_RARITY_HINT")
        terms.append(_term(rarity))
    terms.append(_or(c["buy_keywords"]))
    if require_edition: terms.append(_or(c["edition_keywords"]))
    terms.extend("-" + _term(x[1:]) for x in c["exclude_keywords"])
    if images: terms.append("filter:images")
    if restrict_language: terms.append("lang:" + c["lang"])
    return " ".join(terms)


def generate_twitter_url(game_key, rarity=None, region="JP", **kwargs):
    query = generate_twitter_query(game_key, rarity, region, **kwargs)
    return "https://x.com/search?" + urlencode({"q": query, "f": "live"})


def generate_search_plan(regions=LOCALES, *, kind="card", declared_only=True):
    """Search seeds for each game-market, with explicit availability uncertainty."""
    plan = []
    for game in _registry():
        for region in regions:
            if region not in LOCALES: raise ValueError("UNKNOWN_MARKET")
            entry = tcg_search_config[game["id"]][region]
            if declared_only and not entry["declared_region"]: continue
            plan.append({
                "game_id": game["id"], "game": game["label_ko"],
                "market": region, "declared_region": entry["declared_region"],
                "currency": entry["currency"], "data_status": "SEARCH_LEAD_ONLY",
                "price_kind": "STORE_BUY_OFFER_NOT_COMPLETED_SALE",
                "query": generate_twitter_query(game["id"], region=region, kind=kind),
                "url": generate_twitter_url(game["id"], region=region, kind=kind),
            })
    return plan


def main():
    ap = argparse.ArgumentParser(description="Free 30-game X store-buying-price search planner")
    ap.add_argument("--game", default="all", help="Registered game ID, or all")
    ap.add_argument("--region", choices=(*LOCALES,"ALL"), default="ALL")
    ap.add_argument("--kind", choices=("card","box"), default="card")
    ap.add_argument("--rarity", default=None, help="Known rarity hint or ALL_HINTS, single-game only")
    ap.add_argument("--all-markets", action="store_true",
                    help="Include undeclared countries as discovery-only, never as verified local editions")
    ap.add_argument("--language-filter", action="store_true", help="X lang: may miss mixed-language posts")
    ap.add_argument("--edition-filter", action="store_true", help="Edition terms may miss otherwise valid offers")
    ap.add_argument("--no-images", action="store_true")
    args = ap.parse_args()
    regions = LOCALES if args.region == "ALL" else (args.region,)
    try:
        if args.game == "all":
            if args.rarity: ap.error("--rarity requires a single --game")
            rows = generate_search_plan(regions,kind=args.kind,declared_only=not args.all_markets)
        else:
            if args.game not in tcg_search_config: ap.error("Unknown game ID")
            rows = []
            for region in regions:
                c = tcg_search_config[args.game][region]
                if not c["declared_region"] and not args.all_markets: continue
                kw = dict(region=region,kind=args.kind,images=not args.no_images,
                          restrict_language=args.language_filter,require_edition=args.edition_filter)
                rows.append({"game_id":args.game,"market":region,
                             "declared_region":c["declared_region"],
                             "price_kind":"STORE_BUY_OFFER_NOT_COMPLETED_SALE",
                             "query":generate_twitter_query(args.game,args.rarity,**kw),
                             "url":generate_twitter_url(args.game,args.rarity,**kw)})
        print(json.dumps({"game_count":len(tcg_search_config),"scope_count":len(rows),
                          "note":"Search leads only; no X API requests, no store price fact asserted",
                          "results":rows},ensure_ascii=False,indent=2))
        return 0
    except (ValueError,KeyError,OSError,json.JSONDecodeError) as exc:
        ap.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
