#!/usr/bin/env python3
"""Cross-collector meta learner for TCG public-data discovery.

Purpose
- Learn collection *coverage and diversity*, not truth or grading labels.
- Read existing runtime outputs from event/search/social/stock/market/graded-photo
  collectors without deleting or merging their dedicated learning memories.
- Track game x region x topic coverage, unique/duplicate/fresh/stale ratios,
  official/cross-check/image evidence, and source-family diversity.
- Recommend one under-covered game/region/topic focus for the next search cycle.

Safety
- A frequent fan/market/search source never becomes official from this learner.
- Official/trusted status remains controlled by the existing registries/verifiers.
- Public data only; no login/CAPTCHA/private-API bypass.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
import urllib.parse
from pathlib import Path

from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
MEMORY = ROOT / "collection_meta_learning.json"
BACKUP = ROOT / "collection_meta_learning.json.bak"
PROFILE = ROOT / "collection_meta_profile.json"
SCHEMA_VERSION = 1
MAX_CONTEXTS = 180
MAX_SOURCES = 180

INPUT_FILES = (
    "social_event_candidates.json",
    "web_discovery_candidates.json",
    "supplementary_candidates.json",
    "social_stock_signals.json",
    "purchase_signals.json",
    "releases.json",
    "market_prices.json",
    "market_watch.json",
    "graded_photo_candidates.json",
)

GAMES = {
    "포켓몬": ("포켓몬", "pokemon", "pokémon", "ポケモン"),
    "원피스": ("원피스", "one piece", "ワンピース"),
    "나루토": ("나루토", "naruto", "ナルト"),
}
REGIONS = ("KR", "JP", "US")
TOPICS = ("release", "reprint", "event", "tournament", "popup", "promo", "collab", "movie", "merch", "anniversary", "stock", "entry", "broadcast", "deadline", "status_update", "rules", "access", "results", "purchase_policy", "service_status", "market", "graded_photo")
SEARCH_TOPICS = ("release", "reprint", "event", "tournament", "popup", "promo", "collab", "movie", "merch", "anniversary", "stock", "entry", "broadcast", "deadline", "status_update", "rules", "access", "results", "purchase_policy", "service_status")
TOPIC_PRECEDENCE = (
    "graded_photo", "market", "service_status", "results", "purchase_policy", "status_update", "rules", "deadline", "access", "stock", "broadcast", "entry",
    "movie", "anniversary", "merch", "collab", "reprint", "release", "popup",
    "tournament", "promo", "event",
)

TOPIC_PATTERNS = {
    "graded_photo": re.compile(r"\bpsa(?:\s?\d{1,2})?\b|\bbgs(?:\s?\d{1,2}(?:\.\d)?)?\b|\bcgc(?:\s?\d{1,2}(?:\.\d)?)?\b|\btag(?:\s?\d{1,2})?\b|\bbrg(?:\s?\d{1,2})?\b|\bgraded\b|\bslab\b|등급\s*카드|감정\s*카드|鑑定", re.I),
    "market": re.compile(r"시세|가격|실거래|거래|판매가|price|sold|market|相場|落札|価格", re.I),
    "service_status": re.compile(r"점검|서비스\s*장애|접속\s*(?:장애|오류)|로그인\s*(?:불가|장애)|복구\s*완료|maintenance|service\s+(?:outage|unavailable|disruption)|login\s+(?:issue|failure|unavailable)|incident|resolved|メンテナンス|障害|不具合|ログインできない|利用できません|復旧", re.I),
    "results": re.compile(r"대회\s*결과|경기\s*결과|결과\s*발표|우승자\s*발표|입상자|최종\s*순위|우승\s*덱|상위\s*덱|tournament\s+results?|event\s+results?|match\s+results?|final\s+standings?|top\s+finishers?|winning\s+deck|champion\s+deck|大会結果|試合結果|結果発表|優勝者発表|入賞者|最終順位|優勝デッキ|上位デッキ", re.I),
    "purchase_policy": re.compile(r"추첨\s*판매|구매\s*제한|판매\s*제한|1인\s*\d+개|본인\s*인증.{0,20}(?:판매|구매)|구매권|구매\s*티켓|가상\s*대기열|lottery\s+sale|purchase\s+limit|sales?\s+limit|limited\s+to\s+(?:one|\d+)\s+items?\s+per\s+person|identity\s+verification.{0,30}(?:sale|purchase)|virtual\s+queue|purchase\s+(?:ticket|voucher)|抽選販売|購入制限|販売制限|お一人様\s*\d+点|本人認証.{0,20}(?:販売|購入)|購入券|購入チケット|仮想待機列", re.I),
    "status_update": re.compile(r"취소|연기|일정\s*변경|시간\s*변경|장소\s*변경|갱신내용|cancel(?:led|ed|ation)?|postpon(?:e|ed|ement)|reschedul(?:e|ed|ing)|schedule\s+change|venue\s+change|中止|延期|日程変更|時間変更|会場変更|内容変更", re.I),
    "deadline": re.compile(r"마감|신청\s*기한|응모\s*기한|접수\s*기한|신청기간|응모기간|접수기간|deadline|apply\s+by|registration\s+closes?|application\s+period|締切|期限|応募期間|申込期間|受付期間", re.I),
    "access": re.compile(r"참가\s*자격|참가조건|체크인|입장권|관람객|패스|정원|대기\s*명단|플레이어\s*ID|덱\s*리스트|참가비|eligib(?:le|ility)|check[- ]?in|waitlist|interest\s+list|spectator|admission|entry\s+fee|player\s+id|deck\s+list|seating|capacity|\bbadge\b|\bpass\b|参加資格|参加条件|チェックイン|入場券|観戦|パス|定員|キャンセル待ち|プレイヤーID|デッキリスト|参加費", re.I),
    "rules": re.compile(r"금지\s*/?\s*제한|금지카드|제한카드|금지\s*페어|에라타|사용\s*규정|룰|규칙|banned|restricted|restriction|errata|legality|legal\s+date|regulation|rulebook|floor\s+rules?|\brules?\b|禁止|制限|禁止カード|制限カード|禁止ペア|エラッタ|ルール|レギュレーション|使用可能", re.I),
    "stock": re.compile(r"재고|입고|재입고|품절|매진|자판기|in stock|restock|sold out|在庫|再入荷|売り切れ", re.I),
    "broadcast": re.compile(r"라이브|생방송|스트리밍|시청|twitch\s*drops?|live[ -]?stream|broadcast|streaming|redeem|ライブ配信|生配信|配信|視聴|ドロップ|コード", re.I),
    "entry": re.compile(r"응모|신청|접수|등록|추첨|당첨|엔트리|entry|application|registration|register|lottery|drawing|応募|申込|受付|登録|抽選|当選|エントリー", re.I),
    "movie": re.compile(r"영화|극장판|movie|film|cinema|映画|劇場版", re.I),
    "anniversary": re.compile(r"기념|주년|anniversary|commemorative|周年|記念", re.I),
    "merch": re.compile(r"굿즈|공식숍|점프샵|JUMP SHOP|merch|merchandise|official shop|グッズ|公式ショップ", re.I),
    "collab": re.compile(r"콜라보|협업|제휴|브랜드데이|collab|collaboration|partnership|コラボ|タイアップ", re.I),
    "reprint": re.compile(r"재발매|재판|복각|reprint|re-release|rerun|再販|再版|復刻", re.I),
    "release": re.compile(r"출시|발매|신탄|신제품|부스터|스타터|예약|재발매|release|launch|new set|booster|starter|preorder|reprint|発売|新弾|再販", re.I),
    "popup": re.compile(r"팝업|팝업스토어|박람회|전시회|pop[- ]?up|expo|convention|exhibition|ポップアップ|展示会", re.I),
    "tournament": re.compile(r"대회|리그|챔피언십|tournament|league|championship|regional|worlds|大会|リーグ|チャンピオンシップ", re.I),
    "promo": re.compile(r"프로모|증정|배포|특전|한정|promo|giveaway|distribution|exclusive|プロモ|配布|特典|限定", re.I),
    "event": re.compile(r"행사|이벤트|대회|팝업|페스타|체험회|event|tournament|pop[- ]?up|festival|イベント|大会|ポップアップ", re.I),
}

FOCUS_TERMS = {
    "KR": {
        "release": "출시 발매 신탄 신제품 부스터 스타터 예약 재발매",
        "reprint": "재발매 재판 복각 추가생산 재입고",
        "event": "행사 이벤트 대회 팝업 페스타 체험회",
        "tournament": "대회 리그 컵 챔피언십 월드챔피언십 매장대회",
        "popup": "팝업 팝업스토어 점프샵 JUMP SHOP 박람회 전시회 체험회 카드샵",
        "merch": "굿즈 공식숍 점프샵 JUMP SHOP 한정판매 특설매장 백화점",
        "anniversary": "기념 주년 기념전 전시 페어 축제",
        "promo": "프로모 프로모카드 증정 배포 특전 한정",
        "collab": "콜라보 협업 제휴 브랜드데이 카페 편의점 마트",
        "movie": "영화 극장판 개봉 특별상영",
        "stock": "재입고 입고 재고 품절 구매처",
        "entry": "응모 신청 접수 등록 추첨 당첨 LINE BANDAI TCG+",
        "broadcast": "라이브 생방송 스트리밍 시청 Twitch Drops 코드",
        "deadline": "마감 신청마감 응모마감 접수마감 신청기한 응모기한",
        "status_update": "변경 취소 연기 일정변경 시간변경 장소변경 갱신내용",
        "rules": "룰 규칙 금지 제한 금지페어 에라타 사용규정 레귤레이션",
        "access": "참가자격 체크인 입장권 관람객 패스 정원 대기명단 플레이어ID 덱리스트 참가비 RK9 PLAYGO",
        "results": "대회결과 경기결과 결과발표 우승자발표 입상자 최종순위 우승덱 상위덱",
        "purchase_policy": "추첨판매 구매제한 판매제한 1인1개 본인인증 구매권 구매티켓 가상대기열",
        "service_status": "점검 서비스장애 접속장애 접속오류 로그인불가 복구완료",
    },
    "JP": {
        "release": "発売 新弾 新商品 ブースター スターター 予約 再販",
        "reprint": "再販 再版 復刻 追加生産 再入荷",
        "event": "イベント 大会 ポップアップ フェス 体験会",
        "tournament": "大会 リーグ カップ チャンピオンシップ 店舗大会",
        "popup": "ポップアップ ポップアップストア フェス 展示会 体験会",
        "promo": "プロモ プロモカード 配布 特典 限定 キャンペーン",
        "collab": "コラボ タイアップ カフェ コンビニ",
        "movie": "映画 劇場版 上映",
        "merch": "グッズ 公式ショップ ジャンプショップ 限定販売 百貨店",
        "anniversary": "記念 周年 記念展 フェア 祭典",
        "stock": "再入荷 入荷 在庫 売り切れ 販売店舗",
        "entry": "応募 申込 受付 登録 抽選 当選 LINE BANDAI TCG+",
        "broadcast": "ライブ配信 生配信 配信 視聴 Twitch ドロップ コード",
        "deadline": "締切 期限 応募期間 申込期間 受付期間",
        "status_update": "変更 中止 延期 日程変更 時間変更 会場変更",
        "rules": "ルール 禁止 制限 禁止カード 制限カード エラッタ レギュレーション 使用可能",
        "access": "参加資格 チェックイン 入場券 観戦 パス 定員 キャンセル待ち プレイヤーID デッキリスト 参加費",
        "results": "大会結果 試合結果 結果発表 優勝者発表 入賞者 最終順位 優勝デッキ 上位デッキ",
        "purchase_policy": "抽選販売 購入制限 販売制限 お一人様1点 本人認証 購入券 購入チケット 仮想待機列",
        "service_status": "メンテナンス 障害 不具合 ログインできない 利用できません 復旧",
    },
    "US": {
        "release": "release new set booster starter preorder reprint",
        "reprint": "reprint re-release restock additional print rerun",
        "event": "event tournament pop-up festival demo championship",
        "tournament": "tournament league cup championship regional worlds store battle",
        "popup": "pop-up popup store festival expo convention exhibition demo",
        "promo": "promo promo card giveaway distribution exclusive",
        "collab": "collab collaboration partnership cafe retailer",
        "movie": "movie film cinema screening",
        "merch": "merch merchandise official shop limited store",
        "anniversary": "anniversary celebration commemorative exhibition fair",
        "stock": "restock in stock sold out retailer availability",
        "entry": "entry application registration lottery LINE BANDAI TCG+",
        "broadcast": "livestream broadcast streaming Twitch Drops reward code",
        "deadline": "deadline apply by registration closes application period",
        "status_update": "change cancelled canceled postponed rescheduled schedule change venue change",
        "rules": "rules banned restricted restriction errata legality legal date regulation rulebook",
        "access": "eligibility check-in spectator pass badge waitlist interest list player ID deck list entry fee capacity RK9",
        "results": "tournament results event results match results final standings top finishers winning deck champion deck",
        "purchase_policy": "lottery sale purchase limit sales limit one item per person identity verification virtual queue purchase ticket voucher",
        "service_status": "maintenance service outage unavailable disruption login issue incident resolved",
    },
}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _int(value, default=0, low=0, high=100_000_000) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError, OverflowError):
        return default


def _float(value, default=0.0, low=-1_000_000.0, high=1_000_000.0) -> float:
    try:
        number = float(value)
        if not math.isfinite(number):
            return default
        return max(low, min(high, number))
    except (TypeError, ValueError, OverflowError):
        return default


def _read_json(path: Path) -> object:
    try:
        return json.loads(safe_read_text(path))
    except Exception:
        return None


def _fresh() -> dict:
    return {"version": SCHEMA_VERSION, "updated_at": None, "runs": 0, "contexts": {}, "sources": {}}


def _load() -> dict:
    for path in (MEMORY, BACKUP):
        data = _read_json(path)
        if isinstance(data, dict) and isinstance(data.get("contexts"), dict):
            data.setdefault("sources", {})
            data.setdefault("runs", 0)
            return data
    return _fresh()


def _norm(text: object) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip().lower()
    return value[:600]


def _host(url: object) -> str:
    try:
        return (urllib.parse.urlsplit(str(url or "")).hostname or "").lower()
    except ValueError:
        return ""


def _game(row: dict) -> str | None:
    hay = _norm(f"{row.get('game','')} {row.get('title','')} {row.get('name_ko','')} {row.get('name_native','')} {row.get('product','')}")
    for game, aliases in GAMES.items():
        if any(alias.lower() in hay for alias in aliases):
            return game
    raw = str(row.get("game") or "").lower()
    if raw == "pokemon": return "포켓몬"
    if raw in {"onepiece", "one_piece"}: return "원피스"
    if raw == "naruto": return "나루토"
    return None


def _region(row: dict) -> str:
    raw = str(row.get("region") or row.get("country") or "").upper()
    if raw in REGIONS:
        return raw
    hay = _norm(f"{row.get('location','')} {row.get('source','')} {row.get('url','')}")
    if re.search(r"한국|korea|\.kr\b", hay, re.I): return "KR"
    if re.search(r"일본|japan|\.jp\b", hay, re.I): return "JP"
    if re.search(r"미국|usa|united states|\.com\b", hay, re.I): return "US"
    return "KR"


def classify_topic(row: dict, origin: str = "") -> str:
    """Classify collection coverage without letting broad event words hide rare topics."""
    explicit = str(row.get("category") or row.get("purpose") or "").lower()
    aliases = {"collaboration": "collab", "graded": "graded_photo", "price": "market"}
    explicit = aliases.get(explicit, explicit)
    if explicit in TOPICS:
        return explicit
    if "graded_photo" in origin: return "graded_photo"
    if "market" in origin: return "market"
    if "stock" in origin or "purchase" in origin: return "stock"
    if "release" in origin: return "release"
    text = _norm(" ".join(str(row.get(k) or "") for k in ("title", "name_ko", "name_native", "product", "summary", "excerpt", "status")))
    for name in TOPIC_PRECEDENCE:
        if TOPIC_PATTERNS[name].search(text):
            return name
    return "event"


# Backward-compatible private name used by existing diagnostics/tests.
_topic = classify_topic


def _source_name(row: dict, origin: str) -> str:
    for key in ("search_method", "search_provider", "source_kind", "provider", "source_platform", "source_market", "market", "source_label"):
        value = str(row.get(key) or "").strip()
        if value:
            return value[:100]
    host = _host(row.get("source") or row.get("url") or row.get("source_url"))
    return (host or origin)[:100]


def _signature(row: dict) -> str:
    url = str(row.get("source") or row.get("url") or row.get("source_url") or "")
    canonical_url = re.sub(r"[#?].*$", "", url).rstrip("/").lower()
    title = _norm(row.get("title") or row.get("name_ko") or row.get("name_native") or row.get("product"))
    base = canonical_url or title
    return hashlib.sha1(base.encode("utf-8", "ignore")).hexdigest()[:20]


def _parse_time(value: object) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", text):
            return dt.datetime.fromisoformat(text + "T00:00:00+00:00")
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except ValueError:
        return None


def _freshness(row: dict) -> tuple[bool, bool]:
    now = dt.datetime.now(dt.timezone.utc)
    stamps = []
    for key in ("published_at", "observed_at", "collected_at", "updated_at", "start_date"):
        stamp = _parse_time(row.get(key))
        if stamp:
            stamps.append(stamp)
    dates = row.get("dates") if isinstance(row.get("dates"), list) else []
    for value in dates[:4]:
        stamp = _parse_time(value)
        if stamp:
            stamps.append(stamp)
    if not stamps:
        return False, False
    newest = max(stamps)
    age = (now - newest).total_seconds() / 86400.0
    if age <= 60:
        return True, False
    if age > 180:
        return False, True
    return False, False


def _official(row: dict) -> bool:
    return bool(row.get("verified") is True or row.get("official_domain_match") is True or row.get("official_account_verified") is True or str(row.get("source_grade") or "").lower() == "official")


def _cross(row: dict) -> bool:
    return bool(row.get("cross_checked") is True or _int(row.get("independent_source_count")) >= 2 or row.get("verification_source"))


def _has_image(row: dict) -> bool:
    return any(str(row.get(k) or "").startswith("http") for k in ("image_url", "image", "thumbnail", "photo_url"))


def _extract_rows(data: object, origin: str) -> list[dict]:
    rows: list[dict] = []
    if isinstance(data, list):
        return [dict(x, _meta_origin=origin) for x in data if isinstance(x, dict)]
    if not isinstance(data, dict):
        return rows
    for key in ("items", "results", "candidates", "rows", "entries", "watch"):
        value = data.get(key)
        if isinstance(value, list):
            rows.extend(dict(x, _meta_origin=origin) for x in value if isinstance(x, dict))
        elif isinstance(value, dict):
            rows.extend(dict(x, _meta_origin=origin) for x in value.values() if isinstance(x, dict))
    queries = data.get("queries")
    if isinstance(queries, list):
        for block in queries:
            if not isinstance(block, dict): continue
            keyword = block.get("keyword")
            for item in block.get("results") or []:
                if isinstance(item, dict):
                    row = dict(item, _meta_origin=origin)
                    row.setdefault("game", keyword)
                    rows.append(row)
    # Some data files are keyed maps without a wrapper field.
    if not rows and origin in {"market_prices.json", "releases.json"}:
        for value in data.values():
            if isinstance(value, dict):
                rows.append(dict(value, _meta_origin=origin))
            elif isinstance(value, list):
                rows.extend(dict(x, _meta_origin=origin) for x in value if isinstance(x, dict))
    return rows


def _collect_snapshot() -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    used = []
    for name in INPUT_FILES:
        path = ROOT / name
        if not path.exists():
            continue
        data = _read_json(path)
        part = _extract_rows(data, name)
        if part:
            rows.extend(part)
            used.append(name)
    return rows, used


def _context_score(stat: dict) -> float:
    items = max(0, _int(stat.get("items")))
    unique_ratio = _float(stat.get("unique_ratio"))
    fresh_ratio = _float(stat.get("fresh_ratio"))
    official_ratio = _float(stat.get("official_ratio"))
    cross_ratio = _float(stat.get("cross_ratio"))
    source_diversity = _int(stat.get("source_diversity"))
    stale_ratio = _float(stat.get("stale_ratio"))
    return round(
        min(2.0, items / 4.0)
        + unique_ratio * 1.5 + fresh_ratio * 1.1 + official_ratio * 1.0 + cross_ratio * 0.8
        + min(1.0, source_diversity * 0.18) - stale_ratio * 0.8,
        5,
    )


def refresh_profile() -> dict:
    memory = _load()
    memory["runs"] = _int(memory.get("runs")) + 1
    raw_rows, used_files = _collect_snapshot()
    grouped: dict[str, list[dict]] = {}
    source_groups: dict[str, list[dict]] = {}
    for row in raw_rows:
        game = _game(row)
        if not game:
            continue
        region = _region(row)
        origin = str(row.get("_meta_origin") or "")
        topic = _topic(row, origin)
        key = f"{game}|{region}|{topic}"
        grouped.setdefault(key, []).append(row)
        source_groups.setdefault(_source_name(row, origin), []).append(row)

    snapshot_contexts = []
    contexts = memory.setdefault("contexts", {})
    for game in GAMES:
        for region in REGIONS:
            for topic in TOPICS:
                key = f"{game}|{region}|{topic}"
                items = grouped.get(key, [])
                signatures = [_signature(x) for x in items]
                unique = len(set(signatures))
                total = len(items)
                fresh = stale = official = cross = images = 0
                sources = set()
                for row in items:
                    is_fresh, is_stale = _freshness(row)
                    fresh += 1 if is_fresh else 0
                    stale += 1 if is_stale else 0
                    official += 1 if _official(row) else 0
                    cross += 1 if _cross(row) else 0
                    images += 1 if _has_image(row) else 0
                    sources.add(_source_name(row, str(row.get("_meta_origin") or "")))
                sample = {
                    "items": total,
                    "unique": unique,
                    "duplicates": max(0, total - unique),
                    "unique_ratio": round(unique / max(1, total), 4),
                    "duplicate_ratio": round(max(0, total - unique) / max(1, total), 4),
                    "fresh": fresh,
                    "fresh_ratio": round(fresh / max(1, total), 4),
                    "stale": stale,
                    "stale_ratio": round(stale / max(1, total), 4),
                    "official": official,
                    "official_ratio": round(official / max(1, total), 4),
                    "cross_checked": cross,
                    "cross_ratio": round(cross / max(1, total), 4),
                    "images": images,
                    "image_ratio": round(images / max(1, total), 4),
                    "source_diversity": len(sources),
                }
                sample["score"] = _context_score(sample)
                old = contexts.setdefault(key, {})
                old["runs"] = _int(old.get("runs")) + 1
                for field in ("items", "unique", "duplicates", "fresh", "stale", "official", "cross_checked", "images", "source_diversity"):
                    old[field] = _int(sample[field])
                for field in ("unique_ratio", "duplicate_ratio", "fresh_ratio", "stale_ratio", "official_ratio", "cross_ratio", "image_ratio", "score"):
                    previous = _float(old.get("ema_" + field), sample[field])
                    old["ema_" + field] = round(previous * 0.72 + _float(sample[field]) * 0.28, 5)
                old["last_snapshot"] = _now()
                snapshot_contexts.append({"game": game, "region": region, "topic": topic, **sample, "ema_score": old.get("ema_score")})

    sources_memory = memory.setdefault("sources", {})
    snapshot_sources = []
    for source, items in source_groups.items():
        total = len(items)
        signatures = {_signature(x) for x in items}
        fresh = sum(1 for x in items if _freshness(x)[0])
        official = sum(1 for x in items if _official(x))
        cross = sum(1 for x in items if _cross(x))
        images = sum(1 for x in items if _has_image(x))
        games = len({_game(x) for x in items if _game(x)})
        regions = len({_region(x) for x in items})
        stat = {
            "items": total,
            "unique_ratio": round(len(signatures) / max(1, total), 4),
            "fresh_ratio": round(fresh / max(1, total), 4),
            "official_ratio": round(official / max(1, total), 4),
            "cross_ratio": round(cross / max(1, total), 4),
            "image_ratio": round(images / max(1, total), 4),
            "game_diversity": games,
            "region_diversity": regions,
        }
        utility = stat["unique_ratio"] * 1.5 + stat["fresh_ratio"] + stat["cross_ratio"] * 0.8 + min(0.8, games * 0.18 + regions * 0.12)
        stat["utility_score"] = round(utility, 5)
        old = sources_memory.setdefault(source[:100], {})
        old["runs"] = _int(old.get("runs")) + 1
        for field, value in stat.items():
            if field == "items":
                old[field] = value
            else:
                prior = _float(old.get("ema_" + field), value)
                old["ema_" + field] = round(prior * 0.72 + _float(value) * 0.28, 5)
        old["last_snapshot"] = _now()
        snapshot_sources.append({"source": source, **stat})

    # Keep memories bounded by recent usefulness.
    if len(contexts) > MAX_CONTEXTS:
        memory["contexts"] = dict(sorted(contexts.items(), key=lambda kv: _float(kv[1].get("ema_score")), reverse=True)[:MAX_CONTEXTS])
    if len(sources_memory) > MAX_SOURCES:
        memory["sources"] = dict(sorted(sources_memory.items(), key=lambda kv: _float(kv[1].get("ema_utility_score")), reverse=True)[:MAX_SOURCES])

    # Highest gap = low current/EMA score among search-relevant topics. Always keep
    # all games/regions eligible so a popular franchise cannot starve another one.
    recommendations = []
    for row in snapshot_contexts:
        if row["topic"] not in SEARCH_TOPICS:
            continue
        gap = max(0.0, 4.2 - _float(row.get("score")))
        if row["items"] == 0:
            gap += 1.8
        if row["fresh_ratio"] < 0.35:
            gap += 0.7
        if row["source_diversity"] < 2:
            gap += 0.5
        recommendations.append({**row, "gap_score": round(gap, 4)})
    recommendations.sort(key=lambda x: (x["gap_score"], -x["items"]), reverse=True)

    memory["version"] = SCHEMA_VERSION
    memory["updated_at"] = _now()
    if MEMORY.exists():
        try:
            previous = _read_json(MEMORY)
            if isinstance(previous, dict):
                atomic_write_json(BACKUP, previous, suffix=".meta.bak.tmp")
        except Exception:
            pass
    atomic_write_json(MEMORY, memory, suffix=".meta.tmp")

    snapshot_sources.sort(key=lambda x: (x["utility_score"], x["items"]), reverse=True)
    profile = {
        "version": SCHEMA_VERSION,
        "updated_at": _now(),
        "runs": memory["runs"],
        "input_files": used_files,
        "row_count": len(raw_rows),
        "policy": "다양성/커버리지 수집전략만 학습. 반복 발견이나 팬/시장 출처 빈도로 공식성·사실성·등급정답을 자동승격하지 않음.",
        "learned_values": [
            "items", "unique", "duplicates", "unique_ratio", "duplicate_ratio",
            "fresh", "fresh_ratio", "stale", "stale_ratio", "official", "official_ratio",
            "cross_checked", "cross_ratio", "images", "image_ratio", "source_diversity",
            "game_diversity", "region_diversity", "coverage_gap",
        ],
        "coverage": snapshot_contexts,
        "top_gaps": recommendations[:30],
        "top_sources": snapshot_sources[:40],
    }
    atomic_write_json(PROFILE, profile, suffix=".meta-profile.tmp")
    return profile


def recommended_focus(game: str) -> dict | None:
    canonical = None
    text = _norm(game)
    for name, aliases in GAMES.items():
        if name in text or any(alias.lower() in text for alias in aliases):
            canonical = name
            break
    if not canonical:
        return None
    profile = _read_json(PROFILE)
    if not isinstance(profile, dict):
        return None
    rows = [x for x in profile.get("top_gaps", []) if isinstance(x, dict) and x.get("game") == canonical and x.get("topic") in SEARCH_TOPICS]
    # ``top_gaps`` is deliberately bounded.  When many empty cells tie, a plain
    # global slice can contain only the games encountered first and make another
    # game (typically Naruto) return no recommendation.  Fall back to the full
    # bounded coverage matrix for that requested game; trust/evidence scores are
    # unchanged and this affects collection priority only.
    if not rows:
        rows = [dict(x) for x in profile.get("coverage", [])
                if isinstance(x,dict) and x.get("game") == canonical and x.get("topic") in SEARCH_TOPICS]
        for row in rows:
            gap=max(0.0,4.2-_float(row.get("score")))
            if _int(row.get("items")) == 0: gap += 1.8
            if _float(row.get("fresh_ratio")) < 0.35: gap += 0.7
            if _int(row.get("source_diversity")) < 2: gap += 0.5
            row["gap_score"]=round(gap,4)
        rows.sort(key=lambda x:(x.get("gap_score",0),-_int(x.get("items"))),reverse=True)
    if not rows:
        return None
    row = dict(rows[0])
    region = str(row.get("region") or "KR")
    topic = str(row.get("topic") or "event")
    row["terms"] = FOCUS_TERMS.get(region, FOCUS_TERMS["KR"]).get(topic, FOCUS_TERMS.get(region, FOCUS_TERMS["KR"])["event"])
    return row


if __name__ == "__main__":
    print(json.dumps(refresh_profile(), ensure_ascii=False, indent=2))
