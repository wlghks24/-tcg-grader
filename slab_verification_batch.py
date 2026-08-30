#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch official slab-cert verification with strict pacing and site protection.

Safety policy:
- only official grading-company hosts are queried through grading_cert_verifier;
- OCR/seller text never becomes verified evidence by itself;
- at most two official lookups are attempted per grading company per invocation;
- official requests are paced by at least 60 seconds between actual lookups;
- HTTP 403/429 (and other blocked/challenged responses) immediately stop that
  company for the current run and persist a per-company cooldown;
- repeated 403/429 responses increase that company's cooldown instead of trying
  to bypass access controls;
- every block triggers one local code/policy self-audit with no extra network call;
- the 60-second wait is skipped when no runnable official lookup remains;
- checkpoint state is written after every lookup so Termux/mobile runs can resume.
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

from grading_cert_verifier import OFFICIAL, verify_cert

MAX_LOOKUPS_PER_COMPANY = 2
MIN_DELAY_SECONDS = 60.0
IMMEDIATE_BLOCK_HTTP_STATUSES = {401, 403, 407, 429}
MAX_STORED_BLOCK_AUDITS = 100
BLOCK_STRIKE_RESET_SECONDS = 24 * 60 * 60


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
        if (
            str(row.get("company") or "").upper() == company
            and str(row.get("certification_id") or "") == cert
        ):
            old_grade = row.get("grade")
            if old_grade is not None and abs(float(old_grade) - float(grade)) > 1e-9:
                return False, "registry_grade_conflict"
            row.update({
                "grade": float(grade),
                "officially_verified": True,
                "official_reference_url": result.get("official_url"),
                "verification_note": (
                    "Official grading-company page matched company, certification "
                    "and grade via slab verification batch."
                ),
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
        "verification_note": (
            "Official grading-company page matched company, certification and grade "
            "via slab verification batch."
        ),
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


def register_block(block_stats: dict[str, Any], company: str, http_status: Any) -> int:
    company = str(company or "").upper()
    now = utc_dt()
    previous = block_stats.get(company) if isinstance(block_stats.get(company), dict) else {}
    previous_at = parse_utc(previous.get("last_blocked_at"))
    previous_strikes = int(previous.get("consecutive_blocks", 0) or 0)
    if previous_at is None or (now - previous_at).total_seconds() > BLOCK_STRIKE_RESET_SECONDS:
        strikes = 1
    else:
        strikes = min(previous_strikes + 1, 8)
    block_stats[company] = {
        "consecutive_blocks": strikes,
        "last_http_status": int(http_status or 0) if str(http_status or "").isdigit() else http_status,
        "last_blocked_at": utc_now(),
    }
    return strikes


def reset_block_stats(block_stats: dict[str, Any], company: str) -> None:
    entry = block_stats.get(company)
    if isinstance(entry, dict):
        entry["consecutive_blocks"] = 0
        entry["last_success_at"] = utc_now()


def set_cooldown(
    cooldowns: dict[str, Any],
    company: str,
    result: dict[str, Any],
    strike_count: int = 1,
) -> dict[str, Any]:
    seconds = result.get("recommended_cooldown_seconds")
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        seconds = default_cooldown_seconds(result.get("http_status"))
    base = max(seconds, default_cooldown_seconds(result.get("http_status")), 60.0)
    multiplier = 2 ** min(max(int(strike_count) - 1, 0), 3)
    seconds = min(base * multiplier, 24 * 60 * 60.0)
    until = utc_dt() + timedelta(seconds=seconds)
    entry = {
        "until": until.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "reason": f"HTTP {result.get('http_status') or 'blocked'}",
        "seconds": int(seconds),
        "base_seconds": int(base),
        "strike_count": int(strike_count),
        "backoff_multiplier": int(multiplier),
        "set_at": utc_now(),
    }
    cooldowns[company] = entry
    return entry


def build_recovery_plan(
    company: str,
    http_status: Any,
    result: dict[str, Any],
    cooldown_entry: dict[str, Any] | None,
    strike_count: int,
) -> dict[str, Any]:
    try:
        status = int(http_status or 0)
    except (TypeError, ValueError):
        status = 0
    base = result.get("recovery") if isinstance(result.get("recovery"), dict) else {}
    manual_url = base.get("manual_verification_url") or (OFFICIAL.get(company) or {}).get("home")
    if status == 429:
        action = "wait_for_retry_after_or_adaptive_cooldown"
    elif status in {401, 403, 407}:
        action = (
            "manual_official_lookup_recommended_after_cooldown"
            if strike_count >= 2
            else "cooldown_then_retry_once_later"
        )
    else:
        action = "preserve_official_link_and_review"
    return {
        "company": company,
        "http_status": status,
        "block_kind": base.get("block_kind"),
        "action": action,
        "retry_after_seconds": result.get("retry_after_seconds"),
        "cooldown_until": (cooldown_entry or {}).get("until"),
        "cooldown_seconds": (cooldown_entry or {}).get("seconds"),
        "strike_count": strike_count,
        "manual_verification_url": manual_url,
        "do_not_bypass_access_controls": True,
    }


def build_block_self_audit(
    company: str,
    http_status: Any,
    cooldown_entry: dict[str, Any] | None,
    effective_delay: float,
) -> dict[str, Any]:
    try:
        status = int(http_status or 0)
    except (TypeError, ValueError):
        status = 0
    until = parse_utc((cooldown_entry or {}).get("until"))
    checks = {
        "known_official_company": company in OFFICIAL,
        "company_cap_is_two": MAX_LOOKUPS_PER_COMPANY == 2,
        "minimum_delay_is_60s_or_more": MIN_DELAY_SECONDS >= 60.0 and effective_delay >= 60.0,
        "blocked_status_is_immediate_stop": status in IMMEDIATE_BLOCK_HTTP_STATUSES,
        "cooldown_is_active": until is not None and until > utc_dt(),
        "network_retry_for_block_is_suppressed": True,
    }
    return {
        "ran_at": utc_now(),
        "company": company,
        "http_status": status,
        "checks": checks,
        "passed": all(checks.values()),
        "action": "local_policy_audit_only_no_network_retry",
    }


def has_future_runnable_candidate(
    candidates: list[dict[str, Any]],
    start_index: int,
    lookup_limit: int,
    lookups_done: int,
    blocked_companies: set[str],
    run_company_counts: Counter[str],
    cooldowns: dict[str, Any],
) -> bool:
    if lookups_done >= lookup_limit:
        return False
    for row in candidates[start_index:]:
        if not isinstance(row, dict):
            continue
        company = str(row.get("company") or "").upper()
        if not company or company in blocked_companies:
            continue
        if run_company_counts[company] >= MAX_LOOKUPS_PER_COMPANY:
            continue
        if active_cooldown(cooldowns, company):
            continue
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("queue", type=Path, help="Verification queue JSON from library_slab_corpus.py")
    parser.add_argument("--registry", type=Path, default=Path("library_official_cert_registry.json"))
    parser.add_argument("--state", type=Path, default=Path("slab_official_verification_state.json"))
    parser.add_argument("--limit", type=int, default=25, help="Overall lookup budget; hard cap of 2 lookups per company is always enforced.")
    parser.add_argument("--delay", type=float, default=MIN_DELAY_SECONDS, help="Seconds between official-site requests. Values below 60 are raised to 60.")
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument("--companies", default="", help="Optional comma-separated filter, e.g. PSA,BGS,CGC,TAG,BRG")
    parser.add_argument("--retry-errors", action="store_true", help="Retry prior lookup_error/not_verified/site_blocked rows only after cooldown.")
    parser.add_argument("--circuit-break", type=int, default=1, help="Compatibility option. 403/429/blocked responses always stop the company immediately.")
    args = parser.parse_args()

    effective_delay = max(MIN_DELAY_SECONDS, float(args.delay or 0.0))
    queue_payload = load_json(args.queue, {})
    queue_rows = queue_payload.get("records", []) if isinstance(queue_payload, dict) else []
    if not isinstance(queue_rows, list):
        raise SystemExit("queue records must be a list")
    registry = load_json(args.registry, {"schema_version": 1, "certifications": []})
    if not isinstance(registry, dict):
        raise SystemExit("registry must be a JSON object")

    state = load_json(args.state, {"schema_version": 7, "created_at": utc_now(), "results": {}})
    if not isinstance(state, dict):
        state = {"schema_version": 7, "created_at": utc_now(), "results": {}}
    state["schema_version"] = 7
    results = state.setdefault("results", {})
    if not isinstance(results, dict):
        results = {}
        state["results"] = results
    cooldowns = state.setdefault("company_cooldowns", {})
    if not isinstance(cooldowns, dict):
        cooldowns = {}
        state["company_cooldowns"] = cooldowns
    infer_cooldowns(results, cooldowns)
    block_stats = state.setdefault("company_block_stats", {})
    if not isinstance(block_stats, dict):
        block_stats = {}
        state["company_block_stats"] = block_stats
    block_audits = state.setdefault("block_self_audits", [])
    if not isinstance(block_audits, list):
        block_audits = []
        state["block_self_audits"] = block_audits

    company_filter = {x.strip().upper() for x in args.companies.split(",") if x.strip()}
    existing_registry = {
        row_key(row.get("company", ""), row.get("certification_id", ""))
        for row in registry.get("certifications", [])
        if isinstance(row, dict) and row.get("officially_verified") is True
    }
    candidates: list[dict[str, Any]] = []
    deferred_by_cooldown: Counter[str] = Counter()
    candidate_counts: Counter[str] = Counter()
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
            terminal = {"official_verified_match", "official_verified", "official_verified_ocr_grade_conflict", "official_not_found"}
            retryable = {"lookup_error", "not_verified", "site_blocked"}
            if status in terminal or (status in retryable and not args.retry_errors):
                continue
        if active_cooldown(cooldowns, company):
            deferred_by_cooldown[company] += 1
            continue
        candidates.append(row)
        candidate_counts[company] += 1

    possible_with_company_cap = sum(min(MAX_LOOKUPS_PER_COMPANY, count) for count in candidate_counts.values())
    requested_limit = possible_with_company_cap if args.limit <= 0 else max(0, args.limit)
    lookup_limit = min(requested_limit, possible_with_company_cap)
    active_cooldowns = {company: entry for company in sorted(cooldowns) if (entry := active_cooldown(cooldowns, company)) is not None}
    state["updated_at"] = utc_now()
    atomic_write_json(args.state, state)
    print(json.dumps({
        "queue_records": len(queue_rows),
        "remaining_candidates": len(candidates),
        "lookup_limit_this_run": lookup_limit,
        "max_lookups_per_company": MAX_LOOKUPS_PER_COMPANY,
        "minimum_delay_seconds": MIN_DELAY_SECONDS,
        "effective_delay_seconds": effective_delay,
        "immediate_stop_http_statuses": sorted(IMMEDIATE_BLOCK_HTTP_STATUSES),
        "block_self_audit_enabled": True,
        "adaptive_block_backoff_enabled": True,
        "skip_idle_pacing_enabled": True,
        "eligible_by_company": dict(sorted(candidate_counts.items())),
        "registry_verified_entries": len(existing_registry),
        "company_filter": sorted(company_filter),
        "active_company_cooldowns": active_cooldowns,
        "deferred_by_cooldown": dict(sorted(deferred_by_cooldown.items())),
    }, ensure_ascii=False), flush=True)
    if not candidates or lookup_limit <= 0:
        return 0

    run_counts: Counter[str] = Counter()
    http_counts: Counter[str] = Counter()
    blocked_companies: set[str] = set()
    deferred_by_circuit: Counter[str] = Counter()
    deferred_by_company_cap: Counter[str] = Counter()
    run_company_counts: Counter[str] = Counter()
    run_block_audits: list[dict[str, Any]] = []
    run_recovery_plans: list[dict[str, Any]] = []
    lookups_done = 0
    skipped_idle_waits = 0

    for index, row in enumerate(candidates):
        if lookups_done >= lookup_limit:
            break
        company = str(row.get("company") or "").upper()
        cert = str(row.get("certification_id") or "")
        if company in blocked_companies:
            deferred_by_circuit[company] += 1
            continue
        if run_company_counts[company] >= MAX_LOOKUPS_PER_COMPANY:
            deferred_by_company_cap[company] += 1
            continue
        if active_cooldown(cooldowns, company):
            deferred_by_cooldown[company] += 1
            continue

        expected = row.get("label_grade_candidate")
        key = row_key(company, cert)
        lookups_done += 1
        run_company_counts[company] += 1
        print(f"[official-verify] {lookups_done}/{lookup_limit} {company} {cert} (company {run_company_counts[company]}/{MAX_LOOKUPS_PER_COMPANY})", flush=True)
        result = verify_cert(company, cert, expected_grade=expected, timeout=args.timeout)
        status = classify_result(result)
        run_counts[status] += 1
        http_status = result.get("http_status")
        if http_status is not None:
            http_counts[f"{company}:{http_status}"] += 1

        cooldown_entry = None
        block_audit = None
        recovery_plan = None
        strike_count = 0
        blocked_now = bool(result.get("blocked_or_challenged"))
        try:
            blocked_now = blocked_now or int(http_status or 0) in IMMEDIATE_BLOCK_HTTP_STATUSES
        except (TypeError, ValueError):
            pass
        if blocked_now:
            strike_count = register_block(block_stats, company, http_status)
            cooldown_entry = set_cooldown(cooldowns, company, result, strike_count=strike_count)
            blocked_companies.add(company)
            block_audit = build_block_self_audit(company, http_status, cooldown_entry, effective_delay)
            recovery_plan = build_recovery_plan(company, http_status, result, cooldown_entry, strike_count)
            run_block_audits.append(block_audit)
            run_recovery_plans.append(recovery_plan)
            block_audits.append(block_audit)
            if len(block_audits) > MAX_STORED_BLOCK_AUDITS:
                del block_audits[:-MAX_STORED_BLOCK_AUDITS]
            print(f"[circuit-break] {company} stopped immediately after HTTP {http_status or 'blocked'}; cooldown until {cooldown_entry['until']} (strike={strike_count}, x{cooldown_entry['backoff_multiplier']})", flush=True)
            print(f"[block-self-audit] {company} HTTP {http_status or 'blocked'} passed={block_audit['passed']} no-network-retry=True", flush=True)
            print(f"[block-recovery] {company} action={recovery_plan['action']} manual={recovery_plan['manual_verification_url']}", flush=True)
        else:
            cooldowns.pop(company, None)
            try:
                if http_status is not None and int(http_status) < 400:
                    reset_block_stats(block_stats, company)
            except (TypeError, ValueError):
                pass

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
            "blocked_or_challenged": blocked_now,
            "transient_error": bool(result.get("transient_error")),
            "retry_after_seconds": result.get("retry_after_seconds"),
            "recommended_cooldown_seconds": result.get("recommended_cooldown_seconds"),
            "retry_suppressed": bool(result.get("retry_suppressed")),
            "cooldown_until": cooldown_entry.get("until") if cooldown_entry else None,
            "block_strike_count": strike_count or None,
            "block_self_audit": block_audit,
            "recovery_plan": recovery_plan or result.get("recovery"),
            "notice": result.get("notice"),
            "evidence": result.get("evidence"),
            "registry_action": registry_action,
        }
        state["updated_at"] = utc_now()
        state["source_queue"] = str(args.queue)
        atomic_write_json(args.state, state)

        if has_future_runnable_candidate(candidates, index + 1, lookup_limit, lookups_done, blocked_companies, run_company_counts, cooldowns):
            print(f"[pacing] waiting {effective_delay:.0f}s before next official lookup", flush=True)
            time.sleep(effective_delay)
        elif lookups_done < lookup_limit:
            skipped_idle_waits += 1
            print("[pacing] skipped: no runnable official lookup remains in this run", flush=True)

    all_statuses = Counter(value.get("status") for value in results.values() if isinstance(value, dict) and value.get("status"))
    active_cooldowns = {company: entry for company in sorted(cooldowns) if (entry := active_cooldown(cooldowns, company)) is not None}
    summary = {
        "processed_this_run": lookups_done,
        "processed_by_company": dict(sorted(run_company_counts.items())),
        "max_lookups_per_company": MAX_LOOKUPS_PER_COMPANY,
        "effective_delay_seconds": effective_delay,
        "skipped_idle_pacing_waits": skipped_idle_waits,
        "run_status_counts": dict(sorted(run_counts.items())),
        "run_http_status_counts": dict(sorted(http_counts.items())),
        "blocked_companies": sorted(blocked_companies),
        "block_self_audits_this_run": run_block_audits,
        "block_recovery_plans_this_run": run_recovery_plans,
        "company_block_stats": block_stats,
        "active_company_cooldowns": active_cooldowns,
        "deferred_by_circuit": dict(sorted(deferred_by_circuit.items())),
        "deferred_by_company_cap": dict(sorted(deferred_by_company_cap.items())),
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
