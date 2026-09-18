#!/usr/bin/env python3
"""Classify grading-provider health failures for RCA and alerting.

This module is deliberately read-only with respect to grading-company facts.  It
turns the watcher snapshot into operational diagnostics without changing source
allowlists, following blocked redirects, retrying 401/403/451 responses, or
promoting degraded/last-good data to fresh data.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
SNAPSHOT = ROOT / "grading_company_updates.json"
REPORT = ROOT / "GRADING_COMPANY_HEALTH_DIAGNOSTICS.json"
EXPECTED_COMPANIES = ("PSA", "BGS", "CGC", "TAG", "BRG")

_BLOCKED_RE = re.compile(r"HTTPError:\s*status\s*(401|403|451)\b", re.I)
_RATE_LIMIT_RE = re.compile(r"HTTPError:\s*status\s*429\b", re.I)
_TRANSIENT_RE = re.compile(
    r"HTTPError:\s*status\s*(408|425|500|502|503|504)\b|"
    r"URLError|TimeoutError|IncompleteRead|RemoteDisconnected|HTTPException|"
    r"timed out|connection reset|name resolution|DNS",
    re.I,
)
_UNAPPROVED_REDIRECT_RE = re.compile(r"unapproved host(?::\s*([^\s/]+))?", re.I)
_PARSER_EMPTY_RE = re.compile(r"parser yielded zero verified services", re.I)


def classify_failure(error: Any) -> tuple[str, str | None]:
    """Return an evidence-based failure class and optional rejected redirect host."""
    text = str(error or "").strip()
    if not text:
        return "ROOT_CAUSE_UNRESOLVED", None
    if _BLOCKED_RE.search(text):
        return "SOURCE_BLOCKED", None
    if _RATE_LIMIT_RE.search(text):
        return "RATE_LIMIT_PRESSURE", None
    if _TRANSIENT_RE.search(text):
        return "SOURCE_TRANSIENT", None
    redirect = _UNAPPROVED_REDIRECT_RE.search(text)
    if redirect:
        host = (redirect.group(1) or "").strip().lower().rstrip(".") or None
        if host == "beckett-maintenance-page.s3.amazonaws.com":
            return "PROVIDER_MAINTENANCE_REDIRECT", host
        return "REDIRECT_TARGET_UNAPPROVED", host
    if _PARSER_EMPTY_RE.search(text):
        return "SCHEMA_PARSER_CHANGE_SUSPECTED", None
    return "ROOT_CAUSE_UNRESOLVED", None


def _recommended_action(failure_class: str) -> str:
    return {
        "HEALTHY": "none",
        "SOURCE_BLOCKED": "preserve last-good; do not bypass or retry storm; recheck on next bounded cycle",
        "RATE_LIMIT_PRESSURE": "respect Retry-After/cooldown; defer this provider only",
        "SOURCE_TRANSIENT": "bounded retry/backoff; preserve last-good if retry fails",
        "PROVIDER_MAINTENANCE_REDIRECT": "treat provider as maintenance/degraded; do not auto-allowlist third-party maintenance host",
        "REDIRECT_TARGET_UNAPPROVED": "inspect redirect target ownership; keep blocked until explicitly verified",
        "SCHEMA_PARSER_CHANGE_SUSPECTED": "inspect current official page schema and update parser with regression fixture",
        "ROOT_CAUSE_UNRESOLVED": "collect more evidence before changing source/parser policy",
    }[failure_class]


def diagnose(snapshot: dict[str, Any]) -> dict[str, Any]:
    sources = snapshot.get("sources") if isinstance(snapshot, dict) else None
    sources = sources if isinstance(sources, dict) else {}
    rows: list[dict[str, Any]] = []
    classes: Counter[str] = Counter()
    company_status: dict[str, dict[str, Any]] = {
        company: {"healthy": 0, "degraded": 0, "failure_classes": Counter()}
        for company in EXPECTED_COMPANIES
    }

    for source_id, source in sorted(sources.items()):
        if not isinstance(source, dict):
            row = {
                "source_id": str(source_id),
                "company": "",
                "status": "invalid",
                "failure_class": "ROOT_CAUSE_UNRESOLVED",
                "error": "source row is not an object",
                "recommended_action": _recommended_action("ROOT_CAUSE_UNRESOLVED"),
            }
            rows.append(row)
            classes[row["failure_class"]] += 1
            continue
        company = str(source.get("company") or "").upper()
        status = str(source.get("status") or "").lower()
        healthy = status in {"ok", "healthy"}
        error = str(source.get("last_error") or source.get("error") or "")
        failure_class, redirect_host = ("HEALTHY", None) if healthy else classify_failure(error)
        row = {
            "source_id": str(source_id),
            "company": company,
            "market": str(source.get("market") or ""),
            "kind": str(source.get("kind") or ""),
            "status": "healthy" if healthy else "degraded",
            "failure_class": failure_class,
            "error": error[:300],
            "recommended_action": _recommended_action(failure_class),
        }
        if redirect_host:
            row["rejected_redirect_host"] = redirect_host
        rows.append(row)
        classes[failure_class] += 1
        if company in company_status:
            key = "healthy" if healthy else "degraded"
            company_status[company][key] += 1
            if not healthy:
                company_status[company]["failure_classes"][failure_class] += 1

    providers: dict[str, Any] = {}
    no_healthy: list[str] = []
    for company in EXPECTED_COMPANIES:
        state = company_status[company]
        failure_counts = dict(sorted(state["failure_classes"].items()))
        providers[company] = {
            "healthy_sources": int(state["healthy"]),
            "degraded_sources": int(state["degraded"]),
            "failure_classes": failure_counts,
        }
        if state["healthy"] == 0:
            no_healthy.append(company)

    return {
        "schema_version": 1,
        "snapshot_checked_at": snapshot.get("checked_at") if isinstance(snapshot, dict) else None,
        "policy": {
            "read_only_diagnostics": True,
            "source_allowlist_mutation": False,
            "blocked_source_bypass": False,
            "last_good_promotion": False,
        },
        "summary": {
            "sources": len(rows),
            "healthy": classes.get("HEALTHY", 0),
            "degraded": len(rows) - classes.get("HEALTHY", 0),
            "failure_classes": dict(sorted(classes.items())),
            "companies_without_healthy_source": no_healthy,
        },
        "providers": providers,
        "sources": rows,
    }


def load_snapshot(path: Path = SNAPSHOT) -> dict[str, Any]:
    data = json.loads(safe_read_text(path, max_bytes=8_000_000))
    if not isinstance(data, dict):
        raise ValueError("grading-company snapshot root must be an object")
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", default=str(SNAPSHOT))
    parser.add_argument("--report", default=str(REPORT))
    args = parser.parse_args()
    report = diagnose(load_snapshot(Path(args.snapshot)))
    atomic_write_json(Path(args.report), report, suffix=".grading-health.tmp")
    print(json.dumps(report["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
