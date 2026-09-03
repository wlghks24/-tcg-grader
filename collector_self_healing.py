#!/usr/bin/env python3
"""Bounded, evidence-driven recovery policy for collectors.

The module never executes text learned from errors and never rewrites Python source.
It learns which allow-listed recovery policy worked for each collector/error family,
applies that policy on the next run, and retires policies that repeatedly fail.
Structural/source changes are quarantined for a code-and-test repair instead of being
allowed to teach unverified data as truth. Structural/code failures are also sent to
tcg_code_repair_learning, which builds a bounded code+test candidate queue without
automatically editing source files.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

import auto_repair_engine
import tcg_code_repair_learning
from safe_runtime import atomic_write_json, bounded_int, safe_read_text

ROOT = Path(__file__).resolve().parent
MEMORY = ROOT / "collector_self_heal_memory.json"
MAX_FILES = 64
MAX_EVENTS = 300
MAX_SIGNATURES_PER_FILE = 80

# These are code-defined capabilities, not commands loaded from the learning file.
POLICIES = {
    "transient_balanced": {
        "max_attempts": 3, "timeout_floor": 90, "retry_delay": 3,
        "env": {"TCG_HEAL_TRANSIENT_RETRY": "1"},
        "label": "일시 연결오류 재시도 확대",
    },
    "transient_patient": {
        "max_attempts": 3, "timeout_floor": 150, "retry_delay": 5,
        "env": {"TCG_HEAL_TRANSIENT_RETRY": "1"},
        "label": "느린 출처 대기시간 확대",
    },
    "rate_limit_cooldown": {
        "max_attempts": 2, "timeout_floor": 120, "retry_delay": 8,
        "env": {"TCG_HEAL_RATE_LIMIT": "1"},
        "label": "요청 제한 안전 대기",
    },
    "server_route_retry": {
        "max_attempts": 3, "timeout_floor": 90, "retry_delay": 4,
        "env": {"TCG_HEAL_CANONICAL_ROUTE": "1"},
        "label": "서버오류 정규 경로 재확인",
    },
    "timeout_isolation": {
        "max_attempts": 2, "timeout_floor": 180, "retry_delay": 3,
        "env": {"TCG_HEAL_TIMEOUT_ISOLATION": "1"},
        "label": "시간초과 출처 분리 수집",
    },
}

QUARANTINE_CODES = {
    "SOURCE_STRUCTURE_CHANGED", "DATA_SCHEMA_ERROR", "DATA_VALUE_ERROR",
    "INTERNAL_CODE_ERROR", "SECURITY_POLICY_BLOCK", "FILE_PERMISSION_ERROR",
}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _default() -> dict:
    return {
        "version": 1, "updated_at": None, "runs": 0, "files": {},
        "events": [], "quarantine": [],
        "safety": {
            "learned_text_executable": False,
            "source_rewrite": False,
            "unverified_data_promotion": False,
            "allowlisted_policy_only": True,
        },
    }


def _file_row() -> dict:
    return {
        "signatures": {}, "pending_policy": None, "last_applied_policy": None,
        "cooldown_until": None, "cooldown_kind": None, "access_control_blocked": False,
    }


def _parse_utc(value) -> dt.datetime | None:
    if not isinstance(value, str) or len(value) > 80:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _safe_int(value: Any, default: int = 0, maximum: int = 1_000_000) -> int:
    return bounded_int(value, default, 0, maximum)


def _load(path: Path = MEMORY) -> dict:
    try:
        value = json.loads(safe_read_text(path, max_bytes=2_000_000))
    except (OSError, ValueError, TypeError, UnicodeError):
        return _default()
    if not isinstance(value, dict) or not isinstance(value.get("files"), dict):
        return _default()
    clean = _default()
    clean["updated_at"] = value.get("updated_at") if isinstance(value.get("updated_at"), str) else None
    clean["runs"] = _safe_int(value.get("runs"))
    for filename, raw in list(value["files"].items())[:MAX_FILES]:
        if not isinstance(filename, str) or Path(filename).name != filename or not isinstance(raw, dict):
            continue
        row = _file_row()
        signatures = raw.get("signatures") if isinstance(raw.get("signatures"), dict) else {}
        for signature, stat in list(signatures.items())[:MAX_SIGNATURES_PER_FILE]:
            if not isinstance(signature, str) or len(signature) > 120 or not isinstance(stat, dict):
                continue
            policies = {}
            for policy_id, score in (stat.get("policies") or {}).items():
                if policy_id not in POLICIES or not isinstance(score, dict):
                    continue
                policies[policy_id] = {
                    "runs": _safe_int(score.get("runs")),
                    "successes": _safe_int(score.get("successes")),
                    "failures": _safe_int(score.get("failures")),
                }
            row["signatures"][signature] = {
                "code": str(stat.get("code") or "UNCLASSIFIED_ERROR")[:80],
                "occurrences": _safe_int(stat.get("occurrences")),
                "last_seen": stat.get("last_seen"),
                "policies": policies,
            }
        for field in ("pending_policy", "last_applied_policy"):
            candidate = raw.get(field)
            if candidate in POLICIES:
                row[field] = candidate
        cooldown_until = _parse_utc(raw.get("cooldown_until"))
        if cooldown_until is not None:
            row["cooldown_until"] = cooldown_until.isoformat(timespec="seconds")
        if raw.get("cooldown_kind") in {"retry_after", "default_rate_limit"}:
            row["cooldown_kind"] = raw["cooldown_kind"]
        row["access_control_blocked"] = raw.get("access_control_blocked") is True
        clean["files"][filename] = row
    clean["events"] = [x for x in (value.get("events") or [])[-MAX_EVENTS:] if isinstance(x, dict)]
    clean["quarantine"] = [x for x in (value.get("quarantine") or [])[-MAX_EVENTS:] if isinstance(x, dict)]
    return clean


def _save(memory: dict, path: Path = MEMORY) -> None:
    memory["updated_at"] = _now()
    memory["events"] = memory.get("events", [])[-MAX_EVENTS:]
    memory["quarantine"] = memory.get("quarantine", [])[-MAX_EVENTS:]
    atomic_write_json(path, memory, suffix=".self-heal.tmp")


def _signature(filename: str, analysis: dict) -> str:
    raw = f"{filename}|{analysis.get('code')}|{analysis.get('error_subtype')}"
    return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:20]


def _policy_candidates(analysis: dict) -> list[str]:
    code = str(analysis.get("code") or "")
    status = analysis.get("http_status")
    subtype = str(analysis.get("error_subtype") or "")
    if status == 429 or "rate" in subtype:
        return ["rate_limit_cooldown", "transient_patient"]
    if status in {500, 502, 503, 504}:
        return ["server_route_retry", "transient_patient"]
    if code == "NETWORK_TIMEOUT":
        return ["timeout_isolation", "transient_patient"]
    if code in {"NETWORK_ERROR", "DNS_ERROR", "TLS_ERROR"} or analysis.get("bounded_retry_allowed") is True:
        return ["transient_balanced", "transient_patient"]
    return []


def _choose_policy(stat: dict, candidates: list[str]) -> str | None:
    """Prefer proven policies, but try an unused fallback after repeated failure."""
    scored = []
    policies = stat.setdefault("policies", {})
    for index, policy_id in enumerate(candidates):
        score = policies.get(policy_id) if isinstance(policies.get(policy_id), dict) else {}
        runs = _safe_int(score.get("runs"))
        successes = _safe_int(score.get("successes"))
        failures = _safe_int(score.get("failures"))
        if runs >= 3 and successes == 0:
            continue
        confidence = (successes + 1.0) / (runs + 2.0)
        exploration = 0.16 if runs == 0 else 0.0
        scored.append((confidence + exploration - failures * 0.04 - index * 0.02, policy_id))
    return max(scored)[1] if scored else None


def plan_for(filename: str, path: Path = MEMORY) -> dict:
    """Return a defensive copy of the pending allow-listed plan for one job."""
    memory = _load(path)
    row = memory.get("files", {}).get(filename, {})
    policy_id = row.get("pending_policy")
    policy = POLICIES.get(policy_id)
    until = _parse_utc(row.get("cooldown_until"))
    remaining = max(0, int((until - dt.datetime.now(dt.timezone.utc)).total_seconds())) if until else 0
    cooldown = {
        "cooldown_active": remaining > 0,
        "cooldown_remaining_seconds": remaining,
        "cooldown_kind": row.get("cooldown_kind"),
        "access_control_blocked": row.get("access_control_blocked") is True,
    }
    if not policy:
        return {"policy_id": None, "max_attempts": 2, "timeout_floor": 0, "retry_delay": 2, "env": {}, **cooldown}
    return {"policy_id": policy_id, **policy, "env": dict(policy.get("env") or {}), **cooldown}


def observe(report: dict, path: Path = MEMORY) -> dict:
    """Reward applied policies and prepare the next bounded recovery plan."""
    memory = _load(path)
    memory["runs"] = min(1_000_000, _safe_int(memory.get("runs")) + 1)
    applied = recovered = quarantined = prepared = 0
    for result in (report.get("results") or [])[:100]:
        if not isinstance(result, dict):
            continue
        filename = result.get("file")
        if not isinstance(filename, str) or Path(filename).name != filename:
            continue
        file_row = memory.setdefault("files", {}).setdefault(filename, _file_row())
        if result.get("cooldown_deferred") is True:
            memory.setdefault("events", []).append({
                "timestamp": _now(), "file": filename, "ok": bool(result.get("ok")),
                "unresolved": True, "applied_policy": None,
                "next_policy": file_row.get("pending_policy"), "cooldown_deferred": True,
            })
            continue
        applied_policy = result.get("self_heal_policy")
        remaining = result.get("remaining_collection_errors")
        unresolved = bool(remaining) or not bool(result.get("ok"))
        details = auto_repair_engine._report_error_details(result, bool(result.get("ok")))[0]
        analyses = [auto_repair_engine.analyze_error(detail) for detail in details]
        if applied_policy in POLICIES:
            applied += 1
            file_row["last_applied_policy"] = applied_policy
            # Attribute the outcome to every matching signature seen in this run.
            targets = analyses or [{"code": "RECOVERY_CHECK", "error_subtype": "clean"}]
            for analysis in targets:
                sig = _signature(filename, analysis)
                stat = file_row.setdefault("signatures", {}).setdefault(sig, {
                    "code": str(analysis.get("code") or ""), "occurrences": 0,
                    "last_seen": _now(), "policies": {},
                })
                score = stat.setdefault("policies", {}).setdefault(
                    applied_policy, {"runs": 0, "successes": 0, "failures": 0}
                )
                score["runs"] = min(1_000_000, _safe_int(score.get("runs")) + 1)
                key = "failures" if unresolved else "successes"
                score[key] = min(1_000_000, _safe_int(score.get(key)) + 1)
            if not unresolved:
                recovered += 1

        next_policy = None
        next_cooldown_seconds = None
        next_cooldown_kind = None
        access_control_blocked = False
        for detail, analysis in zip(details, analyses):
            sig = _signature(filename, analysis)
            stat = file_row.setdefault("signatures", {}).setdefault(sig, {
                "code": str(analysis.get("code") or ""), "occurrences": 0,
                "last_seen": _now(), "policies": {},
            })
            stat["occurrences"] = min(1_000_000, _safe_int(stat.get("occurrences")) + 1)
            stat["last_seen"] = _now()
            if analysis.get("code") in QUARANTINE_CODES:
                memory.setdefault("quarantine", []).append({
                    "timestamp": _now(), "file": filename, "signature": sig,
                    "code": analysis.get("code"),
                    "reason": "검증된 코드·파서 수정 필요; 자동 데이터 승격 금지",
                    "detail": auto_repair_engine.redact_sensitive(detail, 500),
                })
                quarantined += 1
                continue
            candidate = _choose_policy(stat, _policy_candidates(analysis))
            if candidate:
                next_policy = candidate
            if analysis.get("http_status") == 429:
                retry_after = _safe_int(analysis.get("retry_after_seconds"), 0, 86_400)
                next_cooldown_seconds = retry_after or 300
                next_cooldown_kind = "retry_after" if retry_after else "default_rate_limit"
            elif analysis.get("http_status") in {401, 403}:
                access_control_blocked = True
            if candidate or next_cooldown_seconds or access_control_blocked:
                break
        file_row["pending_policy"] = next_policy if unresolved else None
        if unresolved and next_cooldown_seconds:
            until = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=next_cooldown_seconds)
            file_row["cooldown_until"] = until.isoformat(timespec="seconds")
            file_row["cooldown_kind"] = next_cooldown_kind
        elif not unresolved:
            file_row["cooldown_until"] = None
            file_row["cooldown_kind"] = None
        file_row["access_control_blocked"] = bool(unresolved and access_control_blocked)
        if next_policy:
            prepared += 1
        memory.setdefault("events", []).append({
            "timestamp": _now(), "file": filename, "ok": bool(result.get("ok")),
            "unresolved": unresolved, "applied_policy": applied_policy if applied_policy in POLICIES else None,
            "next_policy": file_row.get("pending_policy"),
        })

    _save(memory, path)
    try:
        code_repair = tcg_code_repair_learning.observe(report)
    except Exception as exc:
        # Code-repair learning is advisory. It must never make collection fail.
        code_repair = {
            "ok": False,
            "error": auto_repair_engine.redact_sensitive(f"{type(exc).__name__}: {exc}", 500),
            "safety": {"source_rewrite": False, "git_write": False},
        }
    return {
        "ok": True, "runs": memory["runs"], "policy_applied": applied,
        "policy_recovered": recovered, "next_policy_prepared": prepared,
        "quarantined_for_code_repair": quarantined,
        "active_files": sum(1 for row in memory.get("files", {}).values() if row.get("pending_policy")),
        "code_repair_learning": code_repair,
        "safety": memory["safety"],
    }


def public_status(path: Path = MEMORY) -> dict:
    memory = _load(path)
    active = []
    for filename, row in memory.get("files", {}).items():
        policy_id = row.get("pending_policy")
        plan = plan_for(filename, path)
        if policy_id in POLICIES or plan.get("cooldown_active") or plan.get("access_control_blocked"):
            label = (POLICIES[policy_id]["label"] if policy_id in POLICIES
                     else "접근제어 차단 · 자동 우회 금지")
            active.append({"file": filename, "policy_id": policy_id, "label": label,
                           "cooldown_active": plan.get("cooldown_active", False),
                           "cooldown_remaining_seconds": plan.get("cooldown_remaining_seconds", 0),
                           "cooldown_kind": plan.get("cooldown_kind"),
                           "access_control_blocked": plan.get("access_control_blocked", False)})
    try:
        code_repair = tcg_code_repair_learning.public_status()
    except Exception as exc:
        code_repair = {"ok": False, "error": auto_repair_engine.redact_sensitive(f"{type(exc).__name__}: {exc}", 500)}
    return {
        "ok": True, "runs": memory.get("runs", 0), "active": active,
        "quarantine_count": len(memory.get("quarantine", [])),
        "recent_quarantine": memory.get("quarantine", [])[-10:],
        "code_repair_learning": code_repair,
        "safety": memory.get("safety", {}),
    }
