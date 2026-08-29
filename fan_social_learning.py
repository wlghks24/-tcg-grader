#!/usr/bin/env python3
"""Device-local learning for public TCG fan/community social sources.

This learner optimizes discovery only. It never turns a fan/community account into
an official source. Official trust remains controlled by social_source_registry.json.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import urllib.parse
from pathlib import Path

from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
MEMORY = ROOT / "fan_social_learning.json"
BACKUP = ROOT / "fan_social_learning.json.bak"
SCHEMA_VERSION = 1
MAX_SOURCES = 300


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _int(value, default=0) -> int:
    try:
        return max(0, min(10_000_000, int(value)))
    except (TypeError, ValueError, OverflowError):
        return default


def _host(url: object) -> str:
    try:
        return (urllib.parse.urlsplit(str(url or "")).hostname or "").lower()
    except ValueError:
        return ""


def _fresh() -> dict:
    return {"version": SCHEMA_VERSION, "updated_at": None, "sources": {}, "runs": 0}


def _load(path: Path, backup: Path) -> dict:
    for candidate in (path, backup):
        try:
            data = json.loads(safe_read_text(candidate))
            if isinstance(data, dict) and isinstance(data.get("sources"), dict):
                data.setdefault("runs", 0)
                return data
        except Exception:
            continue
    return _fresh()


def _score(stat: dict) -> float:
    discovered = max(1, _int(stat.get("discovered"), 1))
    selected = _int(stat.get("selected"))
    corroborated = _int(stat.get("corroborated"))
    cross_rate = corroborated / discovered
    select_rate = selected / discovered
    exploration = 0.55 / math.sqrt(discovered)
    # This is utility/relevance only, not a trust score.
    return round(select_rate * 2.1 + cross_rate * 1.4 + exploration, 5)


def source_key(row: dict) -> str | None:
    explicit = str(row.get("fan_source_key") or "").strip().lower()
    if explicit:
        return explicit[:140]
    author = str(row.get("author") or "").strip().lower().lstrip("@")
    kind = str(row.get("source_kind") or "social").split("_", 1)[0].lower()
    if author:
        return f"{kind}:{author}"[:140]
    host = _host(row.get("source"))
    if host:
        return f"{kind}:{host}"[:140]
    return None


class FanSocialLearner:
    def __init__(self, memory_path: Path | str = MEMORY, backup_path: Path | str | None = None):
        self.memory_path = Path(memory_path)
        self.backup_path = Path(backup_path) if backup_path else self.memory_path.with_suffix(self.memory_path.suffix + ".bak")
        self.data = _load(self.memory_path, self.backup_path)
        self.data["runs"] = _int(self.data.get("runs")) + 1

    def _row(self, key: str) -> dict:
        return self.data.setdefault("sources", {}).setdefault(key[:140], {})

    def observe_discovered(self, rows: list[dict]) -> int:
        count = 0
        for item in rows:
            if not isinstance(item, dict) or item.get("fan_candidate") is not True:
                continue
            key = source_key(item)
            if not key:
                continue
            stat = self._row(key)
            stat["discovered"] = _int(stat.get("discovered")) + 1
            stat["game"] = str(item.get("game") or "")[:40]
            stat["region"] = str(item.get("region") or "")[:8]
            stat["author"] = str(item.get("author") or "")[:80]
            stat["platform"] = str(item.get("source_kind") or "social").split("_", 1)[0][:24]
            stat["known_watch_account"] = bool(item.get("fan_account_known"))
            stat["last_seen"] = _now()
            stat["score"] = _score(stat)
            count += 1
        return count

    def observe_selected(self, rows: list[dict]) -> int:
        count = 0
        for item in rows:
            if not isinstance(item, dict):
                continue
            keys = item.get("fan_sources") if isinstance(item.get("fan_sources"), list) else []
            if not keys and item.get("fan_candidate") is True:
                key = source_key(item)
                keys = [key] if key else []
            for key in dict.fromkeys(str(x).lower()[:140] for x in keys if x):
                stat = self._row(key)
                stat["selected"] = _int(stat.get("selected")) + 1
                if item.get("cross_checked") is True or int(item.get("independent_source_count") or 0) >= 2:
                    stat["corroborated"] = _int(stat.get("corroborated")) + 1
                stat["last_selected"] = _now()
                stat["score"] = _score(stat)
                count += 1
        return count

    def preferred_authors(self, game: str, region: str, limit: int = 6) -> list[str]:
        rows = []
        for key, stat in (self.data.get("sources") or {}).items():
            author = str(stat.get("author") or "").strip().lstrip("@")
            if not author or stat.get("game") != game or stat.get("region") != region:
                continue
            rows.append((_score(stat), _int(stat.get("corroborated")), _int(stat.get("selected")), author))
        rows.sort(reverse=True)
        return [author for _, _, _, author in rows[: max(1, min(12, int(limit)))] ]

    def save(self) -> None:
        sources = self.data.setdefault("sources", {})
        if len(sources) > MAX_SOURCES:
            ranked = sorted(sources.items(), key=lambda kv: (_score(kv[1]), _int(kv[1].get("selected"))), reverse=True)
            self.data["sources"] = dict(ranked[:MAX_SOURCES])
        self.data["version"] = SCHEMA_VERSION
        self.data["updated_at"] = _now()
        if self.memory_path.exists():
            try:
                atomic_write_json(self.backup_path, _load(self.memory_path, self.backup_path), suffix=".fan-social.bak.tmp")
            except Exception:
                pass
        atomic_write_json(self.memory_path, self.data, suffix=".fan-social.tmp")

    def report(self) -> dict:
        ranked = []
        for key, stat in (self.data.get("sources") or {}).items():
            discovered = max(1, _int(stat.get("discovered"), 1))
            ranked.append({
                "source": key,
                "game": stat.get("game"),
                "region": stat.get("region"),
                "author": stat.get("author"),
                "platform": stat.get("platform"),
                "known_watch_account": bool(stat.get("known_watch_account")),
                "discovered": _int(stat.get("discovered")),
                "selected": _int(stat.get("selected")),
                "corroborated": _int(stat.get("corroborated")),
                "selection_rate": round(_int(stat.get("selected")) / discovered, 4),
                "corroboration_rate": round(_int(stat.get("corroborated")) / discovered, 4),
                "utility_score": _score(stat),
                "last_seen": stat.get("last_seen"),
            })
        ranked.sort(key=lambda x: (x["utility_score"], x["corroborated"], x["selected"]), reverse=True)
        return {
            "version": SCHEMA_VERSION,
            "updated_at": self.data.get("updated_at"),
            "runs": _int(self.data.get("runs")),
            "sources": ranked[:80],
            "policy": "팬/커뮤니티 계정은 발견 유용성만 학습하며 공식성·사실성은 자동 승격하지 않음",
        }


if __name__ == "__main__":
    print(json.dumps(FanSocialLearner().report(), ensure_ascii=False, indent=2))
