#!/usr/bin/env python3
"""반복 오류를 통합하고 신규 원인과 검증된 해결 경험을 누적하는 안전 학습 엔진.

v95는 교차 플랫폼 예외에 카메라·센터링·표면 결함 측정·링크·버튼·정적자원·API 연결 오류와 복합 오류 우선순위,
안정된 원인 서명과 안전한 사전학습 프로필을 적용한다. 오류 설명이나 학습된 문자열은 코드로 실행하지 않으며 자동
동작은 내장된 제한 재시도와 검증된 정상본 복원으로 제한한다.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import ipaddress
import json
import logging
import math
import os
import re
import stat
import threading
import time
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable
from safe_runtime import (
    atomic_write_text,
    bounded_int as _safe_int,
    reject_nonstandard_json as _reject_json_constant,
    safe_read_text,
    unique_json_object as _unique_json_object,
    utc_timestamp as _utc_timestamp,
    validate_public_https_url,
)

ROOT = Path(__file__).resolve().parent
MEMORY = ROOT / "auto_repair_memory.json"
SCENARIO_PROFILES = ROOT / "scenario_learning_profiles.json"
LAST_GOOD = ROOT / ".tcg_last_good"
MEMORY_LOCK = threading.RLock()
REPAIR_FILE_LOCK = threading.RLock()
MAX_ERROR_PATTERNS = 2000
MAX_ERROR_GROUPS = 500
MAX_MONITOR_HISTORY = 500
MAX_NEW_ERROR_LOG = 200
MAX_GROUP_FILES = 100
MAX_GROUP_SAMPLES = 5
MAX_RESOLUTION_HISTORY = 30
MAX_JSON_BYTES = 20_000_000
MAX_JSON_NODES = 500_000
MAX_JSON_DEPTH = 64
MAX_SCENARIO_PROFILE_BYTES = 2_000_000
MAX_SCENARIO_PROFILES = 300
MAX_SCENARIO_PROFILE_CACHE_ENTRIES = 8
MEMORY_LOCK_TIMEOUT_SECONDS = 15.0
MEMORY_STALE_LOCK_SECONDS = 60.0
SCENARIO_PROFILE_CACHE_LOCK = threading.RLock()
SCENARIO_PROFILE_CACHE: dict[tuple[Any, ...], dict[str, Any]] = {}
SCENARIO_PROFILE_CACHE_HITS = 0
SCENARIO_PROFILE_CACHE_MISSES = 0

LOGGER = logging.getLogger("tcg.auto_repair")
if not LOGGER.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    LOGGER.addHandler(handler)
LOGGER.setLevel(logging.INFO)
LOGGER.propagate = False

# 자동복구가 파일을 만져도 되는 프로젝트 파일만 명시적으로 허용한다.
SAFE_JSON_FILES = {
    "releases.json", "market_watch.json", "market_prices.json", "promo_events.json",
    "purchase_sources.json", "exchange_rates.json", "purchase_signals.json",
    "supplementary_candidates.json", "web_discovery_candidates.json",
    "learning_store.json", "verification_history.json", "auto_update_report.json",
    "auto_update_issues.json", "adaptive_collection_stats.json", "source_collection_stats.json",
    "link_health_report.json", "tcg_live_data.json", "auto_repair_memory.json",
    "verification_cycles.json", "graded_photo_candidates.json",
}

REQUIRED_JSON_FIELDS = {
    "releases.json": {"items": list},
    "market_watch.json": {"items": list},
    "market_prices.json": {"entries": dict},
    "promo_events.json": {"items": list},
    "purchase_sources.json": {"sources": list},
    "exchange_rates.json": {"rates": dict},
    "purchase_signals.json": {"items": list},
    "supplementary_candidates.json": {"items": list},
    "web_discovery_candidates.json": {"queries": list},
    "learning_store.json": {"v30_validation": list, "v11_validation": list},
    "verification_history.json": {"runs": list},
    "auto_update_report.json": {"results": list},
    "auto_update_issues.json": {"issues": list},
    "adaptive_collection_stats.json": {"jobs": dict},
    "source_collection_stats.json": {"sources": dict},
    "tcg_live_data.json": {"sources": dict, "pending": list, "applied": list},
    "auto_repair_memory.json": {"patterns": dict, "files": dict},
    "verification_cycles.json": {"results": list},
    "graded_photo_candidates.json": {"records": list, "summary": dict},
}


def _load_strict_json(path: Path) -> Any:
    try:
        raw = safe_read_text(path, max_bytes=MAX_JSON_BYTES)
        data = json.loads(raw, parse_constant=_reject_json_constant,
                          object_pairs_hook=_unique_json_object)
    except RecursionError as exc:
        raise ValueError("JSON 중첩 깊이 제한 초과") from exc
    pending = [(data, 1)]
    visited = 0
    while pending:
        value, depth = pending.pop()
        visited += 1
        if visited > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
            raise ValueError("JSON 구조 제한 초과")
        if isinstance(value, dict):
            pending.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            pending.extend((item, depth + 1) for item in value)
    return data


def _valid_project_payload(filename: str, data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    required = REQUIRED_JSON_FIELDS.get(filename, {})
    if any(not isinstance(data.get(field), expected) for field, expected in required.items()):
        return False
    try:
        if filename == "releases.json":
            if any(not isinstance(row, dict) or not all(isinstance(row.get(field), str) and row[field].strip()
                       for field in ("game", "region", "name", "source"))
                   for row in data["items"]):
                return False
        elif filename == "market_watch.json":
            if any(not isinstance(row, dict) or row.get("region") not in {"KR", "JP", "US"}
                   or row.get("asset") not in {"BOX", "HIT"}
                   or not isinstance(row.get("name"), str) or not row["name"].strip()
                   for row in data["items"]):
                return False
        elif filename == "market_prices.json":
            if any(not isinstance(key, str) or key.count("|") != 2
                   or not isinstance(row, dict) or not isinstance(row.get("display"), str)
                   or not row["display"].strip()
                   for key, row in data["entries"].items()):
                return False
        elif filename == "promo_events.json":
            if any(not isinstance(row, dict) or not all(row.get(field)
                   for field in ("game", "region", "name_ko", "source"))
                   for row in data["items"]):
                return False
        elif filename == "purchase_sources.json":
            sources = data["sources"]
            if len(sources) < 20 or any(not isinstance(row, dict) for row in sources):
                return False
            if not {"KR", "JP", "US"}.issubset({row.get("region") for row in sources}):
                return False
            for row in sources:
                if not isinstance(row.get("name"), str) or not row["name"].strip():
                    return False
                urls = [(row.get("url"), False), (row.get("url_template"), True)]
                if not any(value for value, _ in urls):
                    return False
                for value, template in urls:
                    if not value:
                        continue
                    if not isinstance(value, str) or (template and value.count("{query}") != 1):
                        return False
                    validate_public_https_url(value.replace("{query}", "TCG"))
                reference = row.get("official_reference_url")
                if reference:
                    validate_public_https_url(reference)
                category = row.get("retailer_category")
                if category is not None and category not in {
                    "general", "convenience", "hypermarket", "stationery", "toy",
                    "bookstore", "cardshop", "discount",
                }:
                    return False
                if row.get("channel") == "offline":
                    status = row.get("inventory_status")
                    if row.get("inventory_verified") is True:
                        return False
                    if status is not None and (not isinstance(status, str) or "미확인" not in status):
                        return False
                coordinates = [field in row for field in ("lat", "lon")]
                if any(coordinates) and not all(coordinates):
                    return False
                if all(coordinates):
                    lat, lon = row["lat"], row["lon"]
                    if (isinstance(lat, bool) or isinstance(lon, bool)
                            or not isinstance(lat, (int, float)) or not isinstance(lon, (int, float))
                            or not math.isfinite(lat) or not math.isfinite(lon)
                            or not -90 <= lat <= 90 or not -180 <= lon <= 180):
                        return False
        elif filename == "exchange_rates.json":
            rates = data["rates"]
            values = [rates.get("JPY_KRW"), rates.get("USD_KRW")]
            if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
                return False
            if not (0 < values[0] < 30 and 500 < values[1] < 3000):
                return False
        elif filename == "graded_photo_candidates.json":
            records = data["records"]
            if len(records) > 2_000:
                return False
            for row in records:
                if not isinstance(row, dict):
                    return False
                company = str(row.get("company") or "").upper()
                game = str(row.get("game") or "").lower()
                url = row.get("url")
                if company not in {"PSA", "BGS", "CGC", "TAG", "BRG"}:
                    return False
                if game not in {"pokemon", "onepiece", "naruto", "unknown"}:
                    return False
                if not isinstance(url, str):
                    return False
                validate_public_https_url(url)
                if row.get("official_result") is True:
                    cert = re.sub(r"[^A-Z0-9]", "", str(row.get("certification_id") or "").upper())
                    grade = row.get("official_grade", row.get("grade"))
                    if not cert or isinstance(grade, bool) or not isinstance(grade, (int, float)):
                        return False
                    if not math.isfinite(float(grade)) or not 1 <= float(grade) <= 10:
                        return False
                    if row.get("evidence_conflicts"):
                        return False
    except (KeyError, TypeError, ValueError):
        return False
    pending = [data]
    visited = 0
    while pending:
        value = pending.pop()
        visited += 1
        if visited > 200_000:
            return False
        if isinstance(value, dict):
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
        elif isinstance(value, float) and not math.isfinite(value):
            return False
    return True


def _default_memory() -> dict:
    return {
        "version": 4,
        "updated_at": None,
        "total_runs": 0,
        "invalid_report_count": 0,
        "patterns": {},
        "error_groups": {},
        "new_error_log": [],
        "learning_summary": {
            "error_group_count": 0, "new_group_count": 0,
            "recurring_group_count": 0, "unresolved_group_count": 0,
            "resolved_group_count": 0, "verified_solution_group_count": 0,
            "consolidated_event_total": 0,
        },
        "files": {},
        "monitor_known_errors": {},
        "monitor_history": [],
    }



def _canonical_report_timestamp(value: Any) -> str | None:
    """Accept a bounded ISO timestamp and normalize it to UTC.

    Report timestamps are untrusted input. Returning ``None`` keeps mappings,
    lists, control characters, and implausible dates out of learning keys and
    ordering fields.
    """
    if not isinstance(value, str):
        return None
    if not value or len(value) > 80 or re.search(r"[\x00-\x1f\x7f]", value):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    parsed = parsed.astimezone(dt.timezone.utc)
    if not 2000 <= parsed.year <= 2100:
        return None
    # A future report can pin ``last_seen`` ahead of every later real event and
    # distort retention/status ordering. Permit normal clock skew, not decades.
    if parsed > dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=24):
        return None
    return parsed.isoformat(timespec="seconds")


def _read_lock_payload(lock_path: Path) -> dict | None:
    """Read bounded lock metadata without following a symbolic link."""
    try:
        descriptor = os.open(lock_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode):
                return None
            raw = os.read(descriptor, 1024).decode("utf-8", "replace")
        finally:
            os.close(descriptor)
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else None
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def _lock_owner_alive(lock_path: Path) -> bool | None:
    """Return whether the process recorded in a lock is alive, when knowable."""
    try:
        payload = _read_lock_payload(lock_path)
        process_id = int(payload.get("pid")) if isinstance(payload, dict) else 0
    except (ValueError, TypeError, OverflowError):
        return None
    if process_id <= 0:
        return None
    try:
        os.kill(process_id, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return None


def _lock_matches_owner(lock_path: Path, owned_stat: os.stat_result | None, token: str) -> bool:
    """Confirm that cleanup still targets the lock created by this context."""
    try:
        current = os.lstat(lock_path)
    except OSError:
        return False
    if not stat.S_ISREG(current.st_mode) or owned_stat is None:
        return False
    if owned_stat.st_ino and (current.st_dev, current.st_ino) == (owned_stat.st_dev, owned_stat.st_ino):
        return True
    payload = _read_lock_payload(lock_path)
    return isinstance(payload, dict) and payload.get("token") == token


@contextmanager
def _memory_process_lock(path: Path, *, timeout_seconds: float = MEMORY_LOCK_TIMEOUT_SECONDS,
                         stale_seconds: float = MEMORY_STALE_LOCK_SECONDS):
    """Serialize each load-modify-save transaction across operating-system processes.

    ``threading.RLock`` protects threads only. A small exclusive lock file keeps a
    desktop server, scheduled updater, and verification process from overwriting
    each other's newly learned events. Lock contents are metadata, never code.
    """
    memory_path = Path(path)
    lock_path = memory_path.with_suffix(memory_path.suffix + ".lock")
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    timeout = max(0.05, min(60.0, float(timeout_seconds)))
    stale_after = max(1.0, min(3600.0, float(stale_seconds)))
    deadline = time.monotonic() + timeout
    descriptor: int | None = None
    owned_stat: os.stat_result | None = None
    token = hashlib.sha256(
        f"{os.getpid()}|{threading.get_ident()}|{time.time_ns()}".encode("ascii", "ignore")
    ).hexdigest()
    encoded = json.dumps({"pid": os.getpid(), "created_at": _utc_timestamp(), "token": token}).encode("utf-8")
    while descriptor is None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(lock_path, flags, 0o600)
            owned_stat = os.fstat(descriptor)
            if os.write(descriptor, encoded) != len(encoded):
                raise OSError("학습 잠금 메타데이터를 완전히 기록하지 못했습니다.")
            try:
                os.fsync(descriptor)
            except OSError:
                pass
            break
        except FileExistsError:
            try:
                current = os.lstat(lock_path)
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(current.st_mode) or not stat.S_ISREG(current.st_mode):
                raise ValueError("학습 메모리 잠금 경로가 안전한 일반 파일이 아닙니다.")
            age = max(0.0, time.time() - current.st_mtime)
            owner_alive = _lock_owner_alive(lock_path)
            # Never steal a lock from a process that is still alive. Age is only
            # a recovery signal when the owner cannot be identified.
            if owner_alive is False or (owner_alive is None and age >= stale_after):
                try:
                    os.unlink(lock_path)
                except FileNotFoundError:
                    pass
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError("다른 프로세스의 오류학습 저장이 끝나지 않아 안전하게 중단했습니다.")
            time.sleep(min(0.05, max(0.005, deadline - time.monotonic())))
        except Exception:
            if descriptor is not None:
                os.close(descriptor)
                descriptor = None
            if owned_stat is not None:
                try:
                    if _lock_matches_owner(lock_path, owned_stat, token):
                        os.unlink(lock_path)
                except OSError:
                    pass
            raise
    try:
        yield
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            if _lock_matches_owner(lock_path, owned_stat, token):
                os.unlink(lock_path)
        except FileNotFoundError:
            pass
        except OSError:
            LOGGER.warning("오류학습 잠금 정리 실패: %s", lock_path.name)


def _redact_ip_literal(match: re.Match[str]) -> str:
    raw = match.group(0)
    candidate = raw
    if raw.startswith("["):
        candidate = raw[1:raw.index("]")]
    elif raw.count(".") == 3 and ":" in raw:
        candidate = raw.rsplit(":", 1)[0]
    candidate = candidate.split("%", 1)[0]
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return raw
    return "<ip>"


def redact_sensitive(value: Any, limit: int = 1200) -> str:
    """Keep diagnostics useful without persisting URLs or authentication secrets."""
    bounded_limit = max(0, int(limit))
    input_limit = max(4096, min(20_000, bounded_limit * 4 + 1024))
    text = str(value if value is not None else "")[:input_limit]
    text = re.sub(r"https?://[^\s\"'<>]+", "<url>", text, flags=re.IGNORECASE)
    text = re.sub(r"(?<![\\\w])\\\\[^\\\s]+\\[^\\\s]+(?:\\[^\\\s]+)*", "<path>", text)
    text = re.sub(r"\b[A-Za-z]:[\\/](?:[^\s\\/]+[\\/])+[^\s\\/:,;]+", "<path>", text)
    text = re.sub(r"(?<![:\w])/(?:[^/\s]+/)+[^/\s:,;]+", "<path>", text)
    text = re.sub(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?::\d{1,5})?(?![\d.])", _redact_ip_literal, text)
    text = re.sub(r"\[[0-9A-Fa-f:]+(?:%[A-Za-z0-9_.-]+)?\](?::\d{1,5})?", _redact_ip_literal, text)
    text = re.sub(r"(?<![A-Za-z0-9:])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?:%[A-Za-z0-9_.-]+)?(?![A-Za-z0-9:])", _redact_ip_literal, text)
    text = re.sub(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", "Bearer <redacted>", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)\b", "<redacted>", text)
    text = re.sub(
        r"\b(api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|passwd|secret|authorization)"
        r"([\"']?\s*[=:]\s*[\"']?)([^\s,;\"'}]+)",
        lambda match: f"{match.group(1)}{match.group(2)}<redacted>",
        text,
        flags=re.IGNORECASE,
    )
    return text[:bounded_limit]


def _clean_error_template(value: Any) -> str:
    """Remove volatile values so the same root cause receives one stable key."""
    text = redact_sensitive(value, 1200).lower()
    text = re.sub(r"\b[0-9a-f]{8}-[0-9a-f-]{27,}\b", "<id>", text)
    text = re.sub(r"\b0x[0-9a-f]+\b", "<hex>", text)
    text = re.sub(r"(?:[a-z]:)?[/\\](?:[^\s:/\\]+[/\\])+[^\s:]+", "<path>", text)
    text = re.sub(r"\b\d+(?:\.\d+)?\b", "<n>", text)
    return re.sub(r"\s+", " ", text).strip()[:300]


def _safe_signature_token(value: Any, fallback: str = "general") -> str:
    token = re.sub(r"[^a-z0-9_.-]+", "-", str(value or "").lower()).strip("-.")[:80]
    return token or fallback


def _http_status_from_error(text: str) -> int | None:
    matches = re.findall(r"\b(?:http(?:\s*error)?|httperror|status(?:\s+code)?)\D{0,16}([1-5]\d{2})\b", text)
    if not matches:
        return None
    status = int(matches[-1])
    return status if 100 <= status <= 599 else None


def _diagnostic_needle_matches(needle: str, text: str) -> bool:
    """Match fixed diagnostics without confusing WinError 2 with WinError 206."""
    # Almost all diagnostic needles are literal substrings. Avoid running a
    # regular expression for each of them; only WinError rules need a numeric
    # boundary so code 2 cannot match code 206.
    if not needle.startswith("winerror"):
        return needle in text
    windows_code = re.fullmatch(r"winerror\s+(\d+)", needle)
    if windows_code:
        return re.search(rf"\bwinerror\s+{re.escape(windows_code.group(1))}\b", text) is not None
    return needle in text


def _root_cause_subtype(code: str, lowered: str, normalized: str) -> tuple[str, int | None]:
    """Build a stable root-cause signature without volatile line numbers or secrets."""
    http_status = _http_status_from_error(lowered) if code == "NETWORK_HTTP_ERROR" else None
    if code == "NETWORK_HTTP_ERROR":
        if "redirect loop" in lowered or "too many redirects" in lowered:
            return "redirect-loop", http_status
        if http_status is None and any(value in lowered for value in ("rate limit", "too many requests", "요청 제한")):
            return "rate-limit-no-status", None
        if http_status == 429:
            return "rate-limit-429", http_status
        if http_status in {401, 403}:
            return f"access-{http_status}", http_status
        if http_status in {404, 410}:
            return f"missing-{http_status}", http_status
        if http_status in {408, 425, 500, 502, 503, 504}:
            return "transient-server", http_status
        if http_status and 400 <= http_status < 500:
            return f"client-{http_status}", http_status
        if http_status and 500 <= http_status < 600:
            return f"server-{http_status}", http_status
        return "unknown-status", http_status
    if code == "INTERNAL_CODE_ERROR":
        exception = next((name for name in (
            "nameerror", "unboundlocalerror", "modulenotfounderror", "importerror",
            "attributeerror", "indexerror", "assertionerror", "zerodivisionerror",
            "notimplementederror",
        ) if name in lowered), "code-error")
        symbol = None
        for pattern in (
            r"name\s+['\"]([^'\"]+)['\"]\s+is not defined",
            r"no module named\s+['\"]([^'\"]+)['\"]",
            r"cannot import name\s+['\"]([^'\"]+)['\"]",
            r"has no attribute\s+['\"]([^'\"]+)['\"]",
            r"local variable\s+['\"]([^'\"]+)['\"]",
        ):
            match = re.search(pattern, lowered)
            if match:
                symbol = _safe_signature_token(match.group(1))
                break
        if symbol is None:
            simple = re.search(
                r"\b(?:nameerror|unboundlocalerror|modulenotfounderror|importerror|attributeerror)"
                r"\s*:\s*([a-z_][a-z0-9_.-]{1,79})(?:\s|$)",
                lowered,
            )
            if simple and simple.group(1) not in {"name", "no", "cannot"}:
                symbol = _safe_signature_token(simple.group(1))
        return f"{exception}:{symbol}" if symbol else exception, None
    if code == "PROCESS_EXECUTION_ERROR":
        if "signal" in lowered or "terminated by" in lowered:
            return "signal", None
        return "nonzero-exit", None
    if code == "PROCESS_CANCELLED":
        if any(value in lowered for value in (
            "keyboardinterrupt", "cancelled by user", "사용자 취소", "사용자 인터럽트",
        )):
            return "user-interrupt", None
        return "task-cancelled", None
    if code == "INTERNAL_SYNTAX_ERROR":
        if "indentationerror" in lowered:
            return "indentation", None
        if "taberror" in lowered:
            return "mixed-indentation", None
        return "syntax", None
    if code == "PROCESS_TIMEOUT":
        if "subprocesstimeoutexpired" in lowered or "timeoutexpired" in lowered:
            return "subprocess", None
        if "update job" in lowered or "작업 제한시간" in lowered:
            return "update-job", None
        return "worker", None
    if code == "RESOURCE_EXHAUSTION":
        if any(value in lowered for value in ("no space left", "enospc", "disk full", "디스크 공간", "winerror 112", "not enough space on the disk")):
            return "disk-space", None
        if any(value in lowered for value in ("memoryerror", "out of memory", "메모리 부족")):
            return "memory", None
        if any(value in lowered for value in ("too many open files", "emfile")):
            return "file-descriptors", None
        if any(value in lowered for value in ("can't start new thread", "cannot start new thread", "thread limit")):
            return "thread-limit", None
        if any(value in lowered for value in ("too many processes", "cannot fork", "resource temporarily unavailable", "eagain")):
            return "process-limit", None
        return "resource", None
    if code == "CONCURRENCY_CONFLICT":
        if any(value in lowered for value in ("database is locked", "database locked", "database busy")):
            return "database-lock", None
        if any(value in lowered for value in ("lock timeout", "lock acquisition timeout", "잠금 대기", "다른 프로세스")):
            return "process-lock", None
        if any(value in lowered for value in ("version conflict", "stale version", "optimistic lock", "compare-and-swap conflict")):
            return "version-conflict", None
        if any(value in lowered for value in ("winerror 32", "used by another process", "sharing violation")):
            return "sharing-violation", None
        if "brokenbarriererror" in lowered or "broken barrier" in lowered:
            return "barrier-broken", None
        if "fileexistserror" in lowered or "lock already exists" in lowered:
            return "lock-exists", None
        return "write-conflict", None
    if code == "STORAGE_CORRUPTION_ERROR":
        if any(value in lowered for value in ("wal checksum", "wal file", "write-ahead log", "recovery log")):
            return "wal-corrupt", None
        if any(value in lowered for value in ("index corruption", "corrupt index", "corrupt database index", "index is corrupt")):
            return "index-corrupt", None
        if any(value in lowered for value in ("page checksum", "database page")):
            return "page-checksum", None
        if any(value in lowered for value in ("database disk image is malformed", "file is not a database", "database header", "sqlite", "데이터베이스 손상")):
            return "sqlite-corrupt", None
        return "storage-corrupt", None
    if code == "DATA_LIMIT_ERROR":
        if any(value in lowered for value in ("too deeply nested", "중첩 깊이", "recursionerror")):
            return "depth", None
        if any(value in lowered for value in ("too large", "size limit", "용량 제한", "크기 제한")):
            return "size", None
        if any(value in lowered for value in ("too many nodes", "항목 수 제한", "노드 수")):
            return "node-count", None
        return "complexity", None
    if code == "DATA_INTEGRITY_ERROR":
        if any(value in lowered for value in ("checksum", "sha256", "hash mismatch", "해시 불일치")):
            return "checksum", None
        if any(value in lowered for value in ("truncated", "unexpected eof", "불완전 저장")):
            return "truncated", None
        if any(value in lowered for value in ("stale cache", "cache generation mismatch", "cache poisoned")):
            return "stale-cache", None
        return "integrity", None
    if code == "DATA_COMPRESSION_ERROR":
        if any(value in lowered for value in ("decompression bomb", "expansion ratio", "압축폭탄")):
            return "expansion-bomb", None
        if any(value in lowered for value in ("bad crc", "crc-32", "crc mismatch")):
            return "crc", None
        if "badgzipfile" in lowered or "not a gzipped file" in lowered:
            return "gzip", None
        if "badzipfile" in lowered or "not a zip file" in lowered or "central directory" in lowered:
            return "zip", None
        if "unsupported compression" in lowered or "지원하지 않는 압축" in lowered:
            return "unsupported-method", None
        return "compression", None
    if code == "DEPENDENCY_ERROR":
        if any(value in lowered for value in ("requires-python", "requires python", "unsupported python", "python 최소", "python version")):
            return "runtime-version", None
        if any(value in lowered for value in ("abi mismatch", "binary interface", "wrong architecture")):
            return "abi-mismatch", None
        if any(value in lowered for value in ("unsupportedwheel", "unsupported wheel", "wheel is not supported")):
            return "unsupported-wheel", None
        if any(value in lowered for value in ("runtime dependency", "required dependency", "dependency unavailable")):
            return "missing-runtime-dependency", None
        return "version-conflict", None
    if code == "SECURITY_POLICY_BLOCK":
        if any(value in lowered for value in ("ssrf", "private dns", "private ip", "dns rebinding")):
            return "private-network-target", None
        if "origin" in lowered or "요청 출처" in lowered:
            return "origin-policy", None
        if any(value in lowered for value in ("symlink", "심볼릭 링크")):
            return "symlink-path", None
        if any(value in lowered for value in ("path traversal", "경로탈출", "경로 이탈")):
            return "path-traversal", None
        if any(value in lowered for value in ("https only", "unsafe scheme", "non-https", "file://")):
            return "unsafe-scheme", None
        if any(value in lowered for value in ("credentials in url", "url credentials", "userinfo")):
            return "url-credentials", None
        if "host header" in lowered or "위조 host" in lowered:
            return "host-header", None
        if any(value in lowered for value in ("method policy", "blocked method", "허용되지 않은 method")):
            return "method-policy", None
        if any(value in lowered for value in ("xss", "script injection", "스크립트 주입")):
            return "script-injection", None
        return "policy-block", None
    if code == "NETWORK_CONNECTION_ERROR":
        if any(value in lowered for value in ("gaierror", "name resolution", "dns", "winerror 11001", "getaddrinfo failed")):
            return "dns-resolution", None
        if "refused" in lowered or "거부" in lowered or "winerror 10061" in lowered:
            return "connection-refused", None
        if any(value in lowered for value in ("temporary failure", "temporarily unavailable", "일시 확인불가")):
            return "temporary-unavailable", None
        if "urlerror" in lowered:
            return "url-connection", None
        if "connectionreseterror" in lowered or "connection reset" in lowered or "winerror 10054" in lowered:
            return "connection-reset", None
        if "connectionabortederror" in lowered or "connection abort" in lowered:
            return "connection-aborted", None
        if "brokenpipeerror" in lowered or "broken pipe" in lowered:
            return "broken-pipe", None
        if "unreachable" in lowered:
            return "unreachable", None
        return "connection", None
    if code == "NETWORK_TLS_ERROR":
        if any(value in lowered for value in ("not yet valid", "아직 유효하지")):
            return "certificate-not-yet-valid", None
        if any(value in lowered for value in ("expired", "만료")):
            return "certificate-expired", None
        if any(value in lowered for value in ("hostname mismatch", "hostname does not match", "host name mismatch", "호스트 불일치")):
            return "certificate-hostname", None
        if any(value in lowered for value in ("self signed", "self-signed", "unknown ca", "신뢰할 수 없는")):
            return "certificate-untrusted", None
        if any(value in lowered for value in ("certificate", "인증서")):
            return "certificate", None
        return "tls-protocol", None
    if code == "DATA_TIME_ERROR":
        if any(value in lowered for value in ("clock skew", "system clock", "시스템 시각")):
            return "clock-skew", None
        if any(value in lowered for value in ("timezone", "time zone", "utc offset", "시간대")):
            return "timezone", None
        if any(value in lowered for value in ("precedes start", "before start", "start date after end", "종료일이 시작일")):
            return "date-order", None
        if any(value in lowered for value in ("out of range", "date range", "날짜 범위")):
            return "date-range", None
        return "date-parse", None
    if code == "DATA_ENCODING_ERROR":
        if "utf-8 bom" in lowered or "byte order mark" in lowered:
            return "bom", None
        if "unicodedecodeerror" in lowered or "cannot decode" in lowered or "invalid utf-8" in lowered:
            return "decode", None
        if "unicodeencodeerror" in lowered or "cannot encode" in lowered:
            return "encode", None
        if "charset mismatch" in lowered or "문자셋 불일치" in lowered:
            return "charset-mismatch", None
        return "encoding", None
    if code == "SOURCE_CONTENT_TYPE_ERROR":
        if "text/html" in lowered and any(value in lowered for value in ("application/json", "json")):
            return "html-instead-of-json", None
        if "unsupported media type" in lowered:
            return "unsupported-media", None
        if "missing content-type" in lowered or "content-type missing" in lowered:
            return "missing-header", None
        return "content-type", None
    if code == "CONFIGURATION_ERROR":
        if any(value in lowered for value in ("environment variable", "env var", "환경변수")) and any(
            value in lowered for value in ("missing", "not set", "unset", "누락", "없음")
        ):
            return "missing-environment", None
        if "port" in lowered or "포트" in lowered:
            return "invalid-port", None
        if any(value in lowered for value in ("malformed configuration", "malformed config", "config file", "설정 파일")):
            return "malformed-file", None
        if any(value in lowered for value in ("unknown configuration option", "unknown config option", "unsupported option", "알 수 없는 설정")):
            return "unknown-option", None
        return "invalid-value", None
    if code == "DATA_SCHEMA_ERROR":
        if any(value in lowered for value in ("jsondecodeerror", "json decode")):
            return "json-decode", None
        if "중복 json" in lowered or "duplicate" in lowered:
            return "duplicate-key", None
        if any(value in lowered for value in ("nan", "infinity", "nonstandard number", "비표준 숫자")):
            return "nonstandard-number", None
        if any(value in lowered for value in ("top-level list", "top-level array", "root must be object", "최상위 배열")):
            return "wrong-root-type", None
        field_match = re.search(r"keyerror\s*:\s*['\"]([^'\"]+)['\"]", lowered)
        if field_match:
            return f"missing-field:{_safe_signature_token(field_match.group(1))}", None
        if any(value in lowered for value in ("필수값", "필수 자료", "required field", "missing field", "누락")):
            return "missing-required-field", None
        return "schema", None
    if code == "DATA_VALUE_ERROR":
        if any(value in lowered for value in ("nan", "infinity", "non-finite", "유한수")):
            return "nonfinite", None
        if any(value in lowered for value in ("boolean", "bool", "불리언", "true/false")):
            return "boolean", None
        if any(value in lowered for value in ("outside allowed range", "out of range", "negative price", "좌표 범위", "등급 범위", "범위 오류")):
            return "range", None
        if "decimal.invalidoperation" in lowered or "invalid decimal" in lowered:
            return "decimal", None
        if "floatingpointerror" in lowered:
            return "floating-point", None
        exception = next((name for name in ("valueerror", "typeerror", "overflowerror") if name in lowered), "value")
        return exception, None
    if code in {"FILE_MISSING", "FILE_PERMISSION_ERROR"}:
        filename = re.search(
            r"(?<![a-z0-9_.-])([a-z0-9_.-]{1,100}\.(?:json|py|js|html|webmanifest|md|txt))(?![a-z0-9_.-])",
            lowered,
        )
        prefix = "missing" if code == "FILE_MISSING" else "permission"
        return f"{prefix}:{_safe_signature_token(filename.group(1))}" if filename else f"{prefix}-file", None
    if code == "FILE_PATH_ERROR":
        if "winerror 206" in lowered or "path too long" in lowered or "filename too long" in lowered:
            return "path-too-long", None
        if "isadirectoryerror" in lowered or "is a directory" in lowered:
            return "is-directory", None
        if "notadirectoryerror" in lowered or "not a directory" in lowered:
            return "not-directory", None
        if "cross-device" in lowered or "exdev" in lowered:
            return "cross-device", None
        return "path-type", None
    if code == "SOURCE_ACCESS_CHALLENGE":
        if "captcha" in lowered:
            return "captcha", None
        return "bot-challenge", None
    if code == "CAMERA_RUNTIME_ERROR":
        if any(value in lowered for value in ("camerapermissiondenied", "카메라 권한 거부")):
            return "permission", None
        if any(value in lowered for value in ("camerasecurecontexterror", "getusermedia unavailable", "보안 컨텍스트")):
            return "secure-context", None
        if any(value in lowered for value in ("cameranotfound", "camerastreamconflict", "카메라 없음", "카메라 사용 중")):
            return "unavailable", None
        if any(value in lowered for value in ("cameraframeunavailable", "cameraframereaderror", "영상 프레임")):
            return "frame-read", None
        if any(value in lowered for value in ("cameraencodeerror", "cameracanvaserror", "촬영 인코딩")):
            return "encode", None
        if any(value in lowered for value in ("duplicatesidecapture", "앞뒷면 중복 촬영")):
            return "duplicate-side", None
        if any(value in lowered for value in ("camerafilehandofferror", "datatransferunavailable", "촬영 파일 전달")):
            return "file-handoff", None
        if any(value in lowered for value in ("camerarequestrace", "cameraresourceleak", "카메라 수명주기")):
            return "lifecycle", None
        return "camera-runtime", None
    if code == "VISION_MEASUREMENT_ERROR":
        if any(value in lowered for value in ("visionimagesizeerror", "visionimagedataerror", "사진 픽셀 형식")):
            return "input", None
        if any(value in lowered for value in ("visionqualitygate", "visionblurerror", "visionexposureerror", "visionglareerror", "촬영 품질 게이트")):
            return "quality", None
        if any(value in lowered for value in ("visioncenteringgate", "visionborderdetectionerror", "visionborderless", "내부 보더 검출")):
            return "border", None
        if any(value in lowered for value in ("visionperspectiveerror", "원근 왜곡", "과도한 기울기")):
            return "perspective", None
        if any(value in lowered for value in ("visionscratchconfidenceerror", "visionobliquemissing", "사선광 증거 부족")):
            return "surface-confidence", None
        if any(value in lowered for value in ("visionenginemissing", "visioncanvaserror", "visionbrowsercanvasunavailable", "비전 엔진 로드")):
            return "engine", None
        return "vision-runtime", None
    if code == "LINK_RUNTIME_ERROR":
        if any(value in lowered for value in ("missingbuttonbinding", "버튼 연결 누락")):
            return "button-binding", None
        if any(value in lowered for value in ("brokenanchorerror", "화면 이동 대상 누락")):
            return "anchor-target", None
        if "staticasset404" in lowered:
            return "static-asset", None
        if any(value in lowered for value in ("apiroutemismatch", "api 경로 불일치", "method mismatch")):
            return "api-route-method", None
        if any(value in lowered for value in ("serviceworkerassetmismatch", "manifesttargetmissing")):
            return "pwa-asset", None
        if any(value in lowered for value in ("unsafeblankopener", "popupblockedlink")):
            return "new-window", None
        if "externalurltemplateerror" in lowered:
            return "external-template", None
        return "link-contract", None
    if code == "SOURCE_STRUCTURE_CHANGED":
        return _safe_signature_token(normalized, "source-structure"), None
    if code == "RUNTIME_ERROR":
        return _safe_signature_token(normalized, "runtime"), None
    return "general", None


def _scenario_profile_key(analysis: dict) -> str:
    return f"{analysis.get('code','UNCLASSIFIED_ERROR')}|{analysis.get('error_subtype','general')}"


def _empty_scenario_profiles() -> dict:
    return {"ok": False, "version": 1, "scenario_count": 0, "family_count": 0, "profiles": {}}


def _scenario_profile_cache_key(target: Path) -> tuple[Any, ...]:
    metadata = target.lstat()
    if target.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise OSError("unsafe scenario profile path")
    return (
        str(target.absolute()), metadata.st_dev, metadata.st_ino, metadata.st_size,
        metadata.st_mtime_ns, metadata.st_ctime_ns,
    )


def clear_scenario_profile_cache() -> None:
    global SCENARIO_PROFILE_CACHE_HITS, SCENARIO_PROFILE_CACHE_MISSES
    with SCENARIO_PROFILE_CACHE_LOCK:
        SCENARIO_PROFILE_CACHE.clear()
        SCENARIO_PROFILE_CACHE_HITS = 0
        SCENARIO_PROFILE_CACHE_MISSES = 0


def scenario_profile_cache_info() -> dict[str, int]:
    with SCENARIO_PROFILE_CACHE_LOCK:
        return {"entries": len(SCENARIO_PROFILE_CACHE), "hits": SCENARIO_PROFILE_CACHE_HITS,
                "misses": SCENARIO_PROFILE_CACHE_MISSES}


def load_scenario_profiles(path: str | Path | None = None) -> dict:
    """Load verified advisory profiles with stat-bound caching and defensive copies."""
    global SCENARIO_PROFILE_CACHE_HITS, SCENARIO_PROFILE_CACHE_MISSES
    target = Path(path or SCENARIO_PROFILES)
    cache_key: tuple[Any, ...] | None = None
    try:
        cache_key = _scenario_profile_cache_key(target)
        with SCENARIO_PROFILE_CACHE_LOCK:
            cached = SCENARIO_PROFILE_CACHE.get(cache_key)
            if cached is not None:
                SCENARIO_PROFILE_CACHE_HITS += 1
                return copy.deepcopy(cached)
            SCENARIO_PROFILE_CACHE_MISSES += 1
        raw = safe_read_text(target, max_bytes=MAX_SCENARIO_PROFILE_BYTES)
        data = json.loads(raw, parse_constant=_reject_json_constant,
                          object_pairs_hook=_unique_json_object)
        if not isinstance(data, dict) or data.get("training_only") is not True:
            raise ValueError("시나리오 학습파일 형식 오류")
        profiles = data.get("profiles")
        if not isinstance(profiles, dict) or len(profiles) > MAX_SCENARIO_PROFILES:
            raise ValueError("시나리오 프로필 개수 오류")
        clean: dict[str, dict] = {}
        for key, row in profiles.items():
            if not isinstance(key, str) or len(key) > 220 or not isinstance(row, dict):
                continue
            code = redact_sensitive(row.get("code"), 80)
            subtype = redact_sensitive(row.get("error_subtype"), 100)
            expected_key = _scenario_profile_key({"code": code, "error_subtype": subtype,
                                                  "http_status": row.get("http_status")})
            if key != expected_key or row.get("verified") is not True:
                continue
            def strings(field: str, limit: int) -> list[str]:
                values = row.get(field) if isinstance(row.get(field), list) else []
                return [redact_sensitive(value, 400) for value in values if isinstance(value, str) and value.strip()][:limit]
            profile_id = str(row.get("profile_id") or "")
            if not re.fullmatch(r"[0-9a-f]{16}", profile_id):
                continue
            clean[key] = {
                "profile_id": profile_id, "code": code, "error_subtype": subtype,
                "http_status": row.get("http_status") if isinstance(row.get("http_status"), int) else None,
                "verified": True,
                "scenario_count": _safe_int(row.get("scenario_count"), 0, 1, 1000),
                "diagnostic_priority": _safe_int(row.get("diagnostic_priority"), 50, 1, 100),
                "first_checks": strings("first_checks", 5),
                "fast_resolution_steps": strings("fast_resolution_steps", 6),
                "verification_steps": strings("verification_steps", 6),
                "stop_conditions": strings("stop_conditions", 5),
                "bounded_retry_allowed": row.get("bounded_retry_allowed") is True,
            }
        result = {
            "ok": bool(clean), "version": _safe_int(data.get("version"), 1, 1, 999),
            "scenario_count": _safe_int(data.get("scenario_count"), 0, 0, 5000),
            "family_count": _safe_int(data.get("family_count"), 0, 0, 100),
            "profiles": clean,
        }
    except (OSError,ValueError,TypeError,json.JSONDecodeError,RecursionError):
        result = _empty_scenario_profiles()
    if cache_key is not None:
        try:
            unchanged = _scenario_profile_cache_key(target) == cache_key
        except OSError:
            unchanged = False
        if unchanged:
            with SCENARIO_PROFILE_CACHE_LOCK:
                for old_key in [key for key in SCENARIO_PROFILE_CACHE if key[0] == cache_key[0]]:
                    SCENARIO_PROFILE_CACHE.pop(old_key, None)
                while len(SCENARIO_PROFILE_CACHE) >= MAX_SCENARIO_PROFILE_CACHE_ENTRIES:
                    SCENARIO_PROFILE_CACHE.pop(next(iter(SCENARIO_PROFILE_CACHE)))
                SCENARIO_PROFILE_CACHE[cache_key] = copy.deepcopy(result)
    return copy.deepcopy(result)


def scenario_learning_summary(path: str | Path | None = None) -> dict:
    data = load_scenario_profiles(path)
    return {
        "ok": data["ok"], "version": data["version"],
        "scenario_count": data["scenario_count"], "family_count": data["family_count"],
        "verified_profile_count": len(data["profiles"]),
        "operational_occurrences_modified": False,
        "advisory_text_executed": False,
    }


def scenario_profile_for(analysis: dict, path: str | Path | None = None) -> dict | None:
    """Return one defensive profile copy without copying the complete cache on hits."""
    global SCENARIO_PROFILE_CACHE_HITS
    target = Path(path or SCENARIO_PROFILES)
    try:
        cache_key = _scenario_profile_cache_key(target)
    except OSError:
        return None
    profile_key = _scenario_profile_key(analysis)
    with SCENARIO_PROFILE_CACHE_LOCK:
        cached = SCENARIO_PROFILE_CACHE.get(cache_key)
        if cached is not None:
            SCENARIO_PROFILE_CACHE_HITS += 1
            profile = cached.get("profiles", {}).get(profile_key)
            return copy.deepcopy(profile) if isinstance(profile, dict) else None
    loaded = load_scenario_profiles(target)
    profile = loaded.get("profiles", {}).get(profile_key)
    return copy.deepcopy(profile) if isinstance(profile, dict) else None


def _apply_scenario_profile(analysis: dict, path: str | Path | None = None) -> dict:
    result = dict(analysis)
    profile = scenario_profile_for(result, path)
    result["prepared_scenario_match"] = bool(profile)
    if not profile:
        return result
    # Profiles can accelerate diagnosis, but can never widen retry permission.
    result.update({
        "scenario_profile_id": profile["profile_id"],
        "prepared_scenario_count": profile["scenario_count"],
        "diagnostic_priority": profile["diagnostic_priority"],
        "first_checks": profile["first_checks"],
        "fast_resolution_steps": profile["fast_resolution_steps"],
        "stop_conditions": profile["stop_conditions"],
        "bounded_retry_allowed": bool(result.get("bounded_retry_allowed") and profile["bounded_retry_allowed"]),
    })
    return result


CLASSIFICATION_POLICY: dict[str, tuple[str, str, str]] = {
    "INTERNAL_SYNTAX_ERROR": ("내부 문법 오류", "자동 재시도 중단 · 코드 격리검사", "문법·들여쓰기 수정 후 전체 회귀검사를 실행하세요."),
    "PROCESS_TIMEOUT": ("프로세스 시간초과", "하위 프로세스 정리 · 해당 작업만 제한 재시도", "잔존 프로세스와 작업별 전체예산을 확인하세요."),
    "PROCESS_EXECUTION_ERROR": ("프로세스 실행 오류", "자동 재시도 중단 · 종료코드와 stderr 격리", "하위 수집기의 종료코드·신호·입력을 확인하세요."),
    "PROCESS_CANCELLED": ("프로세스 작업 취소", "추가 실행 중단 · 부분결과 폐기", "사용자 중단과 작업 취소 전파 경로를 확인하세요."),
    "RESOURCE_EXHAUSTION": ("시스템 자원 부족", "신규 저장 중단 · 기존 정상자료 유지", "메모리·디스크·프로세스·열린 파일 한도를 확보하세요."),
    "CONCURRENCY_CONFLICT": ("동시쓰기 충돌", "잠금 소유자 확인 · 제한 대기 후 1회 재시도", "동시 실행·버전·잠금 상태를 확인하세요."),
    "DATA_LIMIT_ERROR": ("자료 제한 초과", "초과 입력 격리 · 저장/학습 금지", "입력 크기·항목 수·중첩 깊이를 확인하세요."),
    "DATA_INTEGRITY_ERROR": ("자료 무결성 오류", "불완전 결과 격리 · 정상본 확인", "파일 크기·해시·캐시 세대와 원자저장 결과를 확인하세요."),
    "DATA_COMPRESSION_ERROR": ("압축자료 오류", "압축결과 격리 · 해제 제한 유지", "압축 형식·CRC·해제 비율과 원본 크기를 확인하세요."),
    "STORAGE_CORRUPTION_ERROR": ("저장소 손상 오류", "손상 저장소 격리 · 정상백업 우선", "SQLite·WAL·인덱스·페이지 체크섬과 정상백업을 확인하세요."),
    "DEPENDENCY_ERROR": ("실행환경 의존성 오류", "자동 설치 중단 · 호환 버전 확인", "Python·패키지·ABI·플랫폼 호환표를 확인하세요."),
    "INTERNAL_CODE_ERROR": ("내부 코드 오류", "자동 재시도 중단 · 기존 검증자료 유지 · 회귀검사 우선", "누락 import·이름·속성·계산 예외를 코드 검사에서 확인하세요."),
    "CAMERA_RUNTIME_ERROR": ("카메라·자동촬영 오류", "카메라 중지 · 파일촬영 대체경로 유지", "권한·보안 주소·프레임·앞뒷면 전환·파일 전달·스트림 해제를 확인하세요."),
    "VISION_MEASUREMENT_ERROR": ("사진 측정·결함 검출 오류", "등급 계산 중지 · 재촬영/수동 교차측정", "해상도·초점·노출·반사·원근·외곽/내부 보더·사선광 증거를 확인하세요."),
    "LINK_RUNTIME_ERROR": ("화면·링크 연결 오류", "자동 재시도 중단 · 연결 계약 검사", "버튼 ID·화면 대상·정적파일·API 경로·새 창 보안을 함께 확인하세요."),
    "SOURCE_ACCESS_CHALLENGE": ("원출처 자동접근 제한", "자동 우회 중단 · 기존 정상자료 유지", "공식 공개 대체 출처와 수동 확인 필요 여부를 검토하세요."),
    "SECURITY_POLICY_BLOCK": ("보안 정책 차단", "자동 재시도 중단 · 요청/출처 격리", "URL·DNS·Origin·Host·경로 정책 위반 여부를 확인하세요."),
    "NETWORK_TIMEOUT": ("통신 오류", "제한 재시도 후 기존 검증자료 유지", "공식 출처 응답시간과 학습된 제한시간을 확인하세요."),
    "NETWORK_HTTP_ERROR": ("통신 오류", "상태별 제한 재시도 · 영구 오류 중단", "HTTP 상태·Retry-After·공식 주소 변경 여부를 확인하세요."),
    "NETWORK_CONNECTION_ERROR": ("통신 오류", "제한 재시도 후 기존 검증자료 유지", "인터넷·DNS·공식 사이트 연결 상태를 확인하세요."),
    "NETWORK_TLS_ERROR": ("통신 보안 오류", "인증검증 유지 · 자동 우회 금지", "기기 시각·인증서 호스트·TLS 정책을 확인하세요."),
    "DATA_TIME_ERROR": ("날짜·시간 오류", "잘못된 시각 격리 · 임의 날짜 생성 금지", "ISO 날짜·시간대·시계 오차·시작/종료 순서를 확인하세요."),
    "FILE_MISSING": ("필수 파일 누락", "검증된 정상본 확인 · 임의 파일 생성 금지", "설치 파일과 검증된 정상 백업을 확인하세요."),
    "FILE_PERMISSION_ERROR": ("파일 권한 오류", "자동 권한변경 중단 · 기존자료 유지", "저장 폴더 권한·읽기 전용 상태·파일 잠금을 확인하세요."),
    "FILE_PATH_ERROR": ("파일 경로형식 오류", "잘못된 대상 격리 · 원본 유지", "파일·디렉터리 형식과 동일 파일시스템 원자교체 조건을 확인하세요."),
    "DATA_ENCODING_ERROR": ("문자 인코딩 오류", "손상 텍스트 격리 · 기존자료 유지", "응답 Content-Type·문자셋·UTF-8 디코딩을 확인하세요."),
    "SOURCE_CONTENT_TYPE_ERROR": ("원출처 콘텐츠 형식 오류", "비JSON 응답 격리 · 기존자료 유지", "응답 Content-Type과 실제 본문 형식을 확인하세요."),
    "CONFIGURATION_ERROR": ("환경설정 오류", "잘못된 설정 격리 · 안전 기본값만 허용", "필수 환경변수·포트·설정파일·허용 옵션을 확인하세요."),
    "DATA_SCHEMA_ERROR": ("데이터 구조 오류", "손상 결과 폐기 · 마지막 정상본 복원", "표준 JSON·최상위 형식·필수 항목을 확인하세요."),
    "SOURCE_STRUCTURE_CHANGED": ("원출처 구조변경", "기존 검증자료 유지 · 반복횟수 학습", "공식 페이지의 상품명·가격 표시 구조가 바뀌었는지 확인하세요."),
    "EXCHANGE_RATE_VALIDATION": ("환율 검증 오류", "비정상 환율 폐기 · 직전 정상환율 유지", "환율 공급처·통화 단위·허용범위를 확인하세요."),
    "DATA_VALUE_ERROR": ("입력값 오류", "비정상 값 격리 · 기존자료 유지", "자료형·유한수·불리언·허용범위를 확인하세요."),
    "RUNTIME_ERROR": ("실행 오류", "자동 재시도 중단 · 실패 함수 격리", "동일 입력 재현과 전체 회귀검사를 실행하세요."),
    "UNCLASSIFIED_ERROR": ("기타 수집 오류", "자동조치 확대 금지 · 신규 원인 기록", "오류 상세와 발생 범위를 비식별화해 확인하세요."),
}


def _classification_policy(code: str) -> tuple[str, str, str]:
    return CLASSIFICATION_POLICY.get(code, CLASSIFICATION_POLICY["UNCLASSIFIED_ERROR"])


def analyze_error(detail: Any, error_type: str | None = None, *, use_scenario_profile: bool = True) -> dict:
    """Return a deterministic root-cause code and a safe investigation plan.

    The plan is advisory data. It is never evaluated as code. Automatic actions
    remain restricted to the built-in retry and verified last-good restoration.
    """
    original_detail = str(detail if detail is not None else "")[:20_000]
    # Paths remain redacted, while an allowlisted project basename is retained
    # solely for stable diagnosis (never copied from arbitrary user paths).
    known_files = [name for name in SAFE_JSON_FILES if name.lower() in original_detail.lower()]
    filename_hint = f" known-file {' '.join(sorted(known_files))}" if known_files else ""
    raw = f"{error_type or ''}: {redact_sensitive(original_detail)}{filename_hint}".strip(": ")
    lowered = raw.lower()
    normalized = _clean_error_template(raw)
    matching_text = f"{lowered}\n{normalized}"
    # A known project file rejected by an older/stale allowlist is an internal
    # version-contract defect, not an unsafe user path and not a photo-content
    # failure.  Preserve that distinction for the screenshot-era v135 reports.
    if "허용되지 않은 파일" in lowered and (
        known_files or "등급카드 사진 후보" in lowered or "graded photo" in lowered
    ):
        matching_text += "\nknown safe project file rejected by stale allowlist"
    rules = (
        (("known safe project file rejected by stale allowlist",),
         "INTERNAL_CODE_ERROR", "내부 파일 허용목록 버전 불일치",
         "업데이트 실행기와 자동복구 모듈의 버전이 달라 정상 프로젝트 파일을 차단했을 가능성이 큽니다.",
         ("실행기와 자동복구 모듈의 배포 버전을 대조합니다.", "정상 프로젝트 파일 허용목록과 스키마를 함께 갱신합니다.", "수정 후 사진후보 사전검증과 전체 회귀검사를 실행합니다."), False),
        (("syntaxerror", "indentationerror", "taberror"),
         "INTERNAL_SYNTAX_ERROR", "Python 문법·들여쓰기 오류",
         "코드 편집 중 문법 또는 들여쓰기 구조가 잘못됐을 가능성이 큽니다.",
         ("오류 줄 전후의 괄호·따옴표·들여쓰기를 검사합니다.", "해당 파일을 py_compile로 격리 검사합니다.", "수정 후 전체 회귀검사를 실행합니다."), False),
        (("cancellederror", "keyboardinterrupt", "task cancelled", "collector cancelled by user", "작업 취소", "사용자 취소", "사용자 인터럽트"),
         "PROCESS_CANCELLED", "수집 작업 취소",
         "사용자 중단 또는 상위 작업 취소가 하위 수집기에 전달됐을 가능성이 큽니다.",
         ("취소 요청과 하위 프로세스 종료 상태를 확인합니다.", "부분 결과와 임시파일을 운영자료로 반영하지 않습니다.", "다음 정상 실행에서 전체 수집과 원본 보존을 확인합니다."), False),
        (("subprocesstimeoutexpired", "timeoutexpired", "worker process timeout", "작업 제한시간 초과"),
         "PROCESS_TIMEOUT", "수집 프로세스 제한시간 초과",
         "하위 수집 프로세스가 종료되지 않았거나 작업량에 비해 전체 실행예산이 부족할 가능성이 큽니다.",
         ("하위 프로세스 종료와 잔존 작업을 확인합니다.", "해당 작업만 제한된 1회 확대예산으로 재실행합니다.", "다른 정상자료와 마지막 정상본 보존을 검사합니다."), True),
        (("calledprocesserror", "non-zero exit status", "nonzero exit", "terminated by signal"),
         "PROCESS_EXECUTION_ERROR", "수집 프로세스 비정상 종료",
         "하위 수집기가 정상 종료코드가 아닌 값이나 종료 신호를 반환했습니다.",
         ("종료코드·신호와 비식별화한 stderr를 확인합니다.", "동일 결정적 종료는 자동 재시도하지 않습니다.", "수정 후 해당 수집기와 전체 회귀검사를 실행합니다."), False),
        (("memoryerror", "out of memory", "메모리 부족", "no space left", "enospc", "disk full", "디스크 공간", "winerror 112", "not enough space on the disk", "too many open files", "emfile",
          "can't start new thread", "cannot start new thread", "thread limit", "too many processes", "cannot fork", "resource temporarily unavailable", "eagain"),
         "RESOURCE_EXHAUSTION", "시스템 자원 부족",
         "메모리·디스크 공간·열린 파일 한도가 부족해 안전한 저장 또는 실행이 중단됐을 가능성이 큽니다.",
         ("메모리·디스크 여유와 열린 파일 수를 확인합니다.", "새 수집과 저장을 중단하고 기존 정상자료를 보존합니다.", "자원 확보 후 원자저장과 전체 검사를 다시 실행합니다."), False),
        (("database is locked", "database locked", "database busy", "lock timeout", "lock acquisition timeout", "잠금 대기", "다른 프로세스의 오류학습 저장", "concurrent write conflict",
          "version conflict", "stale version", "optimistic lock", "compare-and-swap conflict", "동시 수정 충돌", "winerror 32", "used by another process", "sharing violation",
          "fileexistserror", "lock already exists", "brokenbarriererror", "broken barrier"),
         "CONCURRENCY_CONFLICT", "동시쓰기·잠금 충돌",
         "서버·자동수집·검사기가 같은 기록을 동시에 저장해 잠금 대기 또는 버전 충돌이 발생했을 가능성이 큽니다.",
         ("현재 실행 중인 저장 작업과 잠금 소유자를 확인합니다.", "살아 있는 잠금을 훔치지 않고 짧은 제한 대기 후 한 번 재시도합니다.", "원본·백업·최종 JSON의 누락과 중복을 검사합니다."), True),
        (("too deeply nested", "중첩 깊이", "recursionerror", "too many nodes", "항목 수 제한", "노드 수", "payload too large", "size limit", "용량 제한", "크기 제한"),
         "DATA_LIMIT_ERROR", "자료 크기·복잡도 제한 초과",
         "입력 JSON·HTML·학습기록이 안전한 크기 또는 중첩 한도를 초과했을 가능성이 큽니다.",
         ("입력 바이트·항목 수·중첩 깊이를 확인합니다.", "초과 입력은 저장·학습하지 않고 격리합니다.", "정상 경계값과 초과값 회귀검사를 실행합니다."), False),
        (("database disk image is malformed", "file is not a database", "database header invalid", "database index corruption", "corrupt database index",
          "database page checksum", "sqlite wal checksum", "wal file corrupt", "write-ahead log corrupt", "recovery log corrupt", "데이터베이스 손상"),
         "STORAGE_CORRUPTION_ERROR", "저장소·데이터베이스 손상",
         "SQLite 본체·WAL·인덱스 또는 저장 페이지가 손상됐을 가능성이 큽니다.",
         ("현재 저장소와 WAL·인덱스 체크섬을 확인합니다.", "손상본을 격리하고 검증된 정상백업을 우선 확인합니다.", "복원 후 읽기·쓰기·전체 회귀검사를 실행합니다."), False),
        (("checksum mismatch", "sha256 mismatch", "hash mismatch", "해시 불일치", "unexpected eof", "truncated file", "불완전 저장",
          "stale cache", "cache generation mismatch", "cache poisoned"),
         "DATA_INTEGRITY_ERROR", "자료 무결성 오류",
         "다운로드·복사·원자저장 결과가 불완전하거나 검증 해시와 일치하지 않을 가능성이 큽니다.",
         ("현재 파일 크기와 검증 해시를 비교합니다.", "불완전 결과를 격리하고 검증된 마지막 정상본을 확인합니다.", "재수집 후 JSON 구조·해시·전체 회귀검사를 실행합니다."), False),
        (("badgzipfile", "badzipfile", "not a gzipped file", "not a zip file", "bad crc", "crc-32", "crc mismatch",
          "decompression bomb", "expansion ratio", "unsupported compression", "압축 손상", "압축폭탄"),
         "DATA_COMPRESSION_ERROR", "압축자료 형식·해제한도 오류",
         "압축 파일이 손상됐거나 안전한 해제 크기·비율을 초과했을 가능성이 큽니다.",
         ("압축 형식·CRC·원본/해제 크기를 확인합니다.", "손상 압축과 과도한 해제 결과를 격리합니다.", "검증된 정상백업과 경계값 회귀검사를 실행합니다."), False),
        (("dependencyconflict", "dependency conflict", "package version conflict", "incompatible with", "requires-python", "requires python",
          "unsupported python", "python 최소", "abi mismatch", "binary interface mismatch", "wrong architecture", "unsupportedwheel",
          "unsupported wheel", "wheel is not supported", "runtime dependency", "required dependency", "dependency unavailable", "openssl version incompatible"),
         "DEPENDENCY_ERROR", "실행환경·패키지 의존성 오류",
         "Python·패키지·바이너리 ABI 또는 운영체제용 배포물이 현재 환경과 맞지 않을 가능성이 큽니다.",
         ("현재 Python·패키지·플랫폼 버전을 확인합니다.", "실행 중 자동 설치하지 않고 검증된 호환 조합을 확인합니다.", "고정 환경에서 import와 전체 회귀검사를 실행합니다."), False),
        (("nameerror", "unboundlocalerror", "importerror", "modulenotfounderror", "attributeerror", "indexerror", "assertionerror",
          "zerodivisionerror", "notimplementederror"),
         "INTERNAL_CODE_ERROR", "내부 코드 이름·가져오기 오류",
         "필요한 모듈·함수·속성 이름이 코드 변경 과정에서 빠졌거나 달라졌을 가능성이 큽니다.",
         ("Python 문법과 import를 검사합니다.", "해당 함수를 격리 실행해 같은 예외가 재현되는지 확인합니다.", "수정 후 전체 회귀검사를 실행합니다."), False),
        (("camerapermissiondenied", "camerasecurecontexterror", "getusermedia unavailable", "cameranotfound",
          "camerastreamconflict", "cameraframeunavailable", "cameraframereaderror", "cameraencodeerror",
          "cameracanvaserror", "duplicatesidecapture", "camerafilehandofferror", "datatransferunavailable",
          "camerarequestrace", "cameraresourceleak", "카메라 권한 거부", "보안 컨텍스트", "카메라 없음",
          "카메라 사용 중", "영상 프레임", "촬영 인코딩", "앞뒷면 중복 촬영", "촬영 파일 전달", "카메라 수명주기"),
         "CAMERA_RUNTIME_ERROR", "카메라·자동촬영 런타임 오류",
         "카메라 권한·보안 컨텍스트·영상 프레임·앞뒷면 전환 또는 촬영 파일 전달이 실패했을 가능성이 큽니다.",
         ("카메라 권한과 HTTPS/127.0.0.1 보안 컨텍스트를 확인합니다.", "같은 면 중복촬영과 파일 전달·스트림 해제 상태를 확인합니다.", "카메라 전용 브라우저 검사와 전체 회귀검사를 실행합니다."), False),
        (("visionimagesizeerror", "visionimagedataerror", "visionqualitygate", "visionblurerror",
          "visionexposureerror", "visionglareerror", "visioncenteringgate",
          "visionborderdetectionerror", "visionborderless", "visionperspectiveerror", "visionscratchconfidenceerror",
          "visionobliquemissing", "visionenginemissing", "visioncanvaserror", "visionbrowsercanvasunavailable",
          "촬영 품질 게이트", "사진 픽셀 형식", "내부 보더 검출", "원근 왜곡", "과도한 기울기", "사선광 증거 부족", "비전 엔진 로드"),
         "VISION_MEASUREMENT_ERROR", "사진 센터링·표면 결함 측정 오류",
         "촬영 품질·카드 외곽·내부 보더·원근 또는 다각도 표면 증거가 안전한 자동 판정 조건을 충족하지 못했습니다.",
         ("해상도·초점·노출·반사·조명 균일도를 먼저 확인합니다.", "외곽과 내부 보더 반복 검출 및 원근 오차를 확인합니다.", "사선광 사진을 추가하고 비전 전용 회귀검사를 실행합니다."), False),
        (("linkcontracterror", "brokenanchorerror", "missingbuttonbinding", "staticasset404", "apiroutemismatch",
          "serviceworkerassetmismatch", "manifesttargetmissing", "unsafeblankopener", "popupblockedlink",
          "externalurltemplateerror", "링크 계약 오류", "버튼 연결 누락", "화면 이동 대상 누락", "api 경로 불일치"),
         "LINK_RUNTIME_ERROR", "화면·링크 런타임 연결 오류",
         "버튼·화면 대상·정적자원·서비스워커 또는 서버 API 사이의 연결 계약이 어긋났을 가능성이 큽니다.",
         ("버튼 ID와 화면 이동 대상을 대조합니다.", "정적파일·서비스워커·API 경로와 HTTP 메서드를 확인합니다.", "수정 후 링크 전용 검사와 전체 브라우저·서버 회귀검사를 실행합니다."), False),
        (("captcha", "cloudflare challenge", "bot challenge", "자동접근 확인"),
         "SOURCE_ACCESS_CHALLENGE", "원출처 자동접근 제한",
         "원출처가 CAPTCHA 또는 봇 확인 화면을 반환해 자동수집 결과로 사용할 수 없습니다.",
         ("응답 상태·Content-Type·공식 공개 대체 출처를 확인합니다.", "CAPTCHA 우회나 브라우저 자동조작을 실행하지 않습니다.", "기존 정상자료를 유지하고 수동 확인 필요 상태를 표시합니다."), False),
        (("ssrf", "private dns", "private ip", "dns rebinding", "security", "blocked", "차단", "허용되지 않은 요청 출처", "cors", "csrf",
          "symlink", "심볼릭 링크", "path traversal", "경로탈출", "경로 이탈", "https only", "unsafe scheme", "non-https",
          "credentials in url", "url credentials", "userinfo", "host header", "위조 host", "method policy", "blocked method",
          "허용되지 않은 method", "xss", "script injection", "스크립트 주입"),
         "SECURITY_POLICY_BLOCK", "보안 정책 차단",
         "허용되지 않은 주소·DNS·Origin 또는 보안 정책 위반 요청일 가능성이 큽니다.",
         ("요청 주소와 출처를 허용목록과 비교합니다.", "차단된 요청이 외부 수집을 실행하지 않았는지 확인합니다.", "정상 로컬·공식 요청의 회귀검사를 실행합니다."), False),
        (("invalid isoformat", "invalid date", "date parse error", "datetime parse", "timezoneerror", "timezone-aware", "invalid timezone",
          "utc offset", "clock skew", "system clock", "end date precedes start", "end date before start", "start date after end",
          "date range", "날짜 형식", "잘못된 날짜", "시간대 오류", "종료일이 시작일", "날짜 범위"),
         "DATA_TIME_ERROR", "날짜·시간·시간대 오류",
         "날짜 형식, 시간대, 시스템 시각 또는 시작·종료 순서가 유효하지 않을 가능성이 큽니다.",
         ("ISO 날짜·시간대·기기 시각을 확인합니다.", "임의 날짜로 보정하지 않고 잘못된 항목만 격리합니다.", "윤년·경계·시간대 변형 회귀검사를 실행합니다."), False),
        (("timeouterror", "timed out", "timeout", "시간초과"),
         "NETWORK_TIMEOUT", "네트워크 시간초과",
         "공식 사이트 응답 지연, 연결 불안정 또는 학습된 제한시간 부족 가능성이 큽니다.",
         ("공식 출처 연결과 응답시간을 확인합니다.", "제한된 1회 재시도와 확대된 시간예산을 적용합니다.", "실패 시 기존 정상자료가 유지됐는지 확인합니다."), True),
        (("httperror", "http error", "http <n>", "status code", "rate limit", "too many requests", "요청 제한", "redirect loop", "too many redirects"),
         "NETWORK_HTTP_ERROR", "HTTP 응답 오류",
         "원출처가 오류·차단 응답을 반환했거나 접근 정책이 바뀌었을 가능성이 큽니다.",
         ("HTTP 상태와 공식 주소 변경 여부를 확인합니다.", "인증정보 없이 제한된 재시도를 실행합니다.", "기존 정상자료 보존과 다음 실행 결과를 비교합니다."), True),
        (("sslerror", "ssl", "tls", "certificate", "인증서"),
         "NETWORK_TLS_ERROR", "HTTPS 인증·암호화 오류",
         "인증서, 기기 시각 또는 TLS 연결 문제일 가능성이 큽니다.",
         ("기기 시각과 인증서 오류를 확인합니다.", "HTTPS와 공개 주소 검증을 다시 수행합니다.", "검증 실패 응답이 저장되지 않았는지 확인합니다."), False),
        (("urlerror", "connectionerror", "connection refused", "connectionreseterror", "connection reset", "connectionabortederror", "connection abort",
          "brokenpipeerror", "broken pipe", "host unreachable", "network unreachable", "gaierror", "name resolution", "temporary failure",
          "temporarily unavailable", "dns", "연결 실패", "일시 확인불가", "winerror 10054", "winerror 10061", "winerror 11001", "getaddrinfo failed"),
         "NETWORK_CONNECTION_ERROR", "네트워크 연결·DNS 오류",
         "인터넷, DNS 또는 원출처 연결이 일시적으로 실패했을 가능성이 큽니다.",
         ("인터넷과 DNS 상태를 확인합니다.", "공식 HTTPS 주소만 제한적으로 재시도합니다.", "복구되지 않으면 기존 검증자료를 유지합니다."), True),
        (("filenotfounderror", "파일 없음", "no such file", "enoent", "winerror 2", "winerror 3", "cannot find the file", "cannot find the path"),
         "FILE_MISSING", "필수 파일 누락",
         "필수 프로젝트 파일이 이동·삭제됐거나 설치가 불완전할 가능성이 큽니다.",
         ("허용된 프로젝트 파일인지 확인합니다.", "검증된 정상 백업의 구조를 검사합니다.", "복원 후 실행파일과 JSON 전체 검사를 실행합니다."), False),
        (("permissionerror", "permission denied", "권한", "read-only file system", "readonly filesystem", "eacces", "winerror 5", "access is denied"),
         "FILE_PERMISSION_ERROR", "파일 권한 오류",
         "저장 폴더 권한 또는 다른 프로그램의 파일 잠금 문제일 가능성이 큽니다.",
         ("프로그램 폴더 쓰기 권한과 파일 잠금을 확인합니다.", "임의 권한 변경 없이 안전한 폴더에서 재시도합니다.", "임시파일 잔존과 원본 보존 여부를 검사합니다."), False),
        (("isadirectoryerror", "notadirectoryerror", "is a directory", "not a directory", "cross-device", "exdev", "winerror 206", "path too long", "filename too long"),
         "FILE_PATH_ERROR", "파일·디렉터리 경로형식 오류",
         "파일이 필요한 위치에 디렉터리가 있거나 원자교체가 불가능한 경로일 가능성이 큽니다.",
         ("대상의 실제 파일형식과 상위 경로를 확인합니다.", "경로를 자동 삭제하거나 바꾸지 않습니다.", "정상 경로에서 원자저장과 전체 검사를 실행합니다."), False),
        (("configurationerror", "configerror", "invalid configuration", "malformed configuration", "malformed config", "configuration file",
          "config file", "required environment variable", "required env var", "environment variable missing", "env var not set",
          "unknown configuration option", "unknown config option", "unsupported option", "설정 오류", "설정 파일", "환경변수 누락", "잘못된 포트"),
         "CONFIGURATION_ERROR", "환경·실행 설정 오류",
         "필수 환경변수·포트·설정파일 또는 허용 옵션이 유효하지 않을 가능성이 큽니다.",
         ("필수 설정 존재·자료형·범위를 확인합니다.", "비밀값을 기록하지 않고 잘못된 설정만 격리합니다.", "정상·누락·경계 설정으로 전체 회귀검사를 실행합니다."), False),
        (("unicodedecodeerror", "unicodeencodeerror", "invalid utf-8", "utf-8 bom", "byte order mark", "charset mismatch", "cannot decode", "cannot encode", "문자 인코딩"),
         "DATA_ENCODING_ERROR", "문자 인코딩 오류",
         "원출처 문자셋 또는 저장 텍스트가 예상한 UTF-8과 일치하지 않을 가능성이 큽니다.",
         ("응답 Content-Type과 원본 바이트를 확인합니다.", "대체 문자로 조용히 손상시키지 않고 결과를 격리합니다.", "정상·잘못된 인코딩 회귀검사를 실행합니다."), False),
        (("content-type", "content type", "unsupported media type", "application/json expected", "expected application/json", "콘텐츠 타입", "콘텐츠 형식"),
         "SOURCE_CONTENT_TYPE_ERROR", "원출처 콘텐츠 형식 불일치",
         "JSON을 기대한 수집기가 HTML 또는 지원하지 않는 미디어 형식을 받았을 가능성이 큽니다.",
         ("응답 Content-Type과 실제 본문 첫 부분을 확인합니다.", "로그인·차단 HTML을 JSON으로 저장하지 않습니다.", "공식 JSON 응답과 오류 HTML 회귀검사를 실행합니다."), False),
        (("jsondecodeerror", "keyerror", "json decode", "json", "구조 오류", "필수값", "필수 자료", "누락", "top-level list", "top-level array", "root must be object", "최상위 배열"),
         "DATA_SCHEMA_ERROR", "JSON·자료 구조 오류",
         "수집 결과가 표준 JSON 또는 파일별 필수 구조와 맞지 않을 가능성이 큽니다.",
         ("표준 JSON과 필수 필드를 검사합니다.", "손상 결과를 폐기하고 검증된 정상 백업만 확인합니다.", "복원 후 전체 데이터 회귀검사를 실행합니다."), False),
        (("parser", "parse", "패턴 <n>건", "확인 실패", "읽지 못"),
         "SOURCE_STRUCTURE_CHANGED", "원출처 표시 구조 변경",
         "공식 페이지의 상품명·가격·날짜 표시 방식이 달라졌을 가능성이 큽니다.",
         ("원출처의 현재 표시 구조를 확인합니다.", "기존 파서와 후보 패턴을 비교합니다.", "검증된 필드가 없으면 기존 정상자료를 유지합니다."), False),
        (("환율", "exchange rate", "exchange_rate", "currency rate"),
         "EXCHANGE_RATE_VALIDATION", "환율 범위·단위 오류",
         "환율 공급처 단위가 바뀌었거나 비정상 범위의 값이 들어왔을 가능성이 큽니다.",
         ("통화 기준과 환율 범위를 확인합니다.", "두 통화 값이 모두 유한수인지 검사합니다.", "비정상 값은 폐기하고 직전 정상환율을 유지합니다."), False),
        (("valueerror", "typeerror", "overflowerror", "decimal.invalidoperation", "invalid decimal", "floatingpointerror"),
         "DATA_VALUE_ERROR", "입력값·자료형 오류",
         "수집값의 자료형, 범위 또는 필수값이 처리 규칙과 맞지 않을 가능성이 큽니다.",
         ("오류가 난 입력값의 자료형과 범위를 확인합니다.", "비정상 값만 격리하고 기존 정상자료를 유지합니다.", "정상·경계·잘못된 입력으로 회귀검사를 실행합니다."), False),
        (("runtimeerror",), "RUNTIME_ERROR", "실행 중 기능 오류",
         "수집 함수가 안전조건을 충족하지 못해 실행을 중단했을 가능성이 큽니다.",
         ("오류가 난 함수와 입력자료를 격리합니다.", "동일 입력으로 한 번 재현해 원인을 좁힙니다.", "수정 뒤 해당 기능과 전체 회귀검사를 실행합니다."), False),
    )
    code = "UNCLASSIFIED_ERROR"
    title = "분류되지 않은 신규 오류"
    cause = "기존 규칙에 없는 오류입니다. 상세정보를 비식별화해 기록하고 재현 범위를 확인해야 합니다."
    steps = ("발생 함수·파일·입력 범위를 확인합니다.", "동일 조건에서 안전하게 재현되는지 검사합니다.", "원인을 확인한 뒤 전용 회귀검사를 추가합니다.")
    retry_allowed = False
    detected_http_status = _http_status_from_error(lowered)
    content_type_signal = any(value in matching_text for value in (
        "content-type", "content type", "unsupported media type", "application/json expected",
        "expected application/json", "콘텐츠 타입", "콘텐츠 형식",
    ))
    dependency_signal = any(value in matching_text for value in (
        "dependencyconflict", "dependency conflict", "package version conflict", "incompatible with",
        "requires-python", "requires python", "unsupported python", "python 최소", "abi mismatch",
        "unsupported wheel", "runtime dependency", "required dependency", "openssl version incompatible",
    ))
    for needles, candidate, candidate_title, candidate_cause, candidate_steps, candidate_retry in rules:
        if candidate == "NETWORK_HTTP_ERROR" and content_type_signal:
            continue
        if candidate == "CONCURRENCY_CONFLICT" and dependency_signal:
            continue
        if detected_http_status is not None and candidate in {"NETWORK_TIMEOUT", "DATA_LIMIT_ERROR"}:
            continue
        matched = candidate == "NETWORK_HTTP_ERROR" and detected_http_status is not None and not content_type_signal
        if matched or any(_diagnostic_needle_matches(needle, matching_text) for needle in needles):
            code, title, cause, steps, retry_allowed = candidate, candidate_title, candidate_cause, candidate_steps, candidate_retry
            break
    subtype, http_status = _root_cause_subtype(code, lowered, normalized)
    template = normalized if code == "UNCLASSIFIED_ERROR" else (
        code if subtype == "general" else f"{code}:{subtype}"
    )
    if code == "NETWORK_HTTP_ERROR":
        retry_allowed = http_status in {408, 425, 429, 500, 502, 503, 504} or subtype == "rate-limit-no-status"
        if http_status in {401, 403}:
            title = "HTTP 접근 권한 오류"
            cause = "원출처가 인증 또는 접근 권한 부족 응답을 반환했습니다. 같은 요청을 반복해도 해결되지 않습니다."
            steps = ("공식 주소와 공개 접근 가능 여부를 확인합니다.", "인증정보를 자동 생성하거나 우회하지 않습니다.", "접근 가능한 공식 대체 출처와 기존 정상자료를 검증합니다.")
        elif http_status in {404, 410}:
            title = "HTTP 주소 소멸·변경 오류"
            cause = "원출처 주소가 이동·삭제되어 영구 실패 응답을 반환했을 가능성이 큽니다."
            steps = ("공식 사이트에서 현재 주소를 확인합니다.", "같은 주소의 자동 재시도를 중단합니다.", "새 주소 검증 전까지 기존 정상자료를 유지합니다.")
        elif retry_allowed:
            title = "HTTP 일시 응답 오류"
            cause = "원출처의 요청 제한 또는 일시적인 서버 장애일 가능성이 큽니다."
            steps = ("HTTP 상태와 Retry-After 정책을 확인합니다.", "제한된 재시도와 대기 시간을 적용합니다.", "복구되지 않으면 기존 정상자료를 유지합니다.")
    category, safe_action, recommendation = _classification_policy(code)
    result = {
        "code": code, "title": title, "category": category,
        "canonical_template": template, "error_subtype": subtype,
        "http_status": http_status, "probable_cause": cause,
        "safe_action": safe_action, "recommended_action": recommendation,
        "resolution_steps": list(steps),
        "verification_steps": [steps[-1], "기존 정상자료가 손상되지 않았는지 확인합니다."],
        "bounded_retry_allowed": retry_allowed,
        "automation_policy": "내장된 안전 규칙만 허용 · 기록된 문자열/코드는 실행 금지",
    }
    return _apply_scenario_profile(result) if use_scenario_profile else result


def error_group_key(analysis: dict) -> str:
    raw = f"{analysis.get('category','')}|{analysis.get('canonical_template','UNCLASSIFIED_ERROR')}"
    return hashlib.sha256(raw.encode("utf-8", "ignore")).hexdigest()[:16]


def _safe_file_label(value: Any) -> str:
    text = re.sub(r"[\x00-\x1f\x7f]+", "", redact_sensitive(value or "unknown", 160)).replace("\\", "/")
    name = Path(text).name
    return name if name and name not in (".", "..") else "unknown"


def _update_group_status(group: dict) -> None:
    """Derive the group status from each affected file's latest state."""
    states = group.get("file_states") if isinstance(group.get("file_states"), dict) else {}
    unresolved = []
    for name, state in states.items():
        if not isinstance(state, dict):
            continue
        occurrences = _safe_int(state.get("occurrences"), 0)
        resolved_count = min(occurrences, _safe_int(state.get("resolved_count"), 0))
        if occurrences <= 0 or state.get("last_outcome") != "resolved" or resolved_count < occurrences:
            unresolved.append(_safe_file_label(name))
    group["unresolved_files"] = list(dict.fromkeys(unresolved))[-MAX_GROUP_FILES:]
    group["unresolved_count"] = max(
        0, _safe_int(group.get("occurrences"), 0) - _safe_int(group.get("resolved_count"), 0)
    )
    if states:
        group["last_outcome"] = "resolved" if not group["unresolved_files"] else "unresolved"
    if group.get("last_outcome") == "resolved":
        group["analysis_status"] = "해결 확인"
    else:
        group["analysis_status"] = (
            "신규 분석" if _safe_int(group.get("occurrences"), 0) <= 1 else "반복 발생"
        )


def _record_error_group(memory: dict, *, filename: Any, detail: Any, timestamp: str,
                        resolved: bool, action: Any, error_type: str | None = None,
                        origin: str = "pipeline", count: int = 1,
                        resolved_count: int | None = None, migrated: bool = False) -> tuple[str, bool]:
    analysis = analyze_error(detail, error_type)
    key = error_group_key(analysis)
    groups = memory.setdefault("error_groups", {})
    is_new = key not in groups
    group = groups.setdefault(key, {
        "group_id": key, "code": analysis["code"], "title": analysis["title"],
        "category": analysis["category"], "error_subtype": analysis["error_subtype"],
        "http_status": analysis["http_status"],
        "http_statuses": [analysis["http_status"]] if analysis["http_status"] is not None else [],
        "occurrences": 0, "resolved_count": 0,
        "first_seen": timestamp, "last_seen": timestamp, "last_outcome": "unresolved",
        "affected_files": [], "file_counts": {}, "file_states": {}, "sample_details": [],
        "probable_cause": analysis["probable_cause"], "safe_action": analysis["safe_action"],
        "recommended_action": analysis["recommended_action"],
        "resolution_steps": analysis["resolution_steps"],
        "verification_steps": analysis["verification_steps"],
        "bounded_retry_allowed": analysis["bounded_retry_allowed"],
        "scenario_prepared": analysis.get("prepared_scenario_match") is True,
        "scenario_profile_id": analysis.get("scenario_profile_id"),
        "prepared_scenario_count": _safe_int(analysis.get("prepared_scenario_count"), 0, 0, 1000),
        "diagnostic_priority": _safe_int(analysis.get("diagnostic_priority"), 50, 1, 100),
        "first_checks": analysis.get("first_checks", []),
        "fast_resolution_steps": analysis.get("fast_resolution_steps", []),
        "stop_conditions": analysis.get("stop_conditions", []),
        "automation_policy": analysis["automation_policy"],
        "successful_actions": {}, "resolution_history": [],
    })
    group.setdefault("error_subtype", analysis["error_subtype"])
    group.setdefault("http_status", analysis["http_status"])
    group.setdefault("bounded_retry_allowed", analysis["bounded_retry_allowed"])
    if analysis.get("prepared_scenario_match") is True:
        group["scenario_prepared"] = True
        group["scenario_profile_id"] = analysis.get("scenario_profile_id")
        group["prepared_scenario_count"] = _safe_int(analysis.get("prepared_scenario_count"), 0, 0, 1000)
        group["diagnostic_priority"] = _safe_int(analysis.get("diagnostic_priority"), 50, 1, 100)
        group["first_checks"] = list(analysis.get("first_checks", []))[:5]
        group["fast_resolution_steps"] = list(analysis.get("fast_resolution_steps", []))[:6]
        group["stop_conditions"] = list(analysis.get("stop_conditions", []))[:5]
    statuses = []
    for value in group.get("http_statuses", []) if isinstance(group.get("http_statuses"), list) else []:
        parsed = _safe_int(value, 0, 0, 599)
        if 100 <= parsed <= 599 and parsed not in statuses:
            statuses.append(parsed)
    if analysis["http_status"] is not None:
        if analysis["http_status"] not in statuses:
            statuses.append(analysis["http_status"])
        group["http_status"] = analysis["http_status"]
    group["http_statuses"] = statuses[-20:]
    increment = max(1, _safe_int(count, 1, 1, 1_000_000))
    fixed = int(resolved) if resolved_count is None else _safe_int(resolved_count, 0, 0, increment)
    group["occurrences"] = min(1_000_000, _safe_int(group.get("occurrences"), 0) + increment)
    group["resolved_count"] = min(group["occurrences"], _safe_int(group.get("resolved_count"), 0) + fixed)
    group["last_seen"] = max(str(group.get("last_seen") or ""), str(timestamp or "")) or timestamp
    group["first_seen"] = min(x for x in (str(group.get("first_seen") or ""), str(timestamp or "")) if x)
    file_label = _safe_file_label(filename)
    files = [x for x in group.get("affected_files", []) if isinstance(x, str)]
    if file_label not in files:
        files.append(file_label)
    group["affected_files"] = files[-MAX_GROUP_FILES:]
    counts = group.get("file_counts") if isinstance(group.get("file_counts"), dict) else {}
    counts[file_label] = min(1_000_000, _safe_int(counts.get(file_label), 0) + increment)
    group["file_counts"] = dict(list(counts.items())[-MAX_GROUP_FILES:])
    states = group.get("file_states") if isinstance(group.get("file_states"), dict) else {}
    state = states.get(file_label) if isinstance(states.get(file_label), dict) else {}
    state_occurrences = min(1_000_000, _safe_int(state.get("occurrences"), 0) + increment)
    state_resolved = min(
        state_occurrences, _safe_int(state.get("resolved_count"), 0) + fixed
    )
    state.update({
        "occurrences": state_occurrences,
        "resolved_count": state_resolved,
        "last_seen": max(str(state.get("last_seen") or ""), str(timestamp or "")) or timestamp,
        "last_outcome": "resolved" if resolved and state_resolved >= state_occurrences else "unresolved",
        "resolution_confirmed": bool(resolved and state_resolved >= state_occurrences),
    })
    if state["last_outcome"] == "unresolved":
        state["clean_observations_after_error"] = 0
    else:
        state["clean_observations_after_error"] = max(
            2, _safe_int(state.get("clean_observations_after_error"), 0)
        )
    states[file_label] = state
    group["file_states"] = dict(list(states.items())[-MAX_GROUP_FILES:])
    sample = redact_sensitive(detail, 500)
    samples = [x for x in group.get("sample_details", []) if isinstance(x, str) and x != sample]
    if sample:
        samples.append(sample)
    group["sample_details"] = samples[-MAX_GROUP_SAMPLES:]
    group["last_detail"] = sample
    _update_group_status(group)
    safe_recorded_action = redact_sensitive(action or analysis["safe_action"], 400)
    history = group.get("resolution_history") if isinstance(group.get("resolution_history"), list) else []
    if not migrated:
        history.append({"timestamp": timestamp, "file": file_label, "origin": origin,
                        "action": safe_recorded_action, "resolved": bool(resolved)})
    group["resolution_history"] = history[-MAX_RESOLUTION_HISTORY:]
    if fixed:
        successes = group.get("successful_actions") if isinstance(group.get("successful_actions"), dict) else {}
        successes[safe_recorded_action] = min(1_000_000, _safe_int(successes.get(safe_recorded_action), 0) + fixed)
        group["successful_actions"] = successes
        group["proven_action"] = max(successes, key=successes.get)
    if is_new and not migrated:
        log = memory.setdefault("new_error_log", [])
        log.append({
            "group_id": key, "first_seen": timestamp, "code": analysis["code"],
            "title": analysis["title"], "category": analysis["category"],
            "error_subtype": analysis["error_subtype"], "http_status": analysis["http_status"],
            "bounded_retry_allowed": analysis["bounded_retry_allowed"],
            "scenario_prepared": analysis.get("prepared_scenario_match") is True,
            "scenario_profile_id": analysis.get("scenario_profile_id"),
            "diagnostic_priority": analysis.get("diagnostic_priority"),
            "file": file_label, "detail": sample, "probable_cause": analysis["probable_cause"],
            "safe_action": analysis["safe_action"], "resolution_steps": analysis["resolution_steps"],
            "verification_steps": analysis["verification_steps"],
            "analysis_status": group.get("analysis_status", "신규 분석"),
        })
        del log[:-MAX_NEW_ERROR_LOG]
    return key, is_new


def _refresh_learning_summary(memory: dict) -> None:
    groups = memory.get("error_groups") if isinstance(memory.get("error_groups"), dict) else {}
    memory["learning_summary"] = {
        "error_group_count": len(groups),
        "new_group_count": sum(row.get("analysis_status") == "신규 분석" for row in groups.values()),
        "recurring_group_count": sum(_safe_int(row.get("occurrences"), 0) > 1 for row in groups.values()),
        "unresolved_group_count": sum(row.get("last_outcome") != "resolved" for row in groups.values()),
        "resolved_group_count": sum(row.get("last_outcome") == "resolved" for row in groups.values()),
        "verified_solution_group_count": sum(bool(row.get("proven_action")) for row in groups.values()),
        "scenario_prepared_group_count": sum(row.get("scenario_prepared") is True for row in groups.values()),
        "consolidated_event_total": sum(_safe_int(row.get("occurrences"), 0) for row in groups.values()),
    }


def _sync_new_error_log(memory: dict) -> None:
    """Keep each one-time discovery record aligned with the group's current result."""
    groups = memory.get("error_groups") if isinstance(memory.get("error_groups"), dict) else {}
    log = memory.get("new_error_log") if isinstance(memory.get("new_error_log"), list) else []
    for item in log:
        if not isinstance(item, dict):
            continue
        group = groups.get(item.get("group_id"))
        if not isinstance(group, dict):
            item["analysis_status"] = "기록 보존"
            continue
        item.update({
            "analysis_status": group.get("analysis_status", "신규 분석"),
            "last_outcome": group.get("last_outcome", "unresolved"),
            "last_seen": group.get("last_seen"),
            "occurrences": _safe_int(group.get("occurrences"), 0),
            "unresolved_count": _safe_int(group.get("unresolved_count"), 0),
            "error_subtype": group.get("error_subtype", "general"),
            "http_status": group.get("http_status"),
            "http_statuses": list(group.get("http_statuses", []))
                if isinstance(group.get("http_statuses"), list) else [],
            "bounded_retry_allowed": group.get("bounded_retry_allowed") is True,
        })
        if group.get("proven_action"):
            item["proven_action"] = redact_sensitive(group["proven_action"], 400)


def _observe_clean_file(memory: dict, filename: str, timestamp: str) -> None:
    """Confirm a previous error as resolved only after two clean file runs."""
    label = _safe_file_label(filename)
    groups = memory.get("error_groups") if isinstance(memory.get("error_groups"), dict) else {}
    for group in groups.values():
        if not isinstance(group, dict) or label not in group.get("affected_files", []):
            continue
        states = group.get("file_states") if isinstance(group.get("file_states"), dict) else {}
        state = states.get(label)
        if not isinstance(state, dict):
            continue
        clean_count = min(
            1_000_000, _safe_int(state.get("clean_observations_after_error"), 0) + 1
        )
        state["clean_observations_after_error"] = clean_count
        state["last_clean_seen"] = max(str(state.get("last_clean_seen") or ""), str(timestamp or "")) or timestamp
        states[label] = state
        group["file_states"] = states
        if clean_count < 2 or state.get("last_outcome") == "resolved":
            _update_group_status(group)
            continue
        occurrences = _safe_int(state.get("occurrences"), 0)
        previous_resolved = min(occurrences, _safe_int(state.get("resolved_count"), 0))
        newly_resolved = max(0, occurrences - previous_resolved)
        state["resolved_count"] = occurrences
        state["last_outcome"] = "resolved"
        state["resolution_confirmed"] = True
        group["resolved_count"] = min(
            _safe_int(group.get("occurrences"), 0),
            _safe_int(group.get("resolved_count"), 0) + newly_resolved,
        )
        _update_group_status(group)
        history = group.get("resolution_history") if isinstance(group.get("resolution_history"), list) else []
        history.append({"timestamp": timestamp, "file": label, "origin": "clean-observation",
                        "action": "동일 파일 2회 연속 정상 실행으로 해결 확인", "resolved": True})
        group["resolution_history"] = history[-MAX_RESOLUTION_HISTORY:]
        action = "동일 파일 2회 연속 정상 실행으로 해결 확인"
        successes = group.get("successful_actions") if isinstance(group.get("successful_actions"), dict) else {}
        successes[action] = min(1_000_000, _safe_int(successes.get(action), 0) + 1)
        group["successful_actions"] = successes
        group["proven_action"] = max(successes, key=successes.get)


def _migrate_legacy_patterns(memory: dict) -> None:
    if memory.get("error_groups"):
        return
    patterns = memory.get("patterns") if isinstance(memory.get("patterns"), dict) else {}
    for row in patterns.values():
        if not isinstance(row, dict) or not row.get("last_detail"):
            continue
        occurrences = max(1, _safe_int(row.get("occurrences"), 1))
        successful = min(occurrences, _safe_int(row.get("successful_repairs"), 0))
        _record_error_group(
            memory, filename=row.get("file"), detail=row.get("last_detail"),
            timestamp=str(row.get("last_seen") or memory.get("updated_at") or "legacy"),
            resolved=bool(successful and successful >= occurrences), action=row.get("auto_action"),
            count=occurrences, resolved_count=successful, migrated=True,
        )


def public_error_learning_summary(memory: dict) -> dict:
    """Return the compact, traceback-free error-learning view used by the UI."""
    clean = _sanitize_memory(copy.deepcopy(memory) if isinstance(memory, dict) else _default_memory())
    groups = sorted(clean.get("error_groups", {}).values(),
                    key=lambda row: (_safe_int(row.get("occurrences"), 0), str(row.get("last_seen") or "")),
                    reverse=True)
    fields = ("group_id", "code", "title", "category", "error_subtype", "http_status", "http_statuses",
              "bounded_retry_allowed", "occurrences", "resolved_count",
              "unresolved_count", "first_seen", "last_seen", "last_outcome", "analysis_status",
              "affected_files", "unresolved_files", "probable_cause", "safe_action", "recommended_action",
              "resolution_steps", "verification_steps", "proven_action", "last_detail",
              "scenario_prepared", "scenario_profile_id", "prepared_scenario_count",
              "diagnostic_priority", "first_checks", "fast_resolution_steps", "stop_conditions")
    return {
        "version": clean.get("version", 4), "updated_at": clean.get("updated_at"),
        "total_runs": clean.get("total_runs", 0), "summary": clean.get("learning_summary", {}),
        "groups": [{key: row.get(key) for key in fields if key in row} for row in groups],
        "new_errors": clean.get("new_error_log", [])[-20:],
        "scenario_learning": scenario_learning_summary(),
        "safety": "해결방법은 분석·검증 계획으로만 저장되며 문자열이나 생성 코드를 자동 실행하지 않습니다.",
    }

def _sanitize_memory(base: dict) -> dict:
    """v73: repair nested counters in persisted learning memory.

    Older/corrupted JSON could keep the outer dict valid while storing counters as
    strings/NaN-like values. Those values used to crash the *next* learning write.
    """
    base["total_runs"] = _safe_int(base.get("total_runs"), 0)
    base["invalid_report_count"] = _safe_int(base.get("invalid_report_count"), 0)
    if base.get("updated_at") is not None:
        base["updated_at"] = _canonical_report_timestamp(base.get("updated_at"))
    patterns = base.get("patterns") if isinstance(base.get("patterns"), dict) else {}
    clean_patterns = {}
    for key, row in list(patterns.items())[-MAX_ERROR_PATTERNS:]:
        if not isinstance(key, str) or not isinstance(row, dict):
            continue
        item = dict(row)
        item["occurrences"] = _safe_int(item.get("occurrences"), 0)
        item["successful_repairs"] = _safe_int(item.get("successful_repairs"), 0)
        if "last_detail" in item:
            item["last_detail"] = redact_sensitive(item["last_detail"])
        clean_patterns[key] = item
    base["patterns"] = clean_patterns
    _migrate_legacy_patterns(base)
    raw_groups = base.get("error_groups") if isinstance(base.get("error_groups"), dict) else {}
    clean_groups = {}
    group_id_aliases = {}
    ordered_groups = sorted(raw_groups.items(), key=lambda pair: str(pair[1].get("last_seen") or "")
                            if isinstance(pair[1], dict) else "")[-MAX_ERROR_GROUPS:]
    for key, row in ordered_groups:
        if not isinstance(key, str) or not isinstance(row, dict):
            continue
        normalized_key = key.lower()
        if re.fullmatch(r"[0-9a-f]{16,64}", normalized_key):
            safe_group_id = normalized_key[:64]
        else:
            safe_group_id = hashlib.sha256(key.encode("utf-8", "ignore")).hexdigest()[:16]
        if safe_group_id in clean_groups:
            safe_group_id = hashlib.sha256(
                f"{key}|{row.get('code','')}|{row.get('first_seen','')}".encode("utf-8", "ignore")
            ).hexdigest()[:16]
        group_id_aliases[key] = safe_group_id
        item = dict(row)
        item["group_id"] = safe_group_id
        item["occurrences"] = _safe_int(item.get("occurrences"), 0)
        item["resolved_count"] = min(item["occurrences"], _safe_int(item.get("resolved_count"), 0))
        item["unresolved_count"] = max(0, item["occurrences"] - item["resolved_count"])
        raw_http_status = item.get("http_status")
        try:
            parsed_http_status = int(raw_http_status) if not isinstance(raw_http_status, bool) else 0
        except (TypeError, ValueError, OverflowError):
            parsed_http_status = 0
        item["http_status"] = parsed_http_status if 100 <= parsed_http_status <= 599 else None
        statuses = []
        raw_statuses = item.get("http_statuses") if isinstance(item.get("http_statuses"), list) else []
        for value in raw_statuses + ([item["http_status"]] if item["http_status"] is not None else []):
            parsed = _safe_int(value, 0, 0, 599)
            if 100 <= parsed <= 599 and parsed not in statuses:
                statuses.append(parsed)
        item["http_statuses"] = statuses[-20:]
        item["bounded_retry_allowed"] = item.get("bounded_retry_allowed") is True
        item["scenario_prepared"] = item.get("scenario_prepared") is True
        raw_profile_id = item.get("scenario_profile_id")
        item["scenario_profile_id"] = raw_profile_id if isinstance(raw_profile_id, str) and re.fullmatch(r"[0-9a-f]{16}", raw_profile_id) else None
        item["prepared_scenario_count"] = _safe_int(item.get("prepared_scenario_count"), 0, 0, 1000)
        item["diagnostic_priority"] = _safe_int(item.get("diagnostic_priority"), 50, 1, 100)
        item.pop("clean_observations_after_error", None)
        item.pop("resolution_confirmed", None)
        for field, limit in (("code", 80), ("title", 160), ("category", 100),
                             ("error_subtype", 100),
                             ("probable_cause", 600), ("safe_action", 500),
                             ("recommended_action", 500), ("automation_policy", 500),
                             ("proven_action", 400), ("last_detail", 500)):
            if field in item:
                item[field] = redact_sensitive(item[field], limit)
        fallback_timestamp = base.get("updated_at") or _utc_timestamp()
        first_seen = _canonical_report_timestamp(item.get("first_seen"))
        last_seen = _canonical_report_timestamp(item.get("last_seen"))
        first_seen = first_seen or last_seen or fallback_timestamp
        last_seen = last_seen or first_seen
        item["first_seen"], item["last_seen"] = min(first_seen, last_seen), max(first_seen, last_seen)
        files = []
        for value in item.get("affected_files", []) if isinstance(item.get("affected_files"), list) else []:
            label = _safe_file_label(value)
            if label not in files:
                files.append(label)
        item["affected_files"] = files[-MAX_GROUP_FILES:]
        raw_counts = item.get("file_counts") if isinstance(item.get("file_counts"), dict) else {}
        item["file_counts"] = {_safe_file_label(name): _safe_int(count, 0)
                               for name, count in list(raw_counts.items())[-MAX_GROUP_FILES:]}
        raw_states = item.get("file_states") if isinstance(item.get("file_states"), dict) else {}
        clean_states = {}
        for name, value in list(raw_states.items())[-MAX_GROUP_FILES:]:
            if not isinstance(value, dict):
                continue
            label = _safe_file_label(name)
            state_occurrences = _safe_int(
                value.get("occurrences"), item["file_counts"].get(label, 0)
            )
            state_resolved = min(state_occurrences, _safe_int(value.get("resolved_count"), 0))
            state = {
                "occurrences": state_occurrences,
                "resolved_count": state_resolved,
                "last_outcome": (
                    "resolved"
                    if state_occurrences > 0 and value.get("last_outcome") == "resolved" and state_resolved >= state_occurrences
                    else "unresolved"
                ),
                "clean_observations_after_error": _safe_int(
                    value.get("clean_observations_after_error"), 0
                ),
                "resolution_confirmed": bool(value.get("resolution_confirmed")),
            }
            for stamp in ("last_seen", "last_clean_seen"):
                if value.get(stamp) is not None:
                    state[stamp] = redact_sensitive(value.get(stamp), 80)
            clean_states[label] = state
        allocated = sum(_safe_int(state.get("resolved_count"), 0) for state in clean_states.values())
        remaining_resolved = max(0, item["resolved_count"] - allocated)
        labels = list(dict.fromkeys([*item["affected_files"], *item["file_counts"]]))
        if not labels and item["occurrences"]:
            labels = ["unknown"]
            item["affected_files"] = labels
            item["file_counts"]["unknown"] = item["occurrences"]
        for label in labels[-MAX_GROUP_FILES:]:
            if label in clean_states:
                continue
            state_occurrences = item["file_counts"].get(label, 0)
            if item.get("last_outcome") == "resolved":
                state_resolved = state_occurrences
            else:
                state_resolved = min(state_occurrences, remaining_resolved)
                remaining_resolved -= state_resolved
            clean_states[label] = {
                "occurrences": state_occurrences,
                "resolved_count": state_resolved,
                "last_outcome": "resolved" if state_occurrences > 0 and state_occurrences <= state_resolved else "unresolved",
                "clean_observations_after_error": 2 if state_occurrences > 0 and state_occurrences <= state_resolved else 0,
                "resolution_confirmed": bool(state_occurrences > 0 and state_occurrences <= state_resolved),
            }
        item["file_states"] = clean_states
        if clean_states:
            item["resolved_count"] = min(
                item["occurrences"],
                sum(_safe_int(state.get("resolved_count"), 0) for state in clean_states.values()),
            )
        item["sample_details"] = [redact_sensitive(value, 500) for value in
                                  (item.get("sample_details") if isinstance(item.get("sample_details"), list) else [])
                                  if value][-MAX_GROUP_SAMPLES:]
        for field in ("resolution_steps", "verification_steps"):
            values = item.get(field) if isinstance(item.get(field), list) else []
            item[field] = [redact_sensitive(value, 400) for value in values if value][:6]
        for field, limit in (("first_checks", 5), ("fast_resolution_steps", 6), ("stop_conditions", 5)):
            values = item.get(field) if isinstance(item.get(field), list) else []
            item[field] = [redact_sensitive(value, 400) for value in values if isinstance(value, str) and value.strip()][:limit]
        successes = item.get("successful_actions") if isinstance(item.get("successful_actions"), dict) else {}
        clean_successes = {}
        for action, count in list(successes.items())[-20:]:
            safe_action = redact_sensitive(action, 400)
            clean_successes[safe_action] = min(1_000_000, _safe_int(clean_successes.get(safe_action), 0) + _safe_int(count, 0))
        item["successful_actions"] = clean_successes
        history = []
        for event in item.get("resolution_history", []) if isinstance(item.get("resolution_history"), list) else []:
            if not isinstance(event, dict):
                continue
            history.append({
                "timestamp": redact_sensitive(event.get("timestamp"), 80),
                "file": _safe_file_label(event.get("file")),
                "origin": redact_sensitive(event.get("origin"), 40),
                "action": redact_sensitive(event.get("action"), 400),
                "resolved": bool(event.get("resolved")),
            })
        item["resolution_history"] = history[-MAX_RESOLUTION_HISTORY:]
        item["last_outcome"] = "resolved" if item.get("last_outcome") == "resolved" else "unresolved"
        _update_group_status(item)
        clean_groups[safe_group_id] = item
    base["error_groups"] = clean_groups
    clean_log_by_group = {}
    raw_log = base.get("new_error_log") if isinstance(base.get("new_error_log"), list) else []
    for row in raw_log[-MAX_NEW_ERROR_LOG:]:
        if not isinstance(row, dict):
            continue
        item = {key: redact_sensitive(row.get(key), 600) for key in
                ("code", "title", "category", "error_subtype", "file", "detail",
                 "probable_cause", "safe_action", "analysis_status", "last_outcome",
                 "proven_action") if row.get(key) is not None}
        fallback_timestamp = base.get("updated_at") or _utc_timestamp()
        item["first_seen"] = _canonical_report_timestamp(row.get("first_seen")) or fallback_timestamp
        item["last_seen"] = _canonical_report_timestamp(row.get("last_seen")) or item["first_seen"]
        item["occurrences"] = _safe_int(row.get("occurrences"), 0)
        item["unresolved_count"] = _safe_int(row.get("unresolved_count"), 0)
        raw_http_status = row.get("http_status")
        parsed_http_status = _safe_int(raw_http_status, 0, 0, 599)
        item["http_status"] = parsed_http_status if 100 <= parsed_http_status <= 599 else None
        item["bounded_retry_allowed"] = row.get("bounded_retry_allowed") is True
        item["http_statuses"] = []
        for value in row.get("http_statuses", []) if isinstance(row.get("http_statuses"), list) else []:
            parsed = _safe_int(value, 0, 0, 599)
            if 100 <= parsed <= 599 and parsed not in item["http_statuses"]:
                item["http_statuses"].append(parsed)
        for field in ("resolution_steps", "verification_steps"):
            values = row.get(field) if isinstance(row.get(field), list) else []
            item[field] = [redact_sensitive(value, 400) for value in values if value][:6]
        raw_group_id = row.get("group_id")
        group_id = group_id_aliases.get(raw_group_id) if isinstance(raw_group_id, str) else None
        if group_id is None and isinstance(raw_group_id, str) and re.fullmatch(r"[0-9a-fA-F]{16,64}", raw_group_id):
            group_id = raw_group_id.lower()[:64]
        group_id = group_id or hashlib.sha256(
            f"{item.get('code','')}|{item.get('title','')}|{item.get('first_seen','')}".encode("utf-8", "ignore")
        ).hexdigest()[:16]
        item["group_id"] = group_id
        if group_id not in clean_log_by_group:
            clean_log_by_group[group_id] = item
    base["new_error_log"] = list(clean_log_by_group.values())[-MAX_NEW_ERROR_LOG:]
    _sync_new_error_log(base)
    files = base.get("files") if isinstance(base.get("files"), dict) else {}
    clean_files = {}
    for key, row in list(files.items())[-200:]:
        if not isinstance(key, str) or not isinstance(row, dict):
            continue
        item = dict(row)
        for field in ("runs", "recent_failures", "successful_repairs", "clean_success_streak"):
            item[field] = _safe_int(item.get(field), 0, 0, 1_000_000)
        clean_files[key] = item
    base["files"] = clean_files
    known = base.get("monitor_known_errors") if isinstance(base.get("monitor_known_errors"), dict) else {}
    clean_known = {}
    for key, row in list(known.items())[-MAX_ERROR_PATTERNS:]:
        if not isinstance(key, str) or not isinstance(row, dict):
            continue
        item = dict(row)
        item["occurrences"] = _safe_int(item.get("occurrences"), 0)
        item["resolved_count"] = _safe_int(item.get("resolved_count"), 0)
        if "last_message" in item:
            item["last_message"] = redact_sensitive(item["last_message"], 800)
        clean_known[key] = item
    base["monitor_known_errors"] = clean_known
    if not isinstance(base.get("monitor_history"), list):
        base["monitor_history"] = []
    else:
        cleaned_history = []
        for row in base["monitor_history"][-MAX_MONITOR_HISTORY:]:
            if not isinstance(row, dict):
                continue
            item = dict(row)
            if "error_message" in item:
                item["error_message"] = redact_sensitive(item["error_message"], 800)
            if "traceback_tail" in item:
                item["traceback_tail"] = redact_sensitive(item["traceback_tail"], 2500)
            cleaned_history.append(item)
        base["monitor_history"] = cleaned_history
    base["version"] = max(4, _safe_int(base.get("version"), 4, 4, 999))
    _refresh_learning_summary(base)
    return base

def load_memory(path: Path | None = None) -> dict:
    path = Path(path or MEMORY)
    # v59: 학습 메모리가 손상돼도 즉시 초기화하지 않고 직전 원자 백업을 먼저 복구한다.
    candidates = (path, path.with_suffix(path.suffix + ".bak"))
    for candidate in candidates:
        try:
            data = _load_strict_json(candidate)
            if isinstance(data, dict) and isinstance(data.get("patterns"), dict):
                base = _default_memory()
                base.update(data)
                base.setdefault("monitor_known_errors", {})
                base.setdefault("monitor_history", [])
                base["version"] = max(4, _safe_int(base.get("version"), 1, 1, 999))
                base = _sanitize_memory(base)
                if candidate != path:
                    LOGGER.warning("학습 메모리 손상 감지 · 백업에서 복구: %s", candidate.name)
                return base
        except (OSError, ValueError, TypeError):
            continue
    return _default_memory()


def _atomic_save_memory(memory: dict, path: Path | None = None) -> None:
    path = Path(path or MEMORY)
    with MEMORY_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        bak = path.with_suffix(path.suffix + ".bak")
        if path.is_symlink() or bak.is_symlink():
            raise ValueError("학습 메모리의 심볼릭 링크 저장 경로를 차단했습니다.")
        sanitized = _sanitize_memory(memory)
        encoded = json.dumps(sanitized, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        # 현재 메모리가 정상 JSON일 때만 직전 정상본으로 보존한다.
        if path.exists():
            try:
                old = _load_strict_json(path)
                if isinstance(old, dict) and isinstance(old.get("patterns"), dict):
                    backup = json.dumps(_sanitize_memory(old), ensure_ascii=False, indent=2, allow_nan=False) + "\n"
                    atomic_write_text(bak, backup)
            except (OSError, ValueError, TypeError):
                pass
        atomic_write_text(path, encoded)


def classify(detail: str) -> tuple[str, str, str]:
    """Return the same policy used by root-cause analysis without duplicate rules."""
    analysis = analyze_error(detail, use_scenario_profile=False)
    return analysis["category"], analysis["safe_action"], analysis["recommended_action"]


def fingerprint(filename: str, category: str, detail: str) -> str:
    normalized = redact_sensitive(detail, 1200).lower()
    normalized = re.sub(r"\d+", "#", normalized)[:240]
    return hashlib.sha256(f"{filename}|{category}|{normalized}".encode()).hexdigest()[:16]


def attempts_for(filename: str, memory: dict) -> int:
    files = memory.get("files", {}) if isinstance(memory, dict) else {}
    row = files.get(filename, {}) if isinstance(files, dict) else {}
    failures = _safe_int(row.get("recent_failures", 0) if isinstance(row, dict) else 0, 0, 0, 4)
    return min(4, 2 + failures)


def _report_error_details(result: dict, ok: bool) -> tuple[list[str], int]:
    """Return unique, bounded diagnostics and the number of malformed fields."""
    details: list[str] = []
    seen: set[str] = set()
    invalid = 0

    def append(value: Any) -> None:
        nonlocal invalid
        if value is None or value == "":
            return
        if not isinstance(value, str):
            invalid += 1
            return
        safe = redact_sensitive(value).strip()
        identity = safe.casefold()
        if safe and identity not in seen:
            seen.add(identity)
            details.append(safe)

    raw_details = result.get("collection_errors")
    if isinstance(raw_details, (list, tuple)):
        for value in raw_details[:50]:
            append(value)
    elif raw_details is not None:
        append(raw_details)
    append(result.get("collection_error"))

    raw_error = result.get("error")
    if raw_error is not None and raw_error != "":
        if isinstance(raw_error, str):
            safe_error = redact_sensitive(raw_error).strip()
            parts = [part.strip().casefold() for part in re.split(r"\s+(?:/|·)\s+", safe_error) if part.strip()]
            # ``auto_update_all`` may provide both the atomic collection errors
            # and one human-readable joined summary. Store each event only once.
            joined_duplicate = len(parts) > 1 and all(part in seen for part in parts)
            if not joined_duplicate:
                append(safe_error)
        else:
            invalid += 1
    if not ok and not details:
        append(result.get("status") if result.get("status") is not None else "오류")
    return details[:50], invalid


def _remaining_report_errors(result: dict) -> tuple[set[str], int, bool]:
    """Return unresolved diagnostics explicitly reported by the final attempt.

    ``collection_errors`` includes earlier failed attempts as useful history.
    Treating every such row as repaired merely because the JSON fallback stayed
    readable produced false "해결 확인" counts.  Newer collectors expose the
    final-attempt subset in ``remaining_collection_errors``; its presence is an
    outcome contract, including an intentionally empty list after recovery.
    """
    if "remaining_collection_errors" not in result:
        return set(), 0, False
    raw = result.get("remaining_collection_errors")
    if raw is None:
        values: list[Any] = []
    elif isinstance(raw, (list, tuple)):
        values = list(raw[:50])
    elif isinstance(raw, str):
        values = [raw]
    else:
        return set(), 1, True
    remaining: set[str] = set()
    invalid = 0
    for value in values:
        if not isinstance(value, str):
            invalid += 1
            continue
        safe = redact_sensitive(value).strip().casefold()
        if safe:
            remaining.add(safe)
    return remaining, invalid, True


def learn(report: dict, path: Path | None = None) -> dict:
    path = Path(path or MEMORY)
    if not isinstance(report, dict) or not isinstance(report.get("results", []), list):
        raise ValueError("학습 보고서 형식 오류")
    with MEMORY_LOCK, _memory_process_lock(path):
        memory = load_memory(path)
        memory["total_runs"] = min(1_000_000, _safe_int(memory.get("total_runs"), 0) + 1)
        previous_timestamp = _canonical_report_timestamp(memory.get("updated_at"))
        supplied_timestamp = report.get("finished_at")
        timestamp = _canonical_report_timestamp(supplied_timestamp) if supplied_timestamp not in (None, "") else None
        if supplied_timestamp not in (None, "") and timestamp is None:
            memory["invalid_report_count"] = min(
                1_000_000, _safe_int(memory.get("invalid_report_count"), 0) + 1
            )
        event_timestamp = timestamp or _utc_timestamp()
        memory["updated_at"] = max(value for value in (previous_timestamp, event_timestamp) if value)
        for result in report.get("results", [])[:1000]:
            if not isinstance(result, dict):
                memory["invalid_report_count"] = min(
                    1_000_000, _safe_int(memory.get("invalid_report_count"), 0) + 1
                )
                continue
            filename = result.get("file")
            if (not isinstance(filename, str) or not filename or len(filename) > 160
                    or any(char in filename for char in ("/", "\\", "\r", "\n", "\x00"))
                    or Path(filename).name != filename):
                memory["invalid_report_count"] = min(1_000_000, _safe_int(memory.get("invalid_report_count"), 0) + 1)
                continue
            ok_value = result.get("ok")
            if type(ok_value) is not bool:
                memory["invalid_report_count"] = min(
                    1_000_000, _safe_int(memory.get("invalid_report_count"), 0) + 1
                )
                continue
            invalid_flag = False
            for field in ("recovered_after_retry", "recovered_after_deferred_timeout"):
                if field in result and type(result[field]) is not bool:
                    memory["invalid_report_count"] = min(
                        1_000_000, _safe_int(memory.get("invalid_report_count"), 0) + 1
                    )
                    invalid_flag = True
            if invalid_flag:
                continue
            recovered_after_retry = result.get("recovered_after_retry") is True
            recovered_after_deferred = result.get("recovered_after_deferred_timeout") is True
            file_state = memory.setdefault("files", {}).setdefault(filename, {"runs": 0, "recent_failures": 0, "successful_repairs": 0})
            file_state["runs"] = min(1_000_000, _safe_int(file_state.get("runs"), 0) + 1)
            details, invalid_detail_count = _report_error_details(result, ok_value)
            remaining, invalid_remaining_count, has_remaining_contract = _remaining_report_errors(result)
            invalid_detail_count += invalid_remaining_count
            recovery_claimed = bool(ok_value and (recovered_after_retry or recovered_after_deferred))
            resolved_by_recovery = bool(recovery_claimed and (not has_remaining_contract or not remaining))
            detail_outcomes = {
                detail.casefold(): bool(
                    recovery_claimed
                    and (not has_remaining_contract or detail.casefold() not in remaining)
                )
                for detail in details
            }
            unresolved_details = [detail for detail in details if not detail_outcomes.get(detail.casefold(), False)]
            resolved_details = [detail for detail in details if detail_outcomes.get(detail.casefold(), False)]
            if invalid_detail_count:
                memory["invalid_report_count"] = min(
                    1_000_000,
                    _safe_int(memory.get("invalid_report_count"), 0) + invalid_detail_count,
                )
            had_problem = (not ok_value) or bool(details) or bool(invalid_detail_count) or recovery_claimed
            has_unresolved_problem = (not ok_value) or bool(unresolved_details) or bool(invalid_detail_count)
            if has_unresolved_problem:
                file_state["recent_failures"] = min(4, _safe_int(file_state.get("recent_failures"), 0) + 1)
                file_state["clean_success_streak"] = 0
                file_state["last_result"] = "partial_unresolved" if ok_value else "failed"
            elif had_problem:
                file_state["recent_failures"] = max(0, _safe_int(file_state.get("recent_failures"), 0) - 1)
                file_state["clean_success_streak"] = 0
                file_state["last_result"] = "recovered_verified"
                if resolved_details or resolved_by_recovery:
                    file_state["successful_repairs"] = min(1_000_000, _safe_int(file_state.get("successful_repairs"), 0) + 1)
            else:
                file_state["recent_failures"] = max(0, _safe_int(file_state.get("recent_failures"), 0) - 1)
                file_state["clean_success_streak"] = min(1_000_000, _safe_int(file_state.get("clean_success_streak"), 0) + 1)
                file_state["last_result"] = "clean_success"
                _observe_clean_file(memory, filename, event_timestamp)
            for detail in details:
                category, action, advice = classify(detail)
                key = fingerprint(filename, category, detail)
                recorded_action = result.get("auto_action")
                detail_resolved = detail_outcomes.get(detail.casefold(), False)
                learned_action = recorded_action if detail_resolved and isinstance(recorded_action, str) and recorded_action.strip() else action
                group_id, _ = _record_error_group(
                    memory, filename=filename, detail=detail, timestamp=event_timestamp,
                    resolved=detail_resolved,
                    action=learned_action, origin="update-report",
                )
                row = memory.setdefault("patterns", {}).setdefault(key, {
                    "file": filename, "category": category, "occurrences": 0,
                    "successful_repairs": 0, "auto_action": action, "recommended_action": advice,
                })
                row["occurrences"] = min(1_000_000, _safe_int(row.get("occurrences"), 0) + 1)
                row["last_seen"] = event_timestamp
                row["last_detail"] = redact_sensitive(detail)
                row["error_group_id"] = group_id
                if detail_resolved:
                    row["successful_repairs"] = min(1_000_000, _safe_int(row.get("successful_repairs"), 0) + 1)
        _atomic_save_memory(memory, path)
        return memory


class AutoRepairEngine:
    """프로젝트 기능 실행 감시 + 안전한 자동복구 + 오류패턴 학습.

    사용자 제안 코드의 장점을 반영하되 다음 안전장치를 둔다.
    * 임의 파일 경로를 예외문자열에서 추출해 생성하지 않는다.
    * JSON 파싱 오류를 빈 객체로 덮어쓰지 않는다. 마지막 정상본이 있을 때만 복원한다.
    * 학습된 `recommended_action` 문자열은 조언으로만 사용하고 코드처럼 실행하지 않는다.
    * 자동 재실행은 최대 1회이며, 동일 오류가 반복되면 즉시 중단한다.
    """

    def __init__(self, memory_file: str | Path = MEMORY, root: str | Path = ROOT, last_good: str | Path | None = None):
        self.root = Path(root).resolve()
        self.memory_file = Path(memory_file)
        if not self.memory_file.is_absolute():
            self.memory_file = self.root / self.memory_file
        self.last_good = Path(last_good).resolve() if last_good else self.root / ".tcg_last_good"
        self.learning_memory = load_memory(self.memory_file)

    def _safe_target(self, filename: str | Path | None) -> Path | None:
        if not filename:
            return None
        p = Path(filename)
        # 디렉터리 탈출 차단 + JSON 화이트리스트만 허용
        if p.is_absolute():
            try:
                rel = p.resolve().relative_to(self.root)
            except ValueError:
                return None
        else:
            rel = p
        if len(rel.parts) != 1 or rel.name not in SAFE_JSON_FILES:
            return None
        target = self.root / rel.name
        try:
            if target.is_symlink() or target.resolve().parent != self.root:
                return None
        except OSError:
            return None
        return target

    def _restore_last_good(self, target: Path) -> tuple[bool, str]:
        backup = self.last_good / target.name
        if not backup.exists():
            return False, f"마지막 정상본 없음: {target.name}"
        try:
            if backup.is_symlink() or backup.resolve().parent != self.last_good:
                return False, f"안전하지 않은 백업 경로: {target.name}"
            if self._safe_target(target) is None:
                return False, f"안전하지 않은 복구 대상: {target.name}"
            data = _load_strict_json(backup)
            if not _valid_project_payload(target.name, data):
                return False, f"백업 구조 오류: {target.name}"
            tmp = target.with_suffix(target.suffix + ".repair.tmp")
            encoded = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
            with REPAIR_FILE_LOCK:
                tmp.unlink(missing_ok=True)
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
                descriptor = os.open(tmp, flags, 0o600)
                try:
                    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                        output.write(encoded)
                        output.flush()
                        try:
                            os.fsync(output.fileno())
                        except OSError:
                            pass
                    tmp.replace(target)
                finally:
                    tmp.unlink(missing_ok=True)
            return True, f"마지막 정상본 복원: {target.name}"
        except Exception as exc:
            return False, f"정상본 복원 실패: {type(exc).__name__}: {exc}"

    def _record_monitor_event(self, *, func_name: str, error_type: str, error_msg: str, tb: str,
                              resolved: bool, action: str, target_file: str | None, attempt: int) -> None:
        with MEMORY_LOCK, _memory_process_lock(self.memory_file):
            # Another pipeline may have learned since this engine was created.
            self.learning_memory = load_memory(self.memory_file)
            now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            normalized = redact_sensitive(error_msg, 800)
            normalized = re.sub(r"\b\d+(?:\.\d+)?\b", "<n>", normalized)[:800]
            key = fingerprint(target_file or func_name, error_type, normalized)
            known = self.learning_memory.setdefault("monitor_known_errors", {}).setdefault(key, {
                "function": func_name,
                "target_file": target_file,
                "error_type": error_type,
                "occurrences": 0,
                "resolved_count": 0,
                "safe_action": action,
            })
            known["occurrences"] = min(1_000_000, _safe_int(known.get("occurrences"), 0) + 1)
            known["resolved_count"] = min(1_000_000, _safe_int(known.get("resolved_count"), 0) + (1 if resolved else 0))
            known["last_seen"] = now
            known["last_message"] = normalized
            group_id, _ = _record_error_group(
                self.learning_memory, filename=target_file or func_name,
                detail=error_msg, error_type=error_type, timestamp=now,
                resolved=resolved, action=action, origin="runtime-monitor",
            )
            known["error_group_id"] = group_id
            if resolved:
                known["last_successful_action"] = action
            hist = self.learning_memory.setdefault("monitor_history", [])
            hist.append({
                "timestamp": now, "function": func_name, "target_file": target_file,
                "error_type": error_type, "error_message": normalized, "resolved": resolved,
                "fix_action": action, "attempt": attempt,
                "traceback_tail": redact_sensitive("\n".join(tb.strip().splitlines()[-8:]), 2500),
            })
            if len(hist) > MAX_MONITOR_HISTORY:
                del hist[:-MAX_MONITOR_HISTORY]
            self.learning_memory["updated_at"] = now
            _atomic_save_memory(self.learning_memory, self.memory_file)

    def _attempt_auto_repair(self, error_type: str, error_msg: str, target_file: str | Path | None = None) -> tuple[bool, str]:
        target = self._safe_target(target_file)
        if error_type in {"FileNotFoundError", "JSONDecodeError", "UnicodeDecodeError", "ValueError"} and target:
            return self._restore_last_good(target)
        # PermissionError, 코드 오류, 구조변경 등은 자동으로 파일/권한을 임의 수정하지 않는다.
        return False, "안전한 자동수정 규칙 없음 · 기존 정상자료 유지/상위 복구정책에 위임"

    def execute_with_monitoring(self, target_func: Callable[..., Any], *args,
                                target_file: str | Path | None = None, max_retries: int = 1, **kwargs) -> Any:
        func_name = getattr(target_func, "__name__", target_func.__class__.__name__)
        max_retries = _safe_int(max_retries, 1, 0, 1)
        seen: set[str] = set()
        for attempt in range(max_retries + 1):
            try:
                LOGGER.info("파이프라인 모듈 실행 시작: %s (시도 %d)", func_name, attempt + 1)
                result = target_func(*args, **kwargs)
                LOGGER.info("파이프라인 모듈 정상 완료: %s", func_name)
                return result
            except Exception as err:
                error_type = type(err).__name__
                error_msg = str(err)
                tb = traceback.format_exc()
                sig = fingerprint(str(target_file or func_name), error_type, error_msg)
                LOGGER.warning("[오류 감지] %s | %s", error_type, redact_sensitive(error_msg))
                if sig in seen:
                    self._record_monitor_event(func_name=func_name, error_type=error_type, error_msg=error_msg, tb=tb,
                                               resolved=False, action="동일 오류 반복 · 재실행 중단", target_file=str(target_file) if target_file else None, attempt=attempt + 1)
                    raise
                seen.add(sig)
                repaired, action = self._attempt_auto_repair(error_type, error_msg, target_file)
                self._record_monitor_event(func_name=func_name, error_type=error_type, error_msg=error_msg, tb=tb,
                                           resolved=repaired, action=action, target_file=str(target_file) if target_file else None, attempt=attempt + 1)
                if repaired and attempt < max_retries:
                    LOGGER.info("[보완 완료] %s · 재실행", action)
                    continue
                raise
        raise RuntimeError("모니터링 실행 한도 초과")

    def validate_project_files(self, filenames: list[str]) -> dict:
        """핵심 JSON을 점검하고 손상/누락 시 마지막 정상본으로만 복원한다."""
        results = []
        for name in filenames:
            target = self._safe_target(name)
            if not target:
                results.append({"file": name, "ok": False, "action": "허용되지 않은 파일"})
                continue
            try:
                data = _load_strict_json(target)
                if not _valid_project_payload(target.name, data):
                    raise ValueError("프로젝트 JSON 구조 또는 숫자 오류")
                results.append({"file": name, "ok": True, "action": "검증 통과"})
            except Exception as exc:
                ok, action = self._attempt_auto_repair(type(exc).__name__, str(exc), name)
                self._record_monitor_event(func_name="validate_project_files", error_type=type(exc).__name__, error_msg=str(exc),
                                           tb=traceback.format_exc(), resolved=ok, action=action, target_file=name, attempt=1)
                results.append({"file": name, "ok": ok, "action": action, "error": f"{type(exc).__name__}: {exc}"})
        return {"ok": all(r["ok"] for r in results), "results": results}
