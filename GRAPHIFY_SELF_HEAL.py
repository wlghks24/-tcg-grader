#!/usr/bin/env python3
"""Bounded self-healing for the local Graphify code map.

This module intentionally does NOT generate/execute arbitrary repair code and does not
commit anything to git.  It learns which *pre-approved* recovery strategy worked for
a known failure signature and tries that strategy first next time.
"""
from __future__ import annotations

import argparse
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

PINNED_VERSION = os.environ.get("GRAPHIFY_VERSION", "0.9.53")
MEMORY_PATH = Path(os.environ.get("GRAPHIFY_SELF_HEAL_MEMORY", "graphify_self_heal_memory.json"))
REPORT_PATH = Path(os.environ.get("GRAPHIFY_SELF_HEAL_REPORT", "graphify_self_heal_report.json"))
RECOVERY_ROOT = Path(os.environ.get("GRAPHIFY_RECOVERY_DIR", ".graphify_recovery"))
GRAPHIFY_BIN = os.environ.get("GRAPHIFY_BIN", "graphify")
REQUIRED_OUTPUTS = (
    Path("graphify-out/graph.json"),
    Path("graphify-out/GRAPH_REPORT.md"),
    Path("graphify-out/graph.html"),
)

# Only these named strategies can ever be selected from learned memory.
APPROVED_STRATEGIES = {
    "materialize_outputs",
    "rebuild_from_scratch",
    "repair_install_and_rebuild",
    "reinstall_hooks",
}

DEFAULT_STRATEGIES = {
    "command_missing": ["repair_install_and_rebuild", "rebuild_from_scratch"],
    "version_mismatch": ["repair_install_and_rebuild", "rebuild_from_scratch"],
    "missing_outputs": ["materialize_outputs", "rebuild_from_scratch", "repair_install_and_rebuild"],
    "update_failed": ["rebuild_from_scratch", "repair_install_and_rebuild"],
    "extract_failed": ["rebuild_from_scratch", "repair_install_and_rebuild"],
    "cluster_failed": ["rebuild_from_scratch", "repair_install_and_rebuild"],
    "hook_failed": ["reinstall_hooks", "rebuild_from_scratch"],
    "unknown": ["rebuild_from_scratch", "repair_install_and_rebuild"],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run(args: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=check)


def graphify_cmd(*args: str) -> subprocess.CompletedProcess[str]:
    return run([GRAPHIFY_BIN, *args])


def version_text() -> str:
    try:
        proc = graphify_cmd("--version")
    except OSError:
        return ""
    return (proc.stdout or proc.stderr or "").strip()


def version_matches(text: str) -> bool:
    if not text:
        return False
    pattern = rf"(?<!\d){re.escape(PINNED_VERSION)}(?!\d)"
    return re.search(pattern, text) is not None


def outputs_ok() -> bool:
    return all(path.is_file() and path.stat().st_size > 0 for path in REQUIRED_OUTPUTS)


def load_memory(path: Path = MEMORY_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"schema": 1, "updated_at": None, "categories": {}, "history": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("memory root must be an object")
        data.setdefault("schema", 1)
        data.setdefault("categories", {})
        data.setdefault("history", [])
        return data
    except Exception:
        # Corrupt learning state must never stop the grader. Preserve it for diagnosis.
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        corrupt = path.with_name(f"{path.name}.corrupt.{stamp}")
        try:
            path.replace(corrupt)
        except OSError:
            pass
        return {"schema": 1, "updated_at": None, "categories": {}, "history": []}


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


def tail_text(path: Path, limit: int = 16000) -> str:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return raw[-limit:]


def classify_failure(text: str, failure_code: int = 0, reason: str = "") -> str:
    haystack = f"{reason}\n{text}".lower()
    if "command not found" in haystack or "no such file or directory" in haystack and "graphify" in haystack:
        return "command_missing"
    if "version mismatch" in haystack or "unsupported version" in haystack or "pinned version" in haystack:
        return "version_mismatch"
    if "필수 지도 산출물" in haystack or "missing output" in haystack or "graph_report.md" in haystack and "없" in haystack:
        return "missing_outputs"
    if "cluster-only" in haystack and ("fail" in haystack or "error" in haystack or "오류" in haystack):
        return "cluster_failed"
    if "extract" in haystack and ("fail" in haystack or "error" in haystack or "오류" in haystack):
        return "extract_failed"
    if "hook" in haystack and ("fail" in haystack or "error" in haystack or "오류" in haystack):
        return "hook_failed"
    if failure_code in (21, 31) or "update" in haystack and ("fail" in haystack or "error" in haystack or "오류" in haystack):
        return "update_failed"
    if failure_code in (10,):
        return "command_missing"
    if failure_code in (11,):
        return "version_mismatch"
    if failure_code in (22, 32):
        return "extract_failed"
    if failure_code in (23, 33):
        return "cluster_failed"
    if failure_code in (24, 34):
        return "missing_outputs"
    return "unknown"


def learned_order(memory: dict[str, Any], category: str) -> list[str]:
    base = list(DEFAULT_STRATEGIES.get(category, DEFAULT_STRATEGIES["unknown"]))
    category_data = memory.get("categories", {}).get(category, {})
    preferred = category_data.get("preferred_strategy")
    if preferred in APPROVED_STRATEGIES and preferred in base:
        base.remove(preferred)
        base.insert(0, preferred)
    return base


def record_result(
    memory: dict[str, Any], *, category: str, strategy: str, success: bool,
    failure_code: int, reason: str, detail: str,
) -> None:
    categories = memory.setdefault("categories", {})
    item = categories.setdefault(category, {"successes": {}, "failures": {}, "preferred_strategy": None})
    bucket = "successes" if success else "failures"
    item.setdefault(bucket, {})[strategy] = int(item.setdefault(bucket, {}).get(strategy, 0)) + 1
    if success:
        item["preferred_strategy"] = strategy
        item["last_success_at"] = utc_now()
    else:
        item["last_failure_at"] = utc_now()
    item["last_failure_code"] = failure_code

    history = memory.setdefault("history", [])
    history.append({
        "at": utc_now(),
        "category": category,
        "strategy": strategy,
        "success": success,
        "failure_code": failure_code,
        "reason": reason[:300],
        "detail": detail[-1200:],
    })
    del history[:-100]
    memory["updated_at"] = utc_now()


def ensure_pinned_install() -> tuple[bool, str]:
    current = version_text()
    if version_matches(current):
        return True, f"already pinned: {current}"

    spec = f"graphifyy=={PINNED_VERSION}"
    if shutil.which("uv"):
        proc = run(["uv", "tool", "install", "--force", spec])
        detail = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            return False, detail
    else:
        # pipx is the supported fallback. Install it only when absent.
        if not shutil.which("pipx"):
            proc = run([sys.executable, "-m", "pip", "install", "pipx"])
            if proc.returncode != 0:
                return False, (proc.stdout or "") + (proc.stderr or "")
        run([sys.executable, "-m", "pipx", "ensurepath"])
        proc = run([sys.executable, "-m", "pipx", "install", "--force", spec])
        detail = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            return False, detail

    # The current process may need ~/.local/bin added even after install.
    local_bin = str(Path.home() / ".local" / "bin")
    if local_bin not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = local_bin + os.pathsep + os.environ.get("PATH", "")

    current = version_text()
    if not version_matches(current):
        return False, f"version mismatch after repair: {current or 'unavailable'}"
    return True, f"installed pinned version: {current}"


def quarantine_outputs() -> tuple[bool, str]:
    out = Path("graphify-out")
    if not out.exists():
        return True, "no previous graphify-out"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = RECOVERY_ROOT / stamp / "graphify-out"
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(out), str(target))
        return True, f"preserved old outputs at {target}"
    except OSError as exc:
        return False, f"failed to preserve old outputs: {exc}"


def materialize_outputs() -> tuple[bool, str]:
    graph_json = Path("graphify-out/graph.json")
    if not graph_json.is_file() or graph_json.stat().st_size <= 0:
        return False, "graph.json missing; materialize cannot run"
    proc = graphify_cmd("cluster-only", ".", "--no-label")
    detail = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0 and outputs_ok(), detail or "cluster-only completed"


def rebuild_from_scratch() -> tuple[bool, str]:
    ok, preserved = quarantine_outputs()
    if not ok:
        return False, preserved
    proc = graphify_cmd("extract", ".", "--code-only")
    detail = preserved + "\n" + (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return False, detail
    if not outputs_ok():
        proc2 = graphify_cmd("cluster-only", ".", "--no-label")
        detail += "\n" + (proc2.stdout or "") + (proc2.stderr or "")
        if proc2.returncode != 0:
            return False, detail
    return outputs_ok(), detail


def reinstall_hooks() -> tuple[bool, str]:
    proc = graphify_cmd("hook", "install")
    detail = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return False, detail
    status = graphify_cmd("hook", "status")
    detail += "\n" + (status.stdout or "") + (status.stderr or "")
    return status.returncode == 0, detail


def execute_strategy(strategy: str) -> tuple[bool, str]:
    if strategy not in APPROVED_STRATEGIES:
        return False, f"blocked unapproved strategy: {strategy}"
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
    return False, "unknown approved strategy"


def repair(log_path: Path, failure_code: int, reason: str) -> int:
    log_text = tail_text(log_path)
    category = classify_failure(log_text, failure_code=failure_code, reason=reason)
    memory = load_memory()
    strategies = learned_order(memory, category)

    report: dict[str, Any] = {
        "schema": 1,
        "started_at": utc_now(),
        "category": category,
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
            strategy=strategy,
            success=success,
            failure_code=failure_code,
            reason=reason,
            detail=detail,
        )
        atomic_json_write(MEMORY_PATH, memory)
        report["attempts"].append({"strategy": strategy, "success": success, "detail": detail[-2000:]})
        if success:
            # Hook repair is best-effort after a successful map recovery.
            hook_ok, hook_detail = reinstall_hooks()
            report["hook_refresh"] = {"success": hook_ok, "detail": hook_detail[-1200:]}
            report["success"] = True
            report["completed_at"] = utc_now()
            atomic_json_write(REPORT_PATH, report)
            print(f"[Graphify 자가복구] {category} → {strategy} 성공")
            return 0

    report["completed_at"] = utc_now()
    atomic_json_write(REPORT_PATH, report)
    print(f"[Graphify 자가복구] {category} 복구 실패 · 로그/리포트를 확인하세요.", file=sys.stderr)
    return 1


def self_test() -> int:
    assert classify_failure("graphify: command not found") == "command_missing"
    assert classify_failure("required missing output GRAPH_REPORT.md") == "missing_outputs"
    assert classify_failure("extract error") == "extract_failed"
    assert classify_failure("hook error") == "hook_failed"
    memory = {
        "schema": 1,
        "categories": {"update_failed": {"preferred_strategy": "repair_install_and_rebuild"}},
        "history": [],
    }
    order = learned_order(memory, "update_failed")
    assert order[0] == "repair_install_and_rebuild"
    memory["categories"]["update_failed"]["preferred_strategy"] = "rm_everything"
    assert learned_order(memory, "update_failed")[0] != "rm_everything"
    print("Graphify self-heal bounded-learning self-test: OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repair", action="store_true")
    parser.add_argument("--log", default="GRAPHIFY_UPDATE.log")
    parser.add_argument("--failure-code", type=int, default=0)
    parser.add_argument("--reason", default="")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if args.repair:
        return repair(Path(args.log), args.failure_code, args.reason)
    parser.error("use --repair or --self-test")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
