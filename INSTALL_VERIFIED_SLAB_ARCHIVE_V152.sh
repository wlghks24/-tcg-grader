#!/data/data/com.termux/files/usr/bin/bash
set -eu
cd "$(dirname "$0")"

printf '\n=== 검증완료 등급사진 업체별 자동정리 v152 ===\n'

if [ ! -d /storage/emulated/0/Download ]; then
  printf '[안내] Android Download 폴더 권한을 확인하지 못했습니다. 필요하면 termux-setup-storage 를 한 번 실행하세요.\n'
fi

python -m unittest -v test_verified_slab_training_archive_v152.py
python verified_slab_training_archive_v152.py --sync

pkill -f '[v]erified_slab_training_archive_v152.py --watch' 2>/dev/null || true
nohup python verified_slab_training_archive_v152.py --watch --interval 60 \
  > TCG_VERIFIED_SLAB_ARCHIVE.log 2>&1 &
printf '%s\n' "$!" > .verified_slab_archive.pid

mkdir -p "$HOME/.termux/boot"
cat > "$HOME/.termux/boot/start-tcg-verified-archive.sh" <<'EOF'
#!/data/data/com.termux/files/usr/bin/bash
sleep 35
cd "$HOME/-tcg-grader" || exit 1
pkill -f '[v]erified_slab_training_archive_v152.py --watch' 2>/dev/null || true
nohup python verified_slab_training_archive_v152.py --watch --interval 60 \
  >> TCG_VERIFIED_SLAB_ARCHIVE.log 2>&1 &
EOF
chmod +x "$HOME/.termux/boot/start-tcg-verified-archive.sh"

printf '\n[OK] 자동정리 감시 시작\n'
printf '[OK] 재부팅 후에도 Termux:Boot에서 자동 시작\n'
printf '[폴더] /storage/emulated/0/Download/TCG등급학습/검증완료\n'
printf '[구조] PSA/BGS/CGC/TAG/BRG → pokemon/onepiece/naruto → 카드별 앞면·뒷면·학습정보\n'
printf '[포토앱] 검증완료 폴더에는 .nomedia를 두어 관리용 복사본이 Photos/Gallery에 다시 섞이지 않게 합니다.\n'
printf '[학습] 검증완료 슬랩은 참고학습 전용이며 RAW 등급 보정값에는 직접 사용하지 않습니다.\n'
