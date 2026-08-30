#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch official slab-cert verification with checkpointing and site-block protection.

Only official grading-company hosts are queried. OCR/seller text never becomes
verified evidence by itself. The runner records HTTP status details, opens a
per-company circuit breaker after blocking/rate-limit responses, and persists a
cooldown so a later mobile/Termux command cannot immediately hammer the same
protected official site again.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from grading_cert_verifier import verify_cert


def utc_dt() -> datetime:
    return datetime.now(timezone.utc)


def utc_now() -> str:
    return utc_dt().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_utc(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def row_key(company: str, cert: str) -> str:
    return f"{str(company).upper()}:{str(cert)}"


def official_evidence_confirmed(result: dict[str, Any]) -> bool:
    evidence = result.get("evidence") or {}
    return bool(
        result.get("ok")
        and evidence.get("company_match")
        and evidence.get("cert_match")
        and not evidence.get("failure_marker")
        and result.get("grade") is not None
    )


def upsert_registry(registry: dict[str, Any], result: dict[str, Any]) -> tuple[bool, str]:
    company = str(result.get("company") or "").upper()
    cert = str(result.get("certification_id") or "")
    grade = result.get("grade")
    if not company or not cert or grade is None:
        return False, "missing_official_fields"
    rows = registry.setdefault("certifications", [])
    for row in rows:
        if str(row.get("company") or "").upper() == company and str(row.get("certification_id") or "") == cert:
            old_grade = row.get("grade")
            if old_grade is not None and abs(float(old_grade) - float(grade)) > 1e-9:
                return False, "registry_grade_conflict"
            row.update({
                "grade": float(grade),
                "officially_verified": True,
                "official_reference_url": result.get("official_url"),
                "verification_note": "Official grading-company page matched company, certification and grade via slab verification batch.",
            })
            return True, "registry_updated"
    rows.append({
        "company": company,
        "certification_id": cert,
        "grade": float(grade),
        "card_name": None,
        "game": "unknown",
        "officially_verified": True,
        "official_reference_url": result.get("official_url"),
        "verification_note": "Official grading-company page matched company, certification and grade via slab verification batch.",
    })
    return True, "registry_added"


def classify_result(result: dict[str, Any]) -> str:
    if result.get("verified") is True:
        return "official_verified_match"
    if official_evidence_confirmed(result):
        return "official_verified_ocr_grade_conflict" if result.get("conflict") else "official_verified"
    if result.get("blocked_or_challenged"):
        return "site_blocked"
    if result.get("lookup_error"):
        return "lookup_error"
    if (result.get("evidence") or {}).get("failure_marker"):
        return "official_not_found"
    return "not_verified"


def default_cooldown_seconds(http_status: Any) -> float:
    try:
        status = int(http_status or 0)
    except (TypeError, ValueError):
        status = 0
    if status == 429:
        return 30 * 60.0
    if status in {401, 403, 407}:
        return 2 * 60 * 60.0
    return 15 * 60.0


def infer_cooldowns(results: dict[str, Any], cooldowns: dict[str, Any]) -> None:
    """Migrate older state files by deriving cooldowns from recent blocked rows."""
    now = utc_dt()
    for value in results.values():
        if not isinstance(value, dict) or value.get("status") != "site_blocked":
            continue
        company = str(value.get("company") or "").upper()
        checked = parse_utc(value.get("checked_at"))
        if not company or checked is None:
            continue
        until = checked + timedelta(seconds=default_cooldown_seconds(value.get("http_status")))
        if until <= now:
            continue
        current = cooldowns.get(company) if isinstance(cooldowns.get(company), dict) else {}
        current_until = parse_utc(current.get("until"))
        if current_until is None or until > current_until:
            cooldowns[company] = {
                "until": until.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "reason": f"HTTP {value.get('http_status') or 'blocked'}",
                "source": "migrated_from_blocked_result",
            }


def active_cooldown(cooldowns: dict[str, Any], company: str) -> dict[str, Any] | None:
    entry = cooldowns.get(company)
    if not isinstance(entry, dict):
        return None
    until = parse_utc(entry.get("until"))
    if until is None or until <= utc_dt():
        cooldowns.pop(company, None)
        return None
    return entry


def set_cooldown(cooldowns: dict[str, Any], company: str, result: dict[str, Any]) -> dict[str, Any]:
    seconds = result.get("recommended_cooldown_seconds")
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        seconds = default_cooldown_seconds(result.get("http_status"))
    seconds = max(60.0, min(seconds, 24 * 60 * 60.0))
    until = utc_dt() + timedelta(seconds=seconds)
    entry = {
        "until": until.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "reason": f"HTTP {result.get('http_status') or 'blocked'}",
        "seconds": int(seconds),
        "set_at": utc_now(),
    }
    cooldowns[company] = entry
    return entry


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("queue", type=Path, help="Verification queue JSON from library_slab_corpus.py")
    parser.add_argument("--registry", type=Path, default=Path("library_official_cert_registry.json"))
    parser.add_argument("--state", type=Path, default=Path("slab_official_verification_state.json"))
    parser.add_argument("--limit", type=int, default=25, help="Actual official lookups this run; 0 means all eligible candidates.")
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds between official-site requests.")
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument("--companies", default="", help="Optional comma-separated filter, e.g. PSA,CGC")
    parser.add_argument("--retry-errors", action="store_true", help="Retry prior lookup_error/not_verified/site_blocked rows after cooldown.")
    parser.add_argument("--circuit-break", type=int, default=3, help="Pause one company after N consecutive blocked/rate-limited responses; 0 disables.")
    args = parser.parse_args()

    queue_payload = load_json(args.queue, {})
    queue_rows = queue_payload.get("records", []) if isinstance(queue_payload, dict) else []
    if not isinstance(queue_rows, list):
        raise SystemExit("queue records must be a list")
    registry = load_json(args.registry, {"schema_version": 1, "certifications": []})
    if not isinstance(registry, dict):
        raise SystemExit("registry must be a JSON object")
    state = load_json(args.state, {"schema_version": 3, "created_at": utc_now(), "results": {}})
    if not isinstance(state, dict):
        state = {"schema_version": 3, "created_at": utc_now(), "results": {}}
    state["schema_version"] = 3
    results = state.setdefault("results", {})
    if not isinstance(results, dict):
        results = {}
        state["results"] = results
    cooldowns = state.setdefault("company_cooldowns", {})
    if not isinstance(cooldowns, dict):
        cooldowns = {}
        state["company_cooldowns"] = cooldowns
    infer_cooldowns(results, cooldowns)

    company_filter = {x.strip().upper() for x in args.companies.split(",") if x.strip()}
    existing_registry = {
        row_key(row.get("company", ""), row.get("certification_id", ""))
        for row in registry.get("certifications", [])
        if isinstance(row, dict) and row.get("officially_verified") is True
    }

    candidates: list[dict[str, Any]] = []
    deferred_by_cooldown: Counter[str] = Counter()
    for row in queue_rows:
        if not isinstance(row, dict):
            continue
        company = str(row.get("company") or "").upper()
        cert = str(row.get("certification_id") or "")
        if not company or not cert or (company_filter and company not in company_filter):
            continue
        key = row_key(company, cert)
        if key in existing_registry:
            continue
        previous = results.get(key) if isinstance(results.get(key), dict) else None
        if previous:
            status = previous.get("status")
            terminal = status in {
                "official_verified_match", "official_verified",
                "official_verified_ocr_grade_conflict", "official_not_found",
            }
            retryable = status in {"lookup_error", "not_verified", "site_blocked"}
            if terminal or (retryable and not args.retry_errors):
                continue
        if active_cooldown(cooldowns, company):
            deferred_by_cooldown[company] += 1
            continue
        candidates.append(row)

    lookup_limit = len(candidates) if args.limit <= 0 else min(args.limit, len(candidates))
    active_cooldowns = {
        company: entry for company in sorted(cooldowns)
        if (entry := active_cooldown(cooldowns, company)) is not None
    }
    state["updated_at"] = utc_now()
    atomic_write_json(args.state, state)
    print(json.dumps({
        "queue_records": len(queue_rows),
        "remaining_candidates": len(candidates),
        "lookup_limit_this_run": lookup_limit,
        "registry_verified_entries": len(existing_registry),
        "delay_seconds": max(0.0, args.delay),
        "company_filter": sorted(company_filter),
        "circuit_break_after": max(0, args.circuit_break),
        "active_company_cooldowns": active_cooldowns,
        "deferred_by_cooldown": dict(sorted(deferred_by_cooldown.items())),
    }, ensure_ascii=False), flush=True)

    if not candidates:
        return 0

    run_counts: Counter[str] = Counter()
    http_counts: Counter[str] = Counter()
    consecutive_blocked: Counter[str] = Counter()
    blocked_companies: set[str] = set()
    deferred_by_circuit: Counter[str] = Counter()
    lookups_done = 0

    for row in candidates:
        if lookups_done >= lookup_limit:
            break
        company = str(row.get("company") or "").upper()
        cert = str(row.get("certification_id") or "")
        if company in blocked_companies:
            deferred_by_circuit[company] += 1
            continue
        expected = row.get("label_grade_candidate")
        key = row_key(company, cert)
        lookups_done += 1
        print(f"[official-verify] {lookups_done}/{lookup_limit} {company} {cert}", flush=True)

        result = verify_cert(company, cert, expected_grade=expected, timeout=args.timeout)
        status = classify_result(result)
        run_counts[status] += 1
        http_status = result.get("http_status")
        if http_status is not None:
            http_counts[f"{company}:{http_status}"] += 1

        cooldown_entry = None
        if result.get("blocked_or_challenged"):
            consecutive_blocked[company] += 1
            cooldown_entry = set_cooldown(cooldowns, company, result)
            threshold = max(0, args.circuit_break)
            if threshold and consecutive_blocked[company] >= threshold:
                blocked_companies.add(company)
                print(
                    f"[circuit-break] {company} paused after {consecutive_blocked[company]} blocked responses; "
                    f"cooldown until {cooldown_entry['until']}",
                    flush=True,
                )
        else:
            consecutive_blocked[company] = 0
            cooldowns.pop(company, None)

        registry_action = None
        if official_evidence_confirmed(result):
            changed, registry_action = upsert_registry(registry, result)
            if changed:
                registry["updated_at"] = utc_now()
                atomic_write_json(args.registry, registry)

        previous = results.get(key) if isinstance(results.get(key), dict) else {}
        results[key] = {
            "company": company,
            "certification_id": cert,
            "label_grade_candidate": expected,
            "source_name": row.get("source_name"),
            "status": status,
            "checked_at": utc_now(),
            "attempts": int(previous.get("attempts", 0)) + 1,
            "official_grade": result.get("grade"),
            "official_url": result.get("official_url"),
            "final_url": result.get("final_url"),
            "verified": bool(result.get("verified")),
            "conflict": bool(result.get("conflict")),
            "lookup_error": result.get("lookup_error"),
            "http_status": result.get("http_status"),
            "blocked_or_challenged": bool(result.get("blocked_or_challenged")),
            "transient_error": bool(result.get("transient_error")),
            "retry_after_seconds": result.get("retry_after_seconds"),
            "recommended_cooldown_seconds": result.get("recommended_cooldown_seconds"),
            "cooldown_until": cooldown_entry.get("until") if cooldown_entry else None,
            "notice": result.get("notice"),
            "evidence": result.get("evidence"),
            "registry_action": registry_action,
        }
        state["updated_at"] = utc_now()
        state["source_queue"] = str(args.queue)
        atomic_write_json(args.state, state)
        if lookups_done < lookup_limit and args.delay > 0:
            time.sleep(max(0.0, args.delay))

    all_statuses = Counter(
        value.get("status") for value in results.values()
        if isinstance(value, dict) and value.get("status")
    )
    active_cooldowns = {
        company: entry for company in sorted(cooldowns)
        if (entry := active_cooldown(cooldowns, company)) is not None
    }
    summary = {
        "processed_this_run": lookups_done,
        "run_status_counts": dict(sorted(run_counts.items())),
        "run_http_status_counts": dict(sorted(http_counts.items())),
        "blocked_companies": sorted(blocked_companies),
        "active_company_cooldowns": active_cooldowns,
        "deferred_by_circuit": dict(sorted(deferred_by_circuit.items())),
        "deferred_by_cooldown": dict(sorted(deferred_by_cooldown.items())),
        "state_status_counts": dict(sorted(all_statuses.items())),
        "state_records": len(results),
        "registry_certifications": len(registry.get("certifications", [])),
        "remaining_eligible_estimate": max(0, len(candidates) - lookups_done),
    }
    state["updated_at"] = utc_now()
    atomic_write_json(args.state, state)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
