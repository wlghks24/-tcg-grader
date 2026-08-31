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
  tcg_updater.py \
  tcg_updater_v135.py \
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
    echo "[오류] v142 안전서버 필수파일 누락: $required"
    echo "[안전] 구버전 서버로 폴백하지 않습니다. 최신 설치/갱신 스크립트를 다시 실행하세요."
    exit 1
  fi
done

# Fail early on partial tablet updates. This catches a missing v142 dependency
# before the background server starts and silently loses collection-learning safety.
if ! python - <<'PY' >/dev/null 2>&1
import collection_learning_hardening_v142 as h
status=h.apply()
assert int(status.get('patch') or 0) == 142
assert status.get('unique_evidence_host_counting') is True
assert status.get('strict_official_social_url_match') is True
assert float(status.get('unverified_payload_learning_weight', -1)) == 0.0
assert float(status.get('unverified_search_host_term_learning_weight', -1)) == 0.0
PY
then
  echo "[오류] v142 자료수집·자가학습 보안 모듈 연결 검사 실패"
  echo "[안전] 부분 업데이트 상태로 서버를 시작하지 않습니다."
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
echo "자료수집 자가학습 v142: 고유출처 교차검증 + 미검증 host/검색어 학습 차단 + 공식 SNS URL 엄격검증"
exec python tcg_updater_v135.py
