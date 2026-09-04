#!/usr/bin/env python3
"""Learn event search gaps and verified vocabulary without learning trust.

v2 adds a bounded missed-event recovery loop:
- canonical official promo rows keep teaching useful search vocabulary;
- manually recovered events teach only when the evidence is explicitly verified
  through an official account/domain;
- verified miss recoveries may teach region/location anchors so a Korean-language
  community post about a Japan event can be searched and classified as Japan;
- learned terms/region hints only affect discovery priority. They never promote a
  community source to official/trusted/verified status.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
from pathlib import Path

from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
MEMORY = ROOT / "event_gap_learning.json"
PROMO = ROOT / "promo_events.json"
MANUAL_EVIDENCE = ROOT / "manual_event_evidence.json"
MAX_CELLS, MAX_TERMS, MAX_SEEN = 220, 650, 550
MAX_REGION_HINTS, MAX_RECOVERIES = 360, 240
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.&'/-]{2,32}|[가-힣]{2,18}|[ァ-ヶ一-龠]{2,18}")
PHRASE_RE = re.compile(r"\b[A-Z][A-Z0-9&'./-]{2,}(?:\s+[A-Z][A-Z0-9&'./-]{2,}){1,4}\b")
STOP = {
    "카드", "카드게임", "공식", "행사", "이벤트", "안내", "판매", "상품", "관련", "확인",
    "THE", "AND", "FOR", "CARD", "CARDS", "OFFICIAL", "EVENT", "GAME",
    "プロモ", "カード", "イベント", "公式", "商品", "発売",
}
REGION_HINT_STOP = STOP | {
    "콜라보", "프로모", "증정", "배포", "응모", "구매", "정기구독", "특전", "발표",
    "コラボ", "配布", "応募", "購入", "定期購読", "特典", "発表",
    "COLLAB", "PROMO", "GIVEAWAY", "PURCHASE", "SUBSCRIPTION", "ANNOUNCEMENT",
}

# Static hints are deliberately geographic/publisher-specific rather than generic
# event vocabulary. Verified device-local learning can reinforce or add hints.
REGION_HINT_SEEDS = {
    "KR": (
        "대한민국", "한국", "코리아", "서울", "부산", "인천", "대구", "대전", "광주", "수원",
        "seoul", "korea", "busan", "pokemon korea", "서울미디어코믹스", "신세계",
    ),
    "JP": (
        "日本", "일본", "japan", "東京", "도쿄", "tokyo", "原宿", "하라주쿠", "harajuku",
        "渋谷", "시부야", "shibuya", "大阪", "오사카", "osaka", "集英社", "슈에이샤",
        "shueisha", "週刊少年ジャンプ", "주간소년점프", "weekly shonen jump", "nike umeda",
    ),
    "US": (
        "미국", "usa", "u.s.", "united states", "north america", "뉴욕", "new york",
        "로스앤젤레스", "los angeles", "california", "chicago", "las vegas",
    ),
}


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _int(value, default=0):
    try:
        return max(0, min(1_000_000, int(value)))
    except (TypeError, ValueError, OverflowError):
        return default


def _float(value, default=0.0):
    try:
        number = float(value)
        return max(-100.0, min(100.0, number)) if math.isfinite(number) else default
    except (TypeError, ValueError, OverflowError):
        return default


def _fresh():
    return {
        "version": 2,
        "updated_at": None,
        "runs": 0,
        "rotation": 0,
        "cells": {},
        "terms": {},
        "region_hints": {},
        "miss_recoveries": {},
        "seen_verified": [],
    }


def _load(path: Path):
    backup = path.with_suffix(path.suffix + ".bak")
    for candidate in (path, backup):
        try:
            data = json.loads(safe_read_text(candidate))
            if isinstance(data, dict) and isinstance(data.get("cells"), dict) and isinstance(data.get("terms"), dict):
                clean = _fresh()
                clean.update({
                    "runs": _int(data.get("runs")),
                    "rotation": _int(data.get("rotation")),
                    "updated_at": data.get("updated_at"),
                })
                clean["seen_verified"] = [str(x)[:48] for x in (data.get("seen_verified") or [])[-MAX_SEEN:]]
                clean["cells"] = {
                    str(k)[:100]: dict(v)
                    for k, v in list(data["cells"].items())[:MAX_CELLS]
                    if isinstance(v, dict)
                }
                clean["terms"] = {
                    str(k)[:180]: dict(v)
                    for k, v in list(data["terms"].items())[:MAX_TERMS]
                    if isinstance(v, dict)
                }
                clean["region_hints"] = {
                    str(k)[:180]: dict(v)
                    for k, v in list((data.get("region_hints") or {}).items())[:MAX_REGION_HINTS]
                    if isinstance(v, dict)
                }
                clean["miss_recoveries"] = {
                    str(k)[:100]: dict(v)
                    for k, v in list((data.get("miss_recoveries") or {}).items())[-MAX_RECOVERIES:]
                    if isinstance(v, dict)
                }
                return clean
        except (OSError, ValueError, TypeError, UnicodeError):
            continue
    return _fresh()


def _topic(row):
    if row.get("event_scope") == "licensed_ip_popup_not_tcg_tournament":
        return "popup"
    text = " ".join(
        str(row.get(k) or "")
        for k in (
            "category", "name_ko", "name_native", "reward", "condition", "title", "excerpt",
            "status", "source_label", "event_scope",
        )
    )
    checks = (
        ("service_status", r"점검|서비스\s*장애|접속\s*(?:장애|오류)|로그인\s*(?:불가|장애)|복구\s*완료|maintenance|service\s+(?:outage|unavailable|disruption)|login\s+(?:issue|failure|unavailable)|incident|resolved|メンテナンス|障害|不具合|ログインできない|利用できません|復旧"),
        ("results", r"대회\s*결과|경기\s*결과|결과\s*발표|우승자\s*발표|입상자|최종\s*순위|우승\s*덱|상위\s*덱|tournament\s+results?|event\s+results?|match\s+results?|final\s+standings?|top\s+finishers?|winning\s+deck|champion\s+deck|大会結果|試合結果|結果発表|優勝者発表|入賞者|最終順位|優勝デッキ|上位デッキ"),
        ("purchase_policy", r"추첨\s*판매|구매\s*제한|판매\s*제한|1인\s*\d+개|본인\s*인증.{0,20}(?:판매|구매)|구매권|구매\s*티켓|가상\s*대기열|lottery\s+sale|purchase\s+limit|sales?\s+limit|limited\s+to\s+(?:one|\d+)\s+items?\s+per\s+person|identity\s+verification.{0,30}(?:sale|purchase)|virtual\s+queue|purchase\s+(?:ticket|voucher)|抽選販売|購入制限|販売制限|お一人様\s*\d+点|本人認証.{0,20}(?:販売|購入)|購入券|購入チケット|仮想待機列"),
        ("status_update", r"취소|연기|일정\s*변경|시간\s*변경|장소\s*변경|갱신내용|cancel(?:led|ed|ation)?|postpon(?:e|ed|ement)|reschedul(?:e|ed|ing)|schedule\s+change|venue\s+change|中止|延期|日程変更|時間変更|会場変更|内容変更"),
        ("deadline", r"마감|신청\s*기한|응모\s*기한|접수\s*기한|신청기간|응모기간|접수기간|deadline|apply\s+by|registration\s+closes?|application\s+period|締切|期限|応募期間|申込期間|受付期間"),
        ("access", r"참가\s*자격|참가조건|체크인|입장권|관람객|패스|정원|대기\s*명단|플레이어\s*ID|덱\s*리스트|참가비|eligib(?:le|ility)|check[- ]?in|waitlist|interest\s+list|spectator|admission|entry\s+fee|player\s+id|deck\s+list|seating|capacity|\bbadge\b|\bpass\b|参加資格|参加条件|チェックイン|入場券|観戦|パス|定員|キャンセル待ち|プレイヤーID|デッキリスト|参加費"),
        ("rules", r"금지\s*/?\s*제한|금지카드|제한카드|금지\s*페어|에라타|사용\s*규정|룰|규칙|banned|restricted|restriction|errata|legality|legal\s+date|regulation|rulebook|floor\s+rules?|\brules?\b|禁止|制限|禁止カード|制限カード|禁止ペア|エラッタ|ルール|レギュレーション|使用可能"),
        ("movie", r"영화|극장판|movie|film|映画|劇場版"),
        ("broadcast", r"라이브|생방송|스트리밍|시청|twitch\s*drops?|live[ -]?stream|broadcast|streaming|redeem|ライブ配信|生配信|配信|視聴|ドロップ|コード"),
        ("anniversary", r"기념|주년|anniversary|周年|記念"),
        ("merch", r"굿즈|점프샵|JUMP SHOP|공식숍|official shop|merch|グッズ|ショップ"),
        ("popup", r"팝업|pop[- ]?up|ポップアップ|RESEARCH LAB"),
        ("entry", r"응모|신청|접수|등록|추첨|당첨|엔트리|entry|application|registration|register|lottery|drawing|応募|申込|受付|登録|抽選|当選|エントリー"),
        ("tournament", r"대회|리그|championship|tournament|大会|リーグ"),
        ("stock", r"재입고|입고|재고|품절|구매처|restock|in stock|sold out|availability|retailer|再入荷|入荷|在庫|売り切れ"),
        ("promo", r"프로모|증정|배포|특전|전원서비스|promo|giveaway|distribution|配布|特典|全員サービス"),
        ("collab", r"콜라보|협업|collab|partnership|コラボ"),
        ("reprint", r"재발매|재판|reprint|再販|再版"),
        ("release", r"출시|발매|release|発売"),
    )
    return next((topic for topic, pattern in checks if re.search(pattern, text, re.I)), "event")


def _terms(row):
    text = " ".join(
        str(row.get(k) or "")
        for k in (
            "name_ko", "name_native", "reward", "condition", "location", "title", "excerpt",
            "author", "source_label",
        )
    )
    out = []
    explicit = []
    for key in ("learning_terms", "dedupe_terms"):
        for value in row.get(key) or []:
            clean = re.sub(r"\s+", " ", str(value or "")).strip()[:50]
            if clean:
                explicit.append(clean)
    for value in explicit + PHRASE_RE.findall(text) + TOKEN_RE.findall(text):
        clean = re.sub(r"\s+", " ", str(value)).strip()[:50]
        if len(clean) >= 2 and clean.upper() not in STOP and clean not in out:
            out.append(clean)
    return out[:32]


def _region_terms(row):
    out = []
    explicit = row.get("region_anchors") or []
    location = str(row.get("location") or "")
    values = list(explicit) + TOKEN_RE.findall(location)
    for value in values:
        clean = re.sub(r"\s+", " ", str(value or "")).strip()[:50]
        if len(clean) < 2 or clean.upper() in REGION_HINT_STOP or clean in REGION_HINT_STOP:
            continue
        if clean not in out:
            out.append(clean)
    return out[:24]


def _official_manual_row(row: dict) -> bool:
    if row.get("manual_evidence") is not True or row.get("verified") is not True:
        return False
    return bool(
        row.get("official_account_verified") is True
        or row.get("official_domain_match") is True
        or str(row.get("source_grade") or "").lower() == "official"
    )


class EventGapLearner:
    def __init__(self, memory_path=MEMORY):
        self.memory_path = Path(memory_path)
        self.backup_path = self.memory_path.with_suffix(self.memory_path.suffix + ".bak")
        self.data = _load(self.memory_path)

    def _learn_terms(self, game, region, topic, row, *, weight=1.0, learned_from="official_event"):
        learned = 0
        for term in _terms(row):
            key = f"{game}|{region}|{topic}|{term}"
            stat = self.data["terms"].setdefault(key, {})
            stat["verified_events"] = _int(stat.get("verified_events")) + 1
            stat["score"] = round(min(20.0, max(0.0, _float(stat.get("score"))) * 0.98 + weight), 4)
            stat["last_seen"] = _now()
            stat["learned_from"] = learned_from
            stat["last_learning_weight"] = round(float(weight), 4)
            learned += 1
        return learned

    def _learn_region_hints(self, game, region, row, *, weight=1.0, learned_from="official_event"):
        learned = 0
        for term in _region_terms(row):
            key = f"{game}|{region}|{term}"
            stat = self.data["region_hints"].setdefault(key, {})
            stat["verified_events"] = _int(stat.get("verified_events")) + 1
            stat["score"] = round(min(12.0, max(0.0, _float(stat.get("score"))) * 0.985 + weight), 4)
            stat["last_seen"] = _now()
            stat["learned_from"] = learned_from
            learned += 1
        return learned

    def learn_verified_file(self, path=PROMO):
        try:
            payload = json.loads(safe_read_text(Path(path)))
        except (OSError, ValueError, TypeError, UnicodeError):
            return 0
        seen, learned = set(self.data.get("seen_verified") or []), 0
        for row in (payload.get("items") or [])[:500]:
            if not isinstance(row, dict) or str(row.get("source_grade") or "").lower() != "official":
                continue
            game = str(row.get("game") or "")
            region = str(row.get("region") or "")
            source = str(row.get("source") or "")
            if not game or region not in {"KR", "JP", "US"} or not source.startswith("https://"):
                continue
            marker = hashlib.sha256(f"promo|{game}|{region}|{source}|{row.get('name_ko')}".encode()).hexdigest()[:24]
            if marker in seen:
                continue
            topic = _topic(row)
            self._learn_terms(game, region, topic, row, weight=1.0, learned_from="official_promo_event")
            self._learn_region_hints(game, region, row, weight=0.45, learned_from="official_promo_location")
            seen.add(marker)
            learned += 1
        self.data["seen_verified"] = list(seen)[-MAX_SEEN:]
        return learned

    def learn_verified_evidence_file(self, path=MANUAL_EVIDENCE):
        """Teach from a recovered miss only after official verification.

        This is the main positive feedback loop for user-reported misses. A raw
        community screenshot/candidate does not qualify and therefore cannot teach
        vocabulary, region hints, trust, or verification.
        """
        try:
            payload = json.loads(safe_read_text(Path(path), max_bytes=1_000_000))
        except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError):
            return 0
        seen = set(self.data.get("seen_verified") or [])
        learned = 0
        recoveries = self.data.setdefault("miss_recoveries", {})
        for row in (payload.get("items") or [])[:300]:
            if not isinstance(row, dict) or not _official_manual_row(row):
                continue
            game = str(row.get("game") or "")
            region = str(row.get("region") or "")
            source = str(row.get("source") or "")
            if not game or region not in {"KR", "JP", "US"} or not source.startswith("https://"):
                continue
            case_id = str(row.get("recovery_case_id") or "").strip()[:80]
            marker_raw = f"manual-miss|{game}|{region}|{source}|{row.get('title')}|{case_id}"
            marker = hashlib.sha256(marker_raw.encode("utf-8", "ignore")).hexdigest()[:24]
            if marker in seen:
                continue
            topic = _topic(row)
            term_count = self._learn_terms(
                game, region, topic, row,
                weight=1.25,
                learned_from="official_manual_miss_recovery",
            )
            region_count = self._learn_region_hints(
                game, region, row,
                weight=1.0,
                learned_from="official_manual_miss_recovery",
            )
            key = case_id or marker
            recoveries[key] = {
                "game": game,
                "region": region,
                "topic": topic,
                "source": source[:500],
                "term_count": term_count,
                "region_hint_count": region_count,
                "learned_at": _now(),
                "policy": "공식 검증된 누락사례만 검색어/지역힌트 학습 · 신뢰도 자동승격 금지",
            }
            if len(recoveries) > MAX_RECOVERIES:
                oldest = sorted(recoveries, key=lambda k: str(recoveries[k].get("learned_at") or ""))
                for old in oldest[: len(recoveries) - MAX_RECOVERIES]:
                    recoveries.pop(old, None)
            seen.add(marker)
            learned += 1
        self.data["seen_verified"] = list(seen)[-MAX_SEEN:]
        return learned

    def terms_for(self, game, region, topic, limit=5):
        prefix, ranked = f"{game}|{region}|{topic}|", []
        for key, stat in self.data.get("terms", {}).items():
            if key.startswith(prefix):
                ranked.append((
                    _float(stat.get("score")) + _int(stat.get("verified_events")) * .5,
                    key[len(prefix):],
                ))
        ranked.sort(reverse=True)
        return tuple(term for score, term in ranked[:max(0, min(12, limit))] if score > 0)

    def top_terms_for_region(self, game, region, limit=8):
        prefix = f"{game}|{region}|"
        ranked = []
        for key, stat in self.data.get("terms", {}).items():
            if not key.startswith(prefix):
                continue
            parts = key.split("|", 3)
            if len(parts) != 4:
                continue
            term = parts[3]
            score = _float(stat.get("score")) + _int(stat.get("verified_events")) * .35
            if score > 0:
                ranked.append((score, term))
        ranked.sort(reverse=True)
        out = []
        for _, term in ranked:
            if term not in out:
                out.append(term)
            if len(out) >= max(0, min(16, int(limit))):
                break
        return tuple(out)

    def region_hint_scores(self, game, text):
        value = re.sub(r"\s+", " ", str(text or "")).strip().lower()
        scores = {"KR": 0.0, "JP": 0.0, "US": 0.0}
        signals = {"KR": [], "JP": [], "US": []}
        for region, terms in REGION_HINT_SEEDS.items():
            for term in terms:
                needle = str(term).lower()
                if needle and needle in value:
                    scores[region] += 1.4
                    if len(signals[region]) < 8:
                        signals[region].append(str(term))
        prefix = f"{game}|"
        for key, stat in self.data.get("region_hints", {}).items():
            if not key.startswith(prefix):
                continue
            parts = key.split("|", 2)
            if len(parts) != 3 or parts[1] not in scores:
                continue
            region, term = parts[1], parts[2]
            if term.lower() in value:
                scores[region] += min(2.2, max(0.2, _float(stat.get("score")) * .45))
                if term not in signals[region] and len(signals[region]) < 8:
                    signals[region].append(term)
        return scores, signals

    def infer_region(self, game, text, default="KR"):
        default = default if default in {"KR", "JP", "US"} else "KR"
        scores, signals = self.region_hint_scores(game, text)
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        best_region, best_score = ranked[0]
        second_score = ranked[1][1]
        default_score = scores.get(default, 0.0)
        if (
            best_region != default
            and best_score >= 2.0
            and best_score >= default_score + 0.75
            and best_score >= second_score + 0.25
        ):
            confidence = min(0.96, 0.58 + best_score * 0.055)
            return best_region, round(confidence, 4), tuple(signals[best_region])
        confidence = min(0.90, 0.50 + max(0.0, default_score) * 0.04)
        return default, round(confidence, 4), tuple(signals[default])

    def prioritize(self, missing, limit):
        rotation, ranked = _int(self.data.get("rotation")), []
        for index, key in enumerate(missing):
            stat = self.data.get("cells", {}).get(key, {})
            ranked.append((
                _int(stat.get("miss_streak")) * 3 + _int(stat.get("misses")) * .15,
                -((index - rotation) % max(1, len(missing))),
                key,
            ))
        ranked.sort(reverse=True)
        self.data["rotation"] = rotation + max(1, limit)
        return [key for _, _, key in ranked[:max(0, limit)]]

    def observe(self, coverage):
        self.data["runs"] = _int(self.data.get("runs")) + 1
        for key, count in coverage.items():
            stat = self.data["cells"].setdefault(str(key)[:100], {})
            stat["attempts"] = _int(stat.get("attempts")) + 1
            if _int(count):
                stat["hits"] = _int(stat.get("hits")) + _int(count)
                stat["miss_streak"] = 0
                stat["last_hit"] = _now()
            else:
                stat["misses"] = _int(stat.get("misses")) + 1
                stat["miss_streak"] = _int(stat.get("miss_streak")) + 1
            stat["last_seen"] = _now()

    def save(self):
        self.data["version"] = 2
        self.data["updated_at"] = _now()
        if len(self.data.get("terms", {})) > MAX_TERMS:
            ranked = sorted(
                self.data["terms"].items(),
                key=lambda item: (_float(item[1].get("score")), str(item[1].get("last_seen") or "")),
                reverse=True,
            )[:MAX_TERMS]
            self.data["terms"] = dict(ranked)
        if len(self.data.get("region_hints", {})) > MAX_REGION_HINTS:
            ranked = sorted(
                self.data["region_hints"].items(),
                key=lambda item: (_float(item[1].get("score")), str(item[1].get("last_seen") or "")),
                reverse=True,
            )[:MAX_REGION_HINTS]
            self.data["region_hints"] = dict(ranked)
        if self.memory_path.exists():
            atomic_write_json(self.backup_path, _load(self.memory_path), suffix=".event-gap.bak.tmp")
        atomic_write_json(self.memory_path, self.data, suffix=".event-gap.tmp")

    def report(self):
        hardest = sorted(
            ({
                "cell": k,
                "miss_streak": _int(v.get("miss_streak")),
                "misses": _int(v.get("misses")),
                "hits": _int(v.get("hits")),
            } for k, v in self.data["cells"].items()),
            key=lambda x: (x["miss_streak"], x["misses"]),
            reverse=True,
        )
        return {
            "version": 2,
            "runs": _int(self.data.get("runs")),
            "learned_terms": len(self.data.get("terms", {})),
            "learned_region_hints": len(self.data.get("region_hints", {})),
            "verified_miss_recoveries": len(self.data.get("miss_recoveries", {})),
            "hardest_gaps": hardest[:12],
            "policy": "누락 우선순위 + 공식확인 검색어/지역힌트만 학습 · 출처 신뢰도 자동승격 금지",
        }
