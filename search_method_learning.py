#!/usr/bin/env python3
"""Adaptive operational learner for public search methods.

Learns *how to search*, never whether a source is true/official.
- Tracks response, results, selected results, latency, empty searches and errors.
- Separates 403/429 blocking, timeouts and parser/network errors.
- Temporarily cools down unhealthy methods; never permanently blacklists them.
- Keeps an exploration slot so recovered methods are retried later.
- Stores bounded device-local state with atomic writes and backup recovery.

No proxy rotation, CAPTCHA bypass, login bypass or private API access is used.
"""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
MEMORY = ROOT / "search_method_learning.json"
BACKUP = ROOT / "search_method_learning.json.bak"
SCHEMA_VERSION = 1
MAX_METHODS = 32
MAX_CONTEXTS = 240

DEFAULT_METHODS = (
    "ddg_html", "ddg_lite", "bing_web_rss", "bing_news_rss",
    "google_news_rss", "naver_news_html",
)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(value: dt.datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") if value else None


def _int(value, default=0, low=0, high=10_000_000) -> int:
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


def classify_error(error: object) -> str:
    text = str(error or "").lower()
    if not text:
        return "none"
    if "429" in text or "too many requests" in text or "rate limit" in text:
        return "rate_limited"
    if "403" in text or "captcha" in text or "access denied" in text or "forbidden" in text:
        return "blocked"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "parseerror" in text or "parser" in text or "decode" in text:
        return "parse"
    if "urlerror" in text or "connection" in text or "name resolution" in text or "dns" in text:
        return "network"
    return "other"


def _fresh() -> dict:
    return {
        "version": SCHEMA_VERSION,
        "updated_at": None,
        "rotation": 0,
        "methods": {},
        "contexts": {},
        "totals": {"runs": 0, "attempts": 0, "responses": 0, "results": 0, "selected": 0, "errors": 0},
    }


def _load(path: Path = MEMORY, backup: Path = BACKUP) -> dict:
    for candidate in (path, backup):
        try:
            data = json.loads(safe_read_text(candidate))
            if isinstance(data, dict) and isinstance(data.get("methods"), dict):
                data.setdefault("contexts", {})
                data.setdefault("totals", {})
                data.setdefault("rotation", 0)
                return data
        except Exception:
            continue
    return _fresh()


def _context_key(method: str, region: str, family: str) -> str:
    return f"{method}|{str(region or 'KR')[:8]}|{str(family or 'web')[:80]}"


def _cooldown_until(stat: dict) -> dt.datetime | None:
    raw = stat.get("cooldown_until")
    if not raw:
        return None
    try:
        value = dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        return value.astimezone(dt.timezone.utc)
    except ValueError:
        return None


def _score(stat: dict) -> float:
    attempts = max(1, _int(stat.get("attempts"), 1))
    response_rate = _int(stat.get("responses")) / attempts
    result_rate = _int(stat.get("nonempty")) / attempts
    select_rate = _int(stat.get("selected")) / max(1, _int(stat.get("results"), 1))
    blocks = _int(stat.get("blocked")) + _int(stat.get("rate_limited"))
    timeouts = _int(stat.get("timeouts"))
    errors = _int(stat.get("errors"))
    avg_latency = _float(stat.get("avg_latency_ms"), 0.0, 0.0, 120_000.0)
    latency_penalty = min(1.4, avg_latency / 25_000.0)
    exploration = 0.65 / math.sqrt(attempts)
    return (
        response_rate * 2.2 + result_rate * 1.7 + select_rate * 1.5 + exploration
        - min(2.4, blocks * 0.18) - min(1.5, timeouts * 0.10)
        - min(1.3, errors * 0.05) - latency_penalty
    )


class SearchMethodLearner:
    def __init__(self, memory_path: Path | str = MEMORY, backup_path: Path | str | None = None):
        self.memory_path = Path(memory_path)
        self.backup_path = Path(backup_path) if backup_path else self.memory_path.with_suffix(self.memory_path.suffix + ".bak")
        self.data = _load(self.memory_path, self.backup_path)

    def start_run(self) -> None:
        totals = self.data.setdefault("totals", {})
        totals["runs"] = _int(totals.get("runs")) + 1
        self.data["rotation"] = _int(self.data.get("rotation")) + 1

    def _method(self, name: str) -> dict:
        methods = self.data.setdefault("methods", {})
        return methods.setdefault(str(name)[:80], {})

    def _context(self, name: str, region: str, family: str) -> dict:
        contexts = self.data.setdefault("contexts", {})
        return contexts.setdefault(_context_key(name, region, family), {})

    def method_score(self, name: str, region: str = "KR", family: str = "web") -> float:
        method = self._method(name)
        context = self._context(name, region, family)
        base = _score(method)
        if _int(context.get("attempts")):
            base = base * 0.7 + _score(context) * 0.3
        cooldown = _cooldown_until(method)
        if cooldown and cooldown > _now():
            base -= 5.0
        return base

    def ordered_routes(self, names, *, region: str = "KR", family: str = "web", budget: int | None = None) -> list[str]:
        candidates = [str(x) for x in names if str(x)]
        if not candidates:
            return []
        now = _now()
        rotation = _int(self.data.get("rotation"))
        healthy, cooling = [], []
        for index, name in enumerate(candidates):
            stat = self._method(name)
            score = self.method_score(name, region, family)
            # Stable tiny rotation bonus preserves exploration without randomness.
            bonus = ((rotation + index * 3) % max(2, len(candidates))) * 0.015
            cooldown = _cooldown_until(stat)
            row = (score + bonus, name)
            (cooling if cooldown and cooldown > now else healthy).append(row)
        healthy.sort(reverse=True)
        cooling.sort(reverse=True)
        ordered = [name for _, name in healthy]
        recovery = cooling[rotation % len(cooling)][1] if cooling else None
        # If everything is cooling down, retry only the best candidate to detect recovery.
        if not ordered and recovery:
            ordered = [recovery]
        elif recovery:
            # A cooled route is never permanently starved. On every fourth routing
            # cycle reserve the final budget slot for a recovery probe; otherwise
            # append it only when capacity remains.
            if budget is not None and int(budget) > 1 and len(ordered) >= int(budget) and rotation % 4 == 0:
                ordered = ordered[: int(budget) - 1] + [recovery]
            else:
                ordered.append(recovery)
        if budget is None:
            return ordered
        return ordered[: max(1, min(len(ordered), int(budget)))]

    def observe(self, method: str, *, responded: bool, result_count: int, error: object = "", elapsed_ms: float = 0.0,
                region: str = "KR", family: str = "web") -> dict:
        kind = classify_error(error)
        result_count = _int(result_count)
        elapsed_ms = _float(elapsed_ms, 0.0, 0.0, 120_000.0)
        for stat in (self._method(method), self._context(method, region, family)):
            stat["attempts"] = _int(stat.get("attempts")) + 1
            stat["responses"] = _int(stat.get("responses")) + (1 if responded else 0)
            stat["results"] = _int(stat.get("results")) + result_count
            stat["nonempty"] = _int(stat.get("nonempty")) + (1 if result_count > 0 else 0)
            stat["empty"] = _int(stat.get("empty")) + (1 if responded and result_count == 0 else 0)
            stat["errors"] = _int(stat.get("errors")) + (1 if kind != "none" else 0)
            stat["blocked"] = _int(stat.get("blocked")) + (1 if kind == "blocked" else 0)
            stat["rate_limited"] = _int(stat.get("rate_limited")) + (1 if kind == "rate_limited" else 0)
            stat["timeouts"] = _int(stat.get("timeouts")) + (1 if kind == "timeout" else 0)
            stat["last_error_kind"] = kind
            stat["last_seen"] = _iso(_now())
            old_latency = _float(stat.get("avg_latency_ms"), elapsed_ms, 0.0, 120_000.0)
            stat["avg_latency_ms"] = round(old_latency * 0.82 + elapsed_ms * 0.18, 2)
            streak = _int(stat.get("failure_streak"))
            if responded:
                stat["failure_streak"] = 0
                stat["cooldown_until"] = None
            else:
                streak += 1
                stat["failure_streak"] = streak
                minutes = 0
                if kind == "rate_limited":
                    minutes = min(360, 30 * (2 ** min(4, streak - 1)))
                elif kind == "blocked":
                    minutes = min(720, 60 * (2 ** min(4, streak - 1)))
                elif kind == "timeout" and streak >= 2:
                    minutes = min(120, 10 * streak)
                elif kind in {"network", "other"} and streak >= 3:
                    minutes = min(60, 5 * streak)
                if minutes:
                    stat["cooldown_until"] = _iso(_now() + dt.timedelta(minutes=minutes))
            stat["score"] = round(_score(stat), 5)
        totals = self.data.setdefault("totals", {})
        totals["attempts"] = _int(totals.get("attempts")) + 1
        totals["responses"] = _int(totals.get("responses")) + (1 if responded else 0)
        totals["results"] = _int(totals.get("results")) + result_count
        totals["errors"] = _int(totals.get("errors")) + (1 if kind != "none" else 0)
        return {"method": method, "error_kind": kind, "score": round(self.method_score(method, region, family), 4)}

    def observe_selected(self, rows: list[dict]) -> None:
        counts = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            method = str(row.get("search_method") or row.get("search_provider") or "")
            if method:
                counts[method] = counts.get(method, 0) + 1
        for method, count in counts.items():
            stat = self._method(method)
            stat["selected"] = _int(stat.get("selected")) + _int(count)
            stat["score"] = round(_score(stat), 5)
        totals = self.data.setdefault("totals", {})
        totals["selected"] = _int(totals.get("selected")) + sum(counts.values())

    def save(self) -> None:
        self.data["version"] = SCHEMA_VERSION
        self.data["updated_at"] = _iso(_now())
        methods = self.data.setdefault("methods", {})
        if len(methods) > MAX_METHODS:
            ranked = sorted(methods.items(), key=lambda kv: _score(kv[1]), reverse=True)
            self.data["methods"] = dict(ranked[:MAX_METHODS])
        contexts = self.data.setdefault("contexts", {})
        if len(contexts) > MAX_CONTEXTS:
            ranked = sorted(contexts.items(), key=lambda kv: (_score(kv[1]), _int(kv[1].get("attempts"))), reverse=True)
            self.data["contexts"] = dict(ranked[:MAX_CONTEXTS])
        if self.memory_path.exists():
            try:
                atomic_write_json(self.backup_path, _load(self.memory_path, self.backup_path), suffix=".search-method.bak.tmp")
            except Exception:
                pass
        atomic_write_json(self.memory_path, self.data, suffix=".search-method.tmp")

    def report(self) -> dict:
        now = _now()
        rows = []
        for name, stat in self.data.get("methods", {}).items():
            cooldown = _cooldown_until(stat)
            attempts = max(1, _int(stat.get("attempts"), 1))
            rows.append({
                "method": name,
                "score": round(_score(stat), 4),
                "attempts": _int(stat.get("attempts")),
                "response_rate": round(_int(stat.get("responses")) / attempts, 4),
                "nonempty_rate": round(_int(stat.get("nonempty")) / attempts, 4),
                "results": _int(stat.get("results")),
                "selected": _int(stat.get("selected")),
                "empty": _int(stat.get("empty")),
                "blocked": _int(stat.get("blocked")),
                "rate_limited": _int(stat.get("rate_limited")),
                "timeouts": _int(stat.get("timeouts")),
                "avg_latency_ms": round(_float(stat.get("avg_latency_ms")), 1),
                "failure_streak": _int(stat.get("failure_streak")),
                "cooling_down": bool(cooldown and cooldown > now),
                "cooldown_until": _iso(cooldown),
                "last_error_kind": stat.get("last_error_kind"),
            })
        rows.sort(key=lambda x: x["score"], reverse=True)
        return {
            "version": SCHEMA_VERSION,
            "updated_at": self.data.get("updated_at"),
            "totals": dict(self.data.get("totals") or {}),
            "methods": rows,
            "policy": "검색방법의 운영 성공률만 학습하며 출처의 공식성·사실성은 승격하지 않음. 차단 경로는 임시 cooldown 후 재탐색.",
        }


if __name__ == "__main__":
    learner = SearchMethodLearner()
    print(json.dumps(learner.report(), ensure_ascii=False, indent=2))
