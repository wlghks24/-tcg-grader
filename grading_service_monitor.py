#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Official-source grading service, fee, turnaround and notice monitor.

Safety policy
-------------
* PSA/BGS/CGC/TAG/BRG official pages are the only sources allowed to change
  authoritative numeric values.
* Social/search/user supplied evidence is a recheck trigger only.  It can never
  overwrite a verified fee, turnaround, declared-value limit, service name or
  availability flag.
* A provider failure preserves the last-known-good verified snapshot.
* Verified changes are appended to a bounded history instead of silently
  replacing the previous state.
* Time-bounded notices use the same end-date + five-day lifecycle as the rest of
  the TCG information system.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import html as html_lib
import json
import re
import urllib.request
from pathlib import Path
from typing import Any

from safe_runtime import atomic_write_json, safe_read_text, safe_urlopen

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "grading_services.json"
CHANGES = ROOT / "grading_service_changes.json"
UA = "Mozilla/5.0 TCG-Grader-GradingServiceMonitor/215.1"
ARCHIVE_GRACE_DAYS = 5
MAX_CHANGE_HISTORY = 1000
MAX_PAGE_BYTES = 3_000_000

ALLOWED_HOSTS = {
    "www.psacard.com", "psacard.com",
    "www.beckett.com", "beckett.com",
    "www.cgccards.com", "cgccards.com",
    "taggrading.com", "www.taggrading.com",
    "break.co.kr", "www.break.co.kr",
}

# Static baselines are verified last-known-good values.  Live official parsing can
# update them; a failed/blocked page can only preserve them, never erase them.
PROFILES: dict[str, dict[str, Any]] = {
    "PSA_JP": {
        "provider": "PSA", "market": "JP", "currency": "JPY",
        "service_source": "https://www.psacard.com/ja-JP/services/submit-card",
        "notice_source": "https://www.psacard.com/ja-JP/articles",
        "services": [
            {"id": "standard", "name": "Standard", "aliases": ["スタンダード", "Standard"]},
            {"id": "priority", "name": "Priority", "aliases": ["プライオリティ", "Priority", "レギュラー"]},
            {"id": "express", "name": "Express", "aliases": ["エクスプレス", "Express"]},
            {"id": "super_express", "name": "Super Express", "aliases": ["スーパー・エクスプレス", "スーパー エクスプレス", "Super Express"]},
            {"id": "premier", "name": "Premier", "aliases": ["プレミア", "ウォーク・スルー", "Walk-Through", "Walk Through"]},
            {"id": "premium_1", "name": "Premium 1", "aliases": ["プレミアム1", "Premium 1"]},
            {"id": "premium_2", "name": "Premium 2", "aliases": ["プレミアム2", "Premium 2"]},
            {"id": "premium_3", "name": "Premium 3", "aliases": ["プレミアム3", "Premium 3"]},
            {"id": "premium_5", "name": "Premium 5", "aliases": ["プレミアム5", "Premium 5"]},
            {"id": "premium_10", "name": "Premium 10", "aliases": ["プレミアム10", "Premium 10"]},
        ],
        "baseline": [
            {"id": "priority", "name": "Regular", "fee": 11980, "turnaround_business_days": 60, "max_value": 250000},
            {"id": "express", "name": "Express", "fee": 22980, "turnaround_business_days": 25, "max_value": 400000},
            {"id": "super_express", "name": "Super Express", "fee": 44980, "turnaround_business_days": 25, "max_value": 750000},
            {"id": "premier", "name": "Walk-Through", "fee": 89980, "turnaround_business_days": 25, "max_value": 1500000},
            {"id": "premium_1", "name": "Premium 1", "fee": 149980, "turnaround_business_days": 25, "max_value": 4000000},
            {"id": "premium_2", "name": "Premium 2", "fee": 299980, "turnaround_business_days": 25, "max_value": 8000000},
            {"id": "premium_3", "name": "Premium 3", "fee": 449980, "turnaround_business_days": 25, "max_value": 15000000},
            {"id": "premium_5", "name": "Premium 5", "fee": 749980, "turnaround_business_days": 25, "max_value": 35000000},
            {"id": "premium_10", "name": "Premium 10", "fee": 1499980, "turnaround_business_days": 15, "min_value": 35000001},
        ],
    },
    "PSA_US": {
        "provider": "PSA", "market": "US", "currency": "USD",
        "service_source": "https://www.psacard.com/submit",
        "notice_source": "https://www.psacard.com/articles",
        "services": [
            {"id": "standard", "name": "Standard", "aliases": ["Standard"]},
            {"id": "regular", "name": "Regular", "aliases": ["Regular"]},
            {"id": "express", "name": "Express", "aliases": ["Express"]},
            {"id": "super_express", "name": "Super Express", "aliases": ["Super Express"]},
            {"id": "walk_through", "name": "Walk-Through", "aliases": ["Walk-Through", "Walk Through"]},
        ],
        # PSA official announcement, 2026-09-09.  Other tiers remain live-parsed
        # or are supplied by the legacy compatibility endpoint until reverified.
        "baseline": [
            {"id": "standard", "name": "Standard", "fee": 84.99,
             "turnaround_business_days_min": 100, "turnaround_business_days_max": 110,
             "max_value": 1400, "effective_date": "2026-09-14", "availability": "announced"},
        ],
    },
    "BGS_US": {
        "provider": "BGS", "market": "US", "currency": "USD",
        "service_source": "https://www.beckett.com/grading",
        "notice_source": "https://www.beckett.com/news/",
        "services": [
            {"id": "base", "name": "Base", "aliases": ["Base"]},
            {"id": "standard", "name": "Standard", "aliases": ["Standard"]},
            {"id": "express", "name": "Express", "aliases": ["Express"]},
            {"id": "priority", "name": "Priority", "aliases": ["Priority"]},
        ],
        "baseline": [
            {"id": "base", "name": "Base", "fee": 14.95, "turnaround_business_days": 75, "availability": "paused"},
            {"id": "standard", "name": "Standard", "fee": 34.95, "turnaround_business_days": 45, "availability": "paused"},
            {"id": "express", "name": "Express", "fee": 79.95, "turnaround_business_days": 15, "availability": "open"},
            {"id": "priority", "name": "Priority", "fee": 124.95, "turnaround_business_days": 5, "availability": "open"},
        ],
    },
    "CGC_US": {
        "provider": "CGC", "market": "US", "currency": "USD",
        "service_source": "https://www.cgccards.com/submit/services-fees/cgc-grading/?view=cards",
        "notice_source": "https://www.cgccards.com/news/",
        "services": [
            {"id": "bulk", "name": "Bulk", "aliases": ["Bulk"]},
            {"id": "economy", "name": "Economy", "aliases": ["Economy"]},
            {"id": "standard", "name": "Standard", "aliases": ["Standard"]},
            {"id": "express", "name": "Express", "aliases": ["Express"]},
            {"id": "walkthrough", "name": "WalkThrough", "aliases": ["WalkThrough", "Walk Through"]},
        ],
        "baseline": [
            {"id": "bulk", "name": "Bulk", "fee": 17.0, "turnaround_business_days": 150, "max_value": 500, "min_cards": 25},
            {"id": "economy", "name": "Economy", "fee": 20.0, "turnaround_business_days": 90, "max_value": 1000},
            {"id": "standard", "name": "Standard", "fee": 55.0, "turnaround_business_days": 10, "max_value": 3000},
            {"id": "express", "name": "Express", "fee": 100.0, "turnaround_business_days": 5, "max_value": 10000},
            {"id": "walkthrough", "name": "WalkThrough", "fee": 300.0, "turnaround_business_days": 2, "max_value": 100000},
        ],
    },
    "TAG_US": {
        "provider": "TAG", "market": "US", "currency": "USD",
        "service_source": "https://taggrading.com/pages/pricing",
        "notice_source": "https://taggrading.com/",
        "services": [
            {"id": "basic", "name": "Basic", "aliases": ["Basic"]},
            {"id": "standard", "name": "Standard", "aliases": ["Standard"]},
            {"id": "express", "name": "Express", "aliases": ["Express"]},
            {"id": "priority", "name": "Priority", "aliases": ["Priority"]},
            {"id": "walkthrough", "name": "Walkthrough", "aliases": ["Walkthrough", "Walk Through"]},
        ],
        "baseline": [
            {"id": "basic", "name": "Basic", "fee": 22.0},
            {"id": "standard", "name": "Standard", "fee": 39.0},
            {"id": "express", "name": "Express", "fee": 59.0},
            {"id": "priority", "name": "Priority", "fee": 149.0},
            {"id": "walkthrough", "name": "Walkthrough", "fee": 299.0},
        ],
    },
    "BRG_KR": {
        "provider": "BRG", "market": "KR", "currency": "KRW",
        "service_source": "https://break.co.kr/",
        "notice_source": "https://break.co.kr/",
        "services": [
            {"id": "regular", "name": "Regular", "aliases": ["Regular"]},
            {"id": "express", "name": "Express", "aliases": ["Express"]},
            {"id": "bulk", "name": "Bulk", "aliases": ["Bulk"]},
            {"id": "reholder", "name": "Reholder", "aliases": ["Reholder"]},
            {"id": "brg_gen", "name": "BRG GEN", "aliases": ["brg GEN", "BRG GEN"]},
        ],
        "baseline": [
            {"id": "regular", "name": "Regular", "fee": 19800, "turnaround_business_days": 20},
            {"id": "express", "name": "Express", "fee": 39800, "turnaround_business_days": 5},
            {"id": "bulk", "name": "Bulk", "fee": 13800, "turnaround_business_days": 25, "min_cards": 20},
            {"id": "reholder", "name": "Reholder", "fee": 9800, "turnaround_business_days": 10},
            {"id": "brg_gen", "name": "BRG GEN", "fee": 9800, "turnaround_business_days": 5},
        ],
    },
}

# The attached Instagram post is useful evidence that PSA JP should be rechecked,
# but it is not an authoritative feed.  Numeric details are deliberately absent.
RECHECK_TRIGGERS = [
    {
        "provider": "PSA", "market": "JP", "observed_date": "2026-09-10",
        "source_type": "user_supplied_social_screenshot",
        "verification_status": "candidate_only",
        "reason": "reported service-level addition/rename, fee and turnaround changes",
        "authoritative_overwrite_allowed": False,
    }
]

NOTICE_KEYWORDS = re.compile(
    r"(?:service|pricing|price|fee|turnaround|grading|event|promotion|campaign|"
    r"サービス|料金|価格|納期|イベント|キャンペーン|グレーディング|"
    r"서비스|요금|가격|납기|이벤트|프로모션|캠페인|공지)",
    re.I,
)


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(safe_read_text(path, max_bytes=4_000_000))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return copy.deepcopy(default)


def _html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html_lib.unescape(raw)).strip()


def _fetch(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept-Language": "ko,en-US;q=0.9,ja;q=0.8"},
    )
    with safe_urlopen(req, timeout=20, allowed_hosts=ALLOWED_HOSTS, max_redirects=3) as response:
        return _html_to_text(response.read(MAX_PAGE_BYTES).decode("utf-8", "ignore"))


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()


def _focused_notice_text(text: str) -> str:
    """Fingerprint only grading/service/event-like segments to reduce page-noise churn."""
    chunks: list[str] = []
    for match in NOTICE_KEYWORDS.finditer(text):
        start = max(0, match.start() - 180)
        end = min(len(text), match.end() + 420)
        chunk = re.sub(r"\s+", " ", text[start:end]).strip()
        if chunk and chunk not in chunks:
            chunks.append(chunk)
        if len(chunks) >= 20:
            break
    return " | ".join(chunks)[:12000]


def _find_window(text: str, aliases: list[str]) -> tuple[str, str] | None:
    best: tuple[int, str] | None = None
    for alias in aliases:
        match = re.search(re.escape(alias), text, re.I)
        if match and (best is None or match.start() < best[0]):
            best = (match.start(), alias)
    if best is None:
        return None
    start = max(0, best[0] - 50)
    end = min(len(text), best[0] + 560)
    return best[1], text[start:end]


def _price(window: str, currency: str) -> float | int | None:
    if currency == "JPY":
        values = [int(v.replace(",", "")) for v in re.findall(r"[￥¥]\s*([0-9][0-9,]*)", window)]
        return next((v for v in values if 1000 <= v <= 5_000_000), None)
    if currency == "KRW":
        values = [int(v.replace(",", "")) for v in re.findall(r"([0-9][0-9,]*)\s*원", window)]
        return next((v for v in values if 1000 <= v <= 5_000_000), None)
    values = [float(v.replace(",", "")) for v in re.findall(r"\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)", window)]
    return next((v for v in values if 5 <= v <= 20_000), None)


def _turnaround(window: str) -> int | None:
    patterns = (
        r"(\d{1,3})\s*(?:営業日|business days|working days)",
        r"영업일\s*(?:기준)?\s*(\d{1,3})\s*일",
        r"(?:Turnaround|納期).{0,35}?(\d{1,3})\s*(?:days|日)",
    )
    for pattern in patterns:
        match = re.search(pattern, window, re.I)
        if match:
            value = int(match.group(1))
            if 1 <= value <= 365:
                return value
    return None


def _max_value(window: str, currency: str) -> int | float | None:
    if currency == "JPY":
        match = re.search(r"(?:申告価格|declared value).{0,60}?[￥¥]\s*([0-9][0-9,]*)", window, re.I)
    elif currency == "KRW":
        match = re.search(r"(?:신고|최대|가액).{0,60}?([0-9][0-9,]*)\s*원", window, re.I)
    else:
        match = re.search(r"(?:Max\.?\s*Value|declared value).{0,80}?\$\s*([0-9][0-9,]*)", window, re.I)
    if not match:
        return None
    value = float(match.group(1).replace(",", ""))
    return int(value) if value.is_integer() else value


def _availability(window: str) -> str | None:
    lowered = window.lower()
    if any(token in lowered for token in ("sold out", "paused", "受付停止", "일시중지", "접수 중지")):
        return "paused"
    if any(token in lowered for token in ("submit now", "available", "受付中", "申し込む", "접수중", "접수 중")):
        return "open"
    return None


def _parse_services(text: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for profile in config["services"]:
        hit = _find_window(text, profile["aliases"])
        if not hit:
            continue
        alias, window = hit
        row: dict[str, Any] = {"id": profile["id"], "name": profile["name"], "matched_label": alias}
        fee = _price(window, config["currency"])
        turnaround = _turnaround(window)
        maximum = _max_value(window, config["currency"])
        availability = _availability(window)
        if fee is not None:
            row["fee"] = fee
        if turnaround is not None:
            row["turnaround_business_days"] = turnaround
        if maximum is not None:
            row["max_value"] = maximum
        if availability is not None:
            row["availability"] = availability
        # A label alone is not sufficient evidence for a live numeric/status update.
        if len(row) > 3:
            found.append(row)
    return found


def _merge_service_rows(previous: list[dict], baseline: list[dict], parsed: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for source in (baseline or [], previous or []):
        for row in source:
            if isinstance(row, dict) and row.get("id"):
                merged[row["id"]] = copy.deepcopy(row)
    for row in parsed:
        existing = merged.get(row["id"], {})
        existing.update(row)
        merged[row["id"]] = existing
    return list(merged.values())


def _service_changes(
    profile_key: str,
    before: list[dict],
    after: list[dict],
    checked_at: str,
    source: str,
) -> list[dict]:
    old = {r.get("id"): r for r in before if isinstance(r, dict) and r.get("id")}
    new = {r.get("id"): r for r in after if isinstance(r, dict) and r.get("id")}
    changes: list[dict] = []
    fields = {
        "fee": "price_change",
        "turnaround_business_days": "turnaround_change",
        "turnaround_business_days_min": "turnaround_change",
        "turnaround_business_days_max": "turnaround_change",
        "max_value": "value_limit_change",
        "min_value": "value_limit_change",
        "availability": "availability_change",
        "name": "service_rename",
    }
    for service_id, row in new.items():
        if service_id not in old:
            changes.append({
                "profile": profile_key, "service_id": service_id,
                "change_type": "service_added", "after": row,
                "detected_at": checked_at, "source": source, "verified": True,
            })
            continue
        for field, kind in fields.items():
            if field in row and field in old[service_id] and row.get(field) != old[service_id].get(field):
                changes.append({
                    "profile": profile_key, "service_id": service_id,
                    "change_type": kind, "field": field,
                    "before": old[service_id].get(field), "after": row.get(field),
                    "detected_at": checked_at, "source": source, "verified": True,
                })
    return changes


def lifecycle_state(end_date: str | None, today: dt.date | None = None) -> str:
    if not end_date:
        return "current"
    day = today or dt.datetime.now(dt.timezone.utc).date()
    try:
        end = dt.date.fromisoformat(str(end_date)[:10])
    except ValueError:
        return "current"
    if day <= end:
        return "current"
    if day <= end + dt.timedelta(days=ARCHIVE_GRACE_DAYS):
        return "recently_ended"
    return "archive"


def candidate_can_overwrite(candidate: dict[str, Any]) -> bool:
    return bool(
        candidate.get("source_type") == "official"
        and candidate.get("verification_status") == "verified"
    )


def _change_key(change: dict[str, Any]) -> str:
    stable = {
        key: change.get(key)
        for key in ("profile", "service_id", "change_type", "field", "before", "after", "source")
    }
    return _fingerprint(json.dumps(stable, ensure_ascii=False, sort_keys=True, default=str))


def _dedupe_changes(rows: list[dict]) -> list[dict]:
    seen: set[str] = set()
    result: list[dict] = []
    for row in reversed(rows):
        if not isinstance(row, dict):
            continue
        key = _change_key(row)
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
        if len(result) >= MAX_CHANGE_HISTORY:
            break
    return list(reversed(result))


def update() -> dict[str, Any]:
    previous = _read_json(OUT, {"profiles": {}})
    history = _read_json(CHANGES, {"changes": []})
    previous_profiles = previous.get("profiles", {}) if isinstance(previous, dict) else {}
    checked_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    profiles: dict[str, dict[str, Any]] = {}
    new_changes: list[dict[str, Any]] = []
    collection_errors: list[str] = []

    for key, config in PROFILES.items():
        old = previous_profiles.get(key, {}) if isinstance(previous_profiles, dict) else {}
        old_services = old.get("services", []) if isinstance(old, dict) else []
        row: dict[str, Any] = {
            "provider": config["provider"], "market": config["market"],
            "currency": config["currency"],
            "service_source": config["service_source"], "notice_source": config["notice_source"],
            "checked_at": checked_at, "source_ok": False,
            "verification_status": "last_known_good",
        }
        service_text = ""
        notice_text = ""
        errors: list[str] = []
        try:
            service_text = _fetch(config["service_source"])
        except (OSError, ValueError, TypeError) as exc:
            errors.append("service:" + type(exc).__name__)
        try:
            notice_text = service_text if config["notice_source"] == config["service_source"] else _fetch(config["notice_source"])
        except (OSError, ValueError, TypeError) as exc:
            errors.append("notice:" + type(exc).__name__)

        parsed = _parse_services(service_text, config) if service_text else []
        merged = _merge_service_rows(old_services, config.get("baseline", []), parsed)
        row["services"] = merged
        row["source_ok"] = bool(service_text)
        row["parsed_service_count"] = len(parsed)
        if service_text and parsed:
            row["verification_status"] = "official_verified"
        elif service_text:
            row["verification_status"] = "official_reachable_parse_degraded"
        if errors:
            row["source_errors"] = errors
            collection_errors.append(f"{key}:" + ",".join(errors))
        if service_text:
            row["service_fingerprint"] = _fingerprint(service_text)

        focused_notice = _focused_notice_text(notice_text) if notice_text else ""
        if focused_notice:
            row["notice_fingerprint"] = _fingerprint(focused_notice)
            row["notice_excerpt"] = focused_notice[:900]
            old_fingerprint = old.get("notice_fingerprint") if isinstance(old, dict) else None
            if old_fingerprint and old_fingerprint != row["notice_fingerprint"]:
                new_changes.append({
                    "profile": key,
                    "change_type": "official_notice_content_changed",
                    "detected_at": checked_at,
                    "source": config["notice_source"],
                    "verified": True,
                    "needs_review": True,
                })

        new_changes.extend(_service_changes(key, old_services, merged, checked_at, config["service_source"]))
        profiles[key] = row

    prior_changes = history.get("changes", []) if isinstance(history, dict) else []
    combined = _dedupe_changes([*prior_changes, *new_changes])
    result: dict[str, Any] = {
        "schema_version": 1,
        "engine": "grading-service-monitor-v215",
        "updated_at": checked_at,
        "checked_at": checked_at,
        "refresh_hours": 6,
        "archive_grace_days": ARCHIVE_GRACE_DAYS,
        "official_only_numeric_updates": True,
        "profiles": profiles,
        "recheck_triggers": RECHECK_TRIGGERS,
        "summary": {
            "profiles": len(profiles),
            "source_ok": sum(1 for row in profiles.values() if row.get("source_ok")),
            "official_verified_profiles": sum(1 for row in profiles.values() if row.get("verification_status") == "official_verified"),
            "new_changes": len(new_changes),
            "history_changes": len(combined),
        },
    }
    if collection_errors:
        # Partial source failures remain visible so auto_update_all can learn/retry,
        # while last-known-good values stay intact.
        result["collection_errors"] = collection_errors
    atomic_write_json(OUT, result, suffix=".grading-services.tmp")
    atomic_write_json(
        CHANGES,
        {
            "schema_version": 1,
            "engine": "grading-service-monitor-v215",
            "updated_at": checked_at,
            "archive_grace_days": ARCHIVE_GRACE_DAYS,
            "changes": combined,
        },
        suffix=".grading-service-changes.tmp",
    )
    return result


def main() -> int:
    result = update()
    print(json.dumps(result["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
