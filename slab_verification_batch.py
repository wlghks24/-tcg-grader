#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch official slab-cert verification with checkpointing and site-block protection.

Only official grading-company hosts are queried. OCR/seller text never becomes
verified evidence by itself. The runner records HTTP status details and opens a
per-company circuit breaker after repeated blocking/rate-limit responses, so a
mobile run does not hammer a site protected by CAPTCHA/WAF.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from grading_cert_verifier import verify_cert


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("queue", type=Path, help="Verification queue JSON from library_slab_corpus.py")
    parser.add_argument("--registry", type=Path, default=Path("library_official_cert_registry.json"))
    parser.add_argument("--state", type=Path, default=Path("slab_official_verification_state.json"))
    parser.add_argument("--limit", type=int, default=25, help="Actual official lookups this run; 0 means all eligible candidates.")
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds between official-site requests.")
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument("--companies", default="", help="Optional comma-separated filter, e.g. PSA,CGC")
    parser.add_argument("--retry-errors", action="store_true", help="Retry prior lookup_error/not_verified/site_blocked rows.")
    parser.add_argument("--circuit-break", type=int, default=3, help="Pause one company after N consecutive blocked/rate-limited responses; 0 disables.")
    args = parser.parse_args()

    queue_payload = load_json(args.queue, {})
    queue_rows = queue_payload.get("records", []) if isinstance(queue_payload, dict) else []
    if not isinstance(queue_rows, list):
        raise SystemExit("queue records must be a list")
    registry = load_json(args.registry, {"schema_version": 1, "certifications": []})
    if not isinstance(registry, dict):
        raise SystemExit("registry must be a JSON object")
    state = load_json(args.state, {"schema_version": 2, "created_at": utc_now(), "results": {}})
    if not isinstance(state, dict):
        state = {"schema_version": 2, "created_at": utc_now(), "results": {}}
    state["schema_version"] = 2
    results = state.setdefault("results", {})
    if not isinstance(results, dict):
        results = {}
        state["results"] = results

    company_filter = {x.strip().upper() for x in args.companies.split(",") if x.strip()}
    existing_registry = {
        row_key(row.get("company", ""), row.get("certification_id", ""))
        for row in registry.get("certifications", [])
        if isinstance(row, dict) and row.get("officially_verified") is True
    }

    candidates: list[dict[str, Any]] = []
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
        candidates.append(row)

    lookup_limit = len(candidates) if args.limit <= 0 else min(args.limit, len(candidates))
    print(json.dumps({
        "queue_records": len(queue_rows),
        "remaining_candidates": len(candidates),
        "lookup_limit_this_run": lookup_limit,
        "registry_verified_entries": len(existing_registry),
        "delay_seconds": max(0.0, args.delay),
        "company_filter": sorted(company_filter),
        "circuit_break_after": max(0, args.circuit_break),
    }, ensure_ascii=False), flush=True)

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

        if result.get("blocked_or_challenged"):
            consecutive_blocked[company] += 1
            threshold = max(0, args.circuit_break)
            if threshold and consecutive_blocked[company] >= threshold:
                blocked_companies.add(company)
                print(f"[circuit-break] {company} paused after {consecutive_blocked[company]} blocked responses", flush=True)
        else:
            consecutive_blocked[company] = 0

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
    summary = {
        "processed_this_run": lookups_done,
        "run_status_counts": dict(sorted(run_counts.items())),
        "run_http_status_counts": dict(sorted(http_counts.items())),
        "blocked_companies": sorted(blocked_companies),
        "deferred_by_circuit": dict(sorted(deferred_by_circuit.items())),
        "state_status_counts": dict(sorted(all_statuses.items())),
        "state_records": len(results),
        "registry_certifications": len(registry.get("certifications", [])),
        "remaining_eligible_estimate": max(0, len(candidates) - lookups_done),
    }
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
