#!/usr/bin/env python3
"""AI automatic incident tracker for the TCG grader control plane.

This is an orchestrator, not an unrestricted code rewriter. It detects/deduplicates
incidents, routes them to the correct domain, retries only transient operations,
and hands Main-domain candidates to the existing SELFREFINE quarantine system.
Cross-domain learning state is never merged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Iterable

try:
    from safe_runtime import atomic_write_json, exclusive_file_lock, diagnostic_exception
except ImportError:  # isolated test fallback; repository runtime provides safe_runtime
    from contextlib import contextmanager
    def atomic_write_json(path: Path, payload: Any, suffix: str = ".tmp") -> None:
        tmp = Path(str(path) + suffix)
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    @contextmanager
    def exclusive_file_lock(_: Path):
        yield
    def diagnostic_exception(exc: BaseException, limit: int = 320) -> str:
        return f"{type(exc).__name__}: {str(exc)}"[:limit]

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "AI_AUTO_TRACKER_STATE.json"
REPORT = ROOT / "AI_AUTO_TRACKER_REPORT.json"
SCHEMA = 1
MAX_INCIDENTS = 500
MAX_HISTORY = 300
MAX_TEXT = 320
TRANSIENT_HTTP = {408, 425, 429, 500, 502, 503, 504}

DOMAIN_GITHUB = "github"
DOMAIN_MARKET = "market"
DOMAIN_TABLET = "tablet"
DOMAINS = {DOMAIN_GITHUB, DOMAIN_MARKET, DOMAIN_TABLET}

MARKET_HINTS = (
    "price", "market", "collector", "source", "currency", "krw", "jpy", "usd",
    "403", "429", "rate limit", "listing", "transaction", "시세", "수집", "가격",
)
TABLET_HINTS = (
    "tablet", "termux", "android", "lenovo", "tailscale", "boot", "autostart",
    "background", "localhost", "8765", "browser", "iphone", "태블릿", "재부팅",
)
GITHUB_HINTS = (
    "github", "workflow", "action", "ci", "test", "dependency", "security",
    "deploy", "syntax", "repository", "pull request", "commit",
)
SECRET_PATTERNS = (
    re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)\b(api[_-]?key|token|password|passwd|secret)\s*[=:]\s*[^\s,;]+"),
)
URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+", re.I)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean(value: Any, limit: int = MAX_TEXT) -> str:
    text = " ".join(str(value or "").replace("\x00", " ").split())
    text = URL_PATTERN.sub("<url>", text)
    for pattern in SECRET_PATTERNS:
        text = pattern.sub(lambda m: f"{m.group(1)} <redacted>", text)
    return text[:limit]


def classify_domain(event: dict[str, Any]) -> str:
    explicit = _clean(event.get("domain"), 20).lower()
    if explicit in DOMAINS:
        return explicit
    haystack = " ".join(
        _clean(event.get(k), 500).lower()
        for k in ("stage", "path", "message", "evidence", "source")
    )
    scores = {
        DOMAIN_MARKET: sum(token in haystack for token in MARKET_HINTS),
        DOMAIN_TABLET: sum(token in haystack for token in TABLET_HINTS),
        DOMAIN_GITHUB: sum(token in haystack for token in GITHUB_HINTS),
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else DOMAIN_GITHUB


def severity_for(event: dict[str, Any]) -> str:
    raw = _clean(event.get("severity"), 20).lower()
    if raw in {"critical", "high", "medium", "low"}:
        return raw
    text = " ".join(_clean(event.get(k), 300).lower() for k in ("stage", "message", "evidence"))
    if any(x in text for x in ("security_high", "data loss", "corrupt", "credential", "secret leak")):
        return "critical"
    if any(x in text for x in ("syntax", "startup", "deploy", "unavailable", "crash", "403", "429")):
        return "high"
    if any(x in text for x in ("timeout", "stale", "mismatch", "failed", "error")):
        return "medium"
    return "low"


def fingerprint(event: dict[str, Any], domain: str | None = None) -> str:
    dom = domain or classify_domain(event)
    parts = (
        dom,
        _clean(event.get("stage"), 80).lower(),
        _clean(event.get("path"), 240).replace("\\", "/").lower(),
        _clean(event.get("error_type") or event.get("message"), 220).lower(),
    )
    return hashlib.sha256("|".join(parts).encode("utf-8", "replace")).hexdigest()[:24]


def _default_state() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "updated_at": None,
        "incidents": {},
        "history": [],
        "domain_state_isolation": True,
        "auto_source_patch_from_learned_text": False,
        "full_regression_required_for_verified_repair": True,
    }


def _load_state(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        return _default_state()
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
        return _default_state()
    state = _default_state()
    incidents = raw.get("incidents") if isinstance(raw.get("incidents"), dict) else {}
    state["incidents"] = {
        str(k)[:80]: v for k, v in list(incidents.items())[-MAX_INCIDENTS:]
        if isinstance(k, str) and isinstance(v, dict)
    }
    state["history"] = [x for x in (raw.get("history") or [])[-MAX_HISTORY:] if isinstance(x, dict)]
    return state


def _save_state(state: dict[str, Any], path: Path) -> None:
    state["updated_at"] = _now()
    state["history"] = state.get("history", [])[-MAX_HISTORY:]
    if len(state.get("incidents", {})) > MAX_INCIDENTS:
        ranked = sorted(
            state["incidents"].items(),
            key=lambda kv: (str(kv[1].get("last_seen") or ""), kv[0]),
        )[-MAX_INCIDENTS:]
        state["incidents"] = dict(ranked)
    atomic_write_json(path, state, suffix=".ai-tracker.tmp")


@dataclass(frozen=True)
class RetryDecision:
    retryable: bool
    delay_seconds: float
    reason: str


def _http_status(exc: BaseException) -> int | None:
    for attr in ("code", "status", "status_code"):
        try:
            value = int(getattr(exc, attr))
            if 100 <= value <= 599:
                return value
        except (AttributeError, TypeError, ValueError, OverflowError):
            pass
    return None


def _retry_after_seconds(exc: BaseException, now_ts: float | None = None) -> float | None:
    headers = getattr(exc, "headers", None)
    if headers is None:
        return None
    try:
        raw = headers.get("Retry-After")
    except (AttributeError, TypeError):
        return None
    if raw is None:
        return None
    text = str(raw).strip()
    if text.isdigit():
        return min(3600.0, float(text))
    try:
        target = parsedate_to_datetime(text)
        if target.tzinfo is None:
            target = target.replace(tzinfo=timezone.utc)
        current = datetime.fromtimestamp(now_ts if now_ts is not None else time.time(), timezone.utc)
        return max(0.0, min(3600.0, (target - current).total_seconds()))
    except (TypeError, ValueError, OverflowError):
        return None


def retry_decision(exc: BaseException, attempt: int, *, base: float = 0.5, cap: float = 30.0,
                   rng: Callable[[], float] = random.random) -> RetryDecision:
    status = _http_status(exc)
    retryable = isinstance(exc, (TimeoutError, ConnectionError)) or status in TRANSIENT_HTTP
    if not retryable:
        return RetryDecision(False, 0.0, f"non_transient:{status or type(exc).__name__}")
    retry_after = _retry_after_seconds(exc)
    if retry_after is not None:
        return RetryDecision(True, retry_after, "retry_after")
    upper = min(max(0.05, cap), max(0.05, base) * (2 ** max(0, min(10, attempt))))
    return RetryDecision(True, round(upper * max(0.0, min(1.0, rng())), 3), "exponential_full_jitter")


def call_with_retry(operation: Callable[[], Any], *, attempts: int = 4,
                    sleeper: Callable[[float], None] = time.sleep) -> Any:
    total = max(1, min(8, int(attempts)))
    for attempt in range(total):
        try:
            return operation()
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            decision = retry_decision(exc, attempt)
            if not decision.retryable or attempt + 1 >= total:
                raise
            sleeper(decision.delay_seconds)
    raise RuntimeError("unreachable retry state")


def _handoff_payload(event: dict[str, Any], incident_id: str, domain: str) -> dict[str, Any]:
    return {
        "incident_id": incident_id,
        "domain": domain,
        "stage": _clean(event.get("stage"), 80) or "UNKNOWN",
        "path": _clean(event.get("path"), 240).replace("\\", "/"),
        "severity": severity_for(event),
        "error_type": _clean(event.get("error_type") or "unknown", 100),
        "evidence": _clean(event.get("evidence") or event.get("message"), 240),
        "observed_at": _now(),
    }


def _main_selfrefine_observe(event: dict[str, Any]) -> dict[str, Any] | None:
    """Use existing verified-rule quarantine; never invent a patch from tracker state."""
    try:
        import selfrefine_error_quarantine as quarantine
    except ImportError:
        return None
    row = {
        "state": "open",
        "stage": _clean(event.get("stage"), 80) or "AI_TRACKER_RUNTIME",
        "path": _clean(event.get("path"), 240).replace("\\", "/"),
        "evidence": _clean(event.get("evidence") or event.get("message"), 320),
    }
    try:
        result = quarantine.observe_open_errors([row])
    except Exception as exc:
        return {"ok": False, "error": diagnostic_exception(exc)}
    return {"ok": True, "result": result}


def observe(events: Iterable[dict[str, Any]], *, state_path: Path = STATE,
            dry_run: bool = False) -> dict[str, Any]:
    normalized = [dict(x) for x in events if isinstance(x, dict)]
    with exclusive_file_lock(state_path):
        state = _load_state(state_path)
        observed: list[dict[str, Any]] = []
        handoffs: list[dict[str, Any]] = []
        selfrefine: list[dict[str, Any]] = []
        now = _now()
        for event in normalized:
            domain = classify_domain(event)
            iid = fingerprint(event, domain)
            incident = state["incidents"].get(iid, {})
            count = min(1_000_000, int(incident.get("occurrences", 0) or 0) + 1)
            status = "new" if count == 1 else "recurring"
            row = {
                "incident_id": iid,
                "domain": domain,
                "severity": severity_for(event),
                "status": status,
                "occurrences": count,
                "stage": _clean(event.get("stage"), 80) or "UNKNOWN",
                "path": _clean(event.get("path"), 240).replace("\\", "/"),
                "error_type": _clean(event.get("error_type") or "unknown", 100),
                "message": _clean(event.get("message") or event.get("evidence"), 240),
                "first_seen": incident.get("first_seen") or now,
                "last_seen": now,
            }
            observed.append(row)
            handoffs.append(_handoff_payload(event, iid, domain))
            if not dry_run:
                state["incidents"][iid] = row
                state["history"].append({
                    "at": now, "incident_id": iid, "domain": domain,
                    "event": "incident_observed", "status": status,
                })
            if domain == DOMAIN_GITHUB and not dry_run:
                result = _main_selfrefine_observe(event)
                if result is not None:
                    selfrefine.append({"incident_id": iid, **result})
        if not dry_run:
            _save_state(state, state_path)

    summary = {
        "observed": len(observed),
        "new": sum(x["status"] == "new" for x in observed),
        "recurring": sum(x["status"] == "recurring" for x in observed),
        "by_domain": {d: sum(x["domain"] == d for x in observed) for d in sorted(DOMAINS)},
        "critical_high": sum(x["severity"] in {"critical", "high"} for x in observed),
        "dry_run": dry_run,
    }
    return {
        "schema": SCHEMA,
        "generated_at": _now(),
        "summary": summary,
        "incidents": observed,
        "handoffs": handoffs,
        "main_selfrefine": selfrefine,
        "safety": {
            "domain_state_isolation": True,
            "passive_cross_domain_handoff_only": True,
            "learned_text_executable": False,
            "unverified_patch_generation": False,
            "full_regression_required_for_verified_repair": True,
        },
    }


def events_from_json(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        rows = raw
    elif isinstance(raw, dict) and isinstance(raw.get("errors"), list):
        rows = raw["errors"]
    elif isinstance(raw, dict) and isinstance(raw.get("issues"), list):
        rows = raw["issues"]
    else:
        rows = [raw] if isinstance(raw, dict) else []
    return [x for x in rows if isinstance(x, dict)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI auto tracker with isolated domain handoffs")
    parser.add_argument("--input", type=Path, help="JSON event/error report")
    parser.add_argument("--state", type=Path, default=STATE)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.input:
        try:
            events = events_from_json(args.input)
        except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
            print(json.dumps({"ok": False, "error": diagnostic_exception(exc)}, ensure_ascii=False))
            return 2
    else:
        events = []
    result = observe(events, state_path=args.state, dry_run=args.dry_run)
    if not args.dry_run:
        atomic_write_json(args.report, result, suffix=".ai-tracker-report.tmp")
    print(json.dumps(result["summary"], ensure_ascii=False, sort_keys=True))
    return 1 if result["summary"]["critical_high"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
