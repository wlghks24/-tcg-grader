#!/usr/bin/env python3
"""Deterministic reasoning support for the existing AI auto tracker.

This module is an internal intelligence layer, not a second tracker and not an
autonomous code rewriter. It converts already-observed incident evidence into
bounded confidence, root-cause families, recurrence escalation, actionability,
and recommended verification checks. Learned/free-form text is never executed.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

DOMAINS = {"github", "market", "tablet"}
SEVERITY_WEIGHT = {"low": 0.15, "medium": 0.4, "high": 0.7, "critical": 1.0}
MAX_RECOMMENDATIONS = 6
MAX_TEXT = 320

SECRET_PATTERNS = (
    re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|passwd|secret)\s*[=:]\s*[^\s,;]+"),
)
URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+", re.I)

DOMAIN_HINTS = {
    "market": (
        "price", "market", "collector", "source", "currency", "krw", "jpy", "usd",
        "403", "429", "rate limit", "listing", "transaction", "시세", "수집", "가격",
    ),
    "tablet": (
        "tablet", "termux", "android", "lenovo", "tailscale", "boot", "autostart",
        "background", "localhost", "8765", "browser", "iphone", "reboot", "태블릿", "재부팅",
    ),
    "github": (
        "github", "workflow", "action", "ci", "test", "dependency", "security",
        "deploy", "syntax", "repository", "pull request", "commit", "regression",
    ),
}

CAUSE_RULES = (
    ("security_boundary", ("credential", "secret leak", "token leak", "ssrf", "path traversal", "unsafe redirect", "security_high")),
    ("network_rate_limit", ("429", "rate limit", "retry-after", "throttle", "too many requests")),
    ("network_access_blocked", ("403", "forbidden", "access denied", "blocked")),
    ("network_dns_timeout", ("timeout", "timed out", "dns", "name resolution", "connection reset", "unreachable")),
    ("startup_runtime", ("startup", "autostart", "boot", "reboot", "termux", "port 8765", "health check", "background")),
    ("deployment_sync", ("stale", "sha mismatch", "origin/main", "deployment", "deploy", "mixed version", "cache-buster")),
    ("ui_cross_device", ("iphone", "browser", "button", "link", "service worker", "csp", "ui", "cross-device")),
    ("parser_schema", ("schema", "parser", "parse", "jsondecode", "unexpected field", "structure changed")),
    ("data_integrity", ("corrupt", "data loss", "duplicate", "invalid state", "atomic write", "lock", "persistence")),
    ("test_regression", ("test failed", "regression", "assertion", "syntax", "compile", "workflow failed", "ci failed")),
)

RECOMMENDATIONS = {
    "security_boundary": (
        "Re-run defensive security audit and URL/path boundary tests.",
        "Confirm diagnostics redact credentials and raw authorization material.",
        "Require a full regression before promoting any repair learning.",
    ),
    "network_rate_limit": (
        "Honor Retry-After and keep bounded exponential backoff with jitter.",
        "Confirm the source cooldown/circuit-breaker state is persisted safely.",
        "Use another approved public source for cross-validation; do not bypass the block.",
    ),
    "network_access_blocked": (
        "Classify 403 as blocked/degraded rather than attempting bypass logic.",
        "Verify API credentials/permissions only when the source officially requires them.",
        "Keep last verified data and record source health for the next cycle.",
    ),
    "network_dns_timeout": (
        "Run bounded reachability and DNS checks before retrying the same endpoint.",
        "Separate transient network failure from parser/data failure in persistent diagnostics.",
        "Verify retry exhaustion leaves the previous verified state intact.",
    ),
    "startup_runtime": (
        "Check /api/v135-health, launcher PID ownership, and port 8765 before restart.",
        "Verify Termux:Boot startup log, bounded 30s→300s backoff, and wake-lock cleanup.",
        "Validate localhost, LAN, and Tailscale access candidates after recovery.",
    ),
    "deployment_sync": (
        "Compare the local Git SHA with origin/main and reject mixed-version startup.",
        "Run runtime delivery guards plus cache/service-worker version checks.",
        "Preserve device-local runtime state while using fast-forward-only code updates.",
    ),
    "ui_cross_device": (
        "Run button/link and JavaScript syntax smoke tests on the changed runtime assets.",
        "Check service-worker cache invalidation and no-store delivery for mutable assets.",
        "Compare tablet, iPhone, PC, localhost, and GitHub Pages behavior.",
    ),
    "parser_schema": (
        "Quarantine the changed parser/schema path and preserve the last verified dataset.",
        "Add a fixture for the newly observed structure before accepting a parser change.",
        "Require collection verification plus full regression before learning the fix.",
    ),
    "data_integrity": (
        "Verify atomic write, file locking, rollback, and bounded-state contracts.",
        "Check corrupt-state recovery with a temporary fixture before touching live state.",
        "Do not promote recovery knowledge until full regression succeeds.",
    ),
    "test_regression": (
        "Identify the first failing guard and minimize the patch to its affected path.",
        "Re-run the local targeted test before repository-wide regression.",
        "Promote learning only after all required guards pass on the final file hashes.",
    ),
    "unknown": (
        "Collect a bounded error type, stage, path, and reproducible symptom before repair.",
        "Use code-map impact analysis to select the smallest relevant regression set.",
        "Keep the incident in human review until evidence quality improves.",
    ),
}

DOMAIN_CHECKS = {
    "github": "Run Main SELFREFINE, Repository Integrity, and Exhaustive SELFREFINE guards.",
    "market": "Run collection evidence verification and hand market-data defects to 시세오류검사기.",
    "tablet": "Run Android Updater Guard, Runtime delivery guard, and live tablet runtime verification.",
}


def _clean(value: Any, limit: int = MAX_TEXT) -> str:
    text = " ".join(str(value or "").replace("\x00", " ").split())
    text = URL_PATTERN.sub("<url>", text)
    for pattern in SECRET_PATTERNS:
        text = pattern.sub(lambda m: f"{m.group(1)} <redacted>", text)
    return text[: max(1, min(2000, int(limit)))]


def _haystack(event: dict[str, Any]) -> str:
    return " ".join(
        _clean(event.get(key), 500).lower()
        for key in ("stage", "path", "error_type", "message", "evidence", "source")
    )


def domain_assessment(event: dict[str, Any]) -> dict[str, Any]:
    explicit = _clean(event.get("domain"), 20).lower()
    text = _haystack(event)
    raw_scores = {domain: sum(token in text for token in hints) for domain, hints in DOMAIN_HINTS.items()}
    if explicit in DOMAINS:
        raw_scores[explicit] += 5
    ranked = sorted(raw_scores.items(), key=lambda item: (-item[1], item[0]))
    best_domain, best_score = ranked[0]
    second_score = ranked[1][1]
    if best_score <= 0:
        confidence = 0.34
        ambiguous = True
        best_domain = explicit if explicit in DOMAINS else "github"
    else:
        margin = best_score - second_score
        confidence = min(0.99, 0.52 + 0.08 * best_score + 0.07 * max(0, margin))
        ambiguous = margin <= 0 or confidence < 0.67
    if explicit in DOMAINS:
        confidence = max(confidence, 0.95)
        ambiguous = False
    return {
        "domain": best_domain,
        "confidence": round(confidence, 3),
        "ambiguous": bool(ambiguous),
        "scores": raw_scores,
    }


def root_cause_assessment(event: dict[str, Any]) -> dict[str, Any]:
    text = _haystack(event)
    matches: list[tuple[int, str, list[str]]] = []
    for family, hints in CAUSE_RULES:
        hit = sorted({hint for hint in hints if hint in text})
        if hit:
            matches.append((len(hit), family, hit))
    if not matches:
        return {"family": "unknown", "confidence": 0.3, "signals": []}
    matches.sort(key=lambda row: (-row[0], row[1]))
    count, family, signals = matches[0]
    runner_up = matches[1][0] if len(matches) > 1 else 0
    confidence = min(0.98, 0.58 + 0.1 * count + 0.05 * max(0, count - runner_up))
    return {"family": family, "confidence": round(confidence, 3), "signals": signals[:5]}


def evidence_quality(event: dict[str, Any], code_map: dict[str, Any] | None = None) -> dict[str, Any]:
    score = 0.0
    reasons: list[str] = []
    checks = (
        ("stage", 0.12),
        ("path", 0.16),
        ("error_type", 0.14),
        ("evidence", 0.18),
        ("message", 0.08),
    )
    for key, weight in checks:
        if _clean(event.get(key), 500):
            score += weight
            reasons.append(key)
    if isinstance(event.get("changed_files"), list) and event.get("changed_files"):
        score += 0.08
        reasons.append("changed_files")
    if event.get("regression_pass") is not None:
        score += 0.06
        reasons.append("regression_result")
    verification = _clean(event.get("verification"), 40).lower()
    if event.get("verified") is True or verification in {"verified", "full_verified", "full_regression_verified"}:
        score += 0.08
        reasons.append("verification")
    text = _haystack(event)
    if re.search(r"\b(?:403|408|425|429|500|502|503|504)\b", text):
        score += 0.05
        reasons.append("status_code")
    if isinstance(code_map, dict) and code_map.get("available"):
        score += 0.05
        reasons.append("code_map")
    score = max(0.0, min(1.0, score))
    level = "high" if score >= 0.72 else ("medium" if score >= 0.45 else "low")
    return {"score": round(score, 3), "level": level, "signals": reasons[:10]}


def recurrence_assessment(occurrences: Any) -> dict[str, Any]:
    try:
        count = max(1, min(1_000_000, int(occurrences)))
    except (TypeError, ValueError, OverflowError):
        count = 1
    if count >= 8:
        level, multiplier = "persistent", 1.0
    elif count >= 4:
        level, multiplier = "repeated", 0.7
    elif count >= 2:
        level, multiplier = "recurring", 0.4
    else:
        level, multiplier = "new", 0.1
    return {"occurrences": count, "level": level, "weight": multiplier}


def _bounded_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(number):
        return default
    return max(0.0, min(1.0, number))


def actionability_assessment(
    event: dict[str, Any],
    *,
    occurrences: Any = 1,
    code_map: dict[str, Any] | None = None,
) -> dict[str, Any]:
    domain = domain_assessment(event)
    cause = root_cause_assessment(event)
    evidence = evidence_quality(event, code_map)
    recurrence = recurrence_assessment(occurrences)
    severity = _clean(event.get("severity"), 20).lower()
    severity_weight = SEVERITY_WEIGHT.get(severity, 0.35)
    structural_risk = str(code_map.get("structural_risk") or "") if isinstance(code_map, dict) else ""
    structural = 0.15 if structural_risk == "high" else (0.07 if structural_risk == "medium" else 0.0)
    score = (
        0.34 * severity_weight
        + 0.22 * _bounded_float(domain["confidence"])
        + 0.22 * _bounded_float(evidence["score"])
        + 0.17 * recurrence["weight"]
        + structural
    )
    score = max(0.0, min(1.0, score))
    priority = "P0" if score >= 0.85 else ("P1" if score >= 0.67 else ("P2" if score >= 0.45 else "P3"))
    human_review = bool(
        domain["ambiguous"]
        or cause["confidence"] < 0.55
        or evidence["score"] < 0.35
        or (severity in {"high", "critical"} and evidence["score"] < 0.5)
        or (
            severity in {"high", "critical"}
            and isinstance(code_map, dict)
            and code_map.get("status") == "stale_for_origin"
        )
    )
    return {
        "score": round(score, 3),
        "priority": priority,
        "human_review_required": human_review,
        "domain": domain,
        "root_cause": cause,
        "evidence": evidence,
        "recurrence": recurrence,
    }


def recommended_checks(
    event: dict[str, Any],
    assessment: dict[str, Any],
    code_map: dict[str, Any] | None = None,
) -> list[str]:
    domain = str((assessment.get("domain") or {}).get("domain") or "github")
    family = str((assessment.get("root_cause") or {}).get("family") or "unknown")
    rows: list[str] = []

    if isinstance(code_map, dict):
        for path in (code_map.get("suggested_tests") or [])[:2]:
            cleaned_path = _clean(path, 180)
            if cleaned_path:
                rows.append(f"Run code-map targeted regression for {cleaned_path}.")

    rows.extend(RECOMMENDATIONS.get(family, RECOMMENDATIONS["unknown"]))
    domain_check = DOMAIN_CHECKS.get(domain)
    if domain_check:
        rows.append(domain_check)
    if bool(assessment.get("human_review_required")):
        rows.append("Keep automatic repair disabled until the missing/ambiguous evidence is resolved.")
    deduped: list[str] = []
    for row in rows:
        cleaned = _clean(row, 240)
        if cleaned and cleaned not in deduped:
            deduped.append(cleaned)
    return deduped[:MAX_RECOMMENDATIONS]


def enrich_incident(
    event: dict[str, Any],
    *,
    occurrences: Any = 1,
    code_map: dict[str, Any] | None = None,
) -> dict[str, Any]:
    safe_event = dict(event) if isinstance(event, dict) else {}
    assessment = actionability_assessment(safe_event, occurrences=occurrences, code_map=code_map)
    return {
        "schema": 1,
        "assessment": assessment,
        "recommended_checks": recommended_checks(safe_event, assessment, code_map),
        "safety": {
            "learned_text_executable": False,
            "auto_patch_from_reasoning": False,
            "domain_state_merged": False,
            "full_regression_required": True,
        },
    }


def enrich_tracker_report(report: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with reasoning attached; never mutates tracker state."""
    source = report if isinstance(report, dict) else {}
    enriched_rows: list[dict[str, Any]] = []
    for row in source.get("incidents") or []:
        if not isinstance(row, dict):
            continue
        event = {
            "domain": row.get("domain"),
            "severity": row.get("severity"),
            "stage": row.get("stage"),
            "path": row.get("path"),
            "error_type": row.get("error_type"),
            "message": row.get("message"),
        }
        reasoning = enrich_incident(
            event,
            occurrences=row.get("occurrences", 1),
            code_map=row.get("code_map") if isinstance(row.get("code_map"), dict) else None,
        )
        enriched_rows.append({"incident_id": _clean(row.get("incident_id"), 80), **reasoning})
    return {
        "schema": 1,
        "source_schema": source.get("schema"),
        "reasoned_incidents": enriched_rows,
        "summary": {
            "reasoned": len(enriched_rows),
            "human_review_required": sum(
                bool((x.get("assessment") or {}).get("human_review_required")) for x in enriched_rows
            ),
            "p0_p1": sum(
                (x.get("assessment") or {}).get("priority") in {"P0", "P1"} for x in enriched_rows
            ),
        },
        "safety": {
            "read_only_report_enrichment": True,
            "learned_text_executable": False,
            "auto_patch_from_reasoning": False,
            "cross_domain_state_merge": False,
        },
    }


def _self_test() -> None:
    tablet = enrich_incident(
        {
            "domain": "tablet",
            "severity": "high",
            "stage": "BOOT_HEALTH",
            "path": "ANDROID_AUTO_START_INSTALL.sh",
            "error_type": "TimeoutError",
            "message": "Termux reboot health check timed out on localhost 8765",
            "evidence": "api/v135-health failed after reboot",
        },
        occurrences=4,
        code_map={"available": True, "structural_risk": "high"},
    )
    assert tablet["assessment"]["domain"]["domain"] == "tablet"
    assert tablet["assessment"]["root_cause"]["family"] in {"startup_runtime", "network_dns_timeout"}
    assert tablet["assessment"]["priority"] in {"P0", "P1"}
    assert tablet["safety"]["auto_patch_from_reasoning"] is False

    market = enrich_incident({"message": "price source HTTP 429 Retry-After 120", "severity": "high"})
    assert market["assessment"]["domain"]["domain"] == "market"
    assert market["assessment"]["root_cause"]["family"] == "network_rate_limit"
    assert any("Retry-After" in row for row in market["recommended_checks"])

    secret = _clean("Bearer abc.def token=123 https://example.com/private")
    assert "abc.def" not in secret and "123" not in secret and "example.com" not in secret


if __name__ == "__main__":
    _self_test()
    print(json.dumps({"ok": True, "module": "ai_reasoning_enhancer"}, sort_keys=True))
