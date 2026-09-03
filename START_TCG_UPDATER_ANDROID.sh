#!/data/data/com.termux/files/usr/bin/bash
set -u
cd "$(dirname "$0")"

# Keep exactly one Android launcher/server pair alive. A second manual, boot,
# or recovery start must not kill/rebind the healthy server that is already
# running. The lock survives for the lifetime of this shell and is removed on
# normal exit or signal. Stale locks are recovered automatically.
START_LOCK_DIR=".tcg_android_start.lock"
START_LOCK_PID="$START_LOCK_DIR/pid"
WAKE_LOCKED=0
PAIR_QUEUE_PID=""
SERVER_PID=""
CLEANUP_RUNNING=0

cleanup_android_start() {
  # v186: cleanup may be reached from a signal and again from EXIT. Make it
  # idempotent so children are never signalled twice or a fresh lock removed.
  if [ "${CLEANUP_RUNNING:-0}" = "1" ]; then
    return 0
  fi
  CLEANUP_RUNNING=1

  # Track the real Python server explicitly. Sending TERM only to the launcher
  # shell must not leave tcg_updater_v135.py orphaned in the background.
  if [ -n "${SERVER_PID:-}" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill -TERM "$SERVER_PID" 2>/dev/null || true
    for _wait_i in 1 2 3 4 5; do
      kill -0 "$SERVER_PID" 2>/dev/null || break
      sleep 1
    done
    if kill -0 "$SERVER_PID" 2>/dev/null; then
      kill -KILL "$SERVER_PID" 2>/dev/null || true
    fi
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  SERVER_PID=""

  if [ -n "${PAIR_QUEUE_PID:-}" ] && kill -0 "$PAIR_QUEUE_PID" 2>/dev/null; then
    kill -TERM "$PAIR_QUEUE_PID" 2>/dev/null || true
    wait "$PAIR_QUEUE_PID" 2>/dev/null || true
  fi
  PAIR_QUEUE_PID=""

  if [ "${WAKE_LOCKED:-0}" = "1" ] && command -v termux-wake-unlock >/dev/null 2>&1; then
    termux-wake-unlock >/dev/null 2>&1 || true
  fi
  WAKE_LOCKED=0
  rm -rf "$START_LOCK_DIR" 2>/dev/null || true
}

handle_android_signal() {
  exit_code="$1"
  # TERM/INT traps do not exit automatically in bash. Disable traps first,
  # perform one deterministic cleanup, then exit with the conventional code.
  trap - EXIT INT TERM HUP
  cleanup_android_start
  exit "$exit_code"
}

acquire_android_start_lock() {
  if mkdir "$START_LOCK_DIR" 2>/dev/null; then
    printf '%s\n' "$$" > "$START_LOCK_PID"
    return 0
  fi

  old_pid=""
  if [ -r "$START_LOCK_PID" ]; then
    old_pid="$(cat "$START_LOCK_PID" 2>/dev/null || true)"
  fi
  case "$old_pid" in
    ''|*[!0-9]*) old_pid="" ;;
  esac
  if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
    echo "[OK] TCG Android 서버 시작 작업이 이미 실행 중입니다(PID $old_pid). 중복 시작을 생략합니다."
    exit 0
  fi

  rm -rf "$START_LOCK_DIR" 2>/dev/null || true
  if ! mkdir "$START_LOCK_DIR" 2>/dev/null; then
    echo "[오류] Android 서버 시작 잠금을 만들 수 없습니다. 잠시 후 다시 실행하세요."
    exit 1
  fi
  printf '%s\n' "$$" > "$START_LOCK_PID"
  echo "[복구] 종료된 이전 시작 잠금을 정리했습니다."
}

acquire_android_start_lock
trap cleanup_android_start EXIT
trap 'handle_android_signal 130' INT
trap 'handle_android_signal 143' TERM
trap 'handle_android_signal 129' HUP

# Manual-only graded-photo policy. Child collection processes inherit this
# and therefore cannot make automatic PSA/BGS/CGC/TAG/BRG certification requests.
export TCG_DISABLE_AUTO_GRADER_LOOKUP=1

if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  TCG_BUILD="$(git rev-parse --short=8 HEAD 2>/dev/null || true)"
  TCG_BRANCH="$(git branch --show-current 2>/dev/null || true)"
else
  TCG_BUILD=""
  TCG_BRANCH=""
fi
[ -n "${TCG_BUILD}" ] || TCG_BUILD="local"
[ -n "${TCG_BRANCH}" ] || TCG_BRANCH="unknown"

echo "========================================"
echo " TCG Android 태블릿 서버 시작"
echo " 현재 빌드: ${TCG_BUILD} · 브랜치: ${TCG_BRANCH}"
echo "========================================"

# v167: migrate older Termux:Boot installs that directly relaunched
# `python tcg_updater.py` every 10 seconds. That legacy parent could revive the
# old server after pkill and steal port 8765 while the v135 launcher was still
# running its startup checks.
LEGACY_BOOT_FILE="$HOME/.termux/boot/TCG_AUTO_START.sh"
if [ -f "$LEGACY_BOOT_FILE" ] && grep -Fq 'python tcg_updater.py' "$LEGACY_BOOT_FILE"; then
  echo "[복구] 구형 Android 자동시작 루프를 발견했습니다. v167 단일서버 방식으로 전환합니다."
  pkill -f '[T]CG_AUTO_START.sh' 2>/dev/null || true
  sleep 1
  if [ -s "ANDROID_AUTO_START_INSTALL.sh" ]; then
    bash ANDROID_AUTO_START_INSTALL.sh || {
      echo "[오류] Android 자동시작 v167 전환에 실패했습니다."
      exit 1
    }
  else
    echo "[오류] ANDROID_AUTO_START_INSTALL.sh 파일이 없어 구형 자동시작을 안전하게 전환할 수 없습니다."
    exit 1
  fi
fi

if ! command -v python >/dev/null 2>&1; then
  echo "Python을 처음 설치합니다. 잠시 기다려 주세요."
  pkg update -y || exit 1
  pkg install python -y || exit 1
fi

if ! python -c 'from PIL import Image' >/dev/null 2>&1; then
  echo "사진 검증용 Pillow를 설치합니다..."
  python -m pip install -r requirements.txt || echo "[안내] Pillow 설치를 확인하세요. 서버는 계속 시작합니다."
fi
if ! command -v tesseract >/dev/null 2>&1; then
  echo "라벨 OCR용 Tesseract를 설치합니다..."
  pkg install tesseract -y || echo "[안내] Tesseract 미설치 상태에서는 사진 수집 후 OCR만 보류됩니다."
fi
if command -v tesseract >/dev/null 2>&1; then
  if ! tesseract --list-langs 2>/dev/null | grep -Fxq 'kor'; then
    if [ -s "ensure_tesseract_kor.sh" ]; then
      bash ensure_tesseract_kor.sh || echo "[안내] 한글 OCR 설치를 완료하지 못했습니다. 공식 조회결과 한글 인식만 보류됩니다."
    else
      echo "[안내] ensure_tesseract_kor.sh가 없어 한글 OCR 자동설치를 건너뜁니다."
    fi
  fi
fi

echo "서버를 종료하려면 Ctrl+C를 누르세요."
for required in \
  index.html \
  safe_runtime.py \
  auto_repair_engine.py \
  auto_update_all.py \
  collector_self_healing.py \
  tcg_code_repair_learning.py \
  tcg_updater.py \
  tcg_updater_v135.py \
  runtime_bundle_guard_v143.py \
  update_releases.py \
  update_market_watch.py \
  update_market_prices.py \
  update_promo_events.py \
  update_purchase_sources.py \
  update_exchange_rates.py \
  graded_photo_multi_source.py \
  graded_photo_manual_pair_queue.py \
  grading_cert_verifier.py \
  manual_collection_mode.py \
  manual_graded_photo_registration.py \
  manual_dual_photo_registration.py \
  manual_dual_photo_bridge.js \
  manual_official_proof.py \
  ocr_accuracy_boost_v147.py \
  public_ocr_accuracy_boost_v147.py \
  ocr_front_back_fallback_v148.py \
  legacy_ocr_registry_cleanup_v149.py \
  release_tcg_port.py \
  multi_channel_agent.py \
  search_method_learning.py \
  verified_grade_learning_v135.py \
  verified_grade_learning_v135_safe.py \
  event_collection_hardening_v139.py \
  event_collection_hardening_v140.py \
  event_collection_hardening_v141.py \
  collection_learning_hardening_v142.py \
  event_gap_learning.py \
  event_priority_watch.py \
  event_quick_watch.py \
  social_event_discovery.py \
  multi_route_event_discovery.py \
  adaptive_collection_learner.py \
  fan_social_learning.py; do
  if [ ! -s "$required" ]; then
    echo "[오류] v149 안전서버 필수파일 누락: $required"
    echo "[안전] 구버전/혼합 버전 서버로 폴백하지 않습니다. 최신 설치/갱신 스크립트를 다시 실행하세요."
    exit 1
  fi
done

if ! grep -q 'manual_dual_photo_bridge.js' index.html; then
  echo "[오류] index.html에 앞면+뒷면 수동등록 UI가 설치되지 않았습니다."
  echo "[조치] 로컬 index.html을 직접 수정하지 말고 GitHub main 최신본으로 갱신하세요: bash ANDROID_UPDATE_AND_START.sh"
  exit 1
fi

# Verify semantic contracts, including manual-only grader lookup, game-only
# storage and dual front/back manual upload.
if ! python - <<'PY' >/dev/null 2>&1
import collection_learning_hardening_v142 as learning_guard
import runtime_bundle_guard_v143 as bundle_guard
import manual_collection_mode as manual_mode
import graded_photo_manual_pair_queue as pair_queue
import legacy_ocr_registry_cleanup_v149 as legacy_cleanup
learning=learning_guard.apply()
bundle=bundle_guard.require_compatible()
contracts=bundle.get('contracts',{})
mode=manual_mode.status()
assert int(learning.get('patch') or 0) == 142
assert int(bundle.get('patch') or 0) == 143
assert bundle.get('missing_file_count') == 0
assert bundle.get('issue_count') == 0
assert contracts.get('graded_photo_preflight_allowlisted') is True
assert contracts.get('source_structure_classification') is True
assert contracts.get('search_timeout_circuit_breaker') is True
assert contracts.get('automatic_grader_lookup_disabled') is True
assert contracts.get('manual_registration_auto_lookup_disabled') is True
assert contracts.get('certified_front_back_pair_only') is True
assert mode.get('manual_front_back_upload') is True
assert mode.get('back_stored_separately') is True
assert mode.get('grouped_by_game_only') is True
assert mode.get('grader_subfolders_created') is False
assert legacy_cleanup.PATCH_ID == 149
probe=pair_queue._pair_folder(pair_queue.ANDROID_ROOT,'pokemon','0123456789abcdefabcd')
assert str(probe).endswith('/pokemon/수동등록대기/0123456789abcdefabcd')
assert '/pokemon/PSA/' not in str(probe)
PY
then
  echo "[오류] v149 전체 런타임/앞뒤사진 수동등록 정책 검사 실패"
  echo "[원인] 일부 파일만 최신이거나 앞면+뒷면/OCR 기능이 빠졌을 수 있습니다."
  echo "[안전] 혼합 업데이트 상태로 서버를 시작하지 않습니다. bash ANDROID_UPDATE_AND_START.sh 로 GitHub main을 다시 확인하세요."
  exit 1
fi

# Remove only stale, unverified OCR certification fragments before the server
# exposes them in the manual-official-review UI. Trusted/live-verified rows are
# intentionally left untouched by the cleanup module.
python legacy_ocr_registry_cleanup_v149.py --quiet || {
  echo "[오류] 레거시 OCR 인증번호 정리에 실패했습니다. 안전을 위해 서버를 시작하지 않습니다."
  exit 1
}

if command -v termux-wake-lock >/dev/null 2>&1; then
  if termux-wake-lock; then
    WAKE_LOCKED=1
  fi
fi
if [ -f "storage_optimizer.py" ]; then
  echo "저장공간을 안전하게 최적화합니다..."
  python storage_optimizer.py || echo "[안내] 최적화 일부를 건너뛰고 서버를 시작합니다."
fi

# A legacy `python -m http.server 8765` can remain alive after earlier tablet
# setups. It serves index.html but returns 404 for /api/v135-health, masking the
# real v135 process. Release only same-Termux-user LISTEN sockets on port 8765,
# then keep the legacy-pattern kill as a compatibility fallback.
python release_tcg_port.py || true
pkill -f 'python.*http\.server.*8765' 2>/dev/null || true
pkill -f 'python.*tcg_updater_v135.py' 2>/dev/null || true
pkill -f 'python.*tcg_updater.py' 2>/dev/null || true
sleep 1

pkill -f 'graded_photo_manual_pair_queue.py --watch' 2>/dev/null || true
nohup python graded_photo_manual_pair_queue.py --watch --interval 60 \
  > TCG_MANUAL_PAIR_QUEUE.log 2>&1 &
PAIR_QUEUE_PID=$!
echo "등급사진 수동대기 자동분류 시작: 인증번호+앞뒤사진만 pokemon/onepiece/naruto 게임별 저장"

echo "로컬 서버를 먼저 시작합니다. 자료 수집은 서버 안에서 안전하게 순차 실행됩니다."
echo "등급학습 안전게이트 사용: 공식인증 + RAW 원시예측 + 교차검증 + 하향보정만"
echo "수동등록 정책: 앞면+뒷면 2장 필수 · 앞면 OCR · 뒷면 별도 증빙 저장"
echo "등급사진 정책: 자동 등급사 조회 OFF · 공식사이트 직접확인/수동등록 · 인증번호+앞뒤사진만 게임폴더에 보관"
echo "자료수집 자가학습 v142 + 런타임 번들 v143 + OCR v149: 고유출처 검증 + timeout circuit-breaker + 혼합버전 차단"
python tcg_updater_v135.py &
SERVER_PID=$!
wait "$SERVER_PID"
SERVER_RC=$?
SERVER_PID=""
exit "$SERVER_RC"
