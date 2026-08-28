#!/usr/bin/env python3
"""Current release gate for v107 with a portable no-Node end-user mode."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from safe_runtime import safe_read_text, utc_timestamp
from tcg_updater import save_json_atomic


ROOT = Path(__file__).resolve().parent
HISTORY = ROOT / "verification_history.json"
REPORT = ROOT / "V107_CURRENT_VERIFICATION.json"
VERSION = "v107-full-audit-hardened"
SUITES = (
    ("Python 전체 문법", [sys.executable, "-m", "compileall", "-q", "."]),
    ("v107 서버·PWA 통합", [sys.executable, "verify_v107_runtime_integration.py"]),
    ("화면·링크 런타임", [sys.executable, "verify_link_runtime.py"]),
    ("24개 기능 계약", [sys.executable, "feature_contract.py"]),
    ("전체 코드·자료 감사", [sys.executable, "verify_v107_code_audit.py"]),
    ("SNS·Google 수집", [sys.executable, "verify_v105_social_sources.py"]),
    ("브라우저 런타임", ["node", "verify_browser_runtime.js"]),
    ("카메라 런타임", ["node", "verify_camera_runtime.js"]),
    ("서비스워커 런타임", ["node", "verify_service_worker_runtime.js"]),
    ("비전 런타임", ["node", "verify_vision_runtime.js"]),
    ("5개 감정사 브라우저 정확도", ["node", "verify_v99_browser_accuracy.js"]),
    ("5개 감정사 교차런타임", [sys.executable, "verify_v99_cross_runtime.py"]),
    ("등급 학습 파이프라인", [sys.executable, "verify_v99_learning_pipeline.py"]),
    ("시세 출처 회귀", [sys.executable, "verify_v103_market_sources.py"]),
    ("eBay 등급학습 회귀", [sys.executable, "verify_v102_provider_learning.py"]),
    ("비전 보정 회귀", [sys.executable, "verify_vision_calibration.py"]),
    ("격리 고장주입·자가복구", [sys.executable, "verify_fault_injection_healing.py"]),
)
NODE_REQUIRED_SUITES = {
    "브라우저 런타임", "카메라 런타임", "서비스워커 런타임", "비전 런타임",
    "5개 감정사 브라우저 정확도", "5개 감정사 교차런타임",
    "격리 고장주입·자가복구",
}


def _bounded_output(value: str) -> str:
    clean = "\n".join(line.strip() for line in value.splitlines() if line.strip())
    return clean[-4000:]


def _record_history(result: dict) -> None:
    try:
        history = json.loads(safe_read_text(HISTORY))
        if not isinstance(history, dict):
            history = {}
    except (OSError, ValueError, TypeError):
        history = {}
    runs = history.get("runs")
    if not isinstance(runs, list):
        runs = []
    row = {
        "checked_at": result["checked_at"],
        "ok": result["ok"],
        "pass_count": result["passed"],
        "failure_count": result["failed"],
        "checks": [
            {"name": item["name"], "ok": item["ok"], "detail": item["detail"]}
            for item in result["suites"]
        ],
        "release_gate": VERSION,
    }
    runs.append(row)
    runs = runs[-24:]
    history.update({
        "version": max(5, int(history.get("version", 5) or 5)),
        "updated_at": result["checked_at"],
        "retention_limit": 24,
        "full_detail_limit": 8,
        "lifetime_runs": int(history.get("lifetime_runs", 0) or 0) + 1,
        "lifetime_passed_checks": int(history.get("lifetime_passed_checks", 0) or 0) + result["passed"],
        "lifetime_failed_checks": int(history.get("lifetime_failed_checks", 0) or 0) + result["failed"],
        "pruned_runs": int(history.get("pruned_runs", 0) or 0) + max(0, len(history.get("runs", [])) + 1 - len(runs)),
        "runs": runs,
    })
    save_json_atomic(str(HISTORY), history)


def main() -> dict:
    rows = []
    node_available = shutil.which("node") is not None
    require_node = os.environ.get("TCG_REQUIRE_NODE", "").strip().lower() in {"1", "true", "yes", "on"}
    for name, command in SUITES:
        if name in NODE_REQUIRED_SUITES and not node_available:
            ok = not require_node
            rows.append({
                "name": name, "ok": ok, "skipped": not require_node,
                "detail": "Node.js 미설치로 건너뜀" if ok else "개발 검증은 Node.js가 필요함",
            })
            print(f"[{'SKIP' if ok else 'FAIL'}] {name}: Node.js 없음", flush=True)
            continue
        try:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                check=False,
            )
            ok = completed.returncode == 0
            output = _bounded_output(completed.stdout if ok else completed.stderr or completed.stdout)
            detail = "통과" if ok else (output or f"종료코드 {completed.returncode}")
        except (OSError, subprocess.TimeoutExpired) as exc:
            ok = False
            detail = f"{type(exc).__name__}: {exc}"
        rows.append({"name": name, "ok": ok, "skipped": False, "detail": detail})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}", flush=True)

    result = {
        "version": VERSION,
        "checked_at": utc_timestamp(),
        "ok": all(row["ok"] for row in rows),
        "passed": sum(row["ok"] and not row.get("skipped") for row in rows),
        "failed": sum(not row["ok"] for row in rows),
        "skipped": sum(bool(row.get("skipped")) for row in rows),
        "node_available": node_available,
        "strict_node_required": require_node,
        "suites": rows,
    }
    save_json_atomic(str(REPORT), result)
    _record_history(result)
    print(json.dumps({key: result[key] for key in ("version", "checked_at", "ok", "passed", "failed", "skipped")}, ensure_ascii=False))
    return result


if __name__ == "__main__":
    raise SystemExit(0 if main()["ok"] else 1)
