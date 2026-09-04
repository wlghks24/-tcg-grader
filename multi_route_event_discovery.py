#!/usr/bin/env python3
"""Independent no-key discovery routes for Pokemon / ONE PIECE / NARUTO.

This module intentionally overlaps *providers*, not trust levels:
- Bing RSS broad discovery
- Bing official-domain scoped discovery
- Bing partner/retail scoped discovery
- direct official-site anchor scanning
- DuckDuckGo HTML fallback when Bing is unavailable or too sparse

All output is candidate/reference data. A search hit never becomes official merely
because it mentions an official brand; official_domain_match is based on the final
result host only. The caller still performs canonical promotion/verification.
"""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import email.utils
import html
import os
import re
import shlex
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

from event_gap_learning import EventGapLearner
from safe_runtime import env_int, safe_urlopen, validate_public_https_url

TIMEOUT = env_int("TCG_HTTP_TIMEOUT", 20, 5, 60)
SOURCE_TIMEOUT = max(5, min(12, TIMEOUT))
MAX_PER_QUERY = env_int("TCG_ROUTE_MAX_PER_QUERY", 8, 3, 15)
BING_HOSTS = {"www.bing.com", "bing.com"}
DDG_HOSTS = {"html.duckduckgo.com", "duckduckgo.com", "www.duckduckgo.com"}

GAMES = {
    "포켓몬 카드": {
        "ko": ("포켓몬 카드", "포켓몬카드", "포켓몬"),
        "ja": ("ポケモンカード", "ポケカ", "ポケモン"),
        "en": ("Pokemon TCG", "Pokemon cards", "Pokémon"),
    },
    "원피스 카드": {
        "ko": ("원피스 카드", "원피스카드", "원피스"),
        "ja": ("ワンピースカード", "ワンピカード", "ONE PIECE"),
        "en": ("One Piece Card Game", "ONE PIECE cards"),
    },
    "나루토 카드": {
        "ko": ("나루토 카드", "나루토 카드게임", "나루토"),
        "ja": ("NARUTO CARD GAME", "ナルト カード", "NARUTO"),
        "en": ("NARUTO CARD GAME", "Naruto cards"),
    },
}
REGIONS = {"KR": "ko", "JP": "ja", "US": "en"}

QUERY_FAMILIES = {
    "ko": {
        "release": "출시 발매 신제품 신탄 부스터 스타터 예약 재발매 재판",
        "event": "행사 이벤트 챌린지 도전 개최 대회 팝업 페스타 체험회 매장대회 월드챔피언십",
        "tournament": "대회 리그 컵 챔피언십 월드챔피언십 매장대회 배틀",
        "popup": "팝업 팝업스토어 점프샵 \"JUMP SHOP\" 슈에이샤 신세계 페스타 박람회 전시회 체험회 카드샵",
        "promo": "프로모 증정 배포 한정 수령 특전 캠페인 프로모션팩",
        "collab": "콜라보 협업 제휴 브랜드데이 야구 카페 편의점 마트",
        "movie": "영화 극장판 개봉 특별상영 시사회 관람특전 영화특전",
        "reprint": "재발매 재판 재출시 추가생산 재입고 복각",
        "merch": "굿즈 공식숍 공식샵 점프샵 \"JUMP SHOP\" 한정판매 예약판매 특설매장 백화점",
        "anniversary": "기념 주년 기념전 전시 페어 축제 생일 anniversary",
        "stock": "재입고 입고 판매 자판기 재고 품절 구매처",
        "entry": "응모 신청 접수 등록 추첨 당첨 참가신청 사전신청 엔트리 LINE BANDAI TCG+ TCG+",
        "broadcast": "라이브 생방송 방송 스트리밍 시청 트위치 Twitch 드롭 드롭스 코드 교환 리딤",
        "deadline": "마감 신청마감 응모마감 접수마감 신청기한 응모기한 접수기한 신청기간",
        "status_update": "변경 취소 연기 일정변경 시간변경 장소변경 갱신내용",
        "rules": "룰 규칙 금지 제한 금지카드 제한카드 금지페어 에라타 사용규정 레귤레이션",
        "access": "참가자격 참가조건 체크인 입장권 관람객 패스 정원 대기명단 플레이어ID 덱리스트 참가비 RK9 PLAYGO",
        "results": "대회결과 경기결과 결과발표 우승자발표 입상자 최종순위 우승덱 상위덱",
        "purchase_policy": "추첨판매 구매제한 판매제한 1인1개 본인인증 구매권 구매티켓 가상대기열",
        "service_status": "점검 서비스장애 접속장애 접속오류 로그인불가 복구완료",
        "official_price": "가격개정 가격변경 가격인상 가격인하 희망소비자가격 변경",
        "product_issue": "봉입오류 내용물누락 제품불량 제조불량 인쇄오류 가공오류 교환대응 회수 리콜",
        "authenticity_notice": "위조품 가품 모조품 복제품 레플리카 비정규카드 오리파 서치팩 서치박스 사기주의",
    },
    "ja": {
        "release": "発売 新商品 新弾 ブースター スターター 予約 再販",
        "event": "イベント チャレンジ 開催 大会 ポップアップ フェス 体験会 店舗大会",
        "tournament": "大会 リーグ カップ チャンピオンシップ 店舗大会 バトル",
        "popup": "ポップアップ ポップアップストア フェス 展示会 体験会 カードショップ",
        "promo": "プロモ 配布 特典 限定 キャンペーン プレゼント",
        "collab": "コラボ タイアップ カフェ コンビニ ブランド 野球",
        "movie": "映画 劇場版 公開 上映 試写会 入場者特典 映画特典",
        "reprint": "再販 再版 復刻 追加生産 再入荷",
        "merch": "グッズ 公式ショップ ジャンプショップ 限定販売 予約販売 百貨店",
        "anniversary": "記念 周年 記念展 フェア 祭典 anniversary",
        "stock": "再入荷 入荷 在庫 売り切れ 販売 店舗",
        "entry": "応募 申込 申し込み 受付 登録 抽選 当選 エントリー 事前応募 LINE BANDAI TCG+ TCG+",
        "broadcast": "ライブ ライブ配信 生配信 配信 視聴 Twitch ドロップ コード シリアルコード",
        "deadline": "締切 期限 応募期間 申込期間 受付期間 締め切り",
        "status_update": "変更 中止 延期 日程変更 時間変更 会場変更 内容変更",
        "rules": "ルール 禁止 制限 禁止カード 制限カード 禁止ペア エラッタ レギュレーション 使用可能",
        "access": "参加資格 参加条件 チェックイン 入場券 観戦 パス 定員 キャンセル待ち プレイヤーID デッキリスト 参加費 RK9",
        "results": "大会結果 試合結果 結果発表 優勝者発表 入賞者 最終順位 優勝デッキ 上位デッキ",
        "purchase_policy": "抽選販売 購入制限 販売制限 お一人様1点 本人認証 購入券 購入チケット 仮想待機列",
        "service_status": "メンテナンス 障害 不具合 ログインできない 利用できません 復旧",
        "official_price": "価格改定 価格変更 値上げ 値下げ 希望小売価格改定",
        "product_issue": "封入内容の誤り 表面加工の誤り イラストの誤り 製造不良 交換対応 回収 リコール",
        "authenticity_notice": "偽造品 模倣品 偽物 レプリカ 非正規カード オリパ サーチ済み",
    },
    "en": {
        "release": "release new set booster starter preorder reprint",
        "event": "event challenge special mission tournament pop-up festival demo store championship",
        "tournament": "tournament league cup championship regional worlds store battle",
        "popup": "pop-up popup store festival expo convention exhibition demo card shop",
        "promo": "promo promotional card giveaway distribution exclusive campaign",
        "collab": "collaboration collab cafe retailer partnership brand baseball",
        "movie": "movie film cinema screening premiere theatrical bonus admission promo",
        "reprint": "reprint re-release restock additional print rerun",
        "merch": "merch merchandise official shop limited store department store",
        "anniversary": "anniversary celebration commemorative exhibition fair festival",
        "stock": "restock in stock sold out retailer store vending",
        "entry": "entry application apply registration register lottery drawing winner signup sign-up LINE BANDAI TCG+ TCG+",
        "broadcast": "livestream live stream broadcast streaming watch twitch drops reward code redeem redemption",
        "deadline": "deadline apply-by registration-closes application-period entry-period closing-date",
        "status_update": "change cancelled canceled postponed rescheduled schedule-change time-change venue-change location-change",
        "rules": "rules banned restricted restriction errata legality legal-date regulation rulebook floor-rules",
        "access": "eligibility check-in spectator pass badge waitlist interest-list player-ID deck-list entry-fee capacity RK9 PLAYGO",
        "results": "tournament-results event-results match-results final-standings top-finishers winning-deck champion-deck",
        "purchase_policy": "lottery-sale purchase-limit sales-limit one-item-per-person identity-verification virtual-queue purchase-ticket purchase-voucher",
        "service_status": "maintenance service-outage service-unavailable disruption login-issue incident resolved",
        "official_price": "price-revision price-change price-increase price-decrease MSRP-update RRP-update",
        "product_issue": "manufacturing-error printing-error packaging-error incorrect-contents missing-contents defective-product product-replacement exchange-program product-recall",
        "authenticity_notice": "counterfeit fake-cards replica knockoff unauthorized-reproduction searched-packs repacked scam-warning",
    },
}

COVERAGE_TOPICS = ("event", "tournament", "popup", "promo", "collab", "movie", "release", "reprint", "merch", "anniversary", "stock", "entry", "broadcast", "deadline", "status_update", "rules", "access", "results", "purchase_policy", "service_status", "official_price", "product_issue", "authenticity_notice")

OFFICIAL_ROUTES = {
    ("포켓몬 카드", "KR"): (
        "https://pokemoncard.co.kr/card/category/info1",
        "https://www.pokemonkorea.co.kr/",
    ),
    ("포켓몬 카드", "JP"): (
        "https://www.pokemon-card.com/info/",
        "https://www.pokemon-card.com/products/",
        "https://players.pokemon-card.com/",
        "https://www.30th.pokemon-card.com/event",
        "https://www.pokemon.co.jp/",
    ),
    ("포켓몬 카드", "US"): (
        "https://www.pokemon.com/us/pokemon-news",
        "https://www.pokemon.com/us/pokemon-tcg/",
        "https://play.pokemon.com/en-us/news/",
        "https://support.play.pokemon.com/hc/en-us",
        "https://community.pokemon.com/en-us/categories/news-announcements?sort=new",
        "https://www.pokemon.com/us/play-pokemon/pokemon-events/championship-series-event-results",
        "https://support.pokemon.com/hc/en-us",
        "https://support.pokemon.com/hc/en-us/categories/115000426053-Pok%C3%A9mon-Trading-Card-Game",
    ),
    ("원피스 카드", "KR"): (
        "https://onepiece-cardgame.kr/events.do",
        "https://onepiece-cardgame.kr/topics.do",
        "https://onepiece-cardgame.kr/products.do",
        "https://onepiece-cardgame.kr/rules.do",
    ),
    ("원피스 카드", "JP"): (
        "https://www.onepiece-cardgame.com/",
        "https://www.onepiece-cardgame.com/events/",
        "https://www.onepiece-cardgame.com/products/",
        "https://www.onepiece-cardgame.com/rules/",
        "https://one-piece.com/news/index.html",
    ),
    ("원피스 카드", "US"): (
        "https://en.onepiece-cardgame.com/",
        "https://en.onepiece-cardgame.com/events/",
        "https://en.onepiece-cardgame.com/products/",
        "https://en.onepiece-cardgame.com/rules/",
        "https://en.onepiece-cardgame.com/events/official-shop.html",
    ),
    ("나루토 카드", "KR"): (
        "https://www.naruto-cardgame.com/asia-en/",
        "https://www.naruto-cardgame.com/asia-en/news/article-list.php",
        "https://naruto-official.com/",
    ),
    ("나루토 카드", "JP"): (
        "https://naruto-official.com/",
        "https://www.naruto-cardgame.com/",
    ),
    ("나루토 카드", "US"): (
        "https://www.naruto-cardgame.com/en/",
        "https://www.naruto-cardgame.com/en/news/article-list.php",
        "https://naruto-official.com/en/",
    ),
}

# These are discovery-only domains. They do not get official_domain_match=True.
PARTNER_DOMAINS = {
    ("포켓몬 카드", "KR"): ("musinsa.com", "lotte.co.kr", "emart.ssg.com", "pokemon-go.com"),
    ("포켓몬 카드", "JP"): ("pokemoncenter-online.com", "pokemon.co.jp"),
    ("포켓몬 카드", "US"): ("pokemoncenter.com", "events.pokemon.com", "rk9.gg", "www.rk9.gg"),
    ("원피스 카드", "KR"): ("playgo.bandainamcokorea.co.kr", "ktwizstore.co.kr", "seoulmediacomics.com", "www.seoulmediacomics.com", "shinsegae.com", "www.shinsegae.com"),
    ("원피스 카드", "JP"): ("p-bandai.jp", "one-piece.com"),
    ("원피스 카드", "US"): ("bandai.com",),
    ("나루토 카드", "KR"): ("bandainamcokorea.co.kr", "seoulmediacomics.com", "www.seoulmediacomics.com", "shinsegae.com", "www.shinsegae.com"),
    ("나루토 카드", "JP"): ("bandai.co.jp",),
    ("나루토 카드", "US"): ("bandai.com",),
}

OFFICIAL_HOSTS = {
    urllib.parse.urlsplit(url).hostname.lower()
    for urls in OFFICIAL_ROUTES.values() for url in urls
    if urllib.parse.urlsplit(url).hostname
}
PARTNER_HOSTS = {host for hosts in PARTNER_DOMAINS.values() for host in hosts}
PRESS_DOMAINS = {
    "KR": ("newsis.com", "yna.co.kr", "newswire.co.kr", "blog.naver.com"),
    "JP": ("prtimes.jp", "atpress.ne.jp", "famitsu.com", "dengekionline.com"),
    "US": ("prnewswire.com", "businesswire.com", "globenewswire.com", "comicbook.com"),
}
PRESS_HOSTS = {host for hosts in PRESS_DOMAINS.values() for host in hosts}
SOCIAL_DISCOVERY_HOSTS = ("x.com", "instagram.com", "youtube.com", "tiktok.com", "twitch.tv", "facebook.com")
SERVICE_DISCOVERY_HOSTS = ("lin.ee", "line.me", "www.line.me", "bandai-tcg-plus.com", "www.bandai-tcg-plus.com", "rk9.gg", "www.rk9.gg", "playgo.bandainamcokorea.co.kr")
COMMUNITY_DISCOVERY_HOSTS = ("namu.wiki", "www.namu.wiki", "namu.moe", "www.namu.moe", "reddit.com", "www.reddit.com")

KEYWORD_RE = re.compile(
    r"가격개정|가격변경|가격인상|가격인하|희망소비자가격|봉입오류|내용물누락|제품불량|제조불량|인쇄오류|가공오류|교환대응|상품회수|리콜|위조품|가품|모조품|복제품|레플리카|비정규카드|오리파|서치팩|서치박스|사기주의|대회결과|경기결과|결과발표|우승자발표|입상자|최종순위|우승덱|상위덱|추첨판매|구매제한|판매제한|본인인증|구매권|구매티켓|가상대기열|점검|서비스장애|접속장애|접속오류|로그인불가|복구완료|행사|이벤트|대회|팝업|페스타|프로모|증정|배포|출시|발매|신탄|부스터|스타터|예약|재발매|재입고|입고|재고|품절|구매처|콜라보|협업|영화|극장판|굿즈|공식숍|점프샵|기념|주년|응모|신청|접수|등록|추첨|당첨|엔트리|라이브|생방송|방송|스트리밍|시청|코드|리딤|마감|기한|취소|연기|일정변경|시간변경|장소변경|갱신내용|룰|규칙|금지|제한|금지카드|제한카드|금지페어|에라타|체크인|참가자격|입장권|패스|대기명단|플레이어ID|덱리스트|RK9|PLAYGO|\bLINE\b|BANDAI\s*TCG\+|TCG\+|"
    r"価格改定|価格変更|値上げ|値下げ|希望小売価格|封入内容の誤り|表面加工の誤り|イラストの誤り|製造不良|交換対応|回収|リコール|偽造品|模倣品|偽物|レプリカ|非正規カード|オリパ|サーチ済み|大会結果|試合結果|結果発表|優勝者発表|入賞者|最終順位|優勝デッキ|上位デッキ|抽選販売|購入制限|販売制限|本人認証|購入券|購入チケット|仮想待機列|メンテナンス|障害|不具合|ログインできない|利用できません|復旧|イベント|大会|ポップアップ|プロモ|配布|発売|新弾|ブースター|スターター|予約|再販|再入荷|入荷|在庫|売り切れ|コラボ|映画|劇場版|グッズ|公式ショップ|記念|周年|応募|申込|受付|登録|抽選|当選|エントリー|ライブ配信|生配信|配信|視聴|ドロップ|コード|プレゼント|締切|期限|変更|中止|延期|日程変更|時間変更|会場変更|内容変更|ルール|禁止|制限|禁止カード|制限カード|エラッタ|チェックイン|参加資格|入場券|パス|キャンセル待ち|プレイヤーID|デッキリスト|RK9|\bLINE\b|BANDAI\s*TCG\+|TCG\+|"
    r"price revision|price change|price increase|price decrease|MSRP update|RRP update|manufacturing error|printing error|packaging error|incorrect contents?|missing contents?|defective product|product replacement|exchange program|product recall|counterfeit|fake cards?|replica|knockoff|unauthorized reproduction|searched? packs?|repacked|scam warning|tournament results?|event results?|match results?|final standings?|top finishers?|winning deck|champion deck|lottery sale|purchase limit|sales? limit|one item per person|identity verification|virtual queue|purchase ticket|purchase voucher|maintenance|service outage|service unavailable|login issue|incident|resolved|event|tournament|pop[- ]?up|promo|giveaway|release|booster|starter|preorder|reprint|restock|in stock|sold out|availability|retailer|entry|application|apply|registration|register|lottery|drawing|signup|livestream|live stream|broadcast|streaming|watch|twitch drops|reward code|redeem|redemption|deadline|apply by|registration closes?|application period|cancelled|canceled|postponed|rescheduled|schedule change|venue change|rules?|banned|restricted|restriction|errata|legality|check[- ]?in|eligibility|spectator|waitlist|interest list|player id|deck list|entry fee|\bbadge\b|\bpass\b|RK9|PLAYGO|\bLINE\b|BANDAI\s*TCG\+|TCG\+|collab|movie|film|merch|official shop|anniversary|commemorative|collector|collection|unboxing|deck|decklist|review|price|"
    r"개봉|언박싱|덱|덱리스트|수집|컬렉터|카드샵|후기|시세|開封|デッキ|コレクター|コレクション|レビュー|相場",
    re.I,
)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _short(value: object, limit: int = 320) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()[:limit]


def _host(url: str) -> str:
    try:
        return (urllib.parse.urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def _category(text: str) -> str:
    topic = _topic(text)
    if topic == "movie": return "movie"
    if topic == "collab": return "collaboration"
    return "promo"


def _topic(text: str) -> str:
    value = text or ""
    patterns = (
        ("authenticity_notice", r"위조\s*품|위조품|가품|모조품|복제품|레플리카|비정규\s*카드|짝퉁|오리파|서치\s*(?:팩|박스)|사기\s*주의|counterfeit|fake\s+(?:card|cards|booster|pack|packs|product|products)|replica|knockoff|unauthorized\s+(?:copy|reproduction)|searched?\s+(?:pack|packs|box|boxes)|repacked|scam\s+warning|偽造品|模倣品|偽物|レプリカ|非正規カード|オリパ|サーチ済み"),
        ("product_issue", r"봉입\s*(?:내용\s*)?오류|내용물\s*(?:누락|오류)|카드\s*(?:인쇄|가공|재단|일러스트)\s*(?:불량|오류)|제품\s*(?:불량|오류)|제조\s*불량|교환\s*대응|교환\s*안내|리콜|상품\s*회수|manufacturing\s+(?:error|defect)|printing\s+(?:error|defect)|packaging\s+(?:error|defect)|incorrect\s+contents?|missing\s+contents?|defective\s+product|damaged\s+(?:card|cards|part|parts).{0,30}replacement|product\s+replacement|exchange\s+program|product\s+recall|封入内容.{0,12}誤り|表面加工.{0,12}誤り|イラスト.{0,12}誤り|製造.{0,12}不良|商品.{0,12}(?:不良|不具合)|交換対応|交換案内|回収|リコール"),
        ("official_price", r"가격\s*(?:인상|인하|개정|변경|조정)|희망\s*소비자\s*가격.{0,12}(?:인상|인하|개정|변경|조정)|권장\s*소비자\s*가격.{0,12}(?:인상|인하|개정|변경|조정)|price\s+(?:revision|change|increase|decrease|adjustment|update)|MSRP.{0,12}(?:revision|change|increase|decrease|update)|RRP.{0,12}(?:revision|change|increase|decrease|update)|価格改定|価格変更|値上げ|値下げ|希望小売価格.{0,12}(?:改定|変更)"),
        ("service_status", r"점검|서비스\s*장애|접속\s*(?:장애|오류)|로그인\s*(?:불가|장애)|복구\s*완료|maintenance|service\s+(?:outage|unavailable|disruption)|login\s+(?:issue|failure|unavailable)|incident|resolved|メンテナンス|障害|不具合|ログインできない|利用できません|復旧"),
        ("results", r"대회\s*결과|경기\s*결과|결과\s*발표|우승자\s*발표|입상자|최종\s*순위|우승\s*덱|상위\s*덱|tournament\s+results?|event\s+results?|match\s+results?|final\s+standings?|top\s+finishers?|winning\s+deck|champion\s+deck|大会結果|試合結果|結果発表|優勝者発表|入賞者|最終順位|優勝デッキ|上位デッキ"),
        ("purchase_policy", r"추첨\s*판매|구매\s*제한|판매\s*제한|1인\s*\d+개|본인\s*인증.{0,20}(?:판매|구매)|구매권|구매\s*티켓|가상\s*대기열|lottery\s+sale|purchase\s+limit|sales?\s+limit|limited\s+to\s+(?:one|\d+)\s+items?\s+per\s+person|identity\s+verification.{0,30}(?:sale|purchase)|virtual\s+queue|purchase\s+(?:ticket|voucher)|抽選販売|購入制限|販売制限|お一人様\s*\d+点|本人認証.{0,20}(?:販売|購入)|購入券|購入チケット|仮想待機列"),
        ("status_update", r"취소|연기|일정\s*변경|시간\s*변경|장소\s*변경|갱신내용|cancel(?:led|ed|ation)?|postpon(?:e|ed|ement)|reschedul(?:e|ed|ing)|schedule\s+change|time\s+change|venue\s+change|location\s+change|中止|延期|日程変更|時間変更|会場変更|内容変更"),
        ("deadline", r"마감|신청\s*기한|응모\s*기한|접수\s*기한|신청기간|응모기간|접수기간|deadline|apply\s+by|registration\s+closes?|application\s+period|entry\s+period|closing\s+date|締切|期限|応募期間|申込期間|受付期間"),
        ("access", r"참가\s*자격|참가조건|체크인|입장권|관람객|패스|정원|대기\s*명단|플레이어\s*ID|덱\s*리스트|참가비|eligib(?:le|ility)|check[- ]?in|waitlist|interest\s+list|spectator|admission|entry\s+fee|player\s+id|deck\s+list|seating|capacity|\bbadge\b|\bpass\b|参加資格|参加条件|チェックイン|入場券|観戦|パス|定員|キャンセル待ち|プレイヤーID|デッキリスト|参加費"),
        ("rules", r"금지\s*/?\s*제한|금지카드|제한카드|금지\s*페어|에라타|사용\s*규정|룰|규칙|banned|restricted|restriction|errata|legality|legal\s+date|regulation|rulebook|floor\s+rules?|\brules?\b|禁止|制限|禁止カード|制限カード|禁止ペア|エラッタ|ルール|レギュレーション|使用可能"),
        ("movie", r"영화|극장판|개봉|관람특전|movie|film|cinema|screening|映画|劇場版|上映|入場者特典"),
        ("broadcast", r"라이브|생방송|방송|스트리밍|시청|twitch\s*drops?|live[ -]?stream|broadcast|streaming|watch\s+live|redeem|redemption|ライブ配信|生配信|配信|視聴|Twitch|ドロップ|コード|シリアルコード"),
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
    return "event"


def _official_for(game: str, region: str, host: str) -> bool:
    normalized = host.lower().removeprefix("www.")
    allowed = {_host(url).removeprefix("www.") for url in OFFICIAL_ROUTES.get((game, region), ())}
    return any(normalized == root or normalized.endswith("." + root) for root in allowed)


def _error_summary(label: str, exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        retry_after = str(exc.headers.get("Retry-After") or "").strip() if exc.headers else ""
        if exc.code == 429:
            cooldown = f"Retry-After={retry_after}" if retry_after else "Retry-After=미제공"
            return f"{label}: HTTP 429 · {cooldown} · cooldown-required"
        if exc.code == 403:
            return f"{label}: HTTP 403 · access-denied · no-bypass"
        return f"{label}: HTTP {exc.code}"
    return f"{label}: {type(exc).__name__}"


def _parse_pubdate(value: str | None) -> str | None:
    if not value: return None
    try:
        stamp = email.utils.parsedate_to_datetime(value)
        if stamp.tzinfo is None: stamp = stamp.replace(tzinfo=dt.timezone.utc)
        return stamp.astimezone(dt.timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OverflowError):
        return None


def _query(game: str, region: str, *, scoped_hosts: tuple[str, ...] = (), topic: str | None = None,
           extra_terms: tuple[str, ...] = ()) -> str:
    lang = REGIONS[region]
    names = GAMES[game][lang][:2]
    name_expr = " OR ".join(f'"{x}"' for x in names)
    families = QUERY_FAMILIES[lang]
    selected = {topic: families[topic]} if topic in families else families
    terms = " OR ".join(
        "(" + " OR ".join(f'\"{token}\"' if " " in token else token for token in shlex.split(value)) + ")"
        for value in selected.values()
    )
    learned = ""
    if extra_terms:
        learned = " OR (" + " OR ".join(f'\"{term}\"' if " " in term else term for term in extra_terms[:6]) + ")"
    site_expr = ""
    if scoped_hosts:
        site_expr = " (" + " OR ".join(f"site:{host}" for host in scoped_hosts[:8]) + ")"
    return f"({name_expr}) ({terms}{learned}){site_expr}"


def _bing_one(game: str, region: str, route: str, hosts: tuple[str, ...] = (), topic: str | None = None,
              extra_terms: tuple[str, ...] = ()) -> tuple[list[dict], str | None]:
    q = _query(game, region, scoped_hosts=hosts, topic=topic, extra_terms=extra_terms)
    url = "https://www.bing.com/search?" + urllib.parse.urlencode({"format": "rss", "q": q})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 TCG-Grader-RouteDiversity/1.0", "Accept": "application/rss+xml,application/xml,text/xml;q=0.9,*/*;q=0.5"})
    try:
        with safe_urlopen(req, timeout=SOURCE_TIMEOUT, allowed_hosts=BING_HOSTS) as response:
            raw = response.read(1_200_000)
        if b"<!ENTITY" in raw.upper():
            raise ValueError("XML entity expansion blocked")
        root = ET.fromstring(raw)
        rows = []
        for item in root.findall(".//item")[:MAX_PER_QUERY]:
            title = _short(item.findtext("title"), 220)
            link = _short(item.findtext("link"), 700)
            desc = _short(item.findtext("description"), 500)
            if not title or not link.startswith("https://") or not KEYWORD_RE.search(f"{title} {desc}"):
                continue
            try: validate_public_https_url(link)
            except (TypeError, ValueError): continue
            host = _host(link)
            official = _official_for(game, region, host)
            partner = host in set(PARTNER_DOMAINS.get((game, region), ()))
            press = host in set(PRESS_DOMAINS.get(region, ()))
            service = host in SERVICE_DISCOVERY_HOSTS
            community = host in COMMUNITY_DISCOVERY_HOSTS
            confidence = 0.91 if official else (0.73 if partner else 0.66 if service else 0.64 if press else 0.48 if community else 0.59)
            rows.append({
                "game": game, "region": region, "category": _category(f"{title} {desc}"),
                "topic": _topic(f"{title} {desc}"), "search_topic": topic or "broad",
                "title": title, "source": link, "source_kind": f"bing_{route}",
                "source_tier": "A-search" if official else ("C-community" if community else "B-service" if service else "B-news" if press else "B-search"),
                "source_label": "Bing RSS · 공식도메인" if official else ("Bing RSS · 나무위키/커뮤니티 발견층" if community else "Bing RSS · 공식 서비스 경로 공개검색" if service else "Bing RSS · 파트너/유통처" if partner else "Bing RSS · 보도/전문매체" if press else "Bing RSS · 공개웹"),
                "official_domain_match": official, "partner_domain_match": partner, "press_domain_match": press,
                "official_service_candidate": service, "community_discovery_only": community,
                "published_at": _parse_pubdate(item.findtext("pubDate")), "dates": [],
                "excerpt": desc or title, "status": "공식출처 검색후보" if official else ("커뮤니티 보조후보 · 공식 교차확인 필요" if community else "서비스 경로 후보 · 공식페이지 교차확인 필요" if service else "교차확인 후보"),
                "verified": official, "confidence": confidence,
                "route_family": f"{route}:{topic}" if topic else route,
                "collected_at": _now(),
            })
        return rows, None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError, ET.ParseError, UnicodeDecodeError) as exc:
        return [], _error_summary(f"Bing {route} {game}/{region}", exc)


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(); self.current_href = None; self.current_text = []; self.links = []
    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self.current_href = dict(attrs).get("href"); self.current_text = []
    def handle_data(self, data):
        if self.current_href is not None: self.current_text.append(data)
    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.current_href is not None:
            self.links.append((self.current_href, _short(" ".join(self.current_text), 220)))
            self.current_href = None; self.current_text = []


def _official_scan_one(game: str, region: str, url: str) -> tuple[list[dict], str | None]:
    try:
        validate_public_https_url(url, OFFICIAL_HOSTS)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 TCG-Grader-OfficialLinkScan/1.0"})
        with safe_urlopen(req, timeout=SOURCE_TIMEOUT, allowed_hosts=OFFICIAL_HOSTS) as response:
            final = response.geturl(); raw = response.read(1_000_000).decode("utf-8", "replace")
        parser = _AnchorParser(); parser.feed(raw); rows = []; seen = set()
        for href, text in parser.links:
            if not text or not KEYWORD_RE.search(text): continue
            target = urllib.parse.urljoin(final, href).split("#", 1)[0]
            host = _host(target)
            if not _official_for(game, region, host) or not target.startswith("https://"): continue
            try: validate_public_https_url(target, OFFICIAL_HOSTS)
            except (TypeError, ValueError): continue
            key = (target, text)
            if key in seen: continue
            seen.add(key)
            rows.append({
                "game": game, "region": region, "category": _category(text),
                "topic": _topic(text), "search_topic": _topic(text), "title": text,
                "source": target, "source_kind": "official_anchor_scan", "source_tier": "A-search",
                "source_label": "공식사이트 직접 링크 탐색", "official_domain_match": True,
                "published_at": None, "dates": [], "excerpt": text,
                "status": "공식사이트 링크 후보", "verified": True, "confidence": 0.94,
                "route_family": "official_anchor", "discovered_from": final, "collected_at": _now(),
            })
            if len(rows) >= MAX_PER_QUERY: break
        return rows, None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError, UnicodeDecodeError) as exc:
        return [], _error_summary(f"공식링크 {game}/{region}", exc)


def _decode_ddg(url: str) -> str | None:
    value = html.unescape(str(url or ""))
    if value.startswith("//"): value = "https:" + value
    if value.startswith("/"): value = "https://html.duckduckgo.com" + value
    try: parsed = urllib.parse.urlsplit(value)
    except ValueError: return None
    if (parsed.hostname or "").lower() in DDG_HOSTS:
        target = urllib.parse.parse_qs(parsed.query).get("uddg", [None])[0]
        if target: value = urllib.parse.unquote(target)
    return value if value.startswith("https://") else None


def _ddg_one(game: str, region: str, topic: str | None = None,
             extra_terms: tuple[str, ...] = ()) -> tuple[list[dict], str | None]:
    q = _query(game, region, topic=topic, extra_terms=extra_terms)
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": q})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 TCG-Grader-DDGFallback/1.0"})
    try:
        with safe_urlopen(req, timeout=SOURCE_TIMEOUT, allowed_hosts=DDG_HOSTS) as response:
            raw = response.read(900_000).decode("utf-8", "replace")
        rows = []
        for href, raw_title in re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', raw, re.I | re.S)[:MAX_PER_QUERY * 2]:
            link = _decode_ddg(href); title = _short(re.sub(r"<[^>]+>", " ", raw_title), 220)
            if not link or not title or not KEYWORD_RE.search(title): continue
            try: validate_public_https_url(link)
            except (TypeError, ValueError): continue
            host = _host(link)
            official = _official_for(game, region, host)
            partner = host in set(PARTNER_DOMAINS.get((game, region), ()))
            rows.append({
                "game": game, "region": region, "category": _category(title),
                "topic": _topic(title), "search_topic": topic or "broad", "title": title,
                "source": link, "source_kind": "ddg_general_fallback", "source_tier": "A-search" if official else "B-search",
                "source_label": "DuckDuckGo · 공식도메인" if official else "DuckDuckGo 공개검색 폴백",
                "official_domain_match": official, "partner_domain_match": partner,
                "published_at": None, "dates": [], "excerpt": title,
                "status": "공식출처 검색후보" if official else "검색 교차확인 후보",
                "verified": official, "confidence": 0.89 if official else 0.56,
                "route_family": f"ddg_fallback:{topic}" if topic else "ddg_fallback", "collected_at": _now(),
            })
            if len(rows) >= MAX_PER_QUERY: break
        return rows, None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError, UnicodeDecodeError) as exc:
        return [], _error_summary(f"DDG fallback {game}/{region}", exc)


def _topic_coverage(rows: list[dict], *, verified_only: bool = False) -> dict[str, int]:
    """Return game/region/topic coverage without letting discovery-only hits hide gaps.

    Candidate rows remain useful for cross-checking and are still reported separately,
    but only rows explicitly marked verified may resolve a learned coverage gap. This
    prevents a press/social/retail search hit from resetting miss_streak before an
    official-source result has actually been found.
    """
    return {
        f"{game}/{region}/{topic}": sum(
            1 for row in rows
            if isinstance(row, dict)
            and row.get("game") == game
            and row.get("region") == region
            and row.get("search_topic") == topic
            and (not verified_only or row.get("verified") is True)
        )
        for game in GAMES for region in REGIONS for topic in COVERAGE_TOPICS
    }


def collect_all() -> tuple[list[dict], list[str], dict]:
    """Collect candidates through independent routes with bounded concurrency."""
    learner = EventGapLearner()
    learned_verified = learner.learn_verified_file()
    jobs = []
    for game in GAMES:
        for region in REGIONS:
            official_hosts = tuple(dict.fromkeys(_host(u) for u in OFFICIAL_ROUTES.get((game, region), ()) if _host(u)))
            partner_hosts = tuple(PARTNER_DOMAINS.get((game, region), ()))
            for topic in COVERAGE_TOPICS:
                jobs.append(("bing_topic", _bing_one, (game, region, "topic", (), topic, learner.terms_for(game, region, topic))))
            jobs.append(("bing_social", _bing_one, (game, region, "social", SOCIAL_DISCOVERY_HOSTS)))
            jobs.append(("bing_service", _bing_one, (game, region, "service", SERVICE_DISCOVERY_HOSTS)))
            jobs.append(("bing_community", _bing_one, (game, region, "community", COMMUNITY_DISCOVERY_HOSTS)))
            if official_hosts: jobs.append(("bing_official", _bing_one, (game, region, "official", official_hosts)))
            if partner_hosts: jobs.append(("bing_partner", _bing_one, (game, region, "partner", partner_hosts)))
            press_hosts = tuple(PRESS_DOMAINS.get(region, ()))
            if press_hosts: jobs.append(("bing_press", _bing_one, (game, region, "press", press_hosts)))
            for url in OFFICIAL_ROUTES.get((game, region), ()):
                jobs.append(("official_anchor", _official_scan_one, (game, region, url)))

    rows = []; errors = []; by_route = {}; successes = 0
    is_android = 'com.termux' in os.environ.get('PREFIX', '') or 'ANDROID_ROOT' in os.environ
    workers = 2 if is_android else 5
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {pool.submit(fn, *args): route for route, fn, args in jobs}
        for future in concurrent.futures.as_completed(future_map):
            route = future_map[future]
            try:
                part, error = future.result()
            except Exception as exc:
                part, error = [], f"{route}: {type(exc).__name__}"
            stat = by_route.setdefault(route, {"queries": 0, "successes": 0, "results": 0, "errors": 0})
            stat["queries"] += 1
            if error:
                stat["errors"] += 1; errors.append(error)
            else:
                stat["successes"] += 1; successes += 1
            stat["results"] += len(part); rows.extend(part)

    # A broad provider can look healthy while still missing a low-volume subject.
    # Retry cells that still lack verified-source coverage through an independent
    # provider. Unverified candidates remain visible but never suppress gap retry.
    first_verified_topic_coverage = _topic_coverage(rows, verified_only=True)
    missing_topics = [key for key, count in first_verified_topic_coverage.items() if count == 0]
    if missing_topics:
        gap_limit = env_int("TCG_ROUTE_GAP_RETRY_LIMIT", 18, 0, len(missing_topics))
        fallback_jobs = [tuple(key.split("/", 2)) for key in learner.prioritize(missing_topics, gap_limit)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            future_map = {
                pool.submit(_ddg_one, g, r, topic, learner.terms_for(g, r, topic)): (g, r, topic)
                for g, r, topic in fallback_jobs
            }
            for future in concurrent.futures.as_completed(future_map):
                stat = by_route.setdefault("ddg_fallback", {"queries": 0, "successes": 0, "results": 0, "errors": 0})
                stat["queries"] += 1
                try: part, error = future.result()
                except Exception as exc: part, error = [], f"DDG fallback: {type(exc).__name__}"
                if error: stat["errors"] += 1; errors.append(error)
                else: stat["successes"] += 1; successes += 1
                stat["results"] += len(part); rows.extend(part)

    coverage = {}
    for game in GAMES:
        for region in REGIONS:
            key = f"{game}/{region}"
            coverage[key] = sum(1 for row in rows if row.get("game") == game and row.get("region") == region)
    topic_coverage = _topic_coverage(rows)
    verified_topic_coverage = _topic_coverage(rows, verified_only=True)
    # Only verified-source coverage changes the learner's hit/miss streak. Discovery
    # candidates can guide human/independent verification but cannot teach a gap as solved.
    learner.observe(verified_topic_coverage)
    learner.save()

    status = {
        "configured": True,
        "status": f"Bing RSS 작품×국가×{len(COVERAGE_TOPICS)}주제 독립검색 + 공식/서비스/파트너/보도/팬SNS/나무위키 커뮤니티 발견층 + 공식사이트 직접스캔 + 검증근거 기준 학습형 누락주제 DDG 폴백",
        "route_count": len(by_route),
        "query_count": sum(v.get("queries", 0) for v in by_route.values()),
        "success_query_count": successes,
        "result_count": len(rows),
        "error_count": len(errors),
        "by_route": by_route,
        "coverage": coverage,
        "topic_coverage": topic_coverage,
        "verified_topic_coverage": verified_topic_coverage,
        "expected_topic_cells": len(GAMES) * len(REGIONS) * len(COVERAGE_TOPICS),
        "covered_topic_cells": sum(1 for value in topic_coverage.values() if value > 0),
        "missing_topic_cells": [key for key, value in topic_coverage.items() if value == 0],
        "verified_covered_topic_cells": sum(1 for value in verified_topic_coverage.values() if value > 0),
        "verified_missing_topic_cells": [key for key, value in verified_topic_coverage.items() if value == 0],
        "gap_learning_coverage_basis": "verified-source-only",
        "gap_learning": learner.report(),
        "verified_events_learned_this_run": learned_verified,
    }
    return rows, errors[:60], status


if __name__ == "__main__":
    import json
    rows, errors, status = collect_all()
    print(json.dumps({"items": len(rows), "errors": len(errors), "status": status}, ensure_ascii=False))
