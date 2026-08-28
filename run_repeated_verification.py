#!/usr/bin/env python3
"""Run five or more complete checks and retain safe, auditable recovery history."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from auto_repair_engine import AutoRepairEngine, learn, redact_sensitive
from safe_runtime import env_int, safe_read_text, utc_timestamp as _timestamp
from tcg_updater import save_json_atomic


ROOT = Path(__file__).resolve().parent
REPORT = ROOT / "verification_cycles.json"
HISTORY = ROOT / "verification_history.json"
MEMORY = ROOT / "auto_repair_memory.json"
FINAL_REPORT = ROOT / "FINAL_VERIFICATION_REPORT.json"
RECOVERABLE_FILES = (
    "releases.json",
    "market_watch.json",
    "market_prices.json",
    "promo_events.json",
    "purchase_sources.json",
    "exchange_rates.json",
)


def _latest_run() -> dict:
    try:
        data = json.loads(safe_read_text(HISTORY))
        rows = data.get("runs") if isinstance(data, dict) else None
        return rows[-1] if isinstance(rows, list) and rows and isinstance(rows[-1], dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _history_signature() -> tuple[int, int, int] | None:
    try:
        info = HISTORY.stat()
        return info.st_ino, info.st_size, info.st_mtime_ns
    except OSError:
        return None


def _verified_latest(previous: tuple[int, int, int] | None) -> tuple[dict, str]:
    if _history_signature() == previous:
        return {}, "현재 실행의 새 검사기록이 저장되지 않았습니다."
    latest = _latest_run()
    if not latest:
        return {}, "현재 실행의 검사기록을 읽을 수 없습니다."
    try:
        passed = int(latest.get("pass_count", -1))
        failed = int(latest.get("failure_count", -1))
    except (TypeError, ValueError, OverflowError):
        return {}, "검사기록의 통과/실패 수치가 잘못되었습니다."
    if passed < 1 or failed < 0:
        return {}, "검사기록의 통과/실패 수치가 잘못되었습니다."
    if latest.get("ok") is not True or failed:
        return latest, "최신 검사기록에 실패한 항목이 있습니다."
    return latest, ""


def _save_report(report: dict) -> None:
    save_json_atomic(str(REPORT), report)


def _sync_final_report(cycles: dict, memory: dict) -> bool:
    """Keep the packaged verification summary aligned with the latest run.

    Repeated verification advances the learning memory on every pass.  Updating
    only ``verification_cycles.json`` left the final report with an older
    ``total_runs`` value, which made two public status files disagree.
    """
    try:
        final = json.loads(safe_read_text(FINAL_REPORT))
        if not isinstance(final, dict):
            return False
        verification = final.get("verification")
        error_learning = final.get("error_learning")
        if not all(isinstance(item, dict) for item in (verification, error_learning, memory)):
            return False
        rows = cycles.get("results")
        if not isinstance(rows, list) or not rows:
            return False
        checked_rows = [row for row in rows if isinstance(row, dict)]
        if len(checked_rows) != len(rows):
            return False
        learning_summary = memory.get("learning_summary")
        if not isinstance(learning_summary, dict):
            return False

        final["verified_at"] = str(cycles.get("finished_at") or cycles.get("updated_at") or _timestamp())
        final["result"] = "PASS" if cycles.get("ok") is True else "FAIL"
        verification.update({
            "complete_passes": int(cycles.get("completed_passes", 0)),
            "successful_passes": int(cycles.get("successful_passes", 0)),
            "failed_passes": int(cycles.get("failed_passes", 0)),
            "checks_per_pass": min(int(row.get("checks", 0)) for row in checked_rows),
            "checks_executed": sum(int(row.get("checks", 0)) for row in checked_rows),
        })
        try:
            history = json.loads(safe_read_text(HISTORY))
            history_rows = history.get("runs") if isinstance(history, dict) else []
            verification["history_records_retained"] = len(history_rows) if isinstance(history_rows, list) else 0
        except (OSError, ValueError, TypeError):
            verification["history_records_retained"] = 0

        error_learning.update({
            "memory_version": int(memory.get("version", 4)),
            "total_runs": int(memory.get("total_runs", 0)),
            **{key: int(value) for key, value in learning_summary.items()
               if isinstance(value, int) and not isinstance(value, bool)},
            "new_error_log_count": len(memory.get("new_error_log", []))
                if isinstance(memory.get("new_error_log"), list) else 0,
            "all_existing_groups_resolved": learning_summary.get("unresolved_group_count") == 0,
        })
        save_json_atomic(str(FINAL_REPORT), final)
        return True
    except (OSError, ValueError, TypeError, OverflowError):
        return False


def run_repeated_verification(passes: int = 5) -> dict:
    passes = max(5, min(10, int(passes)))
    timeout = env_int("TCG_VERIFY_TIMEOUT", 180, 30, 600)
    report = {
        "version": 1,
        "engine": "v109-card-identity-ocr-learning",
        "started_at": _timestamp(),
        "requested_passes": passes,
        "completed_passes": 0,
        "successful_passes": 0,
        "failed_passes": 0,
        "ok": False,
        "results": [],
    }
    environment = dict(os.environ)
    environment["PYTHONUTF8"] = "1"
    learning: dict = {}
    for number in range(1, passes + 1):
        print(f"[TCG] verification {number}/{passes} started", flush=True)
        started = time.monotonic()
        previous_history = _history_signature()
        error = ""
        try:
            process = subprocess.run(
                [sys.executable, "-B", "verify_v109_final.py"],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
            ok = process.returncode == 0
            if not ok:
                failed = [line for line in process.stdout.splitlines() if "실패:" in line]
                error = redact_sensitive(" | ".join(failed) or process.stderr or process.stdout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            ok = False
            error = redact_sensitive(f"{type(exc).__name__}: {exc}")

        latest, history_error = _verified_latest(previous_history)
        if history_error:
            ok = False
            error = redact_sensitive(" | ".join(item for item in (error, history_error) if item))
        failed_checks = latest.get("failure_count", 0)
        if not ok and not failed_checks:
            failed_checks = 1
        row = {
            "pass": number,
            "checked_at": _timestamp(),
            "ok": ok,
            "duration_seconds": round(time.monotonic() - started, 3),
            "checks": latest.get("pass_count", 0) + latest.get("failure_count", 0),
            "failed_checks": failed_checks,
            "history_updated": bool(latest),
        }
        if error:
            row["error"] = error
        if not ok:
            recovery = AutoRepairEngine(memory_file=MEMORY, root=ROOT).validate_project_files(list(RECOVERABLE_FILES))
            row["safe_recovery"] = recovery

        learning_results = [
            {
                "file": "verification_history.json",
                "ok": ok,
                "status": "verification passed" if ok else "verification failed",
                **({"error": error} if error else {}),
            }
        ]
        # A complete successful pass inspected every recoverable data file. Feed that
        # evidence back to the learner so two clean passes can close only the matching
        # file states; a failed pass must never create false resolution evidence.
        if ok:
            learning_results.extend(
                {"file": filename, "ok": True, "status": "full verification passed"}
                for filename in RECOVERABLE_FILES
            )
        learning = learn(
            {"finished_at": row["checked_at"], "results": learning_results},
            MEMORY,
        )
        row["learned_runs"] = learning["total_runs"]
        report["results"].append(row)
        report["completed_passes"] = len(report["results"])
        report["successful_passes"] = sum(item["ok"] for item in report["results"])
        report["failed_passes"] = sum(not item["ok"] for item in report["results"])
        report["ok"] = bool(report["results"]) and all(item["ok"] for item in report["results"])
        report["updated_at"] = _timestamp()
        _save_report(report)
        print(
            f"[{'PASS' if ok else 'FAIL'}] verification {number}/{passes}: "
            f"checks={row['checks']} failed_checks={row['failed_checks']}",
            flush=True,
        )

    report["finished_at"] = _timestamp()
    report["ok"] = report["completed_passes"] >= 5 and report["successful_passes"] == report["completed_passes"]
    report["final_report_synced"] = _sync_final_report(report, learning)
    if not report["final_report_synced"]:
        report["ok"] = False
        report["report_sync_error"] = "최종 검증 보고서의 학습 통계를 동기화하지 못했습니다."
    _save_report(report)
    print(
        f"[TCG] complete: {report['successful_passes']}/{passes} passes successful; "
        f"report={REPORT.name}",
        flush=True,
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run at least five complete TCG verification passes.")
    parser.add_argument("--passes", type=int, default=5, help="Number of passes; safely limited to 5 through 10.")
    arguments = parser.parse_args()
    return 0 if run_repeated_verification(arguments.passes)["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
