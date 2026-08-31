#!/usr/bin/env python3
"""Learn event search gaps and verified vocabulary without learning trust."""
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
MAX_CELLS, MAX_TERMS, MAX_SEEN = 120, 600, 500
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,24}|[가-힣]{2,14}|[ァ-ヶ一-龠]{2,14}")
PHRASE_RE = re.compile(r"\b[A-Z][A-Z0-9-]{2,}(?:\s+[A-Z][A-Z0-9-]{2,}){1,3}\b")
STOP = {"카드", "카드게임", "공식", "행사", "이벤트", "안내", "판매", "상품", "관련", "확인", "THE", "AND", "FOR"}


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _int(value, default=0):
    try: return max(0, min(1_000_000, int(value)))
    except (TypeError, ValueError, OverflowError): return default


def _float(value, default=0.0):
    try:
        number = float(value)
        return max(-100.0, min(100.0, number)) if math.isfinite(number) else default
    except (TypeError, ValueError, OverflowError): return default


def _fresh():
    return {"version": 1, "updated_at": None, "runs": 0, "rotation": 0, "cells": {}, "terms": {}, "seen_verified": []}


def _load(path: Path):
    backup = path.with_suffix(path.suffix + ".bak")
    for candidate in (path, backup):
        try:
            data = json.loads(safe_read_text(candidate))
            if isinstance(data, dict) and isinstance(data.get("cells"), dict) and isinstance(data.get("terms"), dict):
                clean = _fresh()
                clean.update({"runs": _int(data.get("runs")), "rotation": _int(data.get("rotation")), "updated_at": data.get("updated_at")})
                clean["seen_verified"] = [str(x)[:40] for x in (data.get("seen_verified") or [])[-MAX_SEEN:]]
                clean["cells"] = {str(k)[:100]: dict(v) for k, v in list(data["cells"].items())[:MAX_CELLS] if isinstance(v, dict)}
                clean["terms"] = {str(k)[:180]: dict(v) for k, v in list(data["terms"].items())[:MAX_TERMS] if isinstance(v, dict)}
                return clean
        except (OSError, ValueError, TypeError, UnicodeError):
            continue
    return _fresh()


def _topic(row):
    if row.get("event_scope") == "licensed_ip_popup_not_tcg_tournament": return "popup"
    text = " ".join(str(row.get(k) or "") for k in ("category", "name_ko", "name_native", "reward", "condition"))
    checks = (("movie", r"영화|극장판|movie|film|映画|劇場版"), ("anniversary", r"기념|주년|anniversary|周年|記念"),
              ("merch", r"굿즈|점프샵|JUMP SHOP|공식숍|official shop|merch|グッズ|ショップ"),
              ("popup", r"팝업|pop[- ]?up|ポップアップ"), ("tournament", r"대회|리그|championship|tournament|大会|リーグ"),
              ("promo", r"프로모|증정|배포|특전|promo|giveaway|プロモ|配布"), ("collab", r"콜라보|협업|collab|partnership|コラボ"),
              ("reprint", r"재발매|재판|reprint|再販|再版"), ("release", r"출시|발매|release|発売"))
    return next((topic for topic, pattern in checks if re.search(pattern, text, re.I)), "event")


def _terms(row):
    text = " ".join(str(row.get(k) or "") for k in ("name_ko", "name_native", "reward", "condition", "location"))
    out = []
    for value in PHRASE_RE.findall(text) + TOKEN_RE.findall(text):
        clean = re.sub(r"\s+", " ", value).strip()[:50]
        if len(clean) >= 2 and clean.upper() not in STOP and clean not in out: out.append(clean)
    return out[:24]


class EventGapLearner:
    def __init__(self, memory_path=MEMORY):
        self.memory_path = Path(memory_path)
        self.backup_path = self.memory_path.with_suffix(self.memory_path.suffix + ".bak")
        self.data = _load(self.memory_path)

    def learn_verified_file(self, path=PROMO):
        try: payload = json.loads(safe_read_text(Path(path)))
        except (OSError, ValueError, TypeError, UnicodeError): return 0
        seen, learned = set(self.data.get("seen_verified") or []), 0
        for row in (payload.get("items") or [])[:500]:
            if not isinstance(row, dict) or str(row.get("source_grade") or "").lower() != "official": continue
            game, region, source = str(row.get("game") or ""), str(row.get("region") or ""), str(row.get("source") or "")
            if not game or region not in {"KR", "JP", "US"} or not source.startswith("https://"): continue
            marker = hashlib.sha256(f"{game}|{region}|{source}|{row.get('name_ko')}".encode()).hexdigest()[:24]
            if marker in seen: continue
            topic = _topic(row)
            for term in _terms(row):
                stat = self.data["terms"].setdefault(f"{game}|{region}|{topic}|{term}", {})
                stat["verified_events"] = _int(stat.get("verified_events")) + 1
                stat["score"] = round(min(20.0, _float(stat.get("score")) * 0.98 + 1.0), 4)
                stat["last_seen"] = _now()
            seen.add(marker); learned += 1
        self.data["seen_verified"] = list(seen)[-MAX_SEEN:]
        return learned

    def terms_for(self, game, region, topic, limit=5):
        prefix, ranked = f"{game}|{region}|{topic}|", []
        for key, stat in self.data.get("terms", {}).items():
            if key.startswith(prefix): ranked.append((_float(stat.get("score")) + _int(stat.get("verified_events")) * .5, key[len(prefix):]))
        ranked.sort(reverse=True)
        return tuple(term for score, term in ranked[:max(0, min(8, limit))] if score > 0)

    def prioritize(self, missing, limit):
        rotation, ranked = _int(self.data.get("rotation")), []
        for index, key in enumerate(missing):
            stat = self.data.get("cells", {}).get(key, {})
            ranked.append((_int(stat.get("miss_streak")) * 3 + _int(stat.get("misses")) * .15, -((index - rotation) % max(1, len(missing))), key))
        ranked.sort(reverse=True); self.data["rotation"] = rotation + max(1, limit)
        return [key for _, _, key in ranked[:max(0, limit)]]

    def observe(self, coverage):
        self.data["runs"] = _int(self.data.get("runs")) + 1
        for key, count in coverage.items():
            stat = self.data["cells"].setdefault(str(key)[:100], {})
            stat["attempts"] = _int(stat.get("attempts")) + 1
            if _int(count): stat["hits"], stat["miss_streak"], stat["last_hit"] = _int(stat.get("hits")) + _int(count), 0, _now()
            else: stat["misses"], stat["miss_streak"] = _int(stat.get("misses")) + 1, _int(stat.get("miss_streak")) + 1
            stat["last_seen"] = _now()

    def save(self):
        self.data["updated_at"] = _now()
        if self.memory_path.exists(): atomic_write_json(self.backup_path, _load(self.memory_path), suffix=".event-gap.bak.tmp")
        atomic_write_json(self.memory_path, self.data, suffix=".event-gap.tmp")

    def report(self):
        hardest = sorted(({"cell": k, "miss_streak": _int(v.get("miss_streak")), "misses": _int(v.get("misses")), "hits": _int(v.get("hits"))} for k, v in self.data["cells"].items()), key=lambda x: (x["miss_streak"], x["misses"]), reverse=True)
        return {"version": 1, "runs": _int(self.data.get("runs")), "learned_terms": len(self.data["terms"]), "hardest_gaps": hardest[:12], "policy": "누락 우선순위와 공식확인 행사 검색어만 학습 · 출처 신뢰도 자동승격 금지"}
