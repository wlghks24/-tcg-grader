#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI-style automatic tracking orchestrator for TCG Grader.

This module does not execute arbitrary model output or internet patches. It
combines already-verified runtime signals (collectors, feature contract,
SELFREFINE ledger, event/link health and GitHub Actions) into a deterministic,
explainable priority report. Known repairs remain owned by the existing
verified SELFREFINE/collector self-healing modules.

Safety:
- GitHub access is read-only and restricted to api.github.com.
- 401/403/429 are never bypassed and are never retried here.
- GitHub tokens, raw response bodies and external patch text are never stored.
- Unverified search/social content cannot become executable code or verified data.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from safe_runtime import atomic_write_json, env_int, safe_read_text

ROOT = Path(__file__).resolve().parent
REPORT = ROOT / "AI_AUTO_TRACKING_REPORT.json"
STATE = ROOT / "AI_AUTO_TRACKING_STATE.json"
INTERVAL_SECONDS = env_int("TCG_AI_TRACK_INTERVAL_SECONDS", 60 * 60, 30 * 60, 6 * 60 * 60)
START_DELAY_SECONDS = env_int("TCG_AI_TRACK_START_DELAY_SECONDS", 5 * 60, 60, 30 * 60)
_RUN_LOCK = threading.Lock()
SEVERITY_ORDER = {"info": 0, "medium": 1, "high": 2, "critical": 3}
CRITICAL_WORKFLOWS = {
    "Main SELFREFINE",
    "Repository Integrity Guard",
    "Exhaustive SELFREFINE Guard",
    "Deep SELFREFINE Guard",
    "Runtime delivery guard",
    "Runtime Correctness Guard",
    "Grading Vision SELFREFINE Guard",
    "Daily 06:00 Collection ↔ Instagram Accuracy Audit",
    "Final Tablet Guard",
    "Market AI Auto Tracker",
}
IMPORTANT_FILES = (
    "releases.json",
    "market_prices.json",
    "market_watch.json",
    "promo_events.json",
    "purchase_sources.json",
    "exchange_rates.json",
)
MAX_ISSUES = 80
MAX_STATE_ROWS = 400


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(moment: dt.datetime | None = None) -> str:
    return (moment or _now()).astimezone(dt.timezone.utc).isoformat(timespec="seconds")


def _parse_time(value: Any) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        # Existing runtime files sometimes use %z without a colon.
        try:
            parsed = dt.datetime.strptime(text, "%Y-%m-%dT%H:%M:%S%z")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _age_hours(value: Any, now: dt.datetime) -> float | None:
    parsed = _parse_time(value)
    if parsed is None:
        return None
    return max(0.0, (now - parsed).total_seconds() / 3600.0)


def _read_json(path: Path, fallback: Any) -> Any:
    try:
        if path.is_symlink() or not path.is_file():
            return fallback
        raw = safe_read_text(path, max_bytes=4_000_000)
        value = json.loads(raw)
        if isinstance(fallback, dict):
            return value if isinstance(value, dict) else fallback
        if isinstance(fallback, list):
            return value if isinstance(value, list) else fallback
        return value
    except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        return fallback


def _redact(value: Any, limit: int = 320) -> str:
    text = str(value or "")
    text = re.sub(r"(?i)(authorization|token|secret|password|api[_-]?key)\s*[:=]\s*[^\s,;]+", r"\1=<redacted>", text)
    text = re.sub(r"gh[opsu]_[A-Za-z0-9_]{20,}", "<redacted-github-token>", text)
    return " ".join(text.split())[:limit]


def _issue(
    severity: str,
    code: str,
    component: str,
    evidence: Any,
    action: str,
    verification: str,
    *,
    auto_action: str = "none",
) -> dict[str, Any]:
    sev = severity if severity in SEVERITY_ORDER else "medium"
    evidence_text = _redact(evidence)
    signature_base = f"{code}|{component}|{evidence_text.lower()}"
    signature = hashlib.sha256(signature_base.encode("utf-8", "ignore")).hexdigest()[:20]
    return {
        "signature": signature,
        "severity": sev,
        "code": str(code)[:80],
        "component": str(component)[:120],
        "evidence": evidence_text,
        "next_action": str(action)[:400],
        "verification": str(verification)[:400],
        "safe_auto_action": str(auto_action)[:120],
    }


def _feature_contract_signal() -> list[dict[str, Any]]:
    try:
        from feature_contract import audit_feature_contract
        result = audit_feature_contract(str(ROOT))
    except Exception as exc:
        return [_issue(
            "high", "FEATURE_CONTRACT_AUDIT_FAILED", "feature_contract",
            f"{type(exc).__name__}: feature contract audit failed",
            "기능 계약 검사 코드를 확인하고 Main SELFREFINE 전체 회귀검사를 실행",
            "feature contract + Runtime Correctness + Exhaustive가 모두 통과하는지 확인",
            auto_action="verified_selfrefine_only",
        )]
    if bool(result.get("ok", False)):
        return []
    issues = result.get("issues") or result.get("errors") or []
    return [_issue(
        "high", "FEATURE_CONTRACT_REGRESSION", "feature_contract",
        json.dumps(issues[:8], ensure_ascii=False) if isinstance(issues, list) else str(issues),
        "누락/변경된 핵심 기능 계약을 최소범위로 복구",
        "기능별 계약검사와 전체 회귀검사를 다시 통과",
        auto_action="verified_selfrefine_only",
    )]


def _source_health_signals(now: dt.datetime, *, runtime_live: bool) -> list[dict[str, Any]]:
    data = _read_json(ROOT / "source_collection_stats.json", {})
    rows = data.get("sources") if isinstance(data.get("sources"), dict) else {}
    age = _age_hours(data.get("updated_at"), now)
    result: list[dict[str, Any]] = []

    # Repository snapshots are intentionally not the live runtime truth. In CI,
    # stale committed health is informational only; device-local runs are strict.
    if runtime_live:
        if not data.get("updated_at") or not rows:
            result.append(_issue(
                "medium", "SOURCE_HEALTH_SNAPSHOT_MISSING", "collection",
                "source_collection_stats has no fresh source rows",
                "전체 업데이트를 실행해 실제 출처 health snapshot을 갱신",
                "source_collection_stats.updated_at과 sources가 채워지는지 확인",
                auto_action="bounded_collection_refresh",
            ))
        elif age is not None and age > 8:
            result.append(_issue(
                "medium", "SOURCE_HEALTH_STALE", "collection",
                f"source health age={age:.1f}h",
                "수집기 실행상태와 네트워크를 확인하고 bounded refresh 수행",
                "갱신시각이 8시간 이내이고 핵심 수집기가 정상인지 확인",
                auto_action="bounded_collection_refresh",
            ))

    fresh_enough = age is not None and age <= 24
    if fresh_enough:
        for name, row in rows.items():
            if not isinstance(row, dict):
                continue
            failures = int(row.get("consecutive_failures") or 0)
            if failures <= 0:
                continue
            severity = "high" if failures >= 3 else "medium"
            result.append(_issue(
                severity, "SOURCE_REPEATED_FAILURE", str(name),
                f"consecutive_failures={failures}; last_http_status={row.get('last_http_status')}",
                "403/429 우회 없이 기존 collector_self_healing 정책·대체 공식경로·timeout 원인을 확인",
                "다음 정상 수집에서 consecutive_failures=0으로 복구되는지 확인",
                auto_action="collector_self_healing",
            ))
    return result


def _auto_update_signals(now: dt.datetime) -> list[dict[str, Any]]:
    data = _read_json(ROOT / "auto_update_report.json", {})
    age = _age_hours(data.get("finished_at") or data.get("updated_at"), now)
    if age is None or age > 24:
        return []
    result: list[dict[str, Any]] = []
    for row in data.get("results") or []:
        if not isinstance(row, dict) or row.get("file") not in IMPORTANT_FILES:
            continue
        remaining = row.get("remaining_collection_errors") or []
        failed = row.get("ok") is False or bool(remaining)
        if not failed:
            continue
        result.append(_issue(
            "high", "CRITICAL_COLLECTOR_UNRESOLVED", str(row.get("file")),
            f"status={row.get('status')}; remaining={remaining[:4]}",
            "해당 수집기 원인을 분류하고 검증된 fallback/재시도 정책만 적용",
            "동일 파일의 remaining_collection_errors가 비고 실제 데이터 구조검사가 통과하는지 확인",
            auto_action="collector_self_healing",
        ))
    return result


def _link_signals(now: dt.datetime) -> list[dict[str, Any]]:
    data = _read_json(ROOT / "link_health_report.json", {})
    age = _age_hours(data.get("updated_at"), now)
    if age is None or age > 24:
        return []
    broken = int(data.get("broken") or 0)
    if broken <= 0:
        return []
    return [_issue(
        "high", "BROKEN_PUBLIC_LINKS", "link_health",
        f"broken={broken}; checked={int(data.get('checked') or 0)}",
        "깨진 링크의 현재 공식 대체 URL을 확인해 최소범위 교체",
        "External Link Reachability Audit에서 broken=0인지 확인",
        auto_action="official_link_recheck",
    )]


def _event_signals(now: dt.datetime) -> list[dict[str, Any]]:
    data = _read_json(ROOT / "social_event_candidates.json", {})
    age = _age_hours(data.get("updated_at"), now)
    if age is None or age > 24:
        return []
    errors = [str(x) for x in (data.get("collection_errors") or []) if str(x).strip()]
    gaps = data.get("priority_gap_cells") or []
    result: list[dict[str, Any]] = []
    if data.get("degraded") is True and errors:
        result.append(_issue(
            "medium", "EVENT_DISCOVERY_DEGRADED", "event_watch",
            "; ".join(errors[:4]),
            "공식 계정/공식도메인 우선 경로를 재확인하고 미검증 후보는 승격하지 않음",
            "event quick/priority watch에서 fresh_collection_ok가 복구되는지 확인",
            auto_action="event_quick_watch",
        ))
    if isinstance(gaps, list) and gaps:
        result.append(_issue(
            "medium", "EVENT_PRIORITY_COVERAGE_GAP", "event_watch",
            f"gap_cells={len(gaps)}; sample={gaps[:5]}",
            "비어 있는 게임·지역·주제 조합만 공식경로 중심으로 재탐색",
            "priority_gap_cells가 감소하고 공식 검증된 후보만 학습되는지 확인",
            auto_action="event_priority_watch",
        ))
    return result


def _market_ai_signals() -> list[dict[str, Any]]:
    """Summarize the existing market-only tracker without duplicating its repair logic."""
    try:
        import market_ai_auto_tracker
        findings = market_ai_auto_tracker.scan_static(ROOT)
    except Exception as exc:
        return [_issue(
            "medium", "MARKET_AI_TRACKER_READ_FAILED", "market_ai_tracker",
            f"{type(exc).__name__}: market tracker static scan failed",
            "시세 전용 추적기 자체검사와 테스트를 실행",
            "Market AI Auto Tracker와 시세 회귀검사가 정상인지 확인",
            auto_action="market_ai_tracker",
        )]
    if not findings:
        return []
    severe = [
        row for row in findings
        if isinstance(row, dict) and str(row.get("severity") or "").lower() in {"error", "critical", "high"}
    ]
    sample = [
        f"{row.get('code')}:{row.get('path')}"
        for row in findings[:8] if isinstance(row, dict)
    ]
    return [_issue(
        "high" if severe else "medium",
        "MARKET_AI_TRACKER_FINDINGS",
        "market_ai_tracker",
        f"findings={len(findings)}; sample={sample}",
        "시세 전용 Market AI Auto Tracker의 bounded deterministic repair 또는 수동 검토 경로를 사용",
        "Market AI Auto Tracker + market regression + Main SELFREFINE가 모두 통과하는지 확인",
        auto_action="market_ai_tracker",
    )]


def _selfrefine_signals() -> list[dict[str, Any]]:
    ledger = _read_json(ROOT / "MAIN_SELFREFINE_ERROR_LEDGER.json", {})
    rows = ledger.get("errors") if isinstance(ledger.get("errors"), list) else []
    opened = [row for row in rows if isinstance(row, dict) and row.get("state") == "open"]
    if not opened:
        return []
    sample = [
        f"{row.get('stage')}:{row.get('path')}"
        for row in opened[:6]
    ]
    return [_issue(
        "high", "SELFREFINE_OPEN_ERRORS", "main_selfrefine",
        f"open={len(opened)}; sample={sample}",
        "오류코드별 격리 후 기존 verified repair rule만 적용하고 unknown error는 자동수정 금지",
        "국소 검사와 Exhaustive 전체 회귀검사를 모두 통과한 뒤 해결 학습 승격",
        auto_action="verified_selfrefine_only",
    )]


def _validate_repo(value: str) -> str | None:
    text = str(value or "").strip()
    return text if re.fullmatch(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}", text) else None


def _github_runs(repo: str, token: str | None, current_run_id: str | None) -> tuple[list[dict[str, Any]], str | None]:
    url = f"https://api.github.com/repos/{repo}/actions/runs?branch=main&per_page=60"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "tcg-grader-ai-auto-tracker/1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            raw = response.read(1_500_000)
            data = json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # No retry/bypass for access control or rate limits.
        retry_after = str(exc.headers.get("Retry-After") or "")[:20] if exc.headers else ""
        return [], f"HTTP {exc.code}" + (f" Retry-After={retry_after}" if retry_after else "")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        return [], f"{type(exc).__name__}: GitHub Actions read failed"

    runs = data.get("workflow_runs") if isinstance(data, dict) else []
    out = []
    for row in runs if isinstance(runs, list) else []:
        if not isinstance(row, dict):
            continue
        run_id = str(row.get("id") or "")
        if current_run_id and run_id == current_run_id:
            continue
        out.append({
            "id": run_id,
            "name": str(row.get("name") or "")[:160],
            "status": str(row.get("status") or "")[:40],
            "conclusion": str(row.get("conclusion") or "")[:40],
            "created_at": str(row.get("created_at") or "")[:64],
            "head_sha": str(row.get("head_sha") or "")[:64],
        })
    return out[:60], None


def _github_signals(repo: str, token: str | None, current_run_id: str | None) -> list[dict[str, Any]]:
    runs, error = _github_runs(repo, token, current_run_id)
    if error:
        return [_issue(
            "medium", "GITHUB_ACTIONS_READ_UNAVAILABLE", "github_actions", error,
            "GitHub API 상태/권한을 확인하되 403/429는 우회하지 않음",
            "다음 추적 실행에서 최근 workflow 상태를 정상 조회하는지 확인",
            auto_action="none",
        )]

    latest: dict[str, dict[str, Any]] = {}
    for row in runs:
        name = row.get("name") or ""
        if not name or name in {"AI Auto Tracking", "Integrated AI Auto Tracking"}:
            continue
        if name not in latest:
            latest[name] = row

    result: list[dict[str, Any]] = []
    failed_critical = []
    for name, row in latest.items():
        if row.get("status") != "completed":
            continue
        conclusion = row.get("conclusion")
        if conclusion not in {"failure", "timed_out", "startup_failure", "action_required"}:
            continue
        critical = name in CRITICAL_WORKFLOWS
        severity = "high" if critical else "medium"
        if critical:
            failed_critical.append(name)
        result.append(_issue(
            severity, "LATEST_WORKFLOW_FAILED", name,
            f"conclusion={conclusion}; run_id={row.get('id')}; sha={row.get('head_sha')}",
            "실패 job 로그에서 최초 원인을 찾고 최소범위 수정 후 동일 workflow와 전체 회귀검사 재실행",
            "해당 workflow의 최신 completed 결론이 success인지 확인",
            auto_action="verified_selfrefine_only" if critical else "targeted_recheck",
        ))
    if len(failed_critical) >= 3:
        result.append(_issue(
            "critical", "MULTIPLE_CRITICAL_WORKFLOWS_FAILED", "github_actions",
            f"failed_critical={failed_critical[:8]}",
            "배포/자동수정 확대를 중단하고 공통 원인을 먼저 격리",
            "Repository Integrity + Main SELFREFINE + Exhaustive가 모두 success로 복구되는지 확인",
            auto_action="fail_closed",
        ))
    return result


def _load_state() -> dict[str, Any]:
    value = _read_json(STATE, {})
    if not isinstance(value, dict):
        return {"version": 1, "observations": {}}
    rows = value.get("observations")
    if not isinstance(rows, dict):
        rows = {}
    return {"version": 1, "updated_at": value.get("updated_at"), "observations": rows}


def _update_state(issues: list[dict[str, Any]], now: dt.datetime) -> tuple[dict[str, Any], dict[str, int]]:
    state = _load_state()
    rows = state.setdefault("observations", {})
    seen = {str(row.get("signature")) for row in issues if isinstance(row, dict)}
    new_count = repeat_count = resolved_count = 0

    for issue in issues:
        sig = str(issue.get("signature") or "")
        previous = rows.get(sig)
        if isinstance(previous, dict):
            repeat_count += 1
            previous["occurrences"] = min(1_000_000, int(previous.get("occurrences") or 0) + 1)
            previous["consecutive_runs"] = min(1_000_000, int(previous.get("consecutive_runs") or 0) + 1)
            previous["last_seen"] = _iso(now)
            previous["last_severity"] = issue.get("severity")
            previous["last_component"] = issue.get("component")
            previous["resolved"] = False
        else:
            new_count += 1
            rows[sig] = {
                "first_seen": _iso(now),
                "last_seen": _iso(now),
                "occurrences": 1,
                "consecutive_runs": 1,
                "resolved_count": 0,
                "last_severity": issue.get("severity"),
                "last_component": issue.get("component"),
                "resolved": False,
            }

    for sig, row in list(rows.items()):
        if sig in seen or not isinstance(row, dict):
            continue
        if row.get("resolved") is not True and int(row.get("consecutive_runs") or 0) > 0:
            resolved_count += 1
            row["resolved_count"] = min(1_000_000, int(row.get("resolved_count") or 0) + 1)
            row["last_resolved_at"] = _iso(now)
        row["consecutive_runs"] = 0
        row["resolved"] = True

    # Bound runtime learning state while preferring currently active/recent rows.
    if len(rows) > MAX_STATE_ROWS:
        ranked = sorted(
            rows.items(),
            key=lambda item: (
                item[1].get("resolved") is not True,
                str(item[1].get("last_seen") or ""),
            ),
            reverse=True,
        )
        state["observations"] = dict(ranked[:MAX_STATE_ROWS])
    state["updated_at"] = _iso(now)
    atomic_write_json(STATE, state, suffix=".ai-track-state.tmp")
    return state, {
        "new_issue_count": new_count,
        "repeat_issue_count": repeat_count,
        "resolved_since_last": resolved_count,
    }


def run_once(
    *,
    trigger: str = "manual",
    runtime_live: bool = True,
    include_github: bool = False,
    repo: str | None = None,
    token: str | None = None,
    current_run_id: str | None = None,
) -> dict[str, Any]:
    if not _RUN_LOCK.acquire(blocking=False):
        return {"ok": True, "skipped": True, "reason": "AI auto tracking already running"}
    started = time.monotonic()
    now = _now()
    try:
        issues: list[dict[str, Any]] = []
        issues.extend(_feature_contract_signal())
        issues.extend(_source_health_signals(now, runtime_live=runtime_live))
        issues.extend(_auto_update_signals(now))
        issues.extend(_link_signals(now))
        issues.extend(_event_signals(now))
        issues.extend(_market_ai_signals())
        issues.extend(_selfrefine_signals())

        github_repo = _validate_repo(repo or os.environ.get("GITHUB_REPOSITORY", ""))
        if include_github:
            if github_repo:
                issues.extend(_github_signals(
                    github_repo,
                    token if token is not None else os.environ.get("GITHUB_TOKEN"),
                    current_run_id if current_run_id is not None else os.environ.get("GITHUB_RUN_ID"),
                ))
            else:
                issues.append(_issue(
                    "medium", "GITHUB_REPOSITORY_INVALID", "github_actions",
                    "GITHUB_REPOSITORY is missing or invalid",
                    "owner/repository 형식의 읽기전용 추적대상을 설정",
                    "GitHub Actions 조회가 정상 수행되는지 확인",
                ))

        # Deterministic order keeps reports stable and easy to diff.
        issues = sorted(
            issues[:MAX_ISSUES],
            key=lambda row: (-SEVERITY_ORDER.get(str(row.get("severity")), 0), str(row.get("component")), str(row.get("code"))),
        )
        state, learning = _update_state(issues, now)
        counts = {name: 0 for name in SEVERITY_ORDER}
        for row in issues:
            counts[str(row.get("severity"))] = counts.get(str(row.get("severity")), 0) + 1
        status = (
            "critical" if counts["critical"] else
            "high" if counts["high"] else
            "warning" if counts["medium"] else
            "pass"
        )
        report = {
            "version": 1,
            "engine": "ai-auto-tracking-v27-deterministic-selfrefine-orchestrator",
            "generated_at": _iso(now),
            "trigger": str(trigger)[:80],
            "status": status,
            "ok": status in {"pass", "warning"},
            "actionable": bool(counts["critical"] or counts["high"]),
            "summary": {
                "critical": counts["critical"],
                "high": counts["high"],
                "medium": counts["medium"],
                "info": counts["info"],
                **learning,
                "tracked_state_rows": len(state.get("observations", {})),
                "runtime_live": bool(runtime_live),
                "github_actions_checked": bool(include_github and github_repo),
            },
            "issues": issues,
            "safety": {
                "arbitrary_model_code_execution": False,
                "internet_patch_execution": False,
                "github_write": False,
                "github_read_only": True,
                "github_host_allowlist": ["api.github.com"],
                "http_403_429_bypass": False,
                "raw_external_body_persisted": False,
                "token_persisted": False,
                "unverified_source_auto_promotion": False,
                "verified_selfrefine_only_for_code_repair": True,
            },
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
        atomic_write_json(REPORT, report, suffix=".ai-track-report.tmp")
        return report
    finally:
        _RUN_LOCK.release()


def public_report() -> dict[str, Any]:
    data = _read_json(REPORT, {})
    if not data:
        return {
            "ok": True,
            "status": "not-run",
            "generated_at": None,
            "summary": {},
            "issues": [],
            "safety": {
                "github_write": False,
                "http_403_429_bypass": False,
                "verified_selfrefine_only_for_code_repair": True,
            },
        }
    issues = []
    for row in data.get("issues") or []:
        if not isinstance(row, dict):
            continue
        issues.append({
            key: row.get(key)
            for key in ("severity", "code", "component", "evidence", "next_action", "verification", "safe_auto_action")
        })
    return {
        "ok": bool(data.get("ok")),
        "status": data.get("status"),
        "generated_at": data.get("generated_at"),
        "summary": data.get("summary", {}),
        "issues": issues[:30],
        "safety": data.get("safety", {}),
    }


def loop() -> None:
    time.sleep(START_DELAY_SECONDS)
    while True:
        started = time.monotonic()
        try:
            report = run_once(trigger="runtime-hourly", runtime_live=True)
            print(
                "AI 자동추적: " + json.dumps({
                    "status": report.get("status"),
                    "summary": report.get("summary"),
                }, ensure_ascii=False),
                flush=True,
            )
        except Exception as exc:
            print(f"AI 자동추적 오류 격리: {type(exc).__name__}", flush=True)
        elapsed = time.monotonic() - started
        time.sleep(max(60.0, INTERVAL_SECONDS - elapsed))


def _exit_for_threshold(report: dict[str, Any], threshold: str | None) -> int:
    if not threshold:
        return 0
    rank = SEVERITY_ORDER.get(threshold, SEVERITY_ORDER["high"])
    for row in report.get("issues") or []:
        if SEVERITY_ORDER.get(str(row.get("severity")), 0) >= rank:
            return 2
    return 0


def self_test() -> None:
    assert _validate_repo("wlghks24/-tcg-grader") == "wlghks24/-tcg-grader"
    assert _validate_repo("../bad") is None
    assert _redact("token=ghp_abcdefghijklmnopqrstuvwxyz123456") == "token=<redacted>"
    assert SEVERITY_ORDER["critical"] > SEVERITY_ORDER["high"] > SEVERITY_ORDER["medium"]
    print("AI auto tracking safety contract: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--github", action="store_true")
    parser.add_argument("--runtime-live", action="store_true")
    parser.add_argument("--trigger", default="manual")
    parser.add_argument("--repo", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--fail-on", choices=("medium", "high", "critical"), default=None)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    report = run_once(
        trigger=args.trigger,
        runtime_live=args.runtime_live,
        include_github=args.github,
        repo=args.repo,
    )
    if args.output:
        output = Path(args.output)
        if output.is_absolute() or ".." in output.parts:
            raise SystemExit("output path must stay inside repository")
        atomic_write_json(ROOT / output, report, suffix=".ai-track-cli.tmp")
    print(json.dumps({
        "status": report.get("status"),
        "actionable": report.get("actionable"),
        "summary": report.get("summary"),
        "issues": report.get("issues", [])[:12],
    }, ensure_ascii=False))
    return _exit_for_threshold(report, args.fail_on)


if __name__ == "__main__":
    raise SystemExit(main())
