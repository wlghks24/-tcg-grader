#!/data/data/com.termux/files/usr/bin/bash
set -eu
cd "$(dirname "$0")"

printf '\n=== 검증완료 등급사진 업체별 통합관리 v154 ===\n'

if [ ! -d /storage/emulated/0/Download ]; then
  printf '[안내] Android Download 폴더 권한을 확인하지 못했습니다. 필요하면 termux-setup-storage 를 한 번 실행하세요.\n'
fi

python -m unittest -v \
  test_verified_slab_training_archive_v152.py \
  test_manual_proof_archive_status_v153.py \
  test_manual_official_verified_integration_v154.py

printf '\n=== 수동 공식확인 → 공식검증 통합 승격 ===\n'
python manual_official_verified_integration_v154.py

printf '\n=== 공식검증 업체별 보관함 동기화 ===\n'
python verified_slab_training_archive_v152.py --sync

pkill -f '[v]erified_slab_training_archive_v152.py --watch' 2>/dev/null || true
nohup python verified_slab_training_archive_v152.py --watch --interval 30 \
  > TCG_VERIFIED_SLAB_ARCHIVE.log 2>&1 &
printf '%s\n' "$!" > .verified_slab_archive.pid

mkdir -p "$HOME/.termux/boot"
cat > "$HOME/.termux/boot/start-tcg-verified-archive.sh" <<'EOF'
#!/data/data/com.termux/files/usr/bin/bash
sleep 35
cd "$HOME/-tcg-grader" || exit 1
python manual_official_verified_integration_v154.py >> TCG_VERIFIED_SLAB_ARCHIVE.log 2>&1 || true
pkill -f '[v]erified_slab_training_archive_v152.py --watch' 2>/dev/null || true
nohup python verified_slab_training_archive_v152.py --watch --interval 30 \
  >> TCG_VERIFIED_SLAB_ARCHIVE.log 2>&1 &
EOF
chmod +x "$HOME/.termux/boot/start-tcg-verified-archive.sh"

printf '\n[OK] 수동 공식페이지 일치자료를 공식검증으로 통합관리\n'
printf '[OK] 자동정리 감시 시작 (등록목록 변경 시 최대 약 30초 내 반영)\n'
printf '[OK] 재부팅 후에도 Termux:Boot에서 자동 시작\n'
printf '[폴더] /storage/emulated/0/Download/TCG등급학습/검증완료\n'
printf '[구조] PSA/BGS/CGC/TAG/BRG → pokemon/onepiece/naruto → 카드별 앞면·뒷면·공식확인·학습정보\n'
printf '[포토앱] 검증완료 폴더에는 .nomedia를 두어 관리용 복사본이 Photos/Gallery에 다시 섞이지 않게 합니다.\n'
printf '[학습] 공식검증 슬랩은 검증자료로 통합관리하지만 RAW 카드 결함/등급 보정값에는 직접 사용하지 않습니다.\n'