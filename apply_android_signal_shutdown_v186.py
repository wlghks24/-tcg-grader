#!/usr/bin/env python3
from pathlib import Path


def patch_once(path: str, old: str, new: str, label: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"{label}: patch anchor missing")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    patch_once(
        "START_TCG_UPDATER_ANDROID.sh",
        '''WAKE_LOCKED=0\nPAIR_QUEUE_PID=""\n\ncleanup_android_start() {\n  if [ -n "${PAIR_QUEUE_PID:-}" ] && kill -0 "$PAIR_QUEUE_PID" 2>/dev/null; then\n    kill "$PAIR_QUEUE_PID" 2>/dev/null || true\n    wait "$PAIR_QUEUE_PID" 2>/dev/null || true\n  fi\n  if [ "${WAKE_LOCKED:-0}" = "1" ] && command -v termux-wake-unlock >/dev/null 2>&1; then\n    termux-wake-unlock >/dev/null 2>&1 || true\n  fi\n  rm -rf "$START_LOCK_DIR" 2>/dev/null || true\n}\n''',
        '''WAKE_LOCKED=0\nPAIR_QUEUE_PID=""\nSERVER_PID=""\nCLEANUP_RUNNING=0\n\ncleanup_android_start() {\n  # v186: cleanup may be reached from a signal and again from EXIT. Make it\n  # idempotent so children are never signalled twice or a fresh lock removed.\n  if [ "${CLEANUP_RUNNING:-0}" = "1" ]; then\n    return 0\n  fi\n  CLEANUP_RUNNING=1\n\n  # Track the real Python server explicitly. Sending TERM only to the launcher\n  # shell must not leave tcg_updater_v135.py orphaned in the background.\n  if [ -n "${SERVER_PID:-}" ] && kill -0 "$SERVER_PID" 2>/dev/null; then\n    kill -TERM "$SERVER_PID" 2>/dev/null || true\n    for _wait_i in 1 2 3 4 5; do\n      kill -0 "$SERVER_PID" 2>/dev/null || break\n      sleep 1\n    done\n    if kill -0 "$SERVER_PID" 2>/dev/null; then\n      kill -KILL "$SERVER_PID" 2>/dev/null || true\n    fi\n    wait "$SERVER_PID" 2>/dev/null || true\n  fi\n  SERVER_PID=""\n\n  if [ -n "${PAIR_QUEUE_PID:-}" ] && kill -0 "$PAIR_QUEUE_PID" 2>/dev/null; then\n    kill -TERM "$PAIR_QUEUE_PID" 2>/dev/null || true\n    wait "$PAIR_QUEUE_PID" 2>/dev/null || true\n  fi\n  PAIR_QUEUE_PID=""\n\n  if [ "${WAKE_LOCKED:-0}" = "1" ] && command -v termux-wake-unlock >/dev/null 2>&1; then\n    termux-wake-unlock >/dev/null 2>&1 || true\n  fi\n  WAKE_LOCKED=0\n  rm -rf "$START_LOCK_DIR" 2>/dev/null || true\n}\n\nhandle_android_signal() {\n  exit_code="$1"\n  # TERM/INT traps do not exit automatically in bash. Disable traps first,\n  # perform one deterministic cleanup, then exit with the conventional code.\n  trap - EXIT INT TERM HUP\n  cleanup_android_start\n  exit "$exit_code"\n}\n''',
        "Android child PID cleanup",
    )

    patch_once(
        "START_TCG_UPDATER_ANDROID.sh",
        '''acquire_android_start_lock\ntrap cleanup_android_start EXIT INT TERM\n''',
        '''acquire_android_start_lock\ntrap cleanup_android_start EXIT\ntrap 'handle_android_signal 130' INT\ntrap 'handle_android_signal 143' TERM\ntrap 'handle_android_signal 129' HUP\n''',
        "Android signal traps",
    )

    patch_once(
        "START_TCG_UPDATER_ANDROID.sh",
        '''echo "자료수집 자가학습 v142 + 런타임 번들 v143 + OCR v149: 고유출처 검증 + timeout circuit-breaker + 혼합버전 차단"\npython tcg_updater_v135.py\nSERVER_RC=$?\nexit "$SERVER_RC"\n''',
        '''echo "자료수집 자가학습 v142 + 런타임 번들 v143 + OCR v149: 고유출처 검증 + timeout circuit-breaker + 혼합버전 차단"\npython tcg_updater_v135.py &\nSERVER_PID=$!\nwait "$SERVER_PID"\nSERVER_RC=$?\nSERVER_PID=""\nexit "$SERVER_RC"\n''',
        "Android server PID tracking",
    )

    patch_once(
        "test_runtime_delivery_guards.py",
        '''    launcher=text('START_TCG_UPDATER_ANDROID.sh')\n    assert 'PAIR_QUEUE_PID=$!' in launcher\n    assert 'kill "$PAIR_QUEUE_PID"' in launcher\n    assert '혼합 업데이트 상태로 서버를 시작하지 않습니다. INSTALL_MANUAL_OFFICIAL_FALLBACK.sh' not in launcher\n''',
        '''    launcher=text('START_TCG_UPDATER_ANDROID.sh')\n    assert 'PAIR_QUEUE_PID=$!' in launcher\n    assert 'kill -TERM "$PAIR_QUEUE_PID"' in launcher\n    assert 'SERVER_PID=$!' in launcher\n    assert 'kill -TERM "$SERVER_PID"' in launcher\n    assert "trap 'handle_android_signal 130' INT" in launcher\n    assert "trap 'handle_android_signal 143' TERM" in launcher\n    assert "trap 'handle_android_signal 129' HUP" in launcher\n    assert 'trap cleanup_android_start EXIT INT TERM' not in launcher\n    assert '혼합 업데이트 상태로 서버를 시작하지 않습니다. INSTALL_MANUAL_OFFICIAL_FALLBACK.sh' not in launcher\n''',
        "Android signal regression guard",
    )

    print("[OK] v186 Android signal shutdown patch prepared")


if __name__ == "__main__":
    main()
