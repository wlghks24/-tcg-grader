#!/usr/bin/env python3
"""Fail-closed verification for freshly collected TCG data.

This gate does not collect data and does not rewrite learned source code. It validates
freshness, provenance, structural contracts, critical-output status, and source-health
coverage after an existing collection cycle. 403/429 are treated as blocked/degraded
source conditions, never as authorization to bypass a provider.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
CRITICAL_FILES = ("releases.json", "market_prices.json", "promo_events.json", "exchange_rates.json")
ALLOWED_REGIONS = {"KR", "JP", "US", "ALL"}
HTTP_BLOCK_RE = re.compile(r"HTTPError: status (403|429)\b", re.I)
TRANSIENT_RE = re.compile(r"HTTPError: status (?:408|425|429|5(?:00|02|03|04))\b|URLError|TimeoutError|timed out|connection reset|name resolution|DNS", re.I)


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON {path.name}: {type(exc).__name__}") from exc


def _parse_time(value: Any) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _fresh(label: str, value: Any, now: dt.datetime, max_age: int, findings: list[dict[str, Any]]) -> None:
    parsed = _parse_time(value)
    if parsed is None:
        findings.append({"severity": "critical", "code": "MISSING_OR_INVALID_TIMESTAMP", "target": label})
        return
    age = (now - parsed).total_seconds()
    if age < -300:
        findings.append({"severity": "critical", "code": "FUTURE_TIMESTAMP", "target": label, "age_seconds": round(age, 1)})
    elif age > max_age:
        findings.append({"severity": "high", "code": "STALE_COLLECTION_STATE", "target": label, "age_seconds": round(age, 1)})


def _valid_public_https(url: Any) -> bool:
    try:
        parsed = urlparse(str(url or ""))
    except ValueError:
        return False
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or not host or host in {"localhost", "127.0.0.1", "::1"}:
        return False
    return True


def _audit_health(root: Path, now: dt.datetime, max_age: int, findings: list[dict[str, Any]]) -> dict[str, int]:
    source = _load(root / "source_collection_stats.json")
    adaptive = _load(root / "adaptive_collection_stats.json")
    sources = source.get("sources") if isinstance(source, dict) else None
    jobs = adaptive.get("jobs") if isinstance(adaptive, dict) else None
    if not isinstance(sources, dict) or not sources:
        findings.append({"severity": "critical", "code": "EMPTY_SOURCE_HEALTH", "target": "source_collection_stats.json"})
        source_count = 0
    else:
        source_count = len(sources)
    if not isinstance(jobs, dict) or not jobs:
        findings.append({"severity": "critical", "code": "EMPTY_ADAPTIVE_HEALTH", "target": "adaptive_collection_stats.json"})
        job_count = 0
    else:
        job_count = len(jobs)
    _fresh("source_collection_stats.json", source.get("updated_at") if isinstance(source, dict) else None, now, max_age, findings)
    _fresh("adaptive_collection_stats.json", adaptive.get("updated_at") if isinstance(adaptive, dict) else None, now, max_age, findings)
    return {"source_count": source_count, "adaptive_job_count": job_count}


def _audit_market(root: Path, now: dt.datetime, findings: list[dict[str, Any]]) -> dict[str, int]:
    db = _load(root / "market_prices.json")
    entries = db.get("entries") if isinstance(db, dict) else None
    if not isinstance(entries, dict) or not entries:
        findings.append({"severity": "critical", "code": "EMPTY_MARKET_ENTRIES", "target": "market_prices.json"})
        return {"market_entries": 0}
    bad = 0
    for key, row in entries.items():
        reasons = []
        if not isinstance(key, str) or key.count("|") != 2:
            reasons.append("bad_key")
        if not isinstance(row, dict):
            reasons.append("not_object")
        else:
            if not str(row.get("display") or "").strip(): reasons.append("missing_display")
            if not _valid_public_https(row.get("source")): reasons.append("invalid_source")
            source_date = row.get("source_date")
            if source_date:
                try: dt.date.fromisoformat(str(source_date))
                except ValueError: reasons.append("invalid_source_date")
        if reasons:
            bad += 1
            if bad <= 20:
                findings.append({"severity": "high", "code": "INVALID_MARKET_ENTRY", "target": str(key)[:160], "reasons": reasons})
    if bad > 20:
        findings.append({"severity": "high", "code": "INVALID_MARKET_ENTRY_OVERFLOW", "count": bad - 20})
    updated = db.get("updated_at") if isinstance(db, dict) else None
    if updated:
        _fresh("market_prices.json", updated, now, 24 * 3600, findings)
    return {"market_entries": len(entries), "invalid_market_entries": bad}


def _audit_releases(root: Path, findings: list[dict[str, Any]]) -> dict[str, int]:
    db = _load(root / "releases.json")
    rows = db.get("items") if isinstance(db, dict) else None
    if not isinstance(rows, list) or not rows:
        findings.append({"severity": "critical", "code": "EMPTY_RELEASES", "target": "releases.json"})
        return {"release_items": 0}
    invalid = 0
    for idx, row in enumerate(rows):
        reasons = []
        if not isinstance(row, dict): reasons.append("not_object")
        else:
            if not str(row.get("game") or "").strip(): reasons.append("missing_game")
            if str(row.get("region") or "").upper() not in ALLOWED_REGIONS: reasons.append("bad_region")
            if not str(row.get("name") or "").strip(): reasons.append("missing_name")
            if not _valid_public_https(row.get("source")): reasons.append("invalid_source")
            if row.get("release_date"):
                try: dt.date.fromisoformat(str(row["release_date"]))
                except ValueError: reasons.append("bad_release_date")
        if reasons:
            invalid += 1
            if invalid <= 20: findings.append({"severity": "high", "code": "INVALID_RELEASE_ROW", "target": idx, "reasons": reasons})
    return {"release_items": len(rows), "invalid_release_items": invalid}


def _audit_events(root: Path, findings: list[dict[str, Any]]) -> dict[str, int]:
    db = _load(root / "promo_events.json")
    rows = db.get("items") if isinstance(db, dict) else None
    if not isinstance(rows, list) or not rows:
        findings.append({"severity": "critical", "code": "EMPTY_PROMO_EVENTS", "target": "promo_events.json"})
        return {"promo_event_items": 0}
    invalid = 0
    for idx, row in enumerate(rows):
        reasons = []
        if not isinstance(row, dict): reasons.append("not_object")
        else:
            if str(row.get("region") or "").upper() not in ALLOWED_REGIONS: reasons.append("bad_region")
            if not str(row.get("category") or "").strip(): reasons.append("missing_category")
            if not str(row.get("name_ko") or row.get("name_native") or "").strip(): reasons.append("missing_name")
            if not _valid_public_https(row.get("source")): reasons.append("invalid_source")
            if str(row.get("source_grade") or "").lower() not in {"official", "primary", "verified", "", "secondary"}:
                reasons.append("unknown_source_grade")
        if reasons:
            invalid += 1
            if invalid <= 20: findings.append({"severity": "high", "code": "INVALID_EVENT_ROW", "target": idx, "reasons": reasons})
    return {"promo_event_items": len(rows), "invalid_promo_event_items": invalid}


def _audit_auto_update(root: Path, findings: list[dict[str, Any]]) -> dict[str, Any]:
    path = root / "auto_update_report.json"
    if not path.is_file():
        findings.append({"severity": "critical", "code": "MISSING_AUTO_UPDATE_REPORT", "target": path.name})
        return {"critical_outputs_seen": 0}
    report = _load(path)
    rows = report.get("results") if isinstance(report, dict) else None
    if not isinstance(rows, list):
        findings.append({"severity": "critical", "code": "INVALID_AUTO_UPDATE_REPORT", "target": path.name})
        return {"critical_outputs_seen": 0}
    by_file = {str(x.get("file")): x for x in rows if isinstance(x, dict)}
    seen = 0
    for filename in CRITICAL_FILES:
        row = by_file.get(filename)
        if row is None:
            findings.append({"severity": "critical", "code": "CRITICAL_OUTPUT_NOT_REPORTED", "target": filename})
            continue
        seen += 1
        errors = [str(x)[:300] for x in (row.get("remaining_collection_errors") or [])]
        blocked = [x for x in errors if HTTP_BLOCK_RE.search(x)]
        hard = [x for x in errors if not TRANSIENT_RE.search(x)]
        if row.get("ok") is not True and hard:
            findings.append({"severity": "critical", "code": "HARD_COLLECTION_FAILURE", "target": filename, "errors": hard[:5]})
        elif row.get("ok") is not True or errors:
            findings.append({"severity": "high", "code": "DEGRADED_COLLECTION_OUTPUT", "target": filename, "blocked_403_429": len(blocked), "errors": errors[:5]})
    return {"critical_outputs_seen": seen}


def verify(root: Path = ROOT, *, max_health_age_seconds: int = 900, now: dt.datetime | None = None) -> dict[str, Any]:
    now = now or dt.datetime.now(dt.timezone.utc)
    findings: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {}
    for func in (_audit_health,):
        metrics.update(func(root, now, max_health_age_seconds, findings))
    metrics.update(_audit_market(root, now, findings))
    metrics.update(_audit_releases(root, findings))
    metrics.update(_audit_events(root, findings))
    metrics.update(_audit_auto_update(root, findings))
    counts = {level: sum(x.get("severity") == level for x in findings) for level in ("critical", "high", "medium")}
    status = "fail_closed" if counts["critical"] else ("degraded" if counts["high"] else "pass")
    return {
        "schema_version": 1,
        "verified_at": now.isoformat(timespec="seconds"),
        "status": status,
        "counts": counts,
        "metrics": metrics,
        "findings": findings,
        "safety": {"bypass_403_429": False, "learned_text_executable": False, "source_code_auto_rewritten": False},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--max-health-age-seconds", type=int, default=900)
    parser.add_argument("--report", default="COLLECTION_VERIFICATION_REPORT.json")
    parser.add_argument("--fail-on-degraded", action="store_true")
    args = parser.parse_args()
    report = verify(Path(args.root), max_health_age_seconds=max(60, min(86400, args.max_health_age_seconds)))
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "counts": report["counts"], "metrics": report["metrics"]}, ensure_ascii=False))
    if report["status"] == "fail_closed": return 2
    if args.fail_on_degraded and report["status"] == "degraded": return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
