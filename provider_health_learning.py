#!/usr/bin/env python3
"""Persistent provider-health and verified coverage-gap learner.

This module learns two things only:
1. operational reliability/utility of discovery providers and social channels;
2. which Pokemon / ONE PIECE / NARUTO × KR/JP/US × topic cells still lack
   verified evidence.

It never changes source trust, never promotes community/search hits to official,
and never executes learned text. Candidate coverage and verified coverage are
stored separately so an X/Instagram/Google/Namuwiki hit cannot hide an unresolved
official-information gap.
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
MEMORY = ROOT / "collection_provider_health.json"
BACKUP = ROOT / "collection_provider_health.json.bak"
SOCIAL = ROOT / "social_event_candidates.json"
SUPPLEMENTARY = ROOT / "supplementary_candidates.json"
PROMO = ROOT / "promo_events.json"

MAX_PROVIDERS = 80
MAX_SOURCE_KINDS = 80
MAX_SOURCE_KINDS_PER_CELL = 12
GAMES = ("포켓몬 카드", "원피스 카드", "나루토 카드")
REGIONS = ("KR", "JP", "US")
TOPICS = ("event", "tournament", "popup", "promo", "collab", "movie", "release", "reprint", "merch", "anniversary", "stock", "entry", "broadcast", "deadline", "status_update", "rules", "access", "results", "purchase_policy", "service_status", "official_price", "product_issue", "authenticity_notice")
RECHECK_DAYS = {
    "service_status": 7, "status_update": 14, "stock": 14,
    "entry": 30, "deadline": 30, "access": 30, "purchase_policy": 30, "broadcast": 30,
    "event": 60, "tournament": 60, "popup": 60, "promo": 60, "collab": 60,
    "results": 90, "release": 120, "reprint": 120, "movie": 120, "merch": 120, "anniversary": 120,
    "official_price": 180, "product_issue": 180, "authenticity_notice": 180, "rules": 180,
}
GAME_ALIASES = {
    "포켓몬": "포켓몬 카드", "pokemon": "포켓몬 카드", "pokémon": "포켓몬 카드",
    "원피스": "원피스 카드", "one piece": "원피스 카드",
    "나루토": "나루토 카드", "naruto": "나루토 카드",
}

# Verified evidence may close multiple independently matched factual gaps.
# Broad umbrella categories remain primary-only to prevent one generic event page
# from falsely resolving unrelated coverage cells.
VERIFIED_MULTI_LABEL_TOPICS = frozenset({
    "authenticity_notice", "product_issue", "official_price", "service_status",
    "results", "purchase_policy", "status_update", "deadline", "access", "rules",
    "broadcast",
})

_TOPIC_RULES = (
    ("authenticity_notice", re.compile(r"위조\s*품|위조품|가품|모조품|복제품|레플리카|비정규\s*카드|짝퉁|오리파|서치\s*(?:팩|박스)|사기\s*주의|counterfeit|fake\s+(?:card|cards|booster|pack|packs|product|products)|replica|knockoff|unauthorized\s+(?:copy|reproduction)|searched?\s+(?:pack|packs|box|boxes)|repacked|scam\s+warning|偽造品|模倣品|偽物|レプリカ|非正規カード|オリパ|サーチ済み", re.I)),
    ("product_issue", re.compile(r"봉입\s*(?:내용\s*)?오류|내용물\s*(?:누락|오류)|카드\s*(?:인쇄|가공|재단|일러스트)\s*(?:불량|오류)|제품\s*(?:불량|오류)|제조\s*불량|교환\s*대응|교환\s*안내|리콜|상품\s*회수|manufacturing\s+(?:error|defect)|printing\s+(?:error|defect)|packaging\s+(?:error|defect)|incorrect\s+contents?|missing\s+contents?|defective\s+product|damaged\s+(?:card|cards|part|parts).{0,30}replacement|product\s+replacement|exchange\s+program|product\s+recall|封入内容.{0,12}誤り|表面加工.{0,12}誤り|イラスト.{0,12}誤り|製造.{0,12}不良|商品.{0,12}(?:不良|不具合)|交換対応|交換案内|回収|リコール", re.I)),
    ("official_price", re.compile(r"가격\s*(?:인상|인하|개정|변경|조정)|희망\s*소비자\s*가격.{0,12}(?:인상|인하|개정|변경|조정)|권장\s*소비자\s*가격.{0,12}(?:인상|인하|개정|변경|조정)|price\s+(?:revision|change|increase|decrease|adjustment|update)|MSRP.{0,12}(?:revision|change|increase|decrease|update)|RRP.{0,12}(?:revision|change|increase|decrease|update)|価格改定|価格変更|値上げ|値下げ|希望小売価格.{0,12}(?:改定|変更)", re.I)),
    ("service_status", re.compile(r"점검|서비스\s*장애|접속\s*(?:장애|오류)|로그인\s*(?:불가|장애)|복구\s*완료|maintenance|service\s+(?:outage|unavailable|disruption)|login\s+(?:issue|failure|unavailable)|incident|resolved|メンテナンス|障害|不具合|ログインできない|利用できません|復旧", re.I)),
    ("results", re.compile(r"대회\s*결과|경기\s*결과|결과\s*발표|우승자\s*발표|입상자|최종\s*순위|우승\s*덱|상위\s*덱|tournament\s+results?|event\s+results?|match\s+results?|final\s+standings?|top\s+finishers?|winning\s+deck|champion\s+deck|大会結果|試合結果|結果発表|優勝者発表|入賞者|最終順位|優勝デッキ|上位デッキ", re.I)),
    ("purchase_policy", re.compile(r"추첨\s*판매|구매\s*제한|판매\s*제한|1인\s*\d+개|본인\s*인증.{0,20}(?:판매|구매)|구매권|구매\s*티켓|가상\s*대기열|lottery\s+sale|purchase\s+limit|sales?\s+limit|limited\s+to\s+(?:one|\d+)\s+items?\s+per\s+person|identity\s+verification.{0,30}(?:sale|purchase)|virtual\s+queue|purchase\s+(?:ticket|voucher)|抽選販売|購入制限|販売制限|お一人様\s*\d+点|本人認証.{0,20}(?:販売|購入)|購入券|購入チケット|仮想待機列", re.I)),
    ("status_update", re.compile(r"취소|연기|일정\s*변경|시간\s*변경|장소\s*변경|변경\s*공지|갱신내용|cancel(?:led|ed|ation)?|postpon(?:e|ed|ement)|reschedul(?:e|ed|ing)|schedule\s+change|time\s+change|venue\s+change|location\s+change|中止|延期|日程変更|時間変更|会場変更|内容変更|変更のお知らせ", re.I)),
    ("deadline", re.compile(r"마감|신청\s*기한|응모\s*기한|접수\s*기한|신청기간|응모기간|접수기간|deadline|apply\s+by|registration\s+closes?|application\s+period|entry\s+period|entries\s+close|closing\s+date|締切|期限|応募期間|申込期間|受付期間|締め切り", re.I)),
    ("access", re.compile(r"참가\s*자격|참가조건|체크인|입장|관람객|관람권|입장권|패스|정원|대기\s*명단|현장\s*접수|플레이어\s*ID|선수\s*ID|덱\s*리스트|참가비|eligib(?:le|ility)|check[- ]?in|waitlist|interest\s+list|spectator|admission|entry\s+fee|player\s+id|deck\s+list|seating|capacity|\bbadge\b|\bpass\b|参加資格|参加条件|チェックイン|入場|観戦|入場券|パス|定員|キャンセル待ち|当日受付|プレイヤーID|デッキリスト|参加費", re.I)),
    ("rules", re.compile(r"금지\s*/?\s*제한|금지카드|제한카드|금지\s*페어|에라타|사용\s*규정|사용가능|룰|규칙|banned|restricted|restriction|errata|legality|legal\s+date|regulation|rulebook|floor\s+rules?|card\s+q&a|\brules?\b|禁止|制限|禁止カード|制限カード|禁止ペア|エラッタ|ルール|レギュレーション|使用可能|Q&A", re.I)),
    ("movie", re.compile(r"영화|극장판|개봉|movie|film|cinema|映画|劇場版|上映", re.I)),
    ("broadcast", re.compile(r"라이브|생방송|방송|스트리밍|시청|twitch\s*drops?|live[ -]?stream|broadcast|streaming|watch\s+live|redeem|redemption|ライブ配信|生配信|配信|視聴|Twitch|ドロップ|コード|シリアルコード", re.I)),
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
)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _fresh() -> dict:
    return {
        "version": 6,
        "providers": {},
        "coverage_cells": {},
        "source_kinds": {},
        "runs": 0,
        "updated_at": None,
    }


def _load(path: Path = MEMORY, backup_path: Path | None = None) -> dict:
    backup = backup_path or path.with_suffix(path.suffix + ".bak")
    for candidate in (path, backup):
        try:
            data = json.loads(safe_read_text(candidate))
            if isinstance(data, dict) and isinstance(data.get("providers"), dict):
                clean = _fresh()
                clean["runs"] = _num(data.get("runs"))
                clean["updated_at"] = data.get("updated_at")
                clean["providers"] = {
                    str(k)[:80]: dict(v)
                    for k, v in list(data.get("providers", {}).items())[:MAX_PROVIDERS]
                    if isinstance(v, dict)
                }
                clean["coverage_cells"] = {
                    str(k)[:120]: dict(v)
                    for k, v in list((data.get("coverage_cells") or {}).items())[: len(GAMES) * len(REGIONS) * len(TOPICS)]
                    if isinstance(v, dict)
                }
                clean["source_kinds"] = {
                    str(k)[:100]: dict(v)
                    for k, v in list((data.get("source_kinds") or {}).items())[:MAX_SOURCE_KINDS]
                    if isinstance(v, dict)
                }
                return clean
        except Exception:
            continue
    return _fresh()


def _num(value) -> int:
    try:
        return max(0, min(1_000_000, int(value)))
    except Exception:
        return 0


def _float(value) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else 0.0
    except Exception:
        return 0.0


def _host(url: object) -> str:
    try:
        return (urllib.parse.urlsplit(str(url or "")).hostname or "").lower()
    except ValueError:
        return ""


def _read_payload(path: Path) -> dict:
    try:
        data = json.loads(safe_read_text(Path(path)))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _topic_text(row: dict) -> str:
    return " ".join(
        str(row.get(key) or "")
        for key in (
            "category", "title", "excerpt", "name_ko", "name_native", "reward",
            "condition", "status", "source_label", "event_scope",
        )
    )


def _topic(row: dict) -> str:
    """Return the backward-compatible single primary topic."""
    explicit = str(row.get("search_topic") or row.get("topic") or "").strip().lower()
    if explicit in TOPICS:
        return explicit
    if row.get("event_scope") == "licensed_ip_popup_not_tcg_tournament":
        return "popup"
    text = _topic_text(row)
    for topic, pattern in _TOPIC_RULES:
        if pattern.search(text):
            return topic
    category = str(row.get("category") or "").lower()
    if category == "collaboration":
        return "collab"
    if category == "movie":
        return "movie"
    if category == "promo":
        return "promo"
    return "event"


def _topics(row: dict, *, verified: bool = False) -> tuple[str, ...]:
    """Return primary topic plus bounded concrete secondary facts for verified rows."""
    primary = _topic(row)
    if not verified:
        return (primary,)
    text = _topic_text(row)
    topics = [primary]
    for topic, pattern in _TOPIC_RULES:
        if topic == primary or topic not in VERIFIED_MULTI_LABEL_TOPICS:
            continue
        if pattern.search(text):
            topics.append(topic)
    return tuple(dict.fromkeys(topic for topic in topics if topic in TOPICS))


def _source_kind(row: dict, origin: str) -> str:
    value = str(row.get("source_kind") or row.get("search_provider") or "").strip().lower()
    if value:
        return value[:100]
    host = _host(row.get("source"))
    if origin == "promo":
        return f"official:{host or 'canonical'}"[:100]
    if origin == "supplementary":
        return f"supplementary:{host or str(row.get('source_tier') or 'unknown').lower()}"[:100]
    return f"{origin}:{host or 'unknown'}"[:100]


def _expected_keys() -> list[str]:
    return [f"{game}/{region}/{topic}" for game in GAMES for region in REGIONS for topic in TOPICS]


def _evidence_signature(row: dict) -> str:
    stable = {
        key: row.get(key)
        for key in (
            "source", "url", "title", "name_ko", "name_native", "status",
            "start_date", "end_date", "claim_deadline", "date_precision",
            "reward", "condition", "dates", "verification_source",
        )
        if row.get(key) not in (None, "", [], {})
    }
    raw = json.dumps(stable, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8", "ignore")).hexdigest()[:20]


def _fingerprint(signatures: object) -> str:
    values = sorted({str(x)[:40] for x in (signatures or []) if str(x).strip()})
    if not values:
        return ""
    return hashlib.sha1("|".join(values[:32]).encode("utf-8", "ignore")).hexdigest()[:20]


def _parse_iso(value: object) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except ValueError:
        return None


def _age_days(value: object) -> float | None:
    parsed = _parse_iso(value)
    if parsed is None:
        return None
    return max(0.0, (dt.datetime.now(dt.timezone.utc) - parsed).total_seconds() / 86400.0)


def _coverage_snapshot(social: dict, supplementary: dict, promo: dict) -> dict[str, dict]:
    snapshot = {
        key: {
            "candidate_count": 0,
            "verified_count": 0,
            "canonical_count": 0,
            "corroborated_count": 0,
            "verified_signatures": [],
            "source_kinds": {},
        }
        for key in _expected_keys()
    }
    sources = (
        ("social", social.get("items") or []),
        ("supplementary", supplementary.get("items") or []),
        ("promo", promo.get("items") or []),
    )
    for origin, rows in sources:
        for row in rows:
            if not isinstance(row, dict):
                continue
            game = str(row.get("game") or "")
            region = str(row.get("region") or "")
            if game not in GAMES or region not in REGIONS:
                continue
            verified = (
                str(row.get("source_grade") or "").lower() == "official"
                if origin == "promo"
                else row.get("verified") is True
            )
            topics = _topics(row, verified=verified)
            signature = _evidence_signature(row) if verified else ""
            kind = _source_kind(row, origin)
            corroborated = row.get("cross_checked") is True or _num(row.get("independent_source_count")) >= 2
            for topic in topics:
                if topic not in TOPICS:
                    continue
                key = f"{game}/{region}/{topic}"
                cell = snapshot[key]
                cell["candidate_count"] += 1
                if verified:
                    cell["verified_count"] += 1
                    if signature and signature not in cell["verified_signatures"] and len(cell["verified_signatures"]) < 32:
                        cell["verified_signatures"].append(signature)
                if origin == "promo" and verified:
                    cell["canonical_count"] += 1
                if corroborated:
                    cell["corroborated_count"] += 1
                kind_row = cell["source_kinds"].setdefault(kind, {"candidate": 0, "verified": 0})
                kind_row["candidate"] += 1
                kind_row["verified"] += 1 if verified else 0
    return snapshot


def _social_topic_coverage(items: list[dict], *, verified_only: bool) -> dict[str, int]:
    coverage = {key: 0 for key in _expected_keys()}
    for row in items:
        if not isinstance(row, dict):
            continue
        game = str(row.get("game") or "")
        region = str(row.get("region") or "")
        if game not in GAMES or region not in REGIONS:
            continue
        if verified_only and row.get("verified") is not True:
            continue
        topics = _topics(row, verified=verified_only)
        for topic in topics:
            key = f"{game}/{region}/{topic}"
            if key in coverage:
                coverage[key] += 1
    return coverage


def _harden_social_coverage(payload: dict, social_path: Path, *, rewrite: bool) -> dict:
    items = [row for row in (payload.get("items") or []) if isinstance(row, dict)]
    candidate = _social_topic_coverage(items, verified_only=False)
    verified = _social_topic_coverage(items, verified_only=True)
    hardened = dict(payload)
    hardened["candidate_topic_coverage"] = candidate
    hardened["verified_topic_coverage"] = verified
    # Backward-compatible consumers used topic_coverage as a gap-resolved signal.
    # Make that safety-sensitive field verified-only and retain raw discovery counts
    # under candidate_topic_coverage.
    hardened["topic_coverage"] = verified
    hardened["topic_coverage_basis"] = "verified-source-only"
    hardened["candidate_topic_covered_cells"] = sum(1 for value in candidate.values() if value > 0)
    hardened["verified_topic_covered_cells"] = sum(1 for value in verified.values() if value > 0)
    hardened["candidate_only_topic_cells"] = [
        key for key in _expected_keys() if candidate.get(key, 0) > 0 and verified.get(key, 0) == 0
    ]
    hardened["verified_topic_missing_cells"] = [
        key for key in _expected_keys() if verified.get(key, 0) == 0
    ]
    if rewrite and isinstance(payload.get("items"), list):
        atomic_write_json(Path(social_path), hardened, suffix=".verified-coverage.tmp")
    return {
        "candidate_covered_cells": hardened["candidate_topic_covered_cells"],
        "verified_covered_cells": hardened["verified_topic_covered_cells"],
        "candidate_only_cells": hardened["candidate_only_topic_cells"],
        "verified_missing_cells": hardened["verified_topic_missing_cells"],
        "basis": "verified-source-only",
        "verified_fact_basis": "verified-concrete-facts-multi-label; unverified-primary-only",
    }


def _supplementary_provider_rows(payload: dict) -> list[dict]:
    grouped: dict[str, dict] = {}
    for row in payload.get("items") or []:
        if not isinstance(row, dict):
            continue
        host = _host(row.get("source")) or str(row.get("source_tier") or "unknown").lower()
        name = f"supplementary:{host}"[:80]
        stat = grouped.setdefault(name, {"provider": name, "responded": False, "results": 0, "selected": 0, "errors": 0})
        if row.get("error") or str(row.get("status") or "").startswith("재확인 대기"):
            stat["errors"] += 1
        else:
            stat["responded"] = True
            stat["results"] += 1
    return list(grouped.values())


def _social_provider_rows(payload: dict) -> list[dict]:
    rows = []
    for name, status in (payload.get("channel_status") or {}).items():
        if not isinstance(status, dict):
            continue
        configured = status.get("configured")
        results = _num(status.get("result_count"))
        successes = _num(status.get("success_query_count"))
        errors = _num(status.get("error_count"))
        query_count = _num(status.get("query_count") or status.get("account_count"))
        responded = bool(results or successes or (configured is True and errors == 0 and query_count > 0))
        rows.append({
            "provider": f"social:{str(name)[:70]}",
            "configured": configured,
            "responded": responded,
            "results": results,
            "selected": 0,
            "errors": errors,
        })
    return rows


def _observe_provider_rows(data: dict, provider_rows: list[dict]) -> None:
    providers = data.setdefault("providers", {})
    for row in provider_rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("provider") or "unknown")[:80]
        stat = providers.setdefault(name, {})
        stat["runs"] = _num(stat.get("runs")) + 1
        if row.get("configured") is False:
            stat["unconfigured_runs"] = _num(stat.get("unconfigured_runs")) + 1
            stat["last_status"] = "not-configured"
            stat["last_seen"] = _now()
            continue
        responded = bool(row.get("responded", True))
        results = _num(row.get("results"))
        selected = _num(row.get("selected"))
        errors = _num(row.get("errors"))
        stat["responded"] = _num(stat.get("responded")) + (1 if responded else 0)
        stat["results"] = _num(stat.get("results")) + results
        stat["selected"] = _num(stat.get("selected")) + selected
        stat["errors"] = _num(stat.get("errors")) + errors
        stat["empty_streak"] = 0 if results else _num(stat.get("empty_streak")) + 1
        stat["error_streak"] = 0 if errors == 0 else _num(stat.get("error_streak")) + 1
        sample = (
            (1.0 if responded else -1.0)
            + min(2.0, results * 0.08)
            + min(1.5, selected * 0.15)
            - min(2.0, errors * 0.4)
        )
        old = _float(stat.get("score"))
        stat["score"] = round(old * 0.82 + sample * 0.18, 4)
        stat["last_status"] = "ok" if responded and errors == 0 else ("partial" if responded else "failed")
        stat["last_seen"] = _now()
    if len(providers) > MAX_PROVIDERS:
        ranked = sorted(providers.items(), key=lambda kv: _float(kv[1].get("score")), reverse=True)
        data["providers"] = dict(ranked[:MAX_PROVIDERS])


def _observe_coverage(data: dict, snapshot: dict[str, dict]) -> None:
    cells = data.setdefault("coverage_cells", {})
    global_kinds = data.setdefault("source_kinds", {})
    now = _now()
    for key in _expected_keys():
        current = snapshot.get(key) or {}
        candidate = _num(current.get("candidate_count"))
        verified = _num(current.get("verified_count"))
        canonical = _num(current.get("canonical_count"))
        corroborated = _num(current.get("corroborated_count"))
        verified_fingerprint = _fingerprint(current.get("verified_signatures"))
        stat = cells.setdefault(key, {})
        stat["attempts"] = _num(stat.get("attempts")) + 1
        stat["candidate_hits"] = _num(stat.get("candidate_hits")) + candidate
        stat["verified_hits"] = _num(stat.get("verified_hits")) + verified
        stat["canonical_hits"] = _num(stat.get("canonical_hits")) + canonical
        stat["corroborated_hits"] = _num(stat.get("corroborated_hits")) + corroborated
        stat["last_candidate_count"] = candidate
        stat["last_verified_count"] = verified
        stat["last_canonical_count"] = canonical
        if verified:
            stat["miss_streak"] = 0
            stat["verification_gap_streak"] = 0
            stat["discovery_gap_streak"] = 0
            old_fingerprint = str(stat.get("verified_fingerprint") or "")
            if not stat.get("last_verified") or (verified_fingerprint and verified_fingerprint != old_fingerprint):
                stat["last_verified"] = now
                stat["last_verified_change"] = now
            stat["last_verified_seen"] = now
            if verified_fingerprint:
                stat["verified_fingerprint"] = verified_fingerprint
            stat["last_state"] = "verified"
        else:
            stat["misses"] = _num(stat.get("misses")) + 1
            stat["miss_streak"] = _num(stat.get("miss_streak")) + 1
            if candidate:
                stat["verification_gap_runs"] = _num(stat.get("verification_gap_runs")) + 1
                stat["verification_gap_streak"] = _num(stat.get("verification_gap_streak")) + 1
                stat["discovery_gap_streak"] = 0
                stat["last_state"] = "candidate-only"
            else:
                stat["discovery_gap_runs"] = _num(stat.get("discovery_gap_runs")) + 1
                stat["discovery_gap_streak"] = _num(stat.get("discovery_gap_streak")) + 1
                stat["verification_gap_streak"] = 0
                stat["last_state"] = "no-candidate"
        source_hits = stat.setdefault("source_kinds", {})
        for kind, counts in (current.get("source_kinds") or {}).items():
            if not isinstance(counts, dict):
                continue
            entry = source_hits.setdefault(str(kind)[:100], {"candidate": 0, "verified": 0})
            entry["candidate"] = _num(entry.get("candidate")) + _num(counts.get("candidate"))
            entry["verified"] = _num(entry.get("verified")) + _num(counts.get("verified"))
            global_entry = global_kinds.setdefault(str(kind)[:100], {})
            global_entry["candidate"] = _num(global_entry.get("candidate")) + _num(counts.get("candidate"))
            global_entry["verified"] = _num(global_entry.get("verified")) + _num(counts.get("verified"))
            global_entry["runs_seen"] = _num(global_entry.get("runs_seen")) + 1
            global_entry["last_seen"] = now
        if len(source_hits) > MAX_SOURCE_KINDS_PER_CELL:
            ranked = sorted(
                source_hits.items(),
                key=lambda kv: (_num(kv[1].get("verified")), _num(kv[1].get("candidate"))),
                reverse=True,
            )
            stat["source_kinds"] = dict(ranked[:MAX_SOURCE_KINDS_PER_CELL])
        stat["last_seen"] = now

    if len(global_kinds) > MAX_SOURCE_KINDS:
        ranked = sorted(
            global_kinds.items(),
            key=lambda kv: (_num(kv[1].get("verified")), _num(kv[1].get("candidate"))),
            reverse=True,
        )
        data["source_kinds"] = dict(ranked[:MAX_SOURCE_KINDS])


def _coverage_report(data: dict) -> dict:
    rows = []
    for key in _expected_keys():
        stat = (data.get("coverage_cells") or {}).get(key, {})
        candidate = _num(stat.get("last_candidate_count"))
        verified = _num(stat.get("last_verified_count"))
        miss_streak = _num(stat.get("miss_streak"))
        verification_gap_streak = _num(stat.get("verification_gap_streak"))
        discovery_gap_streak = _num(stat.get("discovery_gap_streak"))
        topic = key.rsplit("/", 1)[-1]
        urgency = {"service_status": 5.5, "authenticity_notice": 5.0, "status_update": 5.0, "product_issue": 4.75, "rules": 4.5, "purchase_policy": 4.5, "deadline": 4.0, "access": 4.0, "official_price": 3.5, "entry": 3.0, "broadcast": 3.0, "results": 2.5, "stock": 2.0}.get(topic, 0.0)
        last_verified_age_days = _age_days(stat.get("last_verified"))
        recheck_after_days = int(RECHECK_DAYS.get(topic, 120))
        recheck_due = bool(
            verified > 0
            and last_verified_age_days is not None
            and last_verified_age_days >= recheck_after_days
        )
        freshness_priority = (
            2.0 + min(5.0, last_verified_age_days / max(1.0, float(recheck_after_days)))
            if recheck_due and last_verified_age_days is not None else 0.0
        )
        priority = round(
            miss_streak * 4.0
            + verification_gap_streak * 2.0
            + discovery_gap_streak
            + min(3.0, _num(stat.get("misses")) * 0.08)
            + urgency
            + freshness_priority,
            3,
        )
        rows.append({
            "cell": key,
            "state": stat.get("last_state") or "unknown",
            "candidate_count": candidate,
            "verified_count": verified,
            "miss_streak": miss_streak,
            "verification_gap_streak": verification_gap_streak,
            "discovery_gap_streak": discovery_gap_streak,
            "last_verified": stat.get("last_verified"),
            "last_verified_seen": stat.get("last_verified_seen"),
            "last_verified_age_days": round(last_verified_age_days, 2) if last_verified_age_days is not None else None,
            "recheck_after_days": recheck_after_days,
            "recheck_due": recheck_due,
            "priority": priority,
            "priority_reason": "verified-recheck-due" if recheck_due else ("verified-missing" if verified == 0 else "current"),
        })
    missing = [row for row in rows if row["verified_count"] == 0]
    priority_rows = [row for row in rows if row["verified_count"] == 0 or row["recheck_due"]]
    priority_rows.sort(key=lambda row: (row["priority"], row["candidate_count"]), reverse=True)
    by_game = {
        game: [row for row in priority_rows if row["cell"].startswith(game + "/")][:3]
        for game in GAMES
    }
    return {
        "expected_cells": len(rows),
        "verified_covered_cells": sum(1 for row in rows if row["verified_count"] > 0),
        "fresh_verified_covered_cells": sum(1 for row in rows if row["verified_count"] > 0 and not row["recheck_due"]),
        "candidate_covered_cells": sum(1 for row in rows if row["candidate_count"] > 0),
        "verified_missing_cells": [row["cell"] for row in missing],
        "recheck_due_cells": [row["cell"] for row in priority_rows if row["recheck_due"]],
        "candidate_only_cells": [row["cell"] for row in missing if row["candidate_count"] > 0],
        "no_candidate_cells": [row["cell"] for row in missing if row["candidate_count"] == 0],
        "next_priority_cells": priority_rows[:24],
        "next_priority_by_game": by_game,
        "coverage_basis": "verified-source-only",
        "verified_fact_basis": "verified rows may resolve multiple independently matched concrete factual topics; unverified rows remain primary-topic-only",
        "verified_multi_label_topics": sorted(VERIFIED_MULTI_LABEL_TOPICS),
        "freshness_basis": "unchanged verified evidence ages into bounded recheck-due priority without losing verified status",
    }


def recommended_verified_focus(game: str, data: dict | None = None) -> dict | None:
    text = str(game or "").strip().lower()
    canonical = next((full for full in GAMES if full.lower() in text), None)
    if canonical is None:
        for alias, full in GAME_ALIASES.items():
            if alias in text:
                canonical = full
                break
    if canonical is None:
        return None
    coverage = _coverage_report(data if isinstance(data, dict) else _load())
    rows = (coverage.get("next_priority_by_game") or {}).get(canonical) or []
    if not rows:
        return None
    row = dict(rows[0])
    parts = str(row.get("cell") or "").rsplit("/", 2)
    if len(parts) != 3:
        return None
    row["game"] = parts[0]
    row["region"] = parts[1]
    row["topic"] = parts[2]
    return row


def _source_kind_report(data: dict) -> list[dict]:
    rows = []
    for name, stat in (data.get("source_kinds") or {}).items():
        candidate = max(1, _num(stat.get("candidate")))
        verified = _num(stat.get("verified"))
        utility = verified / candidate + 0.25 / math.sqrt(candidate)
        rows.append({
            "source_kind": name,
            "candidate": _num(stat.get("candidate")),
            "verified": verified,
            "verified_yield": round(verified / candidate, 4),
            "routing_utility": round(utility, 4),
            "runs_seen": _num(stat.get("runs_seen")),
            "last_seen": stat.get("last_seen"),
        })
    rows.sort(key=lambda row: (row["routing_utility"], row["verified"], row["candidate"]), reverse=True)
    return rows[:MAX_SOURCE_KINDS]


def observe(
    provider_rows: list[dict],
    *,
    memory_path: Path = MEMORY,
    backup_path: Path | None = None,
    social_path: Path = SOCIAL,
    supplementary_path: Path = SUPPLEMENTARY,
    promo_path: Path = PROMO,
    rewrite_social_coverage: bool = True,
) -> dict:
    memory_path = Path(memory_path)
    backup = Path(backup_path) if backup_path else memory_path.with_suffix(memory_path.suffix + ".bak")
    social_path = Path(social_path)
    supplementary_path = Path(supplementary_path)
    promo_path = Path(promo_path)

    data = _load(memory_path, backup)
    data["runs"] = _num(data.get("runs")) + 1
    data["updated_at"] = _now()

    social = _read_payload(social_path)
    supplementary = _read_payload(supplementary_path)
    promo = _read_payload(promo_path)
    hardening = _harden_social_coverage(
        social, social_path, rewrite=rewrite_social_coverage
    ) if social else {
        "candidate_covered_cells": 0,
        "verified_covered_cells": 0,
        "candidate_only_cells": [],
        "verified_missing_cells": _expected_keys(),
        "basis": "verified-source-only",
        "verified_fact_basis": "verified-concrete-facts-multi-label; unverified-primary-only",
    }

    all_provider_rows = list(provider_rows or [])
    all_provider_rows.extend(_social_provider_rows(social))
    all_provider_rows.extend(_supplementary_provider_rows(supplementary))
    _observe_provider_rows(data, all_provider_rows)
    snapshot = _coverage_snapshot(social, supplementary, promo)
    _observe_coverage(data, snapshot)

    if memory_path.exists():
        try:
            atomic_write_json(backup, _load(memory_path, backup), suffix=".provider-health.bak.tmp")
        except Exception:
            pass
    atomic_write_json(memory_path, data, suffix=".provider-health.tmp")
    result = report(data)
    result["social_coverage_hardening"] = hardening
    result["current_sources"] = {
        "social_items": len(social.get("items") or []),
        "supplementary_items": len(supplementary.get("items") or []),
        "canonical_promo_items": len(promo.get("items") or []),
    }
    return result


def report(data: dict | None = None) -> dict:
    data = data if isinstance(data, dict) else _load()
    rows = []
    for name, stat in (data.get("providers") or {}).items():
        runs = max(1, _num(stat.get("runs")))
        configured_runs = max(0, runs - _num(stat.get("unconfigured_runs")))
        denominator = max(1, configured_runs)
        rows.append({
            "provider": name,
            "score": round(_float(stat.get("score")), 4),
            "runs": _num(stat.get("runs")),
            "configured_runs": configured_runs,
            "unconfigured_runs": _num(stat.get("unconfigured_runs")),
            "response_rate": round(_num(stat.get("responded")) / denominator, 4),
            "results": _num(stat.get("results")),
            "selected": _num(stat.get("selected")),
            "errors": _num(stat.get("errors")),
            "empty_streak": _num(stat.get("empty_streak")),
            "error_streak": _num(stat.get("error_streak")),
            "last_status": stat.get("last_status"),
        })
    rows.sort(key=lambda x: (x["score"], x["selected"], x["results"]), reverse=True)
    coverage = _coverage_report(data)
    return {
        "version": 5,
        "runs": _num(data.get("runs")),
        "updated_at": data.get("updated_at"),
        "providers": rows,
        "coverage_gap_learning": coverage,
        "source_kind_learning": _source_kind_report(data),
        "safety": {
            "trust_learning": False,
            "auto_verify": False,
            "learned_text_execution": False,
            "access_control_bypass": False,
            "policy": "수집 성공률·누락 우선순위만 학습하며 X/Instagram/Google/나무위키/커뮤니티 반복발견으로 공식성·사실성을 자동승격하지 않음",
        },
    }


if __name__ == "__main__":
    print(json.dumps(report(), ensure_ascii=False, indent=2))
