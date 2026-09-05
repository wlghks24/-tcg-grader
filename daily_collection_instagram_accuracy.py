#!/usr/bin/env python3
"""06:00 KST Main collection ↔ Instagram TCG accuracy/health audit.

The audit is passive across domains:
- compare operational health, coverage and factual exchange records;
- never merge retry/provider/learning state;
- never promote candidate/corroborated data to verified;
- emit bounded repair recommendations instead of executing learned text.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

from selfrefine_crosscheck_gate import run as run_crosscheck

ROOT = Path(__file__).resolve().parent
KST = dt.timezone(dt.timedelta(hours=9))

DEFAULT_MAIN_STATS = ROOT / "adaptive_collection_stats.json"
DEFAULT_SOURCE_STATS = ROOT / "source_collection_stats.json"
DEFAULT_PROMO = ROOT / "promo_events.json"
DEFAULT_ROUTES = ROOT / "instagram_tcg_content" / "source_routes.json"
DEFAULT_MAIN_EXCHANGE = ROOT / "crosscheck_exchange" / "runtime-main.json"
DEFAULT_INSTAGRAM_EXCHANGE = ROOT / "crosscheck_exchange" / "runtime-instagram.json"
DEFAULT_REPORT = ROOT / "COLLECTION_INSTAGRAM_ACCURACY_REPORT.json"

CRITICAL_MAIN_JOBS = (
    "releases.json",
    "market_prices.json",
    "promo_events.json",
    "exchange_rates.json",
)
EXPECTED_GAMES = {"pokemon", "one_piece", "naruto"}
EXPECTED_GAME_REGION_PAIRS = 9

POLICY_REQUIREMENTS = {
    "official_facts_require_official_primary": True,
    "completed_sale_requires_independent_realized_sale_sources": 2,
    "market_reference_requires_independent_sources_for_verified": 2,
    "discovery_lead_can_confirm_fact_alone": False,
    "respect_retry_after": True,
    "bypass_403_429": False,
    "preserve_provider_lineage": True,
    "dedupe_same_underlying_sale_lineage": True,
    "completed_sale_separate_from_market_reference": True,
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError, UnicodeError):
        return {}


def _parse_time(value: object) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _age_hours(value: object, now: dt.datetime) -> float | None:
    parsed = _parse_time(value)
    if parsed is None:
        return None
    return max(0.0, (now.astimezone(dt.timezone.utc) - parsed).total_seconds() / 3600.0)


def _action(severity: str, domain: str, rule: str, reason: str, action: str) -> dict[str, str]:
    return {
        "severity": severity,
        "domain": domain,
        "rule": rule,
        "reason": reason[:800],
        "action": action[:1000],
    }


def audit_main_collection(
    adaptive: dict[str, Any],
    source_stats: dict[str, Any],
    promo: dict[str, Any],
    now: dt.datetime,
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    actions: list[dict[str, str]] = []
    jobs = adaptive.get("jobs") if isinstance(adaptive.get("jobs"), dict) else {}

    for name in CRITICAL_MAIN_JOBS:
        row = jobs.get(name)
        if not isinstance(row, dict):
            findings.append({"kind": "missing_job_health", "job": name, "severity": "high"})
            actions.append(
                _action(
                    "high",
                    "main",
                    "restore_job_health",
                    f"{name} has no health row",
                    "Run the collector once, persist its health row, then rerun the 06:00 audit before trusting downstream content.",
                )
            )
            continue

        age = _age_hours(row.get("last_run"), now)
        consecutive_failures = int(row.get("consecutive_failures") or 0)
        last_ok = bool(row.get("last_ok"))
        recovered = bool(row.get("last_recovered"))

        if age is None or age > 36:
            findings.append(
                {
                    "kind": "stale_job",
                    "job": name,
                    "severity": "high",
                    "age_hours": None if age is None else round(age, 2),
                }
            )
            actions.append(
                _action(
                    "high",
                    "main",
                    "refresh_stale_job",
                    f"{name} is older than the 36h daily freshness guard",
                    "Re-run this collector using its normal source policy; if the same failure repeats, switch to an independent approved source/parser instead of reusing stale output.",
                )
            )

        if consecutive_failures >= 3:
            findings.append(
                {
                    "kind": "repeated_failure",
                    "job": name,
                    "severity": "high",
                    "consecutive_failures": consecutive_failures,
                    "dominant_error_signature": row.get("dominant_error_signature"),
                }
            )
            actions.append(
                _action(
                    "high",
                    "main",
                    "alternate_route_after_repeat",
                    f"{name} has {consecutive_failures} consecutive failures",
                    "Do not repeat the identical route. Apply bounded backoff, then alternate provider; on parser errors alternate parser+provider; quarantine a repeatedly failing route after the configured threshold.",
                )
            )
        elif not last_ok:
            findings.append(
                {
                    "kind": "partial_or_recovered",
                    "job": name,
                    "severity": "medium",
                    "last_recovered": recovered,
                }
            )

    source_map = source_stats.get("sources") if isinstance(source_stats.get("sources"), dict) else {}
    if not source_map or not source_stats.get("updated_at"):
        findings.append({"kind": "empty_source_health", "severity": "high"})
        actions.append(
            _action(
                "high",
                "main",
                "persist_source_health",
                "source_collection_stats.json has no current source health rows",
                "Populate source-level success/failure/freshness statistics during collection so the 06:00 audit can distinguish a healthy fallback from a silent stale cache.",
            )
        )

    coverage = promo.get("coverage") if isinstance(promo.get("coverage"), dict) else {}
    expected = int(coverage.get("expected_game_region_pairs") or 0)
    covered = int(coverage.get("covered_game_region_pairs") or 0)
    missing_pairs = coverage.get("missing_source_pairs") or []
    if expected != EXPECTED_GAME_REGION_PAIRS or covered < EXPECTED_GAME_REGION_PAIRS or missing_pairs:
        findings.append(
            {
                "kind": "coverage_gap",
                "severity": "high",
                "expected_pairs": expected,
                "covered_pairs": covered,
                "missing_pairs": missing_pairs,
            }
        )
        actions.append(
            _action(
                "high",
                "main",
                "reverify_game_region_coverage",
                "Pokémon / ONE PIECE / NARUTO × KR/JP/US coverage is incomplete",
                "Re-query the missing game/region cell with an official primary route first; keep discovery/SNS results candidate-only until independently verified.",
            )
        )

    link_age = _age_hours(promo.get("link_audit_at"), now)
    if link_age is None or link_age > 168:
        findings.append(
            {
                "kind": "stale_link_audit",
                "severity": "high",
                "age_hours": None if link_age is None else round(link_age, 2),
            }
        )
        actions.append(
            _action(
                "high",
                "main",
                "refresh_official_links",
                "promo/event link audit is older than 7 days",
                "Refresh official detail/news pages and retain the old URL only as historical provenance; do not treat an old successful check as current availability.",
            )
        )

    collection_errors = promo.get("collection_errors") or []
    if collection_errors:
        findings.append(
            {
                "kind": "collection_errors",
                "severity": "high" if len(collection_errors) >= 5 else "medium",
                "count": len(collection_errors),
                "samples": [str(x)[:240] for x in collection_errors[:5]],
            }
        )
        actions.append(
            _action(
                "high" if len(collection_errors) >= 5 else "medium",
                "main",
                "group_collection_errors",
                f"{len(collection_errors)} promo/event collection errors are recorded",
                "Group errors by signature/provider, retry with backoff, then use an approved alternate source. Never erase the last verified fact solely because a current fetch failed.",
            )
        )

    return {"findings": findings, "repair_actions": actions}


def audit_instagram_policy(routes: dict[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    actions: list[dict[str, str]] = []
    rules = routes.get("rules") if isinstance(routes.get("rules"), dict) else {}

    for key, expected in POLICY_REQUIREMENTS.items():
        actual = rules.get(key)
        if actual != expected:
            findings.append(
                {
                    "kind": "policy_invariant_violation",
                    "severity": "critical",
                    "key": key,
                    "expected": expected,
                    "actual": actual,
                }
            )
            actions.append(
                _action(
                    "critical",
                    "instagram_content",
                    "restore_fail_closed_policy",
                    f"{key} changed from the required fail-closed value",
                    "Restore the required policy before any Instagram card information is considered postable.",
                )
            )

    groups = routes.get("provider_groups") if isinstance(routes.get("provider_groups"), dict) else {}
    missing_games = sorted(EXPECTED_GAMES - set(groups))
    if missing_games:
        findings.append(
            {
                "kind": "missing_game_source_pool",
                "severity": "critical",
                "games": missing_games,
            }
        )

    for game in sorted(EXPECTED_GAMES):
        group = groups.get(game) if isinstance(groups.get(game), dict) else {}
        official = set(group.get("official_primary") or [])
        realized = set(group.get("completed_sale_original") or []) | set(
            group.get("grading_auction_original") or []
        )
        market = set(group.get("market_reference") or [])
        if len(official) < 1:
            findings.append({"kind": "missing_official_primary", "severity": "critical", "game": game})
        if len(realized) < 2:
            findings.append({"kind": "insufficient_realized_sale_routes", "severity": "high", "game": game})
        if len(market) < 2:
            findings.append({"kind": "insufficient_market_reference_routes", "severity": "high", "game": game})

    if findings:
        actions.append(
            _action(
                "high",
                "instagram_content",
                "restore_provider_diversity",
                "One or more Instagram source pools/policies do not meet the minimum evidence contract",
                "Restore official-primary and independent realized-sale/market-reference diversity. Discovery leads may locate facts but may not confirm them alone.",
            )
        )

    return {"findings": findings, "repair_actions": actions}


def audit_cross_domain(main_exchange: Path, instagram_exchange: Path) -> dict[str, Any]:
    if not main_exchange.exists() or not instagram_exchange.exists():
        missing = []
        if not main_exchange.exists():
            missing.append("main")
        if not instagram_exchange.exists():
            missing.append("instagram_content")
        return {
            "status": "snapshot_missing",
            "missing_domains": missing,
            "agree": 0,
            "conflict": 0,
            "reverification_required": 0,
            "repair_actions": [
                _action(
                    "medium",
                    "crosscheck",
                    "export_daily_snapshot",
                    "A passive factual snapshot is missing for the 06:00 comparison",
                    "Export each domain's latest factual rows through its own crosscheck exporter. Keep runtime/provider/retry/learning state out of the exchange file.",
                )
            ],
        }

    result = run_crosscheck(main_exchange, instagram_exchange)
    actions: list[dict[str, str]] = []
    if int(result.get("conflict") or 0) > 0:
        actions.append(
            _action(
                "high",
                "crosscheck",
                "reverify_conflict",
                f"{result.get('conflict')} canonical facts disagree across Main and Instagram",
                "Do not average the values and do not auto-promote either side. Reverify the conflicting canonical_key with fresh independent evidence, preferring official primary for official facts and direct realized-sale evidence for sales.",
            )
        )
    return {
        "status": result.get("status"),
        "main_records": result.get("main_records", 0),
        "instagram_records": result.get("instagram_records", 0),
        "agree": result.get("agree", 0),
        "conflict": result.get("conflict", 0),
        "reverification_required": result.get("reverification_required", 0),
        "repair_actions": actions,
    }


def _previous_delta(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    if not previous:
        return {"available": False}
    old_summary = previous.get("summary") if isinstance(previous.get("summary"), dict) else {}
    new_summary = current.get("summary") if isinstance(current.get("summary"), dict) else {}
    return {
        "available": True,
        "health_score_change": int(new_summary.get("health_score") or 0)
        - int(old_summary.get("health_score") or 0),
        "high_findings_change": int(new_summary.get("high_or_critical_findings") or 0)
        - int(old_summary.get("high_or_critical_findings") or 0),
        "cross_domain_conflict_change": int(current.get("cross_domain", {}).get("conflict") or 0)
        - int(previous.get("cross_domain", {}).get("conflict") or 0),
    }


def build_report(
    *,
    now: dt.datetime,
    adaptive: dict[str, Any],
    source_stats: dict[str, Any],
    promo: dict[str, Any],
    routes: dict[str, Any],
    main_exchange: Path,
    instagram_exchange: Path,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    main = audit_main_collection(adaptive, source_stats, promo, now)
    instagram = audit_instagram_policy(routes)
    cross = audit_cross_domain(main_exchange, instagram_exchange)

    findings = main["findings"] + instagram["findings"]
    actions = main["repair_actions"] + instagram["repair_actions"] + cross["repair_actions"]

    critical = sum(1 for row in findings if row.get("severity") == "critical")
    high = sum(1 for row in findings if row.get("severity") == "high")
    medium = sum(1 for row in findings if row.get("severity") == "medium")
    conflicts = int(cross.get("conflict") or 0)

    health_score = max(0, 100 - critical * 25 - high * 10 - medium * 3 - conflicts * 15)
    status = "pass"
    if critical or conflicts:
        status = "fail_closed"
    elif high:
        status = "degraded"
    elif cross.get("status") == "snapshot_missing" or medium:
        status = "warning"

    report: dict[str, Any] = {
        "schema_version": 1,
        "run_at_kst": now.astimezone(KST).isoformat(timespec="seconds"),
        "purpose": "daily 06:00 Main collection vs Instagram TCG accuracy and health comparison",
        "summary": {
            "status": status,
            "health_score": health_score,
            "critical_findings": critical,
            "high_findings": high,
            "medium_findings": medium,
            "high_or_critical_findings": high + critical,
            "repair_action_count": len(actions),
        },
        "main_collection": main,
        "instagram_policy": instagram,
        "cross_domain": cross,
        "repair_actions": actions,
        "safety": {
            "main_instagram_runtime_state_merged": False,
            "provider_health_shared": False,
            "retry_history_shared": False,
            "learning_state_shared": False,
            "verification_auto_promoted": False,
            "conflicting_values_averaged": False,
            "403_429_bypass_allowed": False,
            "passive_factual_exchange_only": True,
        },
    }
    report["previous_day_delta"] = _previous_delta(previous or {}, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adaptive", default=str(DEFAULT_MAIN_STATS))
    parser.add_argument("--source-stats", default=str(DEFAULT_SOURCE_STATS))
    parser.add_argument("--promo", default=str(DEFAULT_PROMO))
    parser.add_argument("--routes", default=str(DEFAULT_ROUTES))
    parser.add_argument("--main-exchange", default=str(DEFAULT_MAIN_EXCHANGE))
    parser.add_argument("--instagram-exchange", default=str(DEFAULT_INSTAGRAM_EXCHANGE))
    parser.add_argument("--previous-report")
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--now")
    parser.add_argument("--strict-policy", action="store_true")
    args = parser.parse_args()

    now = _parse_time(args.now) if args.now else dt.datetime.now(dt.timezone.utc)
    if now is None:
        raise SystemExit("--now must be ISO-8601")

    previous = _read_json(Path(args.previous_report)) if args.previous_report else {}
    report = build_report(
        now=now,
        adaptive=_read_json(Path(args.adaptive)),
        source_stats=_read_json(Path(args.source_stats)),
        promo=_read_json(Path(args.promo)),
        routes=_read_json(Path(args.routes)),
        main_exchange=Path(args.main_exchange),
        instagram_exchange=Path(args.instagram_exchange),
        previous=previous,
    )

    output = Path(args.report)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))

    if args.strict_policy and report["summary"]["critical_findings"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
