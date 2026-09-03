#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"{label}: marker not found")
    return text.replace(old, new, 1)


def sub_once(text: str, pattern: str, replacement: str, label: str) -> str:
    out, count = re.subn(pattern, lambda _m: replacement, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"{label}: regex marker count={count}")
    return out


def patch_provider_health() -> None:
    path = "provider_health_learning.py"
    text = read(path)
    text = replace_once(
        text,
        'TOPICS = ("event", "tournament", "popup", "promo", "collab", "movie", "release", "reprint", "merch", "anniversary")',
        'TOPICS = ("event", "tournament", "popup", "promo", "collab", "movie", "release", "reprint", "merch", "anniversary", "stock", "entry", "broadcast")',
        "health topics",
    )
    rules = '''_TOPIC_RULES = (
    ("movie", re.compile(r"영화|극장판|개봉|movie|film|cinema|映画|劇場版|上映", re.I)),
    ("broadcast", re.compile(r"라이브|생방송|방송|스트리밍|시청|twitch\\s*drops?|live[ -]?stream|broadcast|streaming|watch\\s+live|redeem|redemption|ライブ配信|生配信|配信|視聴|Twitch|ドロップ|コード|シリアルコード", re.I)),
    ("anniversary", re.compile(r"기념|주년|anniversary|周年|記念", re.I)),
    ("merch", re.compile(r"굿즈|점프샵|JUMP SHOP|official shop|merch|グッズ|ショップ", re.I)),
    ("popup", re.compile(r"팝업|pop[- ]?up|ポップアップ", re.I)),
    ("entry", re.compile(r"응모|신청|접수|등록|추첨|당첨|엔트리|사전신청|entry|application|apply|registration|register|lottery|drawing|sign[- ]?up|応募|申込|申し込み|受付|登録|抽選|当選|エントリー|事前応募", re.I)),
    ("tournament", re.compile(r"대회|리그|championship|tournament|大会|リーグ|battle|배틀", re.I)),
    ("stock", re.compile(r"재입고|입고|재고|품절|구매처|restock|in stock|sold out|availability|retailer|再入荷|入荷|在庫|売り切れ|販売店舗", re.I)),
    ("reprint", re.compile(r"재발매|재판|재출시|추가생산|복각|reprint|re-release|additional print|rerun|再販|再版|復刻|追加生産", re.I)),
    ("release", re.compile(r"신제품|신탄|부스터|스타터|출시|발매|release|new set|booster|starter|発売|新商品|新弾", re.I)),
    ("promo", re.compile(r"프로모|증정|배포|특전|캠페인|promo|giveaway|distribution|campaign|キャンペーン|配布|特典|プレゼント", re.I)),
    ("collab", re.compile(r"콜라보|협업|collab|collaboration|partnership|コラボ|タイアップ", re.I)),
)'''
    text = sub_once(text, r"_TOPIC_RULES = \(.*?\n\)\n\n\ndef _now", rules + "\n\n\ndef _now", "health topic rules")
    text = text.replace('"version": 2', '"version": 3')
    priority = '''        topic = key.rsplit("/", 1)[-1]
        urgency = {"entry": 3.0, "broadcast": 3.0, "stock": 2.0}.get(topic, 0.0)
        priority = round(
            miss_streak * 4.0
            + verification_gap_streak * 2.0
            + discovery_gap_streak
            + min(3.0, _num(stat.get("misses")) * 0.08)
            + urgency,
            3,
        )
        rows.append'''
    text = sub_once(
        text,
        r"        priority = round\(\n.*?\n        \)\n        rows\.append",
        priority,
        "health priority",
    )
    write(path, text)


def patch_routes() -> None:
    path = "multi_route_event_discovery.py"
    text = read(path)
    for old, new in (
        (
            '        "stock": "재입고 입고 판매 자판기 재고 품절 구매처",',
            '        "stock": "재입고 입고 판매 자판기 재고 품절 구매처",\n        "entry": "응모 신청 접수 등록 추첨 당첨 참가신청 사전신청 엔트리",\n        "broadcast": "라이브 생방송 방송 스트리밍 시청 트위치 Twitch 드롭 드롭스 코드 교환 리딤",',
        ),
        (
            '        "stock": "再入荷 入荷 在庫 売り切れ 販売 店舗",',
            '        "stock": "再入荷 入荷 在庫 売り切れ 販売 店舗",\n        "entry": "応募 申込 申し込み 受付 登録 抽選 当選 エントリー 事前応募",\n        "broadcast": "ライブ ライブ配信 生配信 配信 視聴 Twitch ドロップ コード シリアルコード",',
        ),
        (
            '        "stock": "restock in stock sold out retailer store vending",',
            '        "stock": "restock in stock sold out retailer store vending",\n        "entry": "entry application apply registration register lottery drawing winner signup sign-up",\n        "broadcast": "livestream live stream broadcast streaming watch twitch drops reward code redeem redemption",',
        ),
    ):
        text = replace_once(text, old, new, "route query family")
    text = replace_once(
        text,
        'COVERAGE_TOPICS = ("event", "tournament", "popup", "promo", "collab", "movie", "release", "reprint", "merch", "anniversary")',
        'COVERAGE_TOPICS = ("event", "tournament", "popup", "promo", "collab", "movie", "release", "reprint", "merch", "anniversary", "stock", "entry", "broadcast")',
        "route coverage topics",
    )
    text = replace_once(
        text,
        'SOCIAL_DISCOVERY_HOSTS = ("x.com", "instagram.com", "youtube.com")',
        'SOCIAL_DISCOVERY_HOSTS = ("x.com", "instagram.com", "youtube.com", "tiktok.com", "twitch.tv", "facebook.com")',
        "route social hosts",
    )
    keyword_block = '''KEYWORD_RE = re.compile(
    r"행사|이벤트|대회|팝업|페스타|프로모|증정|배포|출시|발매|신탄|부스터|스타터|예약|재발매|재입고|입고|재고|품절|구매처|콜라보|협업|영화|극장판|굿즈|공식숍|점프샵|기념|주년|응모|신청|접수|등록|추첨|당첨|엔트리|라이브|생방송|방송|스트리밍|시청|코드|리딤|"
    r"イベント|大会|ポップアップ|プロモ|配布|発売|新弾|ブースター|スターター|予約|再販|再入荷|入荷|在庫|売り切れ|コラボ|映画|劇場版|グッズ|公式ショップ|記念|周年|応募|申込|受付|登録|抽選|当選|エントリー|ライブ配信|生配信|配信|視聴|ドロップ|コード|プレゼント|"
    r"event|tournament|pop[- ]?up|promo|giveaway|release|booster|starter|preorder|reprint|restock|in stock|sold out|availability|retailer|entry|application|apply|registration|register|lottery|drawing|signup|livestream|live stream|broadcast|streaming|watch|twitch drops|reward code|redeem|redemption|collab|movie|film|merch|official shop|anniversary|commemorative|collector|collection|unboxing|deck|decklist|review|price|"
    r"개봉|언박싱|덱|덱리스트|수집|컬렉터|카드샵|후기|시세|開封|デッキ|コレクター|コレクション|レビュー|相場",
    re.I,
)'''
    text = sub_once(text, r"KEYWORD_RE = re\.compile\(.*?\n\)\n\n\ndef _now", keyword_block + "\n\n\ndef _now", "route keyword filter")
    topic_func = '''def _topic(text: str) -> str:
    value = text or ""
    patterns = (
        ("movie", r"영화|극장판|개봉|관람특전|movie|film|cinema|screening|映画|劇場版|上映|入場者特典"),
        ("broadcast", r"라이브|생방송|방송|스트리밍|시청|twitch\\s*drops?|live[ -]?stream|broadcast|streaming|watch\\s+live|redeem|redemption|ライブ配信|生配信|配信|視聴|Twitch|ドロップ|コード|シリアルコード"),
        ("anniversary", r"기념|주년|기념전|anniversary|commemorative|周年|記念"),
        ("merch", r"굿즈|공식숍|공식샵|점프샵|JUMP SHOP|merch|merchandise|official shop|グッズ|公式ショップ"),
        ("collab", r"콜라보|협업|제휴|브랜드데이|collab|collaboration|partnership|コラボ|タイアップ"),
        ("entry", r"응모|신청|접수|등록|추첨|당첨|엔트리|사전신청|entry|application|apply|registration|register|lottery|drawing|sign[- ]?up|応募|申込|申し込み|受付|登録|抽選|当選|エントリー|事前応募"),
        ("stock", r"재입고|입고|재고|품절|구매처|restock|in stock|sold out|availability|retailer|再入荷|入荷|在庫|売り切れ|販売店舗"),
        ("reprint", r"재발매|재판|복각|추가생산|reprint|re-release|additional print|rerun|再販|再版|復刻|追加生産"),
        ("release", r"출시|발매|신탄|부스터|스타터|release|launch|new set|booster|starter|発売|新弾"),
        ("popup", r"팝업|팝업스토어|박람회|전시회|pop[- ]?up|expo|convention|exhibition|ポップアップ|展示会"),
        ("tournament", r"대회|리그|챔피언십|월드챔피언십|tournament|league|championship|regional|worlds|大会|リーグ|チャンピオンシップ"),
        ("promo", r"프로모|증정|배포|특전|한정|캠페인|promo|giveaway|distribution|exclusive|campaign|プロモ|配布|特典|限定|キャンペーン|プレゼント"),
    )
    for topic, pattern in patterns:
        if re.search(pattern, value, re.I):
            return topic
    return "event"'''
    text = sub_once(text, r"def _topic\(text: str\) -> str:.*?\n\ndef _official_for", topic_func + "\n\n\ndef _official_for", "route topic classifier")
    write(path, text)


def patch_multichannel() -> None:
    path = "multi_channel_agent.py"
    text = read(path)
    event_or = '''    EVENT_OR = {
        "KR": ("행사", "이벤트", "챌린지", "도전", "개최", "콜라보", "프로모", "프로모카드", "출시", "발매", "재발매", "재입고", "재고", "품절", "한정", "증정", "배포", "특전", "응모", "신청", "등록", "추첨", "당첨", "라이브", "생방송", "스트리밍", "시청", "코드", "대회", "영화"),
        "JP": ("イベント", "チャレンジ", "開催", "コラボ", "プロモ", "プロモカード", "発売", "再販", "再入荷", "在庫", "売り切れ", "限定", "配布", "特典", "応募", "申込", "登録", "抽選", "当選", "ライブ配信", "生配信", "視聴", "コード", "大会", "映画"),
        "US": ("event", "challenge", "special mission", "distribution", "collab", "collaboration", "promo", "promo card", "release", "reprint", "restock", "in stock", "sold out", "exclusive", "giveaway", "entry", "application", "registration", "lottery", "livestream", "broadcast", "streaming", "twitch drops", "redeem", "code", "tournament", "movie"),
    }'''
    text = sub_once(text, r"    EVENT_OR = \{.*?\n    \}\n    GOOGLE_LOCALE", event_or + "\n    GOOGLE_LOCALE", "multi-channel vocab")
    write(path, text)


def patch_social() -> None:
    path = "social_event_discovery.py"
    text = read(path)
    event_terms = '''EVENT_TERMS = {
    "ko": "행사 이벤트 챌린지 도전 개최 특전 배포 콜라보 프로모 팝업 팝업스토어 점프샵 JUMP SHOP 슈에이샤 신세계 영화 극장판 개봉 예약 발매 출시 재발매 재입고 재고 품절 대회 응모 신청 등록 추첨 당첨 라이브 생방송 스트리밍 시청 트위치 드롭 코드 리딤 야구 KBO 굿즈 포토카드 브랜드데이 PLAYGO 재배포 재지급 수령 프로모션팩 신사황",
    "ja": "イベント チャレンジ 開催 特典 配布 コラボ キャンペーン プロモ ポップアップ 映画 劇場版 発売 再販 再入荷 在庫 売り切れ 大会 応募 申込 登録 抽選 当選 ライブ配信 生配信 視聴 Twitch ドロップ コード グッズ カード",
    "en": "event challenge special mission collaboration collab promo distribution giveaway pop-up movie film release reprint restock in-stock sold-out tournament preorder entry application registration lottery livestream broadcast streaming twitch drops redeem code merchandise card tiktok facebook",
}'''
    text = sub_once(text, r"EVENT_TERMS = \{.*?\n\}\nFAN_TERMS", event_terms + "\nFAN_TERMS", "social event terms")
    category = '''CATEGORY_PATTERNS = (
    ("movie", re.compile(r"영화|극장판|개봉|movie|film|cinema|劇場版|映画|上映|netflix", re.I)),
    ("collaboration", re.compile(r"콜라보|협업|브랜드데이|야구|kbo|wiz|giants|collab|collaboration|コラボ|タイアップ|popup|pop-up|ポップアップ", re.I)),
    ("promo", re.compile(r"프로모|증정|이벤트|행사|대회|배틀|예약|발매|출시|재입고|재고|품절|응모|신청|등록|추첨|당첨|라이브|생방송|스트리밍|시청|코드|포토카드|promo|event|campaign|tournament|battle|release|preorder|restock|sold out|entry|application|registration|lottery|livestream|broadcast|streaming|twitch drops|redeem|code|キャンペーン|イベント|大会|発売|予約|再入荷|在庫|売り切れ|応募|申込|登録|抽選|当選|ライブ配信|生配信|配信|視聴|ドロップ|コード|プレゼント", re.I)),
)'''
    text = sub_once(text, r"CATEGORY_PATTERNS = \(.*?\n\)\nDATE_RE", category + "\nDATE_RE", "social category filter")
    hosts = '''SOCIAL_HOSTS = {
    "x.com", "www.x.com", "twitter.com", "www.twitter.com",
    "instagram.com", "www.instagram.com",
    "youtube.com", "www.youtube.com", "youtu.be",
    "tiktok.com", "www.tiktok.com",
    "twitch.tv", "www.twitch.tv",
    "facebook.com", "www.facebook.com", "m.facebook.com",
}'''
    text = sub_once(text, r"SOCIAL_HOSTS = \{.*?\n\}\nGOOGLE_NEWS_HOSTS", hosts + "\nGOOGLE_NEWS_HOSTS", "social hosts")
    parser = '''def _parse_social_link(link: str) -> tuple[str, str] | None:
    try:
        parsed = urllib.parse.urlsplit(link)
    except ValueError:
        return None
    host = (parsed.hostname or "").lower(); path = parsed.path.strip("/")
    if host in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
        user = path.split("/", 1)[0]
        if user and user.lower() not in {"home", "search", "share", "intent", "i"} and re.fullmatch(r"[A-Za-z0-9_]{1,15}", user): return "x", user
    if host in {"instagram.com", "www.instagram.com"}:
        user = path.split("/", 1)[0]
        if user and user.lower() not in {"p", "reel", "explore", "stories"} and re.fullmatch(r"[A-Za-z0-9_.]{1,30}", user): return "instagram", user
    if host in {"facebook.com", "www.facebook.com", "m.facebook.com"}:
        user = path.split("/", 1)[0]
        if user and user.lower() not in {"share", "sharer", "plugins", "watch", "reel", "groups", "events", "login"} and re.fullmatch(r"[A-Za-z0-9_.-]{2,80}", user): return "facebook", user
    if host in {"youtube.com", "www.youtube.com"}:
        if path.startswith("channel/UC"): return "youtube_channel", path.split("/", 1)[1]
        if path.startswith("@"): return "youtube_handle", path.split("/", 1)[0]
    if host in {"tiktok.com", "www.tiktok.com"}:
        user = path.split("/", 1)[0].lstrip("@")
        if user and re.fullmatch(r"[A-Za-z0-9_.]{2,30}", user): return "tiktok", user
    if host in {"twitch.tv", "www.twitch.tv"}:
        user = path.split("/", 1)[0]
        if user and user.lower() not in {"directory", "downloads", "jobs", "p", "videos"} and re.fullmatch(r"[A-Za-z0-9_]{2,30}", user): return "twitch", user
    return None'''
    text = sub_once(text, r"def _parse_social_link\(link: str\).*?\n\ndef _fetch_official_page", parser + "\n\n\ndef _fetch_official_page", "social parser")
    text = replace_once(
        text,
        '                   "platforms": ["x", "instagram", "youtube", "tiktok", "twitch"],',
        '                   "platforms": ["x", "instagram", "youtube", "tiktok", "twitch", "facebook"],',
        "social registry platforms",
    )
    game_query = '''def _game_query_terms(game: str, region: str) -> str:
    lang = REGION_LANG[region]["lang"]; names = GAMES[game][lang]
    name_expr = " OR ".join(f'"{name}"' if " " in name else name for name in names[:3])
    event_words = {
        "ko": "(행사 OR 이벤트 OR 챌린지 OR 콜라보 OR 프로모 OR 영화 OR 극장판 OR 발매 OR 출시 OR 재발매 OR 재입고 OR 재고 OR 품절 OR 응모 OR 신청 OR 등록 OR 추첨 OR 당첨 OR 라이브 OR 생방송 OR 스트리밍 OR 시청 OR 코드 OR 대회 OR 야구 OR 굿즈 OR 포토카드 OR PLAYGO OR 재배포 OR 재지급 OR 수령 OR 프로모션팩 OR 신사황)",
        "ja": "(イベント OR チャレンジ OR コラボ OR キャンペーン OR プロモ OR 映画 OR 劇場版 OR 発売 OR 再販 OR 再入荷 OR 在庫 OR 売り切れ OR 応募 OR 申込 OR 登録 OR 抽選 OR 当選 OR ライブ配信 OR 生配信 OR 配信 OR 視聴 OR コード OR 大会 OR グッズ)",
        "en": "(event OR challenge OR collab OR collaboration OR promo OR movie OR film OR release OR reprint OR restock OR in-stock OR sold-out OR entry OR application OR registration OR lottery OR livestream OR broadcast OR streaming OR twitch OR drops OR redeem OR code OR tournament OR merchandise)",
    }[lang]
    return f"({name_expr}) {event_words} lang:{lang} -is:retweet"'''
    text = sub_once(text, r"def _game_query_terms\(game: str, region: str\) -> str:.*?\n\ndef _x_request", game_query + "\n\n\ndef _x_request", "x query vocabulary")
    text = replace_once(
        text,
        '    query = f"({base_expr}) (site:x.com OR site:instagram.com OR site:youtube.com OR site:tiktok.com OR site:twitch.tv)"',
        '    query = f"({base_expr}) (site:x.com OR site:instagram.com OR site:youtube.com OR site:tiktok.com OR site:twitch.tv OR site:facebook.com)"',
        "public social query",
    )
    kind_block = '''            host = _host(source)
            if "x.com" in host or "twitter.com" in host:
                kind = "x"
            elif "instagram.com" in host:
                kind = "instagram"
            elif "tiktok.com" in host:
                kind = "tiktok"
            elif "twitch.tv" in host:
                kind = "twitch"
            elif "facebook.com" in host:
                kind = "facebook"
            else:
                kind = "youtube"'''
    text = sub_once(
        text,
        r"            host = _host\(source\)\n            if \"x\.com\" in host or \"twitter\.com\" in host:.*?\n            else:\n                kind = \"youtube\"",
        kind_block,
        "public social kind",
    )
    text = replace_once(
        text,
        '                          "status": "무키 공개검색 · 공식 SNS + 팬/컬렉터/크리에이터 X/Instagram/YouTube/TikTok/Twitch 후보"}',
        '                          "status": "무키 공개검색 · 공식 SNS + 팬/컬렉터/크리에이터 X/Instagram/YouTube/TikTok/Twitch/Facebook 후보"}',
        "social status",
    )
    write(path, text)


def patch_pipeline() -> None:
    path = "auto_pipeline_runner.py"
    text = read(path)
    text = replace_once(
        text,
        '    "twitch.tv": "twitch_public_search", "www.twitch.tv": "twitch_public_search",\n}',
        '    "twitch.tv": "twitch_public_search", "www.twitch.tv": "twitch_public_search",\n    "facebook.com": "facebook_public_search", "www.facebook.com": "facebook_public_search", "m.facebook.com": "facebook_public_search",\n}',
        "pipeline social host map",
    )
    write(path, text)


def patch_guard() -> None:
    path = ".github/workflows/provider-source-gap-learning-guard.yml"
    text = read(path)
    marker = "      - 'test_extended_discovery_channels_v5.py'\n      - '.github/workflows/provider-source-gap-learning-guard.yml'"
    text = text.replace(marker, "      - 'test_extended_discovery_channels_v5.py'\n      - 'test_source_gap_taxonomy_v6.py'\n      - '.github/workflows/provider-source-gap-learning-guard.yml'")
    text = replace_once(
        text,
        "            test_extended_discovery_channels_v5.py\n",
        "            test_extended_discovery_channels_v5.py \\\n            test_source_gap_taxonomy_v6.py\n",
        "guard compile list",
    )
    if "Verify stock entry broadcast and Facebook gap taxonomy" not in text:
        text += "\n      - name: Verify stock entry broadcast and Facebook gap taxonomy\n        run: python -m unittest -v test_source_gap_taxonomy_v6.py\n"
    write(path, text)


def main() -> None:
    patch_provider_health()
    patch_routes()
    patch_multichannel()
    patch_social()
    patch_pipeline()
    patch_guard()
    print("v6 source-gap patch applied")


if __name__ == "__main__":
    main()
