#!/data/data/com.termux/files/usr/bin/bash
set -u
cd "$(dirname "$0")"

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

echo "서버를 종료하려면 Ctrl+C를 누르세요."
for required in \
  index.html \
  safe_runtime.py \
  auto_repair_engine.py \
  auto_update_all.py \
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
    echo "[오류] v143 안전서버 필수파일 누락: $required"
    echo "[안전] 구버전/혼합 버전 서버로 폴백하지 않습니다. 최신 설치/갱신 스크립트를 다시 실행하세요."
    exit 1
  fi
done

# v143: filenames alone are not enough. Verify semantic contracts that directly
# correspond to the collector failures shown in the runtime dashboard.
if ! python - <<'PY' >/dev/null 2>&1
import collection_learning_hardening_v142 as learning_guard
import runtime_bundle_guard_v143 as bundle_guard
learning=learning_guard.apply()
bundle=bundle_guard.require_compatible()
assert int(learning.get('patch') or 0) == 142
assert int(bundle.get('patch') or 0) == 143
assert bundle.get('missing_file_count') == 0
assert bundle.get('issue_count') == 0
assert bundle.get('contracts',{}).get('graded_photo_preflight_allowlisted') is True
assert bundle.get('contracts',{}).get('source_structure_classification') is True
assert bundle.get('contracts',{}).get('search_timeout_circuit_breaker') is True
PY
then
  echo "[오류] v143 전체 런타임 호환성/자료수집 자가학습 보안 검사 실패"
  echo "[원인] 일부 파일만 최신이고 실제 수집기·복구기·검색학습기가 구버전일 수 있습니다."
  echo "[안전] 혼합 업데이트 상태로 서버를 시작하지 않습니다. INSTALL_GRADE_LEARNING_V135.sh를 다시 실행하세요."
  exit 1
fi

if command -v termux-wake-lock >/dev/null 2>&1; then
  termux-wake-lock || true
  trap 'termux-wake-unlock >/dev/null 2>&1 || true' EXIT INT TERM
fi
if [ -f "storage_optimizer.py" ]; then
  echo "저장공간을 안전하게 최적화합니다..."
  python storage_optimizer.py || echo "[안내] 최적화 일부를 건너뛰고 서버를 시작합니다."
fi

echo "로컬 서버를 먼저 시작합니다. 자료 수집은 서버 안에서 안전하게 순차 실행됩니다."
echo "등급학습 안전게이트 사용: 공식인증 + RAW 원시예측 + 교차검증 + 하향보정만"
echo "자료수집 자가학습 v142 + 런타임 번들 v143: 고유출처 검증 + timeout circuit-breaker + 혼합버전 차단"
exec python tcg_updater_v135.py
