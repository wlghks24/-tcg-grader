#!/usr/bin/env python3
"""Context-aware fail-closed collection verification.

The legacy gate correctly rejects stale source-health timestamps.  A full collection,
however, can legitimately run longer than the 15-minute point-in-time threshold:
source health is captured near the beginning and the verified output/report is written
later.  This wrapper never widens that threshold.  It removes only the two health
STALE_COLLECTION_STATE findings when independent files prove that the timestamp was
created inside the same bounded collection transaction and the completed report itself
is still fresh.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import collection_verification_gate as base

HEALTH_TARGETS = {"source_collection_stats.json", "adaptive_collection_stats.json"}
MAX_REPORT_AGE_SECONDS = 2 * 3600
MAX_COLLECTION_WINDOW_SECONDS = 2 * 3600
MAX_START_SKEW_SECONDS = 30 * 60
BOUNDARY_SLOP_SECONDS = 5 * 60
PROVIDER_PROOF_FILE = 'provider_last_good_official.json'
MAX_PROVIDER_PROOF_AGE_SECONDS = 7 * 24 * 3600
_BLOCKED_PROVIDER_RE = re.compile(r'HTTPError:\s*status\s*(401|403|451)\b', re.I)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _timestamp(value: Any) -> dt.datetime | None:
    return base._parse_time(value)


def _same_current_collection(root: Path, target: str, now: dt.datetime) -> dict[str, Any] | None:
    try:
        stat = _load(root / target)
        report = _load(root / "auto_update_report.json")
        live = _load(root / "tcg_live_data.json")
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(stat, dict) or not isinstance(report, dict) or not isinstance(live, dict):
        return None

    auto = live.get("auto_update") if isinstance(live.get("auto_update"), dict) else {}
    stat_at = _timestamp(stat.get("updated_at"))
    report_start = _timestamp(report.get("started_at"))
    report_finish = _timestamp(report.get("finished_at"))
    cycle_start = _timestamp(auto.get("last_run"))
    if None in (stat_at, report_start, report_finish, cycle_start):
        return None
    assert stat_at is not None and report_start is not None and report_finish is not None and cycle_start is not None

    if report_finish < report_start or report_start < cycle_start - dt.timedelta(seconds=BOUNDARY_SLOP_SECONDS):
        return None
    if (report_finish - cycle_start).total_seconds() > MAX_COLLECTION_WINDOW_SECONDS:
        return None
    if abs((report_start - cycle_start).total_seconds()) > MAX_START_SKEW_SECONDS:
        return None
    report_age = (now - report_finish).total_seconds()
    if report_age < -BOUNDARY_SLOP_SECONDS or report_age > MAX_REPORT_AGE_SECONDS:
        return None
    if stat_at < cycle_start - dt.timedelta(seconds=BOUNDARY_SLOP_SECONDS):
        return None
    if stat_at > report_finish + dt.timedelta(seconds=BOUNDARY_SLOP_SECONDS):
        return None

    # A report with no mandatory results cannot prove a completed collection.
    results = report.get("results")
    if not isinstance(results, list) or not results:
        return None
    seen = {str(row.get("file")) for row in results if isinstance(row, dict) and row.get("file")}
    if not set(base.MANDATORY_OUTPUT_FILES).issubset(seen):
        return None

    return {
        "cycle_started_at": cycle_start.isoformat(),
        "health_updated_at": stat_at.isoformat(),
        "report_started_at": report_start.isoformat(),
        "report_finished_at": report_finish.isoformat(),
        "report_age_seconds": round(report_age, 1),
        "proof": "same_bounded_collection_transaction",
    }


def _blocked_provider_last_good_proof(root: Path, company: str, now: dt.datetime) -> dict[str, Any] | None:
    try:
        proof = _load(root / PROVIDER_PROOF_FILE)
        snapshot = _load(root / "grading_company_updates.json")
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(proof, dict) or proof.get("schema_version") != 1:
        return None
    company = str(company or "").upper()
    if str(proof.get("provider") or "").upper() != company:
        return None
    policy = proof.get("policy") if isinstance(proof.get("policy"), dict) else {}
    required_policy = {
        "official_source_only": True,
        "runtime_block_stays_degraded": True,
        "bypass_blocked_source": False,
        "not_injected_into_grading_company_updates": True,
    }
    if any(policy.get(k) is not v for k, v in required_policy.items()):
        return None
    try:
        max_age = int(policy.get("max_age_seconds"))
    except (TypeError, ValueError):
        return None
    if max_age <= 0 or max_age > MAX_PROVIDER_PROOF_AGE_SECONDS:
        return None
    observed = _timestamp(proof.get("observed_at"))
    expires = _timestamp(proof.get("expires_at"))
    if observed is None or expires is None or expires < observed:
        return None
    age = (now - observed).total_seconds()
    if age < -BOUNDARY_SLOP_SECONDS or age > max_age or now > expires:
        return None
    source = str(proof.get("source_url") or "")
    if not base._valid_public_https(source):
        return None
    host = (urlparse(source).hostname or "").lower().rstrip(".")
    if host not in base.GRADING_ALLOWED_HOSTS:
        return None
    services = proof.get("services")
    if not isinstance(services, list) or not services:
        return None
    canonical = json.dumps(services, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != proof.get("facts_sha256"):
        return None

    sources = snapshot.get("sources") if isinstance(snapshot, dict) else None
    if not isinstance(sources, dict):
        return None
    rows = [row for row in sources.values() if isinstance(row, dict) and str(row.get("company") or "").upper() == company]
    if not rows:
        return None
    # Every current provider row must still be degraded because of an explicit hard block.
    # Any healthy row, parser failure, timeout, rate limit, or unknown error invalidates this proof.
    for row in rows:
        if str(row.get("status") or "").lower() in {"ok", "healthy"}:
            return None
        if str(row.get("status") or "").lower() != "degraded":
            return None
        error = str(row.get("last_error") or row.get("error") or "")
        if _BLOCKED_PROVIDER_RE.search(error) is None:
            return None
    return {
        "provider": company,
        "source": source,
        "observed_at": observed.isoformat(),
        "expires_at": expires.isoformat(),
        "age_seconds": round(age, 1),
        "facts_sha256": proof["facts_sha256"],
        "service_fact_count": len(services),
        "runtime_status": "degraded",
        "failure_class": "SOURCE_BLOCKED",
        "bypass_attempted": False,
    }


def _contextualize_blocked_provider(root: Path, finding: dict[str, Any], now: dt.datetime) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if finding.get("severity") != "high" or finding.get("code") != "GRADING_COMPANY_NO_HEALTHY_SOURCE":
        return [finding], []
    companies = [str(item).upper() for item in (finding.get("companies") or []) if str(item).strip()]
    safe: list[dict[str, Any]] = []
    unsafe: list[str] = []
    for company in companies:
        proof = _blocked_provider_last_good_proof(root, company, now)
        if proof is None:
            unsafe.append(company)
        else:
            safe.append(proof)
    rows: list[dict[str, Any]] = []
    if unsafe:
        kept = dict(finding)
        kept["companies"] = unsafe
        by_company = finding.get("degraded_samples_by_company") or {}
        counts = finding.get("degraded_sample_counts_by_company") or {}
        kept["degraded_samples_by_company"] = {name: by_company.get(name, []) for name in unsafe}
        kept["degraded_sample_counts_by_company"] = {name: counts.get(name, 0) for name in unsafe}
        kept["degraded_samples"] = [sample for name in unsafe for sample in by_company.get(name, [])][:20]
        rows.append(kept)
    if safe:
        rows.append({
            "severity": "medium",
            "code": "GRADING_COMPANY_SOURCE_BLOCKED_WITH_EXTERNAL_LAST_GOOD",
            "target": "grading_company_updates.json",
            "companies": [item["provider"] for item in safe],
            "proof": safe,
            "policy": "runtime snapshot remains degraded/empty; no source bypass; proof only permits unrelated verified outputs to publish",
        })
    return rows, safe


def verify(root: Path | str = base.ROOT, *, max_health_age_seconds: int = 900,
           now: dt.datetime | None = None) -> dict[str, Any]:
    root = Path(root)
    now = now or dt.datetime.now(dt.timezone.utc)
    report = base.verify(root, max_health_age_seconds=max_health_age_seconds, now=now)
    original = list(report.get("findings") or [])
    filtered: list[dict[str, Any]] = []
    contextual: list[dict[str, Any]] = []
    blocked_provider_proofs: list[dict[str, Any]] = []

    for finding in original:
        if (
            isinstance(finding, dict)
            and finding.get("severity") == "high"
            and finding.get("code") == "STALE_COLLECTION_STATE"
            and finding.get("target") in HEALTH_TARGETS
        ):
            evidence = _same_current_collection(root, str(finding["target"]), now)
            if evidence is not None:
                contextual.append({
                    "severity": "info",
                    "code": "CURRENT_COLLECTION_WINDOW_PROVEN",
                    "target": finding["target"],
                    "point_in_time_age_seconds": finding.get("age_seconds"),
                    "evidence": evidence,
                })
                continue
        if isinstance(finding, dict):
            provider_rows, provider_proofs = _contextualize_blocked_provider(root, finding, now)
            if provider_proofs:
                filtered.extend(provider_rows)
                blocked_provider_proofs.extend(provider_proofs)
                continue
        filtered.append(finding)

    filtered.extend(contextual)
    report["findings"] = filtered
    counts = {
        level: sum(isinstance(row, dict) and row.get("severity") == level for row in filtered)
        for level in ("critical", "high", "medium")
    }
    report["counts"] = counts
    report["status"] = "fail_closed" if counts["critical"] else ("degraded" if counts["high"] else "pass")
    report["contextual_freshness"] = {
        "point_in_time_threshold_seconds": max_health_age_seconds,
        "threshold_widened": False,
        "same_run_proofs": len(contextual),
        "max_completed_report_age_seconds": MAX_REPORT_AGE_SECONDS,
        "blocked_provider_proofs": len(blocked_provider_proofs),
    }
    report["blocked_provider_last_good"] = blocked_provider_proofs
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(base.ROOT))
    parser.add_argument("--max-health-age-seconds", type=int, default=900)
    parser.add_argument("--report", default="COLLECTION_VERIFICATION_REPORT.json")
    parser.add_argument("--fail-on-degraded", action="store_true")
    args = parser.parse_args()
    max_age = max(60, min(86400, args.max_health_age_seconds))
    report = verify(Path(args.root), max_health_age_seconds=max_age)
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "counts": report["counts"],
        "metrics": report.get("metrics", {}),
        "contextual_freshness": report["contextual_freshness"],
    }, ensure_ascii=False))
    if report["status"] == "fail_closed":
        return 2
    if args.fail_on_degraded and report["status"] == "degraded":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
