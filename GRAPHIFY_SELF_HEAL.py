#!/usr/bin/env python3
"""Bounded, learning-based self-healing for the local Graphify integration.

The engine may repair only explicitly approved Graphify/Termux integration state.
It never generates arbitrary Python/shell patches from logs, never edits TCG source
code, and never commits/pushes to git. Learning only changes the priority of
pre-approved recovery strategies for a normalized failure signature.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = 2
PINNED_VERSION = os.environ.get("GRAPHIFY_VERSION", "0.9.53")
MEMORY_PATH = Path(os.environ.get("GRAPHIFY_SELF_HEAL_MEMORY", "graphify_self_heal_memory.json"))
REPORT_PATH = Path(os.environ.get("GRAPHIFY_SELF_HEAL_REPORT", "graphify_self_heal_report.json"))
CANDIDATE_PATH = Path(os.environ.get("GRAPHIFY_SELF_HEAL_CANDIDATES", "graphify_self_heal_candidates.json"))
RECOVERY_ROOT = Path(os.environ.get("GRAPHIFY_RECOVERY_DIR", ".graphify_recovery"))
GRAPHIFY_BIN = os.environ.get("GRAPHIFY_BIN", "graphify")
MAX_HISTORY = 160
MAX_CANDIDATES = 40
MAX_RECOVERY_DIRS = 6
MAX_STRATEGIES_PER_RUN = 4
SUBPROCESS_TIMEOUT = int(os.environ.get("GRAPHIFY_HEAL_COMMAND_TIMEOUT", "180"))

REQUIRED_OUTPUTS = (
    Path("graphify-out/graph.json"),
    Path("graphify-out/GRAPH_REPORT.md"),
    Path("graphify-out/graph.html"),
)

APPROVED_STRATEGIES = {
    "repair_path",
    "repair_install",
    "materialize_outputs",
    "rebuild_from_scratch",
    "repair_install_and_rebuild",
    "reinstall_hooks",
    "repair_codex_integration",
}

DEFAULT_STRATEGIES = {
    "command_missing": ["repair_path", "repair_install"],
    "path_missing": ["repair_path", "repair_install"],
    "version_mismatch": ["repair_install"],
    "missing_outputs": ["materialize_outputs", "rebuild_from_scratch", "repair_install_and_rebuild"],
    "invalid_outputs": ["rebuild_from_scratch", "repair_install_and_rebuild"],
    "update_failed": ["rebuild_from_scratch", "repair_install_and_rebuild"],
    "extract_failed": ["rebuild_from_scratch", "repair_install_and_rebuild"],
    "cluster_failed": ["materialize_outputs", "rebuild_from_scratch", "repair_install_and_rebuild"],
    "hook_failed": ["reinstall_hooks", "repair_install"],
    "codex_install_failed": ["repair_codex_integration", "repair_install"],
    "permission_denied": ["repair_path", "reinstall_hooks"],
    "network_failure": ["repair_install"],
    "rate_limited": ["repair_install"],
    "timeout": ["repair_install_and_rebuild"],
    "unknown": ["rebuild_from_scratch", "repair_install_and_rebuild"],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_run(args: list[str], *, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    timeout = timeout or SUBPROCESS_TIMEOUT
    try:
        return subprocess.run(args, text=True, capture_output=True, timeout=timeout)
    except FileNotFoundError as exc:
        return subprocess.CompletedProcess(args, 127, "", str(exc))
    except PermissionError as exc:
        return subprocess.CompletedProcess(args, 126, "", str(exc))
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return subprocess.CompletedProcess(args, 124, stdout, stderr + f"\ntimeout after {timeout}s")


def graphify_cmd(*args: str) -> subprocess.CompletedProcess[str]:
    return safe_run([GRAPHIFY_BIN, *args])


def version_text() -> str:
    proc = graphify_cmd("--version")
    return (proc.stdout or proc.stderr or "").strip()


def version_matches(text: str) -> bool:
    if not text:
        return False
    pattern = rf"(?<!\d){re.escape(PINNED_VERSION)}(?!\d)"
    return re.search(pattern, text) is not None


def validate_outputs_detail() -> tuple[bool, str]:
    missing = [str(path) for path in REQUIRED_OUTPUTS if not path.is_file() or path.stat().st_size <= 0]
    if missing:
        return False, "missing outputs: " + ", ".join(missing)

    graph_path, report_path, html_path = REQUIRED_OUTPUTS
    try:
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"invalid graph.json: {exc}"
    if not isinstance(graph, (dict, list)):
        return False, f"invalid graph.json root type: {type(graph).__name__}"

    try:
        report = report_path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError as exc:
        return False, f"cannot read GRAPH_REPORT.md: {exc}"
    if len(report) < 20:
        return False, "GRAPH_REPORT.md is unexpectedly small"

    try:
        html = html_path.read_text(encoding="utf-8", errors="replace").lower()
    except OSError as exc:
        return False, f"cannot read graph.html: {exc}"
    if len(html) < 80 or ("<html" not in html and "<!doctype" not in html):
        return False, "graph.html does not look like HTML"

    return True, "all Graphify outputs are structurally valid"


def outputs_ok() -> bool:
    return validate_outputs_detail()[0]


def default_memory() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "updated_at": None,
        "categories": {},
        "signatures": {},
        "history": [],
    }


def load_memory(path: Path = MEMORY_PATH) -> dict[str, Any]:
    if not path.exists():
        return default_memory()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("memory root must be an object")
        data.setdefault("schema", SCHEMA)
        data.setdefault("categories", {})
        data.setdefault("signatures", {})
        data.setdefault("history", [])
        data["schema"] = SCHEMA
        return data
    except Exception:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        corrupt = path.with_name(f"{path.name}.corrupt.{stamp}")
        try:
            path.replace(corrupt)
        except OSError:
            pass
        return default_memory()


def atomic_json_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def tail_text(path: Path, limit: int = 20000) -> str:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return raw[-limit:]


def classify_failure(text: str, failure_code: int = 0, reason: str = "") -> str:
    haystack = f"{reason}\n{text}".lower()

    if failure_code == 40 or "codex install" in haystack and any(k in haystack for k in ("fail", "error", "오류")):
        return "codex_install_failed"
    if failure_code == 41 or "hook" in haystack and any(k in haystack for k in ("fail", "error", "오류")):
        return "hook_failed"
    if "429" in haystack or "too many requests" in haystack or "rate limit" in haystack:
        return "rate_limited"
    if any(k in haystack for k in ("timed out", "timeout", "시간 초과")):
        return "timeout"
    if any(k in haystack for k in (
        "temporary failure in name resolution",
        "network is unreachable",
        "connection reset",
        "connection refused",
        "ssl error",
        "name or service not known",
    )):
        return "network_failure"
    if "permission denied" in haystack or "operation not permitted" in haystack:
        return "permission_denied"
    if "command not found" in haystack or ("no such file or directory" in haystack and "graphify" in haystack):
        return "command_missing"
    if "path" in haystack and "graphify" in haystack and any(k in haystack for k in ("not found", "missing", "없")):
        return "path_missing"
    if "version mismatch" in haystack or "unsupported version" in haystack or "pinned version" in haystack:
        return "version_mismatch"
    if "invalid graph.json" in haystack or "does not look like html" in haystack or "structurally valid" in haystack and "not" in haystack:
        return "invalid_outputs"
    if "필수 지도 산출물" in haystack or "missing output" in haystack or ("graph_report.md" in haystack and "없" in haystack):
        return "missing_outputs"
    if "cluster-only" in haystack and any(k in haystack for k in ("fail", "error", "오류")):
        return "cluster_failed"
    if "extract" in haystack and any(k in haystack for k in ("fail", "error", "오류")):
        return "extract_failed"
    if failure_code in (21, 31) or ("update" in haystack and any(k in haystack for k in ("fail", "error", "오류"))):
        return "update_failed"

    if failure_code == 10:
        return "command_missing"
    if failure_code == 11:
        return "version_mismatch"
    if failure_code in (22, 32):
        return "extract_failed"
    if failure_code in (23, 33):
        return "cluster_failed"
    if failure_code in (24, 34):
        return "missing_outputs"
    return "unknown"


def normalize_failure_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\b[0-9a-f]{7,40}\b", "<sha>", text)
    text = re.sub(r"\b\d{4}-\d{2}-\d{2}[t ][0-9:.+\-z]+\b", "<time>", text)
    text = re.sub(r"/(?:[^/\s]+/)+[^/\s]+", "<path>", text)
    text = re.sub(r"\b\d+\b", "<n>", text)
    lines = []
    for raw in text.splitlines():
        line = " ".join(raw.split())
        if not line:
            continue
        if any(token in line for token in (
            "error", "fail", "오류", "missing", "not found", "denied", "timeout",
            "graphify", "version", "429", "network", "invalid",
        )):
            lines.append(line[:300])
    if not lines:
        lines = [" ".join(text.split())[-1200:]]
    return "\n".join(lines[-16:])


def failure_signature(category: str, text: str, failure_code: int, reason: str) -> str:
    normalized = normalize_failure_text(f"{reason}\n{text}")
    payload = f"{category}|{failure_code}|{normalized}".encode("utf-8", errors="replace")
    return hashlib.sha256(payload).hexdigest()[:16]


def strategy_score(stats: dict[str, Any]) -> int:
    return int(stats.get("successes", 0)) * 3 - int(stats.get("failures", 0)) * 2


def learned_order(memory: dict[str, Any], category: str, signature: str = "") -> list[str]:
    base = list(DEFAULT_STRATEGIES.get(category, DEFAULT_STRATEGIES["unknown"]))

    preferred: list[str] = []
    if signature:
        sig_data = memory.get("signatures", {}).get(signature, {})
        sig_pref = sig_data.get("preferred_strategy")
        if sig_pref in APPROVED_STRATEGIES:
            preferred.append(sig_pref)

    cat_data = memory.get("categories", {}).get(category, {})
    cat_pref = cat_data.get("preferred_strategy")
    if cat_pref in APPROVED_STRATEGIES:
        preferred.append(cat_pref)

    ranked = []
    strategy_stats = cat_data.get("strategies", {})
    for strategy in base:
        stats = strategy_stats.get(strategy, {})
        ranked.append((strategy_score(stats), strategy))
    ranked.sort(key=lambda item: item[0], reverse=True)

    result: list[str] = []
    for strategy in preferred + [name for _, name in ranked]:
        if strategy in APPROVED_STRATEGIES and strategy in base and strategy not in result:
            result.append(strategy)
    return result[:MAX_STRATEGIES_PER_RUN]


def _record_strategy(bucket: dict[str, Any], strategy: str, success: bool) -> None:
    strategies = bucket.setdefault("strategies", {})
    stats = strategies.setdefault(strategy, {"successes": 0, "failures": 0})
    key = "successes" if success else "failures"
    stats[key] = int(stats.get(key, 0)) + 1
    stats["last_result_at"] = utc_now()
    if success:
        bucket["preferred_strategy"] = strategy
        bucket["last_success_at"] = utc_now()
    else:
        bucket["last_failure_at"] = utc_now()


def record_result(
    memory: dict[str, Any], *,
    category: str,
    signature: str,
    strategy: str,
    success: bool,
    failure_code: int,
    reason: str,
    detail: str,
) -> None:
    categories = memory.setdefault("categories", {})
    cat = categories.setdefault(category, {"strategies": {}, "preferred_strategy": None})
    _record_strategy(cat, strategy, success)

    signatures = memory.setdefault("signatures", {})
    sig = signatures.setdefault(signature, {
        "category": category,
        "first_seen_at": utc_now(),
        "last_seen_at": utc_now(),
        "hits": 0,
        "strategies": {},
        "preferred_strategy": None,
    })
    sig["last_seen_at"] = utc_now()
    sig["hits"] = int(sig.get("hits", 0)) + 1
    _record_strategy(sig, strategy, success)

    history = memory.setdefault("history", [])
    history.append({
        "at": utc_now(),
        "category": category,
        "signature": signature,
        "strategy": strategy,
        "success": success,
        "failure_code": failure_code,
        "reason": reason[:300],
        "detail": detail[-1400:],
    })
    del history[:-MAX_HISTORY]
    memory["updated_at"] = utc_now()


def write_candidate(category: str, signature: str, failure_code: int, reason: str, log_text: str) -> None:
    data: dict[str, Any]
    if CANDIDATE_PATH.exists():
        try:
            loaded = json.loads(CANDIDATE_PATH.read_text(encoding="utf-8"))
            data = loaded if isinstance(loaded, dict) else {}
        except Exception:
            data = {}
    else:
        data = {}
    data.setdefault("schema", 1)
    data.setdefault("items", [])
    items = data["items"]

    candidate = {
        "at": utc_now(),
        "category": category,
        "signature": signature,
        "failure_code": failure_code,
        "reason": reason[:500],
        "normalized_excerpt": normalize_failure_text(log_text)[-1800:],
        "status": "needs_code_review",
    }
    items[:] = [item for item in items if item.get("signature") != signature]
    items.append(candidate)
    del items[:-MAX_CANDIDATES]
    data["updated_at"] = utc_now()
    atomic_json_write(CANDIDATE_PATH, data)


def repair_path() -> tuple[bool, str]:
    local_bin = str(Path.home() / ".local" / "bin")
    parts = os.environ.get("PATH", "").split(os.pathsep)
    if local_bin not in parts:
        os.environ["PATH"] = local_bin + os.pathsep + os.environ.get("PATH", "")

    bashrc = Path.home() / ".bashrc"
    marker = "# TCG_GRAPHIFY_PATH"
    line = 'export PATH="$HOME/.local/bin:$PATH"'
    try:
        existing = bashrc.read_text(encoding="utf-8", errors="replace") if bashrc.exists() else ""
        if marker not in existing:
            with bashrc.open("a", encoding="utf-8") as handle:
                handle.write(f"\n{marker}\n{line}\n")
    except OSError as exc:
        return False, f"failed to persist PATH: {exc}"

    found = shutil.which("graphify") or (str(Path.home() / ".local" / "bin" / "graphify")
                                         if (Path.home() / ".local" / "bin" / "graphify").exists() else "")
    return bool(found), f"PATH repaired; graphify={found or 'not installed'}"


def ensure_pinned_install() -> tuple[bool, str]:
    current = version_text()
    if version_matches(current):
        return True, f"already pinned: {current}"

    spec = f"graphifyy=={PINNED_VERSION}"
    details: list[str] = []
    if shutil.which("uv"):
        proc = safe_run(["uv", "tool", "install", "--force", spec])
        details.append((proc.stdout or "") + (proc.stderr or ""))
        if proc.returncode != 0:
            return False, "\n".join(details)
    else:
        if not shutil.which("pipx"):
            proc = safe_run([sys.executable, "-m", "pip", "install", "pipx"])
            details.append((proc.stdout or "") + (proc.stderr or ""))
            if proc.returncode != 0:
                return False, "\n".join(details)
        safe_run([sys.executable, "-m", "pipx", "ensurepath"])
        proc = safe_run([sys.executable, "-m", "pipx", "install", "--force", spec])
        details.append((proc.stdout or "") + (proc.stderr or ""))
        if proc.returncode != 0:
            return False, "\n".join(details)

    repair_path()
    current = version_text()
    if not version_matches(current):
        return False, "\n".join(details) + f"\nversion mismatch after repair: {current or 'unavailable'}"
    return True, "\n".join(details) + f"\ninstalled pinned version: {current}"


def prune_recovery_dirs() -> None:
    if not RECOVERY_ROOT.exists():
        return
    try:
        dirs = sorted((p for p in RECOVERY_ROOT.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime)
    except OSError:
        return
    for old in dirs[:-MAX_RECOVERY_DIRS]:
        shutil.rmtree(old, ignore_errors=True)


def quarantine_outputs() -> tuple[bool, Path | None, str]:
    out = Path("graphify-out")
    if not out.exists():
        return True, None, "no previous graphify-out"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    target = RECOVERY_ROOT / stamp / "graphify-out"
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(out), str(target))
        prune_recovery_dirs()
        return True, target, f"preserved old outputs at {target}"
    except OSError as exc:
        return False, None, f"failed to preserve old outputs: {exc}"


def restore_quarantined(target: Path | None) -> str:
    if target is None or not target.exists():
        return "no preserved outputs to restore"
    out = Path("graphify-out")
    try:
        if out.exists():
            shutil.rmtree(out)
        shutil.move(str(target), str(out))
        return "restored previous graphify-out after failed repair"
    except OSError as exc:
        return f"FAILED to restore previous graphify-out: {exc}"


def materialize_outputs() -> tuple[bool, str]:
    graph_json = Path("graphify-out/graph.json")
    if not graph_json.is_file() or graph_json.stat().st_size <= 0:
        return False, "graph.json missing; materialize cannot run"
    proc = graphify_cmd("cluster-only", ".", "--no-label")
    detail = (proc.stdout or "") + (proc.stderr or "")
    valid, validation = validate_outputs_detail()
    return proc.returncode == 0 and valid, (detail or "cluster-only completed") + "\n" + validation


def rebuild_from_scratch() -> tuple[bool, str]:
    ok, backup, preserved = quarantine_outputs()
    if not ok:
        return False, preserved

    proc = graphify_cmd("extract", ".", "--code-only")
    detail = preserved + "\n" + (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return False, detail + "\n" + restore_quarantined(backup)

    valid, validation = validate_outputs_detail()
    if not valid:
        proc2 = graphify_cmd("cluster-only", ".", "--no-label")
        detail += "\n" + (proc2.stdout or "") + (proc2.stderr or "")
        if proc2.returncode != 0:
            return False, detail + "\n" + restore_quarantined(backup)
        valid, validation = validate_outputs_detail()

    if not valid:
        return False, detail + "\n" + validation + "\n" + restore_quarantined(backup)
    return True, detail + "\n" + validation


def reinstall_hooks() -> tuple[bool, str]:
    proc = graphify_cmd("hook", "install")
    detail = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return False, detail
    status = graphify_cmd("hook", "status")
    detail += "\n" + (status.stdout or "") + (status.stderr or "")
    return status.returncode == 0, detail


def repair_codex_integration() -> tuple[bool, str]:
    proc = graphify_cmd("codex", "install", "--project")
    detail = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        fallback = graphify_cmd("install", "--project", "--platform", "codex")
        detail += "\n" + (fallback.stdout or "") + (fallback.stderr or "")
        if fallback.returncode != 0:
            return False, detail

    agents = graphify_cmd("agents", "install", "--project")
    detail += "\n" + (agents.stdout or "") + (agents.stderr or "")
    return Path("AGENTS.md").is_file(), detail


def execute_strategy(strategy: str) -> tuple[bool, str]:
    if strategy not in APPROVED_STRATEGIES:
        return False, f"blocked unapproved strategy: {strategy}"
    if strategy == "repair_path":
        return repair_path()
    if strategy == "repair_install":
        return ensure_pinned_install()
    if strategy == "materialize_outputs":
        return materialize_outputs()
    if strategy == "rebuild_from_scratch":
        return rebuild_from_scratch()
    if strategy == "repair_install_and_rebuild":
        ok, detail = ensure_pinned_install()
        if not ok:
            return False, detail
        rebuilt, rebuild_detail = rebuild_from_scratch()
        return rebuilt, detail + "\n" + rebuild_detail
    if strategy == "reinstall_hooks":
        return reinstall_hooks()
    if strategy == "repair_codex_integration":
        return repair_codex_integration()
    return False, "unknown approved strategy"


def repair(log_path: Path, failure_code: int, reason: str) -> int:
    log_text = tail_text(log_path)
    category = classify_failure(log_text, failure_code=failure_code, reason=reason)
    signature = failure_signature(category, log_text, failure_code, reason)
    memory = load_memory()
    strategies = learned_order(memory, category, signature)

    report: dict[str, Any] = {
        "schema": 2,
        "started_at": utc_now(),
        "category": category,
        "signature": signature,
        "failure_code": failure_code,
        "reason": reason,
        "pinned_version": PINNED_VERSION,
        "attempts": [],
        "success": False,
    }

    for strategy in strategies:
        success, detail = execute_strategy(strategy)
        record_result(
            memory,
            category=category,
            signature=signature,
            strategy=strategy,
            success=success,
            failure_code=failure_code,
            reason=reason,
            detail=detail,
        )
        atomic_json_write(MEMORY_PATH, memory)
        report["attempts"].append({
            "strategy": strategy,
            "success": success,
            "detail": detail[-2200:],
        })
        if success:
            report["success"] = True
            report["successful_strategy"] = strategy
            report["completed_at"] = utc_now()
            atomic_json_write(REPORT_PATH, report)
            print(f"[Graphify 자가복구] {category}/{signature} → {strategy} 성공")
            return 0

    report["completed_at"] = utc_now()
    report["needs_code_review"] = True
    atomic_json_write(REPORT_PATH, report)
    write_candidate(category, signature, failure_code, reason, log_text)
    print(
        f"[Graphify 자가복구] {category}/{signature} 자동복구 실패 · "
        f"후보를 {CANDIDATE_PATH}에 기록했습니다.",
        file=sys.stderr,
    )
    return 1


def self_test() -> int:
    assert classify_failure("graphify: command not found") == "command_missing"
    assert classify_failure("required missing output GRAPH_REPORT.md") == "missing_outputs"
    assert classify_failure("invalid graph.json: broken") == "invalid_outputs"
    assert classify_failure("extract error") == "extract_failed"
    assert classify_failure("hook error") == "hook_failed"
    assert classify_failure("HTTP 429 too many requests") == "rate_limited"
    assert classify_failure("permission denied") == "permission_denied"
    assert classify_failure("", failure_code=40, reason="codex setup failed") == "codex_install_failed"

    sig1 = failure_signature("update_failed", "error at /tmp/a.py line 123", 21, "update failed")
    sig2 = failure_signature("update_failed", "error at /tmp/b.py line 999", 21, "update failed")
    assert sig1 == sig2

    memory = default_memory()
    memory["categories"]["update_failed"] = {
        "preferred_strategy": "repair_install_and_rebuild",
        "strategies": {},
    }
    order = learned_order(memory, "update_failed")
    assert order[0] == "repair_install_and_rebuild"

    memory["categories"]["update_failed"]["preferred_strategy"] = "rm_everything"
    assert learned_order(memory, "update_failed")[0] != "rm_everything"

    assert execute_strategy("rm_everything")[0] is False
    print("Graphify self-heal bounded-learning self-test: OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repair", action="store_true")
    parser.add_argument("--log", default="GRAPHIFY_UPDATE.log")
    parser.add_argument("--failure-code", type=int, default=0)
    parser.add_argument("--reason", default="")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if args.validate_only:
        valid, detail = validate_outputs_detail()
        print(detail)
        return 0 if valid else 1
    if args.repair:
        return repair(Path(args.log), args.failure_code, args.reason)

    parser.error("use --repair, --validate-only, or --self-test")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
