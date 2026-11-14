#!/usr/bin/env python3
"""V1010 read-only Korean Lenovo/Termux delivery readback.

This checks local evidence only. It cannot fetch GitHub, install updates,
restart the server, or establish physical-tablet/PWA verification.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import tablet_runtime_probe as probe


def _row(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _sha(value: Any) -> str:
    text = str(value or "").lower().strip()
    return text if len(text) == 40 and all(c in "0123456789abcdef" for c in text) else "unknown"


def summarize(report: Any) -> dict[str, Any]:
    """Only independent proofs may become local readback-ready.

    A valid local receipt is NOT a live check against GitHub's main branch,
    and a running SHA is NOT evidence of PWA render/physical restart.
    """
    body = _row(report)
    env = _row(body.get("environment"))
    delivery = _row(body.get("delivery"))
    git = _row(body.get("git"))
    termux = env.get("termux") is True
    disk = _sha(delivery.get("disk_sha"))
    running = _sha(delivery.get("running_sha"))
    saved_remote = _sha(delivery.get("recorded_remote_sha"))
    local_origin = _sha(delivery.get("local_origin_main_sha"))

    code = delivery.get("code_update_status")
    runtime = delivery.get("runtime_status")
    scheduler = delivery.get("scheduler_status")
    if code not in {"LOCAL_MAIN_CHECK_VERIFIED", "MAIN_UPDATE_HOLD", "MAIN_UPDATE_UNVERIFIED"}:
        code = "MAIN_UPDATE_UNVERIFIED"
    if runtime not in {"RUNNING_SHA_VERIFIED_LOCAL_HTTP", "RUNNING_SHA_MISMATCH", "RUNNING_SHA_UNVERIFIED"}:
        runtime = "RUNNING_SHA_UNVERIFIED"
    if scheduler not in {"LOOP_RUNNING_LOCALLY", "LOOP_NOT_VERIFIED"}:
        scheduler = "LOOP_NOT_VERIFIED"

    code_ok = (code == "LOCAL_MAIN_CHECK_VERIFIED"
               and delivery.get("code_update_checked_fresh") is True
               and delivery.get("official_origin_verified") is True
               and git.get("branch") == "main"
               and disk != "unknown" and disk == saved_remote == local_origin)
    runtime_ok = (runtime == "RUNNING_SHA_VERIFIED_LOCAL_HTTP"
                  and body.get("runtime_contract_ok") is True
                  and _row(body.get("health")).get("ok") is True
                  and disk != "unknown" and running == disk)
    loop_ok = scheduler == "LOOP_RUNNING_LOCALLY" and delivery.get("boot_script_present") is True
    ready = (termux and code_ok and runtime_ok and loop_ok
             and delivery.get("ready_for_device_readback") is True)
    missing = []
    if not termux:
        missing.append("termux_environment_not_observed")
    if not code_ok:
        missing.append("local_main_receipt_unverified")
    if not runtime_ok:
        missing.append("running_server_sha_not_verified")
    if not loop_ok:
        missing.append("scheduled_loop_or_termux_boot_unverified")
    if not ready and not missing:
        missing.append("delivery_gate_not_verified")

    if ready:
        status = "READY_FOR_PHYSICAL_CHECK"
    elif runtime == "RUNNING_SHA_MISMATCH":
        status = "OLD_SERVER_RUNNING"
    elif code == "MAIN_UPDATE_HOLD":
        status = "UPDATE_HOLD"
    else:
        status = "READBACK_HOLD"

    return {
        "schema": "tablet-delivery-readback-v1010",
        "status": status,
        "termux_environment_observed": termux,
        "code_update_status": code,
        "runtime_status": runtime,
        "scheduler_status": scheduler,
        "boot_script_present": delivery.get("boot_script_present") is True,
        "disk_sha": disk,
        "recorded_remote_sha": saved_remote,
        "local_origin_main_sha": local_origin,
        "running_sha": running,
        "code_update_checked_fresh": delivery.get("code_update_checked_fresh") is True,
        "ready_for_physical_check": ready,
        "physical_tablet_verified": False,
        "pwa_visual_verified": False,
        "reboot_verified": False,
        "live_github_main_verified": False,
        "device_restart_authorized": False,
        "writes_or_updates_performed": False,
        "missing_evidence": missing,
    }


def render_korean(row: dict[str, Any]) -> str:
    labels = {
        "READY_FOR_PHYSICAL_CHECK": "로컬 실행 확인됨 · 실기기 화면 확인 필요",
        "OLD_SERVER_RUNNING": "코드와 실행 서버 버전 불일치 · 자동 재시작 금지",
        "UPDATE_HOLD": "GitHub main 업데이트 보류 · 기존 데이터 유지",
        "READBACK_HOLD": "태블릿 설치·실행 검증 자료 부족",
    }
    def value(sha: str) -> str:
        return sha[:12] if sha != "unknown" else "확인 안 됨"

    return "\n".join([
        "=== Lenovo 카드 AI 업데이트 · 실행 증빙 (읽기 전용) ===",
        f"상태: {labels[row['status']]}",
        f"환경: {'Termux 감지' if row['termux_environment_observed'] else 'Termux 미확인'}",
        f"main 업데이트 기록: {row['code_update_status']}",
        f"로컬 소스: {value(row['disk_sha'])}",
        f"기록된 원격 main: {value(row['recorded_remote_sha'])}",
        f"로컬 origin/main: {value(row['local_origin_main_sha'])}",
        f"현재 실행 서버: {value(row['running_sha'])} ({row['runtime_status']})",
        f"23시 예약·부팅: {row['scheduler_status']} / {'확인' if row['boot_script_present'] else '미확인'}",
        f"부족한 증빙: {', '.join(row['missing_evidence']) if row['missing_evidence'] else '로컬 조건 충족'}",
        "실제 태블릿 화면·재부팅 검증: 미완료",
        "GitHub 최신 원격 SHA 실시간 확인: 수행 안 함",
        "이 명령은 업데이트·설치·서버 재시작·모델 변경을 수행하지 않습니다.",
    ])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="태블릿 전달 증빙 (읽기 전용)")
    parser.add_argument("--json", action="store_true", help="민감 데이터 없는 기계판독용 요약")
    parser.add_argument("--require-ready", action="store_true",
                        help="로컬 증빙 부족 시 종료코드 2 (실기기 검증 완료 의미 아님)")
    args = parser.parse_args(argv)
    try:
        report = probe.build_report(Path(__file__).resolve().parents[1],
                                    probe_health=True, probe_network=False)
    except (OSError, ValueError, RuntimeError, TypeError) as exc:
        report = {"health": {"ok": False}, "delivery": {},
                  "probe_error": type(exc).__name__}
    row = summarize(report)
    if args.json:
        print(json.dumps(row, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print(render_korean(row))
    return 2 if args.require_ready and not row["ready_for_physical_check"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
