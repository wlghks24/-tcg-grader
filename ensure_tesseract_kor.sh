#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

# Termux's current tesseract package ships English traineddata only.
# Korean is installed from an immutable tesseract-ocr/tessdata_fast commit.
# The exact file size and Git blob object id are verified before installation so
# an upstream branch move, partial download, or substituted payload fails closed.

if ! command -v tesseract >/dev/null 2>&1; then
  echo "[OCR] Tesseract가 없어 먼저 설치합니다."
  pkg install tesseract -y
fi

PREFIX_DIR="${PREFIX:-/data/data/com.termux/files/usr}"
TESSDATA_DIR="$PREFIX_DIR/share/tessdata"
TARGET="$TESSDATA_DIR/kor.traineddata"
UPSTREAM_COMMIT="87416418657359cb625c412a48b6e1d6d41c29bd"
EXPECTED_BLOB_SHA1="60986d44497689f3abace0b148199476d93292e1"
EXPECTED_SIZE="1677415"
URL="https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/${UPSTREAM_COMMIT}/kor.traineddata"
TMP="$TARGET.download.$$"

mkdir -p "$TESSDATA_DIR"
rm -f -- "$TMP"
trap 'rm -f -- "$TMP"' EXIT HUP INT TERM

verify_blob() {
  python - "$1" "$EXPECTED_SIZE" "$EXPECTED_BLOB_SHA1" <<'PY'
from pathlib import Path
import hashlib
import sys

path = Path(sys.argv[1])
expected_size = int(sys.argv[2])
expected_blob = sys.argv[3].strip().lower()
if path.is_symlink() or not path.is_file():
    raise SystemExit("not a regular non-symlink file")
data = path.read_bytes()
if len(data) != expected_size:
    raise SystemExit(f"size mismatch: {len(data)} != {expected_size}")
header = f"blob {len(data)}\0".encode("ascii")
actual_blob = hashlib.sha1(header + data).hexdigest()
if actual_blob != expected_blob:
    raise SystemExit(f"Git blob mismatch: {actual_blob} != {expected_blob}")
print(f"verified bytes={len(data)} git_blob_sha1={actual_blob}")
PY
}

if [ -L "$TARGET" ]; then
  echo "[오류] kor.traineddata 대상이 심볼릭 링크입니다. 안전을 위해 자동 설치를 중단합니다."
  exit 1
fi

# Do not trust presence alone. Older/unpinned data is accepted only when its
# exact immutable upstream bytes match the pinned artifact.
if [ -f "$TARGET" ] && verify_blob "$TARGET" >/dev/null 2>&1; then
  if tesseract --list-langs 2>/dev/null | grep -Fxq 'kor'; then
    echo "[OK] Tesseract 한글 OCR(kor) 무결성 확인 완료"
    exit 0
  fi
fi

echo "[OCR] 고정된 공식 Tesseract 한글 학습자료(kor)를 설치합니다..."
python - "$URL" "$TMP" "$EXPECTED_SIZE" "$EXPECTED_BLOB_SHA1" <<'PY'
from pathlib import Path
import hashlib
import os
import sys
import urllib.parse
import urllib.request

url, target = sys.argv[1], Path(sys.argv[2])
expected_size = int(sys.argv[3])
expected_blob = sys.argv[4].strip().lower()
parsed = urllib.parse.urlsplit(url)
if parsed.scheme != "https" or parsed.hostname != "raw.githubusercontent.com":
    raise SystemExit("unexpected OCR model download origin")

request = urllib.request.Request(url, headers={"User-Agent": "TCG-Grader-Termux/290"})
with urllib.request.urlopen(request, timeout=45) as response:
    final = urllib.parse.urlsplit(response.geturl())
    if final.scheme != "https" or final.hostname != "raw.githubusercontent.com":
        raise SystemExit("unexpected OCR model redirect origin")
    data = response.read(expected_size + 1)

if len(data) != expected_size:
    raise SystemExit(f"download size mismatch: {len(data)} != {expected_size}")
header = f"blob {len(data)}\0".encode("ascii")
actual_blob = hashlib.sha1(header + data).hexdigest()
if actual_blob != expected_blob:
    raise SystemExit(f"download Git blob mismatch: {actual_blob} != {expected_blob}")

flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
if hasattr(os, "O_NOFOLLOW"):
    flags |= os.O_NOFOLLOW
fd = os.open(target, flags, 0o600)
try:
    with os.fdopen(fd, "wb", closefd=True) as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
except Exception:
    try:
        target.unlink()
    except OSError:
        pass
    raise
print(f"[OCR] 다운로드/무결성 확인 완료: {len(data):,} bytes, git-blob {actual_blob}")
PY

verify_blob "$TMP"

# Rename occurs only after exact content verification and within the same
# tessdata directory, so the final replacement is atomic on the normal Termux
# filesystem. A symlink target is rejected above instead of followed.
mv -f -- "$TMP" "$TARGET"
chmod 644 "$TARGET"
verify_blob "$TARGET" >/dev/null

if ! tesseract --list-langs 2>/dev/null | grep -Fxq 'kor'; then
  rm -f -- "$TARGET"
  echo "[오류] 검증된 kor.traineddata를 설치했지만 Tesseract가 인식하지 못했습니다."
  exit 1
fi

trap - EXIT HUP INT TERM
echo "[OK] Tesseract 한글 OCR(kor) 고정 버전 설치 완료"
tesseract --list-langs 2>/dev/null | grep -E '^(eng|kor)$' || true
