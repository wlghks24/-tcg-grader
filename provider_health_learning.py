#!/usr/bin/env python3
"""Persistent provider-health learner for discovery channels.

This learns operational reliability only; it never changes source trust/official status.
It records how often each provider responded, produced candidates, was selected,
and failed, then keeps a bounded EMA-style score for diagnostics and future routing.
"""
from __future__ import annotations

import json
from pathlib import Path

from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
MEMORY = ROOT / "collection_provider_health.json"
BACKUP = ROOT / "collection_provider_health.json.bak"
MAX_PROVIDERS = 40


def _fresh() -> dict:
    return {"version": 1, "providers": {}, "runs": 0}


def _load(path: Path = MEMORY, backup_path: Path | None = None) -> dict:
    backup = backup_path or path.with_suffix(path.suffix + ".bak")
    for candidate in (path, backup):
        try:
            data = json.loads(safe_read_text(candidate))
            if isinstance(data, dict) and isinstance(data.get("providers"), dict):
                return data
        except Exception:
            continue
    return _fresh()


def _num(value) -> int:
    try:
        return max(0, int(value))
    except Exception:
        return 0


def observe(provider_rows: list[dict], *, memory_path: Path = MEMORY, backup_path: Path | None = None) -> dict:
    memory_path = Path(memory_path)
    backup = Path(backup_path) if backup_path else memory_path.with_suffix(memory_path.suffix + ".bak")
    data = _load(memory_path, backup)
    data["runs"] = _num(data.get("runs")) + 1
    providers = data.setdefault("providers", {})
    for row in provider_rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("provider") or "unknown")[:80]
        stat = providers.setdefault(name, {})
        responded = bool(row.get("responded", True))
        results = _num(row.get("results"))
        selected = _num(row.get("selected"))
        errors = _num(row.get("errors"))
        stat["runs"] = _num(stat.get("runs")) + 1
        stat["responded"] = _num(stat.get("responded")) + (1 if responded else 0)
        stat["results"] = _num(stat.get("results")) + results
        stat["selected"] = _num(stat.get("selected")) + selected
        stat["errors"] = _num(stat.get("errors")) + errors
        sample = (1.0 if responded else -1.0) + min(2.0, results * 0.08) + min(1.5, selected * 0.15) - min(2.0, errors * 0.4)
        old = float(stat.get("score") or 0.0)
        stat["score"] = round(old * 0.82 + sample * 0.18, 4)
    if len(providers) > MAX_PROVIDERS:
        ranked = sorted(providers.items(), key=lambda kv: float(kv[1].get("score") or 0.0), reverse=True)
        data["providers"] = dict(ranked[:MAX_PROVIDERS])
    if memory_path.exists():
        try:
            atomic_write_json(backup, _load(memory_path, backup), suffix=".provider-health.bak.tmp")
        except Exception:
            pass
    atomic_write_json(memory_path, data, suffix=".provider-health.tmp")
    return report(data)


def report(data: dict | None = None) -> dict:
    data = data if isinstance(data, dict) else _load()
    rows = []
    for name, stat in (data.get("providers") or {}).items():
        runs = max(1, _num(stat.get("runs")))
        rows.append({
            "provider": name,
            "score": round(float(stat.get("score") or 0.0), 4),
            "runs": _num(stat.get("runs")),
            "response_rate": round(_num(stat.get("responded")) / runs, 4),
            "results": _num(stat.get("results")),
            "selected": _num(stat.get("selected")),
            "errors": _num(stat.get("errors")),
        })
    rows.sort(key=lambda x: (x["score"], x["selected"], x["results"]), reverse=True)
    return {"version": 1, "runs": _num(data.get("runs")), "providers": rows}


if __name__ == "__main__":
    print(json.dumps(report(), ensure_ascii=False, indent=2))
