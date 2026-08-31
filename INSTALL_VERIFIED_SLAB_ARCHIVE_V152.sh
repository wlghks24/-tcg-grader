#!/data/data/com.termux/files/usr/bin/bash
set -eu
cd "$(dirname "$0")"

printf '\n=== 검증완료 등급사진 업체별 통합관리 + RAW 보정학습 v155 ===\n'

if [ ! -d /storage/emulated/0/Download ]; then
  printf '[안내] Android Download 폴더 권한을 확인하지 못했습니다. 필요하면 termux-setup-storage 를 한 번 실행하세요.\n'
fi

python -m unittest -v \
  test_verified_slab_training_archive_v152.py \
  test_manual_proof_archive_status_v153.py \
  test_manual_official_verified_integration_v154.py \
  test_verified_slab_raw_learning_v155.py

printf '\n=== 수동 공식확인 → 공식검증 통합 승격 ===\n'
python manual_official_verified_integration_v154.py

printf '\n=== 공식검증 업체별 보관함 동기화 ===\n'
python verified_slab_training_archive_v152.py --sync

printf '\n=== card-only RAW 결함/등급 보정학습 동기화 ===\n'
python verified_slab_raw_learning_v155.py --sync

pkill -f '[v]erified_slab_training_archive_v152.py --watch' 2>/dev/null || true
pkill -f '[v]erified_slab_raw_learning_v155.py --watch' 2>/dev/null || true
nohup python verified_slab_training_archive_v152.py --watch --interval 30 \
  > TCG_VERIFIED_SLAB_ARCHIVE.log 2>&1 &
printf '%s\n' "$!" > .verified_slab_archive.pid
nohup python verified_slab_raw_learning_v155.py --watch --interval 30 \
  > TCG_VERIFIED_SLAB_RAW_LEARNING.log 2>&1 &
printf '%s\n' "$!" > .verified_slab_raw_learning.pid

mkdir -p "$HOME/.termux/boot"
cat > "$HOME/.termux/boot/start-tcg-verified-archive.sh" <<'EOF'
#!/data/data/com.termux/files/usr/bin/bash
sleep 35
cd "$HOME/-tcg-grader" || exit 1
python manual_official_verified_integration_v154.py >> TCG_VERIFIED_SLAB_ARCHIVE.log 2>&1 || true
python verified_slab_training_archive_v152.py --sync >> TCG_VERIFIED_SLAB_ARCHIVE.log 2>&1 || true
python verified_slab_raw_learning_v155.py --sync >> TCG_VERIFIED_SLAB_RAW_LEARNING.log 2>&1 || true
pkill -f '[v]erified_slab_training_archive_v152.py --watch' 2>/dev/null || true
pkill -f '[v]erified_slab_raw_learning_v155.py --watch' 2>/dev/null || true
nohup python verified_slab_training_archive_v152.py --watch --interval 30 \
  >> TCG_VERIFIED_SLAB_ARCHIVE.log 2>&1 &
nohup python verified_slab_raw_learning_v155.py --watch --interval 30 \
  >> TCG_VERIFIED_SLAB_RAW_LEARNING.log 2>&1 &
EOF
chmod +x "$HOME/.termux/boot/start-tcg-verified-archive.sh"

printf '\n[OK] 수동 공식페이지 일치자료를 공식검증으로 통합관리\n'
printf '[OK] 검증완료 앞면·뒷면에서 슬랩 라벨/바깥 홀더를 제외한 card-only ROI 생성\n'
printf '[OK] card-only ROI의 표면/엣지/코너 특징을 RAW 결함 약한 감독학습에 누적\n'
printf '[OK] 공식등급은 정답으로만 쓰고 raw_pred는 ROI 특징으로 독립 계산\n'
printf '[OK] 업체별 고유 인증번호 20건부터 v135/v99 교차검증 등급보정 후보에 자동 반영\n'
printf '[OK] 동일 인증번호의 순수 RAW 측정자료가 있으면 순수 RAW 자료를 우선\n'
printf '[OK] 자동정리 + RAW학습 감시 시작 (최대 약 30초 내 반영)\n'
printf '[OK] 재부팅 후에도 Termux:Boot에서 자동 시작\n'
printf '[폴더] /storage/emulated/0/Download/TCG등급학습/검증완료\n'
printf '[현황] 검증완료 폴더의 RAW_결함_등급보정_현황.json 확인\n'
printf '[구조] 카드별 front/back/official_proof + raw_card_front_roi/raw_card_back_roi + RAW_학습정보\n'
printf '[포토앱] 검증완료 폴더의 .nomedia 유지\n'
printf '[안전] 숫자 등급만으로 scratch/whitening 종류를 임의 확정하지 않고, 기존 교차검증·하향보정 규칙을 그대로 적용합니다.\n'